"""Backward-compatibility shim for `sparkii_cli.env_loader`.

Moved into `core.env_loader` during the Phase 0 trim.
"""

import core.env_loader as _impl

globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
