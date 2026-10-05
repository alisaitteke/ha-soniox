"""Tests for the Soniox options flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.selector import SelectSelector, TextSelector
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.soniox.catalog import SonioxCatalog
from custom_components.soniox.const import (
    CONF_CONTEXT,
    CONF_CONTEXT_TERMS,
    CONF_ENABLE_DIARIZATION,
    CONF_ENABLE_ENDPOINT_DETECTION,
    CONF_ENABLE_TRANSLATION,
    CONF_LANGUAGE_HINTS,
    CONF_MAX_ENDPOINT_DELAY_MS,
    CONF_REDUCE_SILENCE,
    CONF_STT_MODEL,
    CONF_TRANSLATION_TARGET,
    CONF_TTS_MODEL,
    CONF_TTS_SPEED,
    CONF_TTS_VOICE,
    DEFAULT_OPTIONS,
    DEFAULT_STT_MODEL,
    DEFAULT_TTS_MODEL,
    DEFAULT_TTS_VOICE,
    SONIOX_CONSOLE_URL,
)

from .conftest import (
    TEST_UNIQUE_ID,
    mock_config_entry_kwargs,
)


def _schema_field(schema: object, key: str) -> object:
    """Return the selector/validator for a voluptuous schema key."""
    for marker, value in schema.schema.items():  # type: ignore[attr-defined]
        if getattr(marker, "schema", marker) == key:
            return value
    raise KeyError(key)


def _catalog_with_lists() -> SonioxCatalog:
    """Return a catalog that can populate dropdowns."""
    return SonioxCatalog(
        stt_models=[{"value": DEFAULT_STT_MODEL, "label": "STT RT v5"}],
        tts_models=[{"value": DEFAULT_TTS_MODEL, "label": "TTS RT v2"}],
        voices=[{"value": DEFAULT_TTS_VOICE, "label": "Adrian — warm"}],
        missing_permissions=[],
    )


def _stt_input(**overrides: object) -> dict[str, object]:
    """Return a valid STT step payload."""
    payload: dict[str, object] = {
        CONF_STT_MODEL: DEFAULT_STT_MODEL,
        CONF_LANGUAGE_HINTS: ["tr"],
        CONF_CONTEXT: "kitchen names",
        CONF_CONTEXT_TERMS: "Soniox, Assist",
        CONF_ENABLE_ENDPOINT_DETECTION: True,
        CONF_MAX_ENDPOINT_DELAY_MS: 1500,
        CONF_ENABLE_DIARIZATION: True,
        CONF_ENABLE_TRANSLATION: True,
        CONF_TRANSLATION_TARGET: "en",
    }
    payload.update(overrides)
    return payload


def _tts_input(**overrides: object) -> dict[str, object]:
    """Return a valid TTS step payload."""
    payload: dict[str, object] = {
        CONF_TTS_MODEL: DEFAULT_TTS_MODEL,
        CONF_TTS_VOICE: "Riley",
        CONF_TTS_SPEED: 1.15,
        CONF_REDUCE_SILENCE: True,
    }
    payload.update(overrides)
    return payload


async def test_options_flow_dropdowns_from_catalog(hass: HomeAssistant) -> None:
    """A permitted catalog becomes STT/TTS dropdowns and is saved."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": TEST_UNIQUE_ID,
        }
    )
    entry.add_to_hass(hass)
    catalog = _catalog_with_lists()

    with patch(
        "custom_components.soniox.config_flow.async_load_catalog",
        return_value=catalog,
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "stt"
        assert result["description_placeholders"]["console_url"] == SONIOX_CONSOLE_URL
        stt_model = _schema_field(result["data_schema"], CONF_STT_MODEL)
        assert isinstance(stt_model, SelectSelector)

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input=_stt_input()
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "tts"
        tts_model = _schema_field(result["data_schema"], CONF_TTS_MODEL)
        tts_voice = _schema_field(result["data_schema"], CONF_TTS_VOICE)
        assert isinstance(tts_model, SelectSelector)
        assert isinstance(tts_voice, SelectSelector)

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input=_tts_input()
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_STT_MODEL] == DEFAULT_STT_MODEL
    assert result["data"][CONF_LANGUAGE_HINTS] == ["tr"]
    assert result["data"][CONF_CONTEXT] == "kitchen names"
    assert result["data"][CONF_CONTEXT_TERMS] == "Soniox, Assist"
    assert result["data"][CONF_ENABLE_DIARIZATION] is True
    assert result["data"][CONF_ENABLE_TRANSLATION] is True
    assert result["data"][CONF_TRANSLATION_TARGET] == "en"
    assert result["data"][CONF_MAX_ENDPOINT_DELAY_MS] == 1500
    assert result["data"][CONF_TTS_VOICE] == "Riley"
    assert result["data"][CONF_TTS_SPEED] == 1.15
    assert result["data"][CONF_REDUCE_SILENCE] is True
    await hass.async_block_till_done()


