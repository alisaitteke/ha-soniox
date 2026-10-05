"""Diagnostics for the Soniox integration."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant

from .const import CONF_REGION, REGION_ENDPOINTS
from .models import SonioxConfigEntry

# ``unique_id`` is redacted as well: older entries stored a hash derived from
# the API key, and diagnostics files are routinely attached to public issues.
TO_REDACT = {CONF_API_KEY, "unique_id"}


def _sdk_version() -> str:
    """Return the installed soniox SDK version, or unknown."""
    try:
        return version("soniox")
    except PackageNotFoundError:  # pragma: no cover - SDK is a manifest dep
        return "unknown"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SonioxConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    No request is made to Soniox: diagnostics must stay fast and must work
    without the permissions the API key may or may not have.
    """
    region = entry.data.get(CONF_REGION, "us")
    return {
        "config_entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "region": region,
        "endpoints": REGION_ENDPOINTS.get(region, {}),
        "options": dict(entry.options),
        "versions": {
            "homeassistant": HA_VERSION,
            "soniox": _sdk_version(),
        },
    }
