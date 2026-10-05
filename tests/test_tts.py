"""Tests for the Soniox TTS entity."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from homeassistant.components.tts import ATTR_VOICE, Voice
from homeassistant.exceptions import HomeAssistantError
from soniox.errors import SonioxAPIError
from soniox.types import ApiError

from custom_components.soniox.const import (
    CONF_REDUCE_SILENCE,
    CONF_TTS_MODEL,
    CONF_TTS_SPEED,
    CONF_TTS_VOICE,
    DEFAULT_TTS_MODEL,
    DEFAULT_TTS_VOICE,
)
from custom_components.soniox.tts import SonioxTextToSpeechEntity, _fallback_voices


class _FakeTTSSession:
    """Async context manager that records text and yields audio chunks."""

    def __init__(
        self, chunks: list[bytes], error: Exception | None = None
    ) -> None:
        self.chunks = chunks
        self.error = error
        self.sent: list[object] = []
        self.text_end = False

    async def __aenter__(self) -> _FakeTTSSession:
        if self.error:
            raise self.error
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def send_text_chunks(
        self, chunks: object, *, text_end: bool = True
    ) -> None:
        self.sent.append(chunks)
        self.text_end = text_end

    async def receive_audio_chunks(self):
        for chunk in self.chunks:
            yield chunk


def _entry(
    *,
    generate: AsyncMock | None = None,
    session: _FakeTTSSession | None = None,
) -> MagicMock:
    client = MagicMock()
    client.tts.generate = generate or AsyncMock(return_value=b"RIFF-wav")
    if session is not None:
        client.realtime.tts.connect.return_value = session
    entry = MagicMock()
    entry.entry_id = "entry-tts"
    entry.options = {
        CONF_TTS_MODEL: DEFAULT_TTS_MODEL,
        CONF_TTS_VOICE: DEFAULT_TTS_VOICE,
        CONF_TTS_SPEED: 1.0,
        CONF_REDUCE_SILENCE: False,
    }
    entry.runtime_data = SimpleNamespace(client=client)
    return entry


async def test_tts_generate_returns_wav() -> None:
    """One-shot synthesis returns wav bytes from the REST API."""
    generate = AsyncMock(return_value=b"RIFF-fake-wav")
    entity = SonioxTextToSpeechEntity(_entry(generate=generate))
    ext, audio = await entity.async_get_tts_audio("Hello", "en-US", {})
    assert ext == "wav"
    assert audio == b"RIFF-fake-wav"
    generate.assert_awaited_once()
    kwargs = generate.await_args.kwargs
    assert kwargs["text"] == "Hello"
    assert kwargs["language"] == "en"
    assert kwargs["voice"] == DEFAULT_TTS_VOICE
    assert kwargs["audio_format"] == "wav"


async def test_tts_generate_error_raises() -> None:
    """API failures are wrapped as HomeAssistantError."""
    generate = AsyncMock(side_effect=SonioxAPIError("nope"))
    entity = SonioxTextToSpeechEntity(_entry(generate=generate))
    with pytest.raises(HomeAssistantError):
        await entity.async_get_tts_audio("Hello", "en", {})


async def test_tts_stream_yields_chunks() -> None:
    """Realtime TTS yields audio chunks from the session."""
    session = _FakeTTSSession([b"chunk-a", b"chunk-b"])
    entity = SonioxTextToSpeechEntity(_entry(session=session))

    async def messages():
        yield "Hello "
        yield "world"

    chunks = [
        chunk
        async for chunk in entity.async_iter_tts_audio(messages(), "tr-TR", {})
    ]
    assert chunks == [b"chunk-a", b"chunk-b"]
    assert session.text_end is True
    config = entity._entry.runtime_data.client.realtime.tts.connect.call_args.kwargs[
        "config"
    ]
    assert config.voice == DEFAULT_TTS_VOICE
    assert config.speed == 1.0
    assert config.reduce_silence is False


async def test_tts_generate_uses_speed_and_voice() -> None:
    """Saved speed, voice, and reduce_silence are passed to generate."""
    generate = AsyncMock(return_value=b"RIFF-fake-wav")
    entry = _entry(generate=generate)
    entry.options = {
        CONF_TTS_MODEL: DEFAULT_TTS_MODEL,
        CONF_TTS_VOICE: "Riley",
        CONF_TTS_SPEED: 1.2,
        CONF_REDUCE_SILENCE: True,
    }
    entity = SonioxTextToSpeechEntity(entry)
    await entity.async_get_tts_audio("Hello", "en", {})
    kwargs = generate.await_args.kwargs
    assert kwargs["voice"] == "Riley"
    assert kwargs["config"].speed == 1.2
    assert kwargs["config"].reduce_silence is True


async def test_tts_request_voice_overrides_option() -> None:
    """Assist voice picker value wins over the saved default."""
    generate = AsyncMock(return_value=b"RIFF-fake-wav")
    entity = SonioxTextToSpeechEntity(_entry(generate=generate))
    await entity.async_get_tts_audio("Hello", "en", {ATTR_VOICE: "Rebecca"})
    assert generate.await_args.kwargs["voice"] == "Rebecca"


async def test_tts_stream_error_midstream_becomes_home_assistant_error() -> None:
    """A failure after audio has started must still reach the caller.

    ``except`` around a bare ``yield`` cannot run once the consumer has
    received a chunk, so the raw SDK error used to escape uncaught.
    """

    class _FailingSession(_FakeTTSSession):
        async def receive_audio_chunks(self):
            yield b"partial-audio"
            raise SonioxAPIError("stream died")

    session = _FailingSession([b"partial-audio"])
    entity = SonioxTextToSpeechEntity(_entry(session=session))

    async def messages():
        yield "Hello"

    with pytest.raises(HomeAssistantError, match="Unable to stream Soniox speech"):
        async for _chunk in entity.async_iter_tts_audio(messages(), "en", {}):
            pass


async def test_tts_stream_connect_error_becomes_home_assistant_error() -> None:
    """A connect failure is reported as HomeAssistantError, not an SDK error."""
    session = _FakeTTSSession([], error=SonioxAPIError("connect failed"))
    entity = SonioxTextToSpeechEntity(_entry(session=session))

    async def messages():
        yield "Hello"

    with pytest.raises(HomeAssistantError, match="Unable to stream Soniox speech"):
        async for _chunk in entity.async_iter_tts_audio(messages(), "en", {}):
            pass


async def test_tts_supports_streaming_input() -> None:
    """Assist only uses the streaming path when the entity advertises it."""
    entity = SonioxTextToSpeechEntity(_entry())
    assert entity.async_supports_streaming_input() is True


async def test_tts_logs_request_parameters(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Debug logs must name the model, voice and language actually used."""
    generate = AsyncMock(return_value=b"RIFF-fake-wav")
    entity = SonioxTextToSpeechEntity(_entry(generate=generate))
    with caplog.at_level(logging.DEBUG, logger="custom_components.soniox.tts"):
        await entity.async_get_tts_audio("Merhaba", "tr-TR", {})

    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "Requesting Soniox TTS" in messages
    assert DEFAULT_TTS_MODEL in messages
    assert DEFAULT_TTS_VOICE in messages
    assert "tr-TR" in messages


