"""Media player, sensor and coordinator tests."""

from __future__ import annotations

from homeassistant.components.media_player import (
    ATTR_INPUT_SOURCE,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    DOMAIN as MP_DOMAIN,
    SERVICE_SELECT_SOURCE,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_MEDIA_PAUSE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    SERVICE_VOLUME_MUTE,
    SERVICE_VOLUME_SET,
    SERVICE_VOLUME_UP,
    STATE_OFF,
    STATE_ON,
    STATE_PLAYING,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hegel_streaming.api import HegelConnectionError, HegelState
from custom_components.hegel_streaming.const import CONF_MAX_VOLUME

from .conftest import HOST, playing_state

PLAYER = "media_player.h400"


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_playing(hass: HomeAssistant, config_entry, client, no_event_loop) -> None:
    await setup(hass, config_entry)
    state = hass.states.get(PLAYER)
    assert state.state == STATE_PLAYING
    assert state.attributes["media_title"] == "The Great Living Library - Orenda Remix"
    assert state.attributes["media_artist"] == "Deya Dova"
    assert state.attributes["app_name"] == "Spotify"
    assert state.attributes["media_duration"] == 266
    assert state.attributes["media_position"] == 120
    assert state.attributes[ATTR_MEDIA_VOLUME_LEVEL] == 0.35
    assert state.attributes[ATTR_INPUT_SOURCE] == "Network"
    assert state.attributes["source_list"] == ["XLR", "Analog 1", "Analog 2", "USB", "Network"]
    assert hass.states.get("sensor.h400_audio_quality").state == "lossless"
    assert hass.states.get("sensor.h400_streaming_service").state == "Spotify"
    assert hass.states.get("binary_sensor.h400_network").state == STATE_ON


async def test_standby_is_off(hass: HomeAssistant, config_entry, client, no_event_loop) -> None:
    client.get_state.return_value = HegelState(
        reachable=True, power="networkStandby", volume=23, source=0
    )
    await setup(hass, config_entry)
    state = hass.states.get(PLAYER)
    assert state.state == STATE_OFF
    assert ATTR_MEDIA_VOLUME_LEVEL not in state.attributes
    assert hass.states.get("binary_sensor.h400_network").state == STATE_ON
    assert hass.states.get("sensor.h400_audio_quality").state == "unknown"

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            MP_DOMAIN,
            SERVICE_VOLUME_SET,
            {ATTR_ENTITY_ID: PLAYER, ATTR_MEDIA_VOLUME_LEVEL: 0.3},
            blocking=True,
        )
    await hass.services.async_call(
        MP_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: PLAYER}, blocking=True
    )
    client.power_on.assert_awaited_once()


async def test_not_responding_is_off(
    hass: HomeAssistant, config_entry, client, no_event_loop
) -> None:
    await setup(hass, config_entry)
    client.get_state.side_effect = HegelConnectionError("timeout")
    await refresh(hass, config_entry)

    state = hass.states.get(PLAYER)
    assert state.state == STATE_OFF
    assert hass.states.get("binary_sensor.h400_network").state == STATE_OFF

    with pytest.raises(HomeAssistantError, match="not responding"):
        await hass.services.async_call(
            MP_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: PLAYER}, blocking=True
        )
    client.power_on.assert_not_awaited()

    client.get_state.side_effect = None
    await refresh(hass, config_entry)
    assert hass.states.get(PLAYER).state == STATE_PLAYING


async def test_setup_retries_when_not_responding(
    hass: HomeAssistant, config_entry, client, no_event_loop
) -> None:
    client.get_device_info.side_effect = HegelConnectionError("timeout")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_starts_off_when_seen_before(
    hass: HomeAssistant, config_entry, client, no_event_loop
) -> None:
    await setup(hass, config_entry)
    assert config_entry.data["device"]["model"] == "H400"
    assert await hass.config_entries.async_unload(config_entry.entry_id)

    client.get_device_info.side_effect = HegelConnectionError("timeout")
    client.get_state.side_effect = HegelConnectionError("timeout")
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(PLAYER).state == STATE_OFF
    assert hass.states.get("binary_sensor.h400_network").state == STATE_OFF


async def test_commands(hass: HomeAssistant, config_entry, client, no_event_loop) -> None:
    await setup(hass, config_entry)

    async def call(service: str, **data) -> None:
        await hass.services.async_call(
            MP_DOMAIN, service, {ATTR_ENTITY_ID: PLAYER, **data}, blocking=True
        )

    await call(SERVICE_VOLUME_SET, **{ATTR_MEDIA_VOLUME_LEVEL: 0.4})
    client.set_volume.assert_awaited_with(40)
    await call(SERVICE_VOLUME_UP)
    client.set_volume.assert_awaited_with(36)
    await call(SERVICE_VOLUME_MUTE, **{ATTR_MEDIA_VOLUME_MUTED: True})
    client.set_mute.assert_awaited_with(True)
    await call(SERVICE_SELECT_SOURCE, **{ATTR_INPUT_SOURCE: "USB"})
    client.set_source.assert_awaited_with(9)
    await call(SERVICE_MEDIA_PAUSE)
    client.control.assert_awaited_with("pause")
    await call(SERVICE_TURN_OFF)
    client.power_standby.assert_awaited_once()

    with pytest.raises(ServiceValidationError):
        await call(SERVICE_SELECT_SOURCE, **{ATTR_INPUT_SOURCE: "Phono"})


