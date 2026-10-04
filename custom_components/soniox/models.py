"""Runtime models for the Soniox integration."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from soniox import AsyncSonioxClient


@dataclass
class SonioxRuntimeData:
    """Data stored on ConfigEntry.runtime_data."""

    client: AsyncSonioxClient


type SonioxConfigEntry = ConfigEntry[SonioxRuntimeData]
