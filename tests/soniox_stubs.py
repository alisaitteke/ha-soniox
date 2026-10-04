"""Install Soniox SDK stubs when the real package cannot import.

pytest-homeassistant-custom-component currently pulls Home Assistant
2024.12, which pins Pydantic v1. The official soniox 2.10 SDK needs
Pydantic v2. Production Home Assistant 2025.2+ is compatible with the
real SDK; tests only need the exception types, config models, and
client constructor.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace


def install_soniox_stubs_if_needed() -> None:
    """Register stub modules if `import soniox` fails."""
    try:
        import soniox  # noqa: F401
        from soniox.errors import (  # noqa: F401
            SonioxAuthenticationError,
            SonioxPermissionDeniedError,
        )
        from soniox.types import (  # noqa: F401
            CreateTtsConfig,
            RealtimeSTTConfig,
            RealtimeTTSConfig,
            StructuredContext,
            TranslationConfig,
        )
    except Exception:
        for name in list(sys.modules):
            if name == "soniox" or name.startswith("soniox."):
                del sys.modules[name]
    else:
        return

    class SonioxError(Exception):
        """Base Soniox error."""

    class SonioxAuthenticationError(SonioxError):
        """Auth failure."""

    class SonioxServerError(SonioxError):
        """Server-side failure."""

    class SonioxAPIError(SonioxError):
        """API failure."""

    class SonioxRealtimeError(SonioxError):
        """Realtime session failure."""

    class SonioxPermissionDeniedError(SonioxError):
        """Permission denied."""

        status_code = 403

    class _Config:
        """Minimal stand-in for pydantic realtime config models."""

        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    class AsyncSonioxClient:
        """Minimal async client placeholder."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            self.models = SimpleNamespace(list=_noop_async)
            self.tts_models = SimpleNamespace(list=_noop_async)
            self.voices = SimpleNamespace(list=_noop_async)
            self.tts = SimpleNamespace(generate=_noop_async)
            self.realtime = SimpleNamespace(
                stt=SimpleNamespace(connect=_unused_connect),
                tts=SimpleNamespace(connect=_unused_connect),
            )

        async def aclose(self) -> None:
            return None

    async def _noop_async(*_args: object, **_kwargs: object) -> None:
        return None

    def _unused_connect(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("Stub realtime connect is not used in tests")

    errors = ModuleType("soniox.errors")
    errors.SonioxError = SonioxError
    errors.SonioxAuthenticationError = SonioxAuthenticationError
    errors.SonioxServerError = SonioxServerError
    errors.SonioxAPIError = SonioxAPIError
    errors.SonioxRealtimeError = SonioxRealtimeError
    errors.SonioxPermissionDeniedError = SonioxPermissionDeniedError

    types_mod = ModuleType("soniox.types")
    types_mod.RealtimeSTTConfig = _Config
    types_mod.RealtimeTTSConfig = _Config
    types_mod.CreateTtsConfig = _Config
    types_mod.StructuredContext = _Config
    types_mod.TranslationConfig = _Config

    pkg = ModuleType("soniox")
    pkg.AsyncSonioxClient = AsyncSonioxClient
    pkg.errors = errors
    pkg.types = types_mod

    sys.modules["soniox"] = pkg
    sys.modules["soniox.errors"] = errors
    sys.modules["soniox.types"] = types_mod
