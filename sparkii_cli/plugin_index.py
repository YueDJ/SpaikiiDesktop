"""Backward-compatibility shim for `sparkii_cli.plugin_index`.

Moved into `core.plugin_index` during the Phase 0 trim.
"""

import core.plugin_index as _impl

globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
