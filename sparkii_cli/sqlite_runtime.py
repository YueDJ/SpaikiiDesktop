"""Backward-compatibility shim for ``sparkii_cli.sqlite_runtime``.

Moved into ``core.sqlite_runtime`` during the Phase 0 trim.  New code should
import from ``core.sqlite_runtime``.
"""

from core.sqlite_runtime import *  # noqa: F401,F403
