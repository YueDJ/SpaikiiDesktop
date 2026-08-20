"""Backward-compatibility shim for ``sparkii_cli.default_soul``.

Moved into ``core.default_soul`` during the Phase 0 trim.  New code should
import from ``core.default_soul``.
"""

from core.default_soul import *  # noqa: F401,F403
