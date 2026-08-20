"""Backward-compatibility shim for ``sparkii_cli.sqlite_util``.

Moved into ``core.sqlite_util`` during the Phase 0 trim.  New code should
import from ``core.sqlite_util``.
"""

from core.sqlite_util import *  # noqa: F401,F403
