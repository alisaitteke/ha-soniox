"""Tests for Soniox model/voice catalog loading."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from soniox.errors import SonioxPermissionDeniedError, SonioxServerError

from custom_components.soniox.catalog import (
    PERM_CLONED_VOICES,
    PERM_MODEL_LISTING,
    async_load_catalog,
)
from custom_components.soniox.const import DEFAULT_TTS_MODEL, DEFAULT_TTS_VOICE

_EMPTY_MODELS = SimpleNamespace(models=[])
_EMPTY_VOICES = SimpleNamespace(voices=[])


def _client(
    *,
    models: object | Exception = _EMPTY_MODELS,
    tts_models: object | Exception = _EMPTY_MODELS,
    voices: object | Exception = _EMPTY_VOICES,
) -> SimpleNamespace:
    """Build a catalog client with list results or raised errors."""

    def _list(result: object | Exception) -> AsyncMock:
        mock = AsyncMock()
        if isinstance(result, Exception):
            mock.side_effect = result
        else:
            mock.return_value = result
        return mock

    return SimpleNamespace(
        models=SimpleNamespace(list=_list(models)),
        tts_models=SimpleNamespace(list=_list(tts_models)),
        voices=SimpleNamespace(list=_list(voices)),
    )


async def test_catalog_lists_realtime_models_and_voices() -> None:
    """Realtime STT models and TTS voices are returned; aliases are skipped."""
    catalog = await async_load_catalog(
        _client(
            models=SimpleNamespace(
                models=[
                    SimpleNamespace(
                        id="stt-rt-v5",
                        name="STT RT v5",
                        transcription_mode="real_time",
                        aliased_model_id=None,
                    ),
                    SimpleNamespace(
                        id="stt-async",
                        name="Async",
                        transcription_mode="async",
                        aliased_model_id=None,
                    ),
                    SimpleNamespace(
                        id="stt-alias",
                        name="Alias",
                        transcription_mode="real_time",
                        aliased_model_id="stt-rt-v5",
                    ),
                ]
            ),
            tts_models=SimpleNamespace(
                models=[
                    SimpleNamespace(
                        id="tts-rt-v2",
                        name="TTS RT v2",
                        aliased_model_id=None,
                        voices=[
                            SimpleNamespace(id="Adrian", description="warm"),
                        ],
                    )
                ]
            ),
            voices=SimpleNamespace(
                voices=[SimpleNamespace(id="voice-1", name="Home")]
            ),
        )
    )
    assert [option["value"] for option in catalog.stt_models] == ["stt-rt-v5"]
    assert [option["value"] for option in catalog.tts_models] == ["tts-rt-v2"]
    assert [option["value"] for option in catalog.voices] == ["Adrian", "voice-1"]
    assert catalog.missing_permissions == []


async def test_catalog_permission_denied_falls_back() -> None:
    """403 listing errors become missing_permissions instead of raising."""
    catalog = await async_load_catalog(
        _client(
            models=SonioxPermissionDeniedError("no models"),
            tts_models=SonioxPermissionDeniedError("no tts"),
            voices=SonioxPermissionDeniedError("no cloned"),
        )
    )
    assert catalog.stt_models == []
    assert PERM_MODEL_LISTING in catalog.missing_permissions
    assert PERM_CLONED_VOICES in catalog.missing_permissions
    assert catalog.tts_models == [
        {"value": DEFAULT_TTS_MODEL, "label": DEFAULT_TTS_MODEL}
    ]
    assert catalog.voices == [{"value": DEFAULT_TTS_VOICE, "label": DEFAULT_TTS_VOICE}]


async def test_catalog_other_errors_also_fallback() -> None:
    """Non-permission API errors still fall back so the options form can open."""
    catalog = await async_load_catalog(
        _client(models=SonioxServerError("unavailable"))
    )
    assert PERM_MODEL_LISTING in catalog.missing_permissions
    assert catalog.stt_models == []
