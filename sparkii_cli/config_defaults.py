"""Backward-compatibility shim for ``core.config_defaults``.

Moved into ``core.config_defaults`` during the Phase 0 trim.  New code should
import from ``core.config_defaults``.
"""

from core.config_defaults import *  # noqa: F401,F403
