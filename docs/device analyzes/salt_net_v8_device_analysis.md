# ASIN AQUA Salt NET fw v8 – Reverse Engineering & Field Mapping Notes

## Device

| Field | Value |
|---|---|
| Model | ASIN AQUA Salt NET |
| Firmware | v8.x (text frame, port 51050) |
| Source | Issue #131 (mirovra) — 3 complete diagnostic dumps + 4 hex-dump log snippets, July 2026 |
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

> **Reference frames** used for the byte-level mapping in §3–§5 are stored in
> `docs/temp/`:
>
> - `Issue-131.json` (F1, filtration ON, flow YES, electrolysis 40.1) — 2026-07-05 10:28
> - `Issue-131-scenario1-off.json` (F2, filtration OFF, no flow, electrolysis 33.6) — 2026-07-06 21:49
> - `Issue-131-scenario2-filtration.json` (F3, filtration ON, electrolysis 37.2, algicide pump on??) — 2026-07-06 16:48
>
> Working notes / hypothesis history: `docs/temp/Issue-131-analyze.md`.

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

| index | F1 | F2 | F3 | Formula | `AsekoDevice` field | Confirmed by |
|---|---|---|---|---|---|---|
| `ains[0]` | 752 | 733 | 739 | ÷ 100 → pH | `ph` | ✅ 7.52 / 7.33 / 7.39 matches app |
| `ains[1]` | 752 | 733 | 739 | duplicate of pH | — | always tracks `ains[0]` |
| `ains[2]` | 716 | 673 | 715 | unknown | unknown | ❓ tracks ains[6] but offset by ~5 |
| `ains[3]` | 7210 | 6780 | 7200 | ÷ 10 → mV (= `ains[6] × 10`) | — | = `ains[6] × 10`; not used |
| `ains[4–5]` | 0 | 0 | 0 | — | — | always 0 |
| `ains[6]` | 721 | 678 | 720 | direct mV | `redox` | ✅ 721 / 678 / 720 mV matches app |
| `ains[7]` | 721 | 678 | 720 | duplicate of redox | — | always tracks `ains[6]` |
| `ains[8]` | **49** | **48** | **50** | ÷ 10 → **g/L (salinity)** | `salinity` | ✅ **4.9 / 4.8 / 5.0 g/L** (typical salt-cell range) — NEW, SALT-NET-specific |
| `ains[9]` | 0 | 0 | **19** | raw (ml/min × 10?) | `flowrate_algicide` | 🟡 **algicide pump flow rate** — best guess, see §11 |
| `ains[10]` | **401** | **336** | **372** | ÷ 10 → electrolyzer power | `electrolyzer_power` | ✅ **40.1 / 33.6 / 37.2 g/h** (or %) — NEW, SALT-NET-specific |
| `ains[11–15]` | 0 | 0 | 0 | — | — | always 0 / reserved |

**`ains[8]` (salinity)**: this is the *only* non-zero slot in the
`ains[8..15]` range that is **always populated** in all 3 frames, which makes
it a strong candidate for the salinity reading. Values 4.5–5.5 g/L are the
typical operating range for a salt-chlorinator cell — the captured values
4.8–5.0 g/L match.

**`ains[10]` (electrolyzer power)**: this slot is non-zero in **all 3**
frames including the "no electrolysis" frame F2. It therefore represents
the **current power output**, not a boolean running flag. The on/off state
is implicit (any non-zero value ⇒ electrolyser cell is producing). Values
40.1 / 33.6 / 37.2 vary with chlorine demand, consistent with a
duty-cycled chlorinator.

**`electrolyzer_active`** can be derived as `electrolyzer_power > 0`.

---

## 6. `outs:` section — output states (pumps + filtration)

