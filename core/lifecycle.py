"""Sparkii lifecycle dispatch for first-party observers and plugins.

Moved from ``sparkii_cli/lifecycle.py`` during the Block 4 split.  The
first-party observability observer registration stays on the surface side
(``sparkii_cli/plugins.py`` shim); core hook call sites dispatch through
``core.plugins.invoke_hook``, which fires the registered observer first.
"""

from __future__ import annotations

import logging
from typing import Any, List

logger = logging.getLogger(__name__)


def invoke_hook(hook_name: str, **kwargs: Any) -> List[Any]:
    """Notify first-party observers, then invoke plugin hooks (core-owned)."""
    try:
        from core.observability import observe_lifecycle

        observe_lifecycle(hook_name, **kwargs)
    except Exception:
        logger.warning("Built-in observability hook failed: %s", hook_name, exc_info=True)

    # Dispatch plugins directly (bypassing core.plugins.invoke_hook's observer
    # wrapper) so the first-party observability call above fires exactly once.
    from core.plugins import _delivery_manager

    return _delivery_manager().invoke_hook(hook_name, **kwargs)


def has_hook(hook_name: str) -> bool:
    """Return whether a first-party observer or plugin consumes a hook."""
    from core.plugins import has_hook as _has_hook

    return _has_hook(hook_name)


def finalize_session(**kwargs: Any) -> List[Any]:
    """Notify observers and hard-close one core-owned Relay conversation."""
    try:
        from core.observability import observe_lifecycle

        observe_lifecycle("on_session_finalize", **kwargs)
    except Exception:
        logger.warning("Built-in observability hook failed", exc_info=True)

    session_id = str(kwargs.get("session_id") or "")
    if session_id:
        try:
            from agent import relay_runtime

            relay_runtime.SESSION_COORDINATOR.finalize_conversation(
                profile_key=relay_runtime.current_profile_key(),
                session_id=session_id,
            )
        except Exception:
            logger.warning("Core Relay session finalization failed", exc_info=True)

    from core.plugins import _delivery_manager

    return _delivery_manager().invoke_hook("on_session_finalize", **kwargs)
