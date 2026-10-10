# Backwash history and scheduling

[Documentation](../README.md) / User guide

For ASIN Aqua Home, Salt, Oxygen and Profi. The integration observes valve activity; the unit does not transmit a history of completed cycles.

<details>
<summary>On this page</summary>

- [Configuration](#configuration)
- [History and time bases](#history-and-time-bases)
- [Observed vs. estimated](#observed-vs-estimated)
- [Drift-aware classification](#drift-aware-classification)
- [Next scheduled cycle](#next-scheduled-cycle)
- [Seeding the schedule by hand](#seeding-the-schedule-by-hand)
- [Upgrading from a store that predates the split](#upgrading-from-a-store-that-predates-the-split)
- [Known ways the estimate gets it wrong](#known-ways-the-estimate-gets-it-wrong)

</details>

The device transmits its backwash **configuration** and the live state of the backwash valve, but never its history — it does not report when the last cycle ran. The integration therefore watches the valve itself and builds the history from what it observes.

## Configuration

Configuration read straight from the frame:

| Entity | Description |
|---|---|
| `sensor.backwash_every_n_days` | Interval in days (`0` = automatic backwash disabled) |
| `sensor.backwash_time` | Scheduled start time (HH:MM) |
| `sensor.backwash_duration` | Duration in seconds |
| `binary_sensor.backwash_active` | Valve is open right now |

## History and time bases

History, recorded live and persisted across restarts. **These are not all equally reliable** — see below:

| Entity | Meaning | Clock |
| --- | --- | --- |
| `sensor.last_backwash` | Last observed cycle, whatever started it; unknown until one is seen | HA observation time |
| `datetime.last_scheduled_backwash` | Last cycle classified as scheduled, or a date you enter; see its `source` attribute | ASEKO scheduled slot, e.g. 08:30 |
| `sensor.last_manual_backwash` | Last cycle classified as manual; an unattributed cycle does not move it | HA observation time |
| `sensor.next_scheduled_backwash` | Projected next automatic cycle; unknown until a scheduled cycle is known or the schedule changes | ASEKO schedule time |

The Home Assistant times are the midpoint of the relay window, taken from when
Home Assistant received the frames: each frame is stamped the moment it is
complete, before it is decoded. The delay between the unit sending a frame and
Home Assistant receiving it is not corrected for. The Aseko times read like the
unit's menu; `clock_offset` says how far they are from Home Assistant's clock.
All of them are stored with their time zone, and durations and gaps between
frames are measured with the times normalised to UTC, so a change of summer /
winter time does not stretch or shorten a cycle.

**Observation and classification are separate.** A detected cycle has timing evidence from frames, accurate to about one transmit interval. Whether it belongs in the scheduled or manual bucket is an estimate.

`last_scheduled_backwash` represents that cycle's scheduled slot, or a date you entered by hand. The future `next_scheduled_backwash` is a calculated projection and inherits the classification's uncertainty; it is the entity labelled "(estimated)".

## Observed vs. estimated

A cycle is **recorded** when the backwash valve stays open for at least 60 seconds — short activations (menu navigation, output test mode) are ignored. That part is a direct observation: `sensor.last_backwash` means the valve really did run a full cycle.

The device does **not** report *why* the valve opened.

A unit whose profile says its menu bit means a person at the unit (the profile flag `MENU_BIT_IS_PRESENCE_ONLY`; today the **ASIN Aqua Salt**) reports when its settings menu is open, and a manual backwash is started from that menu:

| Menu during the cycle | Valve opened within **±5 min** of `backwash_time` on the unit's clock — drift and summer / winter time taken out (schedule enabled) | Otherwise |
|---|---|---|
| open | **scheduled** | **manual** |
| closed | **scheduled** | **not attributed** — neither the schedule nor a person explains it |

A not attributed cycle updates `sensor.last_backwash` only; `last_scheduled_backwash` and `last_manual_backwash` keep their values, and the diagnostics show `last_backwash_trigger: unknown`.

**Units without that flag** (today Home, Oxygen, Profi: on HOME the bit is a standing pump override, on Oxygen and Profi its meaning is not confirmed) only the time decides: within **±5 minutes** of `backwash_time` on the unit's clock (drift and summer / winter time taken out) on a unit whose schedule is enabled → **scheduled**; anything else, including any cycle with `backwash_every_n_days = 0` → **manual**.

## Drift-aware classification

`backwash_time` is set on the **unit's clock**, which runs apart from Home Assistant's ([Unit clock](device-clock.md)). The window is **±5 minutes** of `backwash_time` on the unit's clock: the valve start, taken on Home Assistant's clock, is moved by the offset **in the frame in which the valve opened** — drift and a missed change of summer / winter time together, read from that frame's own clock rather than from the smoothed `clock_offset`, so a cycle right after the clock jumped is still recognised; a later change of the clock during the cycle does not move it. A frame that carries no clock (the unit's clock is not read on every model) uses the last offset measured before it; while none has been measured at all — a fresh install, the first frames — the window is ±15 minutes of `backwash_time` on Home Assistant's clock, and an offset measured later does not change how that cycle was recorded. What is left for the window to absorb is up to one transmit interval (~30 s) of lag before the frame reports the valve as open.

For example, with `backwash_time` 08:30 on a unit that did not switch to summer time (an hour behind) and runs 5.5 minutes fast, `clock_offset` is −54.5 minutes. The valve opens at 09:24:30 on Home Assistant's clock; moved by −54.5 minutes that is 08:30 on the unit's clock, within ±5 minutes → **scheduled**. A cycle at 09:40 on Home Assistant's clock is 08:45:30 on the unit's clock, outside → not scheduled.

## Next scheduled cycle

`next_scheduled_backwash` is projected from the last **scheduled** cycle: the day of the `backwash_time` slot that cycle belonged to (fixed when the cycle is recorded; the day before when it ran past midnight), plus the configured interval, stepped forward if cycles were missed while Home Assistant was down. A manual backwash deliberately does not move it — starting one by hand does not tell us (nor, on the unit, change) the schedule phase. Since it builds on the classification, it inherits any error in it.

**Changing the schedule** restarts it. When a frame shows a new `backwash_time` or `backwash_every_n_days`, or the schedule switched back on (every N days from 0), the unit runs the next backwash **the day after the change** at the (new) time, and counts the interval from that cycle. This was checked on an ASIN Aqua Salt; the Home, Oxygen and Profi are assumed to behave the same. `next_scheduled_backwash` shows that day until the cycle has been seen; switching the schedule off shows unknown. A change made while Home Assistant was not running is noticed on the first frame after it starts, and taken as made then.

The projected time is **the time set on the unit**, exactly as its menu shows it (`backwash_time` on the day the unit counts to). It is not moved by the drift nor by a change of summer / winter time the unit did not follow. When the unit's clock is off, the valve opens that much earlier or later on Home Assistant's clock: `clock_offset` says by how much, so the exact moment is the projected time minus `clock_offset`. Which slot is next is decided on the unit's clock.

> **Upgrading:** `sensor.next_backwash` was renamed to `sensor.next_scheduled_backwash`. The integration rewrites the entity registry on startup, so the entity keeps its `entity_id`, its recorded history and any automation or dashboard pointing at it — only the displayed name changes.

## Seeding the schedule by hand

Because the device never transmits its history, `next_scheduled_backwash` stays unknown until the integration has watched a whole scheduled cycle — up to a full interval of waiting.

To skip that wait, **click `datetime.last_scheduled_backwash` and pick the date** in the dialog. That is why it is a `datetime` entity rather than a read-only sensor: no helper, no script, no confirm button.

The same thing from an automation:

```yaml
action: aseko_local.set_last_scheduled_backwash
data:
  timestamp: "2026-08-01 12:30:00"
  # serial_number: 110071590   # optional; omit to set every backwash-capable device
```

Enter it on the unit's clock, as the unit's menu shows the time (e.g. 08:30);
it must not be later than now on that clock. In the first moments after a restart the entry is
refused while the stored history is still being read — the load would replace it — so try again
a moment later. `datetime.last_scheduled_backwash` carries a
`source` attribute saying where its value came from:

| `source` | Meaning |
|---|---|
| `observed` | The integration watched this cycle run |
| `manual` | You entered it |

`next_scheduled_backwash` has no `source` of its own — it is projected from
`last_scheduled_backwash` (or, after a schedule change, from the day after the
change), so that entity's `source` covers both.

**The last write wins, and the stored timestamps are never compared.**

* Entering a date always applies, whatever it is and whatever was there
  before — if you are typing it in, you have a reason to.
* A scheduled cycle detected *after* that entry replaces it, and the source
  flips back to `observed`. The value you entered stood in for a real cycle
  until one turned up; one has.

So a seed is only ever overtaken by an actual observation, never by an older
record, and you can always take control back by entering a date again.

Seeding deliberately does **not** touch `sensor.last_backwash`: that one means
"the integration watched this happen", and a typed-in date has not been
watched. It also does not touch `last_manual_backwash`, which tracks *observed*
cycles that were started by hand — a different thing from a manually entered
date.

To undo a mistyped date there is `aseko_local.clear_last_scheduled_backwash`,
which returns the value to unknown (optionally for one `serial_number`). If the
last cycle was the scheduled one and no manual cycle has been seen, the next
frame classifies that cycle again and may fill the value back in — see below. A
newer manual or not attributed cycle keeps its classification.

## Upgrading from a store that predates the split

`last_scheduled_backwash` and `last_manual_backwash` are newer than
`last_backwash`, so an existing install has a stored cycle but no record of
which kind it was. Rather than leave both empty until the next cycle — up to a
whole interval away — the integration classifies that stored timestamp against
the schedule on the first frame after the upgrade, and fills in whichever of
the two it belongs to (neither, if it comes out not attributed). It does this
once, and only while both are empty, so a real cycle is never second-guessed.

## Known ways the estimate gets it wrong

* A cycle you start **by hand near the scheduled time** is reported as scheduled, on every model.
* Only the **time of day** is checked, not the day itself. A manual cycle at exactly `backwash_time` on a day the interval does not fall on still counts as scheduled. (Checking the day would require knowing the schedule phase — which is exactly what this is trying to establish — and would break whenever you change the interval.)
* Before the unit's **clock offset** is known, a unit whose clock is more than 15 minutes off Home Assistant's has its own scheduled cycles reported as manual (not attributed on an ASIN Aqua Salt). Once `clock_offset` is measured the offset is taken out of the comparison — see [Unit clock](device-clock.md).
* A schedule change made while Home Assistant was not running is dated to the first frame after it starts, so a change made a day or more earlier projects the next cycle too late.
* A cycle the unit runs on its own **for some other reason** (e.g. after a fault) is reported as manual — on an ASIN Aqua Salt as not attributed.
* Classification uses the schedule **as it was at the time of the cycle** and is never revisited — changing `backwash_time` later does not reclassify history.

If a cycle looks misclassified, the integration's diagnostics download carries `last_backwash_trigger` alongside the raw frame, so you can see what it decided and open an issue.

> **Fresh install:** observed history is unknown until a cycle is seen. You can seed `last_scheduled_backwash` by hand; the next scheduled time can also be projected after a schedule change. Neither action invents an observed `last_backwash`.

---

[All guides](../README.md#user-guides) · [Troubleshooting](../troubleshooting.md) · [Project home](../../README.md)
