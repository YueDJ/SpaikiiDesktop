"""Backward-compatibility shim for ``sparkii_cli.credential_lifecycle``.

Moved into ``core.credential_lifecycle`` during the Phase 0 trim.  Re-exports the full
public + private API so existing importers keep working.
"""

import core.credential_lifecycle as _impl

globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
