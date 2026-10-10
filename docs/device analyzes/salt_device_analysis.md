# ASIN AQUA Salt (v7) — Device Analysis

[Documentation](../README.md) / [Device analyses](README.md)

> **Status:** well understood — almost every field confirmed on the maintainer's two units (37 diagnostics dumps Aug 2026, an app and display comparison 2026-09-11, marked test cases 2026-09-13/14); the alarm bits, the pH− pump bit, the heating relay and the DOSE setpoint are still unconfirmed on SALT.
> **Profile:** [`profiles/v7/salt.py`](../../custom_components/aseko_local/decoding/profiles/v7/salt.py) · **Support:** [support matrix](../support_matrix.md)
> **Evidence words** (`confirmed`, `confirmed on X`, `observed`, `assumed`, `not located`): see [evidence rules](../evidence-rules.md).

## 1. Device

| Field | Value |
|---|---|
| Model | ASIN AQUA Salt |
| Firmware | 5.x – 7.x (Issue #84 unit: v5.0) |
| Hardware | integrated salt-water electrolysis cell (chlorine production, reversible electrode polarity), probes pH plus REDOX or CLF, pH− pump, one shared third pump port (algicide **or** flocculant), filtration and backwash relays, refill valve, level meter, air and water temperature inputs, heating control, variable speed (VS) pump support, programmable relay |
| Identification | v7 `byte[4]` = `0x0E` (REDOX), `0x0D` (CLF) or `0x0F` (DOSE), matched exactly → SALT |
| Sources | PR #87 live captures 2026-04-04; earlier frames 2026-04-02 and 2026-04-03; PR #122; Issues #84, #110, #115, #133, #155; the maintainer's two units (one REDOX, one CLF): 37 diagnostics dumps 2026-08-08..28, an Aseko Live app and unit display comparison 2026-09-11, and test cases marked in the frame log on the REDOX unit 2026-09-13/14 (one setting changed at a time, a marker after the next frame) |

## 2. Frame structure

120 bytes, three 40-byte segments. Each segment repeats the serial number (bytes 0–3 / 40–43 / 80–83) and carries a type byte at offset 5, 45 and 85:

| Segment | Type byte | Content |
|---|---|---|
| 0–39 | `0x01` | live data |
| 40–79 | `0x03` | setpoints and schedule |
| 80–119 | `0x02` | parameters and flow rates |

The last byte of each segment (39, 79, 119) is a checksum: 0xAA XOR the 39 bytes before it. The decoder checks it and only logs a mismatch.

No representative hex frame is recorded in this document.

## 3. Byte map

### Bytes 0–39 — live data

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| 0–3 | `serial_number` | uint32 BE | confirmed | repeated in every segment header |
| 4 | `configuration` | unit type + missing-probe bits | confirmed | see [§4](#byte4--unit-type-and-probes) |
| 5 | — | segment type `0x01` | confirmed | |
| 6–11 | `timestamp` | year−2000, month, day, hour, min, sec | confirmed | device clock |
| 12 | alarm bits | bitmask | confirmed on HOME | usually `0x00` on SALT; see [§4](#byte12--byte13--warnings-and-alarms) |
| 13 | alarm bits | bitmask | confirmed on NET / HOME | see [§4](#byte12--byte13--warnings-and-alarms) |
| 14–15 | `ph` | uint16 BE / 100 | confirmed | |
| 16–17 | `free_chlorine` / `redox` | CLF: / 100 mg/l; REDOX: × 1 mV | confirmed | 0.77 and 0.93 mg/l on the CLF unit; 593..670 mV on the REDOX unit |
| 18–19 | `redox` (second slot) | × 1 mV | — | read instead of 16–17 when not `0xFFFF` (CLF + REDOX units); `0xFFFF` on a basic SALT |
| 20 | `salinity` | / 10 (g/l = kg/m³) | confirmed | |
| 21 | `chlorine_production_measured` | raw | confirmed | reported as sent; `0` in almost every frame with the electrolyzer off (`byte[29]` 0x10 clear), 18 of 6 546 such frames carried 3–25 g/h, each in the 1–3 frames after a stop, running down to 0; the derived `chlorine_production` reads 0 while stopped |
| 22 | settings flags | bitmask | confirmed | see [§4](#byte22--settings-flags) |
| 23–24 | `air_temperature` | int16 BE / 10 °C, window −30.0 … 60.0 | confirmed | see [§5 Air temperature](#air-temperature) |
| 25–26 | `water_temperature` | uint16 BE / 10 °C | confirmed | |
| 27 | `water_level` | cm | confirmed | 14..25 cm across the dumps |
| 28 | `water_flow_to_probes` | `== 0xAA` | confirmed | `0xAA` = flowing |
| 29 | actuators | bitmask | confirmed | see [§4](#byte29--actuators) |
| 30, 31 | — | varies frame to frame | observed | one of the few bytes left that could carry a live value |
| 32–36 | — | always 0 | observed | |
| 37 | settings / routing | bitmask | confirmed | see [§4](#byte37--settings-menu-filtration-mode-and-third-pump-routing) |
| 38 | settings / state flags | bitmask | — | `0x10` heating linked to filtration → `heating_linked_to_filtration` (confirmed; offered only while heating control is on, sent cleared while it is off and reported as sent); `0x01` unknown, see [Open questions](#8-open-questions); `0x20`, `0xA1` around winter mode |
| 39 | — | checksum, 0xAA XOR bytes 0–38 | confirmed | |

### Bytes 40–79 — setpoints and schedule

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| 45 | — | segment type `0x03` | confirmed | |
| 52 | `ph_target` | / 10 | confirmed | |
| 53 | `redox_target` / `free_chlorine_target` / `chlorine_dose_target` | REDOX: × 10 mV; CLF: / 10 mg/l; DOSE: raw | confirmed (REDOX, CLF); assumed (DOSE) | 670 mV on the REDOX unit, 0.9 mg/l on the CLF unit; no DOSE unit captured |
| 54 | `algaecide_dose_target` / `flocculant_dose_target` | algicide ml/m³/day or flocculant ml/h, routed by `byte[37]` 0x80 | confirmed | `decode_v7_routed_by_byte37`; winter program value while winter mode is on |
| 55 | `water_temperature_target` | °C | confirmed | 25 °C in every Aug frame; winter program value (2 °C) while winter mode is on |
| 56–57 | `filtration_period_1_start` | HH:MM | confirmed | changed 08:00 → 09:00 during the dumps |
| 58–59 | `filtration_period_1_end` | HH:MM | confirmed | changed 18:05 / 19:00 / 21:35 |
| 60–61 | `filtration_period_2_start` | HH:MM | confirmed | changed 18:00 → 18:10; always transmitted, even with period 2 disabled (Issue #133) |
| 62–63 | `filtration_period_2_end` | HH:MM | confirmed | changed 22:00 → 23:55; always transmitted (Issue #133) |
| 64–65 | — | tracks `ph` | observed | equal in most frames, otherwise up to 0.70 pH away: a lagging or smoothed copy the regulation works from |
| 66–67 | — | tracks `water_temperature` | observed | equal in most frames, otherwise up to 1.6 °C away |
| 68 | `backwash_interval` | days, `0` = disabled | confirmed | |
| 69–70 | `backwash_start_time` | HH:MM | confirmed | |
| 71 | `backwash_duration` | × 10 s | confirmed | matched the relay window |
| 72 | — | always `0xFF` on SALT | observed | `algaecide_dose_target` on the independent-port models; SALT has no such port |
| 73 | — | constant 20 on both SALT units | observed | differs on HOME/OXY; setting or model constant |
| 74–75 | `startup_delay` | s | confirmed | |
| 76–77 | `max_refill_time` | s | confirmed | |
| 78 | live state / VS pump type | bitmask | confirmed | see [§4](#byte78--live-state-and-vs-pump-type) |
| 79 | — | checksum, 0xAA XOR bytes 40–78 | confirmed | |

### Bytes 80–119 — parameters and flow rates

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| 85 | — | segment type `0x02` | confirmed | |
| 92–93 | `pool_volume` | m³ | confirmed | |
| 94 | — | always 0 | observed | |
| 95 | `ph_minus_flow_rate` | ml/min | confirmed | Issues #110, #115 |
| 96, 97, 98 | — | varies frame to frame | observed | |
| 99 | — | chlorine pump flow rate on other models | — | not applicable on SALT (no chlorine pump) |
| 100 | — | always 0 | observed | |
| 101 | `algaecide_flow_rate` / `flocculant_flow_rate` | ml/min, routed by `byte[37]` 0x80 | confirmed | 60 ml/min in all captured frames; does not move with the algicide/flocculant switch |
| 102 | `water_level_low_alarm` | cm | confirmed | 5 and 31 cm on the two units |
| 103 | `water_level_refill_start` | cm | confirmed | 10 and 33 cm; thresholds ordered low < on < off < high |
| 104 | `water_level_refill_stop` | cm | confirmed | 25 and 35 cm |
| 105 | `water_level_high_alarm` | cm | confirmed | 40 and 56..73 cm |
| 106–107 | `dosing_delay` | s | confirmed | |
| 108, 109–110, 111, 113 | — | constant on both SALT units: 10, 3000, 15, 1 | observed | differ on HOME/OXY; settings or model constants |
| 112 | `ph_minus_concentration` | % | confirmed | 14 then 15 % in the dumps |
| 114 | — | varies frame to frame | observed | |
| 115 | `max_ph_doses` | count | confirmed | 20 on the REDOX unit (moved with the setting), 40 on the CLF unit |
| 116, 117, 118 | — | constant on both SALT units: 0xFF, 252, 1 | observed | differ on HOME/OXY; settings or model constants |
| 119 | — | checksum, 0xAA XOR bytes 80–118 | confirmed | |

## 4. Bit fields

### `byte[4]` — unit type and probes

Convention: **bit set = probe absent**, bit clear = probe present.

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x01` | REDOX probe absent | confirmed | `0x0D` = CLF unit |
| `0x02` | CLF probe absent | confirmed | `0x0E` = REDOX unit |
| `0x0C` | SALT unit type (both bits set) | confirmed | |
| `0x0F` | DOSE (both probes absent) | assumed | no DOSE SALT captured; `0x0D` and `0x0E` are the observed values |

### `byte[12]` / `byte[13]` — warnings and alarms

Shared v7 alarm layout; see [`home_device_analysis.md`](home_device_analysis.md) §"Dosing warnings & alarms". Bytes 12–13 were `0x00` throughout the SALT dumps.

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `byte[12]` 0x20 | `alarm_max_disinfection_dose` | confirmed on HOME | Issue #134 |
| `byte[12]` 0x40 | `alarm_ph_dosing_ineffective` | confirmed on HOME | Issue #134 |
| `byte[13]` 0x01 | `alarm_max_disinfection_dose` | confirmed on HOME | Issue #151 |
| `byte[13]` 0x02 | `alarm_ph_dosing_ineffective` | assumed | inferred |
| `byte[13]` 0x04 | `alarm_no_flow_to_probes` | confirmed | set 2026-09-14 05:00:41 when filtration started with no flow yet, cleared when the flow arrived a second later; the unit reported *there is no flow to probes* (also DomSchCoding NET frame) |
| `byte[13]` 0x08 | `alarm_rapid_ph_change` | assumed | from error_codes.md; never set in the SALT dumps; possibly "Low pH under 6,7" instead (open question) |

### `byte[22]` — settings flags

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x01` | heating only inside its time window → `heating_condition` = `time_window` | confirmed | never set together with 0x02 |
| `0x02` | heating by outside temperature → `outside_temperature_above` / `_below` | confirmed | neither 0x01 nor 0x02 → `always` |
| `0x04` | winter mode on → `freeze_protection_enabled` | confirmed | `decode_v7_winter_mode` override |
| `0x08` | VS pump enabled (the setting, not the pump running) → `variable_speed_pump_enabled` | confirmed | clear on the REDOX unit, set on the CLF unit |
| `0x10` | backwash schedule enabled → `backwash_schedule_enabled` | confirmed | cleared with `byte[68]` dropping to 0 |
| `0x20` | with 0x02: heat when **below** the outside temperature (clear = above) | confirmed | |

`byte[22]` was `0x18` in both air-temperature samples.

### `byte[29]` — actuators

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x01` | backwash valve open → `backwash_running` | confirmed | capture of a manual backwash, 2026-08-11 |
| `0x02` | refilling (water filling valve) → `refilling` | confirmed | 2026-09-06 08:12–08:21, see [Ground truth](#6-ground-truth) |
| `0x04` | heating running → `heating_running` | assumed | JS-DE-Tech `relay_byte` bit 2; never set, heating control is off on the REDOX unit |
| `0x08` | filtration relay → `filtration_relay` (→ `filtration_running`) | confirmed | every active phase (PR #87) |
| `0x10` | electrolysis running → `electrolysis_running` | confirmed | 25 frames (PR #87) |
| `0x20` | third port running → `algaecide_pump_running` / `flocculant_pump_running` | confirmed | 27 frames (PR #87); flocculant from the Apr 3 frames; chemical chosen by `byte[37]` 0x80 |
| `0x40` | electrode polarity: set = right, clear = left → `electrode_polarity` | confirmed | switched by hand both ways 2026-09-13; meaningful only while 0x10 is set, otherwise *waiting* |
| `0x80` | pH− pump → `ph_minus_pump_running` | assumed | consistent with HOME/OXY; never set in a captured SALT frame |

### `byte[37]` — settings menu, filtration mode and third-pump routing

Mapped bit by bit by toggling one setting at a time on the unit (2026-09-13).

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x01` | always set | observed | no known meaning |
| `0x02` | flow detection enabled → `flow_detection_enabled` | confirmed | |
| `0x04` | settings menu open → `service_menu_open` | confirmed | six values, both directions of every transition; see [§5](#settings-menu-byte37-0x04) |
| `0x08` | heating control enabled → `heating_control_enabled` | confirmed | |
| `0x10` | filtration period 1 enabled → `filtration_schedule` | confirmed | |
| `0x20` | filtration period 2 enabled → `filtration_schedule` | confirmed | |
| `0x40` | Waterlevel (level meter) enabled → `water_level_sensor_enabled` | confirmed | winter mode clears it |
| `0x80` | third port doses algicide (clear = flocculant) | confirmed | routes `algaecide_*` / `flocculant_*`; follows the dosing unit ml/m³/day vs ml/h (2026-09-14); Issue #84 exception in [§5](#third-pump-routing) |

These are settings, not hardware: Waterlevel, heating control or the VS pump can be enabled without the sensor, heater or pump connected; the app then shows nothing for it.

Captured combinations (mode known from the unit, both directions of each transition):

| `byte[37]` | `service_menu_open` | `filtration_schedule` |
|---|---|---|
| `0xC3` | False | `NONSTOP_24H` |
| `0xD3` | False | `TIMER_PERIOD_1` |
| `0xF3` | False | `TIMER_PERIOD_1_AND_2` |
| `0xC7` | True | `NONSTOP_24H` |
| `0xD7` | True | `TIMER_PERIOD_1` |
| `0xF7` | True | `TIMER_PERIOD_1_AND_2` |

Other observed values: `0xB7`, `0xB3` (algicide), `0x37`, `0x33` (flocculant; PR #122 toggle `0xB3` ↔ `0x33`), `0x13` (Issue #84, algicide), `0xFF` (not configured / NET).

### `byte[78]` — live state and VS pump type

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x80` | heating condition met now → `heating_condition_met` | confirmed | follows the time window and the outside-temperature condition as clock and settings change; set with Heating control off too (always, with no condition), so the derived `heating_allowed` also needs `byte[37]` 0x08 |
| `0x40` | winter mode active | confirmed | same as `byte[22]` 0x04; not decoded separately |
| `0x0C` | VS pump type → `variable_speed_pump_type`: `0x00` Speck / Uwe EO PM, `0x04` Pentair / Dab E.SWIM, `0x08` Hayward | confirmed | every brand selected in turn; kept while the VS pump is off, changes immediately on another pick |
| `0x02` | filtration running | observed | not decoded (`byte[29]` 0x08 says the same); seen the same way on NET and OXY |
| `0x01` | filtration standing | observed | both or neither only in transitions |

## 5. Model-specific behaviour

### Electrolyzer

`electrolysis_running` = `byte[29]` 0x10; `chlorine_production_measured` = `byte[21]` as sent (0 in almost every frame while not running), `chlorine_production` = the same while running, else 0; `electrode_polarity` = `byte[29]` 0x40 (set = right, clear = left, *waiting* while 0x10 is clear); `salinity` = `byte[20]` / 10. The electrolyzer and the third pump can run at the same time.

### Third pump routing

SALT has one physical third pump port, configurable as algicide or flocculant. Both chemicals share `byte[29]` 0x20, `byte[54]` (dose) and `byte[101]` (flow rate); `byte[37]` 0x80 set → algicide (ml/m³/day), clear → flocculant (ml/h). `byte[101]` and (formerly assumed) `byte[103]` did not split the flow rate between chemicals.

Caution: the Issue #84 SALT (v5.0) shows `byte[37]` = `0x13` while set to algicide, bit 7 clear. An older firmware may route differently, so the 0x80 rule is not proven for every SALT firmware.

### Settings menu (`byte[37]` 0x04)

- The bit appears the moment the settings menu is opened on the unit — the menu holding every Aseko setting, where filtration and backwash can be started by hand — **before** anything is touched (three captures "switched to manual mode, did nothing" carry it). On its own it says only that a person is at the unit. The profile flags this as `MENU_BIT_IS_PRESENCE_ONLY`.
- Opening it produces exactly one more frame (the one with 0x04), then transmission stops until the user leaves. Three diagnostics during one session all held the same frame, with `online` going false between them. So `service_menu_open` going True is typically the last thing reported before the device goes offline, and stays True until the user leaves.
- What the user does in the menu is not observable; the pump state in that last frame is the state on the way in. The unit will not let the user leave until filtration is back in its previous state, so the held value is right again when frames resume.
- Not evidence that the schedule is suspended: in the 2026-08-11 capture the pump kept running, and period 1 covered that time anyway.
- Changing the backwash time or interval, or switching the schedule off and on, restarts it: the next backwash runs the day after the change at the set time, and the interval counts from it (checked on the unit, 2026-09-13 and 2026-09-14). The integration applies the same rule to HOME, OXY and PROFI without such a check.
- Exception, by-hand **backwash**: the unit keeps transmitting, with 0x04 set from ~30 s before the valve opens until ~20 s after it closes. The backwash tracker uses it outside the schedule window: a cycle there with the menu open is manual, with the menu closed not attributed. In the schedule window a cycle is scheduled either way.

### Filtration schedule and period 2

The filtration times in bytes 56–63 are reported unchanged in every mode, so the mode comes only from `byte[37]` 0x10 / 0x20. The unit keeps sending the last-configured period 2 times even when period 2 is disabled; they are read unconditionally (Issue #133). Same mode bits as HOME.

### Air temperature

Bytes 23–24: int16 BE two's complement / 10 °C. The water temperature after it is read unsigned (/ 10 °C): no capture with water below 0 °C exists to tell whether it is signed too.

- Two dumps from a SALT (`byte[4]` = `0x0D`, Issue #155), both matching the unit: 2026-08-11 10:33 air `0x0168` = 36.0 °C, water `0x0128` = 29.6 °C; 2026-08-17 18:50 air `0x0134` = 30.8 °C, water `0x0122` = 29.0 °C. Both fields move independently and each raw air value occurs once in its frame, so the offset is unambiguous. `byte[22]` stayed `0x18`, so it is a plain 16-bit field.
- Without an air probe: `0xFE70` (−40.0 °C) and `0xFDC4` (−57.2 °C) — open-circuit values (unsigned they would read 6513.6 / 6502.8 °C). The decoder discards anything outside −30.0 … 60.0 °C. `0xFFFF` (protocol-wide "unspecified") is rejected up front, since signed it would pass as −0.1 °C.
- A genuine sub-zero reading has not been captured; the cold-weather encoding is unverified.
- Scope: confirmed on SALT only. HOME and OXY frames always carry the open-circuit value (no entity until a probe is fitted); NET carries unrelated data in these bytes (e.g. `0x0C3C` = 313.2 °C).

### Winter mode

Switching winter mode on (2026-09-13, twice):

- `byte[22]` 0x04 and `byte[78]` 0x40 set, `byte[37]` 0x40 cleared (level control off);
- the setpoint bytes carry the **winter program** while it is on: `byte[54]` algicide 2 ml, `byte[55]` water 2 °C, bytes 56–59 filtration 12:00–12:15, bytes 60–63 18:00–22:00, `byte[68]` backwash 0 (off); the normal values return when it is switched off;
- filtration runs for about 15–20 s right after switching it on (`byte[29]` 0x08, `byte[78]` 0x02).

### Water temperature target

`byte[55]` keeps the setpoint even while heating control is off and the app hides the value.

## 6. Ground truth

2026-09-11, REDOX unit: settings compared with the last captured frame (2026-08-28), settings unchanged in between. Live values are from different days and show the encoding only.

| Date | Field | Decoded | Unit / app | Result |
|---|---|---|---|---|
| 2026-09-11 | `redox_target` | 670 mV | 670 mV | ✓ |
| 2026-09-11 | `ph_target` | 7.2 | 7.2 | ✓ |
| 2026-09-11 | `algaecide_dose_target` (`byte[37]` bit 7 set) | 5 ml/m³/day | 5 ml/m³/day | ✓ |
| 2026-09-11 | `water_temperature_target` | 25 °C | `---` (heating control off) | ⚠ byte keeps the hidden setpoint |
| 2026-09-11 | `pool_volume` | 40 m³ | 40 m³ | ✓ |
| 2026-09-11 | `startup_delay` | 480 s | 8 min | ✓ |
| 2026-09-11 | `dosing_delay` | 240 s | 4 min | ✓ |
| 2026-09-11 | `backwash_interval` | 15 | every 15 days | ✓ |
| 2026-09-11 | `backwash_start_time` | 08:30 | 08:30 | ✓ |
| 2026-09-11 | `backwash_duration` | 100 s | 01:40 min | ✓ |
| 2026-09-11 | `water_level_high_alarm` | 73 cm | 73 cm | ✓ |
| 2026-09-11 | `water_level_refill_stop` | 25 cm | 25 cm | ✓ |
| 2026-09-11 | `water_level_refill_start` | 10 cm | 10 cm | ✓ |
| 2026-09-11 | `water_level_low_alarm` | 5 cm | 5 cm | ✓ |
| 2026-09-11 | `max_refill_time` | 1140 s | 19 min | ✓ |
| 2026-09-11 | `ph_minus_concentration` | 15 % | 15 % | ✓ |
| 2026-09-11 | `filtration_schedule` (`byte[37]` = `0xD3`) | timer, period 1 | timer on, period 1 on, period 2 off, nonstop off | ✓ |
| 2026-09-11 | `filtration_period_1_start` / `_end` | 08:00 / 21:35 | 08:00 / 21:35 | ✓ |
| 2026-09-11 | `filtration_period_2_start` / `_end` | 18:10 / 23:55 | 18:10 / 23:55 (disabled, still transmitted) | ✓ Issue #133 behaviour |
| 2026-09-11 | `configuration` | REDOX | Redox probe (RX) | ✓ |
| 2026-09-11 | `electrode_polarity` / `chlorine_production` | waiting / 0 | 0 g/h, waiting | ✓ |
| Aug / 2026-09-11 | `salinity` | 4.0 kg/m³ (Aug) | 4.4 kg/m³ (Sep) | ✓ encoding; different day |
| 2026-09-11 | `air_temperature` | None (open-circuit value) | air off / `---` | ✓ no probe, no value |
| 2026-09-11 | `variable_speed_pump_enabled` (`byte[22]` 0x08) | False | VS pump off | ✓ (the CLF unit has the bit set) |
| 2026-09-11 | `max_ph_doses` (`byte[115]`) | 20 | 20 | ✓ |
| 2026-09-11 | `heating_running` | False | heating control off | consistent; running state never captured |
| Aug / 2026-09-11 | `water_level` | 31 cm (Aug) | 30 cm, level OK | ✓ encoding; status text derived from the thresholds |
| 2026-09-06 | `refilling` (`byte[29]` 0x02) | set 08:12 → 08:21 | level fell to 10 cm (refill on), rose only while set, cleared at 25 cm (refill off) | ✓ from the Home Assistant history |
| 2026-09-12 19:47 | `max_ph_doses` | `0x14` → `0x11` | setting 20 → 17 | ✓ the only 17 in the frame |
| 2026-09-13/14 | `max_ph_doses` | moved | 17 → 20 | ✓ |
| 2026-09-14 05:00 | `alarm_no_flow_to_probes` (`byte[13]` 0x04) | on for one second after filtration start, off with the flow | unit: *there is no flow to probes* | ✓ raw frames of the frame log |
| 2026-09-14 20:16–20:17 | `heating_linked_to_filtration` (`byte[38]` 0x10) | set with *heating control parent to filtration* ON, cleared with it OFF | setting on the unit | ✓ one clean on/off pair, heating control on throughout |
| 2026-09-14 20:19–20:23 | `variable_speed_pump_enabled` / `variable_speed_pump_type` | `byte[22]` 0x08 on/off with each switch; `byte[78]` 0x0C Speck/Uwe 0x00, Dab/Pentair 0x04, Hayward 0x08 | VS pump on/off, brand chosen | ✓ four cycles, one per brand |
| 2026-09-14 20:59–21:00 | third port routing (`byte[37]` 0x80) | clear with the dosing unit set to ml/h, set again with ml/m³/day | setting on the unit | ✓ the dosing unit is how the unit switches the port between flocculant (ml/h) and algicide (ml/m³/day) |
| 2026-09-14 20:59:42 | third port running (`byte[29]` 0x20) | one frame, `0x68` | 2 s dose | ✓ |
| 2026-09-14 20:24–20:25 | `water_level_high_alarm` threshold (`byte[105]`) | 73 → 26 cm with the level at 30 cm for 58 s | no alarm on the unit or in the app | `byte[12]` / `byte[13]` unchanged — see open question 3 |
| 2026-09-13/14 | `ph_minus_concentration` (`byte[112]`) | moved | 15 → 21 % | ✓ |
| 2026-09-13/14 | `water_temperature_target` (`byte[55]`) | moved | 25 → 15 °C | ✓ |
| 2026-08-11, 2026-08-17 | `air_temperature` | 36.0 / 30.8 °C | unit readings | ✓ see §5 |

## 7. Settings the frame does not carry

Changed on the unit with a marker after the next frame, and no byte moved:

- heating time window (start / end);
- outside-temperature threshold;
- electrode polarity switching interval (1 h / 24 h / 7 days / manual);
- the programmable relay and its periods;
- display language.

Visible in the unit or the app, not located yet: the **water flow meter** toggle, the **pool flow** type (overflow vs. skimmer). Consumption figures (electrolyzer efficiency / production kg/week, canister levels, pump lifetimes, water filled m³, heating kWh) are cloud aggregates, not frame fields; production could be integrated locally from `chlorine_production`.

## 8. Open questions

1. **pH− pump bit** — `byte[29]` 0x80 assumed (as HOME/OXY); a frame captured while the pH− pump doses.
2. **"Low pH under 6,7" alarm bit** — `byte[13]` 0x08 or 0x20: the HOME frame with pH 6.29 (see `home_device_analysis.md`) carried `byte[13]` = 0x28, while 0x08 is currently read as rapid pH change on the strength of error_codes.md alone; a download while the app shows this alarm.
3. **"Water level too high" alarm** — with the level 4 cm above the high threshold for 58 s (2026-09-14) the unit raised no alarm and bytes 12–13 stayed 0; a longer test (5–10 min above the threshold) would show whether the unit waits or compares differently.
4. **Other SALT alarms** (low salt) — a marked test case while the alarm is shown.
5. **`byte[38]` 0x01** — on in runs of seconds to minutes, around setting changes but also for minutes without any (e.g. 2026-09-14 07:54–08:02); `byte[31]` takes different values meanwhile. Unknown.
6. **Water flow meter toggle and pool flow type** — toggle each with a marker after the next frame.
7. **`byte[37]` routing on older firmware** — Issue #84 (v5.0) `0x13` = algicide with bit 7 clear; a v5.x frame with the third port switched between chemicals.
8. **`heating_running`** — `byte[29]` 0x04 assumed; a frame with heating control on and the heater running.
9. **DOSE SALT** (`byte[4]` = `0x0F`, `byte[53]` as `chlorine_dose_target`) — a frame from a DOSE unit.
10. **Constant bytes 73, 108, 109–110, 111, 113, 116–118** — change one setting at a time with a marker.
11. **Varying bytes 30, 31, 96, 97, 98, 114** — correlate with the app's history.
12. **Sub-zero air temperature** — a capture below 0 °C with an air probe fitted.

## 9. History

- The segment checksum (bytes 39, 79, 119) was once listed as unknown; it is 0xAA XOR the 39 bytes before it and the decoder checks it.
- `free_chlorine_mv` was read from bytes 20–21 as on NET / HOME (6656, 6934 and 7936 mV in SALT CLF frames). Those are `0x1a00`, `0x1b16` and `0x1f00`: salinity 2.6 / 2.7 / 3.1 and chlorine production 0 / 22 / 0 — the same two bytes. SALT has no such value; removed from the profile 2026-09-14.
- `max_refill_time` evidence once said 1800 s = 30 min; the check against the unit on 2026-09-11 read 1140 s = 19 min, which is what the profile records.
- `byte[103]` was once read as a duplicate third-pump flow rate (60 ml/min, mirroring `byte[101]`, "does not flip with the algicide/floc switch"); bytes 102–105 are the water level thresholds, confirmed against the unit 2026-09-11.
- The electrolyzer table once said `electrolysis_running` is True "when RIGHT cycle running"; it is the plain 0x10 run bit, polarity is 0x40.
- Electrode polarity was first read the other way round (`0x50` = left, from one April frame); the by-hand switch on 2026-09-13 settled set = right and the decoder was corrected.
- `byte[37]` 0x04 was read as a dosage encoding from a PR #122 XOR diff (algicide 10 → 11 = `0x04`, algicide 11 → flocculant 11 = `0x84`, algicide 10 → flocculant 11 = `0x80`); superseded — 0x04 is the settings menu, and the dosage and a menu change most likely coincided in that pair. The full XOR analysis was in `docs/temp/byte37_algicide_floc_analysis.md` (no longer in this repository).
- `byte[37]` 0x40 was once taken for a HOME "firmware A / B" split; it is the Waterlevel setting, the same on HOME and SALT, so HOME has one profile now.
- Before the Issue #133 fix, period 2 times (bytes 60–63) were gated on `byte[37]` & 0x80 and read as `None` whenever the routing bit was clear, flipping entities to unknown when period 2 was toggled; they are now read unconditionally on every model with a filtration output (verified on SALT from the PR #122 `0xB3` ↔ `0x33` pair, on HOME with Issue #133's four diagnostics; NET excluded).
- Air temperature (bytes 23–24) was listed as "unknown" before the Issue #155 dumps.
- The SALT decoding moved into the profile `decoding/profiles/v7/salt.py` with one feature file per value under `decoding/features/`; the support matrix is generated from the profiles.

## 10. References

- Issues: #84 (SALT v5.0 routing), #110, #115 (flow rates), #133 (period 2), #134, #151 (alarm bits, HOME), #155 (air temperature)
- PRs: #87 (live captures 2026-04-04), #122 (algicide/flocculant toggle frames)
- Profile: [`profiles/v7/salt.py`](../../custom_components/aseko_local/decoding/profiles/v7/salt.py); shared v7 groups in `profiles/v7/common.py`
- Related analyses: [HOME](home_device_analysis.md), [OXY](oxy_device_analysis.md), [NET](net_device_analysis.md), [PROFI](profi_device_analysis.md), [NET v8](net_v8_device_analysis.md)
- [Support matrix](../support_matrix.md), [evidence rules](../evidence-rules.md)
- Tests: `tests/test_decode_v7.py`
