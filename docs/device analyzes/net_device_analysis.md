# ASIN AQUA NET (v7) — Device Analysis

[Documentation](../README.md) / [Device analyses](README.md)

> **Status:** live values, pump states and probe configuration decoded from the Issue #66 frames and a 2026-04-07 mode-switch capture; setpoints seen but not compared with the app, REDOX variant never captured.
> **Profile:** [`profiles/v7/net.py`](../../custom_components/aseko_local/decoding/profiles/v7/net.py) · **Support:** [support matrix](../support_matrix.md)
> **Evidence words** (`confirmed`, `confirmed on X`, `observed`, `assumed`, `not located`): see [evidence rules](../evidence-rules.md).

## 1. Device

- **Hardware:** measurement and dosing only — pH and chlorine probes (CLF, or REDOX, or volume dosing "DOSE" mode) with two dosing pump outputs (pH− and chlorine). No filtration pump or relay, no backwash valve, no water level sensor, no third pump port.
- **Firmware:** 7.x sends the 120-byte v7 frame described here. Firmware 8.x uses a different text frame, see [net_v8_device_analysis.md](net_v8_device_analysis.md).
- **Identification:** v7 `byte[4]` = `0x09` (CLF), `0x0A` (REDOX) or `0x0B` (DOSE). Base unit type `UNIT_TYPE_NET = 0x08`; the low bits are the missing-probe flags (section 4).
- **Sources:** Issue #66 (frames and pump states); AquaNET log 2026-04-07 13:15–13:16 (70-second capture around a probe-mode switch); DomSchCoding NET frame (no-flow alarm); ChemDoserProxy NET frame (startup delay); Issues #110, #115 (pH− flow rate).

## 2. Frame structure

120 bytes, three 40-byte segments. The segment type sits at byte 5, 45 and 85; the serial number (bytes 0–3) is repeated in every segment header.

| Segment | Type byte | Content |
|---|---|---|
| 0–39 | `0x01` | Live sensor data |
| 40–79 | `0x03` | Configuration / setpoints |
| 80–119 | `0x02` | Flow rates / dosing |

Many setpoint and schedule bytes are `0xFF` (unspecified) on NET because the device has no filtration schedule, backwash or water temperature setpoint. No representative hex frame is kept in this document.

## 3. Byte map

### Bytes 0–39 — live data

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| 0–3 | `serial_number` | big-endian | confirmed | repeated in every segment header |
| 4 | unit type + `configuration` | missing-probe bits, see section 4 | confirmed | `0x09` typical |
| 5 | segment type | `0x01` | confirmed | |
| 6–11 | `timestamp` | not used | observed | `0xFF` on every NET frame; Home Assistant's clock is used instead |
| 12 | dosing warnings | bitmask, see section 4 | assumed | usually `0x00` on NET; HOME encodings, see [home_device_analysis.md](home_device_analysis.md) |
| 13 | alarms | bitmask, see section 4 | confirmed (`0x04`) | |
| 14–15 | `ph` | value / 100 | confirmed | Issue #66 frames |
| 16–17 | `free_chlorine` | value / 100 (mg/L) | confirmed | still a live reading in DOSE mode (e.g. `0x006A` = 1.06 mg/L) |
| 18–19 | `redox` | mV; bytes 16–17 when 18–19 are `0xFFFF` | assumed | protocol default; no REDOX NET frame captured |
| 20–21 | `free_chlorine_mv` | mV, uint16 BE (read unsigned; no negative value captured) | confirmed | SALT uses `byte[20]` for salinity and `byte[21]` for electrolyzer power |
| 25–26 | `water_temperature` | value / 10 (°C) | confirmed | Issue #66 frames |
| 28 | `water_flow_to_probes` | `0xAA` = flowing | confirmed | Issue #66 frames |
| 29 | pump outputs | bitmask, see section 4 | confirmed | override `decode_v7_net` |
| 37 | settings / routing | not decoded | observed | `0xFF` in all captured NET frames; no third pump port, no filtration features |

