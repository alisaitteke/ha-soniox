"""Runtime models for the Soniox integration."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from soniox import AsyncSonioxClient

from .const import DOMAIN


@dataclass
class SonioxRuntimeData:
    """Data stored on ConfigEntry.runtime_data."""

    client: AsyncSonioxClient


type SonioxConfigEntry = ConfigEntry[SonioxRuntimeData]


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
