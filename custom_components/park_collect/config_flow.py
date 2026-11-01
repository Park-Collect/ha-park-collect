"""Config flow for the Park & Collect integration."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import ParkCollectAuthError, ParkCollectClient, ParkCollectError
from .const import DOMAIN

STEP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    }
)


class ParkCollectConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up Park & Collect with an API key from the profile page."""

    VERSION = 1

    async def _async_validate(self, api_key: str) -> str | None:
        """Return an error key, or None if the API key works."""
        client = ParkCollectClient(async_get_clientsession(self.hass), api_key)
        try:
            await client.async_get_parking_lots()
        except ParkCollectAuthError:
            return "invalid_auth"
        except ParkCollectError:
            return "cannot_connect"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            await self.async_set_unique_id(_key_id(api_key))
            self._abort_if_unique_id_configured()
            if (error := await self._async_validate(api_key)) is None:
                return self.async_create_entry(
                    title="Park & Collect", data={CONF_API_KEY: api_key}
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="user", data_schema=STEP_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle a revoked or replaced API key."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the new API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            if (error := await self._async_validate(api_key)) is None:
                entry = self._get_reauth_entry()
                self.hass.config_entries.async_update_entry(
                    entry, unique_id=_key_id(api_key)
                )
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: api_key}
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=STEP_SCHEMA, errors=errors
        )


def _key_id(api_key: str) -> str:
    """Identify a key without exposing it in the entity registry."""
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]
