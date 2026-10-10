# Device support

[Documentation](../README.md) / User guide

Support depends on both the model and the value. Use the summary below to orient yourself, then check the per-value matrix for evidence.

[Supported devices](#supported-devices) · [Not supported yet](#not-supported-yet) · [Help verify support](#help-verify-support)

## Supported devices

✅ checked on this model, or derived from the protocol · 👁 seen in real frames, not compared with the unit · ❓ assumed, not checked on this model · 🔍 not located in the frame · — not read. Per value: [support matrix](../support_matrix.md).

| Device | Firmware | Sensors | Pump state | Chemical consumption |
|---|---|---|---|---|
| ASIN Aqua Net | ≤ 7.x | ✅ | ✅ cl, pH− | ✅ cl, pH− |
| ASIN Aqua Net | 8.x | ✅ | ✅ filtration · ❓ cl, pH− | ❓ cl, pH− |
| ASIN Aqua Salt | ≤ 7.x | ✅ | ✅ filtration, electrolyzer, algicide, flocculant · ❓ pH− | ✅ algicide, flocculant · ❓ pH− |
| ASIN Aqua Oxy | ≤ 7.x | 👁 pH, temperature | ✅ filtration, oxy, algicide, flocculant, pH− | ✅ oxy, algicide, flocculant, pH− |
| ASIN Aqua Home | ≤ 7.x | ✅ | ✅ filtration · ❓ cl, algicide, flocculant, pH− | ❓ cl, flocculant, pH− · 🔍 algicide (flow rate not located, not counted) |
| ASIN Aqua Salt NET | 8.x | ❓ | ❓ filtration, pH− | ❓ pH− |
| ASIN Aqua Profi | ≤ 7.x | ❓ no real frame yet | ❓ filtration, cl, flocculant, pH− | ❓ cl, flocculant, pH− |

> **Firmware note:** This integration supports both the **120-byte binary protocol** (firmware ≤ 7.x, port **47524**) and the **text-frame protocol** (firmware 8.x, port **51050**). The port can be changed in the integration settings to match your device.

## Not supported yet

| Device | Status |
|---|---|
| ASIN Aqua Pro | ❔ unit type not mapped: the unit gets no entities, but its frames reach the diagnostics — please share them (see [Record test cases](recording.md)) |
| ASIN Aqua Home Pro, Salt Pro, Home Pro Oxy, Eox Pro (07.2026) | ❔ as above |
| ASIN Aqua Net+ | ❔ as above |
| ASIN Aqua | ❌ no network connection |

See [Entity states](entities.md) for values that are disabled, unavailable or not decoded.

## Help verify support

A raw frame and a matching display photo can turn an assumption into checked evidence. Follow [Record test cases](recording.md), especially for a ❓ in the [support matrix](../support_matrix.md).

---

[All guides](../README.md#user-guides) · [Troubleshooting](../troubleshooting.md) · [Project home](../../README.md)
