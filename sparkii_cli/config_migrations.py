"""Backward-compatibility shim for ``sparkii_cli.config_migrations``.

Moved into ``core.config_migrations`` during the Phase 0 trim.  Re-exports the full
public + private API so existing importers keep working.
"""

import core.config_migrations as _impl

globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
