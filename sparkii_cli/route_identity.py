"""Backward-compatibility shim for ``sparkii_cli.route_identity``.

Moved into ``core.route_identity`` during the Phase 0 trim.  New code should
import from ``core.route_identity``.
"""

from core.route_identity import *  # noqa: F401,F403
