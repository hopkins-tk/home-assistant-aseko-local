#!/usr/bin/env python3
"""Tools for analysing and test-generating Aseko fw v8 text frames.

Usage:
    python3 v8_tools.py --annotate   '{v1 110203680 ...}'
    python3 v8_tools.py --generateTest '{v1 110203680 ...}'

The frame argument must be the full text of a v8 frame including braces.
Surrounding whitespace and the trailing newline are stripped automatically.
"""

import re
import sys

# ---------------------------------------------------------------------------
# Known field mapping: section -> {index: (field_name, description)}
# ---------------------------------------------------------------------------
FIELD_MAP: dict[str, dict[int, tuple[str, str]]] = {
    "ins": {
        0: ("water_temperature", "/ 10 -> degC  (-500 = absent)"),
        8: ("water_flow_to_probes", "bool (1 = flowing)"),
        13: ("?", "unknown -- varies between frames"),
        14: ("?", "unknown -- varies between frames"),
        15: ("?", "unknown -- varies between frames"),
        16: ("timestamp_hour", "local hour from device clock"),
        17: ("timestamp_minute", "local minute from device clock"),
    },
    "ains": {
        0: ("ph", "/ 100 -> pH value  (-500 = absent)"),
        1: ("ph_duplicate?", "identical to ains[0]"),
        2: ("?", "unknown -- consistently ~5 below ains[6]"),
        3: ("redox_x10?", "= ains[6] * 10  (/ 10 -> same mV)"),
        6: ("redox", "direct mV  (-500 = absent)"),
        7: ("redox_duplicate?", "identical to ains[6]"),
    },
    "outs": {
        0: ("cl_pump_running?", "unconfirmed"),
        1: ("ph_minus_pump_running?", "unconfirmed"),
        2: ("filtration_pump_running", "bool"),
    },
    "areqs": {
        0: ("required_ph", "/ 10 -> pH setpoint"),
        1: ("required_redox", "* 10 -> mV setpoint"),
        14: ("pool_volume", "m3"),
        17: ("delay_after_startup", "minutes"),
        18: ("delay_after_dose", "minutes"),
    },
}

SENTINEL = -500  # v8 absent-probe marker


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_v8_frame(text: str) -> tuple[dict, dict[str, list[int]]]:
    """Parse a raw v8 frame string.

    Returns:
        header   -- dict with keys: serial, f2, f3, f4
        sections -- dict of {section_name: [int, ...]}
    Raises ValueError on parse failure.
    """
    text = text.strip()
    if not text.startswith("{") or "}" not in text:
        raise ValueError("Frame must start with '{' and contain '}'")
    body = text.lstrip("{").rstrip("\n").rstrip("}").strip()

    m = re.match(r"v1\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", body)
    if not m:
        raise ValueError(f"Header not recognised: {body[:60]!r}")

    header = {
        "serial": int(m.group(1)),
        "f2": int(m.group(2)),
        "f3": int(m.group(3)),
        "f4": int(m.group(4)),
    }

    sections: dict[str, list[int]] = {}
    for sm in re.finditer(r"(\w+):\s*(.*?)(?=\s+\w+:|$)", body, re.DOTALL):
        name = sm.group(1)
        if name == "v1":
            continue
        try:
            sections[name] = [int(v) for v in sm.group(2).split()]
        except ValueError:
            sections[name] = []  # crc16 is hex, not decimal

    return header, sections


# ---------------------------------------------------------------------------
# --annotate
# ---------------------------------------------------------------------------


def cmd_annotate(frame_text: str) -> None:
    """Print a human-readable annotated view of every section."""
    header, sections = parse_v8_frame(frame_text)

    print("=== v8 frame annotation ===\n")
    print(f"  serial = {header['serial']}")
    print(f"  f2     = {header['f2']}   (unknown)")
    print(f"  f3     = {header['f3']}   (unknown)")
    print(f"  f4     = {header['f4']}   (unknown)")
    print()

    for sec_name, values in sections.items():
        if not values:
            print(f"[{sec_name}]  (no integer values -- likely hex crc16)")
            continue

        known = FIELD_MAP.get(sec_name, {})
        print(f"[{sec_name}]")
        print(f"  {'idx':>4}  {'value':>7}  {'field':<30}  description")
        print(f"  {'---':>4}  {'-----':>7}  {'-----':<30}  -----------")
        for i, v in enumerate(values):
            field, desc = known.get(i, ("", ""))
            absent = "  <- ABSENT" if v == SENTINEL else ""
            print(f"  [{i:>2}]  {v:>7}  {field:<30}  {desc}{absent}")
        print()


# ---------------------------------------------------------------------------
# --generateTest
# ---------------------------------------------------------------------------


