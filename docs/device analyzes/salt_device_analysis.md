# ASIN AQUA Salt – Reverse Engineering & Implementation Notes

## Device

| Field | Value |
|---|---|
| Model | ASIN AQUA Salt |
| Firmware | 5.x – 7.x |
| Serial | `0x0000000E` (cleared in PR #87 frames) |
| Source | PR #87 live captures 2026-04-04; earlier frames 2026-04-02, 2026-04-03; Issue #84 |
| byte[4] | `0x0E` or `0x0D` → `(data[4] & 0x0C) == 0x0C` → **SALT** |

---

## Frame Structure

All SALT frames are 120 bytes, split into three 40-byte sub-frames. The sub-frame type is
encoded at byte offset 5 (first sub-frame), 45, and 85:

| Sub-frame | Type byte | Content |
|---|---|---|
| 0–39 | `0x01` | Live sensor data |
| 40–79 | `0x03` | Configuration / setpoints |
| 80–119 | `0x02` | Flow rates / dosing |

---

## byte[4] – Unit Type Detection

`UNIT_TYPE_SALT = 0x0C`. Detection: `(data[4] & 0x0C) == 0x0C`.

Known values observed: `0x0D`, `0x0E`. Both match the SALT mask.

**Convention**: **Bit SET (`1`) = probe ABSENT; bit CLEAR (`0`) = probe PRESENT** (negative/inverted
convention, named `PROBE_X_MISSING` in the code).

| Bit | Mask | Constant | Bit SET (1) means | Bit CLEAR (0) means |
|---|---|---|---|---|
| 0 | `0x01` | `PROBE_REDOX_MISSING` | REDOX probe **absent** | REDOX probe **present** |
| 1 | `0x02` | `PROBE_CLF_MISSING` | CLF probe **absent** | CLF probe **present** |
| 2–3 | `0x0C` | `UNIT_TYPE_SALT` | **SALT type identifier** (both bits must be set) | — |

---

## Byte Map – Sub-frame 1 (live sensor data)

| Byte(s) | Decoded | Notes |
|---|---|---|
| `[0:4]` | Serial number (big-endian) | |
| `[4]` | Unit type + probe flags | `0x0E` or `0x0D` |
| `[5]` | Sub-frame type `0x01` | |
| `[6:12]` | Timestamp (year−2000, month, day, hour, min, sec) | Device clock |
| `[14:16]` | pH = value / 100 | |
| `[16:18]` | CLF or REDOX (probe-dependent) | CLF: `/100` mg/L; REDOX: `×1` mV |
| `[18:20]` | REDOX (if CLF also present on PROFI-style) | Not applicable on basic SALT |
| `[20]` | Salinity = value / 10 | SALT-specific |
| `[21]` | Electrolyzer power (% or raw) | `0` when electrolyzer not running |
| `[25:27]` | Water temperature = value / 10 | °C |
| `[28]` | Water flow to probes | `0xAA` = flowing |
| `[29]` | Actuator bitmask | **See §byte[29]** |
| `[37]` | Third-pump routing (algicide vs. flocculant) | **See §byte[37]** |

---

## byte[29] – Actuator Bitmask

### Confirmed masks

**Source: PR #87 captures 2026-04-04 (55 type-01 frames, two distinct phases)**

| Bit | Mask | Phase | Observed byte[29] | Evidence |
|---|---|---|---|---|
| 3 | `0x08` | Filtration | baseline `0x08` | Set in all active phases (04-04) ✅ |
| 4 | `0x10` | Electrolyzer RIGHT | `0x18 = 0x08\|0x10` | 25 frames (04-04 Phase 4) ✅ |
| 5 | `0x20` | Algicide / Flocculant pump | `0x28 = 0x08\|0x20` | 27 frames (04-04 Phase 2) ✅ |
| 6 | `0x40` | Electrolyzer LEFT (tentative) | `0x58 = 0x08\|0x10\|0x40` | 1 frame (04-02) ⚠️ tentative |

**Key insight**: Algicide and Flocculant both use **the same bit `0x20`**. The third pump
port is a single physical output. The chemical type is determined by `byte[37]`, not by
a separate bit in byte[29].

### Unconfirmed masks

| Bit candidate | Mask | Hypothesis | Status |
|---|---|---|---|
| 7 | `0x80` | pH− pump | ⏳ No frame captured with pH− pump running |

### Pump states are exclusive (not parallel)

The SALT unit has only **one third-pump port**. Algicide and flocculant are mutually
exclusive configurations — the pump cannot run as both simultaneously. The electrolyzer
and algicide/flocculant CAN be active at the same time (each has a separate pump/output).

---

## byte[37] – Third-Pump Routing (Algicide vs. Flocculant)

The SALT unit has one physical pump port that can be configured as either algicide or
flocculant. `byte[37]` encodes which chemical is active:

| byte[37] value | bit 7 | Chemical configured |
|---|---|---|
| `0xb7`, `0xb3` | `1` | **Algicide** (ml/m³/day) |
| `0x37` | `0` | **Flocculant** (ml/h) |
| `0xFF` | N/A | Not configured / NET device |

**Routing rule (Hopkins firmware v7.x)**: `byte[37] & 0x80 == 0x80` → algicide; else → flocculant.

### Firmware variant caution

Issue #84 SALT shows `byte[37] = 0x13` for algicide. Here bit 7 (`0x80`) is **not** set —
the routing bit differs from the v7.x firmware. The two SALT variants encode the chemical
type differently in byte[37].

**Implication**: the `0x80` routing rule is not universally reliable across all SALT
firmware versions. See [byte37_algicide_floc_analysis.md](../temp/byte37_algicide_floc_analysis.md) for
full XOR analysis.

### byte[37] also contains other fields

`byte[37]` is a packed multi-field byte — it is **not** a pure single-bit flag:

| Comparison | XOR | Bit(s) changed |
|---|---|---|
| Algicide 10 → Algicide 11 (dosage +1) | `0x04` | bit 2 only |
| Algicide 11 → Flocculant 11 (type change) | `0x84` | bit 7 + bit 2 |
| Algicide 10 → Flocculant 11 (both change) | `0x80` | bit 7 only |

Bit 2 (`0x04`) appears related to dosage encoding. The full semantics of all bits are not
confirmed.

---

## Byte Map – Sub-frame 2 (config / setpoints)

| Byte(s) | Decoded | Notes |
|---|---|---|
| `[52]` | Required pH = value / 10 | |
| `[53]` | Required CLF (mg/L ÷10) or REDOX (×10 mV) | Depends on active probe |
| `[54]` | Required algicide (ml/m³/day) or Required floc (ml/h) | Routed by `byte[37]` |
| `[55]` | Required water temperature (°C) | |
| `[56:58]` | Filtration start1 | HH:MM |
| `[58:60]` | Filtration stop1 | HH:MM |
| `[60:62]` | Filtration start2 | HH:MM |
| `[62:64]` | Filtration stop2 | HH:MM |
| `[68]` | Backwash every N days | `0` = disabled |
| `[69:71]` | Backwash time | HH:MM |
| `[71]` | Backwash duration | ×10 seconds |

---

## Byte Map – Sub-frame 3 (flow rates)

| Byte(s) | Decoded | Notes |
|---|---|---|
| `[92:94]` | Pool volume (m³) | |
| `[95]` | Flowrate pH− (ml/min) | Confirmed |
| `[99]` | Flowrate chlorine pump (ml/min) | Not applicable on SALT (no CL pump) |
| `[101]` | Flowrate third-pump slot (ml/min) | 60 ml/min in all captured frames |
| `[103]` | Flowrate third-pump slot (duplicate?) | Also 60 ml/min; does not flip with algicide/floc switch |

**Note on byte[101] vs byte[103]**: Both bytes carry the same flowrate (60 ml/min)
regardless of whether algicide or flocculant is configured. The third pump slot does NOT
split its flowrate across different bytes when switching chemicals — see
[byte37_algicide_floc_analysis.md](../temp/byte37_algicide_floc_analysis.md).

---

## Electrolyzer

The SALT unit has an integrated salt-water electrolysis cell for chlorine production.

| Field | byte | Notes |
|---|---|---|
| `electrolyzer_active` | `[29] & 0x10` | `True` when RIGHT cycle running |
| `electrolyzer_power` | `[21]` | Raw value; `0` when not running |
| `electrolyzer_direction` | `[29]` bits | `0x10` = RIGHT; `0x50 = 0x10|0x40` = LEFT (tentative) |
| `salinity` | `[20]` | g/L, value / 10 |

**Electrolyzer direction**: RIGHT direction is confirmed (`0x10`, 25 frames, Phase 4).
LEFT direction (`0x40`) is tentative — based on a single April 2 frame (`0x58 = 0x08|0x10|0x40`)
where the interpretation of bit `0x40` is uncertain.

---

## Confirmed `ACTUATOR_MASKS` for SALT

```python
AsekoDeviceType.SALT: AsekoActuatorMasks(
    filtration=0x08,             # confirmed ✓ 2026-04-04
    ph_minus=0x80,               # ⏳ unconfirmed – awaiting frame with pH− running
    algicide=0x20,               # confirmed ✓ 2026-04-04 (27 frames)
    flocculant=0x20,             # confirmed ✓ 2026-04-03 (same bit as algicide)
    electrolyzer_running=0x10,   # confirmed ✓ 2026-04-04 (25 frames)
    electrolyzer_running_right=0x10,  # confirmed ✓
    electrolyzer_running_left=0x50,   # ⚠️ tentative – 1 frame only
)
```

---

## Open Questions

| Question | Status |
|---|---|
| pH− pump mask in byte[29]? | ⏳ Candidate `0x80` — consistent with HOME/OXY; awaiting frame |
| Electrolyzer LEFT mask? | ⚠️ Tentative `0x40` — single frame, April 2, 2026 |
| byte[37] full field layout? | ⏳ Bits 0–6 partially known; full semantics not confirmed |
| byte[37] routing for Issue #84 firmware? | ⚠️ `0x13` = algicide but bit 7 NOT set — different firmware variant |
| byte[103] semantics? | ⏳ Always mirrors byte[101] on SALT — may be a duplicate or separate pump |