async def test_custom_and_hidden_inputs(hass: HomeAssistant, client, no_event_loop) -> None:
    client.get_state.return_value = playing_state(
        source=2,
        player={"state": "stopped", "trackRoles": {"mediaData": {"metaData": {"serviceName": ""}}}},
    )
    entry = MockConfigEntry(
        domain="hegel_streaming",
        unique_id="x",
        data={"host": HOST},
        options={"source_names": {"Analog 1": "Turntable"}, "hidden_sources": ["XLR", "USB"]},
    )
    await setup(hass, entry)
    state = hass.states.get(PLAYER)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_INPUT_SOURCE] == "Turntable"
    assert state.attributes["source_list"] == ["Turntable", "Analog 2", "Network"]
    # Nothing is streaming on a physical input: no media attributes.
    assert "media_content_type" not in state.attributes
    assert "media_title" not in state.attributes

    await hass.services.async_call(
        MP_DOMAIN,
        SERVICE_SELECT_SOURCE,
        {ATTR_ENTITY_ID: PLAYER, ATTR_INPUT_SOURCE: "Turntable"},
        blocking=True,
    )
    client.set_source.assert_awaited_with(2)
    # The amp's own name still works, hidden or not.
    await hass.services.async_call(
        MP_DOMAIN,
        SERVICE_SELECT_SOURCE,
        {ATTR_ENTITY_ID: PLAYER, ATTR_INPUT_SOURCE: "XLR"},
        blocking=True,
    )
    client.set_source.assert_awaited_with(1)


async def test_sources_cached_for_offline_start(
    hass: HomeAssistant, config_entry, client, no_event_loop
) -> None:
    await setup(hass, config_entry)
    assert config_entry.data["sources"]["2"] == "Analog 1"
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    client.get_device_info.side_effect = HegelConnectionError("timeout")
    client.get_state.side_effect = HegelConnectionError("timeout")
    client.get_sources.reset_mock()
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.runtime_data.sources[2] == "Analog 1"
    client.get_sources.assert_not_called()


async def test_volume_limit(hass: HomeAssistant, client, no_event_loop) -> None:
    entry = MockConfigEntry(
        domain="hegel_streaming", unique_id="x", data={"host": HOST}, options={CONF_MAX_VOLUME: 60}
    )
    await setup(hass, entry)
    await hass.services.async_call(
        MP_DOMAIN,
        SERVICE_VOLUME_SET,
        {ATTR_ENTITY_ID: PLAYER, ATTR_MEDIA_VOLUME_LEVEL: 1.0},
        blocking=True,
    )
    client.set_volume.assert_awaited_with(60)


async def test_push_events(hass: HomeAssistant, config_entry, client, no_event_loop) -> None:
    await setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    client.get.return_value = 30_000

    await coordinator._async_handle_events(
        [
            {
                "path": "player:volume",
                "itemType": "update",
                "itemValue": {"type": "i32_", "i32_": 20},
            },
            {
                "path": "player:player/data",
                "itemType": "update",
                "itemValue": {**playing_state().player, "state": "paused"},
            },
        ]
    )
    await hass.async_block_till_done()
    state = hass.states.get(PLAYER)
    assert state.attributes[ATTR_MEDIA_VOLUME_LEVEL] == 0.2
    assert state.state == "paused"
    assert state.attributes["media_position"] == 30

    await coordinator._async_handle_events(
        [
            {
                "path": "powermanager:target",
                "itemType": "update",
                "itemValue": {"powerTarget": {"target": "networkStandby"}, "type": "powerTarget"},
            },
        ]
    )
    await hass.async_block_till_done()
    assert hass.states.get(PLAYER).state == STATE_OFF


async def test_diagnostics_and_unload(
    hass: HomeAssistant, config_entry, client, no_event_loop
) -> None:
    from custom_components.hegel_streaming.diagnostics import async_get_config_entry_diagnostics

    await setup(hass, config_entry)
    diag = await async_get_config_entry_diagnostics(hass, config_entry)
    assert diag["device"]["model"] == "H400"
    assert diag["state"]["volume"] == 35

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_icons_file_matches_entities() -> None:
    """Every translation key has an icon, and no icon points at a missing entity."""
    import json
    from pathlib import Path

    from custom_components.hegel_streaming.sensor import QUALITY_OPTIONS, SENSORS

    root = Path(__file__).parent.parent / "custom_components" / "hegel_streaming"
    icons = json.loads((root / "icons.json").read_text())["entity"]
    assert set(icons["sensor"]) == {d.translation_key for d in SENSORS}
    assert set(icons["sensor"]["audio_quality"]["state"]) == set(QUALITY_OPTIONS)
    assert set(icons["binary_sensor"]) == {"network"}