def cmd_generate_test(frame_text: str) -> None:
    """Output a pytest snippet for this frame."""
    header, sections = parse_v8_frame(frame_text)
    ins = sections.get("ins", [])
    ains = sections.get("ains", [])
    outs = sections.get("outs", [])
    areqs = sections.get("areqs", [])

    def get(lst, i):
        return lst[i] if i < len(lst) else None

    def probe(lst, i):
        v = get(lst, i)
        return None if (v is None or v == SENTINEL) else v

    # Split frame into 70-char chunks for readable bytes literal
    clean = frame_text.strip().rstrip("}") + "}"
    chunks = [clean[i : i + 70] for i in range(0, len(clean), 70)]

    # Compute expected values
    serial = header["serial"]
    temp_raw = probe(ins, 0)
    temp = round(temp_raw / 10, 1) if temp_raw is not None else None
    ph_raw = probe(ains, 0)
    ph = round(ph_raw / 100, 2) if ph_raw is not None else None
    redox = probe(ains, 6)
    filt_raw = get(outs, 2)
    filt = bool(filt_raw) if filt_raw is not None else None
    req_ph_r = get(areqs, 0)
    req_ph = round(req_ph_r / 10, 1) if req_ph_r is not None else None
    req_rx_r = get(areqs, 1)
    req_redox = req_rx_r * 10 if req_rx_r is not None else None
    pool_vol = get(areqs, 14)
    del_start = get(areqs, 17)
    del_dose = get(areqs, 18)
    hour = get(ins, 16)
    minute = get(ins, 17)
    flow_raw = get(ins, 8)
    flow = bool(flow_raw) if flow_raw is not None else None

    print("# --- generated by v8_tools.py --generateTest ---")
    print()
    print("FRAME = (")
    for chunk in chunks:
        print(f'    b"{chunk}"')
    print('    b"\\n"')
    print(")")
    print()
    print()
    print("def test_decoded_frame():")
    print("    device = AsekoV8Decoder.decode(FRAME)")
    print()
    print(f"    assert device.serial_number == {serial}")
    print("    assert device.device_type == AsekoDeviceType.NET")
    print()

    if temp is not None:
        print(f"    # ins[0]={temp_raw}  / 10 = {temp} degC")
        print(f"    assert device.water_temperature == pytest.approx({temp})")
    else:
        print("    # water_temperature: absent (ins[0] == -500)")
        print("    assert device.water_temperature is None")

    if flow is not None:
        print(f"    # ins[8]={flow_raw}")
        print(f"    assert device.water_flow_to_probes is {flow}")

    if hour is not None:
        print(f"    # ins[16]={hour}  ins[17]={minute}")
        print(f"    assert device.timestamp.hour == {hour}")
        print(f"    assert device.timestamp.minute == {minute}")

    print()
    if ph is not None:
        print(f"    # ains[0]={ph_raw}  / 100 = {ph}")
        print(f"    assert device.ph == pytest.approx({ph})")
    else:
        print("    # ph: absent (ains[0] == -500)")
        print("    assert device.ph is None")

    if redox is not None:
        print(f"    # ains[6]={redox}")
        print(f"    assert device.redox == {redox}")
    else:
        print("    # redox: absent (ains[6] == -500)")
        print("    assert device.redox is None")

    print()
    if filt is not None:
        print(f"    # outs[2]={filt_raw}")
        print(f"    assert device.filtration_pump_running is {filt}")

    print()
    if req_ph is not None:
        print(f"    # areqs[0]={req_ph_r}  / 10 = {req_ph}")
        print(f"    assert device.required_ph == pytest.approx({req_ph})")
    if req_redox is not None:
        print(f"    # areqs[1]={req_rx_r}  * 10 = {req_redox} mV")
        print(f"    assert device.required_redox == {req_redox}")
    if pool_vol is not None:
        print(f"    # areqs[14]={pool_vol}")
        print(f"    assert device.pool_volume == {pool_vol}")
    if del_start is not None:
        print(f"    # areqs[17]={del_start}")
        print(f"    assert device.delay_after_startup == {del_start}")
    if del_dose is not None:
        print(f"    # areqs[18]={del_dose}")
        print(f"    assert device.delay_after_dose == {del_dose}")

    # List non-zero unknowns
    unknowns = []
    for sec_name, values in sections.items():
        known = FIELD_MAP.get(sec_name, {})
        for i, v in enumerate(values):
            if i not in known and v != 0 and v != SENTINEL:
                unknowns.append(f"    #   {sec_name}[{i}] = {v}")
    if unknowns:
        print()
        print("    # Unknown / not yet confirmed (non-zero):")
        for line in unknowns:
            print(line)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    func, frame_arg = sys.argv[1], sys.argv[2]

    if func == "--annotate":
        cmd_annotate(frame_arg)
    elif func == "--generateTest":
        cmd_generate_test(frame_arg)
    elif func == "--help":
        print(__doc__)
    else:
        print(f"Unknown function: {func!r}")
        sys.exit(1)
