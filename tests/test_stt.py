"""Tests for the Soniox STT entity."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.components.stt import (
    AudioBitRates,
    AudioChannels,
    AudioCodecs,
    AudioFormats,
    AudioSampleRates,
    SpeechMetadata,
    SpeechResultState,
)
from pydantic import ValidationError
from soniox.errors import SonioxRealtimeError
from soniox.types import RealtimeSTTConfig

from custom_components.soniox.catalog import SonioxCatalog
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
    session: _FakeSTTSession,
    options: dict[str, object] | None = None,
    catalog: object | None = None,
) -> MagicMock:
    client = MagicMock()
    client.realtime.stt.connect.return_value = session
    entry = MagicMock()
    entry.entry_id = "entry-stt"
    entry.options = {"stt_model": DEFAULT_STT_MODEL, **(options or {})}
    entry.runtime_data = SimpleNamespace(client=client, catalog=catalog)
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


def test_stt_entity_does_not_shadow_ha_context() -> None:
    """Entity._context is Home Assistant event provenance; do not override it."""
    assert "_context" not in SonioxSpeechToTextEntity.__dict__
    assert hasattr(SonioxSpeechToTextEntity, "_structured_context")


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


async def test_stt_skips_endpoint_delay_for_unsupported_model() -> None:
    """max_endpoint_delay_ms must not be sent to a model that rejects it.

    Soniox rejects the option on models reporting
    supports_max_endpoint_delay=false, which fails the whole request.
    """
    session = _FakeSTTSession(
        [
            SimpleNamespace(
                tokens=[SimpleNamespace(text="Hi", is_final=True)],
                finished=True,
                error_code=None,
                error_message=None,
            )
        ]
    )
    catalog = SonioxCatalog(
        supports_max_endpoint_delay={DEFAULT_STT_MODEL: False}
    )
    entry = _entry(
        session,
        {CONF_MAX_ENDPOINT_DELAY_MS: 1500, CONF_ENABLE_ENDPOINT_DETECTION: True},
        catalog=catalog,
    )
    entity = SonioxSpeechToTextEntity(entry)
    await entity.async_process_audio_stream(_metadata(), _pcm_stream(b"\x00\x01" * 8))

    config = entry.runtime_data.client.realtime.stt.connect.call_args.kwargs["config"]
    assert config.enable_endpoint_detection is True
    assert config.max_endpoint_delay_ms is None


async def test_stt_sends_endpoint_delay_for_supported_model() -> None:
    """A model that advertises support receives the configured delay."""
    session = _FakeSTTSession(
        [
            SimpleNamespace(
                tokens=[SimpleNamespace(text="Hi", is_final=True)],
                finished=True,
                error_code=None,
                error_message=None,
            )
        ]
    )
    catalog = SonioxCatalog(
        supports_max_endpoint_delay={DEFAULT_STT_MODEL: True}
    )
    entry = _entry(
        session,
        {CONF_MAX_ENDPOINT_DELAY_MS: 1500, CONF_ENABLE_ENDPOINT_DETECTION: True},
        catalog=catalog,
    )
    entity = SonioxSpeechToTextEntity(entry)
    await entity.async_process_audio_stream(_metadata(), _pcm_stream(b"\x00\x01" * 8))

    config = entry.runtime_data.client.realtime.stt.connect.call_args.kwargs["config"]
    assert config.max_endpoint_delay_ms == 1500


def test_realtime_config_rejects_bcp47_language_hints() -> None:
    """Guard the SDK contract the entity relies on.

    Soniox validates language_hints as two-letter ISO 639-1 codes, which is why
    language_to_iso639 must run before the config is built. If Soniox ever
    relaxes this, the test tells us rather than leaving us with dead code.
    """
    with pytest.raises(ValidationError):
        RealtimeSTTConfig(
            model=DEFAULT_STT_MODEL,
            audio_format="pcm_s16le",
            sample_rate=16000,
            num_channels=1,
            language_hints=["tr-TR"],
        )
    # The normalized value is accepted.
    config = RealtimeSTTConfig(
        model=DEFAULT_STT_MODEL,
        audio_format="pcm_s16le",
        sample_rate=16000,
        num_channels=1,
        language_hints=[language_to_iso639("tr-TR")],
    )
    assert config.language_hints == ["tr"]


async def test_stt_logs_model_and_language_on_session_start(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Debug logs must name the model and language actually used."""
    session = _FakeSTTSession(
        [
            SimpleNamespace(
                tokens=[SimpleNamespace(text="Hi", is_final=True)],
                finished=True,
                error_code=None,
                error_message=None,
            )
        ]
    )
    entity = SonioxSpeechToTextEntity(_entry(session))
    with caplog.at_level(logging.DEBUG, logger="custom_components.soniox.stt"):
        await entity.async_process_audio_stream(
            _metadata("tr-TR"), _pcm_stream(b"\x00")
        )

    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "Starting Soniox STT session" in messages
    assert DEFAULT_STT_MODEL in messages
    assert "tr-TR" in messages
    assert "16000" in messages


async def test_stt_logs_error_with_model_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A realtime failure must be logged with the model and a traceback."""
    session = _FakeSTTSession([], error=SonioxRealtimeError("offline"))
    entity = SonioxSpeechToTextEntity(_entry(session))
    with caplog.at_level(logging.ERROR, logger="custom_components.soniox.stt"):
        result = await entity.async_process_audio_stream(
            _metadata(), _pcm_stream(b"\x00\x00")
        )

    assert result.result is SpeechResultState.ERROR
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, "realtime failure was not logged"
    message = errors[0].getMessage()
    assert "Soniox STT session failed" in message
    assert "SonioxRealtimeError" in message
    assert DEFAULT_STT_MODEL in message
    # A traceback is what makes a field failure diagnosable.
    assert errors[0].exc_info is not None


async def test_stt_stream_error_event_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Soniox reports some failures in the stream rather than by raising."""
    session = _FakeSTTSession(
        [
            SimpleNamespace(
                tokens=[],
                finished=False,
                error_code=403,
                error_message="temp_api_key_session_expired",
            )
        ]
    )
    entity = SonioxSpeechToTextEntity(_entry(session))
    with caplog.at_level(logging.ERROR, logger="custom_components.soniox.stt"):
        result = await entity.async_process_audio_stream(
            _metadata(), _pcm_stream(b"\x00\x01" * 8)
        )

    assert result.result is SpeechResultState.ERROR
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors
    message = errors[0].getMessage()
    assert "temp_api_key_session_expired" in message
    assert "403" in message


async def test_stt_empty_transcript_logs_at_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Silence is normal, so it must not spam the log at error level."""
    session = _FakeSTTSession([])
    entity = SonioxSpeechToTextEntity(_entry(session))
    with caplog.at_level(logging.DEBUG, logger="custom_components.soniox.stt"):
        result = await entity.async_process_audio_stream(_metadata(), _pcm_stream())

    assert result.result is SpeechResultState.ERROR
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not errors, "empty audio should not log an error"
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "returned no speech" in messages


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
