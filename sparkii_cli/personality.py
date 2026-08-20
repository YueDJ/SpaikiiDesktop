"""Backward-compatibility shim for ``sparkii_cli.personality``.

Moved into ``core.personality`` during the Phase 0 trim.  New code should
import from ``core.personality``.
"""

from core.personality import *  # noqa: F401,F403
