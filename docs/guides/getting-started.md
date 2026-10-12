# Get started

[Documentation](../README.md) / User guide

Install the integration, choose a listening port, then point the unit at Home Assistant.

<details>
<summary>On this page</summary>

- [Before you start](#before-you-start)
- [Install](#install)
- [Add the integration](#add-the-integration)
- [Configure the unit](#configure-the-unit)
- [Cloud forwarding](#optional-cloud-forwarding)

</details>

## Before you start

- Check your model in [Device support](device-support.md). The [support matrix](../support_matrix.md) gives the evidence for each value.
- The unit must be able to reach Home Assistant on your local network. Allow the listener port through any intervening VLAN or firewall.
- Keep a note of the unit's original remote address and port before changing them.

> **Trusted network only.** The unit sends unencrypted TCP data. Do not expose the integration's listener port to the internet.

## Install

### HACS — recommended

[![Open Aseko Local in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?repository=aseko-local&owner=hopkins-tk)

Install **Aseko Local**, then restart Home Assistant.

### Manual installation

1. Download and extract the source archive from the [release page](https://github.com/hopkins-tk/home-assistant-aseko-local/releases).
2. Copy the archive's `custom_components/aseko_local` directory to `<config>/custom_components/aseko_local`.
3. Restart Home Assistant.

## Add the integration

Open **Settings → Devices & Services → Add integration** and select **Aseko Local**.

| Setting | What to enter |
| --- | --- |
| Host / binding address | Where Home Assistant listens. The default `0.0.0.0` listens on all local interfaces; this is **not the ASEKO unit's address**. |
| Port | The TCP port the unit will send to. Choose `47524`, `51050`, or enter a custom port. The default is `47524`. |

The unit and the integration must use the same destination port. Protocol detection is based on the received data, not the port number.

## Configure the unit

1. Open your ASEKO unit's IP address in a browser. The original default credentials on the network module are **admin / admin**, unless changed.
2. Open **Serial Port** configuration. Note the current **Remote Server Address** (often `pool.aseko.com`) and the port.

   ![ASEKO Serial Port settings before configuration](../../images/aseko-init.png)

3. Change **Remote Server Addr** to Home Assistant's reachable LAN IP address or DNS name.

   ![Remote server address set to Home Assistant](../../images/aseko-changed.png)

4. Set **Remote Port Number** to the integration's listener port.

   | Original protocol defaults | Port | Frame |
   | --- | --- | --- |
   | Firmware v7 and older | `47524` | 120-byte binary |
   | Firmware v8 | `51050` | Variable-length text |

   These are defaults, not fixed requirements. Both ends can use another port.

5. Apply the settings and confirm the network module's **Restart** when requested.

   ![Network module restart confirmation](../../images/aseko-restart.png)

### Several units or mixed firmware

The simplest setup is one integration entry on one port, with all units sending to it. The integration recognises v7 and v8 frames by their content.

Separate entries also work, each on its own port. **Do not configure two entries for the same listener address and port:** the entry set up last receives its frames.

## Check the first data

Open the integration's device and inspect its entities. **Connection status** and the recording card's **Last frame: N s ago** help confirm reception.

A missing entity is not necessarily a network problem: the model may be unmapped or the feature may not have been observed. Follow [Troubleshooting](../troubleshooting.md) and [Entity states](entities.md) before changing network settings again.

## Optional cloud forwarding

Local monitoring works without Aseko Cloud. If you also want the cloud to keep receiving the unit's data, open the integration's settings and enable the built-in forwarder.

The default destination is `pool.aseko.com`. The destination port follows the frame's protocol:

| Received frame | Forwarding port |
| --- | --- |
| v7 binary | `47524` |
| v8 text | `51050` |

![Integration options including forwarding](../../images/aseko-options.png)

Forwarding sends the raw unit data outside Home Assistant. Leave it disabled for local-only reception. A separate TCP proxy is not needed for the built-in forwarder.

---

[Documentation](../README.md) · [Understand entity states](entities.md) · [Troubleshooting](../troubleshooting.md)
