"""Backward-compatibility shim for ``sparkii_cli.fallback_config``.

Moved into ``core.fallback_config`` during the Phase 0 trim.  New code should
import from ``core.fallback_config``.
"""

from core.fallback_config import *  # noqa: F401,F403
