"""Backward-compatibility shim for `sparkii_cli.timeouts`.

Moved into `core.timeouts` during the Phase 0 trim.
"""

import core.timeouts as _impl

globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
