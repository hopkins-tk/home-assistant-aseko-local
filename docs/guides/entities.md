# Entity states and freshness

[Documentation](../README.md) / User guide

A value can be missing, not yet observed, temporarily unreadable or simply old. Those are different states.

[What each state means](#what-each-state-means) · [Offline does not erase the last reading](#offline-does-not-erase-the-last-reading) · [After a restart](#after-a-restart)

## What each state means

| State | Meaning |
| --- | --- |
| No entity | The model's profile does not read this value. Check the [support matrix](../support_matrix.md). |
| Disabled by the integration | The profile allows the value, but this unit has not shown it yet. It is enabled when the value arrives. |
| Unavailable | The latest frame says the feature is absent, for example after an accessory is removed or a shared pump port is rerouted. The entity and its history stay. |
| Unknown | The feature is present, but the frame cannot provide its value right now. |

Enabling a newly observed feature reloads the integration, so entities may briefly blink. Previously enabled entities stay enabled across restarts. An entity you disabled yourself stays disabled.

Some settings, such as water level, heating or a variable-speed pump, can be enabled on the unit without the accessory connected. Their entities may appear without a meaningful reading.

## Offline does not erase the last reading

The integration intentionally keeps the last values when frames stop arriving. Use **Connection status** and the recording card's **Last frame: N s ago** to judge freshness; a displayed value alone does not mean the device is online.

On profiles where the menu bit means a person is at the unit (currently SALT), the last menu-open flag produces `service_menu` without a timeout. See [connection troubleshooting](../troubleshooting.md#no-data-at-all) for the distinction between `online`, `offline` and `service_menu`.

## After a restart

Live values return with the next frame. Consumption counters, backwash history, the recording switch and the frame log are restored from storage. A feature absent from the first frame may be unavailable until a later frame carries it.

---

[All guides](../README.md#user-guides) · [Troubleshooting](../troubleshooting.md) · [Project home](../../README.md)
