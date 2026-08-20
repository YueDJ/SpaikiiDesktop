"""Backward-compatibility shim for ``sparkii_cli.mcp_security``.

Moved into ``core.mcp_security`` during the Phase 0 trim.  New code should
import from ``core.mcp_security``.
"""

from core.mcp_security import *  # noqa: F401,F403
