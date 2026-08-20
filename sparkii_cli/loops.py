"""CLI-facing shim for :mod:`core.loops`.

The implementation moved to core during the Phase 0 foundation trim
(Block 4 Step 2).  This module re-exports the core module so existing surface
imports and tests keep working; new code should import from ``core.loops``
directly.
"""

from __future__ import annotations

import core.loops as _core_mod


def __getattr__(name):
    """Forward any attribute to the core module."""
    return getattr(_core_mod, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_core_mod)))