async def test_tts_logs_error_with_model_and_voice(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A TTS failure must be logged with the request context and a traceback."""
    api_error = ApiError(
        status_code=429,
        error_type="limit_exceeded",
        message="Too many requests",
        request_id="req-tts",
    )
    generate = AsyncMock(
        side_effect=SonioxAPIError(
            "rate limited", api_error=api_error, response=httpx.Response(429)
        )
    )
    entity = SonioxTextToSpeechEntity(_entry(generate=generate))
    with (
        caplog.at_level(logging.ERROR, logger="custom_components.soniox.tts"),
        pytest.raises(HomeAssistantError),
    ):
        await entity.async_get_tts_audio("Merhaba", "en", {})

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, "TTS failure was not logged"
    message = errors[0].getMessage()
    assert "Soniox TTS generation failed" in message
    assert "limit_exceeded" in message
    assert "HTTP 429" in message
    assert "req-tts" in message
    assert DEFAULT_TTS_MODEL in message
    assert errors[0].exc_info is not None


async def test_tts_stream_error_logs_request_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Streaming failures are logged with the Soniox request_id."""
    api_error = ApiError(
        status_code=429,
        error_type="max_concurrent_streams_reached",
        message="Too many concurrent streams",
        request_id="req-stream",
    )
    session = _FakeTTSSession(
        [],
        error=SonioxAPIError(
            "concurrency", api_error=api_error, response=httpx.Response(429)
        ),
    )
    entity = SonioxTextToSpeechEntity(_entry(session=session))

    async def messages():
        yield "Hello"

    with (
        caplog.at_level(logging.ERROR, logger="custom_components.soniox.tts"),
        pytest.raises(HomeAssistantError),
    ):
        async for _chunk in entity.async_iter_tts_audio(messages(), "en", {}):
            pass

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors
    message = errors[0].getMessage()
    assert "max_concurrent_streams_reached" in message
    assert "req-stream" in message
    assert DEFAULT_TTS_MODEL in message


async def test_tts_supported_voices_uses_cached_catalog() -> None:
    """Assist lists voices cached on the entity at setup."""
    entry = _entry()
    voices = [Voice("Adrian", "Adrian — warm"), Voice("Riley", "Riley")]
    entity = SonioxTextToSpeechEntity(entry, voices)
    assert entity.async_get_supported_voices("en") == voices


async def test_tts_fallback_voices_include_adrian() -> None:
    """Catalog fetch failure still exposes the saved voice and Adrian."""
    voices = _fallback_voices("Riley")
    assert [voice.voice_id for voice in voices] == ["Riley", DEFAULT_TTS_VOICE]
