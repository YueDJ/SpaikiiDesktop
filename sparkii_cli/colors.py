"""Backward-compatibility shim for ``sparkii_cli.colors``.

Moved into ``core.colors`` during the Phase 0 trim.  New code should
import from ``core.colors``.
"""

from core.colors import *  # noqa: F401,F403
