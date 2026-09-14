"""State coordinator: a periodic full refresh plus push events from the amp."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import replace
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import (
    PATH_PLAY_TIME,
    PATH_PLAYER_DATA,
    PATH_POWER,
    HegelClient,
    HegelConnectionError,
    HegelDeviceInfo,
    HegelError,
    HegelQueueExpiredError,
    HegelState,
)
from .const import DOMAIN, EVENT_POLL_TIMEOUT, RECONNECT_INTERVAL, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type HegelConfigEntry = ConfigEntry[HegelCoordinator]


class HegelCoordinator(DataUpdateCoordinator[HegelState]):
    """Holds the amp state.

    An amp that does not answer is not an error here: it is reported as a state with
    reachable=False, so entities stay available and show the amp as off.
    """

    config_entry: HegelConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: HegelConfigEntry,
        client: HegelClient,
        device: HegelDeviceInfo,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {device.name}",
            update_interval=SCAN_INTERVAL,
            always_update=False,
        )
        self.client = client
        self.device = device
        self.sources: dict[int, str] = {}
        self._was_reachable = True

    async def _async_update_data(self) -> HegelState:
        try:
            state = await self.client.get_state()
            if not self.sources and state.is_on:
                self.sources = await self.client.get_sources()
        except HegelConnectionError as err:
            if self._was_reachable:
                _LOGGER.info("%s is not responding, reporting it as off: %s", self.device.name, err)
            self._was_reachable = False
            return HegelState(reachable=False)
        except HegelError as err:
            _LOGGER.warning("Unexpected answer from %s: %s", self.device.name, err)
            return self.data or HegelState(reachable=False)
        if not self._was_reachable:
            _LOGGER.info("%s is responding again", self.device.name)
        self._was_reachable = True
        return state

    async def async_run_event_loop(self) -> None:
        """Long-poll the amp's event queue for as long as the entry is loaded."""
        queue_id: str | None = None
        while True:
            try:
                if queue_id is None:
                    queue_id = await self.client.create_queue()
                    # Catch anything that changed while there was no queue.
                    await self.async_refresh()
                events = await self.client.poll_queue(queue_id, EVENT_POLL_TIMEOUT)
            except HegelQueueExpiredError:
                queue_id = None
                continue
            except HegelError as err:
                _LOGGER.debug("Event queue for %s failed: %s", self.device.name, err)
                queue_id = None
                if isinstance(err, HegelConnectionError) and self.data and self.data.reachable:
                    await self.async_refresh()
                await asyncio.sleep(RECONNECT_INTERVAL)
                continue
            if events:
                await self._async_handle_events(events)

    async def _async_handle_events(self, events: list[dict]) -> None:
        state = replace(self.data) if self.data else HegelState(reachable=True)
        state.reachable = True
        changed_paths: set[str] = set()
        for event in events:
            path = event.get("path")
            if event.get("itemType") != "update" or not path:
                continue
            if state.apply(path, event.get("itemValue")):
                changed_paths.add(path)
        if not changed_paths:
            return
        if PATH_PLAYER_DATA in changed_paths and state.is_on:
            try:
                state.apply(PATH_PLAY_TIME, await self.client.get(PATH_PLAY_TIME))
            except HegelError:
                state.play_time_ms = None
        if PATH_POWER in changed_paths and state.is_on and not self.sources:
            with contextlib.suppress(HegelError):
                self.sources = await self.client.get_sources()
        self._was_reachable = True
        self.async_set_updated_data(state)
