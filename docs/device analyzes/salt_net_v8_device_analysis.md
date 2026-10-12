# ASIN AQUA Salt NET (v8) — Device Analysis

[Documentation](../README.md) / [Device analyses](README.md)

> **Status:** the NET v8 layout plus the salt-only values below. Everything a
> salt unit sends on top of NET was read from frames an owner labelled with
> what the Aseko Live app showed at that moment (Issue #131); the shared part
> is the [NET v8](net_v8_device_analysis.md) layout, taken over unverified.
> **Profile:** [`profiles/v8/salt.py`](../../custom_components/aseko_local/decoding/profiles/v8/salt.py) · **Support:** [support matrix](../support_matrix.md)

## 1. Device

| Field | Value |
|---|---|
| Model | ASIN AQUA Salt NET |
| Firmware | 8.x text frames; header type 100 and 106 captured |
| Hardware | salt electrolysis cell (output in g/h, reversing polarity), pH probe and redox probe, pH− pump, one third pump port for algicide **or** flocculant, filtration relay |
| Identification | header type in the range 100–199: the product line picks the model, the rest of the number is the firmware version — header 106 on the unit whose INFO screen shows V: 1.06 (Issue #169) |
| Sources | Issue #131: labelled captures from one unit (header 100, 2026-07-09 … 07-19) and one frame with a display comparison from a second unit (header 106); Issue #169: the second unit's owner ran it on a v1.9.x decoder patched for header 106 from 2026-09-21 and timed a real algicide dose |

The unit has **no chlorine canister**: the profile leaves out
`chlorine_pump_running` and `chlorine_flow_rate`, so a Salt NET no longer
shows a chlorine pump it does not have (the complaint in Issue #131).

## 2. Salt-only values

| Value | Position | Evidence |
|---|---|---|
| `salinity` | `ains[8]` / 10 (kg/m³) | confirmed: the display read **10.1** with `ains[8] = 101` in the same minute (header 106) |
| `chlorine_production_measured` (→ `chlorine_production`) | `ains[9]` (g/h) | confirmed: **19** and **20** in captures their owner labelled 19 and 20 g/h, **0** with the electrolyser off |
| `electrolysis_running` | `outs[14]` ≠ 0 | confirmed on the labelled captures |
| `electrode_polarity` | `outs[14]`: 0 waiting, **2 right**, **3 left** | confirmed: the owner recorded the direction the app showed with each capture |
| `algaecide_pump_running` | `outs[11]` while `fncs[6] = 10` | confirmed: on the header 106 unit `outs[11]` went on and off exactly over the algicide dose 00:03:47–00:06:24 on 2026-09-22 (Issue #169); `outs[11] = 1` in the capture labelled "algicide pump running" (Issue #131) |
| `flocculant_pump_running` | `outs[11]` while `fncs[6] = 18` | observed: `fncs[6]` read **10** with algicide configured and **18** after the port was switched to flocculant on 2026-07-19 |
| `algaecide_dose_target` | `areqs[4]` while `fncs[6] = 10` | confirmed: **2** matching the display and the app on the header 106 unit (Issue #169); **5** with the first unit set to 5 ml/m³/day, 0 after the switch |
| `flocculant_dose_target` | `areqs[3]` while `fncs[6] = 18` | observed: **10** with the unit set to flocculant 10 ml/h |
| `filtration_period_1_start` / `_end` | `reqs[5]` / `reqs[7]`, whole hours | confirmed: **8** and **20** while the app showed "Filtration time 1" 08:00–20:00; **0** and **24** on the header 106 unit, whose app showed 24:00 |
| `filtration_schedule` | the same two hours: 0 to 24 nonstop, anything else the timer | confirmed: 0 to 24 while the app showed "FILTRATION NONSTOP 24H" and the display "Timer 24dag"; a v8 unit offers one period only |
| `alarm_no_flow_to_probes` | `ins[12]` bit `0x100` | derived: the flag the v8 decoder has always read; no capture shows it set |
| `alarm_max_disinfection_dose` | `ins[12]` bit `0x80` | observed: the value flipped 0 → 128 while the unit showed "Maximum disinfection dose exceeded" (Issue #151) |

The third pump port is one physical output. `fncs[6]` says which chemical it
is set up for, and the value for the other one is reported as not present, so
a unit dosing algicide gets no flocculant entities and the other way round —
the same rule the v7 SALT profile follows with its byte[37] routing bit.

The entities follow the port's **mode**, not the product in the canister. The
[Salt NET manual](https://rubinpool.se/wp-content/uploads/2026/01/AA-Salt-Net-Man-EN-2025-01.pdf)
(EN 2025-01) names the port "Algicid / ACO": a daily dose in ml/m³ of Aseko
ALGICID (typically 10) or of the ACO chlorine stabilizer (typically 3). The
header 106 unit runs its port in that mode (`fncs[6] = 10`, dose in `areqs[4]`)
with a flocculant connected, so it shows the algicide entities; that is the
unit's setting read right, not a decoding error (Issue #169). The entities of
this port are named "Algicide / ACO" on a Salt NET (profile flag
`ALGICIDE_OR_ACO`); their keys and unique IDs are the algicide ones.

The algicide dose is **ml/m³ per day**. The Dutch controller texts show it as
"ml/m³ per uur"; with the display set to English the same unit shows per day,
so the Dutch label is a translation error on the unit (Issue #169).

## 3. What the unit and the app show

One photo of the header 106 unit's own display (Dutch UI, Issue #131,
2026-09-21) and Aseko Live screenshots of both units:

| Display tile | Shown | Frame |
|---|---|---|
| Rx | 544 mV, setpoint 720 | `ains[6]`, `areqs[1]` × 10 |
| pH− | 7.1, setpoint 7.1 | `ains[0]` / 100, `areqs[0]` / 10 |
| Alg/Aco | 2 ml/m³/uur | `areqs[4]`; per **day** (see above) |
| PRESTAT. g/d. | 0.0 | `ains[9]`; the app shows the same value in g/h, whole numbers |
| ZOUT kg/m³ | 10.1 | `ains[8]` / 10 |
| Temperatuur | 29.6 °C | `ins[0]` / 10 |
| Timer | 24dag, 12:42 | `reqs[5]`–`reqs[7]`; the unit's clock `ins[16-17]` |

The display labels are the unit's; "g/d." next to a value the app gives in g/h
reads like another Dutch label slip, like "per uur".

**Settings the app shows that nothing decodes.** The Aseko Live *Config* page of
the header 106 unit lists, besides the setpoints: *Water flow meter* ON,
*Polarity switching* Hourly, *Electrolysis max. run time* 0 days, *Dosing
outside filtration timer* No. Where they sit in the frame is not known
(`mods`, `flags` and several `areqs` slots are unread).

**The app counts consumption.** Aseko Live has a *Consum.* tab, and its history
shows each dose with its length: on the header 100 unit "Algicide → 60 for
4m 59s" on 2026-07-09 08:00. What the 60 is (ml dosed, ml/min) is not known.

## 4. Shared values checked on this model

The rest of the frame is the NET v8 layout. These entries were checked against
this model rather than taken over:

| Value | Position | Evidence |
|---|---|---|
| `ph` | `ains[0]` / 100 | 7.09 while the display read pH 7.1 in the same minute (firmware 106) |
| `redox` | `ains[6]` | 542 mV, matching the display |
| `water_temperature` | `ins[0]` / 10 | 29.5 °C, matching the display |
| `ph_target` / `redox_target` | `areqs[0]` / 10, `areqs[1]` × 10 | 7.1 and 720 mV, matching the setpoints on the display |
| `pool_volume` | `areqs[14]` | 55 m³ on the unit whose owner gave its pool as 55 m³; 49 m³ matching the display on the header 106 unit (Issue #169) |
| `unit_clock`, `timestamp` | `ins[16]` hour, `ins[17]` minute | 18:25 and 08:01 in captures their owner timestamped 18:22:49 and 07:58:59 — the unit ran about two minutes ahead |
| `startup_delay`, `dosing_delay` | `areqs[17]`, `areqs[18]` | 5, the 5 min the unit is set to; a NET v8 sends 2 for its 2 min |

**`ins[13-15]` is the unit's own calendar date** -- year + 2000, month, day,
as in v7 bytes 6-8 -- **and no unit sends the right one**, so it is not read.
The field runs correctly, one day per day; only its absolute value is wrong,
by a different amount on every unit:

| Unit | Real date | Sent | Behind |
|---|---|---|---|
| NET v8 | 2025-09-16 | 2024-06-29 | 444 days |
| NET v8 | 2026-04-13 | 2025-01-24 | **444 days** |
| Salt NET 100 | 2026-07-15 | 2024-07-09 | 736 days |
| Salt NET 100 | 2026-07-16 | 2024-07-10 | **736 days** |
| Salt NET 100 | 2026-07-19 | 2024-06-01 | 778 days |
| Salt NET 106 | 2026-09-13 | 2024-09-13 | 730 days |

The same offset after 209 days of real time on the NET unit is what settles
it as a running calendar rather than a counter. The Salt NET dropped to
2024-06-01 between 16 and 19 July, while its owner was reconfiguring the
third pump -- that reads like the date a unit falls back to after losing
power. On the 106 unit the offset happens to be two years, so its month and
day look right.

The time of day is a different matter: it was about two minutes ahead of Home
Assistant, so the clock is set and only the year is not. `timestamp`
therefore takes its date from Home Assistant, `unit_clock` is an hour and a
minute, and the clock offset entity works to about a minute within +/-12 h.

Still taken over unverified, because no capture separates them: the
filtration relay (`outs[2]`, which reads 2 here and 1 on a NET), water flow to
the probes (`ins[8]`, never seen 0) and the pH− pump (`outs[8]`).

## 5. Not taken over from the v1.9.1 decoder

hopkins-tk#162 built the same unit into the pre-2.0.0 decoder. Its readings
are all here, read from the same captures, except two:

- **`installed_pumps` from `fncs`.** It decided which pumps a unit has from
  `fncs[2]` and `fncs[6]` against a table of known combinations. The second
  unit (firmware 106) sends `fncs[2] = 3` with the same hardware, which that
  table rejects (Issue #169: v1.9.2 fell back to NET on it), so the question
  is open; here a pump is part of the model's profile and `fncs[6]` only
  routes the third port.
- **`filtration_hours_per_day` from `reqs[7]`.** The same byte is read as the
  stop hour instead (section 2), which is what both captured units show.

## 6. Open questions

- **A changed timer.** The hours are read as start and stop (see above). A
  capture from a unit whose timer was changed to, say, 09:00-17:00 would
  confirm `reqs[5] = 9`, `reqs[7] = 17` directly.
- **The temperature setting is not captured.** The controller offers a third
  filtration setting next to nonstop and the timer, which runs the pump for
  water temperature / 2 + 2 hours a day (Issue #131; the manual, per
  hopkins-tk#162). No frame of a unit in it has been seen, so nothing decodes
  it: `filtration_schedule` knows only nonstop and the timer, and a unit in
  the temperature setting would most likely be reported as the timer, with
  whatever hours the unit computed for the day. A capture with the setting on,
  and a second one the next day at a different water temperature, would settle
  both where it is flagged and whether the hours move.
- **`fncs[2]`.** 1 on the first unit, 3 on the second, same hardware. It is not
  read, and the profile does not gate anything on it.
- **The shared NET values** (pH, redox, temperature, setpoints, pump bits) are
  taken over from the NET v8 profile and carry its evidence, not a Salt NET
  comparison.
- **No algicide or flocculant consumption.** v8 sends no pump flow rates.
  pH− has an assumed 60 ml/min so its counter runs; the third port has none,
  so `algicide_consumed_total` stays at 0 through a dose (Issues #131, #169).
  Both units send **33** in `areqs[5, 6, 10, 11, 12]` (a NET v8: 36, 36, 6,
  0, 36), unchanged when the third port switched chemical. Read as l/h × 10,
  33 is 55 ml/min, and the header 100 unit's 5 ml/m³ × 55 m³ = 275 ml at
  55 ml/min takes 5 min -- the app showed a 4 min 59 s dose. The header 106
  unit does not fit: 2 × 49 = 98 ml in 2 min 37 s is 37 ml/min. The manual
  gives the pumps as 60 ml/min at up to 1 bar, the figure the pH− counter
  already assumes. A frame before and after changing a pump's flow rate on
  the unit would settle it.
- **No electrolyser setpoint** has been located: the unit sends the produced
  g/h, not the configured percentage.
