# Research and evidence

[Documentation](../README.md) / Research

Protocol observations and supporting captures, separate from the [user guides](../README.md#user-guides). Confidence is recorded per value; a plausible byte map is not proof that a model behaves that way.

## Current model analyses

Start with the [device analysis index](../device%20analyzes/README.md), then compare its findings with the [support matrix](../support_matrix.md) and the model's profile.

When contributing new evidence, follow [Evidence rules](../evidence-rules.md) and [Adding a model](../adding-a-model.md).

## Captures

| Capture | Context |
| --- | --- |
| [NET v7 — capture A](captures/net-v7-110200612-a.md) | First of two consecutive frames supplied with the forwarder change; capture date unknown |
| [NET v7 — capture B](captures/net-v7-110200612-b.md) | Second frame of the same NET unit; useful for comparing changing bytes |

The capture tables show overlapping big-endian words, not a list of independent protocol fields.

## Historical material

[Legacy byte map](legacy-byte-map.md) is retained for historical context. It is superseded and contains known incorrect mappings. **Do not implement from it**; use the current per-model analyses, profiles and evidence.

## Collect better evidence

Use [Record test cases](../guides/recording.md) to associate a single change on the unit with the next frame and an optional display photo. Review identifiers and photos before publishing an export.
