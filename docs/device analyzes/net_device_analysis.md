# ASIN AQUA NET – Reverse Engineering & Implementation Notes

## Device

| Field | Value |
|---|---|
| Model | ASIN AQUA NET |
| Firmware | 7.x (120-byte frame); fw 8.x uses a different 463-byte frame structure (not yet implemented) |
| Source | Issue #66; AquaNET log 2026-04-07 13:15–13:16 (probe-mode switch capture) |
| byte[4] | `0x09` (CLF active) or `0x0b` (DOSE mode) → `bool(data[4] & 0x08)` → **NET** |

---

## Frame Structure

All NET frames are 120 bytes, split into three 40-byte sub-frames. The sub-frame type is
encoded at byte offset 5 (first sub-frame), 45, and 85:

| Sub-frame | Type byte | Content |
|---|---|---|
| 0–39 | `0x01` | Live sensor data |
| 40–79 | `0x03` | Configuration / setpoints |
| 80–119 | `0x02` | Flow rates / dosing |

---

## byte[4] – Unit Type Detection

`UNIT_TYPE_NET = 0x08`. Detection: `bool(data[4] & 0x08)`.

| byte[4] value | Mode | Detected as |
|---|---|---|
| `0x09` | CLF probe active | NET ✅ |
| `0x0b` | DOSE mode (volume dosing) | **HOME** ❌ — existing bug |

### Why NET in DOSE mode decodes as HOME

`0x0b = 0b00001011`. The HOME check `(data[4] & 0x03) == 0x03` fires first in the
decoder's if-chain, matching `0x0b & 0x03 = 0x03`. This misclassification is a known
bug — not introduced by OXY work. It is out of scope for v1.4.0.

### Probe flags in byte[4]

**Convention**: the bit is named `PROBE_X_MISSING` in the code. **Bit SET (`1`) = probe ABSENT; bit CLEAR (`0`) = probe PRESENT.** This is an inverted/negative convention.

| Bit | Mask | Constant | Bit SET (1) means | Bit CLEAR (0) means |
|---|---|---|---|---|
| 0 | `0x01` | `PROBE_REDOX_MISSING` | REDOX probe **absent** | REDOX probe **present** |
| 1 | `0x02` | `PROBE_CLF_MISSING` | CLF probe **absent** | CLF probe **present** |
| 2 | `0x04` | `PROBE_DOSE_MISSING` | DOSE mode inactive | DOSE mode active |
| 3 | `0x08` | `UNIT_TYPE_NET` | **NET identifier** | — |

**Known NET variants:**

| byte[4] | binary | REDOX | CLF | DOSE | Detected as |
|---|---|---|---|---|---|
| `0x09` | `0000 1001` | absent | **present** | off | NET ✅ |
| `0x0a` | `0000 1010` | **present** | absent | off | NET ✅ (REDOX variant) |
| `0x0b` | `0000 1011` | absent | absent | on | **HOME** ❌ (DOSE-mode bug) |

---

## NET-Specific Characteristics

### No filtration output

The ASIN AQUA NET has no pump or relay for the filtration/filter circuit. It is a
measurement-only device (probes) combined with chemical dosing pumps. There is no
`filtration_pump_running` for NET — the bit `0x08` in byte[29] does **not** mean
filtration on NET devices.

Confirmed by Issue #66: `filtration_pump_running` is always `None` on NET.

### Timestamp: all 0xFF

NET devices send `data[6:12] = 0xFF` (all timestamp bytes UNSPECIFIED). The decoder
uses `datetime.now()` as a fallback in this case.

### cl_free_mv in bytes[20:22]

On NET with CLF probe: `bytes[20:22]` = free chlorine in millivolts (signed 16-bit).
This is different from SALT where `byte[20]` = salinity and `byte[21]` = electrolyzer power.

---

## Byte Map – Sub-frame 1 (live sensor data)

| Byte(s) | Decoded | Notes |
|---|---|---|
| `[0:4]` | Serial number (big-endian) | |
| `[4]` | Unit type + probe flags | `0x09` typical |
| `[5]` | Sub-frame type `0x01` | |
| `[6:12]` | Timestamp | **Always `0xFF` on NET** — decoder falls back to `now()` |
| `[14:16]` | pH = value / 100 | |
| `[16:18]` | CLF = value / 100 (mg/L) | |
| `[20:22]` | cl_free_mv (mV, signed) | NET-specific; SALT uses `[20]` for salinity |
| `[25:27]` | Water temperature = value / 10 | °C |
| `[28]` | Water flow to probes | `0xAA` = flowing |
| `[29]` | Actuator bitmask | **See §byte[29]** |
| `[37]` | `0xFF` | Not used on NET — no third-pump port |

