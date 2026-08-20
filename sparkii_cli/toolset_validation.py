"""Backward-compatibility shim for ``sparkii_cli.toolset_validation``.

Moved into ``core.toolset_validation`` during the Phase 0 trim.  New code should
import from ``core.toolset_validation``.
"""

from core.toolset_validation import *  # noqa: F401,F403
