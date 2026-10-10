# ASIN AQUA Profi (v7) — Device Analysis

[Documentation](../README.md) / [Device analyses](README.md)

> **Status:** no real PROFI frame captured yet; everything except the serial number is assumed from the Aseko Profi manuals, the other v7 models and a synthetic test fixture.
> **Profile:** [`profiles/v7/profi.py`](../../custom_components/aseko_local/decoding/profiles/v7/profi.py) · **Support:** [support matrix](../support_matrix.md)
> **Evidence words** (`confirmed`, `confirmed on X`, `observed`, `assumed`, `not located`): see [evidence rules](../evidence-rules.md).

## 1. Device

PROFI is the largest ASIN AQUA pool controller. Per the Aseko Profi manuals it has:

- **Probe inputs** for pH, CLF (free chlorine) **and** REDOX, which can be installed at the same time.
- **Dosing outputs** documented in the manual: chlorine (ml/m³/h, or OXY Pure), pH−, pH+, algicide (ml/m³/day) and flocculant (ml/h). The older analysis treated these as five independent pump ports; the profile follows the Aseko Live app and the manuals' setpoints, where flocculant and algicide share one output (see §5).
- **Water-level input** (capacitive probe) and a **refill valve** output, same function as HOME/SALT/OXY. The hardware was confirmed in the PR #120 review against the manual; the byte positions are not.
- **Heating relay output** (heat pump or electric heater demand).
- **Backwash valve**.
- A **max. filling time** setting (2021 PROFI manual).

**Identification on the wire:** v7 `byte[4]` = `0x10` (`UNIT_TYPE_PROFI` in `const.py`) → `AsekoDeviceType.PROFI`. The low bits of `byte[4]` are read as missing-probe bits (0x01 REDOX, 0x02 CLF) like SALT/NET, but without a DOSE bit (`decode_v7_without_dose`).

**Sources:** Aseko Profi manuals (hardware description, 2021 manual for the filling relay), the synthetic fixture `_make_profi_clf_redox_bytes` in `tests/test_sensor.py`, and PR #120. No units or real frames.

## 2. Frame structure

Assumed to be the common v7 layout: 120 bytes, three 40-byte segments.

| Segment | Type byte | Content |
|---|---|---|
| 0–39 | `0x01` | Live sensor data |
| 40–79 | `0x03` | Setpoints and schedule |
| 80–119 | `0x02` | Parameters and flow rates |

No representative frame exists. The test fixture (CLF + REDOX, synthetic) sets `byte[4]` = `0x10`, `byte[29]` = `0x08`, `byte[37]` = `0x00` (flocculant routing), `byte[101]` = 60, bytes 76-77 = 3600 s and all water-level bytes = `0xFF`.

## 3. Byte map

### Bytes 0–39 — live data

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| 0–3 | `serial_number` | big-endian | derived | Repeated in every segment header — the v7 layout every unit shares; no PROFI frame captured |
| 4 | unit type / `configuration` | `0x10`; missing-probe bits, no DOSE bit | assumed | See §4 |
| 5 | segment type | `0x01` | assumed | |
| 6–11 | `timestamp` | year offset 2000 | assumed | |
| 12 | dosing warnings | bitmask | assumed | See §4 |
| 13 | alarms | bitmask | assumed | See §4 |
| 14–15 | `ph` | / 100, with a pH probe | assumed | |
| 16–17 | `free_chlorine` | / 100, with a CLF probe | assumed | |
| 18–19 | `redox` | mV; bytes 16-17 when 18-19 are `0xFFFF` | assumed | PROFI can carry CLF and REDOX together |
| 20–21 | `free_chlorine_mv` | big-endian mV, with a CLF probe | assumed | |
| 25–26 | `water_temperature` | / 10 | assumed | |
| 27 | `water_level` | cm; `0xFE` = sensor disconnected | assumed | |
| 28 | `water_flow_to_probes` | `0xAA` = flowing | assumed | |
| 29 | actuators | bitmask | assumed | See §4 |
| 37 | settings / routing | bitmask | assumed | See §4 |

