# Chemical consumption and canisters

[Documentation](../README.md) / User guide

Consumption is an estimate from observed pump runtime and flow rate, not a measured volume sent by the unit.

[How the estimate works](#how-the-estimate-works) · [Resetting the canister counter](#resetting-the-canister-counter) · [Optional: Track remaining canister volume](#optional-track-remaining-canister-volume)

## How the estimate works

From the first frame in which a pump is seen running, every following frame adds the time since the previous one multiplied by the pump's flow rate in ml/min, as set on the unit.

The estimate depends on two mappings: the pump-running bit and its flow rate. Check both in the [support matrix](../support_matrix.md); a ❓ or 🔍 means the result is rough or unavailable.

- Each interval contributes at most 30 seconds, so a long gap is not counted as continuous dosing.
- The interval up to the frame in which the pump stops is included.
- Millilitres are stored without rounding to litres. An abrupt HA shutdown can lose the last minute before the save.

Two consumption sensors per pump (the names below are the entity names; pick the entity IDs from your own Home Assistant):

- **… consumed (since refill)** — back to zero when you refill the canister and reset it.
- **… consumed (total)** — a running total that never resets on its own.
- **Reset Button** — a dashboard button to reset the *since last reset* counter after refilling a canister.
- **Pump state** — the integration also decodes pump states (on/off) from the raw data, so you can track when pumps are running in real time and you can analyze the history like how often and how long running.
- **Other information** like canister fill-up volume and remaining volume can be tracked using standard Home Assistant helpers and templates — see below for details.

Here is an example of the consumption sensors and canister settings in Home Assistant:

![Consumption dashboard example](../../images/aseko_dashboard_example.png)

## Resetting the canister counter

After refilling a chemical canister trigger a reset so the *since last reset* counter starts from zero again.

**Option 1 – Dashboard button**

Add a **button card** or an **entity card** and choose the pump's **refill reset** button entity (see image above).

**Option 2 – Developer Tools**

Go to **Developer Tools → Actions**, search for `aseko_local.reset_consumption` and call it with the pump you refilled (or `all`) and counter `canister`. With this method you can also reset the *total* counter, which is not possible with the dashboard button.

![Reset consumption via Developer Tools](../../images/aseko_action_reset.png)

## Optional: Track remaining canister volume

Aseko's own app counts down the remaining chemical volume in a canister. You can replicate this in Home Assistant using two standard helpers.

**Step 1 – Number helper for fill-up amount**

Go to **Settings → Devices & Services → Helpers → Create helper → Number** and create one helper per chemical, e.g.:

| Field | Example value |
|---|---|
| Name | PH Minus fill-up |
| Minimum | 0 |
| Maximum | 25 |
| Step | 0.1 |
| Unit of measurement | L |

When you refill the canister, set this helper to the **whole volume now in the canister** (not only what you added — the reset starts counting from zero), then press the reset.

![Number helper for canister fill-up](../../images/aseko_number_canister_fill-up.png)

**Step 2 – Template sensor for remaining volume**

Go to **Settings → Devices & Services → Helpers → Create helper → Template → Template sensor** and configure it as follows:

| Field | Example value |
|---|---|
| Name | PH minus remaining fill |
| State template | `{{ states('input_number.ph_minus_fill_up') \| float - states('sensor.YOUR_PH_MINUS_CONSUMED_SINCE_REFILL') \| float }}` |
| Availability template | `{{ has_value('input_number.ph_minus_fill_up') and has_value('sensor.YOUR_PH_MINUS_CONSUMED_SINCE_REFILL') }}` |
| Unit of measurement | L |
| Device class | Volume |

Replace the entity IDs with your own helper and sensor. The availability template keeps the sensor unavailable while a value is missing, instead of showing a full canister.

![Template sensor for remaining canister volume](../../images/aseko_template_sensor_remaining.png)

**Step 3 – Utility meter for daily, weekly or monthly usage**

Go to **Settings → Devices & Services → Helpers → Create helper → Utility Meter**:

- Name: PH minus daily usage
- Input sensor: the pump's **… consumed (total)** sensor — the total never resets, so each period is simply its growth
- Meter reset cycle: Daily (or Weekly, Monthly …)

The meter takes its unit (L) from the input sensor.

**Step 4 – Add everything to a dashboard card**

Combine the fill-up number input, the *since last reset* sensor, the remaining volume template sensor, and a reset button into a single dashboard card for a complete canister management view.

---

[All guides](../README.md#user-guides) · [Troubleshooting](../troubleshooting.md) · [Project home](../../README.md)
