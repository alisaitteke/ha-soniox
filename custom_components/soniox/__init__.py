"""The Soniox STT/TTS integration."""

from __future__ import annotations

import logging
import sys

import httpx
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType
from soniox.errors import SonioxAuthenticationError, SonioxError

from .client import async_check_client, create_soniox_client
from .const import (
    CONF_REGION,
    CONF_STT_MODEL,
    CONF_TTS_MODEL,
    DEFAULT_STT_MODEL,
    DEFAULT_TTS_MODEL,
    DOMAIN,
    ISSUE_PYTHON_REGRESSION,
)
from .exceptions import (
    is_permission_denied,
    is_quota_exhausted,
    log_error,
    soniox_error_type,
    soniox_request_id,
)
from .models import SonioxConfigEntry, SonioxRuntimeData
from .repairs import (
    async_create_permission_issue,
    async_create_quota_issue,
    async_delete_all_issues,
    async_delete_permission_issue,
    async_delete_quota_issue,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [Platform.STT, Platform.TTS]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Soniox integration (config-entry only)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SonioxConfigEntry) -> bool:
    """Set up Soniox from a config entry."""
    _async_warn_on_broken_python(hass, entry)
    region = entry.data[CONF_REGION]
    _LOGGER.debug(
        "Setting up Soniox entry %s (region=%s)", entry.entry_id, region
    )

    client = create_soniox_client(entry.data[CONF_API_KEY], region)
    keep_entry = False
    # Close the probe client only when setup will not keep it. Success and
    # quota-exhausted both store this same client on runtime_data, so closing
    # whenever keep_entry is False also kills the working path.
    close_client = True
    try:
        await async_check_client(client)
        close_client = False
    except SonioxError as err:
        # SonioxPermissionDeniedError is a sibling of SonioxAuthenticationError
        # and both use HTTP 403, so the branches are checked by error_type
        # rather than by exception class. Only a real auth failure may start
        # reauthentication; a missing permission must not ask the user for a
        # key that already works.
        if is_permission_denied(err):
            log_error(
                _LOGGER,
                "Soniox API key lacks a required permission; "
                "grant it in the Soniox console",
                err,
                region=region,
            )
            await async_create_permission_issue(hass, entry, err)
            raise ConfigEntryNotReady(
                f"Soniox API key lacks a required permission "
                f"(error_type={soniox_error_type(err)}, "
                f"request_id={soniox_request_id(err)})"
            ) from err
        if is_quota_exhausted(err):
            # Balance and budget rejections are not transient. Keep the entry
            # loaded so the user keeps their configuration, and explain the
            # cause with a repair issue rather than an endless retry loop.
            log_error(
                _LOGGER,
                "Soniox quota exhausted; the integration stays loaded so the "
                "configuration is preserved",
                err,
                region=region,
            )
            await async_create_quota_issue(hass, entry, err)
            keep_entry = True
            close_client = False
        elif isinstance(err, SonioxAuthenticationError):
            log_error(
                _LOGGER,
                "Soniox rejected the API key; reauthentication required",
                err,
                region=region,
            )
            raise ConfigEntryAuthFailed("Invalid Soniox API key") from err
        else:
            log_error(
                _LOGGER,
                "Could not reach Soniox while validating credentials",
                err,
                exc_info=True,
                region=region,
            )
            raise ConfigEntryNotReady(
                f"Unable to connect to Soniox "
                f"(error_type={soniox_error_type(err) or 'network_error'}, "
                f"request_id={soniox_request_id(err) or 'none'})"
            ) from err
    except (httpx.ConnectError, httpx.TimeoutException) as err:
        log_error(
            _LOGGER,
            "Network error while validating Soniox credentials",
            err,
            region=region,
        )
        raise ConfigEntryNotReady("Unable to connect to Soniox") from err
    finally:
        if close_client:
            await client.aclose()

    # Clear stale issues only once the credential check truly succeeded. Doing
    # this unconditionally would erase the quota issue created just above.
    if not keep_entry:
        await async_delete_quota_issue(hass, entry.entry_id)
        await async_delete_permission_issue(hass, entry.entry_id)

    # The credential check passed (or only the quota is exhausted), so the
    # client stays open for the platforms.
    entry.runtime_data = SonioxRuntimeData(client=client)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    stt_model = entry.options.get(CONF_STT_MODEL, DEFAULT_STT_MODEL)
    tts_model = entry.options.get(CONF_TTS_MODEL, DEFAULT_TTS_MODEL)
    if keep_entry:
        _LOGGER.warning(
            "Soniox entry %s loaded but requests will fail until the quota is "
            "restored (region=%s, stt_model=%s, tts_model=%s)",
            entry.entry_id,
            region,
            stt_model,
            tts_model,
        )
    else:
        _LOGGER.info(
            "Soniox entry %s ready (region=%s, stt_model=%s, tts_model=%s)",
            entry.entry_id,
            region,
            stt_model,
            tts_model,
        )
    return True


def _async_warn_on_broken_python(
    hass: HomeAssistant, entry: SonioxConfigEntry
) -> None:
    """Warn when the running Python breaks Soniox realtime WebSockets.

    CPython 3.13.6 ships an ssl regression (CPython/gh-137583) that makes the
    realtime STT/TTS WebSocket handshakes hang with no error, so the failure
    looks like "Soniox does not work". Raising a repair issue names the cause.
    """
    if sys.version_info[:3] == (3, 13, 6):
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_PYTHON_REGRESSION,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_PYTHON_REGRESSION,
            translation_placeholders={"python_version": "3.13.6"},
        )


async def async_unload_entry(hass: HomeAssistant, entry: SonioxConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.aclose()
        await async_delete_all_issues(hass, entry.entry_id)
        _LOGGER.debug("Unloaded Soniox entry %s", entry.entry_id)
    else:
        _LOGGER.warning(
            "Soniox entry %s did not unload cleanly; keeping repair issues",
            entry.entry_id,
        )
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: SonioxConfigEntry) -> None:
    """Reload the entry when options or data change."""
    await hass.config_entries.async_reload(entry.entry_id)
