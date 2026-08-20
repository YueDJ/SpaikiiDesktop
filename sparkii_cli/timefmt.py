"""Backward-compatibility shim for ``sparkii_cli.timefmt``.

Moved into ``core.timefmt`` during the Phase 0 trim.  New code should
import from ``core.timefmt``.
"""

from core.timefmt import *  # noqa: F401,F403
