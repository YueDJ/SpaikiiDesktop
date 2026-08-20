"""Backward-compatibility shim for `sparkii_cli.plugin_capabilities`.

Moved into `core.plugin_capabilities` during the Phase 0 trim.
"""

import core.plugin_capabilities as _impl

globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
