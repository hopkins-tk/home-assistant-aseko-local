# ASIN AQUA Profi — Device Analysis

> **Status: inferred from the Aseko Profi manual and the `_make_profi_clf_redox_bytes`
> test fixture. No live capture from a real PROFI device is available yet — every byte
> position below is a hypothesis that must be confirmed against a real frame before
> being treated as fact.**

| Field | Value |
|---|---|
| Model | ASIN AQUA Profi |
| Source | Aseko Profi manual (hardware description); test fixture in `tests/test_sensor.py` |
| byte[4] | `0x10` → `UNIT_TYPE_PROFI` → `AsekoDeviceType.PROFI` |
| `byte37_routes_pump_type` | **False** (PROFI has 5 independent pump ports: CL, pH−, pH+, algicide, flocculant) |

> **Note on PROFI identification** (`aseko_decoder.py`):
>
> ```python
> if data[4] == UNIT_TYPE_PROFI:  # Uncertain
>     return AsekoDeviceType.PROFI
> ```
>
> The `0x10` match is the only fixed identifier today. Probe bits in byte[4] are **not**
> used for PROFI in the way they are for SALT/NET (no `& 0x0C`, no `& 0x08` mask) — the
> PROFI branch in `_configuration` falls through to the generic `probe_info = data[4]`
> path and applies the standard SALT-style PROBE_REDOX_MISSING / PROBE_CLF_MISSING /
> PROBE_DOSE_MISSING bits. This works because the same convention happens to be encoded
> identically in the high nibble (`0x1?` is what real PROFI devices appear to use), but
> the inheritance has not been validated against a real frame.

---

## Hardware Overview (per Aseko Profi manual)

PROFI is the largest of the ASIN AQUA pool controllers. It has **5 independent pump
ports** (no shared/3-port routing like SALT):

| Port | Connected chemical | Setpoint byte | Flowrate byte | pump_running bit in `byte[29]` |
|---|---|---|---|---|
| CL pump | Chlorine (ml/m³/h) or OXY Pure | `byte[53]` | `byte[99]` | `0x40` ⚠️ unconfirmed |
| pH− pump | pH Minus | not yet mapped | `byte[95]` | `0x80` ⚠️ unconfirmed |
| pH+ pump | pH Plus | not yet mapped | `byte[97]` | not yet mapped |
| Algicide pump | Algicide (ml/m³/day) | not yet mapped | not yet mapped | not yet mapped |
| Flocculant pump | Flocculant (ml/h) | not yet mapped | `byte[101]` | `0x20` ⚠️ unconfirmed |

Other notable PROFI hardware (per manual):

- **Water-level input** (capactive probe) — the Aseko Profi manual documents a
  water-level sensor and refill-valve control identical in function to the HOME/SALT/OXY
  implementation. Until a live PROFI frame is captured, the assumption is that the
  byte positions documented in [`water_level_backwash_analysis.md`](../temp/water_level_backwash_analysis.md)
  (bytes 27, 102, 103, 104, 105) are reused 1:1.
- **Heating relay output** (heat-pump or electric-heater demand) — same `byte[29]` bit
  0x04 used by HOME/SALT/OXY.
- **Backwash valve** — same byte positions as HOME/SALT/OXY (bytes 68/69/70/71).
- **5+ probe inputs** — PROFI supports both CLF **and** REDOX probes simultaneously
  (per manual). The current decoder reads `byte[18:20]` for REDOX **only if** the
  `byte[16:18]` value is `0xFFFF` (UNSPECIFIED) — see `_fill_redox_data`.

---

## Frame Structure (assumed, same as other ASIN AQUA units)

All PROFI frames are 120 bytes, split into three 40-byte sub-frames:

| Sub-frame | Type byte | Content |
|---|---|---|
| 0–39 | `0x01` | Live sensor data |
| 40–79 | `0x03` | Configuration / setpoints |
| 80–119 | `0x02` | Flow rates / dosing |

---

## Byte Map – Sub-frame 1 (live sensor data, assumed)

