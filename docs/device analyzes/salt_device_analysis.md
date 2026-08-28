# ASIN AQUA Salt – Reverse Engineering & Implementation Notes

## Device

| Field | Value |
|---|---|
| Model | ASIN AQUA Salt |
| Firmware | 5.x – 7.x |
| Source | PR #87 live captures 2026-04-04; earlier frames 2026-04-02, 2026-04-03; Issue #84 |
| byte[4] | `0x0E` (Redox) or `0x0D` (CLF) or `0x0f` (DOSE) → `(data[4] & 0x0C) == 0x0C` → **SALT** |

---

## Frame Structure

All SALT frames are 120 bytes, split into three 40-byte sub-frames. The sub-frame type is
encoded at byte offset 5 (first sub-frame), 45, and 85:

| Sub-frame | Type byte | Content |
|---|---|---|
| 0–39 | `0x01` | Live sensor data |
| 40–79 | `0x03` | Configuration / setpoints |
| 80–119 | `0x02` | Flow rates / dosing |

---

## byte[4] – Unit Type Detection

`UNIT_TYPE_SALT = 0x0C`. Detection: `(data[4] & 0x0C) == 0x0C`.

Known values observed: `0x0D`, `0x0E`. Both match the SALT mask.

**Convention**: **Bit SET (`1`) = probe ABSENT; bit CLEAR (`0`) = probe PRESENT** (negative/inverted
convention, named `PROBE_X_MISSING` in the code).

| Bit | Mask | Constant | Bit SET (1) means | Bit CLEAR (0) means |
|---|---|---|---|---|
| 0 | `0x01` | `PROBE_REDOX_MISSING` | REDOX probe **absent** | REDOX probe **present** |
| 1 | `0x02` | `PROBE_CLF_MISSING` | CLF probe **absent** | CLF probe **present** |
| 2–3 | `0x0C` | `UNIT_TYPE_SALT` | **SALT type identifier** (both bits must be set) | — |

---

## Byte Map – Sub-frame 1 (live sensor data)

| Byte(s) | Decoded | Notes |
|---|---|---|
| `[0:4]` | Serial number (big-endian) | |
| `[4]` | Unit type + probe flags | `0x0E` or `0x0D` |
| `[5]` | Sub-frame type `0x01` | |
| `[6:12]` | Timestamp (year−2000, month, day, hour, min, sec) | Device clock |
| `[12]` | Dosing-warning bitmask | Usually `0x00` on SALT — see [`home_device_analysis.md`](home_device_analysis.md) §"Dosing warnings & alarms" |
| `[13]` | Alarm bitmask | `0x04` = no flow to probes; see § above |
| `[14:16]` | pH = value / 100 | |
| `[16:18]` | CLF or REDOX (probe-dependent) | CLF: `/100` mg/L; REDOX: `×1` mV |
| `[18:20]` | REDOX (if CLF also present on PROFI-style) | Not applicable on basic SALT |
| `[20]` | Salinity = value / 10 | SALT-specific |
| `[21]` | Electrolyzer power (% or raw) | `0` when electrolyzer not running |
| `[23:25]` | Air temperature = signed value / 10 | °C — see §Air temperature |
| `[25:27]` | Water temperature = value / 10 | °C |
| `[28]` | Water flow to probes | `0xAA` = flowing |
| `[29]` | Actuator bitmask | **See §byte[29]** |
| `[37]` | Third-pump routing (algicide vs. flocculant) | **See §byte[37]** |

---

## Air temperature — byte `[23:25]`

Bytes 23-24 hold the air (ambient) temperature as a 16-bit big-endian two's
complement value, `value / 10` = °C — the same encoding as the water
temperature that follows it in bytes 25-26. The field was previously listed as
"unknown".

**Evidence** — two diagnostics dumps from serial 110194590 (ASIN AQUA Salt,
type byte `0x0d`), both matching the readings shown on the unit:

| Captured | Bytes 23-24 | Air | Bytes 25-26 | Water |
|---|---|---|---|---|
| 2026-08-11 10:33 | `0x0168` = 360 | 36.0 °C | `0x0128` = 296 | 29.6 °C |
| 2026-08-17 18:50 | `0x0134` = 308 | 30.8 °C | `0x0122` = 290 | 29.0 °C |

