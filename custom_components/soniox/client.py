"""Thin wrapper around the official Soniox async SDK."""

from __future__ import annotations

import hashlib

from soniox import AsyncSonioxClient

from .const import DEFAULT_REGION, REGION_ENDPOINTS


def unique_id_from_api_key(api_key: str) -> str:
    """Return a stable unique id that does not contain the raw API key."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def create_soniox_client(
    api_key: str, region: str = DEFAULT_REGION
) -> AsyncSonioxClient:
    """Create an AsyncSonioxClient for the given region.

    The official SDK builds its own httpx.AsyncClient and does not accept
    Home Assistant's shared websession.
    """
    endpoints = REGION_ENDPOINTS[region]
    return AsyncSonioxClient(api_key=api_key, **endpoints)


async def async_check_client(client: AsyncSonioxClient) -> None:
    """Cheap authenticated call used to validate credentials."""
    await client.models.list()


async def async_validate_api_credentials(api_key: str, region: str) -> None:
    """Validate an API key, then close the temporary client."""
    client = create_soniox_client(api_key, region)
    try:
        await async_check_client(client)
    finally:
        await client.aclose()
