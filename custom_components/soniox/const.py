"""Constants for the Soniox integration."""

from typing import Final

from homeassistant.const import CONF_API_KEY

DOMAIN: Final = "soniox"

CONF_REGION: Final = "region"

CONF_STT_MODEL: Final = "stt_model"
CONF_TTS_MODEL: Final = "tts_model"
CONF_TTS_VOICE: Final = "tts_voice"
CONF_LANGUAGE_HINTS: Final = "language_hints"
CONF_CONTEXT: Final = "context"
CONF_ENABLE_ENDPOINT_DETECTION: Final = "enable_endpoint_detection"
CONF_ENABLE_TRANSLATION: Final = "enable_translation"
CONF_ENABLE_DIARIZATION: Final = "enable_diarization"

DEFAULT_REGION: Final = "us"
DEFAULT_STT_MODEL: Final = "stt-rt-v5"
DEFAULT_TTS_MODEL: Final = "tts-rt-v2"

REGIONS: Final = ("us", "eu", "jp", "in")

DEFAULT_OPTIONS: Final[dict[str, str]] = {
    CONF_STT_MODEL: DEFAULT_STT_MODEL,
    CONF_TTS_MODEL: DEFAULT_TTS_MODEL,
}

# Official regional hosts: https://soniox.com/docs/data-residency
# Keys match AsyncSonioxClient constructor parameters.
REGION_ENDPOINTS: Final[dict[str, dict[str, str]]] = {
    "us": {
        "api_base_url": "https://api.soniox.com/v1",
        "websocket_base_url": "wss://stt-rt.soniox.com/transcribe-websocket",
        "tts_api_base_url": "https://tts-rt.soniox.com",
        "tts_websocket_base_url": "wss://tts-rt.soniox.com/tts-websocket",
    },
    "eu": {
        "api_base_url": "https://api.eu.soniox.com/v1",
        "websocket_base_url": "wss://stt-rt.eu.soniox.com/transcribe-websocket",
        "tts_api_base_url": "https://tts-rt.eu.soniox.com",
        "tts_websocket_base_url": "wss://tts-rt.eu.soniox.com/tts-websocket",
    },
    "jp": {
        "api_base_url": "https://api.jp.soniox.com/v1",
        "websocket_base_url": "wss://stt-rt.jp.soniox.com/transcribe-websocket",
        "tts_api_base_url": "https://tts-rt.jp.soniox.com",
        "tts_websocket_base_url": "wss://tts-rt.jp.soniox.com/tts-websocket",
    },
    "in": {
        "api_base_url": "https://api.in.soniox.com/v1",
        "websocket_base_url": "wss://stt-rt.in.soniox.com/transcribe-websocket",
        "tts_api_base_url": "https://tts-rt.in.soniox.com",
        "tts_websocket_base_url": "wss://tts-rt.in.soniox.com/tts-websocket",
    },
}

# Re-export for config-flow schemas that import from const.
__all__ = [
    "CONF_API_KEY",
    "CONF_CONTEXT",
    "CONF_ENABLE_DIARIZATION",
    "CONF_ENABLE_ENDPOINT_DETECTION",
    "CONF_ENABLE_TRANSLATION",
    "CONF_LANGUAGE_HINTS",
    "CONF_REGION",
    "CONF_STT_MODEL",
    "CONF_TTS_MODEL",
    "CONF_TTS_VOICE",
    "DEFAULT_OPTIONS",
    "DEFAULT_REGION",
    "DEFAULT_STT_MODEL",
    "DEFAULT_TTS_MODEL",
    "DOMAIN",
    "REGIONS",
    "REGION_ENDPOINTS",
]
