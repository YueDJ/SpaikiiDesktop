"""Backward-compatibility shim for `sparkii_cli.sizefmt`.

Moved into `core.sizefmt` during the Phase 0 trim.
"""

import core.sizefmt as _impl

globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
