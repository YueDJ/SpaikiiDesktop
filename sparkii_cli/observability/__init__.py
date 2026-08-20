"""Shim package for :mod:`core.observability` (Block 4 split).

The implementation moved to core; this package aliases the core submodules so
existing surface imports keep working.
"""

from __future__ import annotations

import sys

import core.observability as _core_pkg

sys.modules[__name__] = _core_pkg
