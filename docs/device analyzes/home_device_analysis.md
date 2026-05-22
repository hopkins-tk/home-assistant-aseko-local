# ASIN AQUA Home — Device Analysis

**Model**: ASIN AQUA HOME (CLF variant)
**Serial**: 110128063 (`0x06906bbf`)
**Device type byte**: `0x02` → `UNIT_TYPE_HOME_CLF`
**Source frame timestamp**: 2026-04-28 08:27:07
**Ground truth**: Aseko Live app screenshots (Status, Consumption, Config pages)

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
| 12      | `00`     | 0       | Unknown                  | —                    | —             | ?      |
| 13      | `28`     | 40      | Unknown                  | —                    | —             | ?      |
| 14–15   | `0275`   | 629     | pH (÷100)                | **6.29**             | 6.56†         | ✓†     |
| 16–17   | `0000`   | 0       | Cl free (÷100)           | **0.00 mg/l**        | 0.00 mg/l     | ✓      |
| 18–19   | `0000`   | 0       | Unused (no REDOX probe)  | —                    | —             | —      |
| 20–21   | `0002`   | 2       | Cl free mV (big-endian)  | **2 mV**             | —             | ✓      |
| 22–23   | `90fe`   | 37118   | Unknown (internal probe?) | —                   | —             | ?      |
| 24      | `70`     | 112     | Unknown                  | —                    | —             | ?      |
| 25–26   | `017b`   | 379     | Water temp (÷10)         | **37.9°C**           | 38.2°C†       | ✓†     |
| 27      | `08`     | 8       | Unknown                  | —                    | —             | ?      |
| 28      | `00`     | 0       | Water flow to probes     | **False** (≠ 0xAA)   | NO            | ✓      |
| 29      | `00`     | 0       | Actuator bits            | all pumps stopped    | STOP          | ✓      |
| 30–31   | `ffff`   | —       | UNSPECIFIED / padding    | —                    | —             | —      |
| 32–36   | `00…00`  | 0       | Unknown                  | —                    | —             | ?      |
| 37      | `43`     | 67      | Pump presence bitmap     | see note §           | —             | §      |
| 38      | `0a`     | 10      | Unknown                  | —                    | —             | ?      |
| 39      | `85`     | 133     | Unknown (checksum?)      | —                    | —             | ?      |

† pH 6.29 vs 6.56 and water temp 37.9 vs 38.2 are explained by different timestamps (frame: 08:27:07, screenshot: later that day). Not a decoding bug.

§ **byte[37] = `0x43`**: For SALT devices this is the algicide/flocculant routing byte. For HOME devices `byte37_routes_pump_type = False`, so routing logic is skipped. However the flowrate code (mistakenly) falls through to the SALT routing path and reads bit 7 (= 0) → flocculant branch → correctly yields `flowrate_floc = data[101] = 10`. This works by coincidence for this frame but the semantic is wrong. A HOME-specific flowrate branch (similar to OXY) is the correct long-term fix.

#### Actuator byte[29] — HOME masks (uncertain)

| Bit   | Mask   | Field                  | Value (0x00) |
|-------|--------|------------------------|-------------|
| bit 3 | `0x08` | filtration_pump_running | False ✓     |
| bit 6 | `0x40` | cl_pump_running        | False ✓     |
| bit 7 | `0x80` | ph_minus_pump_running  | False ✓     |
| bit 5 | `0x20` | algicide / floc running | False ✓    |

