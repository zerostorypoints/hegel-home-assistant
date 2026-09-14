"""Stream format sensors: quality, codec, sample rate, bit depth, bitrate, service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfDataRate, UnitOfFrequency
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import HegelState
from .coordinator import HegelConfigEntry
from .entity import HegelEntity

PARALLEL_UPDATES = 0

QUALITY_OPTIONS = ["hi_res", "cd", "lossless", "lossy", "dsd"]


def _resource(state: HegelState) -> dict[str, Any]:
    if not state.is_on or state.player.get("state") not in ("playing", "paused"):
        return {}
    track = state.player.get("trackRoles") or {}
    return (track.get("mediaData") or {}).get("activeResource") or {}


def quality(state: HegelState) -> str | None:
    """Classify the stream: hi_res, cd, lossless, lossy or dsd."""
    res = _resource(state)
    if not res:
        return None
    codec = (res.get("codec") or "").lower()
    rate = res.get("sampleFrequency") or 0
    bits = res.get("bitsPerSample") or 0
    flags = res.get("quality") or {}
    if "dsd" in codec:
        return "dsd"
    if flags.get("qobuzHiRes") or bits > 16 or rate > 48000:
        return "hi_res"
    if bits == 16 and rate in (44100, 48000):
        return "cd"
    # Spotify reports no format, only this flag.
    if flags.get("spotifyHifi"):
        return "lossless"
    if codec:
        return "lossy"
    return None


def _service(state: HegelState) -> str | None:
    if not state.is_on:
        return None
    meta = ((state.player.get("trackRoles") or {}).get("mediaData") or {}).get("metaData") or {}
    return meta.get("serviceName") or (state.player.get("mediaRoles") or {}).get("title")


def _number(key: str, scale: float = 1) -> Callable[[HegelState], float | None]:
    def get(state: HegelState) -> float | None:
        value = _resource(state).get(key)
        return round(value / scale, 1) if isinstance(value, (int, float)) and value else None

    return get


@dataclass(frozen=True, kw_only=True)
class HegelSensorDescription(SensorEntityDescription):
    value_fn: Callable[[HegelState], Any]


SENSORS: tuple[HegelSensorDescription, ...] = (
    HegelSensorDescription(
        key="audio_quality",
        translation_key="audio_quality",
        device_class=SensorDeviceClass.ENUM,
        options=QUALITY_OPTIONS,
        value_fn=quality,
    ),
    HegelSensorDescription(
        key="codec",
        translation_key="codec",
        value_fn=lambda s: _resource(s).get("codec") or None,
    ),
    HegelSensorDescription(
        key="sample_rate",
        translation_key="sample_rate",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.KILOHERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_number("sampleFrequency", 1000),
    ),
    HegelSensorDescription(
        key="bit_depth",
        translation_key="bit_depth",
        native_unit_of_measurement="bit",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_number("bitsPerSample"),
    ),
    HegelSensorDescription(
        key="bitrate",
        translation_key="bitrate",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_number("bitRate", 1000),
    ),
    HegelSensorDescription(
        key="streaming_service",
        translation_key="streaming_service",
        value_fn=_service,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HegelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(HegelSensor(entry.runtime_data, d) for d in SENSORS)


class HegelSensor(HegelEntity, SensorEntity):
    entity_description: HegelSensorDescription

    def __init__(self, coordinator, description: HegelSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
