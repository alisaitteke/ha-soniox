"""Exceptions and structured logging helpers for the Soniox integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from soniox.errors import SonioxAPIError

from .const import QUOTA_ERROR_TYPES


class SonioxIntegrationError(HomeAssistantError):
    """Base exception for the Soniox integration."""


def soniox_error_type(err: BaseException) -> str | None:
    """Return the stable Soniox ``error_type`` for an exception, if any.

    Soniox documents that ``error_type`` is the machine-readable identifier
    and that the human-readable message may change, so callers must branch on
    this rather than on the message text.
    """
    api_error = getattr(err, "api_error", None)
    error_type = getattr(api_error, "error_type", None)
    return error_type if isinstance(error_type, str) else None


def soniox_request_id(err: BaseException) -> str | None:
    """Return the Soniox ``request_id`` so users can quote it to support."""
    request_id = getattr(err, "request_id", None)
    if request_id is None:
        request_id = getattr(getattr(err, "api_error", None), "request_id", None)
    return request_id if isinstance(request_id, str) else None


def is_permission_denied(err: BaseException) -> bool:
    """Return True when the API key is valid but lacks a permission."""
    if soniox_error_type(err) == "permission_denied":
        return True
    return isinstance(err, SonioxAPIError) and err.status_code == 403


def is_quota_exhausted(err: BaseException) -> bool:
    """Return True when the project balance or budget blocks further work.

    These are not transient: retrying in a loop hides the real cause from the
    user, so callers surface them as repair issues instead.
    """
    return soniox_error_type(err) in QUOTA_ERROR_TYPES


def is_rate_limited(err: BaseException) -> bool:
    """Return True for any 429, including short-lived concurrency limits."""
    if isinstance(err, SonioxAPIError) and err.status_code == 429:
        return True
    return soniox_error_type(err) == "limit_exceeded"


def describe_error(err: BaseException) -> str:
    """Return a compact, secret-free description of a Soniox failure.

    The API key never appears here. ``request_id`` is included because Soniox
    support can only trace a request by that identifier.
    """
    status = getattr(err, "status_code", None)
    error_type = soniox_error_type(err) or type(err).__name__
    request_id = soniox_request_id(err) or "none"
    status_text = f" HTTP {status}" if isinstance(status, int) else ""
    return f"{error_type}{status_text} (request_id={request_id})"


def log_error(
    logger: logging.Logger,
    message: str,
    err: BaseException,
    *,
    exc_info: bool = False,
    **context: Any,
) -> None:
    """Log a Soniox failure with its error_type, HTTP status and request_id.

    Support cannot diagnose a request without the ``request_id``, and the
    human-readable message alone is not enough to tell a quota rejection from
    a permission one. ``exc_info`` adds the traceback for unexpected errors.
    """
    details = " ".join(f"{key}={value}" for key, value in context.items())
    suffix = f" [{details}]" if details else ""
    if exc_info:
        # Pass the exception explicitly: exc_info=True outside an except block
        # would resolve to sys.exc_info() and print "NoneType: None".
        logger.error(
            "%s: %s%s",
            message,
            describe_error(err),
            suffix,
            exc_info=err,
        )
    else:
        logger.error("%s: %s%s", message, describe_error(err), suffix)


def log_api_error(
    logger: logging.Logger, message: str, err: BaseException, **context: Any
) -> None:
    """Log a REST API failure at error level with a traceback."""
    log_error(logger, message, err, exc_info=True, **context)


def log_realtime_error(
    logger: logging.Logger, message: str, err: BaseException, **context: Any
) -> None:
    """Log a realtime WebSocket failure at error level with a traceback."""
    log_error(logger, message, err, exc_info=True, **context)
