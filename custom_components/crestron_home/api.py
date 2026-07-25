"""Async client for the Crestron Home REST API."""

from __future__ import annotations

import json
import logging
from typing import Any

from aiohttp import ClientError, ClientSession

_LOGGER = logging.getLogger(__name__)

INVENTORY_ENDPOINTS = (
    "rooms",
    "devices",
    "lights",
    "shades",
    "thermostats",
    "scenes",
    "doorlocks",
    "mediarooms",
    "sensors",
    "securitydevices",
    "quickactions",
)
OPTIONAL_INVENTORY_ENDPOINTS = {
    "doorlocks",
    "mediarooms",
    "sensors",
    "securitydevices",
    "quickactions",
}
QUICK_ACTION_RECALL_PATHS = (
    "/quickactions/recall/{id}",
    "/quickactions/{id}/recall",
    "/quickactions/execute/{id}",
    "/quickactions/{id}/execute",
    "/quickactions/{id}",
)


class CrestronHomeApiError(Exception):
    """Raised when the Crestron Home API returns an error."""


class CrestronHomeAuthError(CrestronHomeApiError):
    """Raised when Crestron Home authentication fails."""


class CrestronHomeApi:
    """Small client for the documented Crestron Home REST API flow."""

    def __init__(
        self,
        session: ClientSession,
        host: str,
        token: str,
        *,
        use_ssl: bool = True,
        verify_ssl: bool = False,
    ) -> None:
        self._session = session
        self._host = host
        self._token = token
        self._scheme = "https" if use_ssl else "http"
        self._verify_ssl = verify_ssl
        self._authkey: str | None = None

    @property
    def base_url(self) -> str:
        """Return the base REST API URL."""
        return f"{self._scheme}://{self._host}/cws/api"

    async def async_login(self) -> str:
        """Exchange the Web API token for a REST API auth key."""
        _LOGGER.debug("Requesting Crestron Home REST API auth key from %s", self.base_url)
        payload = await self._request(
            "GET",
            "/login",
            headers={"Crestron-RestAPI-AuthToken": self._token},
            allow_reauth=False,
        )
        authkey = payload.get("authkey")
        if not isinstance(authkey, str) or not authkey:
            raise CrestronHomeAuthError("Crestron Home login did not return an authkey")
        self._authkey = authkey
        _LOGGER.debug("Received Crestron Home REST API auth key")
        return authkey

    async def async_get_inventory(self) -> dict[str, Any]:
        """Fetch Crestron Home inventory/state."""
        await self._ensure_authkey()
        result: dict[str, Any] = {}
        for endpoint in INVENTORY_ENDPOINTS:
            try:
                result[endpoint] = await self.async_get(endpoint)
            except CrestronHomeApiError:
                if endpoint not in OPTIONAL_INVENTORY_ENDPOINTS:
                    raise
                _LOGGER.debug("Crestron Home optional endpoint %s is unavailable", endpoint)
                result[endpoint] = {}
        result["mediarooms"] = await self._async_enrich_media_rooms(result.get("mediarooms"))
        return result

    async def async_get(self, endpoint: str) -> dict[str, Any]:
        """Read a Crestron Home API endpoint."""
        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        return await self._request("GET", path, auth=True)

    async def _async_enrich_media_rooms(self, payload: Any) -> dict[str, Any]:
        """Merge per-room media details into the media room list payload."""
        if not isinstance(payload, dict):
            return {}
        media_rooms = payload.get("mediaRooms") or payload.get("mediarooms") or []
        if not isinstance(media_rooms, list):
            return payload

        enriched_rooms: list[dict[str, Any]] = []
        for room in media_rooms:
            if not isinstance(room, dict):
                continue
            room_id = room.get("id")
            if room_id is None:
                enriched_rooms.append(room)
                continue
            try:
                detail_payload = await self.async_get(f"/mediarooms/{room_id}")
            except CrestronHomeApiError:
                _LOGGER.debug("Crestron Home media room detail endpoint failed for %s", room_id)
                enriched_rooms.append(room)
                continue
            detail = self._extract_media_room_detail(detail_payload)
            enriched_rooms.append({**room, **detail} if detail else room)

        return {**payload, "mediaRooms": enriched_rooms}

    @staticmethod
    def _extract_media_room_detail(payload: dict[str, Any]) -> dict[str, Any]:
        """Extract a media room detail object from a Crestron payload."""
        for key in ("mediaRoom", "mediaroom", "room"):
            value = payload.get(key)
            if isinstance(value, dict):
                return value
        detail_rooms = payload.get("mediaRooms") or payload.get("mediarooms")
        if isinstance(detail_rooms, list) and detail_rooms and isinstance(detail_rooms[0], dict):
            return detail_rooms[0]
        if payload.get("id") is not None:
            return payload
        return {}

    async def async_post(
        self,
        endpoint: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Write to a Crestron Home API endpoint."""
        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        return await self._request("POST", path, auth=True, json_payload=payload)

    def _raise_for_command_status(
        self,
        payload: dict[str, Any],
        fallback_message: str,
    ) -> None:
        """Raise when a command response reports partial or failed status."""
        status = str(payload.get("status", "success")).lower()
        if status in {"partial", "failure"}:
            message = payload.get("errorMessage") or fallback_message
            raise CrestronHomeApiError(message)

    async def async_set_light_level(
        self,
        light_id: Any,
        level: int,
        *,
        time: int = 0,
    ) -> dict[str, Any]:
        """Set a Crestron Home light level.

        Crestron documents light levels as a 16-bit value from 0 to 65535.
        """
        normalized_level = max(0, min(65535, int(level)))
        payload = await self.async_post(
            "/lights/SetState",
            {"lights": [{"id": light_id, "level": normalized_level, "time": time}]},
        )
        self._raise_for_command_status(payload, f"Light {light_id} failed to update")
        return payload

    async def async_recall_scene(self, scene_id: Any) -> dict[str, Any]:
        """Recall a Crestron Home scene."""
        payload = await self.async_post(f"/scenes/recall/{scene_id}")
        self._raise_for_command_status(payload, f"Scene {scene_id} failed to recall")
        return payload

    async def async_recall_quick_action(self, quick_action_id: Any) -> dict[str, Any]:
        """Recall a Crestron Home quick action.

        Crestron documents quick action discovery but not the recall endpoint.
        Try scene-like and execute-like routes so live processor logs can
        identify the supported command surface.
        """
        errors: list[str] = []
        for template in QUICK_ACTION_RECALL_PATHS:
            path = template.format(id=quick_action_id)
            _LOGGER.debug("Trying Crestron Home quick action POST %s", path)
            try:
                payload = await self.async_post(path)
            except CrestronHomeApiError as err:
                _LOGGER.debug("Crestron Home quick action POST %s failed: %s", path, err)
                errors.append(f"{path}: {err}")
                continue
            _LOGGER.debug(
                "Crestron Home quick action response for %s via %s: %s",
                quick_action_id,
                path,
                payload,
            )
            if _is_generic_api_description(payload):
                _LOGGER.debug(
                    "Crestron Home quick action POST %s returned generic API "
                    "description; trying next candidate",
                    path,
                )
                errors.append(f"{path}: generic API description")
                continue
            self._raise_for_command_status(
                payload,
                f"Quick action {quick_action_id} failed to recall",
            )
            return payload

        raise CrestronHomeApiError(
            f"Quick action {quick_action_id} failed to recall; attempted "
            + "; ".join(errors)
        )

    async def async_set_shade_position(
        self,
        shade_id: Any,
        position: int,
    ) -> dict[str, Any]:
        """Set a Crestron Home shade position.

        Crestron documents shade positions as a 16-bit value from 0 to 65535.
        """
        normalized_position = max(0, min(65535, int(position)))
        payload = await self.async_post(
            "/shades/SetState",
            {"shades": [{"id": shade_id, "position": normalized_position}]},
        )
        self._raise_for_command_status(payload, f"Shade {shade_id} failed to update")
        return payload

    async def async_set_thermostat_setpoints(
        self,
        thermostat_id: Any,
        setpoints: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Set one or more Crestron Home thermostat setpoints."""
        request_payload = {"id": thermostat_id, "setpoints": setpoints}
        _LOGGER.debug("Setting Crestron Home thermostat setpoints: %s", request_payload)
        payload = await self.async_post(
            "/thermostats/SetPoint",
            request_payload,
        )
        _LOGGER.debug("Crestron Home thermostat setpoint response: %s", payload)
        self._raise_for_command_status(
            payload,
            f"Thermostat {thermostat_id} failed to set temperature",
        )
        return payload

    async def async_set_thermostat_mode(
        self,
        thermostat_id: Any,
        mode: str,
    ) -> dict[str, Any]:
        """Set a Crestron Home thermostat operating mode."""
        payload = await self.async_post(
            "/thermostats/mode",
            {"thermostats": [{"id": thermostat_id, "mode": mode.upper()}]},
        )
        self._raise_for_command_status(
            payload,
            f"Thermostat {thermostat_id} failed to set mode",
        )
        return payload

    async def async_set_thermostat_fan_mode(
        self,
        thermostat_id: Any,
        mode: str,
    ) -> dict[str, Any]:
        """Set a Crestron Home thermostat fan mode."""
        request_payload = {"thermostats": [{"id": thermostat_id, "mode": mode.upper()}]}
        _LOGGER.debug("Setting Crestron Home thermostat fan mode: %s", request_payload)
        payload = await self.async_post(
            "/thermostats/fanmode",
            request_payload,
        )
        _LOGGER.debug("Crestron Home thermostat fan mode response: %s", payload)
        self._raise_for_command_status(
            payload,
            f"Thermostat {thermostat_id} failed to set fan mode",
        )
        return payload

    async def async_set_thermostat_schedule(
        self,
        thermostat_id: Any,
        mode: str,
    ) -> dict[str, Any]:
        """Set a Crestron Home thermostat schedule mode."""
        last_error: CrestronHomeApiError | None = None
        for command_mode in _schedule_mode_candidates(mode):
            request_payload = {"thermostats": [{"id": thermostat_id, "mode": command_mode}]}
            _LOGGER.debug("Setting Crestron Home thermostat schedule: %s", request_payload)
            try:
                payload = await self.async_post(
                    "/thermostats/schedule",
                    request_payload,
                )
            except CrestronHomeApiError as err:
                last_error = err
                _LOGGER.debug(
                    "Crestron Home thermostat schedule command %s failed: %s",
                    command_mode,
                    err,
                )
                continue
            _LOGGER.debug("Crestron Home thermostat schedule response: %s", payload)
            self._raise_for_command_status(
                payload,
                f"Thermostat {thermostat_id} failed to set schedule",
            )
            return payload
        raise last_error or CrestronHomeApiError(
            f"Thermostat {thermostat_id} failed to set schedule"
        )

    async def async_lock_door(self, lock_id: Any) -> dict[str, Any]:
        """Lock a Crestron Home door lock."""
        payload = await self.async_post(f"/doorlocks/lock/{lock_id}")
        self._raise_for_command_status(payload, f"Door lock {lock_id} failed to lock")
        return payload

    async def async_unlock_door(self, lock_id: Any) -> dict[str, Any]:
        """Unlock a Crestron Home door lock."""
        payload = await self.async_post(f"/doorlocks/unlock/{lock_id}")
        self._raise_for_command_status(payload, f"Door lock {lock_id} failed to unlock")
        return payload

    async def async_set_media_room_mute(
        self,
        media_room_id: Any,
        mute: bool,
    ) -> dict[str, Any]:
        """Set a Crestron Home media room mute state."""
        action = "mute" if mute else "unmute"
        payload = await self.async_post(f"/mediarooms/{media_room_id}/{action}")
        self._raise_for_command_status(
            payload,
            f"Media room {media_room_id} failed to {action}",
        )
        return payload

    async def async_set_media_room_source(
        self,
        media_room_id: Any,
        source_id: Any,
    ) -> dict[str, Any]:
        """Select a Crestron Home media room source."""
        path = f"/mediarooms/{media_room_id}/selectsource/{source_id}"
        _LOGGER.debug("Selecting Crestron Home media room source with POST %s", path)
        payload = await self.async_post(path)
        _LOGGER.debug(
            "Crestron Home media room source response for room %s source %s: %s",
            media_room_id,
            source_id,
            payload,
        )
        self._raise_for_command_status(
            payload,
            f"Media room {media_room_id} failed to select source {source_id}",
        )
        return payload

    async def async_set_media_room_volume(
        self,
        media_room_id: Any,
        level: int,
    ) -> dict[str, Any]:
        """Set a Crestron Home media room volume level."""
        normalized_level = max(0, min(65535, int(level)))
        payload = await self.async_post(f"/mediarooms/{media_room_id}/volume/{normalized_level}")
        self._raise_for_command_status(
            payload,
            f"Media room {media_room_id} failed to set volume",
        )
        return payload

    async def async_set_media_room_power(
        self,
        media_room_id: Any,
        on: bool,
    ) -> dict[str, Any]:
        """Set a Crestron Home media room power state."""
        state = "on" if on else "off"
        payload = await self.async_post(f"/mediarooms/{media_room_id}/power/{state}")
        self._raise_for_command_status(
            payload,
            f"Media room {media_room_id} failed to power {state}",
        )
        return payload

    async def _ensure_authkey(self) -> None:
        if not self._authkey:
            await self.async_login()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        auth: bool = False,
        allow_reauth: bool = True,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        if auth:
            await self._ensure_authkey()
            request_headers["Crestron-RestAPI-AuthKey"] = self._authkey or ""

        url = f"{self.base_url}{path}"
        ssl_arg = None if self._verify_ssl else False

        try:
            async with self._session.request(
                method,
                url,
                headers=request_headers,
                json=json_payload,
                ssl=ssl_arg,
            ) as response:
                text = await response.text()
                try:
                    payload = json.loads(text) if text.strip() else {}
                except ValueError as err:
                    if 200 <= response.status < 300:
                        raise CrestronHomeApiError(
                            f"Crestron Home API {method} {path} returned invalid JSON"
                        ) from err
                    payload = {}
                if response.status == 401 and auth and allow_reauth:
                    self._authkey = None
                    await self.async_login()
                    return await self._request(
                        method,
                        path,
                        headers=headers,
                        auth=auth,
                        allow_reauth=False,
                        json_payload=json_payload,
                    )
                if response.status < 200 or response.status >= 300:
                    message = payload.get("errorMessage") if isinstance(payload, dict) else None
                    raise CrestronHomeApiError(
                        f"Crestron Home API {method} {path} failed: "
                        f"{response.status} {message or response.reason}"
                    )
                if not isinstance(payload, dict):
                    raise CrestronHomeApiError(
                        f"Crestron Home API {method} {path} returned non-object JSON"
                    )
                return payload
        except ClientError as err:
            raise CrestronHomeApiError(f"Cannot connect to Crestron Home: {err}") from err


def _schedule_mode_candidates(mode: str) -> list[str]:
    """Return scheduler command values to try for firmware case differences."""
    candidates = (mode.upper(), mode.title())
    result: list[str] = []
    for candidate in candidates:
        if candidate not in result:
            result.append(candidate)
    return result


def _is_generic_api_description(payload: dict[str, Any]) -> bool:
    """Return whether a response is the generic API landing payload."""
    keys = set(payload)
    description = str(payload.get("description", "")).lower()
    return (
        "status" not in payload
        and "description" in payload
        and "version" in payload
        and keys <= {"description", "version"}
        and "pyng rest api" in description
    )
