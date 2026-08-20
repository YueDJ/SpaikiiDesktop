"""Backward-compatibility shim for ``sparkii_cli.build_info``.

Moved into ``core.build_info`` during the Phase 0 trim.  New code should
import from ``core.build_info``.
"""

from core.build_info import *  # noqa: F401,F403
