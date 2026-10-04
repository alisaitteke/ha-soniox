"""Shared fixtures for Soniox tests."""

from collections.abc import Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_API_KEY

from tests.soniox_stubs import install_soniox_stubs_if_needed

install_soniox_stubs_if_needed()

from custom_components.soniox.const import (  # noqa: E402, PLC0415
    CONF_REGION,
    DEFAULT_OPTIONS,
    DOMAIN,
)

pytest_plugins = "pytest_homeassistant_custom_component"

TEST_API_KEY = "sk_test_soniox_key"
TEST_REGION = "us"


def empty_catalog_client() -> MagicMock:
    """Return a client whose catalog list methods yield empty results."""
    client = MagicMock()
    client.aclose = AsyncMock()
    client.models.list = AsyncMock(return_value=SimpleNamespace(models=[]))
    client.tts_models.list = AsyncMock(return_value=SimpleNamespace(models=[]))
    client.voices.list = AsyncMock(return_value=SimpleNamespace(voices=[]))
    return client


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Enable loading custom_components in every test."""
    yield


@pytest.fixture(autouse=True)
def mock_soniox_setup_client() -> Generator[MagicMock]:
    """Prevent setup from opening a real Soniox client."""
    client = empty_catalog_client()
    with (
        patch("custom_components.soniox.create_soniox_client", return_value=client),
        patch("custom_components.soniox.async_check_client", new_callable=AsyncMock),
    ):
        yield client


@pytest.fixture
def mock_validate_credentials() -> Generator[AsyncMock]:
    """Bypass live Soniox API validation in config flow tests."""
    with patch(
        "custom_components.soniox.config_flow.async_validate_api_credentials",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


def mock_config_entry_data() -> dict[str, str]:
    """Return typical config entry data."""
    return {CONF_API_KEY: TEST_API_KEY, CONF_REGION: TEST_REGION}


def mock_config_entry_kwargs() -> dict[str, object]:
    """Return kwargs for MockConfigEntry."""
    return {
        "domain": DOMAIN,
        "title": "Soniox",
        "data": mock_config_entry_data(),
        "options": dict(DEFAULT_OPTIONS),
        "unique_id": None,
    }
