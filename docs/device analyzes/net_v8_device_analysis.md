# ASIN AQUA NET (v8) — Device Analysis

[Documentation](../README.md) / [Device analyses](README.md)

> **Status:** core readings confirmed against the Aseko Live app from two frames of one unit (Sep 2025, Apr 2026); pump outputs and most `areqs`/`reqs`/`fncs`/`mods`/`flags` slots still unknown.
> **Profile:** [`profiles/v8/net.py`](../../custom_components/aseko_local/decoding/profiles/v8/net.py) (Salt NET: [`profiles/v8/salt.py`](../../custom_components/aseko_local/decoding/profiles/v8/salt.py)) · **Support:** [support matrix](../support_matrix.md)
> **Evidence words** (`confirmed`, `confirmed on X`, `observed`, `assumed`, `not located`): see [evidence rules](../evidence-rules.md).

## 1. Device

| Field | Value |
|---|---|
| Model | ASIN AQUA NET |
| Firmware | 8.x (text frame, port 51050) |
| Identification | v8 header type field: 8xx = NET (804, 805, 812 — 812 came with firmware 8.12, PR #119); 1xx = ASIN AQUA Salt NET (105) |
| Sources | Two production frames of one unit (2025-09-16, 2026-04-13) from Issue #49, compared with the Aseko Live app |
| Decoded by | `decoding.decode()` with the profile in `decoding/profiles/v8/net.py` |

The header type reads like the firmware version of a product line. The firmware
version does not select a layout; only the line picks the model (see
`decoding/profiles/v8/__init__.py`). An unmatched header type falls back to the
unknown profile, which creates no entities.

**Salt NET (header 1xx):** takes over the NET layout unverified, minus the
chlorine pump and chlorine flow rate (a SALT makes chlorine by electrolysis; the
Aseko Live app gives Salt units a pH- and an algicide canister and an electrode,
no chlorine canister). Every SALT reading is `assumed` except the serial number
(`confirmed`, header token 2 on every captured frame).

## 2. Frame structure

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

- Starts with `{v1`, which distinguishes it from binary frames.
- Terminated with `}\n`; the `\n` must be forwarded to Aseko Cloud (line-based protocol).
- Observed size: ~463 bytes in these frames; the length varies, the frame ends at its newline.
- Sentinel `-500` = probe absent or measurement unavailable → decoded as `None`.

### Representative frames

> The frames below are **illustrative excerpts**: some sections are shortened with `...`, and
> the serial numbers may have been anonymised when they were shared (the two frames carry
> different serials although they were described as one unit). They are not replay fixtures;
> the complete frames used by the tests are in `tests/test_decode_v8.py`.

**2025-09-16, 22:27 CEST** (Issue #49 comment):
```
{v1 110999999 804 0 27 ins: 314 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 24 6 29 22 27 0
ains: 708 708 774 7790 0 0 779 779 0 0 0 0 0 0 0 0
outs: 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
areqs: 74 73 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0
reqs: 0 0 0 0 0 0 0 24 0 1 0 0 ... fncs: 0 0 3 0 0 0 2 0
mods: 2 0 0 1 0 0 0 0 flags: 2 0 0 0 0 0 0 0 crc16: C3C8}
```

**2026-04-13, 12:27 CEST** (Issue #49 comments, compared with the Aseko Live app):
```
{v1 110203680 804 0 27 ins: 180 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 25 1 24 12 27 0
ains: 649 649 804 8090 0 0 809 809 0 0 0 0 0 0 0 0
outs: 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
areqs: 74 74 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0
... crc16: C3C8}
```

## 3. Byte map

Positions are section indices (`section[n]`); values quoted as Sep / Apr.

### Header

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| `v1` | protocol version identifier | literal | confirmed | |
| header[0] (token 2) | `serial_number` | integer | confirmed | 110203680 |
| header[1] | header type (product line + firmware version) | 8xx NET, 1xx SALT | observed | 804 / 804; picks the profile |
| header[2] | unknown | — | observed | always 0 |
| header[3] | unknown | — | observed | always 27 |

### `ins` — instantaneous sensor values

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| `ins[0]` | `water_temperature` | ÷ 10 → °C | confirmed | 314 / 180 |
| `ins[1–3]` | — | `-500` → `None` | confirmed | absent probes |
| `ins[8]` | `water_flow_to_probes` | bool | confirmed | 1 / 1 |
| `ins[9–11]` | — | `-500` | observed | |
| `ins[13]` | unit calendar year + 2000 | not read | observed | 24 / 25 |
| `ins[14]` | unit calendar month | not read | observed | 6 / 1 |
| `ins[15]` | unit calendar day | not read | observed | 29 / 24 |
| `ins[16]` | `timestamp` hour | local hour | confirmed | 22 / 12; matches HA log timestamps |
| `ins[17]` | `timestamp` minute | local minute | confirmed | 27 / 27; date is taken from HA |

`ins[13-15]` is a date that runs correctly but is set wrong: both frames of
this unit are **444 days** behind the moment they were captured (2024-06-29
on 2025-09-16, 2025-01-24 on 2026-04-13), 209 days apart. Salt NET units are
730 and 736 days behind (see [SALT NET v8](salt_net_v8_device_analysis.md)).
The date is therefore taken from Home Assistant on every v8 model.

### `ains` — analog inputs (probe measurements)

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| `ains[0]` | `ph` | ÷ 100 | confirmed | 708 / 649; `!= -500` → pH probe present (`configuration`, confirmed) |
| `ains[1]` | — | ÷ 100 | observed | 708 / 649; probable duplicate of `ains[0]` |
| `ains[2]` | unknown | — | observed | 774 / 804; ~5 below `ains[6]` but not exactly |
| `ains[3]` | — | ÷ 10 → mV | observed | 7790 / 8090; = `ains[6] × 10`, not used |
| `ains[4–5]` | — | — | observed | always 0 |
| `ains[6]` | `redox` | direct mV | confirmed | 779 / 809; `!= -500` → REDOX probe present (`configuration`, confirmed) |
| `ains[7]` | — | — | observed | 779 / 809; identical to `ains[6]` |

### `outs` — output states

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| `outs[0]` | unknown | bool | observed | 0 / 0; once a dosing-pump candidate |
| `outs[1]` | unknown | bool | observed | 0 / 0; once a dosing-pump candidate |
| `outs[2]` | `filtration_relay` (→ `filtration_running`) | bool | confirmed | 1 / 1 |
| `outs[8]` | `ph_minus_pump_running` | bool | assumed | 0 / 0; no frame shows a pump running |
| `outs[9]` | `chlorine_pump_running` | bool | assumed | 0 / 0; no frame shows a pump running |

### `areqs` — setpoints

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| `areqs[0]` | `ph_target` | ÷ 10 | confirmed | 74 / 74 |
| `areqs[1]` | `redox_target` | × 10 → mV | confirmed | 73 / 74; setpoint likely changed between Sep and Apr |
| `areqs[2]` | unknown | — | observed | 4 / 4 |
| `areqs[3]` | unknown | — | observed | 5 / 5 |
| `areqs[5–6]` | unknown | — | observed | 36 / 36 |
| `areqs[10]` | unknown | — | observed | 6 / 6 |
| `areqs[12]` | unknown | — | observed | 36 / 36 |
| `areqs[14]` | `pool_volume` | m³ | confirmed | 45 / 45 |
| `areqs[16]` | unknown | 0xFF = unspecified | observed | 255 / 255 |
| `areqs[17]` | `startup_delay` | minutes | confirmed | 2 / 2 |
| `areqs[18]` | `dosing_delay` | minutes | confirmed | 2 / 2 |
| `areqs[19]` | unknown | — | observed | 10 / 10 |
| `areqs[21]` | unknown | — | observed | 15 / 15 |

### `reqs`

Mostly zeros; non-zero values are the same in both frames.

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| `reqs[7]` | filtration duration? | hours | assumed | 24; app shows req filtration 24 h (probable) |
| `reqs[9]` | unknown | — | observed | 1 |
| `reqs[33–34]` | unknown | — | observed | 10 |

### `fncs`

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| `fncs[2]` | unknown | — | observed | 3 |
| `fncs[6]` | unknown | — | observed | 2 |

### `mods`

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| `mods[0]` | operating mode? | — | assumed | 2 |
| `mods[3]` | unknown | — | observed | 1 |

### `flags`

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| `flags[0]` | unknown | — | observed | 2 |

### `crc16`

| Byte | Field | Decoding | Evidence | Notes |
|---|---|---|---|---|
| `crc16` | checksum | hex, parsed as an integer | observed | `C3C8` in both frames; not validated — the algorithm is not known |

## 4. Bit fields

Nothing known yet.

## 5. Model-specific behaviour

### Units and flow rates

Delays are transmitted in minutes (profile flag `DELAYS_IN_MINUTES`), not seconds
as on v7. Pump flow rates are not transmitted; the chlorine and pH-minus flow
rates are `assumed` at 60 ml/min so the consumption counters have something to
integrate.

### Probe configuration

A probe counts as installed when its `ains` slot is not `-500`: `ains[0]` → pH,
`ains[6]` → REDOX.

### Timestamp

Only hour and minute are in the frame (`ins[16]`, `ins[17]`). `ins[13–15]`
change between frames and could encode a date, but this is not confirmed, so the
date comes from the Home Assistant clock.

### pH offset against the app

On 2026-04-13 `ains[0]=649` → 6.49 while the app showed 6.56 (0.07 difference):
either the app shows a calibrated/averaged value, or the frame and the app
reading were taken at slightly different moments.

## 6. Ground truth

| Date | Field | Decoded | Unit / app | Result |
|---|---|---|---|---|
| 2025-09-16 | `water_temperature` | 31.4 °C (`ins[0]=314`) | 31.4 °C (app) | match |
| 2025-09-16 | `ph` | 7.08 (`ains[0]=708`) | — | recorded as matching; app value not noted |
| 2026-04-13 | `water_temperature` | 18.0 °C (`ins[0]=180`) | 18.1 °C (app) | match (0.1 °C) |
| 2026-04-13 | `ph` | 6.49 (`ains[0]=649`) | 6.56 (app, later reading) | ≈ 0.07 off |
| 2026-04-13 | `redox` | 809 mV (`ains[6]`) | 848 mV (app, later in the day) | plausible, not simultaneous |
| 2026-04-13 | `filtration_running` | on (`outs[2]=1`) | Pump ON, filtration NONSTOP | match |
| 2026-04-13 | `water_flow_to_probes` | yes (`ins[8]=1`) | Water flow YES; water flow meter ON | match |
| 2026-04-13 | `ph_target` | 7.4 (`areqs[0]=74`) | 7.4 | match |
| 2026-04-13 | `redox_target` | 740 mV (`areqs[1]=74`) | 740 mV | match |
| 2026-04-13 | `pool_volume` | 45 m³ (`areqs[14]`) | 45 m³ | match |
| 2026-04-13 | `startup_delay` | 2 min (`areqs[17]`) | 2 min | match |
| 2026-04-13 | `dosing_delay` | 2 min (`areqs[18]`) | 2 min | match |
| 2026-04-13 | req filtration | 24 (`reqs[7]`) | 24 h | probable, not decoded |
| — | `timestamp` hour/minute | `ins[16]`, `ins[17]` | HA log timestamps | match |

## 7. Settings the frame does not carry

Nothing known yet.

## 8. Open questions

1. What are `ins[13–15]` (date-related?) — more frames on different days.
2. Which `outs` slots are the dosing pumps (`outs[8]`/`outs[9]` as decoded, or `outs[0]`/`outs[1]`)? — a frame captured while a pump is dosing.
3. What is `ains[2]` — slightly below `ains[6]`, not a simple duplicate? — frames with a wider redox range.
4. What do header fields `0` and `27` mean? — constant in all known frames; frames from other units.
5. What are `areqs[2–3]` (`4`, `5`)? — frames before and after changing settings on the unit.
6. What are `areqs[5, 6, 10, 12]` (`36` or `6`)? — same.
7. Is `reqs[7]=24` the filtration hours per day? — a frame after changing the filtration requirement.
8. Should CRC16 be validated? — decision pending.
9. Are there v8 frames from SALT / OXY / HOME devices? Salt NET (header 105) is known by header type only; its layout is unverified — a Salt NET diagnostics dump compared with the app.

## 9. History

- Pump outputs: this analysis once listed `outs[0]` / `outs[1]` as dosing-pump candidates; the decoder reads `outs[8]` (pH-minus) and `outs[9]` (chlorine), both still unconfirmed.
- The header type `804` was once treated as an unknown constant; it is now read as product line + firmware version (812 added with firmware 8.12, PR #119; 105 mapped to Salt NET).
- The `{v1` prefix was detected by the old `_sync_frame()` routine to tell text frames from binary ones.
- Earlier notes mapped fields to `AsekoDevice` directly; decoding now lives in per-feature modules and the v8 profiles.

## 10. References

- Issue #49 — source of both v8 NET frames and the app comparison.
- PR #119 — firmware 8.12 header type 812.
- Profiles: [`v8/net.py`](../../custom_components/aseko_local/decoding/profiles/v8/net.py), [`v8/salt.py`](../../custom_components/aseko_local/decoding/profiles/v8/salt.py), [`v8/__init__.py`](../../custom_components/aseko_local/decoding/profiles/v8/__init__.py)
- Related: [NET (v7) device analysis](net_device_analysis.md), [support matrix](../support_matrix.md), [evidence rules](../evidence-rules.md)
- Tests: `tests/test_decode_v8.py`
