"""CLI-facing plugin-system shim.

The plugin loader moved to :mod:`core.plugins` during the Phase 0 foundation
trim (Block 3).  This module re-exports the core loader so existing surface
imports and tests keep working; new code should import from ``core.plugins``
directly.
"""

from __future__ import annotations

import core.plugins as _core_plugins


def __getattr__(name):
    """Forward any attribute to the core plugin loader.

    Pure ``__getattr__`` (no eager re-export) keeps every attribute access —
    including ``from sparkii_cli.plugins import X`` — live against
    ``core.plugins``, so test doubles that patch ``core.plugins.X`` are seen
    by surface consumers too.
    """
    return getattr(_core_plugins, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_core_plugins)))


# Register the first-party observability observer with the core plugin loader.
# Every surface (CLI, gateway, TUI, cron, dashboard) imports this shim, so
# core hook call sites that import ``core.plugins`` directly still dispatch
# to built-in observability features.
try:
    from types import SimpleNamespace as _SimpleNamespace

    from core.plugins import set_lifecycle_observer

    def _observe(hook_name, **kwargs):
        from sparkii_cli.observability import observe_lifecycle

        observe_lifecycle(hook_name, **kwargs)

    def _handles(hook_name):
        from sparkii_cli.observability import handles_hook

        return handles_hook(hook_name)

    set_lifecycle_observer(
        _SimpleNamespace(
            observe=_observe,
            handles=_handles,
        )
    )
except Exception:  # pragma: no cover - defensive
    pass
