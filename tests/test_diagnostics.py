"""Tests for Soniox diagnostics and operational logging."""

import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from soniox.errors import SonioxAPIError, SonioxPermissionDeniedError
from soniox.types import ApiError

from custom_components.soniox.const import (
    DEFAULT_STT_MODEL,
    DEFAULT_TTS_MODEL,
)
from custom_components.soniox.diagnostics import async_get_config_entry_diagnostics
from custom_components.soniox.exceptions import describe_error, log_error

from .conftest import (
    TEST_API_KEY,
    TEST_UNIQUE_ID,
    empty_catalog_client,
    mock_config_entry_kwargs,
)


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


async def test_diagnostics_redacts_the_api_key_and_unique_id(
    hass: HomeAssistant,
) -> None:
    """No secret or key-derived identifier may appear in a diagnostics file.

    Diagnostics files are routinely attached to public issues, so both the API
    key and the unique id must be redacted.
    """
    entry = MockConfigEntry(
        **{
            **mock_config_entry_kwargs(),
            "unique_id": "deadbeefdeadbeefdeadbeefdeadbeef",
        }
    )
    entry.add_to_hass(hass)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    entry_dump = diagnostics["config_entry"]

    assert entry_dump["data"][CONF_API_KEY] != TEST_API_KEY
    assert entry_dump["unique_id"] != "deadbeefdeadbeefdeadbeefdeadbeef"
    assert TEST_API_KEY not in str(diagnostics)


async def test_setup_logs_region_and_models_on_success(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """A successful setup logs the configuration a user needs to verify it."""
    entry = MockConfigEntry(
        **{**mock_config_entry_kwargs(), "unique_id": TEST_UNIQUE_ID}
    )
    entry.add_to_hass(hass)
    with caplog.at_level(logging.INFO, logger="custom_components.soniox"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    messages = [record.getMessage() for record in caplog.records]
    ready = [msg for msg in messages if "ready" in msg]
    assert ready, f"no setup confirmation logged: {messages}"
    assert "region=us" in ready[0]
    assert DEFAULT_STT_MODEL in ready[0]
    assert DEFAULT_TTS_MODEL in ready[0]


async def test_permission_denied_logs_request_id(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Errors must carry the Soniox request_id so support can trace them."""
    entry = MockConfigEntry(
        **{**mock_config_entry_kwargs(), "unique_id": TEST_UNIQUE_ID}
    )
    entry.add_to_hass(hass)
    client = empty_catalog_client()

    with (
        caplog.at_level(logging.ERROR, logger="custom_components.soniox"),
        patch("custom_components.soniox.create_soniox_client", return_value=client),
        patch(
            "custom_components.soniox.async_check_client",
            new_callable=AsyncMock,
            side_effect=_permission_denied(),
        ),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, "permission failure was not logged"
    joined = " ".join(errors)
    assert "permission_denied" in joined
    assert "req-permission_denied" in joined
    assert "HTTP 403" in joined
    assert "region=us" in joined
    # The API key must never reach the log.
    assert TEST_API_KEY not in joined


async def test_quota_logs_warning_and_keeps_entry(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Quota exhaustion is logged and reported without retrying forever."""
    entry = MockConfigEntry(
        **{**mock_config_entry_kwargs(), "unique_id": TEST_UNIQUE_ID}
    )
    entry.add_to_hass(hass)
    client = empty_catalog_client()

    with (
        caplog.at_level(logging.WARNING, logger="custom_components.soniox"),
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
    messages = [r.getMessage() for r in caplog.records]
    joined = " ".join(messages)
    assert "quota exhausted" in joined
    assert "organization_balance_exhausted" in joined
    assert "req-organization_balance_exhausted" in joined
    # A warning makes clear the entry is loaded but not usable yet.
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("will fail until the quota is restored" in w for w in warnings)
    assert TEST_API_KEY not in joined


def test_log_error_never_leaks_the_api_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No code path may write the API key to the log."""
    logger = logging.getLogger("custom_components.soniox.test")
    api_error = _api_error(403, "permission_denied", "denied for sk_do_not_log_me")
    err = SonioxPermissionDeniedError(
        "denied", api_error=api_error, response=httpx.Response(403)
    )
    with caplog.at_level(logging.DEBUG, logger="custom_components.soniox.test"):
        log_error(logger, "Something failed", err, region="us")

    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "sk_do_not_log_me" not in joined
    assert TEST_API_KEY not in joined
    # The useful parts are present.
    assert "permission_denied" in joined
    assert "HTTP 403" in joined
    assert "req-permission_denied" in joined


def test_log_error_traceback_is_the_real_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """exc_info must point at the exception, not resolve to NoneType.

    Passing exc_info=True while no exception is active prints a useless
    "NoneType: None" traceback, which hides the real cause.
    """
    logger = logging.getLogger("custom_components.soniox.test")
    err = SonioxAPIError("boom", api_error=_api_error(500, "internal_error", "oops"))
    with caplog.at_level(logging.ERROR, logger="custom_components.soniox.test"):
        log_error(logger, "Failed", err, exc_info=True)

    assert caplog.records
    record = caplog.records[0]
    assert record.exc_info is not None
    assert record.exc_info[0] is SonioxAPIError
    formatted = logging.Formatter().formatException(record.exc_info)
    assert "NoneType: None" not in formatted
    assert "SonioxAPIError" in formatted


def test_describe_error_handles_missing_metadata() -> None:
    """A plain SDK error must still produce a usable description."""
    description = describe_error(SonioxAPIError("plain"))
    assert "SonioxAPIError" in description
    assert "request_id=none" in description


async def test_diagnostics_include_versions_and_endpoints(
    hass: HomeAssistant,
) -> None:
    """Versions and the resolved regional endpoints aid support requests."""
    entry = MockConfigEntry(
        **{**mock_config_entry_kwargs(), "unique_id": TEST_UNIQUE_ID}
    )
    entry.add_to_hass(hass)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["region"] == "us"
    assert diagnostics["endpoints"]["api_base_url"] == "https://api.soniox.com/v1"
    assert diagnostics["versions"]["soniox"] != "unknown"
    assert diagnostics["versions"]["homeassistant"]
    # Diagnostics must not require a live API call or any extra permission.
    assert "options" in diagnostics