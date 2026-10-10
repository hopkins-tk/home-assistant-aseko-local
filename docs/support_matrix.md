# Support matrix

What each decoding profile reads, and how sure we are.  Generated from `custom_components/aseko_local/decoding/profiles/` by `scripts/generate_support_matrix.py`; do not edit by hand.

A **profile** is one (protocol, model) combination.  A **feature** is one field on `AsekoDevice`, i.e. one value the integration can read.

| Mark | Meaning |
|---|---|
| ✅ | read on this model, checked against the unit display or the Aseko Live app on **this** model — or *derived*: it follows from the protocol or from confirmed values (the evidence text says which) |
| 👁 | seen repeatedly in captures from a real unit with consistent, plausible values, but not compared with the unit display or the app — **a glance at the unit would settle it** |
| ❓ | read on this model, but not checked on it: assumed, or confirmed only on another model — **a diagnostics dump would settle it** |
| — | the profile does not read it: the model does not have the value, or the integration does not decode it (yet); no entity is created |
| 🔍 | this model has the value (its menu or manual shows it), but where the frame carries it is not known yet: the entity exists and reads unknown — **a diagnostics dump before and after changing it on the unit would settle it** |
| `decode_…` | the profile uses this reading instead of the protocol default |

Further profiles exist that no unit is meant to decode with and that the tables leave out: **v7 unknown unit type** and **v8 unknown header type**.  They read an unmapped unit (v7 unit type, v8 header type) with the generic readings so it shows as much as possible in diagnostics, where it is reported as unrecognised; it gets no entities.

## v7

