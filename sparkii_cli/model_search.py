"""Backward-compatibility shim for `sparkii_cli.model_search`.

Moved into `core.model_search` during the Phase 0 trim.
"""

import core.model_search as _impl

globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
