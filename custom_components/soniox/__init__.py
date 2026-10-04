"""The Soniox STT/TTS integration."""

from __future__ import annotations

import logging

import httpx
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from soniox.errors import SonioxAuthenticationError, SonioxError

from .client import async_check_client, create_soniox_client
from .const import CONF_REGION, DOMAIN
from .models import SonioxConfigEntry, SonioxRuntimeData

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Soniox integration (config-entry only)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SonioxConfigEntry) -> bool:
    """Set up Soniox from a config entry."""
    client = create_soniox_client(entry.data[CONF_API_KEY], entry.data[CONF_REGION])
    try:
        await async_check_client(client)
    except SonioxAuthenticationError as err:
        await client.aclose()
        raise ConfigEntryAuthFailed("Invalid Soniox API key") from err
    except (httpx.ConnectError, httpx.TimeoutException, SonioxError) as err:
        await client.aclose()
        raise ConfigEntryNotReady("Unable to connect to Soniox") from err

    entry.runtime_data = SonioxRuntimeData(client=client)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SonioxConfigEntry) -> bool:
    """Unload a config entry."""
    await entry.runtime_data.client.aclose()
    return True


async def _async_update_listener(hass: HomeAssistant, entry: SonioxConfigEntry) -> None:
    """Reload the entry when options or data change."""
    await hass.config_entries.async_reload(entry.entry_id)
