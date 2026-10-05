"""Fetch Soniox STT/TTS models and voices for the options UI."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from homeassistant.helpers.selector import SelectOptionDict
from soniox import AsyncSonioxClient
from soniox.errors import SonioxError, SonioxPermissionDeniedError

from .const import DEFAULT_TTS_MODEL, DEFAULT_TTS_VOICE
from .exceptions import log_api_error

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
    # model_id -> whether the model accepts max_endpoint_delay_ms
    supports_max_endpoint_delay: dict[str, bool] = field(default_factory=dict)

    def allows_max_endpoint_delay(self, model_id: str) -> bool:
        """Return True when a model accepts max_endpoint_delay_ms.

        Unknown models are allowed through: a missing capability flag must not
        silently drop a setting the user configured, and Soniox only rejects
        the option on models that explicitly report no support.
        """
        return self.supports_max_endpoint_delay.get(model_id, True)


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
        stt_response = await client.models.list()
        for model in getattr(stt_response, "models", []) or []:
            model_id = getattr(model, "id", None)
            supports_delay = getattr(model, "supports_max_endpoint_delay", None)
            if isinstance(model_id, str) and model_id:
                if isinstance(supports_delay, bool):
                    catalog.supports_max_endpoint_delay[model_id] = supports_delay
                if getattr(model, "transcription_mode", None) != "real_time":
                    continue
                if getattr(model, "aliased_model_id", None):
                    continue
                catalog.stt_models.append(_model_option(model))
    except SonioxError as err:
        if _is_permission_denied(err):
            catalog.missing_permissions.append(PERM_MODEL_LISTING)
            _LOGGER.warning(
                "Soniox key cannot list STT models (permission missing); "
                "model and voice fields fall back to free text"
            )
        else:
            log_api_error(
                _LOGGER, "Could not list Soniox STT models", err
            )
            catalog.missing_permissions.append(PERM_MODEL_LISTING)

    try:
        tts_response = await client.tts_models.list()
        for model in getattr(tts_response, "models", []) or []:
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
            _LOGGER.warning(
                "Soniox key cannot list TTS models (permission missing); "
                "model and voice fields fall back to free text"
            )
        else:
            log_api_error(
                _LOGGER, "Could not list Soniox TTS models", err
            )
            if PERM_MODEL_LISTING not in catalog.missing_permissions:
                catalog.missing_permissions.append(PERM_MODEL_LISTING)

    try:
        voices_response = await client.voices.list()
        for voice in getattr(voices_response, "voices", []) or []:
            voice_id = str(getattr(voice, "id", ""))
            name = str(getattr(voice, "name", "") or voice_id)
            _add_unique_voice(
                catalog.voices, seen_voices, voice_id, f"{name} (cloned)"
            )
    except SonioxError as err:
        if _is_permission_denied(err):
            catalog.missing_permissions.append(PERM_CLONED_VOICES)
            _LOGGER.debug(
                "Soniox key cannot list cloned voices (permission missing); "
                "only shared voices are offered"
            )
        else:
            _LOGGER.debug("Unable to list cloned Soniox voices: %s", err)

    _LOGGER.debug(
        "Soniox catalog loaded: stt_models=%s tts_models=%s voices=%s "
        "missing_permissions=%s",
        len(catalog.stt_models),
        len(catalog.tts_models),
        len(catalog.voices),
        catalog.missing_permissions or "none",
    )

    if not catalog.voices:
        _add_unique_voice(catalog.voices, seen_voices, DEFAULT_TTS_VOICE, None)

    if not catalog.tts_models:
        catalog.tts_models.append(
            SelectOptionDict(value=DEFAULT_TTS_MODEL, label=DEFAULT_TTS_MODEL)
        )

    return catalog
