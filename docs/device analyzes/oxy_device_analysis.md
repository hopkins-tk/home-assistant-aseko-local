# ASIN AQUA Oxygen (v7) — Device Analysis

[Documentation](../README.md) / [Device analyses](README.md)

> **Status:** decoded from logs of one unit (Winnetoux, 2026-04-02, 04-11, 04-12); pump bits, dose targets and flow rates checked against the Aseko Live app, most settings only observed, alarms and level/heating bits assumed from other models.
> **Profile:** [`profiles/v7/oxy.py`](../../custom_components/aseko_local/decoding/profiles/v7/oxy.py) · **Support:** [support matrix](../support_matrix.md)
> **Evidence words** (`confirmed`, `confirmed on X`, `observed`, `assumed`, `not located`): see [evidence rules](../evidence-rules.md).

## 1. Device

- **Model:** ASIN AQUA Oxygen — pH probe plus an OXY Pure (H₂O₂, "SANOSIL") probe; no CLF or REDOX probe. Four independent dosing pump ports (pH−, OXY Pure, flocculant, algicide) and a filtration output. No water level sensor on the captured unit.
- **Wire identification:** v7 `byte[4]` = `0x05` → unit type OXY (exact match, no overlap with the other unit types). Configuration is fixed to pH + OXY Pure (`decode_v7_ph_and_oxy`).
- **Sources:** one unit (Winnetoux, serial 110157165).
  - `oxy_log.log`, 2026-04-02 18:20 – 19:34 (normal frames and a flocculant dosing event).
  - 2026-04-11 log (algicide and OXY Pure pump events, dose targets).
  - `oxy_2026-04-12.log` (pH− pump, parallel pumps).
  - Aseko Live app history and settings for the same unit.
  - An AquaNET log of 2026-04-07 (serial 110200612) for the meaning of the `byte[4]` probe bits and `byte[53]`.

## 2. Frame structure

120 bytes, three 40-byte segments, each starting with the serial (bytes 0–3 repeated) and `byte[4]` unit type. Segment type at bytes 5 / 45 / 85; checksum at bytes 39 / 79 / 119.

| Segment | Type byte | Content |
|---|---|---|
| 0–39 | `0x01` | Live sensor data |
| 40–79 | `0x03` | Setpoints and schedule |
| 80–119 | `0x02` | Parameters and flow rates |

Normal frame (only filtration running), 2026-04-02 19:33:38:

> **Checksum mismatch, suspected transcription error:** the checksum of the middle segment of this frame does not match
> (computed `0x32`, stored `0x3f`). A mistyped hex digit among bytes 40–78 when the frame was
> copied here would explain it, but without the original capture that is not proven, and which
> byte cannot be told from the checksum. Do not use it
> as test data. The flocculant frame below checks out.

```
06 90 dd 6d 05 01 1a 04 02 17 15 0a 00 00 02 cd 00 1e 00 1e fd 9d 80 fe 70 00 5f fe aa 08
00 00 00 00 00 00 00 03 08 35
06 90 dd 6d 05 03 1a 04 02 17 15 0a 48 08 01 19 08 00 10 00 12 00 16 00 02 c0 00 5f 00 0c
1e 0a 01 28 00 f0 0e 10 aa 3f
06 90 dd 6d 05 02 1a 04 02 17 15 0a 00 29 00 3c 00 3c 00 3c 00 0a 1e 3c 6e 96 00 78 08 02
58 0f 2b 0f 1e 1e aa cb 00 3a
```

Flocculant pump running, 2026-04-02 19:33:52 (about 2 s):

```
06 90 dd 6d 05 01 1a 04 02 17 15 17 00 00 02 cd 00 1e 00 1e fd 9d 80 fe 70 00 5f fe aa 28
00 00 00 00 00 00 00 03 08 08
06 90 dd 6d 05 03 1a 04 02 17 15 17 48 08 01 19 08 00 10 00 12 00 16 00 02 c0 00 5f 00 0c
1e 0a 01 28 00 f0 0e 10 aa 2f
06 90 dd 6d 05 02 1a 04 02 17 15 17 00 29 00 3c 00 3c 00 3c 00 0a 1e 3c 6e 96 00 78 08 02
58 0f 2b 0f 1e 1e aa cb 00 27
```

