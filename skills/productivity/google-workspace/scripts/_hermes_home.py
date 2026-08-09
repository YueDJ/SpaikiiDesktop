"""Resolve SPARKII_HOME for standalone skill scripts.

Skill scripts may run outside the Hermes process (e.g. system Python,
nix env, CI) where ``sparkii_constants`` is not importable.  This module
provides the same ``get_sparkii_home()`` and ``display_sparkii_home()``
contracts as ``sparkii_constants`` without requiring it on ``sys.path``.

When ``sparkii_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``sparkii_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``SPARKII_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from sparkii_constants import display_sparkii_home as display_sparkii_home
    from sparkii_constants import get_sparkii_home as get_sparkii_home
except (ModuleNotFoundError, ImportError):

    def get_sparkii_home() -> Path:
        """Return the Hermes home directory (default: ~/.hermes).

        Mirrors ``sparkii_constants.get_sparkii_home()``."""
        val = os.environ.get("SPARKII_HOME", "").strip()
        return Path(val) if val else Path.home() / ".hermes"

    def display_sparkii_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``sparkii_constants.display_sparkii_home()``."""
        home = get_sparkii_home()
        try:
            return "~/" + str(home.relative_to(Path.home()))
        except ValueError:
            return str(home)
