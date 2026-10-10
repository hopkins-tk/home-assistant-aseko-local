# ASIN AQUA Home (v7) — Device Analysis

[Documentation](../README.md) / [Device analyses](README.md)

> **Status:** core values checked against the Aseko Live app on one CLF unit (2026-04-28) plus settings bits from REDOX-unit diagnostics (Issues #110–#151); pump running bits, heating running and the algicide flow rate are still open.
> **Profile:** [`profiles/v7/home.py`](../../custom_components/aseko_local/decoding/profiles/v7/home.py) · **Support:** [support matrix](../support_matrix.md)
> **Evidence words** (`confirmed`, `confirmed on X`, `observed`, `assumed`, `not located`): see [evidence rules](../evidence-rules.md).

## 1. Device

- **Model:** ASIN AQUA HOME, in a CLF (free chlorine probe) and a REDOX variant.
- **Pump ports:** 4 independent ports — pH−, chlorine (or OXY Pure on the same port), flocculant, algicide — the same layout as OXY Pure. Unlike SALT there is no shared third-pump port and no algicide/flocculant routing via `byte[37]` bit 7.
- **Optional hardware / settings:** water level meter with refill valve, heating control (heat pump / electric heater), antifreeze, variable-speed filtration pump (Speck, Pentair, Hayward, Dab E.SWIM, Uwe EO PM), backwash valve.
- **Identification on the wire:** v7 `byte[4]` unit type, exact sub-type: `0x02` = HOME CLF, `0x03` = HOME REDOX (Issue #110). One profile covers all HOME units (see §9 for the former firmware A/B split).
- **Sources:**
  - Unit serial 110128063 (`0x06906bbf`), HOME CLF, frame 2026-04-28 08:27:07, compared with the Aseko Live app (Issue #110; domin211, DomSchCoding).
  - Serial 110175608, HOME REDOX (`byte[4]` = `0x03`), @dtpugh diagnostics: Issues #134, #135, #136, #137, #139, #151.
  - Serial 110169464, HOME, @dtpugh's four Issue #133 diagnostics (24 h nonstop, P1 only, P1 & P2, OFF manual).
  - Serial 110071590 (chlorine flow rate, Issues #110/#115).
  - Cross-checks on an ASIN AQUA Salt (settings toggled one at a time, 2026-09-11..14) and on OXY/NET frames.

## 2. Frame structure

v7: 120 bytes in one TCP payload, 3 × 40-byte segments. Each segment header: bytes `0–3` serial (big-endian), `4` unit type, `5` segment marker (`0x01` / `0x03` / `0x02`), `6–11` timestamp (YY MM DD hh mm ss). Bytes 39 and 118–119 may be a checksum (not identified).

Representative frame, serial 110128063, 2026-04-28 08:27:07:

```
Seg1 (bytes   0–39): 06 90 6b bf  02 01  1a 04 1c 08 1b 07
                     00 28 02 75 00 00 00 00 00 02 90 fe 70 01 7b 08 00 00 ff ff 00 00 00 00 00 43 0a 85

Seg2 (bytes  40–79): 06 90 6b bf  02 03  1a 04 1c 08 1b 07
                     46 03 0a 19 08 00 10 00 12 00 16 00 02 7c 01 7b 03 15 00 0c 00 28 01 e0 2a 30 a0 d8

Seg3 (bytes 80–119): 06 90 6b bf  02 02  1a 04 1c 08 1b 07
                     00 3c 00 3c 00 3c 00 3c 00 0a 0d 21 37 64 00 f0 14 02 58 0f 0f 0f 1e 14 ff bc 02 71
```

## 3. Byte map

Example values are from the representative frame unless stated otherwise.

### Segment 1 — bytes 0–39, live data

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| 0–3 | `serial_number` | big-endian u32 | confirmed | repeated in every segment header |
| 4 | `configuration` / unit type | `0x02` CLF, `0x03` REDOX | confirmed | Issue #110 |
| 5 | segment marker | `0x01` | confirmed | |
| 6–11 | `timestamp` | YY MM DD hh mm ss | confirmed | `1a 04 1c 08 1b 07` = 2026-04-28 08:27:07 |
| 12 | dosing warnings | bit field, §4 | confirmed | `0x00` |
| 13 | alarms | bit field, §4 | confirmed | `0x28` |
| 14–15 | `ph` | u16 ÷ 100 | confirmed | `0x0275` = 6.29 |
| 16–17 | `free_chlorine` | u16 ÷ 100 mg/l | confirmed | 0.00 mg/l |
| 18–19 | unused on CLF | — | — | `0x0000` (no REDOX probe); the profile reads `redox` for the REDOX variant with no evidence recorded |
| 20–21 | `free_chlorine_mv` | u16 mV | confirmed | 2 mV |
| 22 | settings | bit field, §4 | confirmed | `0x90` |
| 23–24 | `air_temperature` | s16 ÷ 10 | assumed | `0xFE70` (no air probe, the SALT marker) in every captured HOME frame, so no entity yet; the Aseko Live app shows air temperature on HOME units |
| 25–26 | `water_temperature` | u16 ÷ 10 °C | confirmed | 37.9 °C |
| 27 | `water_level` | cm | confirmed | 8 cm (domin211, Issue #110) |
| 28 | `water_flow_to_probes` | `== 0xAA` → flow | confirmed | `0x00` → no flow |
| 29 | actuators | bit field, §4 | see §4 | `0x00`, all stopped |
| 30–31 | — | padding | — | `0xFFFF` here; byte 31 see §8 |
| 32–36 | unknown | — | — | `0x00` |
| 37 | settings / schedule | bit field, §4 | confirmed | `0x43` |
| 38 | settings / state flags | bitmask | — | `0x0a`; `0x10` heating linked to filtration → `heating_linked_to_filtration`, assumed as on SALT (confirmed there 2026-09-14); other bits see §8 |
| 39 | checksum | 0xAA XOR bytes 0–38 | confirmed | `0x85`; the decoder checks it |

### Segment 2 — bytes 40–79, setpoints and schedule

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| 40–51 | segment header | serial, type, marker `0x03`, timestamp | confirmed | |
| 52 | `ph_target` | ÷ 10 | confirmed | 7.0 |
| 53 | `free_chlorine_target` (CLF) | ÷ 10 mg/l | confirmed | 0.3 mg/l |
| 53 | `redox_target` (REDOX) | × 10 mV | assumed | no evidence recorded |
| 53 | `chlorine_dose_target` | — | assumed | no evidence recorded |
| 54 | `flocculant_dose_target` | ml/h | confirmed | 10 ml/h; same position as SALT algicide; gated by `byte[37] != 0xFF` |
| 55 | `water_temperature_target` | °C | confirmed | heating setpoint (Issue #135, 110175608); antifreeze setpoint while antifreeze is on (§5); 25 °C with heating disabled on 110128063 |
| 56–57 | `filtration_period_1_start` | hh mm | confirmed | 08:00, last-configured |
| 58–59 | `filtration_period_1_end` | hh mm | confirmed | 16:00, last-configured |
| 60–61 | `filtration_period_2_start` | hh mm | confirmed | 18:00, always transmitted (Issue #133) |
| 62–63 | `filtration_period_2_end` | hh mm | confirmed | 22:00, always transmitted (Issue #133) |
| 64–65 | unknown | — | — | `0x027c` = 636; byte 65 see §8 |
| 66–67 | unknown | — | — | `0x017b` = 379, equals the water temperature raw value |
| 68 | `backwash_interval` | days | confirmed | 3 |
| 69–70 | `backwash_start_time` | hh mm | confirmed | 21:00 |
| 71 | `backwash_duration` | × 10 s | confirmed | 120 s |
| 72 | `algaecide_dose_target` | ml/m³/day | confirmed | 0; same position as OXY Pure |
| 73 | unknown | — | — | `0x28` = 40 |
| 74–75 | `startup_delay` | u16 s | confirmed | 480 s |
| 76–77 | `max_refill_time` | u16 s | assumed | 10800 s = 180 min, plausible; verified on SALT only |
| 78 | live state | bit field, §4 | confirmed | `0xa0` here |
| 79 | checksum | 0xAA XOR bytes 40–78 | confirmed | `0xd8`; the decoder checks it |

### Segment 3 — bytes 80–119, parameters and flow rates

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| 80–91 | segment header | serial, type, marker `0x02`, timestamp | confirmed | |
| 92–93 | `pool_volume` | u16 m³ | confirmed | 60 m³ |
| 94 | unknown | — | — | `0x00` |
| 95 | `ph_minus_flow_rate` | ml/min | observed | 60; the Aseko Live app lists the pH− pump, the rate itself was not compared (`byte[95]` confirmed on SALT) |
| 96 | unknown | — | — | `0x00` |
| 97 | unknown | — | — | `0x3c` = 60; `ph_plus_flow_rate`? unconfirmed, not mapped |
| 98 | unknown | — | — | `0x00` |
| 99 | `chlorine_flow_rate` | ml/min | confirmed | 60 (serials 110071590 / 110128063, Issues #110, #115) |
| 100 | unknown | — | — | `0x00` |
| 101 | `flocculant_flow_rate` | ml/min | confirmed | 10 (Issues #110, #115) |
| 102 | `water_level_low_alarm` | cm | confirmed | 13 (domin211, Issue #110) |
| 103 | `water_level_refill_start` | cm | confirmed on SALT | 33, between low alarm 13 and refill stop 55 |
| 104 | `water_level_refill_stop` | cm | confirmed | 55 (domin211, DomSchCoding, Issue #110) |
| 105 | `water_level_high_alarm` | cm | confirmed | 100 (domin211, Issue #110) |
| — | `algaecide_flow_rate` | — | not located | entity reads unknown; §5 |
| 106–107 | `dosing_delay` | u16 s | confirmed | 240 s |
| 108 | unknown | — | — | `0x14` = 20 |
| 109–110 | unknown | — | — | `0x0258` = 600 |
| 111 | unknown | — | — | `0x0f` |
| 112 | `ph_minus_concentration` | % | confirmed | 110175608, 5 % → 10 % → 5 % (Issue #139); raw `0x0f` in the 110128063 frame against 5 % in the app, see §8 |
| 113 | unknown | — | — | `0x0f` |
| 114 | unknown | — | — | `0x1e` = 30 |
| 115 | `max_ph_doses` | count | observed | 20; position confirmed on SALT (2026-09-12), HOME setting never compared |
| 116 | — | padding | — | `0xff` |
| 117 | unknown | — | — | `0xbc` |
| 118 | unknown | — | — | `0x02` |
| 119 | checksum | 0xAA XOR bytes 80–118 | confirmed | `0x71`; the decoder checks it |

## 4. Bit fields

### `byte[12]` — dosing warnings

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x20` | too many doses of disinfection (`alarm_max_disinfection_dose`) | confirmed | Issue #134 |
| `0x40` | too many doses of pH (`alarm_ph_dosing_ineffective`) | confirmed | Issues #134, #151 |

### `byte[13]` — alarms

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x01` | too many doses of disinfection (`alarm_max_disinfection_dose`) | confirmed | Issue #151 |
| `0x02` | too many doses of pH (`alarm_ph_dosing_ineffective`) | assumed | inferred, symmetric to `0x01`; no frame capture |
| `0x04` | no flow to probes (`alarm_no_flow_to_probes`) | confirmed on NET | DomSchCoding, NET frame |
| `0x08` | rapid pH change (`alarm_rapid_ph_change`) | assumed | set on 110128063 (`0x28`) with no matching alarm known in the app |

### `byte[22]` — settings

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x01`, `0x02`, `0x20` | heating condition on SALT (time window / outside temperature / below) | — | not decoded on HOME: the HOME VSP frames carry `0x83` with both `0x01` and `0x02`, never seen on SALT |
| `0x08` | variable-speed pump setting (`variable_speed_pump_enabled`) | confirmed | Issue #137, 110175608: `0x83` off, `0x8b` on (any brand); also toggled on SALT |
| `0x10` | backwash schedule (`backwash_schedule_enabled`) | observed | set on 110128063 with backwash every 3 days (`0x90`); confirmed on SALT (2026-09-13) |
| `0x80` | unknown | — | |

### `byte[29]` — actuators

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x01` | backwash valve relay (`backwash_running`) | assumed | confirmed on SALT |
| `0x02` | water filling active (`refilling`) | confirmed | DomSchCoding, Issue #100; also on SALT (2026-09-06) against the refill thresholds |
| `0x04` | heating running (`heating_running`) | assumed | JS-DE-Tech relay_byte bit 2; no HOME frame with the heater running |
| `0x08` | filtration pump relay (`filtration_relay`) | confirmed | stays set under the manual override; `filtration_running` is derived, §5 |
| `0x10` | algicide pump running (`algaecide_pump_running`) | assumed | as on OXY; read only once the algicide flow rate is located, so no state yet |
| `0x20` | flocculant pump running (`flocculant_pump_running`) | assumed | as on OXY (confirmed there) |
| `0x40` | chlorine pump running (`chlorine_pump_running`) | assumed | port may be chlorine or OXY Pure |
| `0x80` | pH− pump running (`ph_minus_pump_running`) | assumed | |

### `byte[37]` — settings and filtration schedule

One bit field of settings shared by HOME and SALT. These are settings, not hardware: Waterlevel, Heating control or the VS pump can be switched on without the device connected, and the app then shows nothing for it.

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x01` | always set | observed | every frame |
| `0x02` | flow detection enabled (`flow_detection_enabled`) | confirmed on SALT | 2026-09-13; set in HOME `0x43` / `0x53`, clear in Issue #135's `0x41` / `0x45` / `0x49` |
| `0x04` | settings menu open / manual override (`service_menu_open`) | confirmed | `0x35` manual OFF (Issue #133); `0x47` / `0x57` are the same bit |
| `0x08` | heating control enabled (`heating_control_enabled`) | confirmed | Issue #135, 110175608; same bit on SALT (2026-09-13) |
| `0x10` | filtration period 1 enabled | confirmed | Issue #133 |
| `0x20` | filtration period 2 enabled | confirmed | Issue #133 |
| `0x40` | Waterlevel enabled (`water_level_sensor_enabled`) | confirmed on SALT | 2026-09-13; set on the level-meter HOME units, clear on 110169464 and in the antifreeze frame `0x81` |
| `0x80` | antifreeze enabled (`freeze_protection_enabled`) | confirmed | Issue #136, 110175608; on SALT this bit is algicide routing |

No period bit → nonstop 24 h. Every captured HOME value, read with these bits:

| `byte[37]` | Source | Schedule | Menu | Heating control | Antifreeze | Flow detection | Waterlevel |
|---|---|---|---|---|---|---|---|
| `0x43` | Issue #110 | nonstop 24 h | — | — | — | ✓ | ✓ |
| `0x53` | Issue #110 | period 1 | — | — | — | ✓ | ✓ |
| `0x47` / `0x57` | Issue #110 | nonstop / period 1 | ✓ | — | — | ✓ | ✓ |
| `0x01` | Issue #133 | nonstop 24 h | — | — | — | — | — |
| `0x11` | Issue #133 | period 1 | — | — | — | — | — |
| `0x31` | Issue #133 | periods 1 and 2 | — | — | — | — | — |
| `0x35` | Issue #133 | periods 1 and 2 | ✓ (manual OFF) | — | — | — | — |
| `0x41` | Issue #135 | nonstop 24 h | — | — | — | — | ✓ |
| `0x45` | Issue #135 | nonstop 24 h | ✓ | — | — | — | ✓ |
| `0x49` | Issue #135 | nonstop 24 h | — | ✓ | — | — | ✓ |
| `0x81` | Issue #136 | nonstop 24 h | — | — | ✓ | — | — |

### `byte[78]` — live state and VS pump type

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x0C` | VS pump type group (`variable_speed_pump_type`) | confirmed | `0x22` → `0x00` Speck / Uwe EO PM (kept with the VS pump off), `0x26` → `0x04` Pentair / Dab E.SWIM, `0x2a` → `0x08` Hayward (Issue #137); same groups on SALT (2026-09-13/14) |
| `0x02` / `0x01` | filtration running / standing | confirmed on SALT | all HOME values have `0x02` set (filtration running at capture) |
| `0x20` | unknown | — | set in all HOME values |
| `0x40` | winter mode active | confirmed on SALT | |
| `0x80` | heating allowed now | confirmed on SALT | |

## 5. Model-specific behaviour

### Settings bits are not hardware

Serial 110128063 sends `byte[37]` = `0x43` (Waterlevel on) and `byte[27]` = 8 cm, while the app showed `---` for the water level: the level meter setting is on without a working sensor. Refilling was not active (`---`, Issue #100).

### Filtration schedule and period bytes

Bytes 56–63 always carry the last-configured schedule; the unit does not clear them when switching to nonstop 24 h or disabling period 2. The active mode lives only in `byte[37]` (`0x10` / `0x20`). Verified on 110169464: bytes 60–63 stay populated in all four Issue #133 modes (24 h nonstop, P1 only, P1 & P2, OFF manual). Bytes 60–63 are therefore read unconditionally on every model with a filtration output (SALT, HOME, OXY, PROFI — PROFI without a toggling capture); `filtration_schedule` reports period 1 when period 2 is inactive. NET has no filtration output.

`0x43` should be read as "consistent with nonstop 24 h": a May 2026 frame from mannekung's unit, taken after switching to nonstop 24 h, still showed `0x53` while the Aseko app was in "Suche" (search) mode (Issue #110).

### Manual OFF override (`byte[37]` `0x04`)

In the `0x35` manual OFF frame, `byte[29]` bit `0x08` is still set — it stays set in all four Issue #133 frames. `filtration_relay` keeps the bit as sent; the derived `filtration_running` reports the pump off while bit `0x04` is set, on the profiles flagged `MENU_BIT_SWITCHES_FILTRATION_OFF` (HOME; `decoding/derived.py`). `service_menu_open` (someone at the unit) and `filtration_schedule` (what runs when nobody is) share the byte but are unrelated facts.

The override is HOME-only. On SALT the same bit marks the settings menu being open, which says nothing about what the person did (they may have switched the pump on), so forcing it off would invent a state (see [SALT analysis](salt_device_analysis.md), byte[37]). Whether HOME's bit is literally the same menu flag is unverified: the Issue #133 frames were downloaded one per mode, so a HOME unit going quiet the way SALT does would not have shown up.

### Heating and antifreeze (`byte[55]`)

`byte[55]` is the heating setpoint (Issue #135). With antifreeze on, it drops from the heating setpoint (e.g. 27 °C) to the antifreeze setpoint (e.g. 4, 5 or 9 °C, user-set; Issue #136). On SALT the corresponding winter mode is `byte[22]` `0x04`, because `byte[37]` `0x80` is algicide routing there. `heating_control_enabled` (`byte[37]` `0x08`) is the master enable, separate from the heating output `byte[29]` `0x04`.

### Dosing alarms: two encodings of one fault

@dtpugh's diagnostics on 110175608:

- **Issue #134** (2026-07-05), before/after clearing on the controller: both warnings → `byte[12]` = `0x60`; pH only → `0x40`; cleared → `0x00`; `byte[13]` stayed `0x00`.
- **Issue #151** (2026-08-06/08): "Maximum disinfection dose exceeded" → `byte[13]` = `0x01` (`byte[12]` = `0x00`); pH fault → `byte[12]` = `0x40`; cleared → both `0x00`.

The disinfection fault appeared in `byte[12]` `0x20` in July and in `byte[13]` `0x01` in August, likely a firmware change; both paths are ORed. Issue #151 reports the same fault as `ins[12]` bit `0x80` on v8 frames; that is a hypothesis for now — the v8 profiles do not read `alarm_max_disinfection_dose`.

### Variable-speed pump

Supported on some HOME REDOX units (110175608). The brand is picked on the unit and in the Aseko app; the unit stores a protocol group, not a brand, so two brands share a value (`byte[78]` `0x0C`). `byte[22]` `0x08` is the setting, not the pump running.

### Algicide flow rate and byte[103]

`byte[103]` was read both as `algaecide_flow_rate` (33 ml/min) and as `water_level_refill_start` (33 cm) on 110128063. It is the threshold: bytes 102–105 are the level thresholds on SALT (confirmed against the unit, 2026-09-11), and 13 / 33 / 55 / 100 cm are in order here. The captured OXY sends its algicide flow rate on `byte[103]`, and it has no level sensor connected. HOME's algicide flow rate is not located, so neither the algicide pump state nor its consumption is computed.

### Chlorine / OXY Pure port

The chlorine port can be configured as chlorine or OXY Pure (same physical port, same `byte[29]` bit). The routing byte is not found in the frames.

## 6. Ground truth

Serial 110128063, frame 2026-04-28 08:27:07, against the Aseko Live app; pH and water temperature differ because the app value was read later that day.

| Date | Field | Decoded | Unit / app | Result |
|---|---|---|---|---|
| 2026-04-28 | `ph` | 6.29 | 6.56 (later) | match (Δt) |
| 2026-04-28 | `free_chlorine` | 0.00 mg/l | 0.00 mg/l | match |
| 2026-04-28 | `water_temperature` | 37.9 °C | 38.2 °C (later) | match (Δt) |
| 2026-04-28 | `water_flow_to_probes` | False | NO | match |
| 2026-04-28 | `filtration_running` | False | STOP | match |
| 2026-04-28 | `filtration_schedule` | nonstop 24 h | NONSTOP 24H | match (Issue #110) |
| 2026-04-28 | filtration times | 08:00–16:00 / 18:00–22:00 | NONSTOP 24H | expected: last-configured times |
| 2026-04-28 | `service_menu_open` | False | nobody at the unit | match |
| 2026-04-28 | `water_level` | 8 cm | `---` (level meter not working) | frame value only |
| 2026-04-28 | `refilling` | False | `---` (valve not active) | match (Issue #100) |
| 2026-04-28 | water level thresholds | 13 / 33 / 55 / 100 cm | configured | not compared value by value |
| 2026-04-28 | `ph_target` | 7.0 | 7.0 | match |
| 2026-04-28 | `free_chlorine_target` | 0.3 mg/l | 0.3 | match |
| 2026-04-28 | `flocculant_dose_target` | 10 ml/h | 10 ml/h | match |
| 2026-04-28 | `algaecide_dose_target` | 0 ml/m³/day | 0 ml/m³/day | match |
| 2026-04-28 | `water_temperature_target` | 25 °C | `---` (heating disabled) | not comparable |
| 2026-04-28 | `backwash_interval` | 3 | every 3 days | match |
| 2026-04-28 | `backwash_start_time` | 21:00 | 21:00 | match |
| 2026-04-28 | `backwash_duration` | 120 s | 02:00 min | match |
| 2026-04-28 | `pool_volume` | 60 m³ | 60 m³ | match |
| 2026-04-28 | `startup_delay` | 480 s | 8 min | match |
| 2026-04-28 | `dosing_delay` | 240 s | 4 min | match |
| 2026-04-28 | `ph_minus_flow_rate` | 60 | pH− pump listed, rate not shown | not compared |
| 2026-04-28 | `chlorine_flow_rate` | 60 | Chlor Pure listed, rate not shown | not compared |
| 2026-04-28 | `flocculant_flow_rate` | 10 | Floc+c listed, rate not shown | not compared |
| 2026-04-28 | `ph_minus_concentration` | 15 % (raw `0x0f`) | 5 % | **mismatch**, unresolved — see §8 |
| Issue #135 | `heating_control_enabled` | True / False | app setting | match (110175608) |
| Issue #135 | `water_temperature_target` | heating setpoint | app setting | match (110175608) |
| Issue #136 | `freeze_protection_enabled` | True / False | app setting | match (110175608) |
| Issue #137 | `variable_speed_pump_enabled` / type | on/off, brand group | app setting | match (110175608) |
| Issue #139 | `ph_minus_concentration` | 5 → 10 → 5 % | app setting | match (110175608) |

## 7. Settings the frame does not carry

- Algicide flow rate: the app lists the algicide pump, but the value is not located in the frame.
- Air temperature: shown in the Aseko Live app on HOME units, but bytes 23–24 were `0xFE70` (no probe marker) in every captured HOME frame.
- Chlorine / OXY Pure port configuration: no routing byte found.

## 8. Open questions

1. **Per-pump bits in `byte[29]`** (chlorine, pH−, algicide, flocculant) are placeholders taken from OXY/NET. A capture with a single HOME pump running (e.g. algicide only) would pin each bit.
2. **`heating_running`** (`byte[29]` `0x04`): needs a frame captured while the heat pump / electric heater is actually running.
3. **`water_temperature_target`**: confirmed as heating setpoint on 110175608; a frame from a unit where the app actively shows a target temperature (not `---`) would validate it further.
4. **Algicide flow rate location**: download diagnostics, change the algicide flow rate on the unit, download again.
5. **`byte[37]` `0x40` (Waterlevel) and `0x02` (Flow detection) on HOME**: a HOME owner toggling each setting once, with a marked test case after each change.
6. **`byte[22]` on the HOME VSP unit = `0x83`**: bits `0x01` and `0x02` both set (never on SALT) and `0x80` unknown; a HOME capture before/after changing the heating condition would explain them.
7. **Manual OFF sub-flags**: in the `0x35` frame bytes 31, 38 and 65 each rise by about 1 (`0x00→0x02`, `0x02→0x03`, `0xa3→0xa4`). Single observation, no meaning assigned; repeated OFF/ON captures would tell.
8. **HOME menu flag behaviour**: whether `byte[37]` `0x04` on HOME is a standing override or a menu session (as on SALT); a series of frames while someone is in the menu would settle it.
9. **`byte[78]` `0x20`**: unknown; set on every HOME value.
10. **`byte[112]` raw vs %**: the 110128063 frame has `0x0f` (15) at byte 112 while the app showed 5 %; Issue #139 frames confirm the byte tracks the setting. A frame with a known concentration on a CLF unit would clarify the encoding.
11. **`max_refill_time`, `max_ph_doses`, refill start threshold**: a glance at the unit settings compared with bytes 76–77, 115 and 103.
12. **REDOX variant values** (`redox`, `redox_target` on byte 53): no evidence recorded; a REDOX HOME dump with the app's REDOX value.

## 9. History

- **2026-09-13 — one HOME, not two firmwares.** HOME v7 was split into "firmware A" and "firmware B" by `byte[37]` bit `0x40` (with two HOME profiles in the decoder). Toggling settings on an ASIN AQUA Salt showed `0x40` is the Waterlevel setting; all former A/B values decode with one bit field, and one profile covers every HOME unit. Consequences versus the old firmware-A decoding: `0x53` is period 1 (was "period 1 and 2"); `0x47` / `0x57` decode to a schedule with the menu open (were "transitional edit states" with no schedule).
- **`byte[103]`** was decoded as `algaecide_flow_rate` (Issues #110, #115, marked fixed); now the refill start threshold, algicide flow rate not located. Previously bit `0x20` counted algicide and flocculant for one running pump ("bit 5, HOME shared"); pump bits now follow OXY (algicide `0x10`, flocculant `0x20`).
- **`max_refill_time`** was read from bytes 94–95 (`0x003c` = 60, overlapping the pH− flow rate on byte 95) before v1.9; moved to bytes 76–77 in seconds (verified on SALT against Aseko Live). Byte 94 is unknown again.
- **Issue #133 fix:** bytes 60–63 were gated on `byte[37]` `0x20`, so existing period 2 entities flipped to unknown when the user switched from P1 & P2 to P1 only; now read unconditionally.
- **Issue #115:** HOME `algaecide_pump_running` was missing; fixed by reading the pump ports independently of `byte[37]` (independent-pump-port branch).
- **`byte[78]`** was an open item (brand ID or pump parameter); resolved as pump type group (Issue #137, SALT).
- Early decoding used `UNIT_TYPE_HOME_CLF` for `byte[4]` = `0x02`, and field names such as `cl_free`, `start1`/`stop1`, `flowrate_*`; values are now named features in `decoding/features/`.
- Working notes for Issues #133 and #135 were kept in `docs/temp/`.

## 10. References

- Issues: #100 (refilling bit), #110 (`byte[37]` `0x43` nonstop, representative frame, water level thresholds), #115 (HOME algicide pump / independent ports), #133 (period bits, period 2 bytes, manual OFF), #134 and #151 (dosing warnings/alarms), #135 (heating control, `byte[55]`), #136 (antifreeze), #137 (VS pump setting and type), #139 (pH− concentration).
- Related analyses: [SALT](salt_device_analysis.md), [OXY](oxy_device_analysis.md) (shared byte layout, four pump ports), [NET](net_device_analysis.md), [NET v8](net_v8_device_analysis.md), [PROFI](profi_device_analysis.md).
- Code: [`profiles/v7/home.py`](../../custom_components/aseko_local/decoding/profiles/v7/home.py), [`decoding/features/`](../../custom_components/aseko_local/decoding/features/) (one file per value).
- Tests in `tests/test_decode_v7.py` and `tests/test_decoding_profiles.py`:
  - `test_decode_home` (REDOX frame end-to-end, schedule, max_refill_time), `test_decode_home_clf_real_frame` and `test_home_issue_110_frame` (Issue #110: `0x53` → period 1, waterlevel enabled)
  - `test_decode_home_independent_flowrates`, `test_decode_home_flowrates_unspecified` (`0xFF` → `None`), `test_decode_home_algicide_pump_running`, `test_decode_home_floc_pump_running_independent` (Issue #115)
  - `test_filtration_schedule_new_encoding_24h` / `_p1` / `_p1_and_p2`, `test_service_menu_new_encoding_p1_and_p2`, `test_decode_filtration_period2_real_dtpugh_frames` (Issue #133)
  - `test_filtration_schedule_old_encoding_24h` / `_timer`, `test_filtration_schedule_with_the_menu_open_is_read_from_the_bits` (Issue #110 values)
  - `test_filtration_pump_running_off_when_manual_override`, `test_filtration_pump_running_on_when_not_override`, `test_filtration_pump_running_not_overridden_on_salt`, `test_home_menu_override_forces_the_pump_off`
  - `test_every_home_frame_uses_the_one_home_profile`, `test_home_byte37_is_one_bit_field`