Only change versus the normal frame: `byte[29]` `0x08` → `0x28` (+`0x20`); the timestamp second (`byte[11]`) and the checksums change as expected. All other bytes are identical.

## 3. Byte map

Values are from the Winnetoux unit. Setpoint values marked (04-11) come from the 2026-04-11 log; the 2026-04-02 frame above differs there (see §8).

### Bytes 0–39 — live data

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| 0–3 | `serial_number` | big-endian integer | confirmed | Repeated in every segment header. |
| 4 | unit type / probe flags | `0x05` = OXY | confirmed | See §4 `byte[4]`. |
| 5 | segment type | `0x01` | confirmed | |
| 6–11 | `timestamp` | Y M D h m s | confirmed | `1a 04 02 17 15 0a` = 2026-04-02 23:21:10 while the log said 19:33:38: device clock not synchronised. |
| 12 | dosing warnings | bit field | assumed | `0x00` in every OXY frame; HOME encoding. See §4. |
| 13 | alarms | bit field | assumed | `0x00` in every OXY frame. See §4. |
| 14–15 | `ph` | ÷100 | observed | `02 cd` = 7.17; not compared with the app. |
| 16–17 | CLF slot | — | observed | `0x001E` invariant placeholder, not read. See §5. |
| 18–19 | REDOX slot | — | observed | `0x001E` invariant placeholder, not read. |
| 20–21 | `free_chlorine_mv` slot | signed | observed | `0xFD9D` = −611 mV, placeholder, not read. |
| 22 | settings | bit field | assumed | `0x80`. See §4. |
| 23–24 | `air_temperature` | ÷10 | assumed | `0xFE70` (no air probe, the SALT marker) in every OXY frame, so no entity yet. See §7. |
| 25–26 | `water_temperature` | ÷10 | observed | `00 5f` = 9.5 °C; not compared with the app. |
| 27 | `water_level` | cm | assumed | Confirmed on HOME; `0xFE` on the captured OXY = no level sensor connected (other OXY units may have one). |
| 28 | `water_flow_to_probes` | `== 0xAA` | observed | `0xAA` = flow; not compared with the app. |
| 29 | actuators | bit field | confirmed | See §4. |
| 37 | settings / routing | bit field | assumed | `0x03` in every frame. See §4. |
| 38 | — | — | not located | `0x08`, meaning unknown. |
| 39 | checksum | | confirmed | |

### Bytes 40–79 — setpoints and schedule

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| 45 | segment type | `0x03` | confirmed | |
| 52 | `ph_target` | ÷10 | observed | `0x48` = 7.2; not compared with the app. |
| 53 | `oxygen_dose_target` | raw, ml/m³/d | confirmed | `0x08` = 8 on 2026-04-02, 12 after the 2026-04-06 change. Universal disinfection setpoint slot, see §5. |
| 54 | `flocculant_dose_target` | raw, ml/h | confirmed | 10 (04-11), matches the app. |
| 55 | `water_temperature_target` | °C | observed | `0x19` = 25 °C; not compared with the app. |
| 56–57 | `filtration_period_1_start` | h, min | observed | 08:00 in every frame; not compared with the app. |
| 58–59 | `filtration_period_1_end` | h, min | observed | 16:00 in every frame. |
| 60–61 | `filtration_period_2_start` | h, min | observed | 18:00 in every frame. Kept after period 2 is disabled, see §5. |
| 62–63 | `filtration_period_2_end` | h, min | observed | 22:00 in every frame. |
| 68 | `backwash_interval` | days, 0 = off | observed | 0 (disabled); not compared with the app. |
| 69–70 | `backwash_start_time` | h, min | observed | `0c 1e` = 12:30; not compared with the app. |
| 71 | `backwash_duration` | ×10 s | observed | `0x0a` = 100 s; not compared with the app. |
| 72 | `algaecide_dose_target` | raw, ml/m³/d | confirmed | 15 (04-11), matches the app. |
| 73 | — | — | not located | `0x28`, meaning unknown. |
| 74–75 | `startup_delay` | s | observed | `00 f0` = 240 s. |
| 76–77 | `max_refill_time` | s | assumed | `0e 10` = 3600 s (60 min), plausible; verified on SALT against the app only. |
| 78 | live state | bit field | assumed | `0xAA`. See §4. |
| 79 | checksum | | confirmed | |

