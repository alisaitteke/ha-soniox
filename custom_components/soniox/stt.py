"""Soniox speech-to-text platform for Assist."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterable
from typing import Any

from homeassistant.components.stt import (
    AudioBitRates,
    AudioChannels,
    AudioCodecs,
    AudioFormats,
    AudioSampleRates,
    SpeechMetadata,
    SpeechResult,
    SpeechResultState,
    SpeechToTextEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from soniox.errors import SonioxError
from soniox.types import RealtimeSTTConfig, StructuredContext, TranslationConfig

from .const import (
    CONF_CONTEXT,
    CONF_CONTEXT_TERMS,
    CONF_ENABLE_DIARIZATION,
    CONF_ENABLE_ENDPOINT_DETECTION,
    CONF_ENABLE_TRANSLATION,
    CONF_LANGUAGE_HINTS,
    CONF_MAX_ENDPOINT_DELAY_MS,
    CONF_STT_MODEL,
    CONF_TRANSLATION_TARGET,
    DEFAULT_ENABLE_DIARIZATION,
    DEFAULT_ENABLE_ENDPOINT_DETECTION,
    DEFAULT_ENABLE_TRANSLATION,
    DEFAULT_LANGUAGE,
    DEFAULT_MAX_ENDPOINT_DELAY_MS,
    DEFAULT_STT_MODEL,
    SUPPORTED_LANGUAGES,
)
from .exceptions import log_realtime_error
from .models import (
    SonioxConfigEntry,
    language_to_iso639,
    model_supports_max_endpoint_delay,
    soniox_device_info,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 10

_ENDPOINT_TOKEN = "<end>"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonioxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Soniox STT entity."""
    async_add_entities([SonioxSpeechToTextEntity(entry)])


