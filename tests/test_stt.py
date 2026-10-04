"""Tests for the Soniox STT entity."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant.components.stt import (
    AudioBitRates,
    AudioChannels,
    AudioCodecs,
    AudioFormats,
    AudioSampleRates,
    SpeechMetadata,
    SpeechResultState,
)
from soniox.errors import SonioxRealtimeError

from custom_components.soniox.const import (
    CONF_CONTEXT,
    CONF_CONTEXT_TERMS,
    CONF_ENABLE_DIARIZATION,
    CONF_ENABLE_ENDPOINT_DETECTION,
    CONF_ENABLE_TRANSLATION,
    CONF_LANGUAGE_HINTS,
    CONF_MAX_ENDPOINT_DELAY_MS,
    CONF_STT_MODEL,
    CONF_TRANSLATION_TARGET,
    DEFAULT_STT_MODEL,
)
from custom_components.soniox.models import language_to_iso639
from custom_components.soniox.stt import SonioxSpeechToTextEntity


class _FakeSTTSession:
    """Async context manager that records audio and yields events."""

    def __init__(self, events: list[object], error: Exception | None = None) -> None:
        self.events = events
        self.error = error
        self.chunks: list[bytes] = []
        self.finished = False

    async def __aenter__(self) -> _FakeSTTSession:
        if self.error:
            raise self.error
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def send_byte_chunk(self, chunk: bytes) -> None:
        self.chunks.append(chunk)

    async def finish(self) -> None:
        self.finished = True

    async def receive_events(self):
        for event in self.events:
            yield event


def _entry(
    session: _FakeSTTSession, options: dict[str, object] | None = None
) -> MagicMock:
    client = MagicMock()
    client.realtime.stt.connect.return_value = session
    entry = MagicMock()
    entry.entry_id = "entry-stt"
    entry.options = {"stt_model": DEFAULT_STT_MODEL, **(options or {})}
    entry.runtime_data = SimpleNamespace(client=client)
    return entry


def _metadata(language: str = "tr-TR") -> SpeechMetadata:
    return SpeechMetadata(
        language=language,
        format=AudioFormats.WAV,
        codec=AudioCodecs.PCM,
        bit_rate=AudioBitRates.BITRATE_16,
        sample_rate=AudioSampleRates.SAMPLERATE_16000,
        channel=AudioChannels.CHANNEL_MONO,
    )


async def _pcm_stream(*chunks: bytes):
    for chunk in chunks:
        yield chunk


def test_language_to_iso639_strips_region() -> None:
    """Assist BCP-47 tags map to ISO 639-1 for Soniox."""
    assert language_to_iso639("tr-TR") == "tr"
    assert language_to_iso639("en") == "en"


async def test_stt_stream_returns_final_text() -> None:
    """Final tokens are concatenated into a successful transcript."""
    session = _FakeSTTSession(
        [
            SimpleNamespace(
                tokens=[
                    SimpleNamespace(text="Merhaba", is_final=True),
                    SimpleNamespace(text=" dünya", is_final=True),
                    SimpleNamespace(text="<end>", is_final=True),
                ],
                finished=False,
                error_code=None,
                error_message=None,
            )
        ]
    )
    entity = SonioxSpeechToTextEntity(_entry(session))
    result = await entity.async_process_audio_stream(
        _metadata(), _pcm_stream(b"\x00\x01" * 8)
    )
    assert result.result is SpeechResultState.SUCCESS
    assert result.text == "Merhaba dünya"
    assert session.finished


async def test_stt_empty_stream_is_error() -> None:
    """No audio and no tokens is an error."""
    session = _FakeSTTSession([])
    entity = SonioxSpeechToTextEntity(_entry(session))
    result = await entity.async_process_audio_stream(_metadata(), _pcm_stream())
    assert result.result is SpeechResultState.ERROR
    assert result.text is None


async def test_stt_sdk_error_is_error() -> None:
    """SDK failures become a speech result error, not an exception."""
    session = _FakeSTTSession([], error=SonioxRealtimeError("offline"))
    entity = SonioxSpeechToTextEntity(_entry(session))
    result = await entity.async_process_audio_stream(
        _metadata(), _pcm_stream(b"\x00\x00")
    )
    assert result.result is SpeechResultState.ERROR
    assert result.text is None


async def test_stt_options_applied_to_realtime_config() -> None:
    """Hints, context, endpoint, diarization, and translation reach the SDK."""
    session = _FakeSTTSession(
        [
            SimpleNamespace(
                tokens=[SimpleNamespace(text="Hello", is_final=True, speaker="1")],
                finished=True,
                error_code=None,
                error_message=None,
            )
        ]
    )
    entry = _entry(
        session,
        {
            CONF_STT_MODEL: "stt-rt-v4",
            CONF_LANGUAGE_HINTS: ["en"],
            CONF_CONTEXT: "kitchen names",
            CONF_CONTEXT_TERMS: "Soniox, Assist",
            CONF_ENABLE_ENDPOINT_DETECTION: True,
            CONF_MAX_ENDPOINT_DELAY_MS: 1500,
            CONF_ENABLE_DIARIZATION: True,
            CONF_ENABLE_TRANSLATION: True,
            CONF_TRANSLATION_TARGET: "en",
        },
    )
    entity = SonioxSpeechToTextEntity(entry)
    result = await entity.async_process_audio_stream(
        _metadata(), _pcm_stream(b"\x00\x01" * 8)
    )
    assert result.result is SpeechResultState.SUCCESS
    config = entry.runtime_data.client.realtime.stt.connect.call_args.kwargs["config"]
    assert config.model == "stt-rt-v4"
    assert config.language_hints == ["en", "tr"]
    assert config.context.text == "kitchen names"
    assert config.context.terms == ["Soniox", "Assist"]
    assert config.enable_endpoint_detection is True
    assert config.max_endpoint_delay_ms == 1500
    assert config.enable_speaker_diarization is True
    assert config.translation.type == "one_way"
    assert config.translation.target_language == "en"


async def test_stt_diarization_prefixes_speaker_change() -> None:
    """Speaker changes are prefixed as [1], [2], … when diarization is on."""
    session = _FakeSTTSession(
        [
            SimpleNamespace(
                tokens=[
                    SimpleNamespace(text="Hello", is_final=True, speaker="1"),
                    SimpleNamespace(text=" there", is_final=True, speaker="1"),
                    SimpleNamespace(text="Hi", is_final=True, speaker="2"),
                    SimpleNamespace(text="<end>", is_final=True, speaker="2"),
                ],
                finished=False,
                error_code=None,
                error_message=None,
            )
        ]
    )
    entity = SonioxSpeechToTextEntity(
        _entry(session, {CONF_ENABLE_DIARIZATION: True})
    )
    result = await entity.async_process_audio_stream(
        _metadata(), _pcm_stream(b"\x00\x01" * 8)
    )
    assert result.result is SpeechResultState.SUCCESS
    assert result.text == "[1] Hello there [2] Hi"
