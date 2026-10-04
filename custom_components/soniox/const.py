"""Constants for the Soniox integration."""

from typing import Any, Final

from homeassistant.const import CONF_API_KEY

DOMAIN: Final = "soniox"

CONF_REGION: Final = "region"

CONF_STT_MODEL: Final = "stt_model"
CONF_TTS_MODEL: Final = "tts_model"
CONF_TTS_VOICE: Final = "tts_voice"
CONF_LANGUAGE_HINTS: Final = "language_hints"
CONF_CONTEXT: Final = "context"
CONF_CONTEXT_TERMS: Final = "context_terms"
CONF_ENABLE_ENDPOINT_DETECTION: Final = "enable_endpoint_detection"
CONF_MAX_ENDPOINT_DELAY_MS: Final = "max_endpoint_delay_ms"
CONF_ENABLE_TRANSLATION: Final = "enable_translation"
CONF_TRANSLATION_TARGET: Final = "translation_target"
CONF_ENABLE_DIARIZATION: Final = "enable_diarization"
CONF_TTS_SPEED: Final = "tts_speed"
CONF_REDUCE_SILENCE: Final = "reduce_silence"

DEFAULT_REGION: Final = "us"
DEFAULT_STT_MODEL: Final = "stt-rt-v5"
DEFAULT_TTS_MODEL: Final = "tts-rt-v2"
DEFAULT_TTS_VOICE: Final = "Adrian"
DEFAULT_LANGUAGE: Final = "en"
DEFAULT_TTS_SPEED: Final = 1.0
DEFAULT_MAX_ENDPOINT_DELAY_MS: Final = 2000
DEFAULT_ENABLE_ENDPOINT_DETECTION: Final = True
DEFAULT_ENABLE_TRANSLATION: Final = False
DEFAULT_ENABLE_DIARIZATION: Final = False
DEFAULT_REDUCE_SILENCE: Final = False

# ISO 639-1 codes Soniox recognizes, plus common Assist BCP-47 tags.
SUPPORTED_LANGUAGES: Final[tuple[str, ...]] = (
    "af",
    "ar",
    "az",
    "be",
    "bg",
    "bn",
    "bs",
    "ca",
    "cs",
    "cy",
    "da",
    "de",
    "el",
    "en",
    "es",
    "et",
    "eu",
    "fa",
    "fi",
    "fr",
    "gl",
    "gu",
    "he",
    "hi",
    "hr",
    "hu",
    "hy",
    "id",
    "is",
    "it",
    "ja",
    "ka",
    "kk",
    "kn",
    "ko",
    "lt",
    "lv",
    "mk",
    "ml",
    "mn",
    "mr",
    "ms",
    "mt",
    "nl",
    "no",
    "pa",
    "pl",
    "pt",
    "ro",
    "ru",
    "sk",
    "sl",
    "sq",
    "sr",
    "sv",
    "sw",
    "ta",
    "te",
    "th",
    "tl",
    "tr",
    "uk",
    "ur",
    "uz",
    "vi",
    "zh",
    "ar-SA",
    "de-DE",
    "en-GB",
    "en-US",
    "es-ES",
    "es-MX",
    "fr-FR",
    "it-IT",
    "ja-JP",
    "ko-KR",
    "nl-NL",
    "pl-PL",
    "pt-BR",
    "pt-PT",
    "ru-RU",
    "tr-TR",
    "uk-UA",
    "zh-CN",
)

# ISO 639-1 codes only — Soniox language_hints reject BCP-47 tags.
LANGUAGE_HINTS: Final[tuple[str, ...]] = tuple(
    code for code in SUPPORTED_LANGUAGES if "-" not in code
)

REGIONS: Final = ("us", "eu", "jp", "in")

SONIOX_CONSOLE_URL: Final = "https://console.soniox.com"

DEFAULT_OPTIONS: Final[dict[str, Any]] = {
    CONF_STT_MODEL: DEFAULT_STT_MODEL,
    CONF_TTS_MODEL: DEFAULT_TTS_MODEL,
    CONF_TTS_VOICE: DEFAULT_TTS_VOICE,
    CONF_LANGUAGE_HINTS: [],
    CONF_CONTEXT: "",
    CONF_CONTEXT_TERMS: "",
    CONF_ENABLE_ENDPOINT_DETECTION: DEFAULT_ENABLE_ENDPOINT_DETECTION,
    CONF_MAX_ENDPOINT_DELAY_MS: DEFAULT_MAX_ENDPOINT_DELAY_MS,
    CONF_ENABLE_DIARIZATION: DEFAULT_ENABLE_DIARIZATION,
    CONF_ENABLE_TRANSLATION: DEFAULT_ENABLE_TRANSLATION,
    CONF_TRANSLATION_TARGET: DEFAULT_LANGUAGE,
    CONF_TTS_SPEED: DEFAULT_TTS_SPEED,
    CONF_REDUCE_SILENCE: DEFAULT_REDUCE_SILENCE,
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
    "CONF_CONTEXT_TERMS",
    "CONF_ENABLE_DIARIZATION",
    "CONF_ENABLE_ENDPOINT_DETECTION",
    "CONF_ENABLE_TRANSLATION",
    "CONF_LANGUAGE_HINTS",
    "CONF_MAX_ENDPOINT_DELAY_MS",
    "CONF_REDUCE_SILENCE",
    "CONF_REGION",
    "CONF_STT_MODEL",
    "CONF_TRANSLATION_TARGET",
    "CONF_TTS_MODEL",
    "CONF_TTS_SPEED",
    "CONF_TTS_VOICE",
    "DEFAULT_ENABLE_DIARIZATION",
    "DEFAULT_ENABLE_ENDPOINT_DETECTION",
    "DEFAULT_ENABLE_TRANSLATION",
    "DEFAULT_LANGUAGE",
    "DEFAULT_MAX_ENDPOINT_DELAY_MS",
    "DEFAULT_OPTIONS",
    "DEFAULT_REDUCE_SILENCE",
    "DEFAULT_REGION",
    "DEFAULT_STT_MODEL",
    "DEFAULT_TTS_MODEL",
    "DEFAULT_TTS_SPEED",
    "DEFAULT_TTS_VOICE",
    "DOMAIN",
    "LANGUAGE_HINTS",
    "SUPPORTED_LANGUAGES",
    "REGIONS",
    "REGION_ENDPOINTS",
    "SONIOX_CONSOLE_URL",
]