class SonioxSpeechToTextEntity(SpeechToTextEntity):
    """Soniox realtime speech-to-text entity."""

    _attr_has_entity_name = True
    _attr_translation_key = "soniox_stt"

    def __init__(self, entry: SonioxConfigEntry) -> None:
        """Initialize the STT entity."""
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_stt"
        self._attr_device_info = soniox_device_info(entry.entry_id)

    @property
    def supported_languages(self) -> list[str]:
        """Return languages Assist can select for this engine."""
        return list(SUPPORTED_LANGUAGES)

    @property
    def supported_formats(self) -> list[AudioFormats]:
        """Return supported container formats."""
        return [AudioFormats.WAV]

    @property
    def supported_codecs(self) -> list[AudioCodecs]:
        """Return supported codecs."""
        return [AudioCodecs.PCM]

    @property
    def supported_bit_rates(self) -> list[AudioBitRates]:
        """Return supported bit rates."""
        return [AudioBitRates.BITRATE_16]

    @property
    def supported_sample_rates(self) -> list[AudioSampleRates]:
        """Return supported sample rates (Assist is 16 kHz)."""
        return [AudioSampleRates.SAMPLERATE_16000]

    @property
    def supported_channels(self) -> list[AudioChannels]:
        """Return supported channel counts."""
        return [AudioChannels.CHANNEL_MONO]

    def _option(self, key: str, default: Any) -> Any:
        """Return a stored option, falling back for older entries."""
        options = self._entry.options
        if key not in options or options[key] is None:
            return default
        return options[key]

    def _language_hints(self, assist_language: str) -> list[str] | None:
        """Merge option hints with the Assist pipeline language.

        Soniox validates ``language_hints`` as two-letter ISO 639-1 codes, so
        every value is normalized before it reaches the SDK.
        """
        hints: list[str] = []
        seen: set[str] = set()
        stored = self._option(CONF_LANGUAGE_HINTS, [])
        raw_values: list[Any] = []
        if isinstance(stored, str):
            raw_values = [part.strip() for part in stored.split(",") if part.strip()]
        elif isinstance(stored, list | tuple):
            raw_values = list(stored)
        raw_values.append(assist_language)
        for raw in raw_values:
            iso = language_to_iso639(str(raw)) if raw else ""
            if iso and iso not in seen:
                seen.add(iso)
                hints.append(iso)
        return hints or None

    def _structured_context(self) -> StructuredContext | None:
        """Return structured context when text or terms are set."""
        text = str(self._option(CONF_CONTEXT, "") or "").strip()
        terms_raw = str(self._option(CONF_CONTEXT_TERMS, "") or "")
        terms = [part.strip() for part in terms_raw.split(",") if part.strip()]
        if not text and not terms:
            return None
        return StructuredContext(text=text or None, terms=terms or None)

    def _translation(self) -> TranslationConfig | None:
        """Return one-way translation config when enabled."""
        if not bool(self._option(CONF_ENABLE_TRANSLATION, DEFAULT_ENABLE_TRANSLATION)):
            return None
        raw_target = self._option(CONF_TRANSLATION_TARGET, DEFAULT_LANGUAGE)
        target = language_to_iso639(str(raw_target or DEFAULT_LANGUAGE))
        return TranslationConfig(type="one_way", target_language=target)

    def _realtime_config(self, metadata: SpeechMetadata) -> RealtimeSTTConfig:
        """Build the realtime session config from entry options."""
        model = str(self._option(CONF_STT_MODEL, DEFAULT_STT_MODEL))
        endpoint_enabled = bool(
            self._option(
                CONF_ENABLE_ENDPOINT_DETECTION, DEFAULT_ENABLE_ENDPOINT_DETECTION
            )
        )
        config: RealtimeSTTConfig = RealtimeSTTConfig(
            model=model,
            audio_format="pcm_s16le",
            sample_rate=int(metadata.sample_rate),
            num_channels=int(metadata.channel),
            language_hints=self._language_hints(metadata.language),
            context=self._structured_context(),
            enable_endpoint_detection=endpoint_enabled,
            enable_speaker_diarization=bool(
                self._option(CONF_ENABLE_DIARIZATION, DEFAULT_ENABLE_DIARIZATION)
            ),
            translation=self._translation(),
        )
        # Soniox models expose supports_max_endpoint_delay; sending the option
        # to a model without it fails the request instead of being ignored.
        if endpoint_enabled and model_supports_max_endpoint_delay(
            model, self._entry
        ):
            config.max_endpoint_delay_ms = int(
                self._option(
                    CONF_MAX_ENDPOINT_DELAY_MS, DEFAULT_MAX_ENDPOINT_DELAY_MS
                )
            )
        return config

    def _append_final_token(
        self,
        texts: list[str],
        token: object,
        *,
        diarization: bool,
        last_speaker: str | None,
    ) -> str | None:
        """Append a final token, prefixing a speaker change when diarization is on."""
        text = getattr(token, "text", None)
        if not text or text == _ENDPOINT_TOKEN or not getattr(token, "is_final", False):
            return last_speaker
        speaker = str(getattr(token, "speaker", "") or "") if diarization else ""
        if speaker and speaker != last_speaker:
            if texts and not texts[-1].endswith((" ", "\n")):
                texts.append(" ")
            texts.append(f"[{speaker}] ")
            last_speaker = speaker
        texts.append(text)
        return last_speaker

    async def async_process_audio_stream(
        self, metadata: SpeechMetadata, stream: AsyncIterable[bytes]
    ) -> SpeechResult:
        """Stream Assist PCM audio to Soniox realtime STT."""
        config = self._realtime_config(metadata)
        client = self._entry.runtime_data.client
        texts: list[str] = []
        got_audio = False
        last_speaker: str | None = None
        diarization = bool(config.enable_speaker_diarization)
        translation = self._translation()
        _LOGGER.debug(
            "Starting Soniox STT session: model=%s language=%s sample_rate=%s "
            "channels=%s endpoint_detection=%s diarization=%s "
            "translation=%s hints=%s",
            config.model,
            metadata.language,
            metadata.sample_rate,
            metadata.channel,
            config.enable_endpoint_detection,
            diarization,
            getattr(translation, "target_language", None),
            config.language_hints,
        )

        try:
            async with client.realtime.stt.connect(config=config) as session:

                async def _pump_audio() -> None:
                    nonlocal got_audio
                    async for chunk in stream:
                        if not chunk:
                            continue
                        got_audio = True
                        await session.send_byte_chunk(chunk)
                    await session.finish()

                pump_task = asyncio.create_task(_pump_audio())
                try:
                    async for event in session.receive_events():
                        if event.error_code or event.error_message:
                            # Soniox reports realtime failures in the stream
                            # itself rather than by raising, so the error is
                            # logged here and the caller gets an error result.
                            _LOGGER.error(
                                "Soniox STT stream reported an error: %s (code=%s, "
                                "model=%s)",
                                event.error_message,
                                event.error_code,
                                config.model,
                            )
                            return SpeechResult(None, SpeechResultState.ERROR)
                        for token in event.tokens:
                            last_speaker = self._append_final_token(
                                texts,
                                token,
                                diarization=diarization,
                                last_speaker=last_speaker,
                            )
                        if event.finished or any(
                            token.text == _ENDPOINT_TOKEN for token in event.tokens
                        ):
                            break
                finally:
                    await pump_task
        except SonioxError as err:
            log_realtime_error(
                _LOGGER,
                "Soniox STT session failed",
                err,
                model=config.model,
            )
            return SpeechResult(None, SpeechResultState.ERROR)

        text = "".join(texts).strip()
        if not text:
            # An empty transcript is common when the user says nothing or the
            # model rejects the audio, so it is logged to aid debugging but is
            # not treated as an error worth a traceback.
            _LOGGER.debug(
                "Soniox STT returned no speech (audio_received=%s, model=%s)",
                got_audio,
                config.model,
            )
            return SpeechResult(None, SpeechResultState.ERROR)
        _LOGGER.debug(
            "Soniox STT transcript ready (characters=%s, model=%s)",
            len(text),
            config.model,
        )
        return SpeechResult(text, SpeechResultState.SUCCESS)
