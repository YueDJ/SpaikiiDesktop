"""Backward-compatibility shim for `sparkii_cli.moa_config`.

Moved into `core.moa_config` during the Phase 0 trim.
"""

import core.moa_config as _impl

globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
