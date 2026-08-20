"""Shim for :mod:`core.dashboard_auth` (Block 4 split).

The dashboard-auth base contract moved to core so dashboard-auth plugins can
subclass it without importing the dashboard surface.  This module re-exports
the core module; new code should import from ``core.dashboard_auth`` directly.
"""

from __future__ import annotations

import core.dashboard_auth as _core_mod


def __getattr__(name):
    return getattr(_core_mod, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_core_mod)))
