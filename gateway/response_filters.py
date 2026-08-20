"""Shim for :mod:`core.response_filters` (Block 4 Step 2b).

The response filtering helpers moved to core so the cron scheduler (core) and
the webhook lane share one canonical implementation.  This module re-exports
the core module; existing gateway callers and patch targets keep working.
"""

from __future__ import annotations

import core.response_filters as _core_mod


def __getattr__(name):
    """Forward any attribute to the core module."""
    return getattr(_core_mod, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_core_mod)))
