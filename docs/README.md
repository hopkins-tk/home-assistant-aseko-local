# Documentation

[Project home](../README.md) / Documentation

Choose a task below. User guides explain how to use the integration; contributor documentation explains its implementation; research records the evidence and its limits.

## Start here

| I want to… | Open |
| --- | --- |
| Connect a pool unit to Home Assistant | [Get started](guides/getting-started.md) |
| Check my model or a particular value | [Device support](guides/device-support.md) → [Support matrix](support_matrix.md) |
| Understand a missing, disabled or stale value | [Entity states](guides/entities.md) |
| Investigate a problem | [Troubleshooting](troubleshooting.md) |
| Share a useful capture | [Record test cases](guides/recording.md) |
| Change the decoder or add a model | [Contributor reading path](#for-contributors) |

## User guides

| Guide | What you will find |
| --- | --- |
| [Get started](guides/getting-started.md) | HACS and manual installation, listener settings, unit configuration, cloud forwarding |
| [Device support](guides/device-support.md) | Model summary, protocols and unverified mappings |
| [Entity states and freshness](guides/entities.md) | Disabled, unavailable, unknown, offline and restart behaviour |
| [Chemical consumption and canisters](guides/chemical-consumption.md) | Runtime estimates, resets, remaining-volume helpers and utility meters |
| [Water level](guides/water-level.md) | Readings, thresholds and an optional display offset |
| [Device clock and drift](guides/device-clock.md) | Clock offset, the drift alert and summer/winter time |
| [Backwash history and scheduling](guides/backwash.md) | Observed history, time bases, drift-aware classification and manual seeding |
| [Record test cases](guides/recording.md) | Dashboard card, photos, diagnostics, exports and retention limits |
| [Troubleshooting](troubleshooting.md) | Symptoms, diagnostic fields and checks |

## For contributors

Read in this order when changing a decoder or adding a value:

1. [Decoder architecture](decoding-by-device-profile.md) — how frames become entities.
2. [Maintenance rules](maintenance-rules.md) — invariants to preserve around storage, clocks and entity identity.
3. [Evidence rules](evidence-rules.md) — what a confidence label does and does not prove.
4. [Adding a model or a value](adding-a-model.md) — implementation steps, tests and matrix generation.

Use the [research index](research/README.md) to find per-model byte maps and captures.

## Reference and research

- [Support matrix](support_matrix.md) — generated from the decoder profiles; do not edit it by hand.
- [Device analyses](device%20analyzes/README.md) — per-model interpretations, evidence and open questions.
- [Research archive](research/README.md) — captures and clearly marked historical material.

Research is not an installation guide or a guarantee of support. Where an older table conflicts with current profiles and their evidence, use the current profile and support matrix.

## Documentation layout

```text
README.md                       Project overview and entry points
docs/
  README.md                     This documentation index
  guides/                       Task-focused user guides
  troubleshooting.md            Symptom-based reference
  decoding-by-device-profile.md Contributor architecture
  adding-a-model.md              Contributor workflow
  evidence-rules.md              Evidence definitions
  maintenance-rules.md           Invariants
  support_matrix.md             Generated reference
  device analyzes/              Per-model evidence, with an index
  research/                     Captures and historical notes
  images/                       Architecture diagrams and their sources
images/                         User-interface screenshots
```

The established reference paths are kept stable: profile comments, tooling, tests and existing links refer to them. The user guides are separate so a detailed feature explanation does not overwhelm the project overview.

### Keep it readable

- Start with the reader's task, then add the details and limitations.
- Link to the canonical guide instead of copying its explanation into several pages.
- Use one page title, descriptive section headings, short paragraphs and tables for repeated comparisons.
- Keep safety warnings, confidence levels and estimate limitations visible.
- Use repository-relative links and preserve old anchors when moving a public section.
- Update profile evidence and regenerate the matrix when support changes; a visual documentation edit must not upgrade an assumption into a confirmed mapping.
