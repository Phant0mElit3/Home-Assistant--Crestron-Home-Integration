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
  host: 192.168.1.229
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

The integration also polls `/quickactions` for future support. The published
Crestron REST docs expose Quick Actions as a listing endpoint only, so this
build does not create pressable HA buttons for them yet.

Binary sensors are read-only by nature. AV-room control still belongs to the
separate User Interface Device Password / port `50001` surface.
