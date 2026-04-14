# Plan: fw v8 Text-Frame Support

Branch: `feat/net-v8-decoder`
Based on: `feat/pump-monitoring-consumption` (will become v1.4.0)
After v1.4.0 is merged to main: `git fetch origin && git rebase origin/main`

---

## Background

Aseko devices with firmware v8 no longer send a 120-byte binary block.
Instead they send a human-readable text frame (example from Issue #49, ASIN AQUA NET):

```
{v1 110203680 804 0 27 ins: 314 -500 -500 -500 0 0 0 0 1 -500 -500 -500 0 24 6 29 21 40 0 ains: 708 708 774 7790 0 0 779 779 0 0 0 0 0 0 0 0 outs: 0 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 areqs: 74 74 4 5 0 36 36 0 0 0 6 0 36 0 45 0 255 2 2 10 0 15 0 0 0 0 reqs: 0 0 0 0 0 0 0 24 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 10 10 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 fncs: 0 0 3 0 0 0 2 0 mods: 2 0 0 1 0 0 0 0 flags: 2 0 0 0 0 0 0 0 crc16: C3C8}
```

Frame structure:
- Header: `{v1 <serial> <field2> <field3> <field4>`
- Sections: `ins:` `ains:` `outs:` `areqs:` `reqs:` `fncs:` `mods:` `flags:` `crc16:`
- Delimiters: `{` … `}`
- Size: 463 bytes (vs. 120 bytes for binary frames)

---

## Architecture Decisions

| Topic | Decision | Reason |
|---|---|---|
| Server | Single server, single port | No extra config, no second process |
| Frame detection | After reading 120 bytes: search for `{` | Robust even if TCP delivers mid-frame |
| Text-frame sync | `readuntil(b'}')` once `{` is found | Unambiguous delimiters, no magic-byte guessing |
| Binary-frame sync | Existing `_rewind_frame` logic, renamed to `_rewind_binary` | Logic unchanged |
| Shared sync entry point | `_sync_frame(reader)` | Makes it clear both frame types are handled the same way |
| New decoder | `aseko_decoder_v8.py` / `AsekoV8Decoder` | v8 = firmware architecture version, not device-specific |
| Device type | Reuse `AsekoDeviceType.NET` | Same entities, no HA entity re-registration on update |
| Mirror forwarder | Forward raw bytes unchanged | Aseko Cloud understands the text format itself |
| Forwarder port v7 | `pool.aseko.com:47524` | Existing binary-frame port (unchanged) |
| Forwarder port v8 | `pool.aseko.com:51050` | New text-frame port for fw v8 |
| Port config (user) | No extra options flow fields | Server auto-routes by `FrameType`; ports defined in `const.py` for easy bugfix releases |
| Two devices, mixed fw | Single receiving port on HA side | Each device has its own TCP connection — no data mixing possible; `_sync_frame` operates per-connection |

---

## Step 1 — Pre-Release: Logging & Forwarding for fekberg

**Status:** ✅ Done

**Goal:** Build a minimal release that fekberg installs manually.
The server receives v8 text frames, logs them as WARNING (visible without debug mode)
and forwards them to `pool.aseko.com:51050` so his Aseko Cloud keeps working.
No decoding, no new entities.

**This release will not be published publicly** — fekberg installs the files manually.

**Changes for the pre-release:**

1. `aseko_server.py` — add `_sync_frame()` (frame detection + logging only):
   - v8 frame detected → log as WARNING (full raw text)
   - forward v8 frame via forwarder callback (raw bytes)
   - do **not** pass v8 frame to `AsekoDecoder.decode()` (no decoder yet)

2. `mirror_forwarder.py` — make port configuration v8-aware:
   - forward v8 frames to `pool.aseko.com:51050`
   - forward v7 frames to `pool.aseko.com:47524` (unchanged)
   - distinguish by `FrameType` passed alongside the bytes

3. `const.py` — two constants (replaces the single user-configurable port):
   ```python
   DEFAULT_FORWARDER_PORT_V7 = 47524   # rename existing DEFAULT_FORWARDER_PORT
   DEFAULT_FORWARDER_PORT_V8 = 51050   # new
   ```

4. `config_flow.py` — remove `forwarder_port` from the options flow:
   - Remove the `forwarder_port` field from `OptionsFlowHandler`
   - Remove `CONF_FORWARDER_PORT` from the options schema
   - The port is no longer stored in config entry options; it is resolved at runtime from `FrameType`
   - **Migration:** existing config entries that have a stored `forwarder_port` value must be ignored gracefully (the field is simply no longer read)

5. `translations/*.json` — remove `forwarder_port` label from all language files (`en`, `de`, `cs`, `fr`)

**No decoding, no new entities, no tests required for this step.**

---

## Step 2 — Field Mapping (after data collection)

**Status:** ✅ Done

Cross-referenced two real frames (Sep 16 2025, Apr 13 2026) against Aseko Pool Live
app screenshots provided by fekberg (Apr 13 2026).

| Section | Index | Formula | AsekoDevice field | Confirmed by |
|---|---|---|---|---|
| Header | 1 | `int` | `serial_number` | Serial matches device |
| `ins:` | 0 | `÷ 10` → °C | `water_temperature` | 31.4°C Sep / 18.1°C Apr ✓ |
| `ins:` | 8 | `bool` | `water_flow_to_probes` | App shows YES, value=1 ✓ |
| `ins:` | 16 | local hour | timestamp (hour) | Matches HA log timestamps ✓ |
| `ins:` | 17 | local minute | timestamp (minute) | Matches HA log timestamps ✓ |
| `ains:` | 0 | `÷ 100` → pH | `ph` | 7.08 Sep / 6.49 Apr ✓ |
| `ains:` | 6 | direct mV | `redox` | 779 mV Sep / 809 mV Apr ✓ |
| `outs:` | 2 | `bool` | `filtration_pump_running` | App shows Pump: ON ✓ |
| `areqs:` | 0 | `÷ 10` | `required_ph` | App shows 7.4 ✓ |
| `areqs:` | 1 | `× 10` | `required_redox` | App shows 740 mV (74×10=740) ✓ |
| `areqs:` | 14 | direct m³ | `pool_volume` | App shows 45 m³ ✓ |
| `areqs:` | 17 | direct min | `delay_after_startup` | App shows 2 min ✓ |
| `areqs:` | 18 | direct min | `delay_after_dose` | App shows 2 min ✓ |
| `crc16:` | — | hex string | (ignored for now) | — |

**Sentinel value:** `-500` in `ins:`/`ains:` means probe absent → map to `None`.

**Device type:** always `AsekoDeviceType.NET` for fw v8 (confirmed: ASIN AQUA NET).

**Configuration:** `{AsekoProbeType.PH, AsekoProbeType.REDOX}` detected dynamically:
PH probe present if `ains[0] != -500`; REDOX probe present if `ains[6] != -500`.

**Timestamp:** `datetime.now()` adjusted to device hour/minute (`ins[16]`, `ins[17]`).
Date fields in `ins[13–15]` are present but semantics not yet confirmed — falling back
to today's date from HA clock.

**Unknown / not yet mapped:**
- `ains[2]` — consistently 5 mV below `ains[6]` (Redox); purpose unclear
- `ins[13–15]` — vary between frames; date-related but exact semantics unknown
- `outs[0]`, `outs[1]` — dosing pump states (cl / pH−); pattern not yet confirmed

---

## Step 3 — Full `aseko_server.py` refactor

**Status:** ✅ Done

**Goal:** Refactor `_handle_client()` to fully support both frame types.

**Changes:**

1. Rename `_rewind_frame()` → `_rewind_binary(data: bytes) -> tuple[bytes, int]`
   - Internal helper, logic unchanged

2. New method `_sync_frame(reader, initial: bytes) -> tuple[bytes, FrameType]`
   - `initial` = the first 120 bytes already read
   - If `b'{'` found in `initial`: text path
     - Locate position of `{`
     - `reader.readuntil(b'}')` for the rest
     - Return complete frame + `FrameType.V8`
   - Otherwise: binary path
     - Call `_rewind_binary(initial)`
     - Return `(rewound_frame, offset)` + `FrameType.BINARY`

3. `_handle_client()` loop:
   - Read initial 120 bytes (unchanged)
   - Call `_sync_frame()`
   - Depending on `FrameType`: call `AsekoDecoder.decode()` or `AsekoV8Decoder.decode()`
   - pH plausibility check only for binary frames (text frames have their own validation)

**New constant in `const.py`** (or as an Enum in `aseko_server.py`):
```python
class FrameType(Enum):
    BINARY = "binary"
    V8 = "v8"
```

---

## Step 4 — Create `aseko_decoder_v8.py`

**Status:** ✅ Done

**File:** `custom_components/aseko_local/aseko_decoder_v8.py`

**Class:** `AsekoV8Decoder`

```python
class AsekoV8Decoder:
    @classmethod
    def decode(cls, raw: bytes) -> AsekoDevice:
        text = raw.decode("ascii")
        # Parse header: {v1 <serial> ...
        # Parse sections: ins:, ains:, outs:, areqs:, reqs:, fncs:, mods:, flags:, crc16:
        # Map to AsekoDevice fields
        # Return AsekoDevice(...)
```

**Optional CRC16:** implement validation once field mapping is complete.

---

## Step 5 — Tests

**Status:** ✅ Done

**File:** `tests/test_aseko_decoder_v8.py`

Fixture: frame from Issue #49 (above).

Minimum assertions:
- `serial_number == 110203680`
- `device_type == AsekoDeviceType.NET`
- All mapped fields match their expected values

---

## Step 6 — Sensor guards (if needed)

**Status:** ⬜ Todo (after Step 5 — check if NET v8 exposes sensors not present in binary frames)

If the v8 frame exposes different sensors than v7 (e.g. no `required_floc`),
guards need to be added in `sensor.py` — same pattern as existing `device_type` checks.

---

## Open Issues

| # | Description | Status |
|---|---|---|
| 1 | Field mapping ins:/ains:/outs: → AsekoDevice | ⏳ Needs raw data from fekberg (after Step 1) |
| 2 | Implement CRC16 validation? | ⏳ Decision pending |
| 3 | Header fields `804 0 27` after serial — meaning? | ⏳ Unknown |
| 4 | Are there v8 frames from other device types (SALT, OXY)? | ⏳ Unknown |
| 5 | Set a max size limit for `readuntil` call? | ⏳ Security review needed |
| 6 | Forwarder port v8: `51050` — confirmed by Aseko? | ⏳ From Issue #49, not yet verified |

---

## Affected Files

| File | Change | From step |
|---|---|---|
| `custom_components/aseko_local/aseko_server.py` | Frame detection + v8 logging (pre-release) → full refactor later | 1 / 3 |
| `custom_components/aseko_local/mirror_forwarder.py` | Port routing v7→47524, v8→51050 | 1 |
| `custom_components/aseko_local/const.py` | Add `DEFAULT_FORWARDER_PORT_V7/V8`; rename existing constant | 1 |
| `custom_components/aseko_local/config_flow.py` | Remove `forwarder_port` field from options flow | 1 |
| `custom_components/aseko_local/translations/en.json` | Remove `forwarder_port` label | 1 |
| `custom_components/aseko_local/translations/de.json` | Remove `forwarder_port` label | 1 |
| `custom_components/aseko_local/translations/cs.json` | Remove `forwarder_port` label | 1 |
| `custom_components/aseko_local/translations/fr.json` | Remove `forwarder_port` label | 1 |
| `custom_components/aseko_local/aseko_decoder_v8.py` | NEW | 4 |
| `tests/test_aseko_decoder_v8.py` | NEW | 5 |
| `custom_components/aseko_local/aseko_data.py` | No changes expected | — |
| `custom_components/aseko_local/sensor.py` | Only if sensor guards needed | 6 |
| `README.md` | Forwarder port documentation v7 vs v8 | 1 |
