"""Base entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HegelCoordinator


class HegelEntity(CoordinatorEntity[HegelCoordinator]):
    """Entity bound to one amplifier."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HegelCoordinator, key: str | None = None) -> None:
        super().__init__(coordinator)
        device = coordinator.device
        self._attr_unique_id = f"{device.unique_id}_{key}" if key else device.unique_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.unique_id)},
            manufacturer=device.manufacturer,
            model=device.model,
            name=device.name,
            sw_version=device.firmware,
            configuration_url=f"http://{coordinator.client.host}/webclient/",
        )
