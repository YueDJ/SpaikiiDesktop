"""Backward-compatibility shim for `sparkii_cli.dep_ensure`.

Moved into `core.dep_ensure` during the Phase 0 trim.
"""

import core.dep_ensure as _impl

globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
