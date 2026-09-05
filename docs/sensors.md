# Entity Reference

This document lists every entity exposed by `aseko_local`, with its
support status on the v7 (binary 120-byte frame) and v8 (text frame)
protocols. Status is checked against the source in `custom_components/aseko_local/`
and the tests in `tests/`; the JSON test fixtures and the captured frames
from the device-analysis documents are the source of truth for what a
real device actually transmits.

## Status legend

| Symbol | Meaning |
| ------ | ------- |
| ✅     | Implemented and tested — the entity is created for a real device, the wire mapping is confirmed against a unit display or app screenshot, and at least one unit test exercises it. |
| 🟡     | Partial — the entity is created, but the wire mapping has either a single-capture confirmation or an unconfirmed hypothesis (e.g. inferred bit assignment). |
| ❌     | Not exposed — the entity is not created for this protocol because the decoder does not populate the underlying field, or because the protocol does not carry the relevant bytes. |

## Protocols

| | v7 (binary 120-byte frame) | v8 (text frame) |
| - | -------------------------- | --------------- |
| Devices | HOME, NET, OXY, PROFI, SALT | NET, SALT_NET |
| Decoder | `aseko_decoder.py` (120-byte binary) | `aseko_decoder_v8.py` (text frame) |
| Helpers | `aseko_v7_helpers.py` | `aseko_v8_helpers.py` |
| Frame analysis | `docs/device analyzes/<device>_device_analysis.md` | `docs/device analyzes/net_v8_device_analysis.md`, `salt_net_v8_device_analysis.md` |

A v8 device never produces the v7 byte[29]/byte[37]/byte[56-63]/byte[92-93]
fields. Anything that depends on those bytes is marked ❌ for v8.

---

## Sensors

