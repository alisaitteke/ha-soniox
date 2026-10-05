"""Soniox text-to-speech platform for Assist."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator
from typing import Any
from uuid import uuid4

from homeassistant.components.tts import (
    ATTR_VOICE,
    TextToSpeechEntity,
    TtsAudioType,
    Voice,
)
from homeassistant.components.tts.entity import (
    TTSAudioRequest,
    TTSAudioResponse,
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
from .exceptions import log_api_error, log_realtime_error
from .models import SonioxConfigEntry, language_to_iso639, soniox_device_info

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 6


async def _aiter(chunks: AsyncIterable[str]) -> AsyncIterator[str]:
    """Adapt an AsyncIterable to the AsyncIterator the SDK expects."""
    async for chunk in chunks:
        yield chunk


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

    def _option(self, key: str, default: Any) -> Any:
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
        voice = self._voice(options)
        model = self._model()
        speed = self._speed()
        _LOGGER.debug(
            "Requesting Soniox TTS: model=%s voice=%s language=%s speed=%s "
            "characters=%s",
            model,
            voice,
            language,
            speed,
            len(message),
        )
        try:
            audio = await self._entry.runtime_data.client.tts.generate(
                text=message,
                voice=voice,
                model=model,
                language=language_to_iso639(language),
                audio_format="wav",
                config=CreateTtsConfig(
                    speed=speed,
                    reduce_silence=self._reduce_silence(),
                ),
            )
        except SonioxError as err:
            log_api_error(
                _LOGGER,
                "Soniox TTS generation failed",
                err,
                model=model,
                voice=voice,
            )
            raise HomeAssistantError("Unable to generate Soniox speech") from err
        if not audio:
            _LOGGER.error(
                "Soniox TTS returned empty audio (model=%s, voice=%s)",
                model,
                voice,
            )
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
        _LOGGER.debug(
            "Starting Soniox streaming TTS: model=%s voice=%s language=%s "
            "stream_id=%s",
            config.model,
            config.voice,
            config.language,
            config.stream_id,
        )
        # A bare ``except`` around a ``yield`` cannot run: once the consumer
        # receives a chunk it may suspend or abandon the generator, and the
        # failure then escapes uncaught. Buffering keeps the session open
        # until the audio is complete so failures are converted to a
        # HomeAssistantError the caller can act on.
        buffered: list[bytes] = []
        try:
            async with self._entry.runtime_data.client.realtime.tts.connect(
                config=config
            ) as session:
                await session.send_text_chunks(
                    _aiter(message_chunks), text_end=True
                )
                async for chunk in session.receive_audio_chunks():
                    if chunk:
                        buffered.append(chunk)
        except SonioxError as err:
            log_realtime_error(
                _LOGGER,
                "Soniox streaming TTS failed",
                err,
                model=config.model,
                voice=config.voice,
                stream_id=config.stream_id,
            )
            raise HomeAssistantError("Unable to stream Soniox speech") from err

        if not buffered:
            _LOGGER.error(
                "Soniox streaming TTS produced no audio (model=%s, voice=%s)",
                config.model,
                config.voice,
            )
        _LOGGER.debug(
            "Soniox streaming TTS finished (chunks=%s, bytes=%s)",
            len(buffered),
            sum(len(chunk) for chunk in buffered),
        )
        for chunk in buffered:
            yield chunk

    async def async_stream_tts_audio(
        self, request: TTSAudioRequest
    ) -> TTSAudioResponse:
        """Stream speech to Assist using the realtime TTS WebSocket API."""
        return TTSAudioResponse(
            "wav",
            self.async_iter_tts_audio(
                request.message_gen, request.language, request.options
            ),
        )
