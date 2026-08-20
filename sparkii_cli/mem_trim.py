"""Backward-compatibility shim for `sparkii_cli.mem_trim`.

Moved into `core.mem_trim` during the Phase 0 trim.
"""

import core.mem_trim as _impl

globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