| Sensor | Key | V7 | V8 | Issues / remarks |
| ------ | --- | -- | -- | ---------------- |
| Air temperature | `air_temperature` | ✅ | ❌ | V7 only — bytes 23-24, gated on `AIR_TEMPERATURE_TYPES = {SALT}`. V8 has no equivalent slot. Issue #155. |
| Electrolyzer power | `electrolyzer_power` | ✅ | ✅ | V7: byte 21 (SALT). V8: `ains[9]` for SALT_NET, gated on device_type. |
| Electrolyzer direction | `electrolyzer_direction` | ✅ | ✅ | V7: byte 29 bits. V8: `outs[14]` for SALT_NET only. |
| Free chlorine | `free_chlorine` | ✅ | ❌ | V7: bytes 16-17 / 10 (CLF devices). V8: not transmitted. |
| Required free chlorine | `required_free_chlorine` | ✅ | ❌ | V7 only (DOSE / CLF devices). |
| Free chlorine (mV) | `free_chlorine_mv` | ✅ | ❌ | V7 only — NET/PROFI redox-as-mV. V8 reports redox in mV separately. |
| pH | `ph` | ✅ | ✅ | Both protocols. V8: `ains[0]`. |
| Required pH | `required_ph` | ✅ | ✅ | V7: byte 52 / 10. V8: `areqs[0] / 10`. |
| pH− concentration | `ph_minus_concentration` | ✅ | ❌ | V7 only — HOME byte 112 (Issue #139). |
| Redox | `rx` | ✅ | ✅ | V7: bytes 16-17 / 18-19. V8: `ains[6]`. |
| Required redox | `required_rx` | ✅ | ✅ | V7: byte 53 × 10 mV. V8: `areqs[1] × 10` mV. |
| Salinity | `salinity` | ✅ | ✅ | V7: byte 20 (SALT). V8: `ains[8] / 10` g/L, SALT_NET only. |
| Water temperature | `water_temperature` | ✅ | ✅ | V7: bytes 25-26. V8: `ins[0] / 10`. |
| Required water temperature | `required_waterTemp` | ✅ | ❌ | V7 only — byte 55. |
| Water level | `water_level` | ✅ | ❌ | V7 only — HOME byte 27 (Issue #110). |
| Water level (low alarm) | `water_level_low_alarm` | ✅ | ❌ | V7 HOME only. |
| Water level (filling on) | `water_level_filling_on` | ✅ | ❌ | V7 HOME only. |
| Water level (filling off) | `water_level_filling_off` | ✅ | ❌ | V7 HOME only. |
| Water level (high alarm) | `water_level_high_alarm` | ✅ | ❌ | V7 HOME only. |
| Max filling time | `max_filling_time` | ✅ | ❌ | V7: HOME/SALT bytes 76-77 (Issue #153). |
| Required algicide | `required_algicide` | ✅ | ✅ | V7: byte 54 (SALT). V8: `areqs[4]` for SALT_NET with fncs[6]=10. |
| Required flocculant | `required_floc` | ✅ | ✅ | V7: byte 54. V8: `areqs[3]` for SALT_NET with fncs[6]=18. |
| Required OXY dose | `required_oxy_dose` | ✅ | ❌ | V7 OXY only — byte 53 raw ml/m³/day. |
| Required CL dose | `required_cl_dose` | ✅ | ❌ | V7 only — DOSE mode (volume-based). |
| Flow rate — chlor | `flowrate_chlor` | ✅ | 🟡 | V7: byte 99 (0xFF = absent). V8: hardcoded to `V8_DEFAULT_PUMP_FLOWRATE_ML_MIN` (60 mL/min) — not measured on the wire. |
| Flow rate — pH− | `flowrate_ph_minus` | ✅ | 🟡 | V7: byte 97. V8: hardcoded constant — same caveat as chlor. |
| Flow rate — pH+ | `flowrate_ph_plus` | ✅ | ❌ | V7 only. |
| Flow rate — algicide | `flowrate_algicide` | ✅ | ❌ | V7 only — byte 95. V8 firmware does not transmit per-pump flow-rate bytes, so the consumption tracker does not accumulate for v8 algicide (see "Consumption" below). |
| Flow rate — flocculant | `flowrate_floc` | ✅ | ❌ | Same as algicide. |
| Flow rate — OXY | `flowrate_oxy` | ✅ | ❌ | V7 OXY only — byte 99 (same slot as chlor). |
| Last seen | `last_seen` | ✅ | ✅ | Set by the coordinator on every incoming frame. |
| Filtration 1 start | `filtration_1_start` | ✅ | ❌ | V7 only — bytes 56-57. V8 frame does not carry the schedule bytes. |
| Filtration 1 stop | `filtration_1_stop` | ✅ | ❌ | V7 only. |
| Filtration 2 start | `filtration_2_start` | ✅ | ❌ | V7 only — bytes 60-61. |
| Filtration 2 stop | `filtration_2_stop` | ✅ | ❌ | V7 only. |
| Filtration schedule | `filtration_schedule` | ✅ | ❌ | V7 only — byte[37] bits 0x10/0x20 (Issue #133, #135). V8 has no byte[37]-style schedule bits; the v8 decoder derives `filtration_mode` internally but does not surface it as an entity. |
| Pool volume | `pool_volume` | ✅ | ✅ | V7: bytes 92-93. V8: `areqs[14]`. |
| Delay after startup | `delay_after_startup` | ✅ | ✅ | V7: bytes 74-75 (seconds). V8: `areqs[17] × 60` seconds — NET uses 2 min, SALT_NET uses 5 min. |
| Delay after dose | `delay_after_dose` | ✅ | ✅ | V7: bytes 107-108. V8: `areqs[18] × 60` seconds. |
| Backwash — every N days | `backwash_every_n_days` | ✅ | ❌ | V7 only — byte 68. Gated on `_has_backwash` (HOME/SALT/OXY). |
| Backwash — time | `backwash_time` | ✅ | ❌ | V7 only — bytes 69-70. |
| Backwash — duration | `backwash_duration` | ✅ | ❌ | V7 only — byte 71. |
| Last backwash (observed) | `last_backwash` | ✅ | ❌ | V7 only — filled by `BackwashTracker` once a real valve cycle is seen. |
| Last manual backwash | `last_manual_backwash` | ✅ | ❌ | V7 only — SALT byte[37] bit 0x04 confirmed, other types inferred. |
| Next scheduled backwash (estimated) | `next_scheduled_backwash` | ✅ | ❌ | V7 only — projected from `last_scheduled_backwash` + `backwash_every_n_days`. Renamed from `next_backwash`; unique_id migrated at setup. |
| Connection status | `connection_status` | ✅ | ✅ | Coordinator-level — same logic for both protocols. |

### Consumption sensors

Every pump in `AsekoDevice.installed_pumps` produces a pair of sensors:
`<pump>_consumed` (mL since last refill) and `<pump>_total_consumed`
(lifetime mL). The pump presence gate is fed by:

* V7 — `ACTUATOR_MASKS[<device>]` + flow-rate presence (see
  `AsekoDecoder._fill_installed_pumps`).
* V8 — `installed_pumps_from_fncs(fncs2, fncs6)` in `aseko_v8_helpers.py`.

| Sensor | Key | V7 | V8 | Issues / remarks |
| ------ | --- | -- | -- | ---------------- |
| CL consumed | `chlor_consumed` | ✅ | ❌ | SALT NET has no CL pump — `fncs[2]=1` excludes `cl` from `installed_pumps`. |
| CL total consumed | `chlor_total_consumed` | ✅ | ❌ | |
| pH− consumed | `ph_minus_consumed` | ✅ | 🟡 | V8 SALT_NET: pH− pump is on, but `flowrate_ph_minus` is the constant 60 mL/min — see flow-rate caveat above. |
| pH− total consumed | `ph_minus_total_consumed` | ✅ | 🟡 | |
| pH+ consumed | `ph_plus_consumed` | ✅ | ❌ | Not installed on any known v8 device. |
| pH+ total consumed | `ph_plus_total_consumed` | ✅ | ❌ | |
| Algicide consumed | `algicide_consumed` | ✅ | ❌ | V8 SALT_NET exposes `algicide_pump_running` and the `required_algicide` setpoint, but the consumption tracker skips accumulation when `flowrate_algicide is None`. To track algicide on v8, the decoder would need to fall back to `V8_DEFAULT_PUMP_FLOWRATE_ML_MIN` for `flowrate_algicide` and `flowrate_floc` (same workaround as `flowrate_ph_minus`). |
| Algicide total consumed | `algicide_total_consumed` | ✅ | ❌ | |
| Flocculant consumed | `floc_consumed` | ✅ | ❌ | Same as algicide. |
| Flocculant total consumed | `floc_total_consumed` | ✅ | ❌ | |
| OXY consumed | `oxy_consumed` | ✅ | ❌ | OXY is v7 only. |
| OXY total consumed | `oxy_total_consumed` | ✅ | ❌ | |

---

## Binary sensors

| Binary sensor | Key | V7 | V8 | Issues / remarks |
| ------------- | --- | -- | -- | ---------------- |
| Water flow to probes | `water_flow_to_probes` | ✅ | ✅ | V7: byte 28. V8: `ins[8]`. |
| Electrolyzer active | `electrolyzer_active` | ✅ | ✅ | V7: byte 29 bit 4. V8: `outs[14] != 0` (SALT_NET). |
| Filtration pump running | `filtration_pump_running` | ✅ | ✅ | V7: byte 29 bit 3, with HOME firmware-B manual-override short-circuit (Issue #133). V8: `outs[2] != 0` (SALT_NET — note V8 uses **2** for ON, V7 NET uses **1**). |
| Heating active | `heating_active` | ✅ | ❌ | V7 HOME only — byte 29 bit 2. |
| Heating control enabled | `heating_control_enabled` | ✅ | ❌ | V7 HOME only — byte 37 bit 3 (0x08). Issue #136. |
| Antifreeze enabled | `antifreeze_enabled` | ✅ | ❌ | V7 HOME only — byte 37 bit 7 (0x80). Issue #136. |
| VSP pump running | `vsp_pump_running` | ✅ | ❌ | V7 HOME only — byte 22 bit 3 (0x08). |
| CL pump running | `cl_pump_running` | ✅ | ❌ | V7 only. V8 SALT_NET has `fncs[2]=1` → CL pump structurally absent (decoder returns `None`). |
| pH− pump running | `ph_minus_pump_running` | ✅ | ✅ | V7: byte 29 bit 7. V8: `outs[8]`. Universally present — never gated. |
| pH+ pump running | `ph_plus_pump_running` | ✅ | ❌ | Not installed on any known v8 device. |
| Algicide pump running | `algicide_pump_running` | ✅ | ✅ | V7: byte 29 bit 4 (SALT). V8: `outs[11]` for SALT_NET with fncs[6]=10. |
| Flocculant pump running | `floc_pump_running` | ✅ | ✅ | V8: `outs[11]` for SALT_NET with fncs[6]=18. Same physical port as algicide (decoder routes by `fncs[6]`). |
| OXY pump running | `oxy_pump_running` | ✅ | ❌ | V7 OXY only. |
| Water filling active | `water_filling_active` | ✅ | ❌ | V7 HOME/SALT only — byte 29 bit 0x02. |
| Service menu open | `service_menu` | ✅ | ❌ | V7 only — byte 37 bit 0x04. V8 has no equivalent; surfaces alongside `filtration_schedule`. Issue #133. |
| Alarm — pH too many doses | `alarm_ph_too_many_doses` | ✅ | ❌ | V7 byte[13] 0x02 / byte[12] 0x40 (Issue #134). |
| Alarm — ORP too many doses | `alarm_orp_too_many_doses` | ✅ | ✅ | V7: byte[13] 0x01 / byte[12] 0x20 (Issue #134). V8: `ins[12]` bit 0x80 for NET and SALT_NET (Issue #151). |
| Alarm — no flow to probes | `alarm_no_flow_to_probes` | ✅ | ✅ | V7: byte 13 bit 0x04. V8: `ins[12]` bit 0x100 (Issue #131 §10, dual encoding). |
| Alarm — rapid pH change | `alarm_rapid_ph_change` | 🟡 | ❌ | V7 byte[13] 0x08 — listed in `error_codes.md` but never directly confirmed against a unit display. |
| Backwash active | `backwash_active` | ✅ | ❌ | V7 only — byte 29 bit 0x01, gated on `BACKWASH_TYPES = {HOME, SALT, OXY}`. NET/SALT_NET have no backwash output. |

---

## Buttons

Refill-reset buttons for every pump in `AsekoDevice.installed_pumps`. Each
button calls `aseko_local.reset_pump_consumption` with the corresponding
pump key, resetting the `canister` counter to 0 (or both counters with the
`all` service variant).

| Button | Key | V7 | V8 | Issues / remarks |
| ------ | --- | -- | -- | ---------------- |
| Reset CL refill | `chlor_refill_reset` | ✅ | ❌ | SALT NET has no CL pump. |
| Reset pH− refill | `ph_minus_refill_reset` | ✅ | ✅ | pH− is universal on every Aseko device. |
| Reset pH+ refill | `ph_plus_refill_reset` | ✅ | ❌ | |
| Reset algicide refill | `algicide_refill_reset` | ✅ | ✅ | Gated on `algicide` in `installed_pumps` (SALT_NET with fncs[6]=10). |
| Reset flocculant refill | `floc_refill_reset` | ✅ | ✅ | Gated on `floc` in `installed_pumps` (SALT_NET with fncs[6]=18). |
| Reset OXY refill | `oxy_refill_reset` | ✅ | ❌ | OXY is v7 only. |

---

## Datetime entities

| Entity | Key | V7 | V8 | Issues / remarks |
| ------ | --- | -- | -- | ---------------- |
| Last scheduled backwash | `last_scheduled_backwash` | ✅ | ❌ | V7 only — writable datetime. The device never transmits this; the user enters it from the UI to seed the schedule phase. |

---

## Coverage summary by device

### SALT NET v8 (mirovra, Issue #131)

Exposed entities: `water_temperature`, `ph`, `required_ph`, `redox`,
`required_redox`, `salinity`, `electrolyzer_power`,
`electrolyzer_direction`, `pool_volume`, `delay_after_startup`,
`delay_after_dose`, `last_seen`, `connection_status`,
`water_flow_to_probes`, `electrolyzer_active`, `filtration_pump_running`,
`ph_minus_pump_running`, `algicide_pump_running` (or `floc_pump_running`),
`alarm_orp_too_many_doses`, `alarm_no_flow_to_probes`,
`ph_minus_refill_reset`, `algicide_refill_reset` (or
`floc_refill_reset`).

Gaps: `required_waterTemp`, `filtration_1_start/stop`/`2_start/stop`
(no schedule bytes on v8), `filtration_schedule` (no byte[37]),
consumption tracking for algicide/floc (no per-pump flow-rate bytes on
v8 wire — would need a constant flow-rate fallback in the decoder).