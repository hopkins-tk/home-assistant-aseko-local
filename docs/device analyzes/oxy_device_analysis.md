# ASIN AQUA Oxygen – Reverse Engineering & Implementation Plan

## Device

| Field | Value |
|---|---|
| Model | ASIN AQUA Oxygen |
| Serial | `0x0690DD6D` (decimal 110_157_165) |
| Source | Log `oxy_log.log`, 2026-04-02 18:20 – 19:34 |
| byte[4] | `0x05` → **Unknown unit type: 5** (current decoder fails here) |

---

## Frame Structure

All OXY frames are 120 bytes, split into three 40-byte sub-frames. The sub-frame type is
encoded at byte offset 5 (first sub-frame), 45, and 85:

| Sub-frame | Type byte | Content |
|---|---|---|
| 0–39 | `0x01` | Live sensor data |
| 40–79 | `0x03` | Configuration / setpoints |
| 80–119 | `0x02` | Flow rates / dosing |

---

## Representative Frames

### Normal frame (no pump running except filtration) – 19:33:38

```
06 90 dd 6d 05 01 1a 04 02 17 15 0a 00 00 02 cd 00 1e 00 1e fd 9d 80 fe 70 00 5f fe aa 08
00 00 00 00 00 00 00 03 08 35
06 90 dd 6d 05 03 1a 04 02 17 15 0a 48 08 01 19 08 00 10 00 12 00 16 00 02 c0 00 5f 00 0c
1e 0a 01 28 00 f0 0e 10 aa 3f
06 90 dd 6d 05 02 1a 04 02 17 15 0a 00 29 00 3c 00 3c 00 3c 00 0a 1e 3c 6e 96 00 78 08 02
58 0f 2b 0f 1e 1e aa cb 00 3a
```

### Flocculant pump running – 19:33:52 (duration: ~2 seconds)

```
06 90 dd 6d 05 01 1a 04 02 17 15 17 00 00 02 cd 00 1e 00 1e fd 9d 80 fe 70 00 5f fe aa 28
00 00 00 00 00 00 00 03 08 08
06 90 dd 6d 05 03 1a 04 02 17 15 17 48 08 01 19 08 00 10 00 12 00 16 00 02 c0 00 5f 00 0c
1e 0a 01 28 00 f0 0e 10 aa 2f
06 90 dd 6d 05 02 1a 04 02 17 15 17 00 29 00 3c 00 3c 00 3c 00 0a 1e 3c 6e 96 00 78 08 02
58 0f 2b 0f 1e 1e aa cb 00 27
```

**Only change vs. normal frame**: byte[29] `0x08` → `0x28` (+bit `0x20`).
Checksum bytes (39, 79, 119) and timestamp second (byte[11]) change as expected.

---

## Byte Map – Sub-frame 1 (live sensor data)

| Byte(s) | Value (normal) | Decoded | Notes |
|---|---|---|---|
| `[0:4]` | `06 90 dd 6d` | Serial = 110_157_165 | |
| `[4]` | `0x05` | Unit type / probe flags | **OXY-specific, see below** |
| `[5]` | `0x01` | Sub-frame type | |
| `[6:12]` | `1a 04 02 17 15 0a` | 2026-04-02 23:21:10 | Device clock desynchronised from server |
| `[14:16]` | `02 cd` | pH = 7.17 | ÷100 |
| `[16:18]` | `00 1e` | CLF slot = 30 → 0.30 | **Placeholder, see §CLF/REDOX** |
| `[18:20]` | `00 1e` | REDOX slot = 30 mV | **Placeholder, see §CLF/REDOX** |
| `[20:22]` | `fd 9d` | cl_free_mv = −611 mV (signed) | **Placeholder, no CLF probe** |
| `[25:27]` | `00 5f` | Water temp = 9.5 °C | ÷10 |
| `[28]` | `0xaa` | Water flow to probes = ON | `== 0xAA` |
| `[29]` | `0x08` / `0x28` | Actuator bitmask | **See §byte[29]** |
| `[37]` | `0x03` | Third-pump config byte | **See §byte[37]** |

## Byte Map – Sub-frame 2 (config / setpoints)