### Bytes 40–79 — setpoints and schedule

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| 52 | `ph_target` | / 10 | assumed | |
| 53 | `free_chlorine_target` / `chlorine_dose_target` | / 10 with CLF | assumed | the DOSE reading of `chlorine_dose_target` is not reachable today: the PROFI configuration has no DOSE bit (`decode_v7_without_dose`); `redox_target` is not read on PROFI (see §5) |
| 54 | `flocculant_dose_target` | only while `byte[37]` routes the shared output to flocculant | assumed | unit unresolved: the manual's setpoints read ml/24 h m³, its dosing outputs ml/h — see §8 |
| 55 | `water_temperature_target` | °C | assumed | |
| 56–57 | `filtration_period_1_start` | HH:MM | assumed | |
| 58–59 | `filtration_period_1_end` | HH:MM | assumed | |
| 60–61 | `filtration_period_2_start` | HH:MM, read unconditionally | assumed | See §5 (Issue #133) |
| 62–63 | `filtration_period_2_end` | HH:MM, read unconditionally | assumed | See §5 (Issue #133) |
| 68 | `backwash_interval` | days, `0` = disabled | assumed | |
| 69–70 | `backwash_start_time` | HH:MM | assumed | |
| 71 | `backwash_duration` | × 10 s | assumed | |
| 72 | algicide dose (other models) | — | not located | Not read on PROFI; see §8 |
| 74–75 | `startup_delay` | s | assumed | |
| 76–77 | `max_refill_time` | s, `0xFFFF` = not implemented | assumed | 2021 manual lists a max. filling time |

### Bytes 80–119 — parameters and flow rates

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| 92–93 | `pool_volume` | m³ | assumed | |
| 95 | `ph_minus_flow_rate` | raw | assumed | |
| 97 | pH+ flow rate | — | not located | Old hypothesis; `ph_plus_*` is not mapped on any protocol |
| 99 | `chlorine_flow_rate` | raw | assumed | |
| 101 | `flocculant_flow_rate` | only while `byte[37]` routes the shared output to flocculant | assumed | |
| 102 | `water_level_low_alarm` | cm | assumed | |
| 103 | `water_level_refill_start` | cm | assumed | |
| 104 | `water_level_refill_stop` | cm | assumed | |
| 105 | `water_level_high_alarm` | cm | assumed | |
| 106–107 | `dosing_delay` | s | assumed | |
| 112 | `ph_minus_concentration` | raw | assumed | |
| 115 | `max_ph_doses` | `0xFF` = not set | assumed | |

## 4. Bit fields

### `byte[4]` — unit type and probes

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| value `0x10` | PROFI unit type | assumed | Only fixed identifier; was marked "Uncertain" in the old decoder |
| `0x01` | REDOX probe missing | assumed | Same convention as SALT/NET, not validated on a real frame |
| `0x02` | CLF probe missing | assumed | |
| `0x04` | DOSE missing | — | Not read on PROFI (`decode_v7_without_dose`) |

### `byte[12]` — dosing warnings

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x20` | `alarm_max_disinfection_dose` | assumed | Confirmed on HOME (Issue #134) |
| `0x40` | `alarm_ph_dosing_ineffective` | assumed | Confirmed on HOME (Issue #134) |

Not the backwash flag.

### `byte[13]` — alarms

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x01` | `alarm_max_disinfection_dose` | assumed | |
| `0x02` | `alarm_ph_dosing_ineffective` | assumed | |
| `0x04` | `alarm_no_flow_to_probes` | assumed | Confirmed on NET |
| `0x08` | `alarm_rapid_ph_change` | assumed | |

### `byte[29]` — actuators

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x01` | `backwash_running` | assumed | Confirmed on SALT |
| `0x02` | `refilling` | assumed | Confirmed on HOME and SALT |
| `0x04` | `heating_running` | assumed | Same bit as HOME/SALT/OXY |
| `0x08` | `filtration_relay` (→ `filtration_running`) | assumed | |
| `0x20` | `flocculant_pump_running` | assumed | Only while a flocculant flow rate is configured |
| `0x40` | `chlorine_pump_running` | assumed | Port may be chlorine or OXY Pure |
| `0x80` | `ph_minus_pump_running` | assumed | |
| — | algicide pump, pH+ pump | not located | Not listed in the profile |

### `byte[37]` — settings and routing

| Bit / mask | Meaning | Evidence | Notes |
|---|---|---|---|
| `0x04` | `service_menu_open` | assumed | |
| `0x10` / `0x20` | `filtration_schedule` | assumed | Since Issue #133 |
| `0x80` | shared output routed to algicide (clear = flocculant) | assumed | Same as SALT; PROFI reads only the flocculant side |

## 5. Model-specific behaviour

### Shared flocculant / algicide output

The profile follows the Aseko Live app and the PROFI manuals: the setpoints show a flocculant dose (ml/24 h m³) on a shared flocculant / algicide output. `flocculant_dose_target` (`byte[54]`) and `flocculant_flow_rate` (`byte[101]`) use `decode_v7_routed_by_byte37`, as on SALT. The profile lists **no** algicide values.

### Disinfection setpoint

`byte[53]` is read as free chlorine target (CLF). The chlorine dose target reading needs a DOSE configuration, which the PROFI profile does not have, so it is never reached. `redox_target` is not in the profile: the old decoder skipped it on PROFI because the REDOX setpoint was believed to use a different scaling (raw mV, not × 10). Neither scaling is verified.

### Filtration period 2 (Issue #133)

Like SALT (PR #122 frame diff) and HOME (Issue #133 diagnostics), PROFI is assumed to keep sending the last-configured period 2 times in bytes 60-63 after period 2 is disabled on the controller. Reasons: the manual describes the same filtration schedule, and there is no reason the firmware would clear the bytes. The bytes are read unconditionally; while they are `0xFF` (never configured) the value is not present, so the entity stays disabled or unavailable rather than showing a time. `filtration_schedule` (from `byte[37]`) reports when the second period is inactive. See [`home_device_analysis.md`](home_device_analysis.md) for the proof on HOME.

### Water level and refill

PROFI has the water-level input and refill valve (PR #120 review, manual), so the water-level values are decoded with the HOME/SALT/OXY bytes 27 and 102-105 plus `byte[29]` `0x02`. NET stays excluded because its bytes 102-104 carry unrelated data (`0x01`, `0x03`, `0x83`; see [`net_device_analysis.md`](net_device_analysis.md)).

### Backwash

Backwash settings use bytes 68-71; the relay is `byte[29]` `0x01` (`backwash_running`), which [`trackers/backwash.py`](../../custom_components/aseko_local/trackers/backwash.py) watches. `last_backwash` and `next_scheduled_backwash` are derived by the `BackwashTracker` across coordinator updates, not read from the frame.

## 6. Ground truth

Nothing known yet.

## 7. Settings the frame does not carry

Nothing known yet.

## 8. Open questions

All need a real PROFI frame. A useful capture set: all pumps off, filtration only, each pump alone (pH−, chlorine, flocculant, algicide), refill valve open, heat pump running, backwash active; each compared with the Aseko Live app.

1. Are the `byte[4]` missing-probe bits (CLF, REDOX) the SALT convention? — any real frame with a known probe set.
2. `byte[29]` masks for each pump. — frames with each pump running alone.
3. Algicide and flocculant setpoints: is the shared output routed by `byte[37]` `0x80`, or are there independent bytes (`byte[54]` and `byte[72]` as on OXY/HOME)? — a frame with both algicide and flocculant configured.
4. Algicide and flocculant flow rates: shared `byte[101]` or two separate bytes? — a frame showing two non-zero flow rates.
5. REDOX setpoint scaling on `byte[53]`: raw mV or something else? — a REDOX frame compared with the app.
6. pH+ pump: setpoint, flow rate (`byte[97]`?) and running bit. — a frame with the pH+ pump running.
7. Water-level bytes 27 and 102-105. — a frame with a non-`0xFF` level, thresholds compared with the app.
8. Heating relay `byte[29]` `0x04`. — a frame while the heat pump runs.
9. Backwash bytes 68-71 and `byte[29]` `0x01`. — a frame while backwash is active.
10. **Flocculant dose unit** — the PROFI manual gives ml/24 h m³ for the flocculant setpoint and ml/h for the flocculant output; a frame with a known setpoint on a real PROFI would settle what `byte[54]` carries.

## 9. History

- **Profile split:** the decoder was split into device profiles; `profiles/v7/profi.py` replaced the `_fill_*` methods, `ACTUATOR_MASKS` and `FILTRATION_TYPES` of `aseko_decoder.py`. The profile now lists `flocculant_dose_target` and `max_refill_time` from the manuals.
- **Older claim, superseded:** the old decoder set `byte37_routes_pump_type = False` ("5 independent pump ports", marked certain), yet `_fill_flowrate_data` still read `byte[101]` as the SALT-style shared slot, giving the flocculant flow rate right "by accident" with the fixture's `byte[37]` = `0x00`. The plan was a PROFI-only branch once positions were known; the profile instead routes flocculant by `byte[37]` `0x80`.
- **Older claim, superseded:** `_fill_required_data` did not assign `algaecide_dose_target` or `flocculant_dose_target` on PROFI, and `test_async_setup_profi_clf_redox` asserted `flocculant_dose_target` was absent. The profile and test now include it.
- **Old actuator masks:** `filtration=0x08`, `cl=0x40`, `ph_minus=0x80`, `flocculant=0x20` were placeholders copied from HOME/SALT/OXY; algicide, pH+, OXY and electrolyser masks were `0x00`, so their binary sensors registered but always read off. Heating and refilling bits were called "partially confirmed"; the profile marks them assumed.
- **Identification:** the old decoder matched `data[4] == UNIT_TYPE_PROFI` with an "Uncertain" comment and fell through to the generic `probe_info = data[4]` path with the SALT-style REDOX/CLF/DOSE missing bits.
- **PR #120** (commit `34957ea`): `_fill_home_water_level_data` changed from a `{HOME, SALT, OXY}` whitelist to a NET-only blacklist, so PROFI got water-level values and a `refilling` binary sensor; the PROFI test count went from 34 to 35 entities.
- **Issue #133:** bytes 60-63 read unconditionally for every model with filtration (SALT, HOME, OXY, PROFI).
- The water-level byte positions were first documented in `docs/temp/water_level_backwash_analysis.md`, no longer in the repository.

## 10. References

- Profile: [`profiles/v7/profi.py`](../../custom_components/aseko_local/decoding/profiles/v7/profi.py); feature files in [`decoding/features/`](../../custom_components/aseko_local/decoding/features/)
- Unit type constant: `custom_components/aseko_local/const.py` → `UNIT_TYPE_PROFI = 0x10`
- Tests: `tests/test_sensor.py` (`_make_profi_clf_redox_bytes`, `test_async_setup_profi_clf_redox`), `tests/test_decode_v7.py` (`test_decode_profi`)
- PR #120 (water level on PROFI), PR #122 (SALT period 2 frame diff), Issue #133 (period 2 bytes), Issue #134 (HOME dosing warnings)
- Sibling analyses: [`home_device_analysis.md`](home_device_analysis.md), [`salt_device_analysis.md`](salt_device_analysis.md), [`net_device_analysis.md`](net_device_analysis.md), [`oxy_device_analysis.md`](oxy_device_analysis.md)
- [Support matrix](../support_matrix.md), [evidence rules](../evidence-rules.md)
