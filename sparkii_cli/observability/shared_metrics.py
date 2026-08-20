"""Shim for :mod:`core.observability.shared_metrics` (Block 4 split)."""

from __future__ import annotations

import sys

import core.observability.shared_metrics as _core_mod

sys.modules[__name__] = _core_mod
