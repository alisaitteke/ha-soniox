"""Install Soniox SDK stubs when the real package cannot import.

pytest-homeassistant-custom-component currently pulls Home Assistant
2024.12, which pins Pydantic v1. The official soniox 2.10 SDK needs
Pydantic v2. Production Home Assistant 2025.2+ is compatible with the
real SDK; tests only need the exception types and client constructor.
"""

from __future__ import annotations

import sys
from types import ModuleType


def install_soniox_stubs_if_needed() -> None:
    """Register stub modules if `import soniox` fails."""
    try:
        import soniox  # noqa: F401
        from soniox.errors import SonioxAuthenticationError  # noqa: F401
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

    class AsyncSonioxClient:
        """Minimal async client placeholder."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            self.models = ModuleType("models")
            self.models.list = _noop_async  # type: ignore[attr-defined]

        async def aclose(self) -> None:
            return None

    async def _noop_async(*_args: object, **_kwargs: object) -> None:
        return None

    errors = ModuleType("soniox.errors")
    errors.SonioxError = SonioxError
    errors.SonioxAuthenticationError = SonioxAuthenticationError
    errors.SonioxServerError = SonioxServerError

    pkg = ModuleType("soniox")
    pkg.AsyncSonioxClient = AsyncSonioxClient
    pkg.errors = errors

    sys.modules["soniox"] = pkg
    sys.modules["soniox.errors"] = errors