| Byte(s) | Decoded | Confidence | Notes |
|---|---|---|---|
| `[0:4]` | Serial number (big-endian) | ✅ certain | |
| `[4]` | Unit type = `0x10` | ✅ certain | See note on PROFI identification above |
| `[5]` | Sub-frame type `0x01` | assumed | Not validated against a real PROFI frame |
| `[6:12]` | Timestamp | assumed | |
| `[14:16]` | pH = value / 100 | assumed | PROFI has a pH probe (per manual) |
| `[16:18]` | CLF free chlorine (mg/L) if CLF probe present | assumed | PROFI supports CLF |
| `[18:20]` | REDOX (mV) — same byte on PROFI when both CLF and REDOX are installed | assumed | `_fill_redox_data` already special-cases this (reads 16:18 if 18:19 is `0xFFFF`, else 18:20) |
| `[20:22]` | Cl free mV (big-endian) if CLF probe present | assumed | |
| `[25:27]` | Water temperature = value / 10 | assumed | |
| `[27]` | **Water level (cm)** | ⚠️ hypothesis | See §"Water level & refill valve" below |
| `[28]` | Water flow to probes (`0xAA` = flowing) | assumed | |
| `[29]` | Actuator bitmask | assumed structure | See §"byte[29] – Actuator Bitmask" below |
| `[37]` | **Not used for routing on PROFI** (`byte37_routes_pump_type = False`) | ✅ certain | PROFI has 5 independent pump ports |

---

## byte[29] – Actuator Bitmask (assumed)

> **All masks below are placeholders — copied from HOME/OXY because no PROFI frame
> has been captured with individual pumps running.** Each must be confirmed by a
> real frame where only the pump in question is active.

```python
AsekoDeviceType.PROFI: AsekoActuatorMasks(
    filtration=0x08,  # uncertain
    cl=0x40,          # uncertain
    ph_minus=0x80,    # uncertain
    flocculant=0x20,  # uncertain
    byte37_routes_pump_type=False,  # PROFI has 5 independent pump ports
)
```

| Bit candidate | Mask | Hypothesis | Status |
|---|---|---|---|
| 3 | `0x08` | `filtration_pump_running` | ⏳ unconfirmed – assumed same as SALT/HOME/OXY |
| 6 | `0x40` | `cl_pump_running` | ⏳ unconfirmed – assumed same as HOME |
| 7 | `0x80` | `ph_minus_pump_running` | ⏳ unconfirmed – assumed same as HOME |
| 5 | `0x20` | `floc_pump_running` | ⏳ unconfirmed – assumed same as SALT flocculant bit |
| 2 | `0x04` | `heating_active` | ⚠️ partially confirmed – see §"Heating demand" below |
| 1 | `0x02` | `water_filling_active` | ⚠️ partially confirmed – see §"Water level & refill valve" below |

**Open**: `algicide_pump_running` and `ph_plus_pump_running` have no mask assigned yet
on PROFI. They are listed in `AsekoActuatorMasks` as defaults (`0x00`), which means the
corresponding binary sensor entity will be registered but always report `False` until a
real mask is discovered.

---

## Water level & refill valve

