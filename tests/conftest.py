"""Fixtures."""

from __future__ import annotations

from collections.abc import Generator
import copy
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hegel_streaming.api import HegelDeviceInfo, HegelState
from custom_components.hegel_streaming.const import DOMAIN

HOST = "192.168.1.50"
UNIQUE_ID = "hegelh600-00000000-1111-2222-3333-444444444444"

DEVICE = HegelDeviceInfo(
    unique_id=UNIQUE_ID, name="H400", model="H400", manufacturer="Hegel", firmware="1205.1011"
)

SOURCES = {1: "XLR", 2: "Analog 1", 3: "Analog 2", 9: "USB", 10: "Network"}

# Trimmed from a real H400 answer while playing Spotify.
PLAYER_SPOTIFY: dict[str, Any] = {
    "state": "playing",
    "mediaRoles": {"title": "Discover Weekly"},
    "status": {"duration": 265546},
    "trackRoles": {
        "title": "The Great Living Library - Orenda Remix",
        "icon": "https://i.scdn.co/image/cover.jpg",
        "mediaData": {
            "activeResource": {"mimeType": "audio/unknown", "quality": {"spotifyHifi": True}},
            "metaData": {
                "album": "The Great Living Library (Orenda Remix)",
                "artist": "Deya Dova",
                "serviceName": "Spotify",
            },
        },
    },
}


def playing_state(**changes: Any) -> HegelState:
    state = HegelState(
        reachable=True,
        power="online",
        volume=35,
        muted=False,
        source=10,
        player=copy.deepcopy(PLAYER_SPOTIFY),
        play_time_ms=120_000,
    )
    for key, value in changes.items():
        setattr(state, key, value)
    return state


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components in every test."""


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, title="H400", unique_id=UNIQUE_ID, data={"host": HOST})


@pytest.fixture
def client() -> Generator[AsyncMock]:
    """A HegelClient mock, used by the integration setup."""
    with patch("custom_components.hegel_streaming.HegelClient", autospec=True) as cls:
        mock = cls.return_value
        mock.host = HOST
        mock.get_device_info.return_value = DEVICE
        mock.get_sources.return_value = SOURCES
        mock.get_state.return_value = playing_state()
        yield mock


@pytest.fixture
def no_event_loop() -> Generator[None]:
    with patch(
        "custom_components.hegel_streaming.coordinator.HegelCoordinator.async_run_event_loop",
        new=AsyncMock(return_value=None),
    ):
        yield
