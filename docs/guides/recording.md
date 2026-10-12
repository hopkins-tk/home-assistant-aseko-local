# Record test cases

[Documentation](../README.md) / User guide

Connect one change on the unit with the next frame it sends. Use notes and optional display photos to help verify or extend device support.

<details>
<summary>On this page</summary>

- [Record with the card](#record-with-the-card)
- [How recording works](#how-recording-works)
- [Add the card](#add-the-card)
- [Capture one change at a time](#capture-one-change-at-a-time)
- [Card controls](#card-controls)
- [Retention and limits](#retention-and-limits)
- [Diagnostics only](#diagnostics-only)
- [Record from an automation](#record-from-an-automation)

</details>

If your model is not fully verified in [Device support](device-support.md), or the [support matrix](../support_matrix.md) shows ❓ for a value, you can help. What we need is simple: the frames your unit sent, and what the unit showed at that moment. The integration can collect both for you.

## Record with the card

<img src="../../images/aseko_test_cases_card.png" alt="Aseko test cases card" width="438">

## How recording works

While recording is on, the integration keeps a *frame log*: every frame the unit sends, compressed and capped at 256 kB, kept across Home Assistant restarts. Roughly five days from one v7 unit is an estimate, not a retention guarantee; it depends on how often the unit sends and how much changes.

Each test case adds a *marker* to that log, with your note and an optional photo of the unit's display. The change and the frames that carry it stay together, without matching photo timestamps by hand.

Recording is **off** until you turn it on in the card, and it stays the way you left it across restarts and updates. While it is off the frame log records nothing; the diagnostics still show the last frame of each unit.

## Add the card

Add the card to any dashboard (it is loaded automatically, no resource to add):

```yaml
type: custom:aseko-test-cases-card
```

## Capture one change at a time

Standing at the unit with your phone:

> **Android:** open the dashboard in **Chrome** (your Home Assistant address, e.g. `http://192.168.1.10:8123`). The Home Assistant app offers only the gallery when the card asks for a photo, even with the camera permission granted; in Chrome **Photo + mark** opens the camera. A photo picked from the gallery works too.

1. **Start recording.** Tap **Recording off** in the header; it turns into **Recording on** with a red dot. **Last frame: N s ago** shows the unit is sending (a v7 unit sends about every 10 seconds). **Photo + mark** and **Mark** work only while recording is on.
2. **Change one setting** on the unit.
3. **Mark it.** Type what you changed, e.g. *Heating control ON*, and tap **Photo + mark** or **Mark**. When several units send to the same entry, choose the one you are testing in the **Unit** list.

   The photo is stored immediately, but the marker waits for the next accepted whole frame, up to 60 seconds. The unit may pause transmission while its settings menu is open, so close the menu if necessary. Wait for *frame received, go on with the next change* before continuing.

4. **Repeat** for as many changes as you like; switching a setting back is a useful case too. The cases stay in Home Assistant, so the list is the same on the phone and on a PC; the ones not downloaded yet are highlighted.
5. **Download and share.** On any device tap **Download new**: one zip with the frames, the markers, the diagnostics and the photos. Open a new issue at [github.com/hopkins-tk/home-assistant-aseko-local](https://github.com/hopkins-tk/home-assistant-aseko-local/issues/new), say which model and firmware you have, and attach the zip.
6. **Stop recording.** Tap **Recording on** when you are done. What was recorded stays until you delete it.

## Card controls

| Button | What it does |
|---|---|
| **Recording on / off** | starts or stops the frame log; the recorded frames stay either way. Stopping cancels a case still waiting for its frame |
| **Photo + mark** / **Mark** | writes a case after the next frame, with or without a photo of the display |
| **Download new** | a zip with the cases not downloaded yet; they count as downloaded once your browser has the whole zip |
| **Download all** | every case again |
| **Clear list** | empties the list of cases; frames and photos stay |
| **Delete recording** | deletes every recorded frame, case and photo (asks first) |

The card follows the Home Assistant language (English, Slovak, Czech, German, French; `language: en` overrides it). Photos are downscaled to 2048 px and kept in `<config>/aseko_local/photos`, at most 200 photos or 100 MB (the oldest go first). The card and its endpoints are for admin users, like the diagnostics download.

> The frames and the unit's display carry its serial number; check the photos before you attach them to a public issue.

> **Security:** the unit sends its data unencrypted to the port the integration listens on. Keep that port inside your trusted network — do not forward it from the internet. The diagnostics download and the zip export contain the unit's serial number.

## Retention and limits

| What | Limit | When it is reached |
|---|---|---|
| Frame log | 256 kB compressed, roughly five days of frames from one v7 unit (an estimate) | the oldest frames are dropped; a marker older than the oldest frame has nothing next to it, so download within a few days |
| Markers (test cases) | 500 | the oldest markers are dropped |
| Photos | 200 photos or 100 MB, 2048 px | the oldest photos are deleted |
| Waiting for a frame | 60 seconds | the case is written without a new frame and the card shows it as an error; check the unit is sending, then record the case again |

- **Downloaded** means your browser received the whole zip. If the download breaks off, the cases stay *new* and **Download new** offers them again.
- Several units sending to one entry share the frame log, so it covers fewer days.
- Bytes that could not be aligned into a frame are counted, with the reason, under `rejected_frames` in the diagnostics, and kept in the log as *rejected* while recording is on.
- A unit whose model the integration does not know gets no entities; it is logged as a warning, its frames are recorded while recording is on, and the diagnostics list it under `unrecognised_devices`, which is exactly what adding it needs.

## Diagnostics only

1. In Home Assistant go to **Settings → Devices & Services → Aseko Local**
2. Click on your device, then click **Download Diagnostics** (3-dots menu beside settings symbol)
3. Open a new issue at [github.com/hopkins-tk/home-assistant-aseko-local](https://github.com/hopkins-tk/home-assistant-aseko-local/issues/new) and attach the downloaded JSON file

The diagnostics file contains an annotated table of every byte in the last raw data frame sent by your device, and — if recording was on — the frame log with its markers.

## Record from an automation

The card is a front end for this action, so an automation or a dashboard button can write markers too. Call `aseko_local.mark_dump`, optionally with a short `note`; recording has to be on (turn it on in the card), otherwise the action fails. It writes the marker only once the next whole frame has arrived (at most 60 seconds); `wait_for_next_frame: false` writes it at once, and `serial_number` waits for one unit's frame when several send to the same entry. It returns the marker number and how many seconds ago each unit's last frame arrived, and a Home Assistant notification shows *waiting for a frame* and then *written*. `python scripts/frame_log_tool.py DIAGNOSTICS.json --around 1` prints the frames around marker 1.

Which values are read on which model, and which of them still lack a confirming capture, is listed per model in the [support matrix](../support_matrix.md). It is generated from the decoder's device profiles and a test checks that the committed file matches them; every ❓ in it is a value a recorded test case from that model would settle.

---

[All guides](../README.md#user-guides) · [Troubleshooting](../troubleshooting.md) · [Project home](../../README.md)
