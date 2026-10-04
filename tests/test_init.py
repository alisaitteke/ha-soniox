"""Tests for Soniox config entry setup and unload."""

from unittest.mock import AsyncMock, patch

import httpx
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from soniox.errors import SonioxAuthenticationError, SonioxServerError

from custom_components.soniox import async_setup
from custom_components.soniox.client import unique_id_from_api_key
from custom_components.soniox.const import DOMAIN

from .conftest import TEST_API_KEY, empty_catalog_client, mock_config_entry_kwargs


def _mock_client():
    return empty_catalog_client()


async def test_setup_and_unload_entry(hass: HomeAssistant) -> None:
    """The entry stores runtime data and closes the client on unload."""
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": unique_id_from_api_key(TEST_API_KEY),
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
            "unique_id": unique_id_from_api_key(TEST_API_KEY),
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
            "unique_id": unique_id_from_api_key(TEST_API_KEY),
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
            "unique_id": unique_id_from_api_key(TEST_API_KEY),
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


async def test_async_setup_returns_true(hass: HomeAssistant) -> None:
    """YAML-less component setup succeeds."""
    assert await async_setup(hass, {DOMAIN: {}})
