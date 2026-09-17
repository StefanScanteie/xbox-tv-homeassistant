"""Xbox occupancy binary sensor for Home automations."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LIVE_ID, DOMAIN
from .coordinator import XboxTvCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Xbox occupancy sensor."""
    coordinator: XboxTvCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([XboxOccupiedSensor(coordinator, entry)])


class XboxOccupiedSensor(CoordinatorEntity[XboxTvCoordinator], BinarySensorEntity):
    """Occupancy sensor that is on while the console is powered on."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_has_entity_name = True
    _attr_name = "Occupied"

    def __init__(self, coordinator: XboxTvCoordinator, entry: ConfigEntry) -> None:
        """Initialize the occupancy sensor."""
        super().__init__(coordinator)
        live_id = entry.data[CONF_LIVE_ID]
        self._attr_unique_id = f"{live_id}_occupied"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, live_id)},
            manufacturer="Microsoft",
            model="Xbox Series",
            name=entry.data.get("name", entry.title),
        )

    @property
    def is_on(self) -> bool:
        """Return True when the console is powered on."""
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.powered_on
