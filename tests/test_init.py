"""Tests for Soniox config entry setup and unload."""

from unittest.mock import AsyncMock, patch

import httpx
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry
from soniox.errors import (
    SonioxAPIError,
    SonioxAuthenticationError,
    SonioxPermissionDeniedError,
    SonioxServerError,
)
from soniox.types import ApiError

from custom_components.soniox import async_setup
from custom_components.soniox.const import DOMAIN

from .conftest import (
    TEST_UNIQUE_ID,
    empty_catalog_client,
    mock_config_entry_kwargs,
)


def _mock_client():
    return empty_catalog_client()


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


async def test_setup_and_unload_entry(hass: HomeAssistant) -> None:
    """The entry stores runtime data and closes the client on unload."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": TEST_UNIQUE_ID,
        }
    )
    entry.add_to_hass(hass)
    client = _mock_client()

    with (
        patch("custom_components.soniox.create_soniox_client", return_value=client),
        patch("custom_components.soniox.async_check_client", new_callable=AsyncMock),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.client is client
    registry = er.async_get(hass)
    domains = {
        item.domain
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert domains == {"stt", "tts"}

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    client.aclose.assert_awaited()


async def test_setup_auth_failed(hass: HomeAssistant) -> None:
    """Invalid credentials mark the entry as auth failed."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": TEST_UNIQUE_ID,
        }
    )
    entry.add_to_hass(hass)
    client = _mock_client()

    with (
        patch("custom_components.soniox.create_soniox_client", return_value=client),
        patch(
            "custom_components.soniox.async_check_client",
            new_callable=AsyncMock,
            side_effect=SonioxAuthenticationError("invalid"),
        ),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    client.aclose.assert_awaited()


async def test_setup_not_ready(hass: HomeAssistant) -> None:
    """Connection errors mark the entry as not ready."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": TEST_UNIQUE_ID,
        }
    )
    entry.add_to_hass(hass)
    client = _mock_client()

    with (
        patch("custom_components.soniox.create_soniox_client", return_value=client),
        patch(
            "custom_components.soniox.async_check_client",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("offline"),
        ),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    client.aclose.assert_awaited()


async def test_setup_not_ready_on_server_error(hass: HomeAssistant) -> None:
    """Soniox API errors during setup are treated as not ready."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": TEST_UNIQUE_ID,
        }
    )
    entry.add_to_hass(hass)
    client = _mock_client()

    with (
        patch("custom_components.soniox.create_soniox_client", return_value=client),
        patch(
            "custom_components.soniox.async_check_client",
            new_callable=AsyncMock,
            side_effect=SonioxServerError("500"),
        ),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_permission_denied_does_not_start_reauth(hass: HomeAssistant) -> None:
    """A 403 permission_denied must not be treated as an invalid key.

    SonioxPermissionDeniedError is a sibling of SonioxAuthenticationError, so
    catching the wrong class silently turns "grant a permission" into "enter a
    new API key", which cannot fix anything.
    """
    entry = MockConfigEntry(
        **{**mock_config_entry_kwargs(), "unique_id": TEST_UNIQUE_ID}
    )
    entry.add_to_hass(hass)
    client = _mock_client()

    with (
        patch("custom_components.soniox.create_soniox_client", return_value=client),
        patch(
            "custom_components.soniox.async_check_client",
            new_callable=AsyncMock,
            side_effect=_permission_denied(),
        ),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    client.aclose.assert_awaited()
    # The user is told what is actually wrong instead of being asked for a key.
    issues = ir.async_get(hass).issues
    assert (DOMAIN, "permission_denied") in issues


async def test_quota_exhausted_keeps_entry_and_creates_issue(
    hass: HomeAssistant,
) -> None:
    """An exhausted balance must not put the entry in a retry loop."""
    entry = MockConfigEntry(
        **{**mock_config_entry_kwargs(), "unique_id": TEST_UNIQUE_ID}
    )
    entry.add_to_hass(hass)
    client = _mock_client()

    with (
        patch("custom_components.soniox.create_soniox_client", return_value=client),
        patch(
            "custom_components.soniox.async_check_client",
            new_callable=AsyncMock,
            side_effect=_quota_error(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    # The client must stay open for the platforms.
    client.aclose.assert_not_awaited()
    issues = ir.async_get(hass).issues
    assert (DOMAIN, "quota_exhausted") in issues

    # Unloading closes the client and clears the repair issues.
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    client.aclose.assert_awaited()
    assert (DOMAIN, "quota_exhausted") not in ir.async_get(hass).issues


async def test_async_setup_returns_true(hass: HomeAssistant) -> None:
    """YAML-less component setup succeeds."""
    assert await async_setup(hass, {DOMAIN: {}})