Both fields move independently, and each raw air value occurs exactly once in
its 120-byte frame, so the offset is unambiguous. Byte 22 stayed `0x18` in both
samples, so this is a plain 16-bit field and not the low half of a 24-bit one.

**Signedness.** Read unsigned, frames from units without an air probe decode to
6513.6 °C (`0xFE70`) and 6502.8 °C (`0xFDC4`); as two's complement the same
bytes read -40.0 °C and -57.2 °C, i.e. an open-circuit temperature input. The
decoder therefore reads the field signed and discards anything outside
-30.0 … 60.0 °C, which filters both sentinels. A genuine sub-zero reading has
not been captured yet, so the cold-weather encoding remains unverified.

`0xFFFF` is rejected up front as the protocol-wide "unspecified" marker — read
signed it would otherwise pass the window as -0.1 °C.

**Scope.** Only SALT is enabled (`AIR_TEMPERATURE_TYPES`). Frames from other
types carry values in these bytes that do not read as an ambient temperature
(e.g. `0x0C3C` = 313.2 °C on a NET unit), so they stay excluded until a dump
from that type is checked against its display.

## byte[29] – Actuator Bitmask

### Confirmed masks

**Source: PR #87 captures 2026-04-04 (55 type-01 frames, two distinct phases)**

| Bit | Mask | Phase | Observed byte[29] | Evidence |
|---|---|---|---|---|
| 3 | `0x08` | Filtration | baseline `0x08` | Set in all active phases (04-04) ✅ |
| 4 | `0x10` | Electrolyzer RIGHT | `0x18 = 0x08\|0x10` | 25 frames (04-04 Phase 4) ✅ |
| 5 | `0x20` | Algicide / Flocculant pump | `0x28 = 0x08\|0x20` | 27 frames (04-04 Phase 2) ✅ |
| 6 | `0x40` | Electrolyzer LEFT (tentative) | `0x58 = 0x08\|0x10\|0x40` | 1 frame (04-02) ⚠️ tentative |

**Key insight**: Algicide and Flocculant both use **the same bit `0x20`**. The third pump
port is a single physical output. The chemical type is determined by `byte[37]`, not by
a separate bit in byte[29].

### Unconfirmed masks

| Bit candidate | Mask | Hypothesis | Status |
|---|---|---|---|
| 7 | `0x80` | pH− pump | ⏳ No frame captured with pH− pump running |

### Pump states are exclusive (not parallel)

The SALT unit has only **one third-pump port**. Algicide and flocculant are mutually
exclusive configurations — the pump cannot run as both simultaneously. The electrolyzer
and algicide/flocculant CAN be active at the same time (each has a separate pump/output).

---

## byte[37] – Third-Pump Routing (Algicide vs. Flocculant)

The SALT unit has one physical pump port that can be configured as either algicide or
flocculant. `byte[37]` encodes which chemical is active:

| byte[37] value | bit 7 | Chemical configured |
|---|---|---|
| `0xb7`, `0xb3` | `1` | **Algicide** (ml/m³/day) |
| `0x37` | `0` | **Flocculant** (ml/h) |
| `0xFF` | N/A | Not configured / NET device |

**Routing rule (Hopkins firmware v7.x)**: `byte[37] & 0x80 == 0x80` → algicide; else → flocculant.

### Firmware variant caution

Issue #84 SALT shows `byte[37] = 0x13` for algicide. Here bit 7 (`0x80`) is **not** set —
the routing bit differs from the v7.x firmware. The two SALT variants encode the chemical
type differently in byte[37].

**Implication**: the `0x80` routing rule is not universally reliable across all SALT
firmware versions. See [byte37_algicide_floc_analysis.md](../temp/byte37_algicide_floc_analysis.md) for
full XOR analysis.

