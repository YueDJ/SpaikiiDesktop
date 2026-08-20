"""Kanban dashboard bridge hooks (Block 4 split).

``plugins/kanban/dashboard`` needs two dashboard-runtime probes that live in
the frontend (``sparkii_cli/web_server.py`` ws-auth and
``sparkii_cli/kanban.py`` dispatcher presence).  The surface registers them
here at import time; plugin runs without the dashboard fall back to
permissive defaults so board creation is never blocked.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

_ws_auth_provider: Optional[Callable[[Any], bool]] = None
_dispatcher_probe_provider: Optional[Callable[..., tuple[bool, str]]] = None


def set_dashboard_ws_auth_provider(provider: Optional[Callable[[Any], bool]]) -> None:
    """Register the dashboard WebSocket auth check (sparkii_cli/web_server)."""
    global _ws_auth_provider
    _ws_auth_provider = provider


def dashboard_ws_auth_ok(ws) -> bool:
    """Return whether a dashboard WebSocket is authorized (default: True)."""
    provider = _ws_auth_provider
    if provider is None:
        return True
    try:
        return bool(provider(ws))
    except Exception:  # noqa: BLE001 - probe absence must not crash plugins
        return True


def set_kanban_dispatcher_probe(provider: Optional[Callable[..., tuple[bool, str]]]) -> None:
    """Register the kanban dispatcher-presence probe (sparkii_cli/kanban)."""
    global _dispatcher_probe_provider
    _dispatcher_probe_provider = provider


def kanban_dispatcher_probe(**kwargs) -> tuple[bool, str]:
    """Return ``(running, message)`` for the dispatcher probe (default: running)."""
    provider = _dispatcher_probe_provider
    if provider is None:
        return True, ""
    try:
        return provider(**kwargs)
    except Exception:  # noqa: BLE001 - probe absence must not crash plugins
        return True, ""