| Byte(s) | Value | Decoded | Notes |
|---|---|---|---|
| `[52]` | `0x48` = 72 | Required pH = 7.2 | ÷10 |
| `[53]` | `0x0c` = 12 | Required OXY dosage = **12 ml/m³/d** | Raw value, no scaling — see §byte[53] |
| `[54]` | `0x0a` = 10 | Required Floc = **10 ml/h** | ✓ Confirmed 2026-04-11 (Winnetoux) |
| `[55]` | `0x19` = 25 | Required water temp = 25 °C | |
| `[56:58]` | `08 00` | Filtration start1 = 08:00 | |
| `[58:60]` | `10 00` | Filtration stop1 = 16:00 | |
| `[60:62]` | `12 00` | Filtration start2 = 18:00 | |
| `[62:64]` | `16 00` | Filtration stop2 = 22:00 | |
| `[68]` | `0x00` | Backwash every N days = 0 (disabled) | |
| `[69:71]` | `0c 1e` | Backwash time = 12:30 | |
| `[71]` | `0x0a` | Backwash duration = 100 s | ×10 |
| `[72]` | `0x0f` = 15 | Required Algicide = **15 ml/m³/d** | ✓ Confirmed 2026-04-11 (Winnetoux) |
| `[73]` | `0x28` = 40 s | Delay after startup | |

## Byte Map – Sub-frame 3 (flow rates)

| Byte(s) | Value | Decoded | Notes |
|---|---|---|---|
| `[92:94]` | `00 29` | Pool volume = 41 m³ | |
| `[95]` | `0x3c` = 60 | Flowrate pH− = **60 ml/min** | Confirmed |
| `[97]` | `0x3c` = 60 | Flowrate pH+ = 60 ml/min | Position unconfirmed |
| `[99]` | `0x3c` = 60 | Flowrate OXY Pure = **60 ml/min** | Confirmed |
| `[101]` | `0x0a` = 10 | Flowrate Floc = **10 ml/min** | Confirmed |
| `[103]` | `0x3c` = 60 | Flowrate Algicide = **60 ml/min** | ✓ Confirmed 2026-04-11 (Winnetoux) |
| `[106:108]` | `00 78` | Delay after dose = 120 s | |

---

## byte[4] = 0x05 – Unit Type & Probe Flags

`0x05 = 0b00000101`

### Why the current decoder fails

| Check | Expression | Result |
|---|---|---|
| `UNIT_TYPE_PROFI` | `0x05 == 0x08` | `False` |
| `UNIT_TYPE_SALT` | `0x05 & 0x0C == 0x0C` | `0x04 ≠ 0x0C` → False |
| `UNIT_TYPE_HOME` | `0x05 & 0x03 == 0x03` | `0x01 ≠ 0x03` → False |
| `UNIT_TYPE_NET` | `bool(0x05 & 0x08)` | `bool(0)` → False |
| **→** | falls through | **`raise ValueError("Unknown unit type: 5")` → connection closed** |

### Probe flags decoded from 0x05

| Flag constant | Mask | `0x05 & mask` | Meaning |
|---|---|---|---|
| `PROBE_REDOX_MISSING` | `0x01` | `0x01` (set) | REDOX **absent** ✓ |
| `PROBE_CLF_MISSING` | `0x02` | `0x00` (**not set**) | ⚠️ CLF flagged as *present* — **incorrect for OXY** |
| `PROBE_DOSE_MISSING` | `0x04` | `0x04` (set) | DOSE absent ✓ |
| `PROBE_SANOSIL_MISSING` | `0x08` | `0x00` (not set) | SANOSIL **present** ✓ (= OXY Pure probe) |

**Bug**: the current `_configuration()` logic would add `AsekoProbeType.CLF` for OXY because
`PROBE_CLF_MISSING` bit is `0`. This is wrong — OXY has no CLF probe. See §CLF/REDOX analysis.

**Fix**: for `AsekoDeviceType.OXY`, hard-code probe set to `{PH, SANOSIL}`. If future OXY
variants with an optional CLF/REDOX probe are observed, revisit with captured frames.

**Recommended constant**: `UNIT_TYPE_OXY = 0x05` (exact match — no overlap with existing types).

