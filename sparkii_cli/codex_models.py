"""Backward-compatibility shim for ``sparkii_cli.codex_models``.

Moved into ``core.codex_models`` during the Phase 0 trim.  New code should
import from ``core.codex_models``.
"""

from core.codex_models import *  # noqa: F401,F403
