"""Runtime models for the Soniox integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from soniox import AsyncSonioxClient

from .const import DOMAIN

if TYPE_CHECKING:
    from .catalog import SonioxCatalog


@dataclass
class SonioxRuntimeData:
    """Data stored on ConfigEntry.runtime_data."""

    client: AsyncSonioxClient
    # Cached so a reload does not re-query models, voices and cloned voices.
    catalog: SonioxCatalog | None = field(default=None)


type SonioxConfigEntry = ConfigEntry[SonioxRuntimeData]


def model_supports_max_endpoint_delay(
    model_id: str, entry: SonioxConfigEntry
) -> bool:
    """Return True when the cached catalog says the model accepts the option."""
    catalog: SonioxCatalog | None = getattr(entry.runtime_data, "catalog", None)
    if catalog is None:
        return True
    allowed: bool = catalog.allows_max_endpoint_delay(model_id)
    return allowed


def soniox_device_info(entry_id: str) -> DeviceInfo:
    """Return the shared service device for STT and TTS entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        manufacturer="Soniox",
        name="Soniox",
        entry_type=DeviceEntryType.SERVICE,
    )


def language_to_iso639(language: str) -> str:
    """Map a Home Assistant BCP-47 tag (tr-TR) to an ISO 639-1 code (tr)."""
    return language.split("-", 1)[0].lower()