| field | HOME | SALT | OXY | NET | PROFI |
|---|---|---|---|---|---|
| `air_temperature` | ❓ | ✅ | ❓ | — | — |
| `alarm_max_disinfection_dose` | ✅ | ❓ | ❓ | ❓ | ❓ |
| `alarm_no_flow_to_probes` | ❓ | ✅ | ❓ | ✅ | ❓ |
| `alarm_ph_dosing_ineffective` | ✅ | ❓ | ❓ | ❓ | ❓ |
| `alarm_rapid_ph_change` | ❓ | ❓ | ❓ | ❓ | ❓ |
| `algaecide_dose_target` | ✅ | ✅ `decode_v7_routed_by_byte37` | ✅ | — | — |
| `algaecide_flow_rate` | 🔍 | ✅ `decode_v7_routed_by_byte37` | ✅ | — | — |
| `algaecide_pump_running` | ❓ `decode_v7_oxy` | ✅ | ✅ `decode_v7_oxy` | — | — |
| `backwash_duration` | ✅ | ✅ | 👁 | — | ❓ |
| `backwash_interval` | ✅ | ✅ | 👁 | — | ❓ |
| `backwash_running` | ❓ | ✅ | ❓ | — | ❓ |
| `backwash_schedule_enabled` | 👁 | ✅ | — | — | — |
| `backwash_start_time` | ✅ | ✅ | 👁 | — | ❓ |
| `chlorine_dose_target` | ❓ | ❓ | — | 👁 | ❓ |
| `chlorine_flow_rate` | ✅ | — | — | ✅ | ❓ |
| `chlorine_production_measured` | — | ✅ | — | — | — |
| `chlorine_pump_running` | ❓ | — | — | ✅ `decode_v7_net` | ❓ |
| `configuration` | ✅ `decode_v7_by_unit_type_byte` | ✅ | ✅ `decode_v7_ph_and_oxy` | ✅ | ❓ `decode_v7_without_dose` |
| `dosing_delay` | ✅ | ✅ | 👁 | 👁 | ❓ |
| `electrode_polarity` | — | ✅ | — | — | — |
| `electrolysis_running` | — | ✅ | — | — | — |
| `filtration_period_1_end` | ✅ | ✅ | 👁 | — | ❓ |
| `filtration_period_1_start` | ✅ | ✅ | 👁 | — | ❓ |
| `filtration_period_2_end` | ✅ | ✅ | 👁 | — | ❓ |
| `filtration_period_2_start` | ✅ | ✅ | 👁 | — | ❓ |
| `filtration_relay` | ✅ | ✅ | ✅ | — | ❓ |
| `filtration_schedule` | ✅ | ✅ | 👁 | — | ❓ |
| `flocculant_dose_target` | ✅ | ✅ `decode_v7_routed_by_byte37` | ✅ | — | ❓ `decode_v7_routed_by_byte37` |
| `flocculant_flow_rate` | ✅ | ✅ `decode_v7_routed_by_byte37` | ✅ | — | ❓ `decode_v7_routed_by_byte37` |
| `flocculant_pump_running` | ❓ | ✅ | ✅ | — | ❓ |
| `flow_detection_enabled` | ❓ | ✅ | ❓ | — | — |
| `free_chlorine` | ✅ | ✅ | — | ✅ | ❓ |
| `free_chlorine_mv` | ✅ | — | — | ✅ | ❓ |
| `free_chlorine_target` | ✅ | ✅ | — | 👁 | ❓ |
| `freeze_protection_enabled` | ✅ | ✅ `decode_v7_winter_mode` | 🔍 | — | — |
| `heating_condition` | — | ✅ | — | — | — |
| `heating_condition_met` | — | ✅ | — | — | — |
| `heating_control_enabled` | ✅ | ✅ | 🔍 | — | — |
| `heating_linked_to_filtration` | ❓ | ✅ | — | — | — |
| `heating_running` | ❓ | ❓ | ❓ | — | ❓ |
| `max_ph_doses` | 👁 | ✅ | 👁 | — | ❓ |
| `max_refill_time` | ❓ | ✅ | ❓ | — | ❓ |
| `oxygen_dose_target` | — | — | ✅ | — | — |
| `oxygen_flow_rate` | — | — | ✅ | — | — |
| `oxygen_pump_running` | — | — | ✅ | — | — |
| `ph` | ✅ | ✅ | 👁 | ✅ | ❓ |
| `ph_minus_concentration` | ✅ | ✅ | ❓ | — | ❓ |
| `ph_minus_flow_rate` | 👁 | ✅ | ✅ | ✅ | ❓ |
| `ph_minus_pump_running` | ❓ | ❓ | ✅ | ✅ `decode_v7_net` | ❓ |
| `ph_target` | ✅ | ✅ | 👁 | ✅ | ❓ |
| `pool_volume` | ✅ | ✅ | 👁 | 👁 | ❓ |
| `redox` | ❓ | ✅ | — | ❓ | ❓ |
| `redox_target` | ❓ | ✅ | — | ❓ | — |
| `refilling` | ✅ | ✅ | ❓ | — | ❓ |
| `salinity` | — | ✅ | — | — | — |
| `serial_number` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `service_menu_open` | ✅ | ✅ | 👁 | — | ❓ |
| `startup_delay` | ✅ | ✅ | 👁 | ❓ | ❓ |
| `timestamp` | ✅ | ✅ | ✅ | ❓ | ❓ |
| `unit_clock` | ✅ | ✅ | ✅ | — | ❓ |
| `variable_speed_pump_enabled` | ✅ | ✅ | ❓ | — | — |
| `variable_speed_pump_type` | ✅ | ✅ | — | — | — |
| `water_flow_to_probes` | ✅ | ✅ | 👁 | ✅ | ❓ |
| `water_level` | ✅ | ✅ | ❓ | — | ❓ |
| `water_level_high_alarm` | ✅ | ✅ | ❓ | — | ❓ |
| `water_level_low_alarm` | ✅ | ✅ | ❓ | — | ❓ |
| `water_level_refill_start` | ❓ | ✅ | 🔍 | — | ❓ |
| `water_level_refill_stop` | ✅ | ✅ | ❓ | — | ❓ |
| `water_level_sensor_enabled` | ❓ | ✅ | ❓ | — | — |
| `water_temperature` | ✅ | ✅ | 👁 | ✅ | ❓ |
| `water_temperature_target` | ✅ | ✅ | 👁 | — | ❓ |

## v8

