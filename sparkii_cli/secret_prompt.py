"""Backward-compatibility shim for ``sparkii_cli.secret_prompt``.

Moved into ``core.secret_prompt`` during the Phase 0 trim.  New code should
import from ``core.secret_prompt``.
"""

from core.secret_prompt import *  # noqa: F401,F403
