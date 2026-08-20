"""Shim for :mod:`core.observability.relay_runtime` (Block 4 split)."""

from __future__ import annotations

import sys

import core.observability.relay_runtime as _core_mod

sys.modules[__name__] = _core_mod
