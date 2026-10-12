# Device clock and drift

[Documentation](../README.md) / User guide

Compare the unit's clock with Home Assistant without changing the clock or silently shifting its schedule.

[Models and readings](#models-and-readings) · [Drift alert](#drift-alert) · [Precision and limitations](#precision-and-limitations) · [Summer time and backwash](#summer-time-and-backwash)

## Models and readings

An ASIN Aqua Home, Salt and Oxygen sends its own clock with each frame as date and time to the second, and an ASIN Aqua Net on firmware v8 as hour and minute; the Profi and a v8 Salt are assumed to do the same (see the [support matrix](../support_matrix.md), `unit_clock`). The ASIN Aqua Net on firmware v7 sends none, so it has neither entity below.

| Entity | What it shows |
|---|---|
| `sensor.…_clock_offset` | Difference from HA in minutes: positive means the unit is ahead; negative means behind. Uses the median of the last three frames. |
| `binary_sensor.…_clock_out_of_sync` | Diagnostic alert when three consecutive frames meet or exceed the configured drift limit. See the exact switching rules below. |

The offset includes both gradual drift and a summer/winter time change the unit missed. A single late frame does not move the median.

## Drift alert

The limit is **15 minutes** by default; change *Alert when the unit clock is off by (minutes)* in the integration's settings (the same dialog as the forwarder). A unit that did not follow a change of summer / winter time is an hour off, which turns the alert on with any limit under 60 minutes (the default 15 included). Both entities are diagnostic, so an automation on `clock_out_of_sync` is the way to get a notification.

The alert uses three consecutive frames:

- **Unknown** until three frames have arrived.
- **On** when all three are at least the limit off, in either direction. This also applies immediately after startup.
- **Off** when all three are below the limit minus a recovery margin. The margin is one fifth of the limit, capped at 3 minutes: a 15-minute limit clears below 12 minutes; a 1-minute limit clears below 48 seconds.
- **Otherwise unchanged.** Before it has first turned on, this intermediate state is off.

## Precision and limitations

A v8 unit sends no date and only whole minutes: its offset is read to about a minute and within ±12 hours, so a clock a day off is not seen.

## Summer time and backwash

The unit may not switch between summer and winter time on its own, and its clock can drift over weeks. The integration never sets the unit's clock.

While no frames arrive, the entities keep their last value. Check `connection_status` and frame age for freshness.

Scheduled backwash recognition accounts for drift and missed summer/winter time changes before applying the **±5-minute** window. It uses the offset from the opening frame; the displayed schedule still uses the time set on the unit. See [Backwash](backwash.md#drift-aware-classification), including the wider fallback window before an offset is known.

---

[All guides](../README.md#user-guides) · [Troubleshooting](../troubleshooting.md) · [Project home](../../README.md)
