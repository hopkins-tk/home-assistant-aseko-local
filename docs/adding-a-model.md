# Adding a model or a value

[Documentation](README.md) / For contributors

<details>
<summary>On this page</summary>

- [1. Collect frames](#1-collect-frames)
- [2. Find the bytes](#2-find-the-bytes)
- [3. Profile](#3-profile)
- [4. A new value (feature)](#4-a-new-value-feature)
- [5. Tests and matrix](#5-tests-and-matrix)

</details>

A short recipe. The design behind it is in
[Decoding by device profile](decoding-by-device-profile.md); what counts as
proof is in [Evidence rules](evidence-rules.md).

## 1. Collect frames

An unmapped unit (v7 `byte[4]` or v8 header type the decoder does not know)
decodes with the *unknown* profile: it gets **no entities**, a warning is
logged, and the diagnostics download lists it under `unrecognised_devices`
with the annotated raw frame and the generic values.

Ask for (or record) marked test cases with the [test-cases card](guides/recording.md) — one change on
the unit per marker — and the zip from **Download new**. The frame next to each
marker is the evidence. `python scripts/frame_log_tool.py DIAGNOSTICS.json --around N`
prints the frames around marker N. For one frame, `python scripts/hex_tools.py HEX --table`
(v7: every byte, `--byteinfo N` for one) and `python scripts/v8_tools.py 'FRAME' --annotate`
(v8: every section value) show the raw values; `--generate-test` prints a test skeleton
whose expected values you fill in from what the unit showed.

## 2. Find the bytes

Compare the frames before and after each marker. Start from the closest known
model's [device analysis](device%20analyzes/) — most v7 models share the layout
and differ in a few bytes (`byte[29]` pump bits, `byte[37]` routing, `byte[53]`
setpoint, flow rates at 99–104). Write the findings into the model's device
analysis, using the common section layout.

## 3. Profile

- New v7 model: add the enum value to `AsekoDeviceType` (`models.py`), map the
  unit type byte in `_MODEL_BY_UNIT_TYPE` (`decoding/profile.py`), create
  `decoding/profiles/v7/<model>.py` and register it in `profiles/v7/__init__.py`
  (`BY_MODEL`) and `profiles/__init__.py` (`ALL_PROFILES`).
- New v8 product line: add the enum value to `AsekoDeviceType` if the model
  is new, extend `model_from_header_type` in `profiles/v8/__init__.py`, create
  `profiles/v8/<model>.py` and register it in `profiles/v8/__init__.py`
  (`BY_MODEL`) and `profiles/__init__.py` (`ALL_PROFILES`). A new firmware of a
  known line needs nothing — it reads with the line's profile.

A profile module is one `Profile(...)`:

```python
MODEL = Profile(
    name="v7 MODEL",
    protocol=Protocol.V7,
    model=AsekoDeviceType.MODEL,
    features=(*IDENTITY, *CHLORINE_PROBES, *FILTRATION, ...),  # groups from common.py
    overrides={AlgaecideFlowRate: "decode_v7_not_located"},
    evidence={...},          # one confirmed(...) / observed(...) / assumed(...) per feature
    flags=frozenset(),       # e.g. AsekoProfileFlag.DELAYS_IN_MINUTES
)
```

List only the features the model has. Use `overrides` only where a capture
shows this model reads a value differently; `decode_v7_not_located` for a value
the model has but nobody has found.

## 4. A new value (feature)

1. Add the field to `AsekoDevice` in `models.py`.
2. Add `decoding/features/<field>.py` with a `Feature` subclass: `field`,
   `decode_v7` / `decode_v8` defaults, named readings for model differences,
   `depends_on` / `optional_depends_on` for values it needs first. Return
   `NOT_PRESENT` when the frame says this unit does not have the value, `None`
   when the frame cannot say right now.

   Report the value as the unit sends it, even when another setting makes it
   moot (backwash times with the backwash schedule off, the VS pump type with
   the pump off): hiding it is the dashboard's job, not the decoder's. A bit of
   a settings byte reads `0xFF` as `None` (`flag_or_none`). See
   [Report what the frame says](decoding-by-device-profile.md#report-what-the-frame-says).

   Never change the value because of another live state. If it misleads
   without one (an output that runs down after its device stops, a condition
   bit evaluated while the function is off), add a `Derived` entry to
   `decoding/derived.py` for the user-facing value and keep this field as
   sent; a value that needs several frames belongs in a tracker. See
   [Derived values](decoding-by-device-profile.md#derived-values-the-user-facing-meaning-beside-the-value-as-sent).
3. Add it to `ALL_FEATURES` in `features/__init__.py`, list it in the profiles that have it.
4. Add the entity description in `sensor.py` / `binary_sensor.py` with
   `feature="<field>"` and the translations in `translations/*.json`. Entities
   are created for every possible feature and enabled once a unit shows it —
   never change an existing entity key.

## 5. Tests and matrix

```bash
python scripts/generate_support_matrix.py
```

- Add the captured frame to `tests/test_decode_v7.py` (or `test_decode_v8.py`)
  with the values the unit showed.
- A profile gets the derived values (`decoding/derived.py`) whose fields it
  lists, without any code of its own: check the "Worked out from other
  fields" section of the regenerated matrix, then add the profile to
  `EXPECTED_DERIVED` in `tests/test_derived.py` and a frame for it to
  `_frame_for`.  Both tests fail until you do, and they decode that frame to
  check every derived value is filled.  If a derived rule does not fit the
  model (it sends the value differently), give the profile a flag the rule
  reads, as HOME's `MENU_BIT_SWITCHES_FILTRATION_OFF` does.

Running the tests:

```bash
# Linux (CI runs this): the full suite, Home Assistant fixtures included
python -m pytest --timeout=10 tests
```

```bash
# Windows: the Home Assistant pytest plugin does not load, so run the suites without it
python -m pytest -q -p no:homeassistant -p no:pytest_homeassistant_custom_component --noconftest --no-cov tests/test_decode_v7.py tests/test_decode_v8.py tests/test_decoding_profiles.py tests/test_support_matrix.py tests/test_frame_log.py tests/test_recording_views.py tests/test_server.py
```

The diagrams in `docs/images/` are rendered from `docs/images/src/*.html`; the
command is in the comment at the top of each file.
- `tests/test_decoding_profiles.py` checks detection and profile consistency;
  `tests/test_support_matrix.py` checks the generated matrix is committed.
