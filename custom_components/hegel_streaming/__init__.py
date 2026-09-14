"""Hegel Streaming: Home Assistant integration for Hegel network amplifiers.

Brought to you by HiFiSync (https://hifisync.com). Made by Zero Story Points.
"""

from __future__ import annotations

from dataclasses import asdict

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HegelClient, HegelConnectionError, HegelDeviceInfo, HegelError
from .const import CONF_DEVICE, DOMAIN
from .coordinator import HegelConfigEntry, HegelCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.MEDIA_PLAYER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: HegelConfigEntry) -> bool:
    """Set up an amplifier from a config entry."""
    client = HegelClient(entry.data[CONF_HOST], async_get_clientsession(hass))
    try:
        device = await client.get_device_info()
    except HegelConnectionError as err:
        # An amp that is off at the mains still gets its entities, shown as off, once it
        # has been seen before.
        if cached := entry.data.get(CONF_DEVICE):
            device = HegelDeviceInfo(**cached)
        else:
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN,
                translation_key="not_responding",
                translation_placeholders={"host": entry.data[CONF_HOST]},
            ) from err
    except HegelError as err:
        raise ConfigEntryNotReady(str(err)) from err
    else:
        if entry.data.get(CONF_DEVICE) != asdict(device):
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_DEVICE: asdict(device)}
            )

    coordinator = HegelCoordinator(hass, entry, client, device)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_create_background_task(
        hass, coordinator.async_run_event_loop(), f"{DOMAIN} events {entry.entry_id}"
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HegelConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
