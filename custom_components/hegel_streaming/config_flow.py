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
from .const import (
    CONF_HIDDEN_SOURCES,
    CONF_MAX_VOLUME,
    CONF_SOURCE_NAMES,
    CONF_SOURCES,
    CORE_HEGEL_URL,
    DEFAULT_MAX_VOLUME,
    DOMAIN,
    HIFISYNC_URL,
    ZSP_URL,
)

CREDITS = {"hifisync_url": HIFISYNC_URL, "zsp_url": ZSP_URL}

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
            description_placeholders={**CREDITS, "core_url": CORE_HEGEL_URL},
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
            return self.async_abort(
                reason=error or "cannot_connect",
                description_placeholders={"core_url": CORE_HEGEL_URL},
            )
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
                **CREDITS,
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
            description_placeholders={**CREDITS, "core_url": CORE_HEGEL_URL},
        )


class HegelOptionsFlow(OptionsFlowWithReload):
    """Volume limit, then input names and hidden inputs."""

    def __init__(self) -> None:
        self._options: dict[str, Any] = {}

    def _amp_sources(self) -> list[str]:
        """Input names as the amp reports them, in the amp's order."""
        cached = self.config_entry.data.get(CONF_SOURCES, {})
        return [cached[k] for k in sorted(cached, key=int)]

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._options = {CONF_MAX_VOLUME: user_input[CONF_MAX_VOLUME]}
            if self._amp_sources():
                return await self.async_step_inputs()
            return self.async_create_entry(data={**self.config_entry.options, **self._options})
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
            description_placeholders=CREDITS,
        )

    async def async_step_inputs(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """One name field per input (labelled with the amp's name) and a list to hide."""
        sources = self._amp_sources()
        if user_input is not None:
            names = {
                amp: custom.strip()
                for amp in sources
                if (custom := (user_input.get(amp) or "").strip()) and custom != amp
            }
            hidden = [amp for amp in sources if amp in user_input.get(CONF_HIDDEN_SOURCES, [])]
            return self.async_create_entry(
                data={**self._options, CONF_SOURCE_NAMES: names, CONF_HIDDEN_SOURCES: hidden}
            )
        current_names: dict[str, str] = self.config_entry.options.get(CONF_SOURCE_NAMES, {})
        fields: dict[Any, Any] = {
            vol.Optional(amp, description={"suggested_value": current_names.get(amp, "")}): str
            for amp in sources
        }
        fields[
            vol.Optional(
                CONF_HIDDEN_SOURCES,
                default=[
                    a
                    for a in self.config_entry.options.get(CONF_HIDDEN_SOURCES, [])
                    if a in sources
                ],
            )
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=sources, multiple=True, mode=selector.SelectSelectorMode.LIST
            )
        )
        return self.async_show_form(
            step_id="inputs", data_schema=vol.Schema(fields), description_placeholders=CREDITS
        )
