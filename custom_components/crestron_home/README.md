# Crestron Home for Home Assistant

Local polling integration for Crestron Home OS using the documented REST API.

Repository:

```text
https://github.com/Phant0mElit3/Home-Assistant--Crestron-Home-Integration
```

## Confirmed Authentication Flow

1. `GET /cws/api/login` with:

   ```http
   Crestron-RestAPI-AuthToken: <web-api-token>
   ```

2. Use the returned `authkey` on subsequent calls:

   ```http
   Crestron-RestAPI-AuthKey: <session-auth-key>
   ```

## YAML

```yaml
crestron_home:
  host: "processor IP address"
  token: !secret crestron_home_token
  use_ssl: true
  verify_ssl: false
  scan_interval: 15
```

## Current Coverage

- `alarm_control_panel`: read-only state for Crestron security devices from
  `/securitydevices`
- `binary_sensor`: occupancy, door/contact, doorbell, and similar sensor state
  from `/sensors` and sensor devices from `/devices`
- `button`: discovered Quick Actions from `/quickactions`; press support is
  experimental while the recall endpoint is validated against live systems
- `light`: polled state from `/lights`; on/off and dimmer control through
  `/lights/SetState`
- `climate`: polled thermostat state from `/thermostats`; setpoint, HVAC mode,
  fan mode, run/hold schedule visibility, turn on, and turn off control. Fan
  and schedule write calls are exposed per the Crestron API, but need more
  thermostat-model validation.
- `scene`: discovered scenes from `/scenes`; activation through
  `/scenes/recall/{id}`
- `cover`: discovered shades from `/shades`; open, close, and position control
  through `/shades/SetState`
- `lock`: discovered door locks from `/doorlocks`; lock and unlock control
- `media_player`: discovered media rooms from `/mediarooms`; power, mute,
  volume, and source-select control
- `select`: separate media room source dropdowns from `/mediarooms`
- `sensor`: numeric or diagnostic sensor values such as light level,
  temperature, humidity, and battery status

The published Crestron REST docs expose Quick Actions as a listing endpoint
only, so button presses try the most likely recall/execute endpoint patterns and
log each attempt for validation.

Binary sensors are read-only by nature. 

This integration currently uses the Crestron Home Web API token over the default HTTP/HTTPS ports. Josh.ai documentation indicates that deeper AV-room control may use a separate User Interface Device Password on port 50001; that interface is not implemented yet.
