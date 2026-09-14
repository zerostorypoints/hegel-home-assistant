"""API client tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hegel_streaming.api import (
    HegelClient,
    HegelConnectionError,
    HegelQueueExpiredError,
    HegelState,
    async_has_ip_control,
    unwrap,
)

BASE = "http://amp"


def test_unwrap() -> None:
    assert unwrap({"type": "i32_", "i32_": 35}) == 35
    assert unwrap({"type": "bool_", "bool_": False}) is False
    assert unwrap(7) == 7


def test_state_apply() -> None:
    state = HegelState(reachable=True)
    assert state.apply(
        "powermanager:target", {"powerTarget": {"target": "online"}, "type": "powerTarget"}
    )
    assert state.is_on
    assert state.apply("player:volume", {"type": "i32_", "i32_": 22})
    assert state.volume == 22
    assert not state.apply("unknown:path", 1)
    state.apply(
        "powermanager:target", {"powerTarget": {"target": "networkStandby"}, "type": "powerTarget"}
    )
    assert not state.is_on


async def test_get_state(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    def answer(path: str, value: object) -> None:
        aioclient_mock.get(
            f"{BASE}/api/getData", params={"path": path, "roles": "value"}, json=[value]
        )

    answer("powermanager:target", {"powerTarget": {"target": "online"}, "type": "powerTarget"})
    answer("player:volume", {"type": "i32_", "i32_": 35})
    answer("settings:/mediaPlayer/mute", {"type": "bool_", "bool_": True})
    answer("hegel:activePhysicalSource", {"type": "i32_", "i32_": 10})
    answer("player:player/data", {"state": "playing"})
    answer("player:player/data/playTime", {"type": "i64_", "i64_": 5000})

    session = async_get_clientsession(hass)
    state = await HegelClient("amp", session).get_state()
    assert state.is_on and state.volume == 35 and state.muted and state.source == 10
    assert state.player == {"state": "playing"}
    assert state.play_time_ms == 5000


async def test_timeout_is_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE}/api/getData", exc=TimeoutError())
    session = async_get_clientsession(hass)
    with pytest.raises(HegelConnectionError):
        await HegelClient("amp", session).get("player:volume")


async def test_expired_queue(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{BASE}/api/event/pollQueue", status=400, text="Unknown queue id!")
    session = async_get_clientsession(hass)
    with pytest.raises(HegelQueueExpiredError):
        await HegelClient("amp", session).poll_queue("{dead}", 1)


async def test_sources(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(
        f"{BASE}/api/getRows",
        json={
            "rows": [
                {"title": "XLR", "value": {"type": "i32_", "i32_": 1}},
                {"title": "Network", "value": {"type": "i32_", "i32_": 10}},
            ]
        },
    )
    session = async_get_clientsession(hass)
    assert await HegelClient("amp", session).get_sources() == {1: "XLR", 10: "Network"}


async def test_power_on_payload(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(f"{BASE}/api/setData", text="null")
    session = async_get_clientsession(hass)
    await HegelClient("amp", session).power_on()
    assert aioclient_mock.mock_calls[-1][2] == {
        "path": "powermanager:goOnline",
        "role": "activate",
        "value": {},
    }


def _fake_connection(reply: bytes | None):
    """Stand-in for asyncio.open_connection to port 50001 (tests may not open sockets)."""
    import asyncio
    from unittest.mock import MagicMock

    async def open_connection(host, port):
        reader = asyncio.StreamReader()
        if reply is not None:
            reader.feed_data(reply)
            reader.feed_eof()
        writer = MagicMock()
        writer.drain = AsyncMock()
        writer.sent = []
        writer.write.side_effect = writer.sent.append
        open_connection.writer = writer
        return reader, writer

    return open_connection


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (b"-p.1\r", True),
        (b"-p.0\r", True),
        (b"-e.1\r", True),
        (b"HTTP/1.0 400\r\n", False),
        (b"", False),
        (None, False),
    ],
)
async def test_ip_control_probe(reply: bytes | None, expected: bool) -> None:
    fake = _fake_connection(reply)
    with patch("custom_components.hegel_streaming.api.asyncio.open_connection", fake):
        assert await async_has_ip_control("amp", timeout=0.2) is expected
    assert fake.writer.sent == [b"-p.?\r"]
    fake.writer.close.assert_called_once()


async def test_ip_control_probe_refused() -> None:
    with patch(
        "custom_components.hegel_streaming.api.asyncio.open_connection",
        AsyncMock(side_effect=ConnectionRefusedError),
    ):
        assert await async_has_ip_control("amp", timeout=0.2) is False