> **Confirmed: PROFI has a water-level input and refill-valve output.** This was
> confirmed in PR [#120](https://github.com/hopkins-tk/home-assistant-aseko-local/pull/120)
> review by `@hopkins-tk` and verified against the Aseko Profi manual: PROFI exposes
> the same water-level hardware as HOME/SALT/OXY.

**Before PR #120**: the decoder's `_fill_home_water_level_data` only ran for
`{HOME, SALT, OXY}` (whitelist). PROFI was silently skipped, so the `water_level*` and
`water_filling_active` fields stayed `None` on PROFI devices.

**After PR #120** (commit `34957ea` by `Enrica`, co-authored by `@hopkins-tk`): the
whitelist was replaced with a **blacklist** for `NET` only:

```python
# aseko_decoder.py → _fill_home_water_level_data
if unit.device_type == AsekoDeviceType.NET:
    return  # bytes 102..104 contain unrelated non-FF data on NET devices
```

`NET` is still excluded because real NET captures (see
[`net_device_analysis.md`](net_device_analysis.md)) show:

| Byte | Real NET value | Would-be mis-decoding |
|---|---|---|
| `byte[102]` | `0x01` | `water_level_low_alarm = 1 cm` (false) |
| `byte[103]` | `0x03` | `water_level_filling_on = 3 cm` (false) |
| `byte[104]` | `0x83` | `water_level_filling_off = 131 cm` (false) |
| `byte[105]` | `0xFF` | correctly decoded as `None` |

…so NET really does need the exclusion. PROFI shares the HOME/SALT/OXY byte layout
(per the manual), so it is safe to enable the decoder for PROFI.

**Test impact** (`tests/test_sensor.py::test_async_setup_profi_clf_redox`): one
additional binary sensor — `water_filling_active` — is now registered for PROFI.
The test was updated from `assert == 34` to `assert == 35`, with the comment block
updated to list `water_filling_active` explicitly under "Binary sensors (6)".

**Live confirmation pending**: the current test fixture
(`_make_profi_clf_redox_bytes`) sets `data[29] = 0x08` and all water-level bytes to
`0xFF`, so `water_filling_active = False` and all `water_level_*` fields are `None`.
A real PROFI frame with non-`0xFF` water-level bytes (or a non-zero `0x02` bit in
`byte[29]`) is needed to confirm the entity reports correct values.

---

## Heating demand (assumed same as HOME/SALT/OXY)

`_fill_heating_demand` reads `byte[29]` bit `0x04` for `heating_active`. This is the
same bit position used by HOME/SALT/OXY (see `_fill_heating_demand` in
`aseko_decoder.py`). PROFI exposes a heating relay output per the manual, so the
mapping is expected to be the same.

**Live confirmation pending**.

---

## Backwash & backwash schedule (assumed same as HOME/SALT/OXY)

PROFI is documented in the manual to have a backwash valve. The decoder fills the
backwash fields in `_fill_backwash_active` and `_fill_backwash_schedule` with the
same byte positions as HOME/SALT/OXY:

- `byte[68]` = backwash every N days
- `byte[69:71]` = backwash time (HH:MM)
- `byte[71]` = backwash duration (× 10 s)
- `byte[12]` = backwash active flag (combined with byte[29] bit 0x01 for water-filling
  state — see [`backwash_tracker.py`](../../custom_components/aseko_local/backwash_tracker.py))

`last_backwash` and `next_backwash` are derived (not from raw bytes) and depend on the
[`BackwashTracker`](../../custom_components/aseko_local/backwash_tracker.py) state
across coordinator updates.

**Live confirmation pending**.

---

## Confirmed `ACTUATOR_MASKS` for PROFI (current state)

```python
AsekoDeviceType.PROFI: AsekoActuatorMasks(
    filtration=0x08,             # uncertain – assumed same as HOME/SALT/OXY
    cl=0x40,                    # uncertain – assumed same as HOME
    ph_minus=0x80,              # uncertain – assumed same as HOME
    flocculant=0x20,            # uncertain – assumed same as SALT flocculant bit
    # algicide, ph_plus, oxy, electrolyzer_*: all 0x00 (no mask assigned yet)
    byte37_routes_pump_type=False,  # ✅ certain – PROFI has 5 independent pump ports
)
```

> **The masks above should be treated as best-guess placeholders, not as confirmed
> facts.** Until a real PROFI frame is captured with each pump running individually,
> `cl_pump_running`, `ph_minus_pump_running`, and `floc_pump_running` may report
> incorrectly when the corresponding pump is active.

---

## `required_*` setpoint bytes on PROFI

`_fill_required_data` (`aseko_decoder.py`):

| Field | Byte | PROFI behaviour | Confidence |
|---|---|---|---|
| `required_ph` | `byte[52]` | Set if pH probe present | assumed |
| `required_cl_free` | `byte[53]` | Set if CLF probe present (`/10`) | assumed |
| `required_redox` | `byte[53]` | **Skipped on PROFI** (not `× 10`) | ✅ certain — `_fill_required_data` has an explicit `unit.device_type != AsekoDeviceType.PROFI` guard. PROFI's REDOX setpoint uses a different scaling (raw mV, not × 10); the decoder does not expose it today. |
| `required_algicide` | `byte[54]` | Not assigned on PROFI (no byte[37] routing, and the OXY/HOME branch that reads `byte[72]` is not entered for PROFI) | ✅ certain by code inspection, ⚠️ byte position **unconfirmed** — see Open Questions |
| `required_floc` | `byte[54]` | Not assigned on PROFI (same reason as above) | ✅ certain by code inspection, ⚠️ byte position **unconfirmed** |

The test `test_async_setup_profi_clf_redox` explicitly asserts
`not any(... == "required_floc" ...)` to document the gap.

---

## `flowrate_*` bytes on PROFI

`_fill_flowrate_data` falls through to the **SALT/NET/PROFI** branch on PROFI:

```python
# SALT / NET / PROFI: byte[99] = chlorine pump flowrate.
unit.flowrate_chlor = AsekoDecoder._normalize_value(data[99], int)

# byte[101]: shared "third pump slot" — algicide OR flocculant per byte[37].
# 0xFF (UNSPECIFIED) → leave both as None.
if data[37] != UNSPECIFIED_VALUE and bool(
    data[37] & AsekoThirdPumpSlot.SALT_ALGICIDE_ROUTING
):
    unit.flowrate_algicide = AsekoDecoder._normalize_value(data[101], int)
elif data[37] != UNSPECIFIED_VALUE:
    unit.flowrate_floc = AsekoDecoder._normalize_value(data[101], int)
```

**Implication for PROFI**: PROFI has 5 independent pump ports but the decoder currently
treats `byte[101]` as a shared slot routed by `byte[37]`. With the test fixture's
`byte[37] = 0x00` (flocculant mode), this populates `flowrate_floc` correctly **by
accident**. The PROFI branch in `_fill_flowrate_data` should be split out into its own
early-return (like OXY and HOME) once the correct byte positions are confirmed.

**Byte positions assumed but unconfirmed**:

| Field | Byte | Status |
|---|---|---|
| `flowrate_chlor` | `byte[99]` | assumed (shared with SALT/NET) |
| `flowrate_ph_minus` | `byte[95]` | assumed (shared with SALT/NET/HOME/OXY) |
| `flowrate_ph_plus` | `byte[97]` | assumed (no decoder branch reads it today) |
| `flowrate_algicide` | `byte[101]` if `byte[37] & 0x80` | ⛔ wrong on PROFI — should be its own byte |
| `flowrate_floc` | `byte[101]` if `byte[37] & 0x80 == 0` | ⛔ wrong on PROFI — should be its own byte |

---

## Open Questions (all require a real PROFI frame to resolve)

| # | Question | Status | Action |
|---|---|---|---|
| 1 | PROFI probe bits in `byte[4]` (CLF-missing, REDOX-missing, DOSE-missing) — same convention as SALT? | ⏳ unconfirmed | Capture a real PROFI frame and compare |
| 2 | PROFI `byte[29]` bit masks for each of the 5 pump ports | ⏳ all unconfirmed | Capture frames with each pump running individually |
| 3 | PROFI `required_algicide` / `required_floc` setpoint bytes (the OXY/HOME byte[54] + byte[72] layout may or may not apply) | ⏳ unconfirmed | Capture a frame with both algicide and flocculant configured and look for non-zero values in byte[54] and byte[72] |
| 4 | PROFI `flowrate_algicide` and `flowrate_floc` are independent bytes on PROFI (not the shared `byte[101]` slot used by SALT) | ⏳ unconfirmed | Capture a frame and look for two non-zero flowrate values |
| 5 | PROFI `required_redox` scaling — confirmed **not** `× 10` (guard in `_fill_required_data`); is it `× 1` (raw mV) or some other scaling? | ⏳ unconfirmed | Capture a frame and compare with the Aseko Live app |
| 6 | PROFI `pH+` pump — does it exist on PROFI hardware (per manual: yes) and which byte/bit carries the setpoint + flowrate + running state? | ⏳ unconfirmed | Capture a frame with pH+ pump running |
| 7 | PROFI water-level byte positions — assumed identical to HOME/SALT/OXY (bytes 27, 102, 103, 104, 105) | ⚠️ assumed | Capture a frame with a non-`0xFF` water level and confirm the thresholds match the app |
| 8 | PROFI heating relay — assumed `byte[29]` bit `0x04` (same as HOME/SALT/OXY) | ⚠️ assumed | Capture a frame while the heat pump is running |
| 9 | PROFI backwash valve — assumed same bytes as HOME/SALT/OXY (68/69/70/71) | ⚠️ assumed | Capture a frame while backwash is active |

---

## How to capture a real PROFI frame

1. Identify a user with an ASIN AQUA Profi unit and ask them to enable Aseko Live /
   Home Assistant logging while the pool is running normally.
2. Capture at least one full 120-byte frame per pump state:
   - All pumps off
   - Filtration only
   - pH− pump only
   - CL pump only
   - Floc pump only
   - Algicide pump only
   - Water refill active (water filling valve open)
   - Heat pump running
   - Backwash active
3. Cross-check decoded values against the Aseko Live app screenshots.
4. Update the `ACTUATOR_MASKS` entry and any `flowrate_*` / `required_*` branches that
   turn out to be wrong.

---

## Cross-References

- Decoder file: `custom_components/aseko_local/aseko_decoder.py`
- Actuator masks: `custom_components/aseko_local/aseko_data.py` → `ACTUATOR_MASKS[AsekoDeviceType.PROFI]`
- Unit-type constant: `custom_components/aseko_local/const.py` → `UNIT_TYPE_PROFI = 0x10`
- Test fixture: `tests/test_sensor.py` → `_make_profi_clf_redox_bytes`
- Test: `tests/test_sensor.py` → `test_async_setup_profi_clf_redox` (asserts 35 entities
  after PR #120; was 34 before, then 35 after the water-level blacklist fix)
- Related water-level analysis: [`water_level_backwash_analysis.md`](../temp/water_level_backwash_analysis.md)
- Sibling device analyses: [`home_device_analysis.md`](home_device_analysis.md), [`salt_device_analysis.md`](salt_device_analysis.md), [`net_device_analysis.md`](net_device_analysis.md), [`oxy_device_analysis.md`](oxy_device_analysis.md)
