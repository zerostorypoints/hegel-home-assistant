# Hegel Streaming for Home Assistant

[![HACS custom repository](https://img.shields.io/badge/HACS-custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)
[![Validate](https://github.com/zerostorypoints/hegel-home-assistant/actions/workflows/validate.yml/badge.svg)](https://github.com/zerostorypoints/hegel-home-assistant/actions/workflows/validate.yml)
[![Tests](https://github.com/zerostorypoints/hegel-home-assistant/actions/workflows/tests.yml/badge.svg)](https://github.com/zerostorypoints/hegel-home-assistant/actions/workflows/tests.yml)

Control a Hegel streaming amplifier from Home Assistant over your local network: power, volume,
mute, input, playback, now playing and the stream format. No cloud and no account.

> **Brought to you by [HiFiSync](https://hifisync.com/?utm_source=github&utm_medium=readme&utm_campaign=hegel_streaming)**, the hi-fi
> recommendation engine grounded in physics, not opinions.
> Check how well your Hegel fits your speakers before you buy the next piece.

---

## Features

- **Found automatically.** The amp announces itself on the network; Home Assistant offers to add
  it. Entering the IP address by hand works too.
- **Instant updates.** The integration subscribes to the amp's own event stream, so a volume
  change or a new track shows up in Home Assistant within a fraction of a second.
- **Power on and standby** from Home Assistant, automations and voice assistants.
- **Volume, mute and input**, with the input names this model reports (XLR, Analog 1, BNC,
  Coaxial, Optical, USB, Network on an H400).
- **Playback** for the built-in streamer: play, pause, stop, next, previous, with title, artist,
  album, cover art, streaming service, track length and position.
- **Stream format sensors**: audio quality (Hi-Res, CD quality, Lossless, Lossy, DSD), codec,
  sample rate, bit depth, bitrate, streaming service.
- **Clear off state.** Standby and "not responding" both show the amp as off. A Network sensor
  tells them apart, and the entities stay usable after a restart even if the amp is switched off
  at the mains.
- **Volume limit.** Set a maximum volume so a slipped slider on a phone can never drive the amp
  to full power.
- English and Polish translations. Diagnostics download for bug reports.

## Supported amplifiers

Hegel has two generations of network amplifiers, and they are controlled in different ways.

### Streaming generation: this integration

The H150, H400 and H600 run a StreamUnlimited streaming platform. They are set up with the
[Hegel Control app](https://support.hegel.com/product-articles/hegel-setup-app) and have a web
client at `http://<amp-address>/webclient/`. This integration uses the same local web API as that
app and web client.

| Model | Firmware | Status |
|---|---|---|
| H400 | 1205.1011 | Tested |
| H150, H600 | | Same platform, expected to work, not tested yet |
| H200 | | Listed in the H400 firmware's model table, so probably the same platform; not tested |

If you own one of the untested models, please
[report whether it works](https://github.com/zerostorypoints/hegel-home-assistant/issues/new?template=model_report.yml).

A quick check: if `http://<amp-address>/webclient/` opens a Hegel page, the amp is on this
platform.

### IP control generation: Home Assistant's built-in Hegel integration

The H95, H120, H190, H190V, H390, H590 and Röst are controlled with Hegel's IP control protocol on
TCP port 50001, documented in Hegel's IP control code sheets. Use the
[Hegel integration](https://www.home-assistant.io/integrations/hegel/) that ships with Home
Assistant. That protocol offers power, volume, mute and input, but no track information or stream
format, so this integration would add nothing for those models.

If you try to add one of these older amplifiers to this integration, the setup dialog recognises
it (it answers an IP control status query on port 50001) and points you to the built-in
integration.

The streaming generation does not implement IP control: on the H400 port 50001 accepts
connections but never answers, whether the amp is on or in standby, and Hegel publishes no IP
control codes for it. The built-in integration therefore does not work with these models.

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=zerostorypoints&repository=hegel-home-assistant&category=integration)

Or by hand:

1. HACS → ⋮ → **Custom repositories**.
2. Repository `https://github.com/zerostorypoints/hegel-home-assistant`, type **Integration**.
3. Install **Hegel Streaming** and restart Home Assistant.

### Manual

Copy `custom_components/hegel_streaming` into the `custom_components` folder of your Home
Assistant configuration and restart.

Requires Home Assistant 2025.8 or newer.

## Setup

After the restart, Home Assistant lists the amp under Settings → Devices & services →
**Discovered**. Click **Add**.

If it is not discovered (for example when Home Assistant runs in a separate network or VLAN), go
to Settings → Devices & services → Add integration → **Hegel Streaming** and enter the amp's IP
address.

**Give the amp a fixed address.** Reserve its IP in your router (a DHCP reservation or static
lease). If the address changes anyway, discovery picks up the new one by itself and Home
Assistant shows a notice under Settings → System → Repairs. Without discovery (another VLAN),
use **Reconfigure** on the integration.

The amp must be powered at the mains; standby is enough.

## Entities

For an amp named `H400`:

| Entity | What it does |
|---|---|
| `media_player.h400` | Power, volume, mute, input (source), playback, now playing |
| `sensor.h400_audio_quality` | `Hi-Res`, `CD quality`, `Lossless`, `Lossy`, `DSD` while the streamer plays |
| `sensor.h400_codec` | As reported by the stream (Spotify reports none) |
| `sensor.h400_sample_rate` | kHz |
| `sensor.h400_bit_depth` | bit |
| `sensor.h400_bitrate` | kbit/s |
| `sensor.h400_streaming_service` | e.g. `Spotify` |
| `binary_sensor.h400_network` | On while the amp answers on the network, standby included |

### Off, standby and not responding

| Situation | Media player | Network |
|---|---|---|
| On | `on` / `playing` / `paused` | on |
| Standby | `off` | on |
| Switched off at the mains, unplugged, network down | `off` | off |

Turning on from standby works from Home Assistant. An amp that does not answer cannot be woken
over the network; the turn-on action then says so.

Stream format sensors have a value only while the built-in streamer is playing or paused, not
while a physical input (XLR, analog, optical, USB) is in use.

## Options

Settings → Devices & services → Hegel Streaming → **Configure**:

- **Maximum volume** (10–100, default 100). Home Assistant never sets the volume above it. The
  amp's remote and front knob are not limited.

## Examples

Dashboard card:

```yaml
type: media-control
entity: media_player.h400
```

Put the amp in standby when everyone leaves:

```yaml
automation:
  - alias: Hegel off when away
    triggers:
      - trigger: state
        entity_id: zone.home
        to: "0"
    actions:
      - action: media_player.turn_off
        target:
          entity_id: media_player.h400
```

## Troubleshooting

- **Not discovered.** Discovery uses mDNS (`_sues800device._tcp`). It does not cross VLANs
  without an mDNS reflector. Add the amp by IP address.
- **Shows off although it is on.** Open `http://<amp-address>/webclient/` from the Home Assistant
  host. If that page does not load, the network path is the problem.
- **Bug reports.** Download diagnostics from the device page and attach them to an
  [issue](https://github.com/zerostorypoints/hegel-home-assistant/issues). Debug logging:

  ```yaml
  logger:
    logs:
      custom_components.hegel_streaming: debug
  ```

## Security

The amp's web API has no authentication by default: anything on your network can control it.
This integration only talks to the amp on your local network. Keep the amp off networks you do
not trust.

## How it works

The integration uses the same local web API as the amp's own web client:
`/api/getData`, `/api/setData` and the long-polling event queue under `/api/event`. A full
refresh runs every 30 seconds as a safety net; changes arrive through the event queue in between.

---

## About HiFiSync

[**HiFiSync**](https://hifisync.com/?utm_source=github&utm_medium=readme&utm_campaign=hegel_streaming) is a hi-fi recommendation
engine that scores system synergy with physics instead of adjectives.

- **Match** — what fits the gear you already own.
- **Compare** — component A against component B, by the numbers.
- **Build** — a complete system from scratch in seven steps: topology, then a model for each slot.
- **Synergy score** — a deterministic readout of 21 physics-based checks across Signal, Room and
  Character, each one cited. No brand or dealer can buy a better score.
- **Sourced specs** — every spec links to a primary source, with manufacturer-confirmed and
  secondary data marked apart.
- **Built in Europe** — prices in local currencies and availability checked against EU
  distributors. A catalogue of 1,600+ components from 76 brands, Hegel included.

[Build your system on HiFiSync →](https://hifisync.com/?utm_source=github&utm_medium=readme&utm_campaign=hegel_streaming)

## Credits

Made by [Zero Story Points](https://zerostorypoints.com), the team behind HiFiSync.

Not affiliated with or endorsed by Hegel Music Systems AS. Hegel is a trademark of its owner.

## License

[MIT](LICENSE)
