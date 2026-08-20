"""Backward-compatibility shim for `sparkii_cli.urllib_security`.

Moved into `core.urllib_security` during the Phase 0 trim.
"""

import core.urllib_security as _impl

globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
