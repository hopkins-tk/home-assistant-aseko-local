# ASIN AQUA Salt NET fw v8 – Reverse Engineering & Field Mapping Notes

## Device

| Field | Value |
|---|---|
| Model | ASIN AQUA Salt NET |
| Firmware | v8.x (text frame, port 51050) |
| Source | Issue #131 (mirovra) — 3 diagnostic dumps + 4 hex-dump snippets + 17 annotated frames (Jul 15–16 2026) |
| Decoded by | `AsekoV8Decoder` in `custom_components/aseko_local/aseko_decoder_v8.py` |
| Sibling docs | [net_v8_device_analysis.md](net_v8_device_analysis.md) (NET v8 reference) · [salt_device_analysis.md](salt_device_analysis.md) (SALT v7 reference) |

---

## 1. What is it

The ASIN AQUA **Salt NET** is a network-connected (Ethernet / Aseko Live) variant of
the SALT product line. It uses the **same v8 text-frame protocol as the NET family**
(recognisable by the `{v1 …` framing and TCP port 51050), but with the salt-water
chlorinator hardware that the SALT products are known for.

Unlike the regular SALT (v7, 120-byte binary frame) which uses `byte[4]` and
sub-frame offsets to encode its type, the Salt NET is identified **purely by
the `header[1]` value** (see §3). The frame body is a strict superset of the
NET v8 body — same section names, more values per section.

### Pump configuration (per @mirovra)

The Salt NET has **two physical dosing pumps**. The configuration captured by
mirovra is:

| Pump | Chemical | Configured as |
|---|---|---|
| Pump 1 | pH− | fixed (no routing) |
| Pump 2 | Algicide **OR** Flocculant | user-configured in the Aseko app, **mutually exclusive** (per mirovra) |

> **Open question (Q5):** the SALT v7 unit has the same hardware (a single
> shared pump port) and uses `byte[37] & 0x80` to route between algicide and
> flocculant. The Salt NET appears to have **two separate, dedicated pump
> ports** (one fixed to pH−, one switchable between algicide and flocculant).
> This is unconfirmed — the only frame set we have is from a unit configured
> for algicide. A flocculant-configured unit would be needed to confirm.

---

## 2. Frame structure (v8 text format)

