"""Backward-compatibility shim for ``gateway.session_context``.

The session-context system moved into the core foundation package (``core``) as
part of the Phase 0 trim.  This module exists only so existing consumers that
still import ``gateway.session_context`` keep working.  New code should import
from ``core.session_context`` instead.
"""

from core.session_context import (  # noqa: F401
    NON_MESSAGING_SESSION_SURFACES,
    async_delivery_supported,
    clear_session_vars,
    declare_stateless_channel,
    get_session_env,
    reset_session_vars,
    scoped_current_session_id,
    session_context_engaged,
    session_is_messaging_surface,
    set_current_session_id,
    set_session_vars,
)

__all__ = [
    "NON_MESSAGING_SESSION_SURFACES",
    "async_delivery_supported",
    "clear_session_vars",
    "declare_stateless_channel",
    "get_session_env",
    "reset_session_vars",
    "scoped_current_session_id",
    "session_context_engaged",
    "session_is_messaging_surface",
    "set_current_session_id",
    "set_session_vars",
]
