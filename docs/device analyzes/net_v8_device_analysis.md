# ASIN AQUA NET fw v8 – Reverse Engineering & Field Mapping Notes

## Device

| Field | Value |
|---|---|
| Model | ASIN AQUA NET |
| Firmware | 8.x (text frame) |
| Serial | `110203680` |
| Source | Two production frames (Sep 16 2025, Apr 13 2026) + Aseko Pool Live app screenshots |
| Decoded by | `AsekoV8Decoder` in `aseko_decoder_v8.py` |

---

## Frame Structure

Unlike fw v7 (120-byte binary), fw v8 sends a human-readable text frame over TCP:

```
{v1 <serial> <f2> <f3> <f4>
 ins: <i0> <i1> ... <iN>
 ains: <a0> <a1> ... <aN>
 outs: <o0> <o1> ... <oN>
 areqs: <r0> <r1> ... <rN>
 reqs: ...
 fncs: ...
 mods: ...
 flags: ...
 crc16: XXXX}\n
```

- Starts with `{v1` — used by `_sync_frame()` to distinguish from binary frames
- Terminated with `}\n` — the `\n` must be forwarded to Aseko Cloud (line-based protocol)
- Observed size: ~463 bytes
- Sentinel value: `-500` = probe absent or measurement unavailable → decoded as `None`

### Reference frames used for analysis