| field | NET | SALT |
|---|---|---|
| `alarm_max_disinfection_dose` | — | 👁 |
| `alarm_no_flow_to_probes` | — | ✅ |
| `algaecide_dose_target` | — | ✅ |
| `algaecide_pump_running` | — | ✅ |
| `chlorine_flow_rate` | ❓ | — |
| `chlorine_production_measured` | — | ✅ |
| `chlorine_pump_running` | ❓ | — |
| `configuration` | ✅ | ✅ |
| `dosing_delay` | ✅ | 👁 |
| `electrode_polarity` | — | ✅ |
| `electrolysis_running` | — | ✅ |
| `filtration_period_1_end` | — | ✅ |
| `filtration_period_1_start` | — | ✅ |
| `filtration_relay` | ✅ | ❓ |
| `filtration_schedule` | — | ✅ |
| `flocculant_dose_target` | — | 👁 |
| `flocculant_pump_running` | — | 👁 |
| `ph` | ✅ | ✅ |
| `ph_minus_flow_rate` | ❓ | ❓ |
| `ph_minus_pump_running` | ❓ | ❓ |
| `ph_target` | ✅ | ✅ |
| `pool_volume` | ✅ | ✅ |
| `redox` | ✅ | ✅ |
| `redox_target` | ✅ | ✅ |
| `salinity` | — | ✅ |
| `serial_number` | ✅ | ✅ |
| `startup_delay` | ✅ | 👁 |
| `timestamp` | ✅ | ✅ |
| `unit_clock` | ✅ | ✅ |
| `water_flow_to_probes` | ✅ | ❓ |
| `water_temperature` | ✅ | ✅ |

## Worked out from other fields

Not read from the frame: each value is computed in `decoding/derived.py` from the fields it names, which keep their own entities as sent.  A profile has the value when it reads all of them; a flag after a profile changes the rule for that model.

| field | from | profiles |
|---|---|---|
| `heating_allowed` | `heating_control_enabled`, `heating_condition_met` | v7 SALT |
| `chlorine_production` | `chlorine_production_measured`, `electrolysis_running` | v7 SALT, v8 SALT |
| `filtration_running` | `filtration_relay` | v7 HOME (`MENU_BIT_SWITCHES_FILTRATION_OFF`), v7 SALT, v7 OXY, v7 PROFI, v8 NET, v8 SALT |

## Help wanted

Every entry below is read today without a confirming capture.  If you own one of these units, a diagnostics download taken while the value is visible on the unit or in the Aseko Live app is exactly what is needed.

### v7 HOME

- `air_temperature` — assumed: bytes 23-24 = 0xFE70 (no air probe, the SALT marker) in every captured HOME frame, so its entity has stayed disabled; the Aseko Live app shows air temperature on HOME units
- `alarm_no_flow_to_probes` — confirmed on NET: byte[13] 0x04 (DomSchCoding, NET frame)
- `alarm_rapid_ph_change` — assumed: byte[13] 0x08 was set on serial 110128063 with no matching alarm known in the app
- `algaecide_pump_running` — assumed: byte[29] 0x10 as on OXY, which has the same four independent pump ports (0x20 is the flocculant); read only once the algicide flow rate is located, so no state yet
- `backwash_running` — assumed: byte[29] 0x01, confirmed on SALT
- `chlorine_dose_target` — assumed: byte[53] with a DOSE unit type, as on NET; no DOSE HOME frame captured
- `chlorine_pump_running` — assumed: byte[29] 0x40, port may be chlorine or OXY Pure
- `flocculant_pump_running` — assumed: byte[29] 0x20 as on OXY (confirmed there)
- `flow_detection_enabled` — confirmed on SALT: byte[37] 0x02 (2026-09-13); on HOME 0x43 / 0x53 have it set and Issue #135's 0x41 / 0x45 / 0x49 clear
- `heating_linked_to_filtration` — assumed: byte[38] 0x10 as on SALT (confirmed there, 2026-09-14); no HOME frame compared
- `heating_running` — assumed: byte[29] 0x04 per JS-DE-Tech relay_byte bit 2; no HOME frame with the heater running (open item 9)
- `max_refill_time` — assumed: bytes 76-77 = 10800 s on serial 110128063, plausible (180 min); verified on SALT only
- `ph_minus_pump_running` — assumed: byte[29] 0x80
- `redox` — assumed: bytes 16-19 as on SALT (bytes 18-19 when not 0xFFFF); no REDOX HOME frame with the app's value
- `redox_target` — assumed: byte[53] x 10 mV as on SALT; no REDOX HOME frame compared
- `water_level_refill_start` — confirmed on SALT: byte[103], bytes 102-105 are the level thresholds (SALT 2026-09-11 against the unit); 33 cm on serial 110128063 sits between the low alarm 13 and the refill stop 55
- `water_level_sensor_enabled` — confirmed on SALT: byte[37] 0x40 (2026-09-13); set in every frame of the level-meter HOME units (once 'firmware A'), clear on serial 110169464 (once 'firmware B')

