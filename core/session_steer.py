"""Session-steer authority bridge (Block 4 split).

``tools/delegate_tool.py`` needs the live TUI session-steer authority for an
owner session.  The authoritative implementation lives in the frontend
(``tui_gateway/server.py``), which registers a provider here at import time;
non-TUI hosts get ``(None, None)``.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

_steer_provider: Optional[Callable[[str], tuple[Any, Any]]] = None


def set_session_steer_authority_provider(provider: Optional[Callable[[str], tuple[Any, Any]]]) -> None:
    """Register the TUI session-steer authority resolver."""
    global _steer_provider
    _steer_provider = provider


def get_session_steer_authority(owner_session_id: str) -> tuple[Any, Any]:
    """Return ``(transport, generation)`` for an owner session, or ``(None, None)``."""
    provider = _steer_provider
    if provider is None:
        return None, None
    try:
        return provider(owner_session_id)
    except Exception:  # noqa: BLE001 - provider absence must not crash the kernel
        return None, None
