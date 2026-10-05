"""Tests for the Soniox config flow."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from soniox.errors import (
    SonioxAPIError,
    SonioxAuthenticationError,
    SonioxPermissionDeniedError,
    SonioxServerError,
)
from soniox.types import ApiError

from custom_components.soniox.catalog import SonioxCatalog
from custom_components.soniox.const import (
    CONF_REGION,
    DEFAULT_OPTIONS,
    DEFAULT_STT_MODEL,
    DEFAULT_TTS_MODEL,
    DOMAIN,
    SONIOX_CONSOLE_URL,
)

from .conftest import (
    TEST_API_KEY,
    TEST_REGION,
    TEST_UNIQUE_ID,
    mock_config_entry_kwargs,
)


async def test_user_form_creates_entry(
    hass: HomeAssistant, mock_validate_credentials: AsyncMock
) -> None:
    """A valid API key creates a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["description_placeholders"]["console_url"] == SONIOX_CONSOLE_URL

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_API_KEY: TEST_API_KEY, CONF_REGION: TEST_REGION},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Soniox"
    assert result["data"] == {CONF_API_KEY: TEST_API_KEY, CONF_REGION: TEST_REGION}
    assert result["options"] == DEFAULT_OPTIONS
    # The unique id is random, so it cannot leak or depend on the API key.
    unique_id = result["result"].unique_id
    assert unique_id and TEST_API_KEY not in unique_id
    assert len(unique_id) == 32
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
    await hass.async_block_till_done()


async def test_same_api_key_cannot_be_added_twice(
    hass: HomeAssistant, mock_validate_credentials: AsyncMock
) -> None:
    """The same API key cannot be configured twice.

    The unique id is random, so the duplicate check matches on the stored key
    instead. Key rotation stays possible through reauthentication.
    """
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": TEST_UNIQUE_ID,
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


async def test_reauth_accepts_a_rotated_api_key(
    hass: HomeAssistant, mock_validate_credentials: AsyncMock
) -> None:
    """A key the user rotated in the console must be accepted.

    The unique id used to be a hash of the API key, so a rotation aborted the
    flow with wrong_account and locked the user out of reauthentication.
    """
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": TEST_UNIQUE_ID,
        }
    )
    entry.add_to_hass(hass)
    rotated = "sk_rotated_replacement_key"

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
        data=entry.data,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: rotated}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == rotated
    # The unique id must survive so the entry keeps its identity.
    assert entry.unique_id == TEST_UNIQUE_ID
    # The update reloads the entry; let the reload finish before teardown.
    await hass.async_block_till_done()


async def test_reconfigure_accepts_a_rotated_api_key(
    hass: HomeAssistant, mock_validate_credentials: AsyncMock
) -> None:
    """Reconfigure must also accept a different key than the stored one."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": TEST_UNIQUE_ID,
        }
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_API_KEY: "sk_another_key", CONF_REGION: "eu"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_API_KEY] == "sk_another_key"
    assert entry.data[CONF_REGION] == "eu"
    # The update reloads the entry; let the reload finish before teardown.
    await hass.async_block_till_done()


def _api_error(status_code: int, error_type: str, message: str) -> ApiError:
    """Build the SDK's structured error payload for a failed response."""
    return ApiError(
        status_code=status_code,
        error_type=error_type,
        message=message,
        request_id=f"req-{error_type}",
    )


def _permission_denied() -> SonioxPermissionDeniedError:
    """Build the SDK error a valid-but-restricted key produces (HTTP 403)."""
    api_error = _api_error(
        403, "permission_denied", "The API key does not have permission."
    )
    response = httpx.Response(403, json=api_error.model_dump())
    return SonioxPermissionDeniedError(
        "permission denied", api_error=api_error, response=response
    )


def _quota_error() -> SonioxAPIError:
    """Build the SDK error for an exhausted balance (HTTP 429)."""
    api_error = _api_error(
        429, "organization_balance_exhausted", "Organization balance exhausted."
    )
    response = httpx.Response(429, json=api_error.model_dump())
    return SonioxAPIError("balance exhausted", api_error=api_error, response=response)


async def test_permission_denied_is_not_an_invalid_key(
    hass: HomeAssistant, mock_validate_credentials: AsyncMock
) -> None:
    """A 403 permission_denied means the key is valid, so setup must proceed."""
    mock_validate_credentials.side_effect = _permission_denied()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_API_KEY: TEST_API_KEY, CONF_REGION: TEST_REGION},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_quota_exhausted_shows_its_own_error(
    hass: HomeAssistant, mock_validate_credentials: AsyncMock
) -> None:
    """An exhausted balance is reported as a quota problem, not a connection one."""
    mock_validate_credentials.side_effect = _quota_error()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_API_KEY: TEST_API_KEY, CONF_REGION: TEST_REGION},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "quota_exhausted"}


async def test_reauth_updates_api_key(
    hass: HomeAssistant, mock_validate_credentials: AsyncMock
) -> None:
    """Reauth updates the stored API key when it still maps to the same unique id."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": TEST_UNIQUE_ID,
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
    await hass.async_block_till_done()


async def test_reauth_invalid_auth_recovers(
    hass: HomeAssistant, mock_validate_credentials: AsyncMock
) -> None:
    """Reauth can recover after an invalid key."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": TEST_UNIQUE_ID,
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
    await hass.async_block_till_done()


async def test_reconfigure_updates_region(
    hass: HomeAssistant, mock_validate_credentials: AsyncMock
) -> None:
    """Reconfigure can change the region for the same API key."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": TEST_UNIQUE_ID,
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
    await hass.async_block_till_done()


async def test_options_flow_starts_at_stt(hass: HomeAssistant) -> None:
    """Configure opens the STT options step."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": TEST_UNIQUE_ID,
        }
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.soniox.config_flow.async_load_catalog",
        return_value=SonioxCatalog(),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "stt"
    assert result["description_placeholders"]["console_url"] == SONIOX_CONSOLE_URL