| index | F1 | F2 | F3 | Formula | `AsekoDevice` field | Confirmed by |
|---|---|---|---|---|---|---|
| `outs[0]` | 0 | 0 | 0 | bool | `cl_pump_running` | ❓ always 0 (no CL probe on SALT NET) |
| `outs[1]` | 0 | 0 | 0 | bool | `ph_plus_pump_running` | ❓ always 0 (no pH+ on SALT NET) |
| `outs[2]` | **2** | 0 | **2** | `bool` (any non-zero ⇒ ON) | `filtration_pump_running` | ✅ **2=ON, 0=OFF** — confirmed vs. app ("Pump: ON / OFF") |
| `outs[3–7]` | 0 | 0 | 0 | — | — | unused in all 3 frames |
| `outs[8]` | 0 | 0 | 0 | bool | `ph_minus_pump_running` | ❓ always 0 in 3 frames (no pH− dosing captured) |
| `outs[9]` | 0 | 0 | 0 | bool | `cl_pump_running` | ❓ always 0 (no CL pump) |
| `outs[10–13]` | 0 | 0 | 0 | — | — | unused |
| `outs[15]` | 0 | 0 | **2** | `bool` (any non-zero ⇒ ON) | `algicide_pump_running` | 🟡 **algicide pump running** — best guess from F3, see §11 |
| `outs[15–18]` | 0 | 0 | 0 | — | — | unused |

**Key finding (compared to NET v8):** NET v8 uses `outs[2] == 1` to mean
"filtration ON". The SALT NET uses `outs[2] == 2` to mean the same thing.
The decoder uses `bool(outs2)` which correctly handles **both** values.
This device-specific "ON" value is one of the few v8 quirks that required
no code change.

**`outs[15]` is the algicide pump running bit.** The mapping is
`bool(outs15)` (any non-zero ⇒ running). It is the only slot in the
`outs[10..19]` range that is non-zero in any of the 3 captured frames.
F3 (the "filtration running, no dosing" frame) shows `outs[15] = 2` even
though mirovra's screenshot showed "no dosing" — this is the single
ambiguity in the analysis. See §11 for the F3 algicide mystery.

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
| `areqs[17]` | 5 | 5 | 5 | minutes | `delay_after_startup` | ✅ 5 min (NET v8 had 2 min) |
| `areqs[18]` | 5 | 5 | 5 | minutes | `delay_after_dose` | ✅ 5 min (NET v8 had 2 min) |
| `areqs[19]` | 10 | 10 | 10 | unknown | unknown | ❓ |
| `areqs[21]` | 15 | 15 | 15 | unknown | unknown | ❓ |
| **`areqs[25]`** | **3** | **3** | **3** | **ml/m³/day** | **`required_algicide`** | ✅ **3 ml/m³/day** (only setpoint in the 0–10 range that fits an algicide dose) — SALT-NET-specific |

> **Note on `areqs[3]` / `areqs[4]` swap:** NET v8 has `(3: 5, 4: 0)`;
> SALT NET has `(3: 0, 4: 5)`. Both could be related to floc/alg routing —
> the SALT v7 unit uses `byte[37] & 0x80` to route between algicide and
> flocculant. The SALT NET does **not** use this routing (it has dedicated
> pump ports), so these are likely other configuration fields.

> **Note on `areqs[25]`:** the v8 frame is 0-indexed. The valid algicide
> setpoint is at **`areqs[25]`** (= 3 ml/m³/day). Earlier analyses that
> quoted `areqs[24]` were off-by-one (1-based vs 0-based indexing).

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
| `fncs[]` | `0 0 1 0 0 0 10 0` | (identical) | (identical) | `fncs[2] = 1` and `fncs[6] = 10` (NET v8 had `3` and `2` — different values, meaning TBD) |
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

## 11. Algicide pump state — the F3 mystery

F3 was captured during mirovra's "Filtration running, no dosing" scenario,
yet `outs[14] = 2` (algicide pump running) and `ains[9] = 19` (algicide
pump flow rate, best guess) indicate the algicide pump **was** running.

Plausible explanations (in order of likelihood):

1. **Timing skew**: mirovra took the screenshot ~seconds before/after
   the raw frame, and a manual algicide dose was triggered in between.
