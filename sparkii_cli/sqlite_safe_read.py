"""Backward-compatibility shim for ``sparkii_cli.sqlite_safe_read``.

Moved into ``core.sqlite_safe_read`` during the Phase 0 trim.  New code should
import from ``core.sqlite_safe_read``.
"""

from core.sqlite_safe_read import *  # noqa: F401,F403
