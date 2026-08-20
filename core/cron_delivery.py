"""Cron delivery bridge (Block 4 Step 2b).

The cron scheduler is core-owned but delivers job results through the
gateway's messaging machinery (live adapters, session mirroring, relay,
delivery routing, media policy).  The gateway registers a namespace of
delivery functions here at import time; core-only processes get ``None`` and
cron delivery degrades to a clear error instead of importing the frontend.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

_delivery_provider: Optional[Callable[[], Any]] = None


def set_cron_delivery_provider(provider: Optional[Callable[[], Any]]) -> None:
    """Register the gateway cron-delivery namespace builder."""
    global _delivery_provider
    _delivery_provider = provider


def get_cron_delivery():
    """Return the registered cron-delivery namespace, or ``None``."""
    provider = _delivery_provider
    if provider is None:
        return None
    try:
        return provider()
    except Exception:  # noqa: BLE001 - surface absence must not crash the scheduler
        return None