---

## byte[29] – Actuator Bitmask

| Frame | byte[29] | Binary | Bits set |
|---|---|---|---|
| Normal (all frames except 19:33:52) | `0x08` | `0000 1000` | bit 3 only |
| Flocculant pump running (19:33:52) | `0x28` | `0010 1000` | bit 3 + bit 5 |

`0x28 XOR 0x08 = 0x20` — **bit 5 (`0x20`) = flocculant pump** confirmed.

**Only byte[29] changed** in the floc frame (besides timestamp second and checksums).
Every other byte across all 110 non-timestamp/non-checksum positions is identical.

### Confirmed masks for OXY

**Updated 2026-04-12** — Winnetoux log `oxy_2026-04-12.log` confirms pH− mask and reveals parallel pump operation.

| Bit | Mask | byte[29] observed | Status | Evidence |
|---|---|---|---|---|
| 3 | `0x08` | `0x08` | Filtration running | Set in all frames; filtration runs 24h ✓ |
| 4 | `0x10` | `0x18 = 0x08|0x10` | **Algicide pump** ✓ | 2026-04-11 log: toggles exactly at algicide pump on/off |
| 5 | `0x20` | `0x28 = 0x08|0x20` | Flocculant pump ✓ | 2026-04-02 log: toggles exactly at floc dosing event |
| 6 | `0x40` | `0x48 = 0x08|0x40` | **OXY Pure pump** ✓ | 2026-04-11 log: toggles exactly at OXY pump on/off |
| 7 | `0x80` | `0x88 = 0x08|0x80` | **pH− pump** ✓ | 2026-04-12 log: byte[29] 0x08→0x88 at pH− pump on |

### Pumps can run in parallel

The 2026-04-12 log contains frames with `byte[29] = 0xa8 = 0x08|0x20|0x80` — filtration, flocculant pump
and pH− pump all active simultaneously. This occurred at 11:37:58 (matching the Aseko cloud timeline:
pH− 1m24s + Floc+c 2s overlapping).

All bits in byte[29] are independent and additive. Any combination is valid.

---

## byte[37] = 0x03 – Third-Pump Config

`0x03 = 0b00000011`

On SALT devices, byte[37] bit 7 (`0x80`) routes the third pump slot to algicide or flocculant.
On OXY, `0x03` has neither `0x80` nor `0x10` set — the SALT routing logic does **not** apply.

**Status**: unchanged across all captured OXY frames (2026-04-02 and 2026-04-11). The value
`0x03` = both pump modules present is a stable presence bitmap, not a routing indicator.