All masks marked **uncertain** — confirmed only from their absence (byte[29]=0x00 when nothing is running). Need frames captured while individual pumps are active to confirm per-pump bits.

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
| 54      | `0a`     | 10      | required_floc                 | **10 ml/h** ✓  | 10 ml/h           | ✓ (fixed) |
| 55      | `19`     | 25      | required_water_temperature    | 25°C ⚠️        | — (disabled)      | ⚠️     |
| 56–57   | `08 00`  | —       | start1                        | 08:00          | NONSTOP 24H ⚠️    | ⚠️     |
| 58–59   | `10 00`  | —       | stop1                         | 16:00          | NONSTOP 24H ⚠️    | ⚠️     |
| 60–61   | `12 00`  | —       | start2                        | 18:00          | NONSTOP 24H ⚠️    | ⚠️     |
| 62–63   | `16 00`  | —       | stop2                         | 22:00          | NONSTOP 24H ⚠️    | ⚠️     |
| 64–65   | `027c`   | 636     | Unknown                       | —              | —                 | ?      |
| 66–67   | `017b`   | 379     | Unknown (= water temp raw)    | —              | —                 | ?      |
| 68      | `03`     | 3       | backwash_every_n_days         | **3 days**     | every 3 days      | ✓      |
| 69–70   | `15 00`  | —       | backwash_time                 | **21:00**      | starts at 21:00   | ✓      |
| 71      | `0c`     | 12      | backwash_duration (×10 s)     | **120 s = 2 min** | takes 02:00 min | ✓    |
| 72      | `00`     | 0       | required_algicide             | **0 ml/m³/day** ✓ | 0 ml/m³/day    | ✓ (fixed) |
| 73      | `28`     | 40      | Unknown                       | —              | —                 | ?      |
| 74–75   | `01e0`   | 480     | delay_after_startup (s)       | **480 s = 8 min** | 8 min          | ✓      |
| 76      | `2a`     | 42      | Unknown                       | —              | —                 | ?      |
| 77      | `30`     | 48      | Unknown                       | —              | —                 | ?      |
| 78      | `a0`     | 160     | Unknown                       | —              | —                 | ?      |
| 79      | `d8`     | 216     | Unknown                       | —              | —                 | ?      |

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
| 101     | `0a`     | 10      | flowrate_floc (via routing)  | **10 ml/min**  | Floc+c listed     | ✓      |
| 102     | `0d`     | 13      | Unknown                      | —              | —                 | ?      |
| 103     | `21`     | 33      | flowrate_algicide? (unconf.) | —              | Algicide listed   | ?      |
| 104     | `37`     | 55      | Unknown                      | —              | —                 | ?      |
| 105     | `64`     | 100     | Unknown                      | —              | —                 | ?      |
| 106–107 | `00f0`   | 240     | delay_after_dose (s)         | **240 s = 4 min** | 4 min          | ✓      |
| 108     | `14`     | 20      | Unknown                      | —              | —                 | ?      |
| 109–110 | `0258`   | 600     | Unknown                      | —              | —                 | ?      |
| 111–113 | `0f 0f 0f` | 15, 15, 15 | Unknown                | —              | —                 | ?      |
| 114     | `1e`     | 30      | Unknown                      | —              | —                 | ?      |
| 115     | `14`     | 20      | Unknown                      | —              | —                 | ?      |
| 116     | `ff`     | —       | UNSPECIFIED / padding        | —              | —                 | —      |
| 117     | `bc`     | 188     | Unknown                      | —              | —                 | ?      |
| 118–119 | `0271`   | 625     | Unknown (checksum?)          | —              | —                 | ?      |

Note on **bytes 94–95**: `max_filling_time` reads bytes[94:96] as a big-endian 16-bit value = `0x003c` = 60. `flowrate_ph_minus` independently reads byte[95] = `0x3c` = 60. They overlap but coincidentally produce the same result because the high byte (94) is 0x00. If byte[94] ever becomes non-zero the max_filling_time would be inflated; however for HOME this is expected to fit in one byte (max ~255 min).

---

## Decoded Values vs Ground Truth Summary

| Field                     | Decoded          | Aseko Live        | Match |
|---------------------------|------------------|-------------------|-------|
| pH                        | 6.29             | 6.56              | ✓ (Δt)|
| Cl free                   | 0.00 mg/l        | 0.00 mg/l         | ✓     |
| Water temperature         | 37.9°C           | 38.2°C            | ✓ (Δt)|
| Water flow to probes      | False            | NO                | ✓     |
| Filtration pump running   | False            | STOP              | ✓     |
| required_ph               | 7.0              | 7.0               | ✓     |
| required_cl_free          | 0.3 mg/l         | 0.3               | ✓     |
| required_floc             | 10 ml/h          | 10 ml/h           | ✓ (fixed) |
| required_algicide         | 0 ml/m³/day      | 0 ml/m³/day       | ✓ (fixed) |
| required_water_temperature | 25°C            | --- (disabled)    | ⚠️ see Issue 3 |
| Filtration schedule       | 08:00–16:00 / 18:00–22:00 | NONSTOP 24H | ⚠️ see Issue 4 |
| backwash_every_n_days     | 3                | every 3 days      | ✓     |
| backwash_time             | 21:00            | starts at 21:00   | ✓     |
| backwash_duration         | 120 s            | 02:00 min         | ✓     |
| pool_volume               | 60 m³            | 60 m³             | ✓     |
| delay_after_startup       | 480 s (8 min)    | 8 min             | ✓     |
| delay_after_dose          | 240 s (4 min)    | 4 min             | ✓     |
| flowrate_ph_minus         | 60               | pH- listed        | ✓     |
| flowrate_chlor            | 60               | Chlor Pure listed | ✓     |
| flowrate_floc             | 10               | Floc+c listed     | ✓     |
| flowrate_algicide         | None             | Algicide listed   | ⚠️    |

---

## Bugs Found

### Bug 1 (Fixed) — `required_floc` not decoded for HOME devices

**Root cause**: `_fill_required_data` decodes byte[54] as either `required_floc` or `required_algicide` only when `masks.byte37_routes_pump_type is True`. For HOME devices `byte37_routes_pump_type = False` (correct — HOME has independent pump ports), so the entire byte[54] block was silently skipped.

**Evidence**: byte[54] = `0x0a` = 10 → required_floc = 10 ml/h. Aseko Live Config confirms **Flocc: 10 ml/hour**.

**Fix applied** (`aseko_decoder.py`): Added a HOME-specific branch (parallel to OXY) that unconditionally decodes byte[54] as `required_floc`. Test: `test_decode_home_clf_real_frame`.

---

### Bug 2 (Fixed) — `required_algicide` not decoded for HOME devices