### Bytes 80–119 — parameters and flow rates

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| 85 | segment type | `0x02` | confirmed | |
| 92–93 | `pool_volume` | m³ | observed | `00 29` = 41 m³; not compared with the app. |
| 95 | `ph_minus_flow_rate` | ml/min | confirmed | 60 ml/min. |
| 97 | pH+ flow rate | ml/min | assumed | 60; position unconfirmed, `ph_plus_flow_rate` is not mapped on any protocol. |
| 99 | `oxygen_flow_rate` | ml/min | confirmed | 60 ml/min. |
| 101 | `flocculant_flow_rate` | ml/min | confirmed | 10 ml/min; see §6 for the consumption check. |
| 102, 104, 105 | water level thresholds | cm | assumed | Level thresholds on SALT. `water_level_refill_start` is not located on OXY: `byte[103]` is the algicide flow rate. |
| 103 | `algaecide_flow_rate` | ml/min | confirmed | 60 ml/min (04-11), stable across sessions. |
| 106–107 | `dosing_delay` | s | observed | `00 78` = 120 s; not compared with the app. |
| 112 | `ph_minus_concentration` | % | assumed | Confirmed on HOME. |
| 115 | `max_ph_doses` | count | observed | `0x1e` = 30; position confirmed on SALT, OXY setting never compared. |
| 119 | checksum | | confirmed | |

All OXY flow rate bytes use ml/min.

## 4. Bit fields

### `byte[4]` — unit type / probe flags

