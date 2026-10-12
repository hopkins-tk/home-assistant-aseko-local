# Troubleshooting

[Documentation](README.md) / Troubleshooting

<details>
<summary>On this page</summary>

- [No data at all](#no-data-at-all)
- [A unit shows up, but has no entities](#a-unit-shows-up-but-has-no-entities)
- [An entity is disabled, unavailable or unknown](#an-entity-is-disabled-unavailable-or-unknown)
- [A value looks wrong](#a-value-looks-wrong)
- [Backwash times look shifted](#backwash-times-look-shifted)
- [A frame looks damaged](#a-frame-looks-damaged)
- [After a restart](#after-a-restart)
- [The frame log and test cases](#the-frame-log-and-test-cases)

</details>

Where to look when something is off. Most answers are in the diagnostics
download: **Settings → Devices & Services → Aseko Local → ⋮ → Download
diagnostics**. The keys named below are keys of that JSON file.

## No data at all

| Check | Where |
|---|---|
| The unit sends to Home Assistant | the unit's **Serial Port** page: remote server = your HA address, port = the port set in the integration (see [Get started](guides/getting-started.md)) |
| The port matches the firmware | port **47524** for v7 (binary), **51050** for v8 (text) by default; a mixed setup can send both units to the port of one entry (frames are told apart by content), or use one entry per port |
| Frames arrive | the **Connection status** entity is `online` when a frame came in the last 60 seconds (the other entities keep their last values while it is `offline`). A unit whose profile carries the flag `MENU_BIT_IS_PRESENCE_ONLY` (today the ASIN Aqua Salt) and whose last frame had the settings menu open shows `service_menu` straight away, with no timeout — in the menu it may go on sending (a backwash) or send nothing until the menu is closed (a filtration run by hand); the test cases card header shows *Last frame: N s ago* |
| Frames arrive but none decodes | `rejected_frames` (bytes that never aligned into a frame, by reason), and per unit `implausible_frames`, `partial_frame` |

The integration log (**Settings → System → Logs**, filter `aseko`) names the
reason for a closed connection, a checksum failure or an unknown unit type.

## A unit shows up, but has no entities

The unit type (v7 `byte[4]`) or v8 header type is not mapped to a model. The
log says *Unknown unit type* or *Unknown v8 header type*, and the diagnostics
list the unit under `unrecognised_devices` with:

- `note` — what happened;
- `device.profile` — `v7 unknown unit type` or `v8 unknown header type`;
- `raw_frame_v7.annotated_table` / `raw_frame_v8` — the frame, byte by byte;
- the values the generic readings made of it (unverified).

Open an issue with that download; [Adding a model](adding-a-model.md) is what
happens next.

## An entity is disabled, unavailable or unknown

| State | Meaning | Where to confirm |
|---|---|---|
| **disabled** (by the integration) | the model can have the value, but this unit has never sent it; it switches itself on when it does and stays enabled after a restart | `devices[].device.possible_features` has it, `features` does not |
| **unavailable** | the last frame did not carry it: the accessory is not fitted (any more), the shared pump port is routed to the other chemical, or the setting is off | `devices[].device.not_present_now` |
| **unknown** | the unit has it, but the last frame could not say (e.g. `0xFF` "not filled in" at start-up, an unreadable v8 value) | `devices[].device.frame_problems` for v8 |
| no entity at all | the profile does not read the value: the model does not have it, or it is not decoded yet | the [support matrix](support_matrix.md) shows — |

A setting such as water level, heating or the variable-speed pump can be
switched on at the unit without the accessory; the entity then appears but
shows nothing meaningful.

An entity you disabled yourself stays disabled.

## A value looks wrong

1. Find the value in the [support matrix](support_matrix.md): ✅ checked
   against the unit on this model or derived from the protocol, 👁 seen but
   never compared, ❓ assumed, 🔍 not located, — not read. See
   [Evidence rules](evidence-rules.md).
2. `devices[].device.profile` and `reading_overrides` say which profile read
   the frame and where it reads differently from the default.
3. Compare with the unit display. For a ❓ or a wrong ✅, record a test case
   with the [test-cases card](guides/recording.md) while the unit shows the value.

## Backwash times look shifted

The schedule the unit shows is in **its own** clock. Compare
**Clock offset** (`devices[].device.clock_offset_minutes`: minutes the unit
is ahead, negative behind; drift and summer / winter time together) with the
shift you see. `next_scheduled_backwash` shows the time set on the
unit, not moved by the offset, so a unit that is off runs its backwash that
much earlier or later on Home Assistant's clock. Recognising a scheduled cycle
takes the offset measured when the valve opened (drift and a missed change of
summer / winter time) out and allows ±5 minutes around the set time; before
the unit's clock has been measured at all it allows ±15 minutes on Home
Assistant's clock instead. `last_scheduled_backwash` shows the unit's set time
of the cycle, `last_backwash` when Home Assistant saw it. An offset near ±60 minutes after a
change between summer and winter time usually means the unit did not switch;
set its clock on the unit. After a change of the
backwash time or interval, the next cycle is the day after the change
(checked on an ASIN Aqua Salt, assumed on the other models). **Clock out of
sync** turns on when the offset passes the limit set in the integration's
settings (15 minutes by default). See [Device clock and drift](guides/device-clock.md).

## A frame looks damaged

| Symptom | Where |
|---|---|
| v7 checksum failed | log: *failed the checksum of segment(s)* — the frame is still decoded |
| v7 values out of range | `devices[].implausible_frames`, e.g. `pH 99.99 outside 0-14` |
| v8 value not a number, or a section missing | `devices[].device.frame_problems` for the last frame; counted under `implausible_frames` as `v8 value unreadable: …` |
| v8 frame could not be parsed at all | `implausible_frames`: `v8 frame rejected: …`; the connection is closed and the unit reconnects |
| bytes never aligned | `rejected_frames` with the reason; the bytes are in the frame log as `rejected` while recording is on |

## After a restart

- Values come back with the next frame (about 10 seconds for v7).
- Entities that were enabled stay enabled; one whose value the first frame
  does not carry is unavailable until a frame does.
- Consumption counters are restored exactly (ml) from Home Assistant's
  storage; backwash history likewise.
- The frame log and its recording switch survive restarts and updates.

## The frame log and test cases

| Question | Answer |
|---|---|
| Is anything recorded? | `frame_log_enabled`; recording is off until turned on in the card |
| How far back? | `frame_log.oldest` / `newest`, `dropped_chunks`; about five days for one v7 unit |
| Which frames go with case N? | `python scripts/frame_log_tool.py DIAGNOSTICS.json --around N` |
| All frames as JSON lines | `python scripts/frame_log_tool.py DIAGNOSTICS.json --jsonl frames.jsonl` |
| Case says *frames aged out* | the log no longer holds frames from that time |
| Case marked with an error | no accepted frame came within 60 s; the case was written without one |
| *Recording was stopped or deleted while waiting* | recording was turned off or deleted (maybe on another device) while the case waited; the case and its photo were not kept |

In the zip from **Download new / all**, every file carries the entry's title
and id (`frames-<title>-<entry_id>.jsonl`, `diagnostics-…`), so several
Aseko Local entries never overwrite each other; `README.txt` in the zip lists
the files.
