# Aseko Local

**Your pool data, directly in Home Assistant.**

Receive readings and operating states from your network-connected ASEKO unit over the local network. Cloud forwarding is optional; available values and their confidence depend on the model.

[Get started](docs/guides/getting-started.md) · [Device support](docs/guides/device-support.md) · [Documentation](docs/README.md) · [Troubleshooting](docs/troubleshooting.md)

[![HACS](https://img.shields.io/badge/HACS-Default-orange.svg?style=flat-square)](https://github.com/custom-components/hacs)

## What you get

| Feature | What it means |
| --- | --- |
| Measurements and operating states | pH, temperature, pumps, filtration, settings and alarms where mapped for your model |
| Chemical consumption | Estimates from observed pump runtime and flow rate, with canister resets |
| Backwash history | Observed valve cycles, drift-aware classification and a projected schedule |
| Clock diagnostics | The difference between the unit's clock and HA, with a configurable drift alert |
| Test-case recording | Frames, notes and optional display photos to help verify device support |

This is a **local-push monitoring integration**. It receives the unit's data; it does not provide commands to change the unit's pool settings.

<details>
<summary>Preview: ASIN Aqua Salt entities in Home Assistant</summary>

![ASIN Aqua Salt entities in Home Assistant](images/sensors-salt.png)

</details>

## Get started

1. **Install** Aseko Local through HACS and restart Home Assistant.
2. **Add the integration** under **Settings → Devices & Services**. Choose its listening address and TCP port.
3. **Point the unit at HA:** set its remote server address to Home Assistant's LAN address and its remote port to the same listener port.
4. **Check reception** in the device's entities. If data is missing, start with [Troubleshooting](docs/troubleshooting.md).

[![Open Aseko Local in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?repository=aseko-local&owner=hopkins-tk)

The common ports are **47524** for v7 binary frames and **51050** for v8 text frames. Both are configurable; the integration detects the protocol from the data. The default binding address `0.0.0.0` is where HA listens, **not the unit's IP address**.

[Full setup guide with screenshots](docs/guides/getting-started.md) · [Manual installation](docs/guides/getting-started.md#manual-installation) · [Optional cloud forwarding](docs/guides/getting-started.md#optional-cloud-forwarding)

> **Keep it local.** The unit's TCP data is unencrypted. Allow it only within a trusted network; do not expose the listener to the internet.

## Device support

Support is tracked **per model and per value**. A profile being available does not mean every function has been verified.

- ✅ **Checked / derived** — checked on this model, or derived from the protocol.
- 👁 **Observed** — seen in real frames, not yet compared with the unit's display.
- ❓ **Assumed** — implemented, but not verified on this model.
- 🔍 **Not located** — the value's position in the frame is not known.
- — **Not read** — not decoded by the profile.

### Supported devices

| Device | Firmware | Sensors | Pump / output states | Chemical consumption |
| --- | --- | --- | --- | --- |
| **ASIN Aqua NET** | ≤ 7.x | ✅ | ✅ chlorine, pH− | ✅ chlorine, pH− |
| **ASIN Aqua NET** | 8.x | ✅ | ✅ filtration<br>❓ chlorine, pH− | ❓ chlorine, pH− |
| **ASIN Aqua SALT** | ≤ 7.x | ✅ | ✅ filtration, electrolyzer, algicide, flocculant<br>❓ pH− | ✅ algicide, flocculant<br>❓ pH− |
| **ASIN Aqua OXY** | ≤ 7.x | 👁 pH, temperature | ✅ filtration, oxy, algicide, flocculant, pH− | ✅ oxy, algicide, flocculant, pH− |
| **ASIN Aqua HOME** | ≤ 7.x | ✅ | ✅ filtration<br>❓ chlorine, algicide, flocculant, pH− | ❓ chlorine, flocculant, pH−<br>🔍 algicide — not calculated |
| **ASIN Aqua Salt NET** | 8.x | ✅ salinity, pH, redox, temperature | ✅ electrolyzer<br>👁 algicide or flocculant<br>❓ filtration, pH− | 👁 algicide or flocculant<br>❓ pH− |
| **ASIN Aqua PROFI** | ≤ 7.x | ❓ no real frame yet | ❓ filtration, chlorine, flocculant, pH− | ❓ chlorine, flocculant, pH− |

**Consumption is always an estimate** from pump runtime and flow rate, not a measured volume sent by the unit. The marks above describe confidence in the underlying mappings.

Firmware ≤ 7.x uses 120-byte binary frames; firmware 8.x uses text frames. **PROFI is a provisional profile**, not a verified device; on the **Salt NET** the salt values are checked against an owner's display and the rest is the NET v8 layout taken over (see [SALT NET v8](docs/device%20analyzes/salt_net_v8_device_analysis.md)).

### Not supported yet

| Device | Status | What would help |
| --- | --- | --- |
| **ASIN Aqua Pro** | ❔ Unit type not mapped; support unconfirmed | Diagnostics and a marked capture |
| **ASIN Aqua Home Pro, Salt Pro, Home Pro Oxy, Eox Pro** | ❔ Unit type not mapped; support unconfirmed | Diagnostics and a marked capture |
| **ASIN Aqua Net+** | ❔ Unit type not mapped; support unconfirmed | Diagnostics and a marked capture |
| **ASIN Aqua** | ❌ No network connection | Not supported by this network integration |

❔ means **potential support needs investigation**, not that the device already works. Unmapped units get no normal entities; received frames can still appear in diagnostics and recordings to help add support.

[Per-value support matrix](docs/support_matrix.md) · [Evidence rules](docs/evidence-rules.md) · [Help verify your device](docs/guides/recording.md)

## Understand your data

| Topic | Guide |
| --- | --- |
| Disabled, unavailable, unknown or offline? | [Entity states and freshness](docs/guides/entities.md) |
| Consumption, refills and remaining volume | [Chemical consumption and canisters](docs/guides/chemical-consumption.md) |
| Water-level readings and thresholds | [Water level](docs/guides/water-level.md) |
| Summer/winter time and a drifting unit clock | [Device clock and drift](docs/guides/device-clock.md) |
| Scheduled vs. manual backwash, history and seeding | [Backwash history and scheduling](docs/guides/backwash.md) |

**Offline keeps the last values by design.** Check connection status and the age of the last frame to judge freshness. Consumption and future backwash times are estimates, not measurements reported by the unit.

## Help verify a device

A useful test case connects **one change on the unit** with **the next frame** and, ideally, a photo of the display. Add the administrator-only card to a dashboard:

```yaml
type: custom:aseko-test-cases-card
```

The integration loads its resource automatically. Turn recording on, make one change, mark it, wait for the frame, then download the cases. Recording is off until you enable it.

[Recording guide and limits](docs/guides/recording.md) · [Report an issue](https://github.com/hopkins-tk/home-assistant-aseko-local/issues/new)

> Exports contain unit identifiers and may include display photos. Review them before sharing publicly.

## For contributors

Start with [Decoder architecture](docs/decoding-by-device-profile.md) and [Maintenance rules](docs/maintenance-rules.md). Then use [Adding a model or a value](docs/adding-a-model.md), [Evidence rules](docs/evidence-rules.md) and the [Device analyses](docs/device%20analyzes/README.md).

The [documentation index](docs/README.md) separates user guides, contributor references and historical research. The support matrix is generated from profiles, not maintained by hand.

<details>
<summary>Looking for a section from the previous README?</summary>

The detailed sections now live in the guides above. Existing section links are kept here.

<a id="summary"></a>

[Project overview](#what-you-get).

[Device support](docs/guides/device-support.md).

<a id="help-wanted--expanding-device-support"></a>
<a id="1-record-test-cases-with-the-card-recommended"></a>
<a id="2-diagnostics-only"></a>
<a id="3-without-the-card-the-aseko_localmark_dump-action"></a>

[Recording and diagnostics](docs/guides/recording.md).

<a id="entities-that-appear-later-or-go-unavailable"></a>

[Entity states](docs/guides/entities.md).

<a id="installation"></a>
<a id="via-hacs---recommended"></a>
<a id="manual-installation"></a>
<a id="configure-your-aseko-unit"></a>
<a id="aseko-unit-configuration"></a>
<a id="optional-send-data-to-aseko-cloud"></a>

[Installation and unit configuration](docs/guides/getting-started.md).

<a id="unit-clock"></a>

[Unit clock](docs/guides/device-clock.md).

<a id="chemical-consumption--canister-management"></a>
<a id="resetting-the-canister-counter"></a>
<a id="optional-track-remaining-canister-volume"></a>

[Chemical consumption and canister management](docs/guides/chemical-consumption.md).

<a id="water-level-asin-aqua-home-salt-oxy"></a>
<a id="optional-correct-the-reading-with-an-offset-helper"></a>

[Water level](docs/guides/water-level.md).

<a id="backwash-asin-aqua-home-salt-oxygen-profi"></a>
<a id="observed-vs-estimated"></a>
<a id="seeding-the-schedule-by-hand"></a>
<a id="upgrading-from-a-store-that-predates-the-split"></a>
<a id="known-ways-the-estimate-gets-it-wrong"></a>

[Backwash](docs/guides/backwash.md).

</details>
