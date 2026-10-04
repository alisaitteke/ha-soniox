"""Soniox text-to-speech platform for Assist."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, AsyncIterable
from typing import Any
from uuid import uuid4

from homeassistant.components.tts import (
    ATTR_VOICE,
    TextToSpeechEntity,
    TtsAudioType,
    Voice,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from soniox.errors import SonioxError
from soniox.types import CreateTtsConfig, RealtimeTTSConfig

from .catalog import async_load_catalog
from .const import (
    CONF_REDUCE_SILENCE,
    CONF_TTS_MODEL,
    CONF_TTS_SPEED,
    CONF_TTS_VOICE,
    DEFAULT_LANGUAGE,
    DEFAULT_REDUCE_SILENCE,
    DEFAULT_TTS_MODEL,
    DEFAULT_TTS_SPEED,
    DEFAULT_TTS_VOICE,
    SUPPORTED_LANGUAGES,
)
from .models import SonioxConfigEntry, language_to_iso639, soniox_device_info

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 6

try:
    from homeassistant.components.tts import TTSAudioRequest, TTSAudioResponse
except ImportError:  # Home Assistant < 2025.2 in some test pins
    TTSAudioRequest = None  # type: ignore[misc, assignment]
    TTSAudioResponse = None  # type: ignore[misc, assignment]


def _fallback_voices(configured: str) -> list[Voice]:
    """Return the saved voice plus Adrian when the catalog cannot be loaded."""
    voices = [Voice(configured, configured)]
    if configured != DEFAULT_TTS_VOICE:
        voices.append(Voice(DEFAULT_TTS_VOICE, DEFAULT_TTS_VOICE))
    return voices


async def _async_supported_voices(entry: SonioxConfigEntry) -> list[Voice]:
    """Load Assist voice picker options from the Soniox catalog."""
    configured = str(
        entry.options.get(CONF_TTS_VOICE, DEFAULT_TTS_VOICE) or DEFAULT_TTS_VOICE
    )
    try:
        catalog = await async_load_catalog(entry.runtime_data.client)
    except Exception:
        _LOGGER.debug("Unable to load Soniox voices for Assist", exc_info=True)
        return _fallback_voices(configured)
    voices = [
        Voice(option["value"], option["label"])
        for option in catalog.voices
        if option.get("value")
    ]
    if not voices:
        return _fallback_voices(configured)
    if configured not in {voice.voice_id for voice in voices}:
        voices.insert(0, Voice(configured, configured))
    return voices


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonioxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Soniox TTS entity."""
    voices = await _async_supported_voices(entry)
    async_add_entities([SonioxTextToSpeechEntity(entry, voices)])


class SonioxTextToSpeechEntity(TextToSpeechEntity):
    """Soniox text-to-speech entity."""

    _attr_has_entity_name = True
    _attr_translation_key = "soniox_tts"
    _attr_supported_options = [ATTR_VOICE]
    _attr_supported_languages = list(SUPPORTED_LANGUAGES)
    _attr_default_language = DEFAULT_LANGUAGE

    def __init__(
        self, entry: SonioxConfigEntry, voices: list[Voice] | None = None
    ) -> None:
        """Initialize the TTS entity."""
        self._entry = entry
        saved_voice = str(
            entry.options.get(CONF_TTS_VOICE, DEFAULT_TTS_VOICE) or DEFAULT_TTS_VOICE
        )
        self._voices = voices or _fallback_voices(saved_voice)
        self._attr_unique_id = f"{entry.entry_id}_tts"
        self._attr_device_info = soniox_device_info(entry.entry_id)

    def _option(self, key: str, default: object) -> object:
        """Return a stored option, falling back for older entries."""
        options = self._entry.options
        if key not in options or options[key] is None:
            return default
        return options[key]

    def _voice(self, options: dict[str, Any]) -> str:
        """Return the voice id for this request."""
        return str(
            options.get(ATTR_VOICE, self._option(CONF_TTS_VOICE, DEFAULT_TTS_VOICE))
        )

    def _model(self) -> str:
        """Return the configured TTS model."""
        return str(self._option(CONF_TTS_MODEL, DEFAULT_TTS_MODEL))

    def _speed(self) -> float:
        """Return the configured speaking rate."""
        return float(self._option(CONF_TTS_SPEED, DEFAULT_TTS_SPEED))

    def _reduce_silence(self) -> bool:
        """Return whether silence reduction is enabled."""
        return bool(self._option(CONF_REDUCE_SILENCE, DEFAULT_REDUCE_SILENCE))

    def async_get_supported_voices(self, language: str) -> list[Voice]:
        """Return catalog voices cached at setup."""
        _ = language
        return list(self._voices)

    async def async_get_tts_audio(
        self, message: str, language: str, options: dict[str, Any]
    ) -> TtsAudioType:
        """Synthesize a complete utterance via the Soniox REST TTS API."""
        try:
            audio = await self._entry.runtime_data.client.tts.generate(
                text=message,
                voice=self._voice(options),
                model=self._model(),
                language=language_to_iso639(language),
                audio_format="wav",
                config=CreateTtsConfig(
                    speed=self._speed(),
                    reduce_silence=self._reduce_silence(),
                ),
            )
        except SonioxError as err:
            _LOGGER.exception("Soniox TTS request failed")
            raise HomeAssistantError("Unable to generate Soniox speech") from err
        if not audio:
            raise HomeAssistantError("Soniox returned empty speech audio")
        return "wav", audio

    async def async_iter_tts_audio(
        self,
        message_chunks: AsyncIterable[str],
        language: str,
        options: dict[str, Any],
    ) -> AsyncGenerator[bytes]:
        """Yield WAV audio chunks from a realtime TTS session."""
        config = RealtimeTTSConfig(
            stream_id=f"ha-{uuid4()}",
            model=self._model(),
            language=language_to_iso639(language),
            voice=self._voice(options),
            audio_format="wav",
            speed=self._speed(),
            reduce_silence=self._reduce_silence(),
        )
        try:
            async with self._entry.runtime_data.client.realtime.tts.connect(
                config=config
            ) as session:
                await session.send_text_chunks(message_chunks, text_end=True)
                async for chunk in session.receive_audio_chunks():
                    if chunk:
                        yield chunk
        except SonioxError as err:
            _LOGGER.exception("Soniox streaming TTS request failed")
            raise HomeAssistantError("Unable to stream Soniox speech") from err

    if TTSAudioRequest is not None and TTSAudioResponse is not None:

        async def async_stream_tts_audio(self, request: Any) -> Any:
            """Stream speech for Assist on Home Assistant versions that support it."""
            return TTSAudioResponse(
                "wav",
                self.async_iter_tts_audio(
                    request.message_gen, request.language, request.options
                ),
            )