---

## byte[29] – Actuator Bitmask

### Confirmed masks

**Source: Issue #66 (confirmed by test `test_decode_net_pump_states`)**

| Bit | Mask | Pump | Status |
|---|---|---|---|
| 0 | `0x01` | **pH− pump** | ✅ Confirmed Issue #66 |
| 1 | `0x02` | **Chlorine (CL) pump** | ✅ Confirmed Issue #66 |
| 3 | `0x08` | ❌ NOT filtration | ✅ No filtration output on NET |

**Note**: Bit `0x08` has no meaning for NET. The bit positions are different from SALT/HOME/OXY.

### Pumps can run in parallel

The NET has independent pH− and CL pump outputs. Both bits can be set simultaneously:
`byte[29] = 0x03 = 0x01|0x02` = pH− and CL pumps running at the same time.

### Unconfirmed masks

| Bit candidate | Mask | Hypothesis | Status |
|---|---|---|---|
| — | — | No other pumps known on NET | — |

---

## Byte Map – Sub-frame 2 (config / setpoints)

| Byte(s) | Decoded | Notes |
|---|---|---|
| `[52]` | Required pH = value / 10 | |
| `[53]` | Required CLF = value / 10 (mg/L) | |
| `[54]` | Required algicide (ml/m³/day) | Non-`0xFF` when pump port configured |
| `[55]` | Required water temperature (°C) | `0xFF` = not set |
| `[56:58]` | Filtration start1 | `0xFFFF` = not set |
| `[58:60]` | Filtration stop1 | `0xFFFF` = not set |
| `[60:62]` | Filtration start2 | `0xFFFF` = not set |
| `[62:64]` | Filtration stop2 | `0xFFFF` = not set |
| `[68]` | Backwash every N days | `0xFF` = not set |
| `[69:71]` | Backwash time | `0xFFFF` = not set |
| `[71]` | Backwash duration | `0xFF` = not set |

Many config bytes are `0xFF` (UNSPECIFIED) on NET because the device has no filtration
schedule, backwash, or water-temperature probe.

---

## Byte Map – Sub-frame 3 (flow rates)

| Byte(s) | Decoded | Notes |
|---|---|---|
| `[92:94]` | Pool volume (m³) | |
| `[95]` | Flowrate pH− (ml/min) | Confirmed |
| `[99]` | Flowrate CL pump (ml/min) | Confirmed (`flowrate_chlor`) |
| `[101]` | Flowrate third-pump slot | `0xFF` on NET (no third pump) |
| `[103]` | `0x03` | Phantom value on NET — ignore |

---

## DOSE Mode (byte[4] = 0x0b)

When the user switches the NET to volume-based dosing mode (ml/m³/h) in the Aseko app,
`byte[4]` changes from `0x09` → `0x0b`. The PROBE_CLF_MISSING bit (`0x02`) toggles,
making the decoder classify the device as HOME.

**Captured 2026-04-07 13:15–13:16** (70-second window around mode switch):

| Time | byte[4] | Decoded as | Active mode |
|---|---|---|---|
| 13:15:00 | `0x0b` | **HOME** (bug) | ml/m³/h DOSE mode |
| 13:16:10 | `0x09` | NET ✅ | CLF probe active |

In DOSE mode, `byte[16:18]` = live CLF reading (e.g. `0x006a` = 1.06 mg/L) — the CLF
probe hardware is still measuring even when the control mode switches to volume dosing.
This contrasts with OXY where `byte[16:18] = 0x001E` (invariant placeholder, no CLF hardware).

---

## Confirmed `ACTUATOR_MASKS` for NET

```python
AsekoDeviceType.NET: AsekoActuatorMasks(
    # Aqua NET has no filtration output — confirmed: Issue #66
    cl=0x02,        # confirmed ✓ Issue #66
    ph_minus=0x01,  # confirmed ✓ Issue #66
)
```

---

## Open Questions

| Question | Status |
|---|---|
| NET-in-DOSE-mode decoded as HOME? | ⚠️ Known bug — filed as separate issue, out of v1.4.0 scope |
| byte[29] other bits on NET? | ⏳ Only `0x01` and `0x02` confirmed — no further pump outputs known |
| ph_plus pump on NET? | ⏳ NET hardware may not have pH+ pump — not confirmed |
| byte[37] = `0xFF` always on NET? | ✅ Confirmed — `0xFF` (UNSPECIFIED) in all captured frames |