### Bytes 40–79 — setpoints and schedule

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| 45 | segment type | `0x03` | confirmed | |
| 52 | `ph_target` | value / 10 | confirmed | Issue #66 frames |
| 53 | `free_chlorine_target` | value / 10 (mg/L), CLF probe | observed | Issue #66 NET; not compared with the app |
| 53 | `redox_target` | value × 10 (mV), REDOX probe | assumed | no REDOX NET frame captured |
| 53 | `chlorine_dose_target` | ml/m³/h, DOSE mode | observed | 5 ml/m³/h in the 2026-04-07 capture; not compared with the app |
| 54 | algicide dose | not decoded on NET | assumed | non-`0xFF` only when a pump port is configured |
| 55 | water temperature target | not decoded on NET | assumed | `0xFF` = not set |
| 56–63 | filtration periods 1 and 2 | not decoded on NET | assumed | `0xFFFF` = not set |
| 68 | backwash interval (days) | not decoded on NET | assumed | `0xFF` = not set |
| 69–70 | backwash start time | not decoded on NET | assumed | `0xFFFF` = not set |
| 71 | backwash duration | not decoded on NET | assumed | `0xFF` = not set |
| 74–75 | `startup_delay` | seconds | assumed | `0xFFFF` (not filled in) on the Issue #66 and ChemDoserProxy NET frames |

### Bytes 80–119 — parameters and flow rates

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| 85 | segment type | `0x02` | confirmed | |
| 92–93 | `pool_volume` | m³ | observed | Issue #66 NET; not compared with the app |
| 95 | `ph_minus_flow_rate` | ml/min | confirmed | Issues #110, #115 |
| 99 | `chlorine_flow_rate` | ml/min | confirmed | |
| 101 | third-pump flow rate | not decoded on NET | observed | `0xFF` (no third pump) |
| 103 | — | ignore | observed | constant `0x03` on NET |
| 106–107 | `dosing_delay` | seconds | observed | Issue #66 NET; not compared with the app |

## 4. Bit fields

### `byte[4]` — unit type and missing-probe flags

Inverted convention: a bit **set** means the probe is **absent**.

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x01` | `PROBE_REDOX_MISSING` | confirmed | clear only on `0x0A` |
| `0x02` | `PROBE_CLF_MISSING` | confirmed | clear on `0x09`; toggles on the CLF ↔ DOSE switch |
| `0x04` | `PROBE_DOSE_MISSING` | observed | clear on all three NET values, so the decoder always adds DOSE; the DOSE mode itself shows as both `0x01` and `0x02` set |
| `0x08` | `UNIT_TYPE_NET` | confirmed | NET identifier |

| `byte[4]` | Binary | REDOX | CLF | Mode | Evidence |
|---|---|---|---|---|---|
| `0x09` | `0000 1001` | absent | present | CLF probe control | confirmed |
| `0x0A` | `0000 1010` | present | absent | REDOX probe control | assumed (no frame captured) |
| `0x0B` | `0000 1011` | absent | absent | DOSE (ml/m³/h) | confirmed (2026-04-07 capture) |

### `byte[12]` — dosing warnings

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x20` | `alarm_max_disinfection_dose` | assumed | HOME encoding; `byte[12]` is `0x00` on NET |
| `0x40` | `alarm_ph_dosing_ineffective` | assumed | HOME encoding; `byte[12]` is `0x00` on NET |

### `byte[13]` — alarms

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x01` | `alarm_max_disinfection_dose` | assumed | HOME encoding |
| `0x02` | `alarm_ph_dosing_ineffective` | assumed | HOME encoding |
| `0x04` | `alarm_no_flow_to_probes` | confirmed | DomSchCoding NET frame |
| `0x08` | `alarm_rapid_ph_change` | assumed | from error_codes.md; never set on NET |

### `byte[29]` — pump outputs

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x01` | `ph_minus_pump_running` | confirmed | Issue #66, `test_decode_net_pump_states` |
| `0x02` | `chlorine_pump_running` | confirmed | Issue #66 |
| `0x08` | not filtration | confirmed | no filtration output on NET; bit positions differ from SALT / HOME / OXY |
| other bits | — | not located | no further pump outputs known |

