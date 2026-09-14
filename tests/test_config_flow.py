"""Config flow tests."""

from __future__ import annotations

from ipaddress import ip_address
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hegel_streaming.api import HegelConnectionError
from custom_components.hegel_streaming.const import CONF_MAX_VOLUME, DOMAIN

from .conftest import DEVICE, HOST, UNIQUE_ID

PROBE = "custom_components.hegel_streaming.config_flow.async_probe"
IP_CONTROL = "custom_components.hegel_streaming.config_flow.async_has_ip_control"
SETUP = "custom_components.hegel_streaming.async_setup_entry"

ZEROCONF = ZeroconfServiceInfo(
    ip_address=ip_address(HOST),
    ip_addresses=[ip_address(HOST)],
    hostname="H400-000000.local.",
    name=f"{UNIQUE_ID}._sues800device._tcp.local.",
    port=80,
    type="_sues800device._tcp.local.",
    properties={
        "name": "H400",
        "serial": "H400-000000",
        "uuid": UNIQUE_ID,
        "manufacturer": "Hegel",
        "ip": HOST,
    },
)


async def test_user_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    with patch(PROBE, return_value=DEVICE), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": f" {HOST} "}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "H400"
    assert result["data"] == {"host": HOST}
    assert result["result"].unique_id == UNIQUE_ID


async def test_user_flow_cannot_connect(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with (
        patch(PROBE, side_effect=HegelConnectionError("timeout")),
        patch(IP_CONTROL, return_value=False),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    with patch(PROBE, return_value=DEVICE), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_legacy_model(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with (
        patch(PROBE, side_effect=HegelConnectionError("timeout")),
        patch(IP_CONTROL, return_value=True) as ip_control,
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "legacy_model"}
    assert result["description_placeholders"]["core_url"].endswith("/integrations/hegel/")
    ip_control.assert_awaited_once_with(HOST)


async def test_user_flow_already_configured(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PROBE, return_value=DEVICE):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.168.1.99"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data["host"] == "192.168.1.99"


async def test_zeroconf_flow(hass: HomeAssistant) -> None:
    with patch(PROBE, return_value=DEVICE):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=ZEROCONF
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"

    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"host": HOST}


async def test_zeroconf_updates_host(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry = MockConfigEntry(domain=DOMAIN, unique_id=UNIQUE_ID, data={"host": "10.0.0.2"})
    config_entry.add_to_hass(hass)
    probe = AsyncMock(return_value=DEVICE)
    with patch(PROBE, probe):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=ZEROCONF
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data["host"] == HOST
    probe.assert_not_called()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"address_changed_{config_entry.entry_id}")
    assert issue is not None
    assert issue.translation_placeholders == {
        "name": config_entry.title,
        "old_host": "10.0.0.2",
        "new_host": HOST,
    }


async def test_zeroconf_same_host_no_issue(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=ZEROCONF
    )
    assert result["reason"] == "already_configured"
    assert not ir.async_get(hass).issues


async def test_zeroconf_not_hegel(hass: HomeAssistant) -> None:
    info = ZeroconfServiceInfo(
        ip_address=ZEROCONF.ip_address,
        ip_addresses=ZEROCONF.ip_addresses,
        hostname=ZEROCONF.hostname,
        name=ZEROCONF.name,
        port=80,
        type=ZEROCONF.type,
        properties={**ZEROCONF.properties, "manufacturer": "Other"},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=info
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_hegel"


async def test_options_flow(
    hass: HomeAssistant, config_entry: MockConfigEntry, client, no_event_loop
) -> None:
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"]["zsp_url"].startswith("https://zerostorypoints.com/")
    assert result["description_placeholders"]["hifisync_url"].startswith("https://hifisync.com/")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MAX_VOLUME: 60}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_MAX_VOLUME: 60}