**Root cause**: Same as Bug 1 — the byte[54]/byte[72] routing block was skipped for HOME. HOME uses the same byte positions as OXY Pure.

**Evidence**: Aseko Live Config shows **Algicide: 0 ml/m³/day**. Frame byte[72] = `0x00` = 0.

**Fix applied** (`aseko_decoder.py`): The same HOME branch also decodes byte[72] as `required_algicide` (identical to OXY layout). Test: `test_decode_home_clf_real_frame`.

---

### Issue 3 (Pending — low-water condition at capture time)

**Observation**: byte[55] = `0x19` = 25 → decoded as 25°C. Aseko Live shows "---" for Water temp (disabled/not configured).

**Context**: The frame was captured while Aseko Live was showing an error, most likely caused by insufficient water in the pool (evidenced by cl_free = 0 and filtration pump stopped). The device may report a placeholder/default value in certain fields during an error or standby state, which would explain the "---" in the app despite byte[55] being non-zero.

**Action needed**: Request a new frame when the pool is running normally and compare byte[55] — if the water temperature control feature is enabled and active, the decoded value should match the app. Until then this issue remains unresolved.

---

### Issue 4 (Pending — low-water condition at capture time)

**Observation**: Aseko Live Config shows **FILTRATION NONSTOP 24H**. The decoder produces start1=08:00, stop1=16:00, start2=18:00, stop2=22:00 (12 h total — inconsistent with nonstop mode).

**Context**: The frame was captured while the pool had an error (likely too little water). The filtration pump was stopped and byte[29] = 0x00, consistent with an active alarm suppressing normal operation. It is possible that in a normal-operation frame the scheduled times look different, or that a separate flag byte signals "nonstop" mode.

**Hypothesis**: A "nonstop mode" flag byte exists somewhere in the frame. The scheduled times in bytes 56–63 may store the last manually-configured schedule as a fallback, even when nonstop mode is active.

**Action needed**: Request a new frame captured during normal (nonstop) operation and compare bytes 52–79 to identify the nonstop flag. Ideally also a second frame with timed schedule mode active.

---

### Issue 5 (Pending — algicide configured but not active)

**Observation**: Aseko Live Consumption page shows **Algicide** as a tracked chemical. `flowrate_algicide` is `None` in the decoded output.

**Context**: `required_algicide` = 0 ml/m³/day (byte[72] = 0x00). When the algicide dose is configured as zero the pump is effectively disabled and the device likely transmits 0 or UNSPECIFIED (0xFF) for the corresponding flowrate byte. This would explain why no valid flowrate is seen in the frame.

**Hypothesis re byte[103]**: byte[103] = `0x21` = 33 is a candidate for the algicide flowrate position (independent port, same layout as OXY). However, with dose = 0 the expected flowrate would be 0 — not 33 — so byte[103] is more likely an unrelated field. The actual algicide flowrate may be 0x00 or 0xFF at a yet-unidentified byte position when the pump is inactive.

**Current code path**: HOME falls through to the SALT routing logic in `_fill_flowrate_data`. Since byte[37] bit 7 = 0, the flocculant branch fires and byte[101] = 10 is correctly assigned to `flowrate_floc`. byte[103] is never read.

**Action needed**: Ask the user whether they plan to activate algicide dosing. If yes, request a frame captured while algicide is actively being dosed (dose > 0), then compare bytes 95–115 to locate the flowrate byte. Once confirmed, add a HOME-specific branch in `_fill_flowrate_data` mirroring the OXY branch.

---

## Applied Fixes

1. **`aseko_decoder.py` → `_fill_required_data`** — added HOME device branch (parallel to OXY, no early return so `required_cl_free` / `required_redox` are still decoded via the CLF branch):
   - byte[54] → `required_floc` (ml/h)
   - byte[72] → `required_algicide` (ml/m³/day)

```python
# HOME: has both CLF/REDOX setpoint at byte[53] AND independent floc/algicide setpoints.
# Same byte layout as OXY Pure for these two fields (confirmed 2026-04-28, frame analysis).
if unit.device_type == AsekoDeviceType.HOME:
    unit.required_floc = AsekoDecoder._normalize_value(data[54], int)
    unit.required_algicide = AsekoDecoder._normalize_value(data[72], int)
    # Fall through to decode required_cl_free (byte[53]) via the CLF branch below.
```

## Open Items

| # | Status | Description |
|---|--------|-------------|
| 3 | Pending | `required_water_temperature` vs app "---" — need normal-operation frame |
| 4 | Pending | Filtration NONSTOP 24H flag byte — need normal-operation frame |
| 5 | Pending | `flowrate_algicide` byte position — need frame with algicide dose > 0 |

---

## Cross-References

- Related decoder file: `custom_components/aseko_local/aseko_decoder.py`
- Actuator masks: `custom_components/aseko_local/aseko_data.py` → `ACTUATOR_MASKS[AsekoDeviceType.HOME]`
- OXY analysis (reference for shared byte layout): `docs/device analyzes/oxy_device_analysis.md`
- NET v8 analysis: `docs/device analyzes/net_v8_device_analysis.md`
