"""Media player entity: power, volume, mute, input and playback."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import HegelError
from .const import (
    CONF_HIDDEN_SOURCES,
    CONF_MAX_VOLUME,
    CONF_SOURCE_NAMES,
    DEFAULT_MAX_VOLUME,
    DOMAIN,
)
from .coordinator import HegelConfigEntry, HegelCoordinator
from .entity import HegelEntity

PARALLEL_UPDATES = 1

PLAYER_STATES = {
    "playing": MediaPlayerState.PLAYING,
    "paused": MediaPlayerState.PAUSED,
    "buffering": MediaPlayerState.BUFFERING,
    "transitioning": MediaPlayerState.BUFFERING,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HegelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([HegelMediaPlayer(entry.runtime_data)])


class HegelMediaPlayer(HegelEntity, MediaPlayerEntity):
    """The amplifier."""

    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_media_image_remotely_accessible = False
    _attr_volume_step = 0.01
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
    )

    def __init__(self, coordinator: HegelCoordinator) -> None:
        super().__init__(coordinator)
        options = coordinator.config_entry.options
        self._max_volume = int(options.get(CONF_MAX_VOLUME, DEFAULT_MAX_VOLUME))
        # Keyed by the amp's own input name, e.g. {"Analog 1": "Turntable"}.
        self._source_names: dict[str, str] = options.get(CONF_SOURCE_NAMES, {})
        self._hidden_sources: set[str] = set(options.get(CONF_HIDDEN_SOURCES, []))
        self._update_attrs()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attrs()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        # An amp that does not answer is shown as off, not unavailable.
        return self.coordinator.data is not None

    def _update_attrs(self) -> None:
        state = self.coordinator.data
        if state is None or not state.is_on:
            self._attr_state = MediaPlayerState.OFF
            self._attr_volume_level = None
            self._attr_is_volume_muted = None
            self._attr_source = None
            self._attr_source_list = None
            self._clear_media()
            return

        sources = self.coordinator.sources
        self._attr_source_list = [
            self._display_name(name)
            for name in sources.values()
            if name not in self._hidden_sources
        ] or None
        amp_name = sources.get(state.source) if state.source else None
        self._attr_source = self._display_name(amp_name) if amp_name else None
        self._attr_volume_level = state.volume / 100 if state.volume is not None else None
        self._attr_is_volume_muted = state.muted

        player = state.player
        self._attr_state = PLAYER_STATES.get(player.get("state"), MediaPlayerState.ON)
        track = player.get("trackRoles") or {}
        # On a physical input the amp still sends trackRoles, with empty metadata.
        if not track.get("title"):
            self._clear_media()
            return
        meta = (track.get("mediaData") or {}).get("metaData") or {}
        self._attr_media_content_type = MediaType.MUSIC
        self._attr_media_title = track.get("title")
        self._attr_media_artist = meta.get("artist")
        self._attr_media_album_name = meta.get("album")
        self._attr_media_image_url = track.get("icon")
        self._attr_app_name = meta.get("serviceName") or (player.get("mediaRoles") or {}).get(
            "title"
        )
        duration = (player.get("status") or {}).get("duration")
        self._attr_media_duration = round(duration / 1000) if duration else None
        if state.play_time_ms is not None:
            self._attr_media_position = round(state.play_time_ms / 1000)
            self._attr_media_position_updated_at = state.play_time_at
        else:
            self._attr_media_position = None
            self._attr_media_position_updated_at = None

    def _display_name(self, amp_name: str) -> str:
        return self._source_names.get(amp_name) or amp_name

    def _clear_media(self) -> None:
        self._attr_media_content_type = None
        self._attr_media_title = None
        self._attr_media_artist = None
        self._attr_media_album_name = None
        self._attr_media_image_url = None
        self._attr_app_name = None
        self._attr_media_duration = None
        self._attr_media_position = None
        self._attr_media_position_updated_at = None

    async def _call(self, func: Callable[[], Awaitable[None]], *, needs_on: bool = True) -> None:
        state = self.coordinator.data
        if state is None or not state.reachable:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_responding",
                translation_placeholders={"host": self.coordinator.client.host},
            )
        if needs_on and not state.is_on:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="turned_off")
        try:
            await func()
        except HegelError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self._call(self.coordinator.client.power_on, needs_on=False)

    async def async_turn_off(self) -> None:
        await self._call(self.coordinator.client.power_standby, needs_on=False)

    async def async_set_volume_level(self, volume: float) -> None:
        level = min(round(volume * 100), self._max_volume)
        await self._call(lambda: self.coordinator.client.set_volume(level))

    async def async_volume_up(self) -> None:
        current = self.coordinator.data.volume or 0
        await self.async_set_volume_level((current + 1) / 100)

    async def async_volume_down(self) -> None:
        current = self.coordinator.data.volume or 0
        await self.async_set_volume_level(max(current - 1, 0) / 100)

    async def async_mute_volume(self, mute: bool) -> None:
        await self._call(lambda: self.coordinator.client.set_mute(mute))

    async def async_select_source(self, source: str) -> None:
        index = next(
            (
                i
                for i, name in self.coordinator.sources.items()
                if source in (name, self._display_name(name))
            ),
            None,
        )
        if index is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_source",
                translation_placeholders={"source": source},
            )
        await self._call(lambda: self.coordinator.client.set_source(index))

    async def async_media_play(self) -> None:
        await self._call(lambda: self.coordinator.client.control("play"))

    async def async_media_pause(self) -> None:
        await self._call(lambda: self.coordinator.client.control("pause"))

    async def async_media_stop(self) -> None:
        await self._call(lambda: self.coordinator.client.control("stop"))

    async def async_media_next_track(self) -> None:
        await self._call(lambda: self.coordinator.client.control("next"))

    async def async_media_previous_track(self) -> None:
        await self._call(lambda: self.coordinator.client.control("previous"))
