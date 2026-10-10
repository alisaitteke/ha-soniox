"""Thin wrapper around the official Soniox async SDK."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from soniox import AsyncSonioxClient

from .const import (
    DEFAULT_REGION,
    REGION_ENDPOINTS,
    REQUEST_TIMEOUT_SEC,
    VALIDATION_TIMEOUT_SEC,
)


def new_unique_id() -> str:
    """Return a random unique id for a config entry.

    The unique id must not be derived from the API key: users rotate keys in
    the Soniox console, and a key-derived id would make reauthentication and
    reconfiguration abort with ``wrong_account`` for a legitimate new key.
    """
    return uuid4().hex


def create_soniox_client(
    api_key: str, region: str = DEFAULT_REGION, **client_kwargs: Any
) -> AsyncSonioxClient:
    """Create an AsyncSonioxClient for the given region.

    The official SDK builds its own httpx.AsyncClient and does not accept
    Home Assistant's shared websession. Extra keyword arguments are forwarded
    to the SDK so callers can inject proxy and TLS settings.
    """
    endpoints = REGION_ENDPOINTS.get(region, REGION_ENDPOINTS[DEFAULT_REGION])
    # Callers may pass timeout_sec (validation uses a shorter one); only fill
    # in the default when they did not, otherwise the SDK receives it twice.
    client_kwargs.setdefault("timeout_sec", REQUEST_TIMEOUT_SEC)
    return AsyncSonioxClient(api_key=api_key, **endpoints, **client_kwargs)


async def async_check_client(client: AsyncSonioxClient) -> None:
    """Cheap authenticated call used to validate credentials."""
    await client.models.list()


async def async_validate_api_credentials(api_key: str, region: str) -> None:
    """Validate an API key, then close the temporary client."""
    client = create_soniox_client(
        api_key, region, timeout_sec=VALIDATION_TIMEOUT_SEC
    )
    try:
        await async_check_client(client)
    finally:
        await client.aclose()
