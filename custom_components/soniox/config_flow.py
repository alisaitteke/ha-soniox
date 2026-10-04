"""Config flow for the Soniox integration."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from soniox.errors import SonioxAuthenticationError, SonioxError

from .client import async_validate_api_credentials, unique_id_from_api_key
from .const import CONF_REGION, DEFAULT_OPTIONS, DEFAULT_REGION, DOMAIN
from .models import SonioxConfigEntry

_LOGGER = logging.getLogger(__name__)

_REGION_OPTIONS = [
    SelectOptionDict(value="us", label="United States"),
    SelectOptionDict(value="eu", label="European Union"),
    SelectOptionDict(value="jp", label="Japan"),
    SelectOptionDict(value="in", label="India"),
]


def _user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return the API key + region schema."""
    suggested = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_API_KEY): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(
                CONF_REGION,
                default=suggested.get(CONF_REGION, DEFAULT_REGION),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=_REGION_OPTIONS,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


OPTIONS_SCHEMA = vol.Schema({})


async def _async_validate(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate credentials and return flow errors."""
    try:
        await async_validate_api_credentials(
            user_input[CONF_API_KEY], user_input[CONF_REGION]
        )
    except SonioxAuthenticationError:
        return {"base": "invalid_auth"}
    except (httpx.ConnectError, httpx.TimeoutException, SonioxError):
        return {"base": "cannot_connect"}
    except Exception:
        _LOGGER.exception("Unexpected error validating Soniox credentials")
        return {"base": "unknown"}
    return {}


class SonioxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Soniox."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _async_validate(user_input)
            if not errors:
                await self.async_set_unique_id(
                    unique_id_from_api_key(user_input[CONF_API_KEY])
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Soniox",
                    data={
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_REGION: user_input[CONF_REGION],
                    },
                    options=DEFAULT_OPTIONS,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle reauthentication when the API key is rejected."""
        _ = entry_data
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new API key."""
        reauth_entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            region = reauth_entry.data[CONF_REGION]
            payload = {CONF_API_KEY: user_input[CONF_API_KEY], CONF_REGION: region}
            errors = await _async_validate(payload)
            if not errors:
                await self.async_set_unique_id(
                    unique_id_from_api_key(user_input[CONF_API_KEY])
                )
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={CONF_API_KEY: user_input[CONF_API_KEY]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow changing API key and region."""
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _async_validate(user_input)
            if not errors:
                await self.async_set_unique_id(
                    unique_id_from_api_key(user_input[CONF_API_KEY])
                )
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates={
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_REGION: user_input[CONF_REGION],
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_user_schema(
                user_input
                or {
                    CONF_REGION: reconfigure_entry.data[CONF_REGION],
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: SonioxConfigEntry,
    ) -> SonioxOptionsFlow:
        """Create the options flow."""
        return SonioxOptionsFlow()


class SonioxOptionsFlow(OptionsFlow):
    """Options flow skeleton. STT/TTS settings are added in the implementation phase."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(
                data={**self.config_entry.options, **user_input}
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