**Sep 16, 2025, 22:27 CEST** (from Issue #49 comment):
```
{v1 110203680 804 0 27 ins: 314 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 24 6 29 22 27 0
ains: 708 708 774 7790 0 0 779 779 0 0 0 0 0 0 0 0
outs: 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
areqs: 74 73 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0
reqs: 0 0 0 0 0 0 0 24 0 1 0 0 ... fncs: 0 0 3 0 0 0 2 0
mods: 2 0 0 1 0 0 0 0 flags: 2 0 0 0 0 0 0 0 crc16: C3C8}
```

**Apr 13, 2026, 12:27 CEST** (from Issue #49 comments + Aseko Pool Live screenshot):
```
{v1 110203680 804 0 27 ins: 180 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 25 1 24 12 27 0
ains: 649 649 804 8090 0 0 809 809 0 0 0 0 0 0 0 0
outs: 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
areqs: 74 74 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0
... crc16: C3C8}
```

---

## Header

| Position | Sep value | Apr value | Meaning | Status |
|---|---|---|---|---|
| `v1` | — | — | Protocol version identifier | confirmed |
| header[0] | `110203680` | `110203680` | `serial_number` | ✅ confirmed |
| header[1] | `804` | `804` | unknown — constant across frames | ❓ |
| header[2] | `0` | `0` | unknown — always 0 | ❓ |
| header[3] | `27` | `27` | unknown — always 27 | ❓ |

---

## `ins:` section — instantaneous sensor values

| index | Sep | Apr | Formula | `AsekoDevice` field | Confirmed by |
|---|---|---|---|---|---|
| `ins[0]` | 314 | 180 | ÷ 10 → °C | `water_temperature` | ✅ 31.4°C Sep / 18.1°C Apr matches app |
| `ins[1–3]` | -500 | -500 | — | `None` | ✅ absent probes |
| `ins[8]` | 1 | 1 | `bool` | `water_flow_to_probes` | ✅ app shows "Water flow: YES" |
| `ins[13]` | 24 | 25 | ? | unknown | ❓ |
| `ins[14]` | 6 | 1 | ? | unknown | ❓ |
| `ins[15]` | 29 | 24 | ? | unknown | ❓ |
| `ins[16]` | 22 | 12 | local hour | `timestamp.hour` | ✅ matches HA log timestamps |
| `ins[17]` | 27 | 27 | local minute | `timestamp.minute` | ✅ matches HA log timestamps |

**Note on `ins[13–15]`:** These change between frames and could encode a date (day/month/year or similar).
Not yet confirmed — `timestamp` currently falls back to HA clock date with device hour/minute.

---

## `ains:` section — analog inputs (probe measurements)

| index | Sep | Apr | Formula | `AsekoDevice` field | Confirmed by |
|---|---|---|---|---|---|
| `ains[0]` | 708 | 649 | ÷ 100 → pH | `ph` | ✅ 7.08 Sep / app shows 6.56 Apr |
| `ains[1]` | 708 | 649 | ÷ 100 (duplicate) | — | probable duplicate of `ains[0]` |
| `ains[2]` | 774 | 804 | ? | unknown | ❓ ~5 below `ains[6]` but not exactly |
| `ains[3]` | 7790 | 8090 | ÷ 10 → mV | — | = `ains[6] × 10`; not used |
| `ains[4–5]` | 0 | 0 | — | — | always 0 |
| `ains[6]` | 779 | 809 | direct mV | `redox` | ✅ app shows 848 mV (later reading) |
| `ains[7]` | 779 | 809 | duplicate | — | identical to `ains[6]` |

**pH vs app discrepancy (Apr 13):** `ains[0]=649` → 6.49, app shows 6.56.
Difference = 0.07 pH — likely the app shows a calibrated/averaged value, or the frame and screenshot were from slightly different moments.

**Probe configuration detection:**
`ains[0] != -500` → `AsekoProbeType.PH` present
`ains[6] != -500` → `AsekoProbeType.REDOX` present

---

## `outs:` section — output states (pumps)

| index | Sep | Apr | Formula | `AsekoDevice` field | Confirmed by |
|---|---|---|---|---|---|
| `outs[0]` | 0 | 0 | `bool` | `cl_pump_running`? | ❓ unconfirmed |
| `outs[1]` | 0 | 0 | `bool` | `ph_minus_pump_running`? | ❓ unconfirmed |
| `outs[2]` | 1 | 1 | `bool` | `filtration_pump_running` | ✅ app shows "Pump: ON / NONSTOP" |

---

## `areqs:` section — application requirements / setpoints

| index | Sep | Apr | Formula | `AsekoDevice` field | Confirmed by |
|---|---|---|---|---|---|
| `areqs[0]` | 74 | 74 | ÷ 10 | `required_ph` | ✅ app shows 7.4 |
| `areqs[1]` | 73 | 74 | × 10 → mV | `required_redox` | ✅ 74×10=740 mV matches app (Apr) |
| `areqs[2]` | 4 | 4 | ? | unknown | ❓ |
| `areqs[3]` | 5 | 5 | ? | unknown | ❓ |
| `areqs[5–6]` | 36 | 36 | ? | unknown | ❓ |
| `areqs[10]` | 6 | 6 | ? | unknown | ❓ |
| `areqs[12]` | 36 | 36 | ? | unknown | ❓ |
| `areqs[14]` | 45 | 45 | m³ | `pool_volume` | ✅ app shows 45 m³ |
| `areqs[16]` | 255 | 255 | = 0xFF | unknown — always `UNSPECIFIED` | ❓ |
| `areqs[17]` | 2 | 2 | minutes | `delay_after_startup` | ✅ app shows 2 min |
| `areqs[18]` | 2 | 2 | minutes | `delay_after_dose` | ✅ app shows 2 min |
| `areqs[19]` | 10 | 10 | ? | unknown | ❓ |
| `areqs[21]` | 15 | 15 | ? | unknown | ❓ |

**Note on `areqs[1]`:** Sep frame had `73` → 730 mV; Apr frame has `74` → 740 mV (matches app).
The user likely changed the setpoint between Sep 2025 and Apr 2026.

---

## `reqs:` section

Mostly zeros. Non-zero values observed (same in both frames):

| index | value | Hypothesis |
|---|---|---|
| `reqs[7]` | 24 | filtration duration = 24h (app shows "req filtration: 24h") |
| `reqs[9]` | 1 | ? |
| `reqs[33–34]` | 10 | ? |

---

## `fncs:` section

| index | value | Hypothesis |
|---|---|---|
| `fncs[2]` | 3 | ? |
| `fncs[6]` | 2 | ? |

---

## `mods:` section

| index | value | Hypothesis |
|---|---|---|
| `mods[0]` | 2 | operating mode? |
| `mods[3]` | 1 | ? |

---

## `flags:` section

| index | value | Hypothesis |
|---|---|---|
| `flags[0]` | 2 | ? |

---

## `crc16:` section

Value `C3C8` in both frames. Hex string — not parsed as integer by the decoder.
CRC16 validation **not yet implemented**.

---

## App Screenshots (Apr 13, 2026) — Reference Values

| App field | App value | Mapped to |
|---|---|---|
| Status: pH | 6.56 | `ains[0]=649` ÷ 100 = 6.49 (≈0.07 diff) |
| Status: Redox | 848 mV | `ains[6]=809` (taken at 12:27; screenshot from later in the day) |
| Status: Water temp | 18.1°C | `ins[0]=180` ÷ 10 = 18.0°C ✅ |
| Status: Pump | ON | `outs[2]=1` ✅ |
| Status: Filtration | NONSTOP | `outs[2]=1` ✅ |
| Status: Water flow | YES | `ins[8]=1` ✅ |
| Config: req pH | 7.4 | `areqs[0]=74` ÷ 10 = 7.4 ✅ |
| Config: req Redox | 740 mV | `areqs[1]=74` × 10 = 740 ✅ |
| Config: Pool volume | 45 m³ | `areqs[14]=45` ✅ |
| Config: Delay startup | 2 min | `areqs[17]=2` ✅ |
| Config: Delay after dose | 2 min | `areqs[18]=2` ✅ |
| Config: req filtration | 24 h | `reqs[7]=24` (probable) |
| Config: Water flow meter | ON | `ins[8]=1` ✅ |

---

## Open Questions

| # | Question | Status |
|---|---|---|
| 1 | What are `ins[13–15]`? (date-related?) | ❓ need more frames |
| 2 | What are `outs[0]` and `outs[1]`? (dosing pumps?) | ❓ need frame with pumps running |
| 3 | What is `ains[2]`? — slightly below `ains[6]`, not a simple duplicate | ❓ |
| 4 | What do header fields `804 0 27` mean? | ❓ constant in all known frames |
| 5 | What are `areqs[2–3]` (`4`, `5`)? | ❓ |
| 6 | What are `areqs[5, 6, 10, 12]` (all `36` or `6`)? | ❓ |
| 7 | What is `reqs[7]=24`? Filtration hours per day? | probable ✅ |
| 8 | CRC16 validation — implement? | decision pending |
| 9 | Are there v8 frames from SALT / OXY / HOME devices? | ❓ unknown |