**Hypothesis** (not confirmed with asymmetric frame):
- bit 0 (`0x01`): flocculant pump module connected
- bit 1 (`0x02`): algicide pump module connected
→ `0x03` = both present (consistent with Winnetoux's device showing 4 pumps).

**Implementation**: for `AsekoDeviceType.OXY`, do not apply the `ALGICIDE_CONFIGURED` byte[37]
routing. Both flowrate_algicide and flowrate_floc are read from their own dedicated bytes.

---

## CLF/REDOX Sentinel Analysis

`bytes[16:18] = bytes[18:20] = 0x001E = 30` — **invariant across all 7 captured frames**.

| Slot | Raw value | Decoded | Assessment |
|---|---|---|---|
| `[16:18]` CLF | `0x001E` | 0.30 mg/L | Never changes — **placeholder**, no CLF probe |
| `[18:20]` REDOX | `0x001E` | 30 mV | Physically impossible (real pool ORP ≥ ~100 mV) — **placeholder** |
| `[20:22]` | `0xFD9D` | −611 mV (signed) | Implausible — **placeholder** |

**Conclusion**: `0x001E` is the OXY firmware's sentinel value for disconnected analogue probe
slots. The values never fluctuate, confirming they are not real measurements.

**Note on the existing REDOX fallback**: the decoder has a fallback
(`if data[18] == 0xFF and data[19] == 0xFF → use [16:18] for REDOX`) — this does **not**
trigger for OXY because `0x1E ≠ 0xFF`. Without an OXY-type guard, a decoded device
would show REDOX = 30 mV (wrong) and CLF = 0.30 mg/L (wrong).

**Fix**: when `device_type == AsekoDeviceType.OXY`, skip `_fill_redox_data()` and
`_fill_clf_data()` entirely.

---

## Flowrate Confirmation – byte[101] = 10 ml/min

The Aseko cloud (Verlauf, 2.4.2026) shows Floc+c dosing **every ~20 minutes, 2 seconds each,
over 24 hours**:

```
24h × 3 pulses/h × 2 s = 144 s total dosing time
Consumed: 0.02 L = 20 ml
Rate: 20 ml ÷ 144 s ≈ 0.14 ml/s = 8.3 ml/min ≈ 10 ml/min
```

**Confirmed**: byte[101] = `0x0A` = 10 → **10 ml/min** (Floc pump hardware flow rate).

The Aseko UI label "Flockungsmittel: 10 ml/Stunde" refers to the configured dosing **setpoint**
(target dose per hour of filtration), which is different from the pump's hardware flow rate
stored in byte[101].

All flowrate bytes on OXY use the same unit: **ml/min**.

| Byte | Value | Pump | Flow rate |
|---|---|---|---|
| `[95]` | 60 | pH− | 60 ml/min ✓ |
| `[97]` | 60 | pH+ (position unconfirmed) | 60 ml/min |
| `[99]` | 60 | OXY Pure | 60 ml/min ✓ |
| `[101]` | 10 | Flocculant | 10 ml/min ✓ |
| `[103]` | 60 | Algicide | 60 ml/min ✓ confirmed 2026-04-11 |

---

## Issue: `raise ValueError` Closes the TCP Connection

**Current flow in `aseko_server.py`:**

```
Frame received
  → _call_forward_cb()      ← cloud forwarding already happens HERE
  → AsekoDecoder.decode()
      → _unit_type()
          → raise ValueError("Unknown unit type: 5")
  → except ValueError → break   ← connection is closed
  → new TCP connect on next frame (~10 s)
```

The frame **is forwarded to the cloud** already. But the `raise` → `break` closes the
connection, forcing a new TCP handshake every 10 seconds. This prevents users with unknown
device types from collecting a stable log while also forwarding data to the cloud.

**Fix**: Change `_unit_type()` to `return None` (keep the WARNING log) instead of
`raise ValueError`. The `decode()` method already handles `unit_type=None` gracefully
(`_fill_consumable_data` returns early when `masks is None`).

## byte[4] – Probe Configuration Changes the Perceived Device Type

**Critical finding from AquaNET log (7.4.2026 13:15–13:16):** The same physical device
(serial 110200612) sent two different `byte[4]` values within 70 seconds, after switching
probe mode in the Aseko cloud:

| Time | byte[4] | Device type decoded | Mode |
|---|---|---|---|
| 13:15:00 | `0x0b = 0b00001011` | HOME | ml/m³/h DOSE mode (CLF probe disabled) |
| 13:16:10 | `0x09 = 0b00001001` | NET | CLF probe active |

**byte[4] XOR: `0x0b XOR 0x09 = 0x02`** — exactly `PROBE_CLF_MISSING` bit toggled.

byte[4] is a **live probe-configuration bitmap**, not a permanent hardware identifier.
The same physical device decodes as different HA types depending only on what the user
configured in the Aseko app.

| byte[4] bit | Mask | Clear (0) = | Set (1) = |
|---|---|---|---|
| 0 | `0x01` | REDOX probe present | REDOX absent |
| 1 | `0x02` | CLF / SANOSIL probe present | CLF absent |
| 2 | `0x04` | DOSE mode active (volume dosing) | DOSE mode inactive |
| 3 | `0x08` | SANOSIL / OXY Pure probe | SANOSIL absent |

---

## How the Aseko Cloud Identifies Hardware Models

The Aseko cloud lists show the correct hardware name ("ASIN AQUA Oxygen", "ASIN AQUA Net")
regardless of probe configuration. This is **not derived from byte[4]** in the 120-byte frame.

**The Aseko cloud uses server-side registration data**: when a device is paired to an account,
its serial number is permanently associated with its hardware model. The cloud does not need
to re-detect the device type from every frame.

**Consequence for the local integration**: there is no byte in the 120-byte frame that
reliably encodes the underlying hardware model independently of probe configuration.
The frame only tells us which probes are configured, not which hardware box is sending.

### Known ambiguity: NET in DOSE mode decodes as HOME

| byte[4] | Actual hardware | Decoded as | Why |
|---|---|---|---|
| `0x09` | NET (CLF active) | NET ✓ | `bool(0x09 & 0x08)` → NET |
| `0x0b` | NET (DOSE mode) | **HOME** ✗ | `0x0b & 0x03 == 0x03` → HOME match first |
| `0x05` | OXY | **ValueError** ✗ | no check matches (existing bug) |

The NET-in-DOSE-mode → HOME misclassification is an **existing bug**, not introduced by
OXY work. It is out of scope for the current PR but should be filed as a separate issue.

### Why OXY detection by byte[4] == 0x05 is reliable

`0x05 = 0b00000101` is the **only known value** that produces all of:
- SANOSIL present (`0x05 & 0x08 = 0`) — identifies the OXY Pure probe hardware
- DOSE absent (`0x05 & 0x04 = 4`) — OXY always uses concentration-based control
- REDOX absent (`0x05 & 0x01 = 1`) — no REDOX probe on base OXY model
- None of the existing type checks match

Across all 100+ captured OXY frames from 2.4.2026 this value never changed. A NET or HOME
device with SANOSIL probe would produce a different byte[4] because they have SANOSIL_MISSING
bit set (`0x08`) differently structured with the HOME/NET bits in the lower nibble.

### Long-term solution

A user-configurable "device type override" per serial number in the HA config entry would
eliminate all ambiguity. This is a future enhancement (not v1.4.0 scope).

---

## byte[53] – Required OXY Dosage (not CLF/REDOX on OXY devices)

On standard devices, byte[53] encodes the setpoint for whichever probe/mode is active.
**byte[53] is the universal "required disinfection setpoint" slot**, interpretation depends on
active probe:

| Active probe / mode | `AsekoProbeType` | byte[53] interpretation | Scaling | Confirmed |
|---|---|---|---|---|
| CLF probe | `CLF` | required_cl_free | ÷10 → mg/L | ✓ `0x02` → 0.20 mg/L (13:16:10 log) |
| REDOX probe | `REDOX` | required_redox | ×10 → mV | ✓ existing |
| OXY / H₂O₂ (SANOSIL) probe | `SANOSIL` | required OXY dosage | raw → ml/m³/d | ✓ `0x08` → 8 ml/m³/d → changed to 12 (log 6.4.) |
| Volume dosing mode | `DOSE` | required dosing rate | raw → ml/m³/h | ✓ `0x05` → 5 ml/m³/h (13:15:00 log) |

**SANOSIL ≠ DOSE**: They are separate concepts:
- `SANOSIL` = H₂O₂/OXY Pure is the **primary disinfection method**, using byte[53] for its dosage setpoint in **ml/m³/d**. The OXY device has no CLF/REDOX probe; the SANOSIL probe occupies that sensor slot.
- `DOSE` = generic **volume dosing mode** that replaces direct probe measurement with timed dosing, uses byte[53] in **ml/m³/h**. When DOSE is active, the CLF bit (0x02) is set in byte[4] (CLF "absent"), which shifts the device from NET → HOME detection.

**Insight from DOSE mode frames (13:15:00):** When the AquaNET is in ml/m³/h mode, byte[16:18] = `0x006a` = **1.06 mg/L** — a real fluctuating value from the CLF hardware, even though the *mode* is "volume dosing". The probe is still physically connected and measuring; only the setpoint/control logic changes. This is different from OXY where `byte[16:18] = 0x001E` (invariant placeholder — no CLF probe hardware present).

**Verification (log 2.4.2026 vs. UI 6.4.2026):**

- Frame byte[53] = `0x08` = **8** → OXY required dosage = 8 ml/m³/d (recorded 2.4.2026)
- Aseko cloud shows change on **6.4.2026 11:36:33**: "Dosierungsmenge 8 ml/m³/d → 12 ml/m³/d"
- Current UI status: **OXY 12 ml/m³/d** ✓

This means: the SANOSIL probe occupies the same sensor slot as CLF/REDOX, and byte[53] is
reused for its required dosage setpoint. No scaling is needed — the raw integer value is the
ml/m³/d target.

**Implementation impact:**
- OXY needs a new `AsekoDevice` field: `required_sanosil: int | None` (ml/m³/d)
- In `decode()`: when `AsekoDeviceType.OXY`, read `required_sanosil = data[53]` instead of `required_redox`/`required_cl_free`
- Alternatively, `required_cl_free` could be repurposed (no CLF probe present anyway), but a dedicated field is cleaner for HA entity naming

---



| Question | Status |
|---|---|
| Algicide mask in byte[29]? | ✅ **0x10** – confirmed 2026-04-11 (Winnetoux log) |
| OXY Pure mask in byte[29]? | ✅ **0x40** – confirmed 2026-04-11 (Winnetoux log) |
| pH− mask in byte[29]? | ✅ **0x80** – confirmed 2026-04-12 (Winnetoux log) |
| Pumps can run in parallel? | ✅ **Yes** – 2026-04-12: `0xa8 = 0x08|0x20|0x80` (floc + pH− simultaneously) |
| byte[103] = algicide flowrate? | ✅ **Confirmed** – 60 ml/min, stable across both sessions |
| byte[54] = required_floc (10 ml/h)? | ✅ **Confirmed** – 2026-04-11: value=10, matches Aseko UI |
| byte[72] = required_algicide (15 ml/m³/d)? | ✅ **Confirmed** – 2026-04-11: value=15, matches Aseko UI |
| OXY with CLF or REDOX probe possible? | ⏳ Awaiting frame from OXY with optional CLF/REDOX installed |

---

## Implementation Plan

### Branch strategy: single branch (`feat/pump-monitoring-consumption`) → v1.4.0

No second branch needed. Unconfirmed pump masks default to `0x00` (no false positives).
v1.5.0 will confirm remaining byte[29] bits once more frames are available.

### Changes per file

#### `const.py`
- Add `UNIT_TYPE_OXY = 0x05`

#### `aseko_data.py`
- ✅ `AsekoDeviceType.OXY = "ASIN AQUA Oxygen"` in enum
- ✅ `ACTUATOR_MASKS[AsekoDeviceType.OXY]` — all confirmed values set:
  ```python
  AsekoDeviceType.OXY: AsekoActuatorMasks(
      filtration=0x08,  # confirmed ✓
      algicide=0x10,    # confirmed ✓ 2026-04-11
      flocculant=0x20,  # confirmed ✓
      oxy=0x40,         # confirmed ✓ 2026-04-11
      ph_minus=0x80,    # confirmed ✓ 2026-04-12
  )
  ```

#### `aseko_decoder.py`
1. ✅ `_unit_type()`: returns `None` instead of raising (keep WARNING log)
2. ✅ `_unit_type()`: `if data[4] == UNIT_TYPE_OXY: return AsekoDeviceType.OXY`
3. ✅ `_configuration()`: returns `{PH, OXY}` directly for `AsekoDeviceType.OXY`
4. ✅ `decode()`: skips `_fill_clf_data()` / `_fill_redox_data()` for OXY
5. ✅ `_fill_required_data()`: OXY path reads `required_floc = byte[54]`, `required_algicide = byte[72]`
6. ✅ `_fill_flowrate_data()`: OXY path reads `flowrate_oxy = byte[99]`, `flowrate_floc = byte[101]`, `flowrate_algicide = byte[103]`
7. ✅ `_fill_consumable_data()`: OXY masks now sufficient — `algicide_pump_running` and `oxy_pump_running` set correctly

#### `tests/test_aseko_decoder.py`
- ✅ OXY normal frame test (byte[29]=0x08)
- ✅ OXY floc-running frame test (byte[29]=0x28)
- ✅ OXY pH− pump test (byte[29]=0x88) — confirmed 2026-04-12
- ⏳ Add test for algicide pump (byte[29]=0x18) — new frame confirmed 2026-04-11
- ⏳ Add test for OXY pump (byte[29]=0x48) — new frame confirmed 2026-04-11
