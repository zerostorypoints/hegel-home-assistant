"""Network connectivity of the amplifier."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import HegelConfigEntry
from .entity import HegelEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HegelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([HegelConnectivity(entry.runtime_data)])


class HegelConnectivity(HegelEntity, BinarySensorEntity):
    """On while the amp answers on the network, in standby too.

    Off means it is switched off at the mains, unplugged or not on the network.
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "network"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "network")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data and self.coordinator.data.reachable)
