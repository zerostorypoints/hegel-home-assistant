"""Config flow: manual host entry and zeroconf discovery."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers import issue_registry as ir, selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
import voluptuous as vol

from .api import (
    HegelConnectionError,
    HegelDeviceInfo,
    HegelError,
    async_has_ip_control,
    async_probe,
)
from .const import CONF_MAX_VOLUME, DEFAULT_MAX_VOLUME, DOMAIN, HIFISYNC_URL

_LOGGER = logging.getLogger(__name__)


class HegelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a Hegel amplifier."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._device: HegelDeviceInfo | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> HegelOptionsFlow:
        return HegelOptionsFlow()

    async def _probe(self, host: str) -> tuple[HegelDeviceInfo | None, str | None]:
        try:
            return await async_probe(host, async_get_clientsession(self.hass)), None
        except (HegelConnectionError, TimeoutError):
            error = "cannot_connect"
        except HegelError:
            _LOGGER.exception("Unexpected answer from %s", host)
            error = "not_hegel"
        # An older Hegel amp has no web API but answers IP control: point to the core integration.
        if await async_has_ip_control(host):
            return None, "legacy_model"
        return None, error

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            device, error = await self._probe(host)
            if device:
                await self.async_set_unique_id(device.unique_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(title=device.name, data={CONF_HOST: host})
            errors["base"] = error or "unknown"
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_HOST): str}), user_input
            ),
            errors=errors,
            description_placeholders={"hifisync_url": HIFISYNC_URL},
        )

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        props = discovery_info.properties
        if (props.get("manufacturer") or "").lower() != "hegel":
            return self.async_abort(reason="not_hegel")
        host = props.get("ip") or discovery_info.host
        if uuid := props.get("uuid"):
            await self.async_set_unique_id(uuid)
            self._async_follow_new_host(host)
        device, error = await self._probe(host)
        if not device:
            return self.async_abort(reason=error or "cannot_connect")
        await self.async_set_unique_id(device.unique_id)
        self._async_follow_new_host(host)
        self._host, self._device = host, device
        self.context["title_placeholders"] = {"name": device.name}
        return await self.async_step_zeroconf_confirm()

    @callback
    def _async_follow_new_host(self, host: str) -> None:
        """Abort if the amp is set up, taking over a changed address.

        A changed address means the router gave the amp a new one. It is followed
        automatically, and a repair issue suggests reserving the address.
        """
        entry = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, self.unique_id)
        if entry and entry.data.get(CONF_HOST) != host:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"address_changed_{entry.entry_id}",
                is_fixable=False,
                is_persistent=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key="address_changed",
                translation_placeholders={
                    "name": entry.title,
                    "old_host": entry.data.get(CONF_HOST, ""),
                    "new_host": host,
                },
            )
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._device and self._host
        if user_input is not None:
            return self.async_create_entry(title=self._device.name, data={CONF_HOST: self._host})
        self._set_confirm_only()
        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={
                "name": self._device.name,
                "model": self._device.model,
                "host": self._host,
                "hifisync_url": HIFISYNC_URL,
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            device, error = await self._probe(host)
            if device:
                await self.async_set_unique_id(device.unique_id)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_HOST: host})
            errors["base"] = error or "unknown"
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_HOST): str}), user_input or entry.data
            ),
            errors=errors,
        )


class HegelOptionsFlow(OptionsFlowWithReload):
    """Volume limit."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        schema = vol.Schema(
            {
                vol.Required(CONF_MAX_VOLUME, default=DEFAULT_MAX_VOLUME): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10, max=100, step=1, mode=selector.NumberSelectorMode.SLIDER
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, self.config_entry.options),
        )
