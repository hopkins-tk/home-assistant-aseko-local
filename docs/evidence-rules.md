# Evidence rules

[Documentation](README.md) / For contributors

Every feature a profile lists carries one `Evidence` entry
(`decoding/evidence.py`), written with a helper that names its status:

```python
from ...evidence import assumed, confirmed, confirmed_on, not_located, observed

evidence={                      # shape of the entries, not real findings
    FeatureA: confirmed("byte[N] 0xMM matches the unit display (2026-09-11)"),
    FeatureB: confirmed_on(AsekoDeviceType.NET, "byte[N] 0xMM (Issue #NNN)"),
    FeatureC: observed("bytes N-M, plausible values in 28 frames"),
    FeatureD: assumed("byte[N] as on OXY"),
    FeatureE: not_located("the manual lists it; byte[N] is something else here"),
}
```

The status decides the mark in the generated
[support matrix](support_matrix.md); the note is free text for people.

| Helper | Mark | Use it when |
|---|---|---|
| `confirmed(note)` | ✅ | the decoded value was compared with the unit display or the Aseko Live app **on this model** |
| `derived(note)` | ✅ | not compared on this model, but it follows from the protocol itself or from confirmed values — say which in the note; not a check of a real unit |
| `confirmed_on(MODEL, note)` / `confirmed_on((MODEL, …), note)` | ✅ only in the named models' columns, ❓ elsewhere | the byte was confirmed on other models and this profile reads it the same way |
| `observed(note)` | 👁 | seen repeatedly in real frames from this model with consistent, plausible values, but never compared with the unit |
| `assumed(note)` | ❓ | taken over from another model or an older decoder, or unverified; nothing contradicts it yet |
| `not_located(note)` with a `decode_v7_not_located` / `decode_v8_not_located` override | 🔍 | the model has the value (menu, manual), but where the frame carries it is unknown; the entity exists and reads unknown |
| feature not listed in the profile | — | the profile does not read it: the model does not have it, or nobody has decoded it yet |

A profile checks its evidence when it is built, i.e. at import, so a mistake
fails before any frame is decoded:

- every entry is an `Evidence` (a plain string is refused), with a note;
- `confirmed_on` names at least one model, and not the profile's own model —
  that would simply be `confirmed`;
- `not_located` goes with a `*_not_located` override, and such an override
  with `not_located` evidence;
- `tests/test_decoding_profiles.py` fails while a feature of any profile has no
  entry at all.

## Writing evidence

- Write what was checked, where and when: bytes/bits, date, issue or PR number,
  number of frames. Serial numbers of other people's units only when they are
  already public in an issue.
- Every profile spells its evidence out in full — nothing is inherited. If you
  copy a reading from another model, say so (`assumed("… as on OXY")`) or use
  `confirmed_on(AsekoDeviceType.OXY, …)`.
- A profile whose every entry has the same reason — no frame of the model has
  been captured, the unit is not mapped — gives that reason once with
  `dict.fromkeys(features, assumed("…"))` and lists the entries that say more
  after it.  Do not do this for a model with real captures: there every entry
  needs its own proof, and a feature added later must fail the test until it
  has one.
- Upgrade a mark only with a capture: a [marked test case](guides/recording.md) or a
  diagnostics download plus what the unit showed at that moment.
- A setting being present in the frame does not mean the hardware is fitted —
  water level, heating and the variable-speed pump can be enabled without the
  accessory. Evidence about a *setting* says so.
- When evidence changes, update the model's
  [device analysis](device%20analyzes/) too and regenerate the matrix:

```bash
python scripts/generate_support_matrix.py
```

`tests/test_support_matrix.py` fails while the committed matrix is out of date.
