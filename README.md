<p align="center">
  <img src="assets/header.png" alt="Crestron Home for Home Assistant" width="720">
</p>

# Crestron Home for Home Assistant

Local polling Home Assistant integration for Crestron Home processors using the
documented Crestron Home REST API.

This project is early and was built against a live Crestron Home processor. Use
it as a custom HACS repository until more systems have been tested.

## Installation With HACS

1. In Home Assistant, open HACS.
2. Open the three-dot menu and choose **Custom repositories**.
3. Add this repository URL:

   ```text
   https://github.com/Phant0mElit3/Home-Assistant--Crestron-Home-Integration
   ```

4. Select category **Integration**.
5. Install **Crestron Home**.
6. Restart Home Assistant.
7. Add the integration from **Settings > Devices & services**.

## Manual Installation

Copy `custom_components/crestron_home` into your Home Assistant config folder:

```text
/config/custom_components/crestron_home
```

Then restart Home Assistant.

## Configuration

The integration supports UI setup and YAML import.

```yaml
crestron_home:
  host: "processor IP address"
  token: !secret crestron_home_token
  use_ssl: true
  verify_ssl: false
  scan_interval: 15
```

The token is the Crestron Home Web API authentication token from the Crestron
Home Setup app. The processor must use the default Web API ports: HTTPS `443` or
HTTP `80`.

## Current Coverage

- Lights and dimmers from `/lights`
- Shades/covers from `/shades`
- Thermostats from `/thermostats`
- Scenes from `/scenes`
- Door locks from `/doorlocks`
- Media rooms from `/mediarooms`
- Media room source selects
- Quick Actions as experimental buttons from `/quickactions`
- Sensors and binary sensors from `/sensors` and `/devices`
- Read-only security device state from `/securitydevices`

## Known Notes

- Media room volume on the tested processor uses `0-65535`, even where the API
  table implies percent.
- Media source selection uses `availableSources[].id` and
  `availableSources[].sourceName` when returned by the processor.
- Thermostat fan and scheduler commands are exposed because the REST API
  documents them, but more live systems are needed to validate behavior across
  thermostat models.
- Quick Action buttons are experimental because the public REST docs expose
  discovery but do not document the recall endpoint. Button presses try the
  most likely Crestron command paths and log each attempt for live validation.

## Crestron API

Crestron Home REST API reference:

https://sdkcon78221.crestron.com/sdk/Crestron-Home-API/Content/Topics/API-Reference/API-Reference.htm

## Trademark and Asset Notice

This project is an independent Home Assistant custom integration and is not
affiliated with, endorsed by, sponsored by, or supported by Crestron Electronics,
Inc.

Crestron, Crestron Home, and related names, marks, logos, and images are the
property of Crestron Electronics, Inc. Any Crestron logos or product images in
this repository are included only to identify compatibility with Crestron Home
systems and are not owned by this project. The MIT license applies to the
original integration source code only and does not grant rights to Crestron
trademarks, logos, images, or other third-party assets.

See [NOTICE](NOTICE) for the asset and trademark notice.