### v7 SALT

- `alarm_max_disinfection_dose` — confirmed on HOME: byte[12] 0x20 (Issue #134), byte[13] 0x01 (Issue #151)
- `alarm_ph_dosing_ineffective` — confirmed on HOME: byte[12] 0x40 (Issue #134); byte[13] 0x02 inferred
- `alarm_rapid_ph_change` — assumed: byte[13] 0x08 from error_codes.md; never set in the own SALT dumps, 37 frames 2026-08-08..28
- `chlorine_dose_target` — assumed: byte[53] for a DOSE unit; neither unit of the own SALT dumps, 37 frames 2026-08-08..28 is one
- `heating_running` — assumed: byte[29] 0x04 per JS-DE-Tech relay_byte bit 2; never set in the own SALT dumps, whose unit has heating control OFF
- `ph_minus_pump_running` — assumed: byte[29] 0x80; the bit was never set in the own SALT dumps, 37 frames 2026-08-08..28

### v7 OXY

- `air_temperature` — assumed: bytes 23-24 = 0xFE70 (no air probe, the SALT marker) in every captured OXY frame, so its entity has stayed disabled; the Aseko Live app shows air temperature on Oxygen units
- `alarm_max_disinfection_dose` — assumed: bytes 12-13 were 0x00 in every OXY frame; HOME encoding assumed
- `alarm_no_flow_to_probes` — assumed: byte[13] was 0x00 in every OXY frame; confirmed on NET and HOME only
- `alarm_ph_dosing_ineffective` — assumed: bytes 12-13 were 0x00 in every OXY frame; HOME encoding assumed
- `alarm_rapid_ph_change` — assumed: byte[13] 0x08 from error_codes.md; never set in the OXY frames
- `backwash_running` — assumed: byte[29] 0x01, confirmed on SALT
- `flow_detection_enabled` — assumed: byte[37] 0x02 as on SALT; set in the OXY frames (0x03)
- `heating_running` — assumed: byte[29] 0x04 per JS-DE-Tech relay_byte bit 2
- `max_refill_time` — assumed: bytes 76-77 = 3600 s on the Winnetoux OXY, plausible (60 min); verified on SALT only
- `ph_minus_concentration` — assumed: byte[112], confirmed on HOME
- `refilling` — assumed: byte[29] 0x02, confirmed on HOME and SALT
- `variable_speed_pump_enabled` — assumed: byte[22] 0x08, confirmed on HOME
- `water_level` — assumed: byte[27], confirmed on HOME
- `water_level_high_alarm` — assumed: byte[105] as on SALT; the captured OXY has no level sensor
- `water_level_low_alarm` — assumed: byte[102] as on SALT; the captured OXY has no level sensor
- `water_level_refill_stop` — assumed: byte[104] as on SALT; the captured OXY has no level sensor
- `water_level_sensor_enabled` — assumed: byte[37] 0x40 as on SALT; clear in the OXY frames (0x03), which fits byte[27] = 0xFE (no level sensor)

### v7 NET

- `alarm_max_disinfection_dose` — assumed: byte[12] is 0x00 on NET; HOME encodings assumed
- `alarm_ph_dosing_ineffective` — assumed: byte[12] is 0x00 on NET; HOME encodings assumed
- `alarm_rapid_ph_change` — assumed: byte[13] 0x08 from error_codes.md; never set on NET
- `redox` — assumed: protocol default, bytes 18-19 (16-17 when 18-19 are 0xFFFF); no REDOX NET frame captured
- `redox_target` — assumed: byte[53] * 10 on a REDOX NET; no such frame captured
- `startup_delay` — assumed: bytes 74-75 = 0xFFFF (not filled in) on the Issue #66 NET frame and on the ChemDoserProxy NET frame
- `timestamp` — assumed: bytes 6-11 are 0xFF on every NET frame, Home Assistant's clock is used instead

### v7 PROFI

- `alarm_max_disinfection_dose` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `alarm_no_flow_to_probes` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `alarm_ph_dosing_ineffective` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `alarm_rapid_ph_change` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `backwash_duration` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `backwash_interval` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `backwash_running` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `backwash_start_time` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `chlorine_dose_target` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `chlorine_flow_rate` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `chlorine_pump_running` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `configuration` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `dosing_delay` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `filtration_period_1_end` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `filtration_period_1_start` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `filtration_period_2_end` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `filtration_period_2_start` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `filtration_relay` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `filtration_schedule` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `flocculant_dose_target` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md); the PROFI setpoints screen has a flocculant dose (ml/24 h m3) on its shared flocculant / algicide output
- `flocculant_flow_rate` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `flocculant_pump_running` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `free_chlorine` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `free_chlorine_mv` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `free_chlorine_target` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `heating_running` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `max_ph_doses` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `max_refill_time` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md); the 2021 PROFI manual lists a max. filling time
- `ph` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `ph_minus_concentration` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `ph_minus_flow_rate` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `ph_minus_pump_running` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `ph_target` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `pool_volume` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `redox` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `refilling` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `service_menu_open` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `startup_delay` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `timestamp` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `unit_clock` — assumed: bytes 6-11 as on the other v7 models; no real PROFI frame has been captured
- `water_flow_to_probes` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `water_level` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `water_level_high_alarm` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `water_level_low_alarm` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `water_level_refill_start` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `water_level_refill_stop` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `water_temperature` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)
- `water_temperature_target` — assumed: no real PROFI frame has been captured; layout inferred from the manual and the other models (profi_device_analysis.md)

