"""Tests for the Soniox config flow."""

from unittest.mock import AsyncMock

import httpx
import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from soniox.errors import SonioxAuthenticationError, SonioxServerError

from custom_components.soniox.client import unique_id_from_api_key
from custom_components.soniox.const import (
    CONF_REGION,
    DEFAULT_OPTIONS,
    DEFAULT_STT_MODEL,
    DEFAULT_TTS_MODEL,
    DOMAIN,
)

from .conftest import TEST_API_KEY, TEST_REGION, mock_config_entry_kwargs


async def test_user_form_creates_entry(
    hass: HomeAssistant, mock_validate_credentials: AsyncMock
) -> None:
    """A valid API key creates a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_API_KEY: TEST_API_KEY, CONF_REGION: TEST_REGION},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Soniox"
    assert result["data"] == {CONF_API_KEY: TEST_API_KEY, CONF_REGION: TEST_REGION}
    assert result["options"] == DEFAULT_OPTIONS
    assert result["result"].unique_id == unique_id_from_api_key(TEST_API_KEY)
    assert result["options"]["stt_model"] == DEFAULT_STT_MODEL
    assert result["options"]["tts_model"] == DEFAULT_TTS_MODEL
    mock_validate_credentials.assert_awaited_once()


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (SonioxAuthenticationError("bad key"), "invalid_auth"),
        (httpx.ConnectError("boom"), "cannot_connect"),
        (SonioxServerError("unavailable"), "cannot_connect"),
        (RuntimeError("unexpected"), "unknown"),
    ],
)
async def test_user_form_errors(
    hass: HomeAssistant,
    mock_validate_credentials: AsyncMock,
    side_effect: Exception,
    error: str,
) -> None:
    """The user step recovers from validation errors."""
    mock_validate_credentials.side_effect = side_effect
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_API_KEY: TEST_API_KEY, CONF_REGION: TEST_REGION},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_validate_credentials.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_API_KEY: TEST_API_KEY, CONF_REGION: "eu"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_REGION] == "eu"


async def test_unique_id_prevents_duplicate(
    hass: HomeAssistant, mock_validate_credentials: AsyncMock
) -> None:
    """The same API key cannot be configured twice."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": unique_id_from_api_key(TEST_API_KEY),
        }
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_API_KEY: TEST_API_KEY, CONF_REGION: TEST_REGION},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_api_key(
    hass: HomeAssistant, mock_validate_credentials: AsyncMock
) -> None:
    """Reauth updates the stored API key when it still maps to the same unique id."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": unique_id_from_api_key(TEST_API_KEY),
        }
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_API_KEY: TEST_API_KEY},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_reauth_invalid_auth_recovers(
    hass: HomeAssistant, mock_validate_credentials: AsyncMock
) -> None:
    """Reauth can recover after an invalid key."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": unique_id_from_api_key(TEST_API_KEY),
        }
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    mock_validate_credentials.side_effect = SonioxAuthenticationError("bad")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_API_KEY: "wrong"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    mock_validate_credentials.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_API_KEY: TEST_API_KEY},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_reconfigure_updates_region(
    hass: HomeAssistant, mock_validate_credentials: AsyncMock
) -> None:
    """Reconfigure can change the region for the same API key."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": unique_id_from_api_key(TEST_API_KEY),
        }
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_API_KEY: TEST_API_KEY, CONF_REGION: "eu"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_REGION] == "eu"


async def test_options_flow_keeps_defaults(hass: HomeAssistant) -> None:
    """The options skeleton stores the existing defaults."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": unique_id_from_api_key(TEST_API_KEY),
        }
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["stt_model"] == DEFAULT_STT_MODEL