## 5. Model-specific behaviour

### No filtration output

The NET has no filtration pump or relay, so the profile has no filtration, backwash, water level or heating features; `filtration_running` is always `None` on NET (Issue #66).

### Pumps run in parallel

pH− and chlorine are independent outputs: `byte[29] = 0x03` means both pumps are running at the same time.

### DOSE mode

Switching the NET to volume dosing (ml/m³/h) in the Aseko app changes `byte[4]` from `0x09` to `0x0B`. In the 2026-04-07 capture `0x0B` was seen at 13:15:00 (DOSE mode) and `0x09` at 13:16:10 (CLF control). The CLF probe keeps measuring in DOSE mode, so bytes 16–17 remain a live reading — unlike OXY, where bytes 16–17 are the invariant placeholder `0x001E` (no CLF hardware). `byte[53]` then holds the dose in ml/m³/h instead of the CLF target.

### Timestamp sentinel

Bytes 6–11 are all `0xFF` on every NET frame, so the timestamp is taken from Home Assistant's clock.

## 6. Ground truth

Nothing known yet.

## 7. Settings the frame does not carry

Nothing known yet.

## 8. Open questions

1. REDOX variant (`byte[4] = 0x0A`): a frame from a REDOX NET would confirm the probe bits, `redox` (bytes 18–19) and `redox_target` (`byte[53]` × 10).
2. Setpoints never compared with the app: `free_chlorine_target`, `chlorine_dose_target`, `pool_volume`, `dosing_delay` — a diagnostics dump taken while the values are visible in the Aseko Live app settles them.
3. `startup_delay` (bytes 74–75) is `0xFFFF` in both NET frames seen — a frame from a NET with the delay set would show whether the position holds.
4. Dosing warnings: `byte[12]` and `byte[13]` bits `0x01`, `0x02`, `0x08` were never set on NET — a dump taken while the unit shows the corresponding alarm.
5. Other `byte[29]` bits and a pH+ pump: the NET hardware may not have a pH+ output — a dump from a unit with a pH+ pump running, if one exists.

## 9. History

- `byte[37]` = `0xFF` question closed: `0xFF` in all captured frames, and the NET profile lists no filtration features, so neither `filtration_schedule` nor `service_menu_open` is decoded.
- Before the split into device profiles the NET decoding lived in `_fill_*` methods with `ACTUATOR_MASKS` (NET: `ph_minus=0x01`, `cl=0x02`, no filtration) and `FILTRATION_TYPES`; now [`profiles/v7/net.py`](../../custom_components/aseko_local/decoding/profiles/v7/net.py) with the `decode_v7_net` override.
- DOSE mode was misclassified as HOME: the old if-chain tested `(data[4] & 0x03) == 0x03` before the NET check `data[4] & 0x08`, and `0x0B` matched. Logged as a known bug, out of scope for v1.4.0. Fixed by the exact `byte[4]` lookup (`0x09`–`0x0B` → NET) in `decoding/profile.py`.
- The old timestamp fallback used `datetime.now()`; now Home Assistant's clock.
- Firmware 8.x (463-byte frame) was "not yet implemented" when this document was started; it now has its own v8 profile.

## 10. References

- Issue #66 — NET frames, pump states, no filtration output
- Issues #110, #115 — pH− flow rate at `byte[95]`
- [net_v8_device_analysis.md](net_v8_device_analysis.md) — NET on firmware 8.x
- [home_device_analysis.md](home_device_analysis.md) — dosing warnings and alarms (`byte[12]`, `byte[13]`)
- [oxy_device_analysis.md](oxy_device_analysis.md), [salt_device_analysis.md](salt_device_analysis.md)
- [support matrix](../support_matrix.md), [evidence rules](../evidence-rules.md)
- Tests: `tests/test_decode_v7.py` (`test_decode_net`, `test_decode_net_120_bytes`, `test_decode_net_pump_states`, `test_decode_net_no_backwash_with_garbage_bytes`, `test_*_none_for_net`)