async def test_options_flow_permission_denied_uses_text_fields(
    hass: HomeAssistant,
) -> None:
    """403 / missing Model listing falls back to typed model and voice fields."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": TEST_UNIQUE_ID,
        }
    )
    entry.add_to_hass(hass)
    catalog = SonioxCatalog(missing_permissions=["model_listing"])

    with patch(
        "custom_components.soniox.config_flow.async_load_catalog",
        return_value=catalog,
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "stt"
        assert result["description_placeholders"]["console_url"] == SONIOX_CONSOLE_URL
        placeholders = result["description_placeholders"]
        assert placeholders["missing_permissions"] == "model_listing"
        stt_model = _schema_field(result["data_schema"], CONF_STT_MODEL)
        assert isinstance(stt_model, TextSelector)

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input=_stt_input(stt_model="stt-rt-v4"),
        )
        assert result["step_id"] == "tts"
        tts_model = _schema_field(result["data_schema"], CONF_TTS_MODEL)
        tts_voice = _schema_field(result["data_schema"], CONF_TTS_VOICE)
        assert isinstance(tts_model, TextSelector)
        assert isinstance(tts_voice, TextSelector)
        assert result["description_placeholders"]["console_url"] == SONIOX_CONSOLE_URL

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input=_tts_input(tts_voice="CustomVoice"),
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_STT_MODEL] == "stt-rt-v4"
    assert result["data"][CONF_TTS_VOICE] == "CustomVoice"
    await hass.async_block_till_done()


async def test_options_flow_keeps_default_options(hass: HomeAssistant) -> None:
    """Submitting the shown defaults preserves DEFAULT_OPTIONS keys."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": TEST_UNIQUE_ID,
        }
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.soniox.config_flow.async_load_catalog",
        return_value=_catalog_with_lists(),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_STT_MODEL: DEFAULT_OPTIONS[CONF_STT_MODEL],
                CONF_LANGUAGE_HINTS: DEFAULT_OPTIONS[CONF_LANGUAGE_HINTS],
                CONF_CONTEXT: DEFAULT_OPTIONS[CONF_CONTEXT],
                CONF_CONTEXT_TERMS: DEFAULT_OPTIONS[CONF_CONTEXT_TERMS],
                CONF_ENABLE_ENDPOINT_DETECTION: DEFAULT_OPTIONS[
                    CONF_ENABLE_ENDPOINT_DETECTION
                ],
                CONF_MAX_ENDPOINT_DELAY_MS: DEFAULT_OPTIONS[CONF_MAX_ENDPOINT_DELAY_MS],
                CONF_ENABLE_DIARIZATION: DEFAULT_OPTIONS[CONF_ENABLE_DIARIZATION],
                CONF_ENABLE_TRANSLATION: DEFAULT_OPTIONS[CONF_ENABLE_TRANSLATION],
                CONF_TRANSLATION_TARGET: DEFAULT_OPTIONS[CONF_TRANSLATION_TARGET],
            },
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_TTS_MODEL: DEFAULT_OPTIONS[CONF_TTS_MODEL],
                CONF_TTS_VOICE: DEFAULT_OPTIONS[CONF_TTS_VOICE],
                CONF_TTS_SPEED: DEFAULT_OPTIONS[CONF_TTS_SPEED],
                CONF_REDUCE_SILENCE: DEFAULT_OPTIONS[CONF_REDUCE_SILENCE],
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_STT_MODEL] == DEFAULT_STT_MODEL
    assert result["data"][CONF_TTS_MODEL] == DEFAULT_TTS_MODEL
    assert result["data"][CONF_TTS_VOICE] == DEFAULT_TTS_VOICE
    await hass.async_block_till_done()
