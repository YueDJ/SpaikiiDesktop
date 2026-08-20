"""Resolve SPARKII_HOME for standalone skill scripts.

Skill scripts may run outside the Sparkii process (system Python, nix env,
CI) where ``sparkii_constants`` is not importable.  This module provides the
same ``get_sparkii_home()`` contract without requiring it on ``sys.path``.

When ``sparkii_constants`` IS available it is used directly so profile
resolution and any future enhancements are picked up automatically.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from sparkii_constants import get_sparkii_home as get_sparkii_home
except (ModuleNotFoundError, ImportError):

    def get_sparkii_home() -> Path:
        """Return the Sparkii home directory (default: ``~/.sparkii``)."""
        val = os.environ.get("SPARKII_HOME", "").strip()
        return Path(val) if val else Path.home() / ".sparkii"
