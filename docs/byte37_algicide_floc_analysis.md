# byte[37] – Algicide vs. Flocculant routing analysis

## Data basis

Three raw frames from your SALT unit (S/N cleared), one from Issue #84, and one Aqua NET.
Extracted with `scripts/hex_tools.py --generateTest`.

### byte[37] and byte[54] (required dosage)

| Record | byte[37] hex | binary | byte[54] |
|--------|-------------|--------|----------|
| Your SALT – Algicide 10 ml/m³/day | `0xb7` | 1011 0111 | 10 |
| Your SALT – Algicide 11 ml/m³/day | `0xb3` | 1011 0011 | 11 |
| Your SALT – Flocculant 11 ml/h    | `0x37` | 0011 0111 | 11 |
| Issue #84 SALT – Algicide         | `0x13` | 0001 0011 | 4  |
| Aqua NET (no third pump)           | `0xff` | 1111 1111 | — |

### byte[101] and byte[103] (flowrates for third pump slot)

| Record | byte[101] | byte[103] |
|--------|-----------|-----------|
| Your SALT – Algicide 10 | 60 ml/min | 60 ml/min |
| Your SALT – Algicide 11 | 60 ml/min | 60 ml/min |
| Your SALT – Flocculant 11 | 60 ml/min | 60 ml/min |
| Issue #84 SALT – Algicide | 60 ml/min | 60 ml/min |
| Aqua NET | 0xff (undef) | 0x03 (phantom) |

**Conclusion on byte[101] vs byte[103]:** The pump slot does **not** flip between bytes
when switching between algicide and flocculant. Both bytes always carry 60 ml/min on
SALT devices, regardless of which chemical is configured. byte[101] and byte[103] are
therefore not "algicide slot" and "flocculant slot" — they are both populated with the
configured flowrate. The NET has 0xff on both, with a known phantom value of 3 on byte[103].

---

## byte[37] is not a simple configuration flag

XOR analysis of the three SALT records:

| Comparison | XOR | Changed bits |
|------------|-----|-------------|
| Algicide 10 → Algicide 11 (same type, dosage +1) | `0x04` | bit 2 only |
| Algicide 11 → Flocculant 11 (same dosage, type change) | `0x84` | bit 7 + bit 2 |
| Algicide 10 → Flocculant 11 (both change) | `0x80` | bit 7 only |

**bit 7 (`0x80`)** toggles exactly when the chemical type changes (for your firmware).
**bit 2 (`0x04`)** changes together with the dosage when the type also changes — suggesting
byte[37] encodes multiple fields packed together, not just a single configuration flag.

---

## Why a single bitmask cannot cover both firmware variants

| Mask candidate | Your Algicide `0xb7` | Your Algicide `0xb3` | **Your Floc `0x37`** | #84 Algicide `0x13` |
|---------------|----------------------|----------------------|----------------------|---------------------|
| `0x80` (bit 7) | ✅ | ✅ | ✅ correct (0) | ❌ misses algicide |
| `0x10` (bit 4) | ✅ | ❌ misses algicide | ❌ **false positive** | ✅ |
| `0x80 \| 0x10` (OR) | ✅ | ✅ | ❌ **false positive** | ✅ |

No single bit or OR combination correctly distinguishes algicide from flocculant
across both SALT units. The two units encode byte[37] differently — most likely
due to different firmware versions. Since Aseko only updates firmware at the factory
(see [#49](https://github.com/hopkins-tk/home-assistant-aseko-local/issues/49)),
this divergence is likely permanent.

---

## Proposed solution for v1.4.0: unified `pump_2` entity

Since the chemical type on the third pump slot cannot be determined reliably from byte[37],
and the flow rate is always 60 ml/min regardless of the chemical, we propose merging
algicide and flocculant into a single **`pump_2`** entity:

- **Binary sensor / pump running**: `pump_2_running` (based on byte[29] mask, same bit for both)
- **Consumption sensors**: `pump_2_canister_ml` / `pump_2_total_ml` — chemically neutral, unit: litres
- **Flowrate sensor**: byte[101], same as before
- **`required` sensor**: omitted for v1.4.0 — byte[54] value is shared, but the unit
  (ml/m³/day for algicide vs. ml/h for flocculant) cannot be determined reliably
- **byte[37]** is preserved as a raw diagnostic value in the Diagnostics dump — useful
  for future reverse-engineering once more frames from both firmware variants are available

This avoids wrong labels and wrong units in HA, while keeping all consumption
and pump-running data correct for both firmware variants.

Once the byte[37] encoding is fully understood, the routing logic can be re-introduced
in a later release.

---

## Open question for you

Can you capture a Diagnostics dump **immediately after switching** the SALT unit between
Algicide and Flocculant mode? We are specifically interested in whether:
- byte[37] bit 7 (`0x80`) is the only bit that changes (confirming it as the type flag for your firmware)
- byte[54] changes value (or stays the same with just a unit change)
- any other bytes change

Two captures — one with algicide, one with flocculant, same dosage value — would be ideal.
