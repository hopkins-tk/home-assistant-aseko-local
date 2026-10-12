# Water level

[Documentation](../README.md) / User guide

For ASIN Aqua Home, Salt and Oxy. Availability depends on the model's profile and the sensor configuration.

[Readings and thresholds](#readings-and-thresholds) · [Optional: Correct the reading with an offset helper](#optional-correct-the-reading-with-an-offset-helper)

## Readings and thresholds

Devices with a built-in water-level sensor expose the following entities:

| Entity | Unit | Description |
|---|---|---|
| Water level | cm | Current water level (real-time) |
| Refilling | — | on while the auto-fill valve is open |
| Water level low alarm | cm | Low-level alarm threshold |
| Refill start level | cm | Threshold that opens the auto-fill valve |
| Refill stop level | cm | Threshold that closes the auto-fill valve |
| Water level high alarm | cm | High-level alarm threshold |

The level sensor sits at the bottom and measures the **distance from the sensor up to the water surface** in centimetres — the water height above the sensor, so the value rises while the pool fills. It is what the unit and the Aseko Live app show, so no adjustment is needed for a standard installation. Confirmed on an ASIN Aqua Salt; the thresholds use the same scale.

## Optional: Correct the reading with an offset helper

If your sensor is mounted at a different height than the Aseko factory default (e.g. relocated, installed in a skimmer with an unusual standoff), the displayed centimetres will be off by a constant. You can apply a fixed offset using a Home Assistant template helper.

1. **Settings → Devices & Services → Helpers → Create helper → Number** named *Water level offset* with unit `cm`, min `-100`, max `250`, step `1`. Default value `0`.
2. **Settings → Devices & Services → Helpers → Create helper → Template sensor**:

   | Field | Value |
   |---|---|
   | Name | Pool water level (corrected) |
   | State template | `{{ states('sensor.YOUR_WATER_LEVEL') \| float + states('input_number.water_level_offset') \| float }}` |
   | Availability template | `{{ has_value('sensor.YOUR_WATER_LEVEL') and has_value('input_number.water_level_offset') }}` |
   | Unit of measurement | cm |
   | Device class | Distance |

Replace the entity ID with your water level sensor. Devices without a water-level sensor (e.g. NET) do not have these entities; on a unit whose sensor is not connected they are unavailable.

---

[All guides](../README.md#user-guides) · [Troubleshooting](../troubleshooting.md) · [Project home](../../README.md)
