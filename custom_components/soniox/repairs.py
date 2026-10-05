"""Repair issues for Soniox problems that retrying cannot fix."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, ISSUE_PERMISSION_DENIED, ISSUE_QUOTA_EXHAUSTED
from .exceptions import soniox_error_type, soniox_request_id
from .models import SonioxConfigEntry

_LOGGER = logging.getLogger(__name__)


def _placeholders(err: BaseException) -> dict[str, str]:
    """Return translation placeholders, including the Soniox request id."""
    return {
        "error_type": soniox_error_type(err) or "unknown_error",
        "request_id": soniox_request_id(err) or "unknown",
    }


async def async_create_quota_issue(
    hass: HomeAssistant, entry: SonioxConfigEntry, err: BaseException
) -> None:
    """Tell the user their Soniox balance or budget blocks requests.

    Soniox rejects these with HTTP 429. Retrying forever hides the cause, so
    the entry stays loaded and a repair issue explains what to do.
    """
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_QUOTA_EXHAUSTED,
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_QUOTA_EXHAUSTED,
        translation_placeholders=_placeholders(err),
        data={"entry_id": entry.entry_id},
    )


async def async_delete_quota_issue(hass: HomeAssistant, entry_id: str) -> None:
    """Remove the quota repair issue once requests succeed again."""
    ir.async_delete_issue(hass, DOMAIN, ISSUE_QUOTA_EXHAUSTED)


async def async_create_permission_issue(
    hass: HomeAssistant, entry: SonioxConfigEntry, err: BaseException
) -> None:
    """Tell the user the key is valid but missing an API permission.

    Soniox returns 403 for a valid key without the required permission. That
    is not an auth failure, so it must not trigger reauthentication.
    """
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_PERMISSION_DENIED,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_PERMISSION_DENIED,
        translation_placeholders=_placeholders(err),
        data={"entry_id": entry.entry_id},
    )


async def async_delete_permission_issue(hass: HomeAssistant, entry_id: str) -> None:
    """Remove the permission repair issue once the key can do the work."""
    ir.async_delete_issue(hass, DOMAIN, ISSUE_PERMISSION_DENIED)


async def async_delete_all_issues(hass: HomeAssistant, entry_id: str) -> None:
    """Clear every Soniox repair issue for an entry on unload."""
    await async_delete_quota_issue(hass, entry_id)
    await async_delete_permission_issue(hass, entry_id)