### v8 NET

- `chlorine_flow_rate` — assumed: not transmitted, 60 ml/min taken for consumption
- `chlorine_pump_running` — assumed: outs[9] per the current decoder; net_v8_device_analysis.md lists outs[0] / outs[1] as candidates and no frame shows a pump running
- `ph_minus_flow_rate` — assumed: not transmitted, 60 ml/min taken for consumption
- `ph_minus_pump_running` — assumed: outs[8] per the current decoder; net_v8_device_analysis.md lists outs[0] / outs[1] as candidates and no frame shows a pump running

### v8 SALT

- `filtration_relay` — assumed: only the header type (1xx) says SALT; the NET layout is taken over unverified
- `ph_minus_flow_rate` — assumed: only the header type (1xx) says SALT; the NET layout is taken over unverified
- `ph_minus_pump_running` — assumed: only the header type (1xx) says SALT; the NET layout is taken over unverified
- `water_flow_to_probes` — assumed: only the header type (1xx) says SALT; the NET layout is taken over unverified

## Not located yet

Values these models have but nobody has found in the frame.  If you own one of these units, download diagnostics, change the setting on the unit, wait a minute and download again: the two frames show where it is.

### v7 HOME

- `algaecide_flow_rate` — not located: byte[103] was read as the algicide flow rate (Issues #110, #115), but bytes 102-105 are the water level thresholds -- confirmed on SALT against the unit (2026-09-11) and 13 / 33 / 55 / 100 cm in order on serial 110128063; the captured OXY sends its algicide flow rate there, and has no level sensor connected

### v7 OXY

- `freeze_protection_enabled` — not located: the ASIN AQUA Oxygen manual describes freeze protection; no OXY frame has been compared with it
- `heating_control_enabled` — not located: the ASIN AQUA Oxygen manual describes heating control; no OXY frame has been compared with it
- `water_level_refill_start` — not located: byte[103] carries the algicide flow rate on OXY (confirmed, 60 ml/min), so the refill start threshold is elsewhere on an OXY with a level sensor; the captured OXY has none

## Seen, not compared

Values captured from real units that nobody has yet checked against the unit display or the app.  If you own one of these units, comparing the entity with what the unit shows is all it takes.

### v7 HOME

- `backwash_schedule_enabled` — observed: byte[22] 0x10 set on serial 110128063 with backwash every 3 days (0x90); confirmed on an ASIN AQUA Salt (2026-09-13)
- `max_ph_doses` — observed: byte[115] = 20 on serial 110128063; the position is confirmed on SALT, the HOME setting was never compared
- `ph_minus_flow_rate` — observed: byte[95] = 60 on serial 110128063; Aseko Live lists the pH- pump but the rate was not compared; the position is confirmed on SALT

### v7 OXY

- `backwash_duration` — observed: byte[71] * 10 = 100 s on the Winnetoux OXY (serial 110157165); not compared with the app
- `backwash_interval` — observed: byte[68] = 0 (disabled) on the Winnetoux OXY (serial 110157165); not compared with the app
- `backwash_start_time` — observed: bytes 69-70 = 12:30 on the Winnetoux OXY (serial 110157165); not compared with the app
- `dosing_delay` — observed: bytes 106-107 = 120 s on the Winnetoux OXY (serial 110157165); not compared with the app
- `filtration_period_1_end` — observed: bytes 58-59 = 16:00 in every frame on the Winnetoux OXY (serial 110157165); not compared with the app
- `filtration_period_1_start` — observed: bytes 56-57 = 08:00 in every frame on the Winnetoux OXY (serial 110157165); not compared with the app
- `filtration_period_2_end` — observed: bytes 62-63 = 22:00 in every frame on the Winnetoux OXY (serial 110157165); not compared with the app
- `filtration_period_2_start` — observed: bytes 60-61 = 18:00 in every frame on the Winnetoux OXY (serial 110157165); not compared with the app
- `filtration_schedule` — observed: byte[37] = 0x03 reads nonstop while the Winnetoux OXY ran filtration 24 h; no schedule transition captured
- `max_ph_doses` — observed: byte[115] = 30 on the Winnetoux OXY; the position is confirmed on SALT, the OXY setting was never compared
- `ph` — observed: bytes 14-15 = 7.17 on the Winnetoux OXY (serial 110157165); not compared with the app
- `ph_target` — observed: byte[52] / 10 = 7.2 on the Winnetoux OXY (serial 110157165); not compared with the app
- `pool_volume` — observed: bytes 92-93 = 41 m3 on the Winnetoux OXY (serial 110157165); not compared with the app
- `service_menu_open` — observed: byte[37] bit 0x04 clear in every OXY frame; the menu never captured open
- `startup_delay` — observed: bytes 74-75 = 240 s on the Winnetoux OXY; not compared with the app
- `water_flow_to_probes` — observed: byte[28] = 0xAA on the Winnetoux OXY (serial 110157165); not compared with the app
- `water_temperature` — observed: bytes 25-26 = 9.5 C on the Winnetoux OXY (serial 110157165); not compared with the app
- `water_temperature_target` — observed: byte[55] = 25 C on the Winnetoux OXY (serial 110157165); not compared with the app

### v7 NET

- `chlorine_dose_target` — observed: byte[53] = 5 ml/m3/h in DOSE mode (2026-04-07 capture); not compared with the app
- `dosing_delay` — observed: bytes 106-107 on the Issue #66 NET; not compared with the app
- `free_chlorine_target` — observed: byte[53] / 10 on the Issue #66 NET; not compared with the app
- `pool_volume` — observed: bytes 92-93 on the Issue #66 NET; not compared with the app

### v8 SALT

- `alarm_max_disinfection_dose` — observed: ins[12] bit 0x80 flipped 0 -> 128 while the unit showed 'Maximum disinfection dose exceeded' (Issue #151)
- `dosing_delay` — observed: areqs[18] = 5, the 5 min the unit is set to (Issue #131); the NET v8 sends 2 for its 2 min
- `flocculant_dose_target` — observed: areqs[3] = 10 with the port set to flocculant 10 ml/h, 0 while it was algicide (Issue #131)
- `flocculant_pump_running` — observed: outs[11] with the chemical from fncs[6] (10 algicide, 18 flocculant): the same unit read 10 with algicide configured and 18 after its owner switched the port on 2026-07-19 (Issue #131)
- `startup_delay` — observed: areqs[17] = 5, the 5 min the unit is set to (Issue #131); the NET v8 sends 2 for its 2 min

## Not mapped on any protocol

Fields that exist on `AsekoDevice` but that nothing knows how to read yet.

- `ph_plus_flow_rate`
- `ph_plus_pump_running`

## Totals

- features known: 73
- with a v7 reading: 71
- with a v8 reading: 31
- profiles: 9
