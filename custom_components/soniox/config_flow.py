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
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from soniox.errors import SonioxAuthenticationError, SonioxError

from .catalog import PERM_MODEL_LISTING, SonioxCatalog, async_load_catalog
from .client import (
    async_validate_api_credentials,
    create_soniox_client,
    unique_id_from_api_key,
)
from .const import (
    CONF_CONTEXT,
    CONF_CONTEXT_TERMS,
    CONF_ENABLE_DIARIZATION,
    CONF_ENABLE_ENDPOINT_DETECTION,
    CONF_ENABLE_TRANSLATION,
    CONF_LANGUAGE_HINTS,
    CONF_MAX_ENDPOINT_DELAY_MS,
    CONF_REDUCE_SILENCE,
    CONF_REGION,
    CONF_STT_MODEL,
    CONF_TRANSLATION_TARGET,
    CONF_TTS_MODEL,
    CONF_TTS_SPEED,
    CONF_TTS_VOICE,
    DEFAULT_ENABLE_DIARIZATION,
    DEFAULT_ENABLE_ENDPOINT_DETECTION,
    DEFAULT_ENABLE_TRANSLATION,
    DEFAULT_LANGUAGE,
    DEFAULT_MAX_ENDPOINT_DELAY_MS,
    DEFAULT_OPTIONS,
    DEFAULT_REDUCE_SILENCE,
    DEFAULT_REGION,
    DEFAULT_STT_MODEL,
    DEFAULT_TTS_MODEL,
    DEFAULT_TTS_SPEED,
    DEFAULT_TTS_VOICE,
    DOMAIN,
    LANGUAGE_HINTS,
    SONIOX_CONSOLE_URL,
)
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


_DESCRIPTION_PLACEHOLDERS = {"console_url": SONIOX_CONSOLE_URL}

_LANGUAGE_HINT_OPTIONS = [
    SelectOptionDict(value=code, label=code) for code in LANGUAGE_HINTS
]


def _option(options: dict[str, Any], key: str, default: Any) -> Any:
    """Return a stored option or its default."""
    if key not in options or options[key] is None:
        return default
    return options[key]


def _normalize_saved_options(data: dict[str, Any]) -> dict[str, Any]:
    """Coerce selector values into the stored options shape."""
    hints = data.get(CONF_LANGUAGE_HINTS) or []
    if isinstance(hints, str):
        hints = [part.strip() for part in hints.split(",") if part.strip()]
    return {
        **DEFAULT_OPTIONS,
        **data,
        CONF_LANGUAGE_HINTS: list(hints),
        CONF_CONTEXT: str(data.get(CONF_CONTEXT) or ""),
        CONF_CONTEXT_TERMS: str(data.get(CONF_CONTEXT_TERMS) or ""),
        CONF_ENABLE_ENDPOINT_DETECTION: bool(
            data.get(
                CONF_ENABLE_ENDPOINT_DETECTION, DEFAULT_ENABLE_ENDPOINT_DETECTION
            )
        ),
        CONF_MAX_ENDPOINT_DELAY_MS: int(
            data.get(CONF_MAX_ENDPOINT_DELAY_MS, DEFAULT_MAX_ENDPOINT_DELAY_MS)
        ),
        CONF_ENABLE_DIARIZATION: bool(
            data.get(CONF_ENABLE_DIARIZATION, DEFAULT_ENABLE_DIARIZATION)
        ),
        CONF_ENABLE_TRANSLATION: bool(
            data.get(CONF_ENABLE_TRANSLATION, DEFAULT_ENABLE_TRANSLATION)
        ),
        CONF_TRANSLATION_TARGET: str(
            data.get(CONF_TRANSLATION_TARGET) or DEFAULT_LANGUAGE
        ),
        CONF_TTS_SPEED: float(data.get(CONF_TTS_SPEED, DEFAULT_TTS_SPEED)),
        CONF_REDUCE_SILENCE: bool(
            data.get(CONF_REDUCE_SILENCE, DEFAULT_REDUCE_SILENCE)
        ),
    }


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
            description_placeholders=_DESCRIPTION_PLACEHOLDERS,
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
            description_placeholders=_DESCRIPTION_PLACEHOLDERS,
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
            description_placeholders=_DESCRIPTION_PLACEHOLDERS,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: SonioxConfigEntry,
    ) -> SonioxOptionsFlow:
        """Create the options flow."""
        return SonioxOptionsFlow()