`0x05` = `0b00000101`, unchanged across all captured OXY frames. The bits are a live probe-configuration map (see §5), the exact value `0x05` identifies OXY.

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x01` | REDOX probe absent | assumed | Set on OXY (no REDOX). |
| `0x02` | CLF probe absent | confirmed on NET | Clear on OXY although there is no CLF probe: the SANOSIL probe sits in the CLF slot. Toggled on a NET when switching to DOSE mode. |
| `0x04` | DOSE mode inactive | assumed | Set on OXY (concentration-based control). |
| `0x08` | SANOSIL / OXY Pure probe absent | assumed | Clear on OXY = OXY Pure present. |
| `0x05` (whole byte) | unit type OXY | confirmed | Profile configuration fixed to pH + OXY Pure. |

### `byte[12]` — dosing warnings

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x20` | max disinfection dose | assumed | HOME encoding (Issue #134); never set on OXY. |
| `0x40` | pH dosing ineffective | assumed | HOME encoding (Issue #134); never set on OXY. |

See [`home_device_analysis.md`](home_device_analysis.md) §"Dosing warnings & alarms".

### `byte[13]` — alarms

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x01` | `alarm_max_disinfection_dose` | assumed | HOME encoding; `0x00` in every OXY frame. |
| `0x02` | `alarm_ph_dosing_ineffective` | assumed | HOME encoding; never set on OXY. |
| `0x04` | `alarm_no_flow_to_probes` | confirmed on NET, HOME | Never set on OXY. |
| `0x08` | `alarm_rapid_ph_change` | assumed | From `error_codes.md`; never set on OXY. |

### `byte[22]` — settings

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x08` | `variable_speed_pump_enabled` | assumed | Confirmed on HOME; clear on OXY (`0x80`). |

### `byte[29]` — actuators

All bits are independent and additive; any combination is valid (see §5).

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x01` | `backwash_running` | assumed | Confirmed on SALT. |
| `0x02` | `refilling` | assumed | Confirmed on HOME and SALT. |
| `0x04` | `heating_running` | assumed | JS-DE-Tech relay_byte bit 2. |
| `0x08` | `filtration_relay` (→ `filtration_running`) | confirmed | Set in every captured frame; filtration ran 24 h. |
| `0x10` | `algaecide_pump_running` | confirmed | 2026-04-11: `0x18` exactly while the algicide pump ran. Profile override `decode_v7_oxy`. |
| `0x20` | `flocculant_pump_running` | confirmed | 2026-04-02 19:33:52: `0x28` at the floc dosing event. |
| `0x40` | `oxygen_pump_running` | confirmed | 2026-04-11: `0x48` exactly while the OXY Pure pump ran. |
| `0x80` | `ph_minus_pump_running` | confirmed | 2026-04-12: `0x08` → `0x88` at pH− pump on. |

### `byte[37]` — settings / routing

`0x03` in every captured OXY frame (2026-04-02 and 2026-04-11). Bits mapped on an ASIN AQUA Salt by toggling one setting at a time (see [`salt_device_analysis.md`](salt_device_analysis.md) §byte[37]).

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x01` | always set | observed | |
| `0x02` | `flow_detection_enabled` | assumed | As on SALT; set on OXY. |
| `0x04` | `service_menu_open` | observed | Clear in every OXY frame; menu never captured open. |
| `0x10` | filtration period 1 | observed | Clear; with `0x20` clear reads nonstop, matching 24 h filtration. No schedule transition captured. |
| `0x20` | filtration period 2 | observed | Clear. Same bits on OXY, HOME and SALT. |
| `0x40` | `water_level_sensor_enabled` | assumed | As on SALT; clear on OXY, fits `byte[27]` = `0xFE`. |
| `0x80` | SALT third-pump routing | assumed | Clear; not applied on OXY, algicide and flocculant have their own bytes. |

### `byte[78]` — live state

`0xAA` on the Winnetoux frames. Not read by the OXY profile.

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x02` | filtration state | confirmed on SALT, NET | Set, filtration was running. |
| `0x08` | VS pump type | confirmed on SALT | Set, but `byte[22]` `0x08` (VS pump enabled) is clear on OXY. |
| `0x20` | — | not located | Not understood on OXY. |
| `0x80` | — | not located | Not understood on OXY. |

## 5. Model-specific behaviour

### Detection and hardware model

- `byte[4]` is a live probe-configuration bitmap, not a hardware identifier. On 2026-04-07 an AquaNET (serial 110200612) sent `0x0b` at 13:15:00 (ml/m³/h DOSE mode, CLF disabled) and `0x09` at 13:16:10 (CLF active): XOR `0x02`, exactly the CLF bit.
- The Aseko cloud shows the correct hardware name regardless of probe configuration because it uses server-side registration of the serial; no byte in the frame encodes the hardware model independently of the probe configuration.
- `0x05` is reliable for OXY: it is the only known value with OXY Pure present, DOSE absent and REDOX absent, and it never changed across the captured OXY frames.

### CLF / REDOX sentinel slots

Bytes 16–17 and 18–19 both read `0x001E` = 30 in every captured frame; bytes 20–21 read `0xFD9D` = −611 mV. As CLF this would be 0.30 mg/L, as REDOX 30 mV (implausible for a pool). The values never fluctuate, which suggests `0x001E` is a placeholder for probe slots with nothing connected on this unit, and the profile creates no CLF or REDOX entities. By contrast, a NET in DOSE mode still sends a real, fluctuating CLF value (`0x006a` = 1.06 mg/L on 2026-04-07) because the probe stays connected.

### `byte[53]` — disinfection setpoint slot

`byte[53]` holds the setpoint of whichever disinfection probe or mode is active:

| Active probe / mode | Meaning | Scaling | Seen |
|---|---|---|---|
| CLF | free chlorine target | ÷10 mg/L | `0x02` = 0.20 mg/L (NET, 2026-04-07 13:16:10) |
| REDOX | redox target | ×10 mV | |
| SANOSIL (OXY Pure) | OXY dose target | raw ml/m³/d | `0x08` = 8, later 12 (OXY) |
| DOSE | dosing rate | raw ml/m³/h | `0x05` = 5 (NET, 2026-04-07 13:15:00) |

SANOSIL and DOSE are different: SANOSIL is H₂O₂ as the primary disinfection with its probe in the CLF slot (ml/m³/d); DOSE is timed volume dosing replacing probe control (ml/m³/h), and sets the CLF-absent bit in `byte[4]`.

### Flow rate versus dose target

`byte[101]` (10 ml/min) is the flocculant pump's hardware flow rate; the app's "flocculant 10 ml/h" is the dosing setpoint in `byte[54]`. All OXY flow rate bytes are ml/min.

### Parallel pumps

On 2026-04-12 11:37:58 `byte[29]` = `0xa8` = `0x08 | 0x20 | 0x80`: filtration, flocculant and pH− running together, matching the app timeline (pH− 1 min 24 s with an overlapping 2 s floc pulse).

### Third pump routing

On SALT, `byte[37]` routes the third pump slot to algicide or flocculant. On OXY that routing does not apply: `algaecide_flow_rate` (`byte[103]`), `flocculant_flow_rate` (`byte[101]`) and both dose targets are read from their own bytes.

### Filtration period 2 (Issue #133)

Like SALT (PR #122 frame diff) and HOME (Issue #133), the unit is assumed to keep sending the last-configured period 2 times in bytes 60–63 after period 2 is disabled; OXY shares the SALT/HOME schedule layout and no reason is known for its firmware to clear them. `0xFF` there means never configured. Whether a period is active is reported by `filtration_schedule` from the `byte[37]` schedule bits.

### Water level

No level sensor on the captured unit (`byte[27]` = `0xFE`, `byte[37]` `0x40` clear). The level features are read with the HOME/SALT positions but have no OXY evidence; `water_level_high_alarm`, `water_level_low_alarm` and `water_level_refill_stop` have none recorded at all.

## 6. Ground truth

| Date | Field | Decoded | Unit / app | Result |
|---|---|---|---|---|
| 2026-04-02 | `oxygen_dose_target` (`byte[53]`) | 8 ml/m³/d | Aseko Live app history: 8 ml/m³/d until changed to 12 on 2026-04-06 11:36:33; 12 afterwards | match |
| 2026-04-02 | `flocculant_pump_running` (`byte[29]` `0x20`) | on at 19:33:52 | app: flocculant dosing event | match |
| 2026-04-02 | `flocculant_flow_rate` (`byte[101]`) | 10 ml/min | app history: pulses every ~20 min, 2 s each, over 24 h = 144 s, 0.02 L = 20 ml → ≈ 8.3 ml/min | consistent |
| 2026-04-11 | `flocculant_dose_target` (`byte[54]`) | 10 ml/h | app: 10 ml/h | match |
| 2026-04-11 | `algaecide_dose_target` (`byte[72]`) | 15 ml/m³/d | app: 15 ml/m³/d | match |
| 2026-04-11 | `algaecide_pump_running` (`byte[29]` `0x10`) | toggles | app: algicide pump on/off | match |
| 2026-04-11 | `oxygen_pump_running` (`byte[29]` `0x40`) | toggles | app: OXY Pure pump on/off | match |
| 2026-04-12 | `ph_minus_pump_running` (`byte[29]` `0x80`) | on | app: pH− pump on | match |
| 2026-04-12 | parallel pumps (`byte[29]` = `0xa8`) | floc + pH− at 11:37:58 | app timeline: pH− 1 min 24 s overlapping floc 2 s | match |

## 7. Settings the frame does not carry

- **Air temperature:** the Aseko Live app shows it on Oxygen units, but bytes 23–24 are `0xFE70` in every captured OXY frame.
- **Heating control** (`heating_control_enabled`): not located — described in the ASIN AQUA Oxygen manual, no OXY frame compared with it.
- **Freeze protection** (`freeze_protection_enabled`): not located — described in the manual, no OXY frame compared with it.

## 8. Open questions

1. **OXY with an optional CLF or REDOX probe** — does it exist, and what do `byte[4]` and bytes 16–21 look like? A frame from such a unit would settle it.
2. **Heating control and freeze protection** — a diagnostics dump before and after toggling each on the unit.
3. **Air temperature** — a dump from an Oxygen unit whose app shows air temperature.
4. **Alarms in bytes 12–13** — a dump while the unit shows an alarm or dosing warning.
5. **Actuator bits `0x01` / `0x02` / `0x04`** (backwash, refill, heating) — frames while each runs.
6. **Filtration schedule bits** — a frame after switching from nonstop to period 1 / period 2, and after disabling period 2 (bytes 60–63).
7. **`byte[54]` / `byte[72]`** read `0x01` in the 2026-04-02 frame but 10 / 15 on 2026-04-11 — were the setpoints changed in between? An app history check for that week.
8. **`byte[97]` pH+ flow rate** — a frame from a unit with a pH+ pump.
9. **Water level on OXY** — a frame from an Oxygen unit with a level sensor (thresholds versus the algicide flow rate at `byte[103]`).
10. **Unknown bytes** `byte[38]` = `0x08`, `byte[73]` = `0x28`, `byte[78]` `0x20` / `0x80` — dumps before and after changing settings.
11. **Observed values** (pH, water temperature, targets, schedule, backwash, delays, pool volume, max pH doses) — a glance at the unit or app next to the entities.

## 9. History

- **2026-09 — profiles:** the decoder was split into device profiles; the OXY profile replaced the `_fill_*` methods, `ACTUATOR_MASKS` and `FILTRATION_TYPES` of the old decoder. `byte[37]` was re-read with the SALT settings bits; the earlier guess that `0x03` meant two pump-module presence bits is superseded. The old HOME "firmware A / B" split turned out to be the waterlevel bit (see [`home_device_analysis.md`](home_device_analysis.md) §"One HOME, not two firmwares").
- **Startup delay label:** the profile notes that an earlier version of this document mislabelled `byte[73]`; the startup delay is bytes 74–75.
- **Frame counts:** the 2026-04-02 analysis spoke both of "7 captured frames" (sentinel slots invariant) and of "100+ captured OXY frames" (`byte[4]` unchanged).
- **Issue #133 implementation:** period 2 bytes were read unconditionally for every device in `FILTRATION_TYPES` (OXY included, NET excluded as it has no filtration output); `sensor.py` skipped creating the period 2 entities only while the bytes were `0xFF`.
- **v1.4.0 (branch `feat/pump-monitoring-consumption`, single branch):** unconfirmed pump masks defaulted to `0x00`. Changes:
  - `const.py`: `UNIT_TYPE_OXY = 0x05`.
  - `aseko_data.py`: `AsekoDeviceType.OXY = "ASIN AQUA Oxygen"`; OXY actuator masks filtration `0x08`, algicide `0x10`, flocculant `0x20`, oxy `0x40`, pH− `0x80`.
  - `aseko_decoder.py`: `_unit_type()` returned `None` instead of raising and matched `0x05`; `_configuration()` returned `{PH, OXY}` for OXY; CLF/REDOX fill skipped for OXY; OXY paths for dose targets (`byte[54]`, `byte[72]`) and flow rates (`byte[99]`, `byte[101]`, `byte[103]`). A dedicated `required_sanosil` field for `byte[53]` was planned instead of reusing `free_chlorine_target`.
  - Tests: normal, floc (`0x28`) and pH− (`0x88`) frames; algicide (`0x18`) and OXY (`0x48`) frame tests were still to do.
- **Why the pre-v1.4.0 decoder failed on OXY:** `0x05` matched none of the PROFI / SALT / HOME / NET checks, so `_unit_type()` raised `ValueError("Unknown unit type: 5")`. In `aseko_server.py` the frame was already forwarded to the cloud, but the exception closed the TCP connection, forcing a reconnect every ~10 s. The probe flags would also have added a CLF probe (bit `0x02` clear), and the REDOX fallback (`bytes[18:20] == 0xFFFF`) did not catch `0x001E`, so OXY would have shown REDOX 30 mV and CLF 0.30 mg/L.
- **Known misclassification at the time:** a NET in DOSE mode (`byte[4]` = `0x0b`) decoded as HOME because the HOME check matched first; flagged as a separate issue, out of scope for the OXY work. A per-serial "device type override" in the config entry was proposed as a future enhancement.

## 10. References

- Issues: #133 (period 2 bytes), #134 and #151 (HOME alarm encodings); PR #122 (SALT period 2 frame diff).
- Related analyses: [`home_device_analysis.md`](home_device_analysis.md), [`salt_device_analysis.md`](salt_device_analysis.md), [`net_device_analysis.md`](net_device_analysis.md).
- Profile: [`profiles/v7/oxy.py`](../../custom_components/aseko_local/decoding/profiles/v7/oxy.py); [support matrix](../support_matrix.md); [evidence rules](../evidence-rules.md).
- Tests: `tests/test_decode_v7.py` (OXY normal, flocculant and pH− frames).