2. **Auto-dose**: the system triggered an automatic algicide dose in
   the seconds between the screenshot and the raw frame.
3. **User misread**: the user was on a dosing cycle at the moment of
   the frame and did not notice.

The mapping `outs[14] != 0 ⇒ algicide_pump_running = True` and
`ains[9]` is implemented as a best guess. The integration exposes both
fields so the next session can confirm with a dedicated algicide-dosing
frame.

**Implementation note:** the SALT NET does **not** use `byte[37] & 0x80`
routing (that is a v7 SALT thing — see [salt_device_analysis.md §byte[37]](salt_device_analysis.md#byte37--third-pump-routing-algicide-vs-flocculant)).
On the SALT NET, the algicide pump is a **dedicated physical port** that
the user configures in the app. `byte[37]` is not used for pump routing on
the v8 firmware, so `byte37_routes_pump_type` must be `False` for
`AsekoDeviceType.SALT_NET` in `ACTUATOR_MASKS`.

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
    algicide=0x00,          # algicide pump running is in outs[14] on v8
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
    # outs[14] (algicide_pump_running) and ains[9] (algicide flow rate).
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
|---|---|---|
| Q1.4 | Confirm `outs[14]` = algicide pump running, `ains[9]` = algicide flow rate (ml/min × 10?) | 🟡 best guess from F3, needs dedicated algicide-dosing frame |
| Q5 | Is Pump 2 of the SALT NET hard-wired to algicide or switchable to flocculant? | 🟡 mirovra confirms switchable, no flocculant frame yet |
| Q6 | What is `reqs[5] = 8`? | ❓ always 8 (was 0 on NET) — possibly a SALT-NET feature flag |
| Q7 | What is `reqs[7] = 20`? Filtration hours per day? | 🟡 probable, unconfirmed by user |
| Q8 | What are `fncs[2]=1` and `fncs[6]=10`? (NET v8 had `3` and `2`) | ❓ unknown |
| Q9 | What are `areqs[5,6,10,12] = 33`? (NET v8 had `36` and `6`) | ❓ unknown |
| Q10 | What is `ains[2]`? tracks `ains[6]` but offset by ~5 | ❓ same mystery on NET v8 |
| Q11 | Is the v8 firmware transmitting water-level / filling-valve data? | 🟡 not in any known section of the 3 frames — possibly not transmitted on SALT NET |
| Q12 | Phantom or missing entities reported by mirovra? | ❓ open — mirovra has not yet reviewed the final entity list |

---

## 17. Implementation summary (PR checklist)

- [x] Add `AsekoDeviceType.SALT_NET = "ASIN AQUA Salt NET"` to `aseko_data.py`
- [x] Add `100: AsekoDeviceType.SALT_NET` to `_V8_DEVICE_TYPE_BY_HEADER` in `aseko_decoder_v8.py`
- [x] Add `ACTUATOR_MASKS[AsekoDeviceType.SALT_NET]` (all 0x00, `byte37_routes_pump_type=False`)
- [x] Decode new fields in `AsekoV8Decoder.decode()`: salinity, electrolyzer power, algicide pump running, algicide flow rate, no-flow alarm, required algicide
- [x] Extend `diagnostics.py` labels for the new ains/outs slots
- [x] Add tests in `tests/test_aseko_decoder_v8.py` (3 frames + algicide dosing case)
- [ ] Ask mirovra to provide one frame with `outs[14] = 0` (algicide off) to remove the §11 ambiguity
- [ ] Ask mirovra to confirm `reqs[7] = 20` semantics (filtration hours per day?)
- [ ] Ask mirovra for a frame with Pump 2 configured as flocculant to confirm the Q5 hypothesis
- [ ] Update `net_v8_device_analysis.md` to note that SALT NET uses the v8 protocol too
- [ ] Manifest version bump (v1.7.0 → v1.8.0)

---

*Last updated: 2026-07-09, end of session 2.*
