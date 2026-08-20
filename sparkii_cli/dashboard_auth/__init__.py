"""Dashboard authentication provider framework.

The dashboard auth gate engages only when the dashboard binds to a
non-loopback host without ``--insecure``. In that mode, every request must
carry a verified session from one of the registered ``DashboardAuthProvider``
plugins.

The Nous provider lives in ``plugins/dashboard-auth-nous/`` and is the
default. Third parties register their own providers via the plugin hook
``ctx.register_dashboard_auth_provider``.
"""
from sparkii_cli.dashboard_auth.base import (
    DashboardAuthProvider,
    Session,
    TokenPrincipal,
    LoginStart,
    InvalidCodeError,
    InvalidCredentialsError,
    ProviderError,
    RefreshExpiredError,
    assert_protocol_compliance,
)
from sparkii_cli.dashboard_auth.registry import (
    register_provider,
    get_provider,
    list_providers,
    list_token_providers,
    list_session_providers,
    clear_providers,
)
from sparkii_cli.dashboard_auth.token_auth import register_token_route

__all__ = [
    "DashboardAuthProvider",
    "Session",
    "TokenPrincipal",
    "LoginStart",
    "InvalidCodeError",
    "InvalidCredentialsError",
    "ProviderError",
    "RefreshExpiredError",
    "assert_protocol_compliance",
    "register_provider",
    "get_provider",
    "list_providers",
    "list_token_providers",
    "list_session_providers",
    "clear_providers",
]


# Register the dashboard-auth provider framework with the core plugin loader
# so ``PluginContext.register_dashboard_auth_provider`` can reach it without
# the plugin system importing the dashboard surface.
try:
    from types import SimpleNamespace as _SimpleNamespace

    from sparkii_cli.dashboard_auth.registry import (
        restore_registration as _restore_registration,
        snapshot_registration as _snapshot_registration,
    )
    from core.plugins import set_dashboard_auth_provider

    set_dashboard_auth_provider(
        _SimpleNamespace(
            DashboardAuthProvider=DashboardAuthProvider,
            InvalidCodeError=InvalidCodeError,
            InvalidCredentialsError=InvalidCredentialsError,
            LoginStart=LoginStart,
            ProviderError=ProviderError,
            RefreshExpiredError=RefreshExpiredError,
            Session=Session,
            TokenPrincipal=TokenPrincipal,
            assert_protocol_compliance=assert_protocol_compliance,
            register_provider=register_provider,
            register_token_route=register_token_route,
            restore_registration=_restore_registration,
            snapshot_registration=_snapshot_registration,
        )
    )
except Exception:  # pragma: no cover - defensive
    pass
