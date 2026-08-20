"""Gateway service-management bridge (Block 4 split).

``core/profiles.py`` needs platform service facts (s6/systemd/launchd detection,
service names, plist paths) for profile lifecycle management, but the actual
implementations live in the frontend (``sparkii_cli/service_manager.py`` +
``sparkii_cli/gateway.py``).  The surface registers a provider namespace here
at import time; core-only processes get ``None`` and skip service actions.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

_service_provider: Optional[Callable[[], Any]] = None


def set_gateway_service_provider(provider: Optional[Callable[[], Any]]) -> None:
    """Register a callable returning the gateway-service namespace."""
    global _service_provider
    _service_provider = provider


def get_gateway_service_context():
    """Return the registered gateway-service namespace, or ``None``."""
    provider = _service_provider
    if provider is None:
        return None
    try:
        return provider()
    except Exception:  # noqa: BLE001 - surface absence must not crash the kernel
        return None
