"""Fetch Soniox STT/TTS models and voices for the options UI."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from homeassistant.helpers.selector import SelectOptionDict
from soniox import AsyncSonioxClient
from soniox.errors import SonioxError, SonioxPermissionDeniedError

from .const import DEFAULT_TTS_MODEL, DEFAULT_TTS_VOICE

_LOGGER = logging.getLogger(__name__)

PERM_MODEL_LISTING = "model_listing"
PERM_CLONED_VOICES = "cloned_voices"


@dataclass
class SonioxCatalog:
    """Selectable models/voices plus which API permissions were missing."""

    stt_models: list[SelectOptionDict] = field(default_factory=list)
    tts_models: list[SelectOptionDict] = field(default_factory=list)
    voices: list[SelectOptionDict] = field(default_factory=list)
    missing_permissions: list[str] = field(default_factory=list)


def _is_permission_denied(err: Exception) -> bool:
    """Return True for a Soniox permission error."""
    if isinstance(err, SonioxPermissionDeniedError):
        return True
    return getattr(err, "status_code", None) == 403


def _model_option(model: object) -> SelectOptionDict:
    """Build a dropdown option from a Soniox model object."""
    model_id = str(getattr(model, "id", ""))
    name = str(getattr(model, "name", "") or model_id)
    return SelectOptionDict(value=model_id, label=name)


def _voice_option(voice_id: str, description: str | None = None) -> SelectOptionDict:
    """Build a dropdown option from a voice id and optional description."""
    label = f"{voice_id} — {description}" if description else voice_id
    return SelectOptionDict(value=voice_id, label=label)


def _add_unique_voice(
    voices: list[SelectOptionDict],
    seen: set[str],
    voice_id: str,
    description: str | None,
) -> None:
    """Append a voice option once."""
    if not voice_id or voice_id in seen:
        return
    seen.add(voice_id)
    voices.append(_voice_option(voice_id, description))


async def async_load_catalog(client: AsyncSonioxClient) -> SonioxCatalog:
    """List realtime STT models, TTS models, and voices.

    Permission errors do not raise: the options flow falls back to text fields.
    """
    catalog = SonioxCatalog()
    seen_voices: set[str] = set()

    try:
        response = await client.models.list()
        for model in getattr(response, "models", []) or []:
            if getattr(model, "transcription_mode", None) != "real_time":
                continue
            if getattr(model, "aliased_model_id", None):
                continue
            if getattr(model, "id", None):
                catalog.stt_models.append(_model_option(model))
    except SonioxError as err:
        if _is_permission_denied(err):
            catalog.missing_permissions.append(PERM_MODEL_LISTING)
        else:
            _LOGGER.exception("Unable to list Soniox STT models")
            catalog.missing_permissions.append(PERM_MODEL_LISTING)

    try:
        response = await client.tts_models.list()
        for model in getattr(response, "models", []) or []:
            if getattr(model, "aliased_model_id", None):
                continue
            if getattr(model, "id", None):
                catalog.tts_models.append(_model_option(model))
            for voice in getattr(model, "voices", []) or []:
                _add_unique_voice(
                    catalog.voices,
                    seen_voices,
                    str(getattr(voice, "id", "")),
                    getattr(voice, "description", None),
                )
    except SonioxError as err:
        if _is_permission_denied(err):
            if PERM_MODEL_LISTING not in catalog.missing_permissions:
                catalog.missing_permissions.append(PERM_MODEL_LISTING)
        else:
            _LOGGER.exception("Unable to list Soniox TTS models")
            if PERM_MODEL_LISTING not in catalog.missing_permissions:
                catalog.missing_permissions.append(PERM_MODEL_LISTING)

    try:
        response = await client.voices.list()
        for voice in getattr(response, "voices", []) or []:
            voice_id = str(getattr(voice, "id", ""))
            name = str(getattr(voice, "name", "") or voice_id)
            _add_unique_voice(
                catalog.voices, seen_voices, voice_id, f"{name} (cloned)"
            )
    except SonioxError as err:
        if _is_permission_denied(err):
            catalog.missing_permissions.append(PERM_CLONED_VOICES)
        else:
            _LOGGER.debug("Unable to list cloned Soniox voices: %s", err)

    if not catalog.voices:
        _add_unique_voice(catalog.voices, seen_voices, DEFAULT_TTS_VOICE, None)

    if not catalog.tts_models:
        catalog.tts_models.append(
            SelectOptionDict(value=DEFAULT_TTS_MODEL, label=DEFAULT_TTS_MODEL)
        )

    return catalog