class SonioxOptionsFlow(OptionsFlow):
    """STT then TTS options, populated from the Soniox catalog when permitted."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._catalog: SonioxCatalog | None = None
        self._stt_options: dict[str, Any] = {}

    async def _async_catalog(self) -> SonioxCatalog:
        """Load models and voices, creating a temporary client if needed."""
        if self._catalog is not None:
            return self._catalog
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime is not None:
            self._catalog = await async_load_catalog(runtime.client)
            return self._catalog
        client = create_soniox_client(
            self.config_entry.data[CONF_API_KEY],
            self.config_entry.data.get(CONF_REGION, DEFAULT_REGION),
        )
        try:
            self._catalog = await async_load_catalog(client)
        finally:
            await client.aclose()
        return self._catalog

    def _placeholders(self, catalog: SonioxCatalog) -> dict[str, str]:
        """Description placeholders including permission hints."""
        missing = ", ".join(catalog.missing_permissions)
        return {
            **_DESCRIPTION_PLACEHOLDERS,
            "missing_permissions": missing or "none",
        }

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start with the STT options step."""
        _ = user_input
        return await self.async_step_stt()

    async def async_step_stt(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure speech-to-text options."""
        if user_input is not None:
            self._stt_options = user_input
            return await self.async_step_tts()

        catalog = await self._async_catalog()
        current = {**DEFAULT_OPTIONS, **self.config_entry.options}
        if catalog.stt_models and PERM_MODEL_LISTING not in catalog.missing_permissions:
            model_field = SelectSelector(
                SelectSelectorConfig(
                    options=catalog.stt_models,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            model_field = TextSelector()
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_STT_MODEL,
                    default=_option(current, CONF_STT_MODEL, DEFAULT_STT_MODEL),
                ): model_field,
                vol.Optional(
                    CONF_LANGUAGE_HINTS,
                    default=_option(current, CONF_LANGUAGE_HINTS, []),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=_LANGUAGE_HINT_OPTIONS,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_CONTEXT,
                    default=_option(current, CONF_CONTEXT, ""),
                ): TextSelector(TextSelectorConfig(multiline=True)),
                vol.Optional(
                    CONF_CONTEXT_TERMS,
                    default=_option(current, CONF_CONTEXT_TERMS, ""),
                ): TextSelector(),
                vol.Required(
                    CONF_ENABLE_ENDPOINT_DETECTION,
                    default=_option(
                        current,
                        CONF_ENABLE_ENDPOINT_DETECTION,
                        DEFAULT_ENABLE_ENDPOINT_DETECTION,
                    ),
                ): BooleanSelector(),
                vol.Required(
                    CONF_MAX_ENDPOINT_DELAY_MS,
                    default=_option(
                        current,
                        CONF_MAX_ENDPOINT_DELAY_MS,
                        DEFAULT_MAX_ENDPOINT_DELAY_MS,
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=500,
                        max=3000,
                        step=100,
                        unit_of_measurement="ms",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_ENABLE_DIARIZATION,
                    default=_option(
                        current, CONF_ENABLE_DIARIZATION, DEFAULT_ENABLE_DIARIZATION
                    ),
                ): BooleanSelector(),
                vol.Required(
                    CONF_ENABLE_TRANSLATION,
                    default=_option(
                        current, CONF_ENABLE_TRANSLATION, DEFAULT_ENABLE_TRANSLATION
                    ),
                ): BooleanSelector(),
                vol.Optional(
                    CONF_TRANSLATION_TARGET,
                    default=_option(
                        current, CONF_TRANSLATION_TARGET, DEFAULT_LANGUAGE
                    ),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=_LANGUAGE_HINT_OPTIONS,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="stt",
            data_schema=schema,
            description_placeholders=self._placeholders(catalog),
        )

    async def async_step_tts(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure text-to-speech options and save."""
        if user_input is not None:
            return self.async_create_entry(
                data=_normalize_saved_options({**self._stt_options, **user_input})
            )

        catalog = await self._async_catalog()
        current = {**DEFAULT_OPTIONS, **self.config_entry.options}
        if catalog.tts_models and PERM_MODEL_LISTING not in catalog.missing_permissions:
            model_field = SelectSelector(
                SelectSelectorConfig(
                    options=catalog.tts_models,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            model_field = TextSelector()
        if catalog.voices and PERM_MODEL_LISTING not in catalog.missing_permissions:
            voice_field = SelectSelector(
                SelectSelectorConfig(
                    options=catalog.voices,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            )
        else:
            voice_field = TextSelector()
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_TTS_MODEL,
                    default=_option(current, CONF_TTS_MODEL, DEFAULT_TTS_MODEL),
                ): model_field,
                vol.Required(
                    CONF_TTS_VOICE,
                    default=_option(current, CONF_TTS_VOICE, DEFAULT_TTS_VOICE),
                ): voice_field,
                vol.Required(
                    CONF_TTS_SPEED,
                    default=_option(current, CONF_TTS_SPEED, DEFAULT_TTS_SPEED),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0.7,
                        max=1.3,
                        step=0.05,
                        mode=NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_REDUCE_SILENCE,
                    default=_option(
                        current, CONF_REDUCE_SILENCE, DEFAULT_REDUCE_SILENCE
                    ),
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="tts",
            data_schema=schema,
            description_placeholders=self._placeholders(catalog),
        )