**Note on Period 2 schedule bytes (Issue #133)**: On SALT, the controller keeps
sending the last-configured `start2`/`stop2` times in bytes 60-63 even after
the user disables Period 2 in the controller UI.  Pre-fix, the decoder
gated these fields on `byte[37] & 0x80` and returned `None` for any frame
where the algicide-routing bit was clear — which caused already-registered
entities to flip to "unknown" when the user toggled Period 2 on/off
(Home Assistant protects the entity registry, so the entity stays but
the value is read as `None`).  Post-fix, bytes 60-63 are read
unconditionally for any device in `FILTRATION_TYPES` (SALT included), and
the mode and schedule are decoded from the `byte[37]` bits (see
§byte[37] – filtration mode and schedule below).  Behaviour was originally verified on SALT by
diffing two frames
captured in PR #122 (algicide mode toggle, `0xb3` ↔ `0x33`); the
corresponding behaviour for HOME was confirmed in Issue #133 with
@dtpugh's four diagnostic files (see
[`home_device_analysis.md`](home_device_analysis.md) §"Note on Period 2
schedule bytes (Issue #133)").  NET is excluded because it has no
filtration output.

### byte[37] also contains other fields

`byte[37]` is a packed multi-field byte — it is **not** a pure single-bit flag:

| Comparison | XOR | Bit(s) changed |
|---|---|---|
| Algicide 10 → Algicide 11 (dosage +1) | `0x04` | bit 2 only |
| Algicide 11 → Flocculant 11 (type change) | `0x84` | bit 7 + bit 2 |
| Algicide 10 → Flocculant 11 (both change) | `0x80` | bit 7 only |

Bit 2 (`0x04`) was read here as dosage encoding.  **That reading is
superseded**: `0x04` marks the unit's settings menu, captured directly on an ASIN
AQUA Salt across six byte[37] values and both directions of every transition
(see §byte[37] – filtration mode and schedule below).  The XOR above came
from two frames diffed in PR #122; the dosage change and a mode change most
likely coincided in that pair.  The remaining bits are unconfirmed.

### byte[37] – filtration mode and schedule

`byte[37]` carries **two independent facts** about filtration, and the decoder
keeps them apart because neither can stand in for the other:

| Bits | Meaning | Field |
|---|---|---|
| `0x10` / `0x20` | which schedule is configured | `filtration_schedule` |
| `0x04` | the unit's settings menu is open | `service_menu_open` |

Every combination below was captured on an ASIN AQUA Salt with the mode shown
on the unit itself known, in both directions of each transition:

| `byte[37]` | `service_menu_open` | `filtration_schedule` |
|---|---|---|
| `0xC3` | `False` | `NONSTOP_24H` |
| `0xD3` | `False` | `TIMER_PERIOD_1` |
| `0xF3` | `False` | `TIMER_PERIOD_1_AND_2` |
| `0xC7` | `True` | `NONSTOP_24H` |
| `0xD7` | `True` | `TIMER_PERIOD_1` |
| `0xF7` | `True` | `TIMER_PERIOD_1_AND_2` |

These are the same mode bits HOME firmware B uses; the constant `0xC0` in the
high nibble is SALT's own configuration (`0x80` = algicide routing).

**Bit `0x40` does not select the firmware variant here.** SALT sets it in every
frame, so routing on it sent SALT into the HOME firmware-A branch, where it
matched none of the exact values and came out with no mode at all.  The
firmware-A branch — and the schedule-derived fallback behind it — are therefore
HOME-only.  On SALT the fallback could not help anyway: the filtration times in
bytes 56-63 are reported unchanged in every mode, so deriving the mode from
them would return one constant answer whatever the unit is doing.

**What the bit actually marks.** `0x04` appears the moment the settings menu
is opened on the unit — the menu holding every Aseko setting, and the place
filtration and backwash can be started by hand from.  It is set **before**
anything is touched: three captures labelled "switched to manual mode, did
nothing" carry it.  So on its own the bit says a person is standing at the
unit, and nothing about what they did.

**The unit goes quiet while the menu is open.** Opening it produces exactly
one more frame — the one carrying `0x04` — and then transmission stops until
the user leaves.  Three diagnostics taken during one such session all
contained the same frame, with `online` going false between them.  Two
consequences:

* `service_menu_open` going True is typically the last thing reported before
  the device goes offline, and it stays True until the user comes back out.
  This is correct — it is the last thing the unit actually said.
* What the user *does* in there is not observable.  The pump state in that
  final frame is the state on the way in, not the result.  The unit will not
  let you leave until filtration is back in the state it was in before, so
  the value Home Assistant is holding is right again by the time frames
  resume.

Note this is **not** evidence that the schedule is suspended while the menu
is open: in the 2026-08-11 capture the pump kept running throughout, and the
configured period 1 covered that time of day anyway.

The exception is a by-hand **backwash**: there the unit keeps transmitting
throughout, with `0x04` set from ~30 s before the valve opens until ~20 s
after it closes.  A cycle running while somebody is at the menu the button
lives on is manual by observation, and `backwash_tracker` uses it as such
rather than inferring from the clock — see `_service_menu_open`.

---

## Byte Map – Sub-frame 2 (config / setpoints)

| Byte(s) | Decoded | Notes |
|---|---|---|
| `[52]` | Required pH = value / 10 | |
| `[53]` | Required CLF (mg/L ÷10) or REDOX (×10 mV) | Depends on active probe |
| `[54]` | Required algicide (ml/m³/day) or Required floc (ml/h) | Routed by `byte[37]` |
| `[55]` | Required water temperature (°C) | |
| `[56:58]` | Filtration start1 | HH:MM |
| `[58:60]` | Filtration stop1 | HH:MM |
| `[60:62]` | Filtration start2 | HH:MM | Always populated — see Issue #133 |
| `[62:64]` | Filtration stop2 | HH:MM | Always populated — see Issue #133 |
| `[68]` | Backwash every N days | `0` = disabled |
| `[69:71]` | Backwash time | HH:MM |
| `[71]` | Backwash duration | ×10 seconds |

---

## Byte Map – Sub-frame 3 (flow rates)

| Byte(s) | Decoded | Notes |
|---|---|---|
| `[92:94]` | Pool volume (m³) | |
| `[95]` | Flowrate pH− (ml/min) | Confirmed |
| `[99]` | Flowrate chlorine pump (ml/min) | Not applicable on SALT (no CL pump) |
| `[101]` | Flowrate third-pump slot (ml/min) | 60 ml/min in all captured frames |
| `[103]` | Flowrate third-pump slot (duplicate?) | Also 60 ml/min; does not flip with algicide/floc switch |

**Note on byte[101] vs byte[103]**: Both bytes carry the same flowrate (60 ml/min)
regardless of whether algicide or flocculant is configured. The third pump slot does NOT
split its flowrate across different bytes when switching chemicals — see
[byte37_algicide_floc_analysis.md](../temp/byte37_algicide_floc_analysis.md).

---

## Electrolyzer

The SALT unit has an integrated salt-water electrolysis cell for chlorine production.

| Field | byte | Notes |
|---|---|---|
| `electrolyzer_active` | `[29] & 0x10` | `True` when RIGHT cycle running |
| `electrolyzer_power` | `[21]` | Raw value; `0` when not running |
| `electrolyzer_direction` | `[29]` bits | `0x10` = RIGHT; `0x50 = 0x10|0x40` = LEFT (tentative) |
| `salinity` | `[20]` | g/L, value / 10 |

**Electrolyzer direction**: RIGHT direction is confirmed (`0x10`, 25 frames, Phase 4).
LEFT direction (`0x40`) is tentative — based on a single April 2 frame (`0x58 = 0x08|0x10|0x40`)
where the interpretation of bit `0x40` is uncertain.

---

## Confirmed `ACTUATOR_MASKS` for SALT

```python
AsekoDeviceType.SALT: AsekoActuatorMasks(
    filtration=0x08,             # confirmed ✓ 2026-04-04
    ph_minus=0x80,               # ⏳ unconfirmed – awaiting frame with pH− running
    algicide=0x20,               # confirmed ✓ 2026-04-04 (27 frames)
    flocculant=0x20,             # confirmed ✓ 2026-04-03 (same bit as algicide)
    electrolyzer_running=0x10,   # confirmed ✓ 2026-04-04 (25 frames)
    electrolyzer_running_right=0x10,  # confirmed ✓
    electrolyzer_running_left=0x50,   # ⚠️ tentative – 1 frame only
)
```

---

## Open Questions

| Question | Status |
|---|---|
| pH− pump mask in byte[29]? | ⏳ Candidate `0x80` — consistent with HOME/OXY; awaiting frame |
| Electrolyzer LEFT mask? | ⚠️ Tentative `0x40` — single frame, April 2, 2026 |
| byte[37] full field layout? | ⏳ Bits 0–6 partially known; full semantics not confirmed |
| byte[37] routing for Issue #84 firmware? | ⚠️ `0x13` = algicide but bit 7 NOT set — different firmware variant |
| byte[103] semantics? | ⏳ Always mirrors byte[101] on SALT — may be a duplicate or separate pump |