Identical layout to the NET v8 frame — see
[net_v8_device_analysis.md §Frame Structure](net_v8_device_analysis.md#frame-structure).
The Salt NET frame is a **strict superset** of the NET frame, with:

| Section | NET v8 length | SALT NET length | Delta |
|---|---|---|---|
| `header[1]` (= f2) | 804 / 805 / 812 | **100** | **device-type identifier** |
| `header[3]` (= f4) | 27 | **31** | sub-variant code, SALT-NET specific |
| `ins[]` | 19 | 19 | identical |
| `ains[]` | 8 | **16** | +8 SALT-specific slots |
| `outs[]` | 19 | 19 | identical layout, but `outs[2]` semantics differ (1 vs 2 for "on") |
| `areqs[]` | 22 | **26** | +4 SALT-specific setpoints |
| `reqs[]` | 54 | 60 | +6 SALT-specific fields |
| `flags[]` | 8 | 8 | identical, but `flags[3]` is meaningful on SALT NET |
| `fncs[]` / `mods[]` | 8 each | 8 each | identical |
| `crc16` | `C3C8` | varies (6142 / 02F6 / E55D) | CRC validation not yet implemented |

> **Reference frames** used for the byte-level mapping in §3–§5 are
> captured as constants in [`tests/test_aseko_decoder_v8.py`](../../tests/test_aseko_decoder_v8.py)
> (`SALT_NET_FRAME_F1` … `SALT_NET_FRAME_F5`). Additional annotated frames
> from Jul 15–16 2026 are in the [issue thread](https://github.com/hopkins-tk/home-assistant-aseko-local/issues/131#issuecomment-4989900121).
>
> | Frame | Source | State |
> |---|---|---|
> | F1 | mirovra Jul 5 diagnostic | Filtration ON, flow YES, electrolyzer OFF |
> | F2 | mirovra Jul 6 diagnostic | Filtration OFF, no flow, alarm active |
> | F3 | mirovra Jul 16 07:58:59 | Filtration ON, algicide ON, electrolyzer RIGHT 19 g/h |
> | F4 | mirovra Jul 16 08:13:09 | Filtration ON, no dosing, electrolyzer LEFT 20 g/h |
> | F5 | mirovra Jul 16 09:27:09 | Filtration ON, no dosing, electrolyzer OFF |

---

## 3. Header

| Position | F1 | F2 | F3 | Meaning | Status |
|---|---|---|---|---|---|
| `v1` | — | — | — | Protocol version identifier | ✅ confirmed |
| `header[0]` | `110215844` | `110215844` | `110215844` | `serial_number` | ✅ confirmed |
| `header[1]` (f2) | `100` | `100` | `100` | **SALT NET device-type identifier** | ✅ confirmed (3 frames) |
| `header[2]` (f3) | `0` | `0` | `0` | unknown — always 0 | ❓ |
| `header[3]` (f4) | `31` | `31` | `31` | sub-variant code (NET v8 uses 27) | ✅ constant in all 3 captured frames |

`header[1] == 100` is the device-type discriminator. The decoder maps it to
`AsekoDeviceType.SALT_NET`. Before this fix the value was unknown and the
device fell back to `AsekoDeviceType.NET`, which caused the
"Unknown V8 header type 100" log spam (7857+ occurrences in mirovra's log
between 2026-07-04 22:01 and 2026-07-05 19:16).

---

## 4. `ins:` section — instantaneous sensor values

| index | F1 | F2 | F3 | Formula | `AsekoDevice` field | Confirmed by |
|---|---|---|---|---|---|---|
| `ins[0]` | 323 | 290 | 319 | ÷ 10 → °C | `water_temperature` | ✅ 32.3 / 29.0 / 31.9 °C matches app |
| `ins[1–3]` | -500 | -500 | -500 | — | `None` | ✅ absent probes |
| `ins[8]` | 1 | 0 | 1 | `bool` | `water_flow_to_probes` | ✅ matches app ("Water flow: YES / NO") |
| `ins[12]` | 0 | **256** | 0 | bit 0x08 set ⇒ alarm | `alarm_no_flow_to_probes` | ✅ **only set in F2 (no-flow frame)** — see §10 |
| `ins[13–14]` | 24 6 | 24 6 | 24 6 | day/month | not decoded (uses HA clock) | 🟡 probable date-related, unconfirmed |
| `ins[15]` | 29 | 30 | 30 | day-of-month | not decoded (uses HA clock) | 🟡 drift between frames, plausible |
| `ins[16]` | 10 | 21 | 16 | local hour | `timestamp.hour` | ✅ matches diagnostic timestamps |
| `ins[17]` | 28 | 49 | 48 | local minute | `timestamp.minute` | ✅ matches diagnostic timestamps |

**Note on `ins[12]`:** the value 256 (= 0x100) is the no-flow alarm bit. It is
**only** set when the flow is interrupted. The integration already had a
no-flow alarm at byte `[13] bit 0x04` for v7 frames; on the SALT NET v8 this
is a different field (the alarm is at `ins[12]` bit 0x08 = 0x100, not at the
v7 byte 13 position). See §10 for the dual-encoding.

---

## 5. `ains:` section — analog inputs (probe measurements + salt-specific)

| index | F1 | F2 | F3 (alg ON) | F4 (LEFT) | F5 (OFF) | Formula | `AsekoDevice` field | Confirmed by |
|---|---|---|---|---|---|---|---|---|
| `ains[0]` | 752 | 733 | 734 | 738 | 741 | ÷ 100 → pH | `ph` | ✅ matches app |
| `ains[1]` | 752 | 733 | 734 | 738 | 741 | duplicate of pH | — | always tracks `ains[0]` |
| `ains[2]` | 716 | 673 | 575 | 579 | 716 | unknown | unknown | ❓ tracks ains[6] but offset varies |
| `ains[3]` | 7210 | 6780 | 5800 | 5840 | 7210 | ÷ 10 → mV (= `ains[6] × 10`) | — | = `ains[6] × 10`; not used |
| `ains[4–5]` | 0 | 0 | 0 | 0 | 0 | — | — | always 0 |
| `ains[6]` | 721 | 678 | 580 | 584 | 721 | direct mV | `redox` | ✅ matches app |
| `ains[7]` | 721 | 678 | 580 | 584 | 721 | duplicate of redox | — | always tracks `ains[6]` |
| `ains[8]` | **49** | **48** | **53** | **51** | **49** | ÷ 10 → **g/L (salinity)** | `salinity` | ✅ **4.9 / 4.8 / 5.3 / 5.1 / 4.9 g/L** |
| `ains[9]` | 0 | 0 | **19** | **20** | 0 | raw g/h (matches app) | **`electrolyzer_power`** | ✅ **0 / 0 / 19 / 20 / 0 g/h** — see §11 |
| `ains[10]` | 401 | 336 | 346 | 407 | 488 | **unknown — NOT electrolyzer power** | reserved | ❓ does not match app display (was previous `electrolyzer_power` — see §11) |
| `ains[11–15]` | 0 | 0 | 0 | 0 | 0 | — | — | always 0 / reserved |

**`ains[8]` (salinity)**: always populated in all frames, 4.5–5.5 g/L is the
typical operating range for a salt-chlorinator cell.

**`ains[9]` (electrolyzer power — CORRECTED)**: this slot directly matches
the app's chlorine production display (g/h). Zero when the cell is off,
non-zero when producing. **`ains[10]` was previously thought to encode
electrolyzer power**, but mirovra's Jul 16 data proved the mapping was wrong:
- App shows 19 g/h ↔ `ains[9]=19`, `ains[10]=346` (would give 34.6 with old ÷10)
- App shows 20 g/h ↔ `ains[9]=20`, `ains[10]=407` (would give 40.7 with old ÷10)
- Factor is not consistent (ranges 17–26×), so `ains[10]` is something else
  (possibly power consumption in W or raw ADC). Left unmapped for now.

**`electrolyzer_active` / `electrolyzer_direction`** are derived from
`outs[14]` — see §6.

---

## 6. `outs:` section — output states (pumps + filtration)

| index | F1 | F2 | F3 (alg ON) | F4 (LEFT) | F5 (OFF) | Formula | `AsekoDevice` field | Confirmed by |
|---|---|---|---|---|---|---|---|---|
| `outs[0]` | 0 | 0 | 0 | 0 | 0 | bool | `cl_pump_running` | ❓ always 0 (no CL pump on SALT NET) |
| `outs[1]` | 0 | 0 | 0 | 0 | 0 | bool | `ph_plus_pump_running` | ❓ always 0 (no pH+ on SALT NET) |
| `outs[2]` | **2** | 0 | **2** | **2** | **2** | `bool` (any non-zero ⇒ ON) | `filtration_pump_running` | ✅ **2=ON, 0=OFF** |
| `outs[3–7]` | 0 | 0 | 0 | 0 | 0 | — | — | unused in all frames |
| `outs[8]` | 0 | 0 | 0 | 0 | 0 | bool | `ph_minus_pump_running` | ❓ always 0 (no pH− dosing in these frames) |
| `outs[9]` | 0 | 0 | 0 | 0 | 0 | bool | `cl_pump_running` | ✅ always 0 (fncs[2]=1 → CL structurally absent) |
| `outs[10]` | 0 | 0 | 0 | 0 | 0 | — | — | unused |
| `outs[11]` | 0 | 0 | **1** | 0 | 0 | `bool` | **`algicide_pump_running`** | ✅ **CORRECTED: 1=ON** (was previously mapped to outs[15]) |
| `outs[12–13]` | 0 | 0 | 0 | 0 | 0 | — | — | unused |
| `outs[14]` | 0 | 0 | **2** | **3** | 0 | **NEW: 2=RIGHT, 3=LEFT, 0=OFF** | **`electrolyzer_direction`** + `electrolyzer_active` | ✅ confirmed mirovra Jul 16 |
| `outs[15–18]` | 0 | 0 | 0 | 0 | 0 | — | — | unused |

**Key updates from mirovra's Jul 16 data:**

1. **`outs[11]` = algicide pump running** (CORRECTED from previous
   `outs[15]`). Confirmed: `outs[11]=1` when algicide dosing active,
   `outs[11]=0` when off.

2. **`outs[14]` = electrolyzer direction**. Previously unmapped:
   - `0` = off (electrolyzer inactive)
   - `2` = right direction
   - `3` = left direction
   
   The decoder derives `electrolyzer_active = (outs[14] != 0)`,
   `electrolyzer_direction = RIGHT(2) / LEFT(3) / None(0)`.

3. **`outs[2] == 1` vs `2`**: NET v8 uses 1, SALT NET uses 2.
   `bool(outs2)` handles both.

4. **`fncs[2]` gate**: Since SALT NET has `fncs[2]=1`, `cl_pump_running`
   is always `None` (structurally absent), not `False`.

---

## 7. `areqs:` section — application requirements / setpoints

| index | F1 | F2 | F3 | Formula | `AsekoDevice` field | Confirmed by |
|---|---|---|---|---|---|---|
| `areqs[0]` | 74 | 74 | 74 | ÷ 10 → pH | `required_ph` | ✅ 7.4 matches app |
| `areqs[1]` | 72 | 72 | 72 | × 10 → mV | `required_redox` | ✅ 720 mV matches app |
| `areqs[2]` | 4 | 4 | 4 | unknown | unknown | ❓ constant 4 (matches NET v8) |
| `areqs[3]` | 0 | 0 | 0 | unknown | unknown | ❓ NET had 5, SALT NET has 0 |
| `areqs[4]` | 5 | 5 | 5 | unknown | unknown | ❓ NET had 0, SALT NET has 5 (swap with areqs[3]) |
| `areqs[5–6]` | 33 | 33 | 33 | unknown | unknown | ❓ three values of 33 — possibly a trio of related thresholds |
| `areqs[10]` | 33 | 33 | 33 | unknown | unknown | ❓ |
| `areqs[12]` | 33 | 33 | 33 | unknown | unknown | ❓ |
| `areqs[14]` | 55 | 55 | 55 | m³ | `pool_volume` | ✅ 55 m³ matches app |
| `areqs[15]` | 255 | 255 | 255 | = UNSPECIFIED | — | unused (SALT NET) |
| `areqs[16]` | 255 | 255 | 255 | = UNSPECIFIED | — | unused (SALT NET) |
| `areqs[17]` | 5 | 5 | 5 | minutes (× 60 → s) | `delay_after_startup` | ✅ 5 min (NET v8 had 2 min) |
| `areqs[18]` | 5 | 5 | 5 | minutes (× 60 → s) | `delay_after_dose` | ✅ 5 min (NET v8 had 2 min) |
| `areqs[19]` | 10 | 10 | 10 | unknown | unknown | ❓ |
| `areqs[21]` | 15 | 15 | 15 | unknown | unknown | ❓ |
| `areqs[3]` | 0 | 0 | 0 | **NEW: flocculant dose (ml/h)** | `required_floc` | ✅ mirovra Jul 19: areqs[3]=10 when floc, 0 when alg |
| `areqs[4]` | **5** | **5** | **5** | **CORRECTED: algicide dose (ml/m³/day)** | `required_algicide` | ✅ misattributed to areqs[25]; areqs[4]=5 matches app "5 ml/m³/day" |
| `areqs[25]` | 3 | 3 | 3 | **NOT algicide dose (constant 3)** | `<not used>` | ❓ constant across all frames — unknown |

> **Corrected mapping (2026-07-19):** The algicide setpoint is at `areqs[4]`,
> not `areqs[25]`. When pump 2 is changed to flocculant, the flocculant
> setpoint appears at `areqs[3]` and `areqs[4]` resets to 0. The decoder
> reads the appropriate field based on `fncs[6]` (10=algicide→areqs[4],
> 18=flocculant→areqs[3]).
>
> `areqs[25]=3` is constant across all frames (algicide, flocculant, no-flow)
> and is therefore NOT the algicide dose. Its meaning is unknown.

> **Note on `areqs[17]` / `areqs[18]` (delay_after_startup, delay_after_dose):**
> the v8 firmware reports these fields in **MINUTES** (raw `5` = 5 min on
> mirovra's SALT NET, raw `2` = 2 min on the NET v8 reference frames).
> The v7 firmware reports the same fields in **seconds** (e.g. `120` =
> 2 min). To keep the `AsekoDevice.delay_*` field unit-consistent with v7
> and the `UnitOfTime.SECONDS` sensor in
> [`sensor.py`](../../custom_components/aseko_local/sensor.py), the v8
> decoder multiplies by 60. A 5-min v8 delay therefore decodes to
> `delay_after_startup = 300` (s), matching what a v7 user with the same
> delay would see (raw v7 byte 74:75 = `300` = 5 min). See
> [net_v8_device_analysis.md §Frame Structure](net_v8_device_analysis.md#frame-structure)
> for the full v7↔v8 unit-convention note.

---

## 8. `reqs:` section — request / schedule fields

| index | F1 | F2 | F3 | Hypothesis | `AsekoDevice` field | Status |
|---|---|---|---|---|---|---|
| `reqs[5]` | 8 | 8 | 8 | unknown | unknown | ❓ **always 8** — was 0 on NET, possibly a SALT-NET-specific feature flag |
| `reqs[7]` | 20 | 20 | 20 | **filtration hours per day** | `filtration_hours_per_day` | 🟡 20 h vs. NET's 24 h — plausible, unconfirmed by user. **Also drives the `filtration_mode` enum (Issue #133):** when `outs[2] != 0` (filtration on) and `reqs[7] < 24`, the mode is `TIMER_PERIOD_1`; when `reqs[7] == 24` the mode is `NONSTOP_24H`; when `outs[2] == 0` the mode is `OFF_MANUAL`. See §6.2 and the new `AsekoFiltrationMode` enum in [`aseko_data.py`](../../custom_components/aseko_local/aseko_data.py). |
| `reqs[9]` | 2 | 2 | 2 | unknown | unknown | ❓ constant 2 (NET had 1) |
| `reqs[33–34]` | 10 | 10 | 10 | unknown | unknown | ❓ constant 10, identical to NET |

The SALT NET `reqs[]` is 60 values long vs. NET v8's 54. The 6 extra slots
(at positions 54–59, mostly trailing zeros) carry no information in the
captured frames. The leading candidate for the new slots is
`reqs[7] = 20` (filtration hours per day) and `reqs[5] = 8` (feature flag
that is non-zero on SALT NET but zero on NET).

---

## 9. `flags:` / `fncs:` / `mods:` / `crc16:`

| Section | F1 | F2 | F3 | Hypothesis |
|---|---|---|---|---|
| `flags[0]` | 2 | 2 | 2 | constant 2 (same on NET) |
| `flags[3]` | 0 | **1** | 0 | **no-flow alarm flag** (matches `ins[12] = 256`) — see §10 |
| `fncs[]` | `0 0 1 0 0 0 10 0` | (identical) | (identical) | `fncs[2] = 1`, `fncs[6] = 10` (NET v8 had `3` and `2`) — see §11.5 below for the capability-gate interpretation |
| `mods[]` | `2 0 0 1 0 0 0 0` | (identical) | (identical) | `mods[0] = 2` (operating mode?), `mods[3] = 1` (constant) |
| `crc16` | `6142` | `02F6` | `E55D` | CRC validation **not yet implemented** |

---

## 10. No-flow alarm — dual encoding

The SALT NET v8 firmware reports the no-flow alarm in **two** places, both
of which correlate 1:1 in the 3 captured frames:

| Frame | `ins[12]` | `flags[3]` | App state |
|---|---|---|---|
| F1 (flow YES) | 0 | 0 | "Water flow: YES" |
| F2 (flow NO) | **256** | **1** | "Water flow: NO" + no-flow alarm |
| F3 (flow YES) | 0 | 0 | "Water flow: YES" |

The integration can use either:

- `ins[12] & 0x100 != 0` (raw value, single-bit mask 0x100)
- `flags[3] != 0` (boolean)

The decoder implements **`ins[12] & 0x100 != 0`** because the `flags[]`
section is otherwise unused by NET v8. The choice is arbitrary — both
work.

> **Architectural note — v7 and v8 share the same AsekoDevice field:**
> the v7 firmware reports the no-flow alarm at `byte[13] bit 0x04`, the
> v8 firmware at `ins[12] bit 0x100`. The wire formats are completely
> different, but the user-visible semantic ("no water is flowing through
> the probe chamber") is identical. The v7 decoder (binary) and the v8
> decoder (text) both write the **same** `AsekoDevice.alarm_no_flow_to_probes`
> field, and the binary sensor in [`binary_sensor.py`](../../custom_components/aseko_local/binary_sensor.py)
> reads from that single field. The `AsekoDevice` data model is the
> abstraction layer that hides the protocol version from the entity
> layer — the alternative (two fields, two sensors) would force every
> downstream consumer (dashboards, automations, scripts) to care about
> the firmware version.

---

## 11. Corrected field mappings (mirovra Jul 16 resolution)

mirovra's Jul 15–16 annotated frames resolved the previous ambiguities:

### 11.1 `ains[9]` is electrolyzer power, not algicide flow rate

The previous analysis mapped `ains[9]` to `flowrate_algicide` (ml/min × 10)
because F3 happened to have `ains[9]=19` while the app showed the algicide
pump running. With mirovra's comprehensive data set:

| Frame | `ains[9]` | `ains[10]` | App power | App direction | Algicide |
|---|---|---|---|---|---|
| F1 (Jul 5) | 0 | 401 | — | — | OFF |
| F2 (Jul 6) | 0 | 336 | — | — | OFF |
| Jul 16 07:58 (alg ON) | **19** | 346 | 19 g/h | RIGHT | ON |
| Jul 16 08:04 (alg OFF) | **19** | 375 | 19 g/h | RIGHT | OFF |
| Jul 16 08:13 (LEFT) | **20** | 407 | 20 g/h | LEFT | OFF |
| Jul 16 09:27 (OFF) | 0 | 488 | OFF | — | OFF |

**Conclusion:** `ains[9]` tracks the electrolyzer setpoint (g/h, matches
app display). `ains[10]` (previously used for `electrolyzer_power`) does
not match the app — it may be power consumption in W or an ADC value.
`ains[10]` is now unmapped.

### 11.2 `outs[11]` is algicide pump, `outs[15]` was a mis-index

The original F3 frame had a **20-element** `outs[]` array that caused
the algicide bit to appear at index 15. All verified SALT NET frames
have **19-element** `outs[]` arrays. The correct index is `outs[11]`:
- `outs[11] = 1` → algicide pump running (confirmed Jul 16 07:58, alg ON)
- `outs[11] = 0` → algicide pump off

### 11.3 `outs[14]` encodes electrolyzer direction

This slot was previously unmapped. The 3-state encoding is:
- `0` = off
- `2` = RIGHT (confirmed Jul 16, multiple frames)
- `3` = LEFT (confirmed Jul 16 08:13)

The decoder now sets both `electrolyzer_active` and
`electrolyzer_direction` from this field.

### 11.4 No per-pump flow rates on v8

The v8 firmware does not transmit per-pump flow rates (no equivalent of
v7 bytes 95/97/99/101). `flowrate_algicide` therefore stays `None` on v8
(the AsekoDevice default). The consumption tracker uses the
hardcoded `V8_DEFAULT_PUMP_FLOWRATE_ML_MIN = 60` instead.

---

The SALT NET does **not** use `byte[37] & 0x80`
routing (that is a v7 SALT thing — see [salt_device_analysis.md §byte[37]](salt_device_analysis.md#byte37--third-pump-routing-algicide-vs-flocculant)).
On the SALT NET, the algicide pump is a **dedicated physical port** that
the user configures in the app. `byte[37]` is not used for pump routing on
the v8 firmware.

---

## 11.5 Structural capability gate: `fncs[2]` distinguishes "has CL pump" from "no CL pump"

A SALT-family device can never have a chlorine (CL) dosing pump — it has
an electrolyzer cell that produces chlorine from salt. Before the fix, the
v8 decoder would still expose a `cl_pump_running` binary sensor on SALT
NET devices, permanently showing `False` ("off"). That is semantically
wrong: the pump is not just off, it does **not exist**.

The v8 frame carries a one-byte **capability indicator** in the `fncs:`
("functions") section. The two values observed in the wild are:

| Device | `fncs[2]` | `fncs[6]` | Meaning |
|---|---|---|---|---|
| NET v8 (110203680, 110999999) | **3** | 2 | has CL pump module installed |
| SALT NET v8 (110215844) — algicide | **1** | **10** | SALT family: electrolyzer + dedicated algicide port, no CL pump |
| SALT NET v8 (110215844) — flocculant | **1** | **18** | same SALT family, pump 2 configured as flocculant instead |

**The decoder now uses `fncs[2] == 3` as the gate for `has_cl_pump`**:

```python
fncs2 = _get(fncs, 2)             # 3 on NET, 1 on SALT NET, None on frames without fncs:
has_cl_pump = fncs2 == 3          # True only for NET-style devices

if has_cl_pump:
    cl_pump_running = bool(_get(outs, 9))  # read outs[9] only when CL pump exists
else:
    cl_pump_running = None        # pump is structurally absent
```

The same gate is applied to `ph_plus_pump_running`, `floc_pump_running`
and `oxy_pump_running` — none of these pump types are installed on any v8
device captured so far (NET v8 and SALT NET v8). The fields are wired
through so the entity layer (`binary_sensor.py` and `consumption_tracker.py`)
can decide whether to surface them.

**Why `None` and not `False`?** The entity layer (`AsekoConsumptionTracker`
in [`consumption_tracker.py`](../../custom_components/aseko_local/consumption_tracker.py))
already treats `is_on is None` as "pump not present" and silently skips
the entity. Returning `False` ("pump is off") would have surfaced a
permanently-off binary sensor and a permanently-zero consumption counter
on the user's SALT NET — confusing UX.

**Robustness for frames without a `fncs:` section:** if a v8 frame does
not include a `fncs:` section (older firmware, or a hypothetical future
revision), `fncs2` is `None` and `has_cl_pump` defaults to `False`. The
worst case is that a NET device without `fncs:` would not get a CL
sensor — preferable to a SALT device that incorrectly shows a
permanently-False CL sensor. A NET device with a missing `fncs:` section
should be reported as a new bug.

**Caveat — single-bit hypothesis only:** `fncs[2]` could equally well be
a 2-bit or 4-bit field. We have only seen `1` and `3` in the wild. If a
future device returns `0`, `2`, `4`, etc., the gate may need refinement.
A diagnostic log line that records the raw `fncs:` section on the first
encountered header type will help debug this if it ever happens.

---

## 12. Filtration mode (Issue #133 cross-reference)

The SALT NET v8 frame does **not** carry a `byte[37]`-style filtration
mode flag (unlike HOME v7 firmware A/B), so the v8 decoder derives the
`AsekoFiltrationMode` enum from the available signals:

| SALT NET state | Decoder rule | Resulting mode |
|---|---|---|
| Filtration pump off (`outs[2] = 0`) | user switched pump off manually | `OFF_MANUAL` |
| Filtration pump on (`outs[2] != 0`) + `reqs[7] == 24` | schedule is 24 h/day | `NONSTOP_24H` |
| Filtration pump on (`outs[2] != 0`) + `reqs[7] < 24` | schedule is < 24 h/day | `TIMER_PERIOD_1` |
| `reqs[7]` not present | unknown, leave as `None` | `None` |

This matches the **HOME v7 firmware A behaviour** (Issue #133 §6.2 "Old
encoding") which also collapses P1 and P1&P2 into a single "timer" state.
The SALT NET v8 firmware does not expose a second filtration period in
the decoded sections, so we cannot distinguish `TIMER_PERIOD_1` from
`TIMER_PERIOD_1_AND_2` without a frame that includes the second period
(which we have not yet captured for SALT NET v8). The same enum and
sensor (`filtration_mode`) are used for both v7 and v8 devices — the
binary sensor in [`binary_sensor.py`](../../custom_components/aseko_local/binary_sensor.py)
is therefore protocol-agnostic.

For mirovra's SALT NET device, `reqs[7] = 20` and the pump is configured
to run on a daily schedule (not 24 h nonstop), so all three known frames
decode as follows:

| Frame | `outs[2]` | `reqs[7]` | `filtration_mode` |
|---|---|---|---|
| F1 (filtration on) | 2 | 20 | `TIMER_PERIOD_1` |
| F2 (filtration off, no flow) | 0 | 20 | `OFF_MANUAL` |
| F3 (filtration on, algicide on??) | 2 | 20 | `TIMER_PERIOD_1` |

The `AsekoFiltrationMode` enum and the `filtration_mode` field are the
same as the v7 HOME branch uses (Issue #133), so the SALT NET and HOME v7
work shares a single entity, a single translation key, and a single sensor
implementation. This is the architectural goal Issue #133 was designed
for: a single 4-state `filtration_mode` sensor visible on every
filtration-capable device (SALT, HOME, OXY, PROFI, SALT_NET).

---

## 13. Cross-validation with mirovra's hex-dump log snippets

The issue thread contains 4 hex-dump log lines (pH−-pump before / during,
algicide-pump before / during, electrolysis LEFT, electrolysis RIGHT).
Each dump is **truncated to 120 bytes** in the log, which is the **header
+ ins + first 8 ains values**. We can therefore confirm:

| Field | pH− before | pH− during | Algicide before | Algicide during | Conclusion |
|---|---|---|---|---|---|
| `ins[0]` (water temp) | 304 → 30.4 °C | 303 → 30.3 °C | 292 → 29.2 °C | ? | ✅ sensor, drifts |
| `ins[8]` (flow) | 1 | 1 | 1 | ? | ✅ always 1 during dosing |
| `ins[16..17]` (time) | 08:14 | 08:14 | 08:01 | ? | ✅ time matches the log timestamps |
| `ains[0]` (pH) | 741 → 7.41 | 741 → 7.41 | 738 → 7.38 | ? | ✅ stable, pH in dosing range |
| `ains[6]` (redox) | 605 → 605 mV | 605 → 605 mV | 590 → 590 mV | ? | ✅ stable |

The hex dumps do **not** reach `outs[]` or `ains[8..15]`, so they cannot
confirm `outs[14]` / `ains[9]` for the algicide-pump-dosing scenario.
But the header `100 0 31` is confirmed for: idle, filtration running,
algicide dosing, pH− dosing, electrolysis LEFT, electrolysis RIGHT —
which is enough to hard-code the SALT NET header mapping.

---

## 14. App Screenshots (mirovra, 2026-07-05) — Reference Values

| App field | App value | Mapped to |
|---|---|---|
| Status: pH | 7.52 | `ains[0]=752` ÷ 100 = 7.52 ✅ |
| Status: Redox | 721 mV | `ains[6]=721` ✅ |
| Status: Water temp | 32.3 °C | `ins[0]=323` ÷ 10 = 32.3 °C ✅ |
| Status: Pump | ON | `outs[2]=2` (any non-zero) ✅ |
| Status: Filtration | NONSTOP | `outs[2]=2` ✅ |
| Status: Water flow | YES | `ins[8]=1` ✅ |
| Status: Salinity | 4.9 g/L | `ains[8]=49` ÷ 10 = 4.9 g/L ✅ |
| Status: Electrolysis | 40.1 | `ains[10]=401` ÷ 10 = 40.1 (unit g/h or %) ✅ |
| Config: req pH | 7.4 | `areqs[0]=74` ÷ 10 = 7.4 ✅ |
| Config: req Redox | 720 mV | `areqs[1]=72` × 10 = 720 mV ✅ |
| Config: Pool volume | 55 m³ | `areqs[14]=55` ✅ |
| Config: Delay startup | 5 min | `areqs[17]=5` ✅ |
| Config: Delay after dose | 5 min | `areqs[18]=5` ✅ |
| Config: req algicide | 3 ml/m³/day | `areqs[24]=3` ✅ (best guess, see §7) |
| Config: req filtration | 20 h | `reqs[7]=20` 🟡 probable, unconfirmed |

---

## 15. Confirmed `ACTUATOR_MASKS` for SALT_NET

```python
AsekoDeviceType.SALT_NET: AsekoActuatorMasks(
    filtration=0x00,        # SALT NET does not use byte[29] — v8 has no byte[29]
    cl=0x00,                # no CL pump on SALT NET
    ph_minus=0x00,          # pump running is in outs[8] on v8, not in byte[29]
    algicide=0x00,          # algicide pump running is in outs[11] on v8
    flocculant=0x00,        # SALT NET does not use byte[37] routing — v7-only
    oxy=0x00,               # no OXY pump
    electrolyzer_running=0x00,  # electrolyzer power is in ains[10] on v8
    electrolyzer_running_right=0x00,
    electrolyzer_running_left=0x00,
    # SALT NET has two dedicated pump ports, not the SALT v7 shared-port
    # architecture. The user configures Pump 2 in the Aseko app as
    # algicide OR flocculant (mutually exclusive, per mirovra). The
    # decoder does not need to route between them — the SALT-NET v8
    # firmware does the routing internally and exposes the result as
    # outs[11] (algicide_pump_running).
    # byte37_routes_pump_type is irrelevant for v8 because the SALT NET
    # frame does not use byte[37] in the same way as the v7 SALT frame.
    byte37_routes_pump_type=False,
)
```

> **Important:** the `AsekoActuatorMasks` fields (filtration, cl, ph_minus,
> algicide, flocculant, electrolyzer_running) are **all 0x00** for SALT_NET
> because the SALT NET v8 frame does **not** have a `byte[29]` actuator
> bitmask. The v8 frame uses `outs[]` for pump states and `ains[]` for
> electrolyzer power. The `ACTUATOR_MASKS` are therefore used only for the
> `byte37_routes_pump_type` flag, which is `False`.

---

## 16. Open Questions

| # | Question | Status |
|---|---|---|---|
| Q1 | Resolved — see §11 | ✅ |
| Q2 | Is Pump 2 of the SALT NET hard-wired to algicide or switchable to flocculant? | **✅ RESOLVED**: `fncs[6]=10`=algicide, `fncs[6]=18`=flocculant (mirovra Jul 19) |
| Q3 | What is `reqs[5] = 8`? | ❓ always 8 (was 0 on NET) — possibly a SALT-NET feature flag |
| Q4 | What is `reqs[7] = 20`? Filtration hours per day? | 🟡 probable, unconfirmed by user |
| Q5 | What are `fncs[2]=1` and `fncs[6]=10`? (NET v8 had `3` and `2`) | **✅ RESOLVED**: `fncs[2]=1`=SALT family; `fncs[6]=10`=algicide, `18`=flocculant |
| Q6 | What are `areqs[5,6,10,12] = 33`? (NET v8 had `36` and `6`) | ❓ unknown |
| Q7 | What is `ains[2]`? tracks `ains[6]` but offset varies | ❓ same mystery on NET v8 |
| Q8 | What is `ains[10]`? Not electrolyzer power (as previously thought) | ❓ raw ADC / power consumption in W? |
| Q9 | Is the v8 firmware transmitting water-level / filling-valve data? | 🟡 not in any known section — possibly not transmitted on SALT NET |
| Q10 | Phantom or missing entities reported by mirovra? | ❓ open — mirovra has not yet reviewed the final entity list |
| Q11 | What is `areqs[25] = 3` (constant)? | ❓ constant across all states, not algicide dose — unknown |
| Q12 | Does `flags[3]=1` also appear for flocculant (not just no-flow alarm)? | ❓ ambiguous — F2 no-flow had it, F6 flocculant also had it with ins[12]=0 |

---

## 17. Implementation summary (PR checklist)

- [x] Add `AsekoDeviceType.SALT_NET = "ASIN AQUA Salt NET"` to `aseko_data.py`
- [x] Add `100: AsekoDeviceType.SALT_NET` to `_V8_DEVICE_TYPE_BY_HEADER` in `aseko_decoder_v8.py`
- [x] Add `ACTUATOR_MASKS[AsekoDeviceType.SALT_NET]` (all 0x00, `byte37_routes_pump_type=False`)
- [x] Decode SAL salt NET fields: salinity, electrolyzer power (from `ains[9]`), electrolyzer direction (from `outs[14]`), algicide pump running (from `outs[11]`), no-flow alarm, required algicide
- [x] Extend `diagnostics.py` labels for the new ains/outs slots
- [x] Correct mapping: `outs_algicide=15` → `outs_algicide=11`, `electrolyzer_power` from `ains[9]` (was `ains[10]`), add `electrolyzer_direction` from `outs[14]`
- [x] Remove erroneous `flowrate_algicide` from v8 decoder (v8 has no per-pump flow rates)
- [x] Add tests for all 5 reference frames (F1–F5) including direction LEFT/RIGHT/OFF
- [x] All 80 v8 decoder tests passing
- [x] Ask mirovra for a frame with Pump 2 configured as flocculant to confirm the Q2 hypothesis
- [x] Implement flocculant detection: `(fncs[2]=1, fncs[6]=18)` → `{ph_minus, floc}`
- [x] Correct `required_algicide` source from `areqs[25]` to `areqs[4]`
- [x] Add `required_floc` sensor from `areqs[3]` when flocculant
- [ ] Update `net_v8_device_analysis.md` to note that SALT NET uses the v8 protocol too
- [ ] Manifest version bump (v1.7.0 → v1.8.0)

---

*Last updated: 2026-07-19, end of session 3 (mirovra's Jul 16 data resolved §11 ambiguities).*
