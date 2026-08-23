# ASIN AQUA Home — Device Analysis

**Model**: ASIN AQUA HOME (CLF variant)
**Serial**: 110128063 (`0x06906bbf`)
**Device type byte**: `0x02` → `UNIT_TYPE_HOME_CLF`
**Source frame timestamp**: 2026-04-28 08:27:07
**Ground truth**: Aseko Live app screenshots (Status, Consumption, Config pages)

---

## Firmware Revisions

Two HOME v7 firmware revisions are observed in the wild. They use **different
byte 37 layouts** for the filtration mode flag but share every other byte
position. The two revisions are referred to throughout this document as
**Firmware A** and **Firmware B**:

| | Firmware A | Firmware B |
|---|---|---|
| Serial (known) | 110128063 (`0x06906bbf`) | 110169464 (`0x06912578`) |
| | 110175608* (`0x06912578`, REDOX) | |
| `byte[37]` mode values | high nibble `0x4` / `0x5` | high nibble `0x0` / `0x1` / `0x3` |
| Known states | nonstop 24h, timer, transitional, | nonstop 24h, P1, P1&P2, each ± manual override, transitional |
| | heating ON, heating OFF, unconfigured | |
| Source | This file (Issue #110, #135) | [Issue #133](../temp/Issue-133.md) |
| Period 2 enable flag | bit 5 (`0x20`) — same as firmware B | bit 5 (`0x20`) |
| Manual OFF signal | not present in captured frames | bit 2 (`0x04`) — see `byte[37]` table |
| Heating control flag | bit 3 (`0x08`) — master enable | (n/o) |
| Antifreeze flag | bit 7 (`0x80`) — master enable (Issue #136) | (n/o) |

\* Serial 110175608 (`byte[4]` = `0x03`, REDOX HOME) is the source of the heating-control findings ([Issue #135](https://github.com/hopkins-tk/home-assistant-aseko-local/issues/135)).

The two revisions are **disjoint by high nibble of byte 37**, so a single
byte check distinguishes them without resorting to the serial number.
Where a fact in this document differs between the two revisions (only
`byte[37]` today), both values are listed side by side in the
*byte[37] — Filtration mode flag* table under "Device Specifications"
below. All other byte positions are identical across A and B.

---

## Raw Frame (120 bytes)

The Aseko protocol sends 3×40-byte segments in a single TCP payload.
Each segment header: `[0-3]` serial (big-endian), `[4]` device type, `[5]` segment marker (`0x01 / 0x03 / 0x02`), `[6-11]` timestamp.

```
Seg1 (bytes   0–39): 06 90 6b bf  02 01  1a 04 1c 08 1b 07
                     00 28 02 75 00 00 00 00 00 02 90 fe 70 01 7b 08 00 00 ff ff 00 00 00 00 00 43 0a 85

Seg2 (bytes  40–79): 06 90 6b bf  02 03  1a 04 1c 08 1b 07
                     46 03 0a 19 08 00 10 00 12 00 16 00 02 7c 01 7b 03 15 00 0c 00 28 01 e0 2a 30 a0 d8

Seg3 (bytes 80–119): 06 90 6b bf  02 02  1a 04 1c 08 1b 07
                     00 3c 00 3c 00 3c 00 3c 00 0a 0d 21 37 64 00 f0 14 02 58 0f 0f 0f 1e 14 ff bc 02 71
```

---

## Byte-by-Byte Analysis

### Segment 1 (bytes 0–39) — real-time sensor data

| Byte(s) | Hex      | Decimal | Field                    | Decoded value        | App value     | Status |
|---------|----------|---------|--------------------------|----------------------|---------------|--------|
| 0–3     | `06906bbf` | —     | Serial number (big-endian) | 110,128,063         | —             | ✓      |
| 4       | `02`     | 2       | Device type              | HOME (CLF variant)   | —             | ✓      |
| 5       | `01`     | 1       | Segment marker           | Segment 1            | —             | ✓      |
| 6–11    | `1a 04 1c 08 1b 07` | — | Timestamp           | 2026-04-28 08:27:07  | —             | ✓      |
| 12      | `00`     | 0       | **Dosing-warning bitmask** (`0x20`=disinfection, `0x40`=pH) | none           | —             | ✓ (Issue #134/#151) |
| 13      | `28`     | 40      | **Alarm bitmask** (`0x01`=disinfection, `0x02`=pH, `0x04`=no flow, `0x08`=rapid pH) | low nibble `0x08` set → rapid-pH flag (unconfirmed) | — | ✓ (Issue #151) |
| 14–15   | `0275`   | 629     | pH (÷100)                | **6.29**             | 6.56†         | ✓†     |
| 16–17   | `0000`   | 0       | Cl free (÷100)           | **0.00 mg/l**        | 0.00 mg/l     | ✓      |
| 18–19   | `0000`   | 0       | Unused (no REDOX probe)  | —                    | —             | —      |
| 20–21   | `0002`   | 2       | Cl free mV (big-endian)  | **2 mV**             | —             | ✓      |
| 22–23   | `90fe`   | 37118   | Unknown / VSP pump (see ¶) | —                 | —             | ¶      |
| 24      | `70`     | 112     | Unknown                  | —                    | —             | ?      |
| 25–26   | `017b`   | 379     | Water temp (÷10)         | **37.9°C**           | 38.2°C†       | ✓†     |
| 27      | `08`     | 8       | **Water level (cm)**     | **8 cm**             | (level meter disabled on this device) | ✓     |
| 28      | `00`     | 0       | Water flow to probes     | **False** (≠ 0xAA)   | NO            | ✓      |
| 29      | `00`     | 0       | Actuator bits            | all pumps stopped    | STOP          | ✓      |
| 30–31   | `ffff`   | —       | UNSPECIFIED / padding    | —                    | —             | —      |
| 32–36   | `00…00`  | 0       | Unknown                  | —                    | —             | ?      |
| 37      | `43`     | 67      | **Filtration mode flag (firmware A)** | see note §  | NONSTOP 24H    | ✓     |
| 38      | `0a`     | 10      | Unknown                  | —                    | —             | ?      |
| 39      | `85`     | 133     | Unknown (checksum?)      | —                    | —             | ?      |

† pH 6.29 vs 6.56 and water temp 37.9 vs 38.2 are explained by different timestamps (frame: 08:27:07, screenshot: later that day). Not a decoding bug.

§ **byte[37] = `0x43`**: HOME filtration mode flag, firmware A. The value `0x43` means *FILTRATION NONSTOP 24H* here. HOME devices have **independent pump ports** for flocculant and algicide (same layout as OXY Pure), so the SALT-style "shared third-pump port" routing rule (bit 7 = algicide) does **not** apply. The full encoding table (firmware A vs B) is in the *Device Specifications → byte[37]* section below.

¶ **byte[22] bit 3 (0x08)**: On devices with a variable-speed filtration pump (serial 110175608 REDOX HOME, Issue #137), `0x83` → pump OFF, `0x8b` → pump ON (any brand). Decoded as `vsp_pump_running` — see *Variable-speed pump* section below. On this CLF frame (no VSP fitted) the byte carries an unknown value (`0x90fe`).

---

### Segment 2 (bytes 40–79) — setpoints and schedule

| Byte(s) | Hex      | Decimal | Field                         | Decoded value  | App value         | Status |
|---------|----------|---------|-------------------------------|----------------|-------------------|--------|
| 40–43   | `06906bbf` | —     | Serial (repeated)             | 110,128,063    | —                 | ✓      |
| 44      | `02`     | 2       | Device type (repeated)        | HOME           | —                 | ✓      |
| 45      | `03`     | 3       | Segment marker                | Segment 2      | —                 | ✓      |
| 46–51   | `1a 04 1c 08 1b 07` | — | Timestamp (repeated)       | 2026-04-28 08:27:07 | —            | ✓      |
| 52      | `46`     | 70      | required_ph (÷10)             | **7.0**        | 7.0               | ✓      |
| 53      | `03`     | 3       | required_cl_free (÷10)        | **0.3 mg/l**   | 0.3               | ✓      |
| 54      | `0a`     | 10      | required_floc                 | **10 ml/h**    | 10 ml/h           | ✓      |
| 55      | `19`     | 25      | required_water_temperature    | 25°C           | — (disabled)      | ⚠ Open Item 3 |
| 56–57   | `08 00`  | —       | start1                        | 08:00          | last-configured   | ✓     |
| 58–59   | `10 00`  | —       | stop1                         | 16:00          | last-configured   | ✓     |
| 60–61   | `12 00`  | —       | start2                        | 18:00          | last-configured   | ✓     |
| 62–63   | `16 00`  | —       | stop2                         | 22:00          | last-configured   | ✓     |
| 64–65   | `027c`   | 636     | Unknown                       | —              | —                 | ?      |
| 66–67   | `017b`   | 379     | Unknown (= water temp raw)    | —              | —                 | ?      |
| 68      | `03`     | 3       | backwash_every_n_days         | **3 days**     | every 3 days      | ✓      |
| 69–70   | `15 00`  | —       | backwash_time                 | **21:00**      | starts at 21:00   | ✓      |
| 71      | `0c`     | 12      | backwash_duration (×10 s)     | **120 s = 2 min** | takes 02:00 min | ✓    |
| 72      | `00`     | 0       | required_algicide             | **0 ml/m³/day** | 0 ml/m³/day     | ✓      |
| 73      | `28`     | 40      | Unknown                       | —              | —                 | ?      |
| 74–75   | `01e0`   | 480     | delay_after_startup (s)       | **480 s = 8 min** | 8 min          | ✓      |
| 76      | `2a`     | 42      | Unknown                       | —              | —                 | ?      |
| 77      | `30`     | 48      | Unknown                       | —              | —                 | ?      |
| 78      | `a0`     | 160     | Unknown                       | —              | —                 | ?      |
| 79      | `d8`     | 216     | Unknown                       | —              | —                 | ?      |

> **Schedule vs. mode flag**: bytes 56-63 always carry the last-configured
> schedule (the unit does not clear them when switching to NONSTOP 24h). The
> actual mode is reported separately in `byte[37]`. See the *byte[37]
> — Filtration mode flag* section under "Device Specifications" below for the
> two encodings.

---

### Segment 3 (bytes 80–119) — pool parameters and flowrates

| Byte(s) | Hex      | Decimal | Field                        | Decoded value  | App value         | Status |
|---------|----------|---------|------------------------------|----------------|-------------------|--------|
| 80–83   | `06906bbf` | —     | Serial (repeated)            | 110,128,063    | —                 | ✓      |
| 84      | `02`     | 2       | Device type (repeated)       | HOME           | —                 | ✓      |
| 85      | `02`     | 2       | Segment marker               | Segment 3      | —                 | ✓      |
| 86–91   | `1a 04 1c 08 1b 07` | — | Timestamp (repeated)      | 2026-04-28 08:27:07 | —            | ✓      |
| 92–93   | `003c`   | 60      | pool_volume (big-endian)     | **60 m³**      | 60 m³             | ✓      |
| 94–95   | `003c`   | 60      | max_filling_time (big-endian) | **60 min**    | —                 | ✓      |
| 96      | `00`     | 0       | Unknown                      | —              | —                 | ?      |
| 97      | `3c`     | 60      | flowrate_ph_plus? (unconf.)  | —              | —                 | ?      |
| 98      | `00`     | 0       | Unknown                      | —              | —                 | ?      |
| 99      | `3c`     | 60      | flowrate_chlor               | **60 ml/min**  | Chlor Pure listed | ✓      |
| 100     | `00`     | 0       | Unknown                      | —              | —                 | ?      |
| 101     | `0a`     | 10      | **flowrate_floc**            | **10 ml/min**  | Floc+c listed     | ✓ (fixed) |
| 102     | `0d`     | 13      | **water_level_low_alarm (cm)** | **13 cm**    | Low alarm         | ✓ (Issue #110) |
| 103     | `21`     | 33      | **flowrate_algicide**        | **33 ml/min**  | Algicide listed   | ✓ (fixed) |
| 104     | `37`     | 55      | **water_level_filling_off (cm)** | **55 cm**  | Filling OFF       | ✓ (Issue #110) |
| 105     | `64`     | 100     | **water_level_high_alarm (cm)** | **100 cm**  | High alarm        | ✓ (Issue #110) |
| 106–107 | `00f0`   | 240     | delay_after_dose (s)         | **240 s = 4 min** | 4 min          | ✓      |
| 108     | `14`     | 20      | Unknown                      | —              | —                 | ?      |
| 109–110 | `0258`   | 600     | Unknown                      | —              | —                 | ?      |
| 111     | `0f`     | 15      | Unknown                      | —              | —                 | ?      |
| 112     | `0f`     | 15      | **ph_minus_concentration**   | **5%**         | **5%**           | ✓ (Issue #139) |
| 113     | `0f`     | 15      | Unknown                      | —              | —                 | ?      |
| 114     | `1e`     | 30      | Unknown                      | —              | —                 | ?      |
| 115     | `14`     | 20      | Unknown                      | —              | —                 | ?      |
| 116     | `ff`     | —       | UNSPECIFIED / padding        | —              | —                 | —      |
| 117     | `bc`     | 188     | Unknown                      | —              | —                 | ?      |
| 118–119 | `0271`   | 625     | Unknown (checksum?)          | —              | —                 | ?      |

Note on **bytes 94–95**: `max_filling_time` reads bytes[94:96] as a big-endian 16-bit value = `0x003c` = 60. `flowrate_ph_minus` independently reads byte[95] = `0x3c` = 60. They overlap but coincidentally produce the same result because the high byte (94) is 0x00. If byte[94] ever becomes non-zero the max_filling_time would be inflated; however for HOME this is expected to fit in one byte (max ~255 min).

---

## Dosing warnings & alarms (bytes 12 / 13)

HOME devices report dosing safety faults in two adjacent bytes. The decoder reads
them for **all** device types (`_fill_alarm_data` in `aseko_decoder.py`):

| Binary sensor | byte[12] bit | byte[13] bit |
|---|---|---|
| Too many doses of disinfection (`alarm_orp_too_many_doses`) | `0x20` | `0x01` |
| Too many doses of pH (`alarm_ph_too_many_doses`) | `0x40` | `0x02` |
| No flow to probes (`alarm_no_flow_to_probes`) | — | `0x04` |
| Rapid pH change (`alarm_rapid_ph_change`) | — | `0x08` (unconfirmed) |

Confirmed by @dtpugh's diagnostics on HOME serial 110175608 (byte[4] = `0x03`):

* **Issue #134** (2026-07-05), before/after clearing on the controller: both
  warnings active → byte[12] = `0x60`; pH only → `0x40`; cleared → `0x00`.
  byte[13] stayed `0x00`.
* **Issue #151** (2026-08-06/08): chlorine/disinfection "Maximum disinfection
  dose exceeded" → byte[13] = `0x01` (byte[12] = `0x00`); pH fault → byte[12] =
  `0x40`; cleared → both `0x00`.

The disinfection fault was observed in byte[12] `0x20` (July) **and** in byte[13]
`0x01` (August) — likely a firmware change on the Home. The decoder ORs both
paths so either encoding is detected. The byte[13] `0x02` = pH mapping is
**inferred** (symmetric to `0x01`; @dtpugh expected `0x02` for a pH fault) and
still lacks a direct frame capture. The same disinfection fault maps to `ins[12]`
bit `0x80` on v8 frames (Issue #151, `aseko_decoder_v8.py`), so both protocols
share the `alarm_orp_too_many_doses` sensor.

---

## Decoded Values vs Ground Truth Summary

| Field                     | Decoded          | Aseko Live        | Match |
|---------------------------|------------------|-------------------|-------|
| pH                        | 6.29             | 6.56              | ✓ (Δt)|
| Cl free                   | 0.00 mg/l        | 0.00 mg/l         | ✓     |
| Water temperature         | 37.9°C           | 38.2°C            | ✓ (Δt)|
| Water flow to probes      | False            | NO                | ✓     |
| Filtration pump running   | False            | STOP              | ✓     |
| filtration_schedule       | NONSTOP_24H      | NONSTOP 24H       | ✓ (Issue #110) |
| filtration_mode           | SCHEDULE         | (not in manual)   | ✓ |
| water_level               | 8 cm             | --- (level meter disabled) | ✓ (frame value) |
| water_level_low_alarm     | 13 cm            | (config)          | ✓ (Issue #110) |
| water_level_filling_on    | 33 cm            | (config)          | ✓ (Issue #110) |
| water_level_filling_off   | 55 cm            | (config)          | ✓ (Issue #110) |
| water_level_high_alarm    | 100 cm           | (config)          | ✓ (Issue #110) |
| water_filling_active      | False            | --- (valve not active) | ✓ (Issue #100) |
| required_ph               | 7.0              | 7.0               | ✓     |
| required_cl_free          | 0.3 mg/l         | 0.3               | ✓     |
| required_floc             | 10 ml/h          | 10 ml/h           | ✓ (fixed) |
| required_algicide         | 0 ml/m³/day      | 0 ml/m³/day       | ✓ (fixed) |
| required_water_temperature | 25°C            | --- (disabled)    | ⚠ Open Item 3 |
| Filtration times          | 08:00–16:00 / 18:00–22:00 (last-configured) | NONSTOP 24H | ✓ (schedule from `byte[37]`, time bytes always present) |
| backwash_every_n_days     | 3                | every 3 days      | ✓     |
| backwash_time             | 21:00            | starts at 21:00   | ✓     |
| backwash_duration         | 120 s            | 02:00 min         | ✓     |
| pool_volume               | 60 m³            | 60 m³             | ✓     |
| delay_after_startup       | 480 s (8 min)    | 8 min             | ✓     |
| delay_after_dose          | 240 s (4 min)    | 4 min             | ✓     |
| flowrate_ph_minus         | 60               | pH- listed        | ✓     |
| flowrate_chlor            | 60               | Chlor Pure listed | ✓     |
| flowrate_floc             | 10               | Floc+c listed     | ✓     |
| flowrate_algicide         | 33               | Algicide listed   | ✓ (fixed) |
| heating_control_enabled   | True / False     | — (app setting)   | ✓ (Issue #135, serial 110175608 REDOX HOME) |
| antifreeze_enabled        | True / False     | — (app setting)   | ✓ (Issue #136, serial 110175608 REDOX HOME) |
| vsp_pump_running          | True / False     | — (app setting)   | ✓ (Issue #137, serial 110175608 REDOX HOME) |
| ph_minus_concentration    | 5%               | 5%                | ✓ (Issue #139, serial 110175608 REDOX HOME) |

---

## Device Specifications

### Pump ports

HOME has **4 independent pump ports** (same layout as OXY Pure), unlike SALT
which has a shared third-pump port. There is no SALT-style algicide/flocculant
routing via `byte[37]` bit 7.

| Port  | Pump                | `flowrate_*` byte | `flowrate_*` value | `byte[29]` bit (uncertain) | `byte[29]` mask |
|-------|---------------------|-------------------|--------------------|-----------------------------|-----------------|
| 1     | pH− (Ph minus)      | `byte[95]`        | `flowrate_ph_minus`  | bit 7                       | `0x80`          |
| 2     | Chlorine / OXY Pure | `byte[99]`        | `flowrate_chlor`     | bit 6                       | `0x40`          |
| 3     | Flocculant          | `byte[101]`       | `flowrate_floc`      | bit 5                       | `0x20`          |
| 4     | Algicide            | `byte[103]`       | `flowrate_algicide`  | bit 4 (PROFI/SALT) / bit 5 (HOME, shared) | `0x20` |

> **Note on cl/oxy routing**: the chlorine pump port can be configured as
> Chlorine OR OXY Pure (same physical port, same bit in `byte[29]`). The
> routing byte is not yet confirmed from frames — see Open Item 7.

### Setpoints

| Field                   | Byte(s)   | Unit             | Notes |
|-------------------------|-----------|------------------|-------|
| `required_ph`           | `byte[52]`| (raw ÷ 10)        |       |
| `required_cl_free`      | `byte[53]`| mg/L (raw ÷ 10)   | HOME CLF variant only |
| `required_redox`        | `byte[53]`| mV (raw × 10)     | HOME REDOX variant only |
| `required_floc`         | `byte[54]`| ml/h              | Same byte position as SALT algicide; gated by `byte[37] != 0xFF` |
| `required_algicide`     | `byte[72]`| ml/m³/day         | HOME-only, same byte position as OXY Pure |
| `required_water_temperature` | `byte[55]` | °C            | Disabled on this device — see Open Item 3 |
| `ph_minus_concentration`     | `byte[112]`| %             | pH⁻ acid concentration (Issue #139). HOME-only — gated on device type. |

### Schedule (bytes 56-63)

| Field   | Byte(s)   | Decoded      | Notes |
|---------|-----------|--------------|-------|
| `start1` | `byte[56:58]` | HH:MM     | Gated on `FILTRATION_TYPES` (HOME in) |
| `stop1`  | `byte[58:60]` | HH:MM     | Gated on `FILTRATION_TYPES` |
| `start2` | `byte[60:62]` | HH:MM     | Gated on `FILTRATION_TYPES` only — see Issue #133 |
| `stop2`  | `byte[62:64]` | HH:MM     | Gated on `FILTRATION_TYPES` only — see Issue #133 |

### `byte[37]` — Filtration mode flag + heating control (two encodings observed)

> See the **Firmware Revisions** section at the top of this document for
> background on why two encodings exist. The two are **disjoint by high
> nibble** of `byte[37]` and therefore distinguishable on a single byte.
> Working notes for firmware B: [docs/temp/Issue-133.md](../temp/Issue-133.md).

HOME v7 firmware comes in two revisions that use **disjoint** byte 37 layouts.
Both revisions are confirmed live (firmware A: serial 110128063, byte 4 = 0x02;
firmware B: serial 110169464, byte 4 = 0x03 — see [Issue #133](../temp/Issue-133.md)).

| Mode                          | Firmware A | Firmware B | Binary (A / B)               |
|-------------------------------|------------|------------|------------------------------|
| 24h nonstop                   | `0x43`     | `0x01`     | `0100_0011` / `0000_0001`    |
| Timer (P1)                    | `0x53`*    | `0x11`     | `0101_0011` / `0001_0001`    |
| Timer (P1 & P2)               | `0x53`*    | `0x31`     | `0101_0011` / `0011_0001`    |
| OFF (manual)                  | (n/o)      | `0x35`     | — / `0011_0101`              |
| Transitional                  | `0x47` / `0x57` | (n/o) | `0100_0111` / `0101_0111` / — |
| Heating ON (nonstop)†         | `0x49`     | (n/o)      | `0100_1001` / —              |
| Heating OFF (nonstop)†        | `0x41`     | (n/o)      | `0100_0001` / —              |
| Heating OFF (initial/unconf.)† | `0x45`    | (n/o)      | `0100_0101` / —              |
| Antifreeze ON (nonstop)†‡     | `0x81`     | (n/o)      | `1000_0001` / —              |

† Bit 1 is clear (`0x02`) in all three heating-health values. When `byte[37]` & `0x40` is set
  but bit-1 is clear, the decoder falls back to a schedule derived from the
  filtration times (see `_fill_filtration_mode` in `aseko_decoder.py`), using
  the time bytes and the `PERIOD2_ENABLED_MASK` (`0x20`).
  `heating_control_enabled` is decoded separately from bit 3 (`0x08`).

  Both this fallback and the firmware-A branch above it are **HOME-only**.
  Bit `0x40` only discriminates the two encodings here: SALT sets it in every
  frame, and reports the filtration times unchanged in every mode, so for a
  SALT the fallback could only ever return one constant answer.

‡ When antifreeze is ON, `byte[55]` drops from the normal heating setpoint
  (eg. 27°C) to the antifreeze setpoint (e.g. 4°C, 5°C or 9°C whatever user sets).
  `antifreeze_enabled` is decoded from bit 7 (`0x80`), independent of
  `heating_control_enabled` (bit 3).

\* Firmware A cannot distinguish P1-only from P1&P2 from `byte[37]` alone — both
share the value `0x53`. The decoder uses the existing `FILTRATION_PERIOD2_ENABLED_MASK = 0x20`
(bit 5) to separate them, treating `0x53` as P1&P2 by default. The actual distinction
on firmware A comes from the per-period enable bit, not the mode flag.

(n/o = not observed in captured frames.)

**Firmware B bit semantics**:

| Bit  | Mask  | Meaning                                       |
|------|-------|-----------------------------------------------|
| 0    | `0x01`| Filtration present (always set)               |
| 2    | `0x04`| Manual override active (user toggled OFF)     |
| 4    | `0x10`| Period 1 enabled                              |
| 5    | `0x20`| Period 2 enabled                              |

Mode decoding on firmware B:
- **24h nonstop** ⇔ `(byte[37] & 0x30) == 0`
- **Timer mode** ⇔ `(byte[37] & 0x30) != 0`
- **Manual override** ⇔ `(byte[37] & 0x04) != 0`

**Firmware A bit semantics** (Issue #135, #136, serial 110175608 REDOX HOME):

| Bit | Mask  | Meaning                                                    |
|-----|-------|------------------------------------------------------------|
| 7   | `0x80`| Antifreeze master enable (Issue #136)                      |
| 6   | `0x40`| Firmware A high-nibble indicator (always set)              |
| 3   | `0x08`| Heating control master enable                              |
| 2   | `0x04`| Unknown / initial-unconfigured indicator (set on unconfigured `0x45`) |
| 1   | `0x02`| Transitional edit in progress (set on `0x47` / `0x57`)     |
| 0   | `0x01`| Filtration present (always set in known nonstop/timer)     |

Filtration mode decoding on firmware A:
- **Known modes**: `0x43` (nonstop), `0x53` (timer), `0x47`/`0x57` (transitional → `None`)
- **Heating overlay values** (`0x41`, `0x45`, `0x49`) have bit 1 clear — the decoder
  falls back to schedule-derived filtration mode for these.
- **Heating control**: bit 3 (`0x08`) is gated on `AsekoDeviceType.HOME` in
  `_fill_heating_demand()` and decoded into `heating_control_enabled`.
- **Antifreeze**: bit 7 (`0x80`) is decoded as `antifreeze_enabled` (Issue #136).
  When active, `byte[55]` holds the antifreeze setpoint (e.g. 4°C, 5°C, 9°C)
  instead of the normal heating setpoint.

**Note on `0x43` (firmware A)**: treat this as "consistent with NONSTOP 24H" rather
than "confirmed NONSTOP 24H active". A frame captured in May 2026 from
mannekung's device (after switching to NONSTOP 24H) still showed `0x53` (timer)
with the Aseko app in "Suche" (search) mode — see [Issue #110 frame
discussion](https://github.com/hopkins-tk/home-assistant-aseko-local/issues/110).

**Note on `0x35` (firmware B, manual OFF)**: when this value appears, `byte[29]`
bit 3 (`filtration_pump_running`) is still set in the frame — the firmware does
not clear the schedule-driven bit on manual override. The decoder compensates
by short-circuiting `filtration_pump_running` to `False` whenever
`filtration_mode == MANUAL`.

This override stays **HOME-only**, and SALT captures are now the reason why
rather than just a lack of evidence: on SALT the same bit means the user is
at the panel driving the pump, which they may equally have switched *on*.
Forcing the pump off there would invent a state the unit never reported.
See `salt_device_analysis.md` §byte[37] – filtration mode and schedule.

**Note on Period 2 schedule bytes (Issue #133)**: All Aseko devices in
`FILTRATION_TYPES` (SALT, HOME, OXY, PROFI) keep sending the last-configured
`start2`/`stop2` times in bytes 60-63 even after the user disables Period 2
in the controller UI. The controller never clears these bytes — they are
treated as the device's "last-known schedule" and the active/inactive
state is carried separately in `byte[37]` bit 5 (`0x20`) for HOME firmware
A/B and SALT/OXY, or in the schedule-byte presence for byte[37] = 0xFF.
Pre-fix, the decoder used `byte[37]` bit 0x20 to gate `start2`/`stop2` on
None for any device where the enable flag was clear, which caused
already-registered entities to flip to "unknown" when the user toggled
the controller back from "P1 & P2" to "P1 only" (the entity registry
protects the entity, but the value is read as `None`).  Post-fix, bytes
60-63 are read unconditionally for any device in `FILTRATION_TYPES` (so
`start2`/`stop2` stay populated and the entity shows the last-configured
time); the `filtration_schedule` sensor separately reports `TIMER_PERIOD_1`
to tell the user that Period 2 is inactive.  This behaviour was
verified against the four diagnostic files from
[Issue #133](../temp/Issue-133.md) (serial 110169464, ASIN AQUA Home
firmware B): bytes 60-63 stay populated in all four modes (24h nonstop,
P1 only, P1 & P2, OFF manual).  The decoder applies the same logic to
SALT/OXY/PROFI for two reasons:

1.  SALT and OXY share the same protocol layout for bytes 60-63, and
    `byte[37]` bit 0x20 is the documented enable flag on those devices.
    There is no protocol-level reason to believe they clear the bytes
    when Period 2 is disabled.
2.  PROFI has the same byte layout but no live frame has been captured
    that toggles Period 2 on/off; the same fix prevents a potential
    regression if a user reports the same "unknown entity" symptom on
    PROFI later.

NET is excluded because it has no filtration output at all and is
not in `FILTRATION_TYPES`.

### `byte[29]` — Actuator bitmask (HOME)

Bit positions in `byte[29]` for HOME pump states. The masks in
`ACTUATOR_MASKS[HOME]` are placeholders — they match OXY/NET but the per-pump
bits for HOME-specific pumps (algicide, flocculant) are **not yet confirmed**
by live capture (see Open Item 7).

| Bit  | Mask  | Field                       | Confidence |
|------|-------|-----------------------------|------------|
| 0    | `0x01`| backwash valve relay        | ✓ confirmed (HOME/SALT/OXY all use this bit) |
| 1    | `0x02`| water-filling active        | ✓ confirmed (NET/NOT-HOME, see Issue #100)    |
| 2    | `0x04`| heating active              | ⚠ unconfirmed — see Open Item 9                |
| 3    | `0x08`| filtration pump running     | ✓ confirmed (all FILTRATION_TYPES)            |
| 4    | `0x10`| algicide pump running       | see Open Item 7        |
| 5    | `0x20`| flocculant pump running     | see Open Item 7        |
| 6    | `0x40`| cl pump running             | see Open Item 7        |
| 7    | `0x80`| pH− pump running            | see Open Item 7        |

### `byte[29]` vs `filtration_mode` (firmware B manual OFF)

Cross-frame analysis of @dtpugh's four firmware B frames (24h nonstop, P1 only,
P1 & P2, OFF manual) shows that `byte[29]` bit 3 stays set in **all four**
frames — including the OFF frame. The override state lives in `byte[37]` bit 2
(firmware B only, value `0x35`), not in `byte[29]`. The decoder compensates for
this HOME-only behaviour in `_fill_consumable_data` (see `_fill_filtration_mode`
in `aseko_decoder.py`).

Bit 2 is decoded into `filtration_mode` (`SCHEDULE` / `MANUAL`) and the
schedule bits into `filtration_schedule`, so the schedule stays readable while
the override is on — the two are independent and one value cannot carry both.

### `byte[22]` — Variable-speed filtration pump (Issue #137)

Some HOME REDOX devices (serial 110175608) support a variable-speed filtration
pump. The brand can be configured in the Aseko app (Speck, Pentair, Hayward,
Dab E.SWIM, Uwe EO PM).

**byte[22] bit 3 (0x08)** reflects the pump ON/OFF state:
- `0x83` (`1000_0011`) → pump OFF
- `0x8b` (`1000_1011`) → pump ON (any brand)

The field is decoded as `vsp_pump_running` and gated on `AsekoDeviceType.HOME` in
`_fill_vsp_pump()` — other device types (SALT, OXY, PROFI, NET) leave it `None`.

**byte[78]** changes with the brand selection but is not a unique brand ID:

| Brand | byte[78] hex | byte[78] dec |
|-------|--------------|--------------|
| OFF / Speck / Uwe EO PM | `0x22` | 34 |
| Pentair / Dab E.SWIM | `0x26` | 38 |
| Hayward | `0x2a` | 42 |

Speck and Uwe share the same value as OFF, suggesting byte[78] is a
**pump parameter** (speed/power class) rather than a brand identifier. The
brand selection itself may be stored only in the Aseko cloud/app, not in the
120-byte frame — see Open Item 11.

---

## Open Items

| # | Description |
|---|-------------|
| 3 | `required_water_temperature` vs app "---" — partially resolved by Issue #135: `byte[55]` is confirmed as the heating setpoint on serial 110175608 (REDOX HOME, heating ON frame). A frame from a device where the app actively shows a target temperature (not "---") would further validate this. |
| 7 | `byte[29]` per-pump bits for HOME (algicide, flocculant, cl, pH−) are unconfirmed. The masks in `ACTUATOR_MASKS[HOME]` are placeholders matching OXY/NET. Capturing frames with a single HOME pump running (e.g. algicide only) would pin down the per-pump bit. Until then, `algicide_pump_running` and `floc_pump_running` may report incorrectly on HOME. |
| 8 | `max_filling_time` overlap with `flowrate_ph_minus` (both use `byte[95]`). If `byte[94]` ever becomes non-zero, `max_filling_time` is inflated. Only a frame with a non-zero `byte[94]` would prove or disprove the assumption. |
| 9 | `heating_active` binary sensor (`byte[29]` bit `0x04`) — needs a frame captured while the heat pump / electric heater is actually running. The `heating_control_enabled` field (byte[37] bit 3) is the **master enable**, separate from the actual heating output state in byte[29] bit 2. A frame with `byte[29]` bit 2 set would confirm this as the running-state indicator. |
| 10 | Bytes 31, 38, 65 in the firmware B OFF frame all rise by ~1 (0x00→0x02, 0x02→0x03, 0xa3→0xa4) — possible additional "manual override active" sub-flags, not used by the decoder today. Single observation, no meaning assigned. |
| 11 | `byte[78]` pump brand correlation (Issue #137): Speck and Uwe EO PM share `0x22` (same as OFF), Pentair and Dab E.SWIM share `0x26`. Needs a diagnostic captured while switching between two same-value brands (e.g. Speck → Uwe) without turning the pump off to confirm whether byte[78] is a brand ID or a pump parameter. |

---

## Test Coverage

Tests for the HOME decoder live in `tests/test_aseko_decoder.py`:

| Test | Covers |
|------|--------|
| `test_decode_home` | End-to-end HOME REDOX frame decoding, including schedule + max_filling_time |
| `test_decode_home_clf_real_frame` | Issue #110: real HOME CLF frame with `max_filling_time = 60` |
| `test_decode_home_independent_flowrates` | Issue #115: HOME reads `byte[101]` and `byte[103]` independently of `byte[37]` |
| `test_decode_home_flowrates_unspecified` | 0xFF on flowrate bytes → `None` (pump not installed) |
| `test_decode_home_algicide_pump_running` | Issue #115: `algicide_pump_running` binary sensor is registered |
| `test_decode_home_floc_pump_running_independent` | HOME reports `floc_pump_running` correctly when only floc pump is installed |
| `test_filtration_mode_new_encoding_24h` | Issue #133 firmware B: `byte[37]=0x01` → schedule `NONSTOP_24H` |
| `test_filtration_mode_new_encoding_p1` | Issue #133 firmware B: `byte[37]=0x11` → schedule `TIMER_PERIOD_1` |
| `test_filtration_mode_new_encoding_p1_and_p2` | Issue #133 firmware B: `byte[37]=0x31` → schedule `TIMER_PERIOD_1_AND_2` |
| `test_filtration_mode_new_encoding_manual_p1_and_p2` | Issue #133 firmware B: `byte[37]=0x35` → mode `MANUAL` |
| `test_filtration_mode_old_encoding_24h` | Issue #110 firmware A: `byte[37]=0x43` → schedule `NONSTOP_24H` |
| `test_filtration_mode_old_encoding_timer` | Issue #110 firmware A: `byte[37]=0x53` → schedule `TIMER_PERIOD_1_AND_2` |
| `test_filtration_mode_salt_uses_the_firmware_b_bits` | SALT: all six captured `byte[37]` values → mode + schedule |
| `test_filtration_schedule_survives_manual_mode` | `0xC3` → `0xC7` → `0xC3`: the schedule reads the same throughout |
| `test_filtration_pump_running_off_when_manual_override` | Issue #133: `byte[37]=0x35` forces `filtration_pump_running=False` |
| `test_filtration_pump_running_on_when_not_override` | Regression guard: `byte[29]&0x08` still drives the entity outside MANUAL |
| `test_filtration_pump_running_not_overridden_on_salt` | Override short-circuit is HOME-only |
| `test_decode_filtration_period2_disabled` | Issue #133: bytes 60-63 stay populated; mode flips to `TIMER_PERIOD_1` |
| `test_decode_filtration_period2_bytes_unspecified` | Issue #133: bytes 60-63 = 0xFF → `start2`/`stop2` = `None` (entity skipped) |
| `test_decode_filtration_period2_none_for_net` | Issue #133: NET never gets filtration entities (lazy-creation guard) |
| `test_decode_filtration_period2_real_dtpugh_frames` | Issue #133: end-to-end against @dtpugh's four diagnostic files (P1 only / P1&P2 / 24h / OFF) |
| `test_decode_home_heating_control_enabled` | Issue #135: `byte[37]=0x49` → `heating_control_enabled=True` with schedule-derived filtration mode |
| `test_decode_home_heating_control_disabled` | Issue #135: `byte[37]=0x41` → `heating_control_enabled=False` |
| `test_decode_home_heating_control_unconfigured` | Issue #135: `byte[37]=0x45` → `heating_control_enabled=False` (initial state) |
| `test_decode_home_heating_control_not_present_on_salt` | Heating gating: SALT frames with `byte[37]` set never report `heating_control_enabled` |

---

## Cross-References

- Related decoder file: `custom_components/aseko_local/aseko_decoder.py`
- Actuator masks: `custom_components/aseko_local/aseko_v7_helpers.py` → `ACTUATOR_MASKS[AsekoDeviceType.HOME]`
- `AsekoByte37Masks`: `custom_components/aseko_local/aseko_v7_helpers.py`
- OXY analysis (reference for shared byte layout): `docs/device analyzes/oxy_device_analysis.md`
- NET v8 analysis: `docs/device analyzes/net_v8_device_analysis.md`
- Issue #110: byte[37] firmware A (`0x43` = nonstop 24h) — original finding, frames in this file
- Issue #115: HOME `algicide_pump_running` missing — fixed by independent-pump-port branch
- Issue #133: byte[37] firmware B (4-state mode + manual OFF) — fixed by `_fill_filtration_mode` rewrite.  Period 2 schedule bytes (60-63) are now read unconditionally for any device in `FILTRATION_TYPES` to avoid "unknown" entities when the user toggles the controller.  See the *Note on Period 2 schedule bytes (Issue #133)* under `byte[29]` vs `filtration_mode` below.
- Issue #135: `byte[37]` bit 3 (`0x08`) = heating control master enable on HOME firmware A
  (serial 110175608, REDOX HOME). Confirms `byte[55]` as target water temp setpoint.
  Working notes: [docs/temp/Issue-135.md](../temp/Issue-135.md).
- Issue #136: `byte[37]` bit 7 (`0x80`) = antifreeze master enable on HOME firmware A
  (same device). `byte[55]` shows the antifreeze setpoint (e.g. 4°C, 5°C, 9°C)
  when enabled.
- Issue #137: `byte[22]` bit 3 (`0x08`) = variable-speed pump running state on HOME.
  `byte[78]` changes with pump brand selection (Speck/Pentair/Hayward/Dab/Uwe) but
  is not a unique brand ID — see Open Item 11.
- Issue #139: `byte[112]` = pH⁻ acid concentration (%) on HOME (serial 110175608).
  Confirmed 5% → 10% → 5% across three diagnostics.
- Working notes: `docs/temp/Issue-133.md`
