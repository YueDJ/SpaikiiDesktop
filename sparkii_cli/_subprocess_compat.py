"""Backward-compatibility shim for `sparkii_cli._subprocess_compat`.

Moved into `core._subprocess_compat` during the Phase 0 trim.
"""

import core._subprocess_compat as _impl

globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
