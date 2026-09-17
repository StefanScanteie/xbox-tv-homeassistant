"""Xbox TV media player platform."""

from __future__ import annotations

import asyncio
import logging
import time

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LIVE_ID, DOMAIN, EVENT_HOMEKIT_TV_REMOTE_KEY_PRESSED, TURN_ON_WAIT
from .coordinator import XboxTvCoordinator
from .xbox_api import extra_media_attributes, resolve_homekit_tv_remote_key, resolve_source_action

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Xbox TV media player."""
    coordinator: XboxTvCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([XboxTvMediaPlayer(coordinator, entry)])


class XboxTvMediaPlayer(CoordinatorEntity[XboxTvCoordinator], MediaPlayerEntity):
    """Representation of an Xbox TV."""

    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
    )
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: XboxTvCoordinator, entry: ConfigEntry) -> None:
        """Initialize the media player."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = entry.data[CONF_LIVE_ID]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_LIVE_ID])},
            manufacturer="Microsoft",
            model="Xbox Series",
            name=entry.data.get("name", entry.title),
        )

    @property
    def state(self) -> str:
        """Return the state of the device."""
        if self.coordinator.data and self.coordinator.data.powered_on:
            return STATE_ON
        return STATE_OFF

    @property
    def source(self) -> str | None:
        """Return the current source."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.source

    @property
    def source_list(self) -> list[str] | None:
        """Return the list of available sources."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.source_list

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return current title attributes for automations."""
        data = self.coordinator.data
        if data is None:
            return {}
        return extra_media_attributes(
            powered_on=data.powered_on,
            aumid=data.aumid,
            titles=data.titles,
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to HomeKit TV remote key events."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.hass.bus.async_listen(
                EVENT_HOMEKIT_TV_REMOTE_KEY_PRESSED,
                self._async_on_tv_remote_key,
            )
        )

    async def _async_on_tv_remote_key(self, event: object) -> None:
        """Map Apple Remote keys to Xbox REST commands."""
        data = getattr(event, "data", {})
        if data.get("entity_id") != self.entity_id:
            return
        key_name = data.get("key_name")
        if not isinstance(key_name, str):
            return
        action = resolve_homekit_tv_remote_key(key_name)
        if action is None:
            return
        webapi = self.coordinator.webapi
        if webapi is None:
            _LOGGER.warning("Remote keys require Microsoft sign-in")
            return
        await webapi.async_execute_remote_action(action)

    async def async_turn_on(self) -> None:
        """Turn the device on."""
        await self.coordinator.smartglass.async_power_on()
        self.hass.async_create_task(self._wait_for_power_on())

    async def _wait_for_power_on(self) -> None:
        """Poll until the console reports on or timeout."""
        deadline = time.monotonic() + TURN_ON_WAIT
        while time.monotonic() < deadline:
            await self.coordinator.async_request_refresh()
            if self.coordinator.data and self.coordinator.data.powered_on:
                return
            await asyncio.sleep(2)

    async def async_turn_off(self) -> None:
        """Turn the device off."""
        webapi = self.coordinator.webapi
        if webapi is None:
            _LOGGER.warning("Turn off requires Microsoft sign-in")
            return
        await webapi.async_turn_off()
        await self.coordinator.async_request_refresh()

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        if self.coordinator.data is None:
            return

        action = resolve_source_action(
            source,
            self.coordinator.data.titles,
            self.coordinator.data.microsoft_connected,
        )
        webapi = self.coordinator.webapi

        if action.kind == "dashboard":
            if webapi is None:
                _LOGGER.warning("Dashboard requires Microsoft sign-in")
                return
            await webapi.async_go_home()
        elif action.kind == "launch":
            assert action.launch_id is not None
            if webapi is None:
                _LOGGER.warning("Launch requires Microsoft sign-in")
                return
            await webapi.async_launch(action.launch_id)
        elif action.kind == "signin":
            async_create_issue(
                self.hass,
                DOMAIN,
                "microsoft_sign_in",
                is_fixable=False,
                severity=IssueSeverity.WARNING,
                translation_key="microsoft_sign_in",
            )
            return
        else:
            _LOGGER.warning("Unknown source %r", source)
            return

        await self.coordinator.async_request_refresh()

    async def async_media_play(self) -> None:
        """Send Play."""
        await self._async_media_command("play")

    async def async_media_pause(self) -> None:
        """Send Pause."""
        await self._async_media_command("pause")

    async def async_media_play_pause(self) -> None:
        """Send Play when HomeKit cannot distinguish pause vs play."""
        await self._async_media_command("play")

    async def async_media_next_track(self) -> None:
        """Send Next."""
        await self._async_media_command("next")

    async def async_media_previous_track(self) -> None:
        """Send Previous."""
        await self._async_media_command("previous")

    async def _async_media_command(self, command: str) -> None:
        webapi = self.coordinator.webapi
        if webapi is None:
            _LOGGER.warning("Media controls require Microsoft sign-in")
            return
        if command == "play":
            await webapi.async_play()
            return
        if command == "pause":
            await webapi.async_pause()
            return
        if command == "next":
            await webapi.async_next()
            return
        if command == "previous":
            await webapi.async_previous()
            return
        raise ValueError(f"Unhandled media command: {command}")
