#!/usr/bin/env python3
"""S2b: extract the credential-store cluster from auth.py into core/auth_store.py.

Verbatim move: the extracted symbols are copied unchanged from ``sparkii_cli.auth``
and re-exported there so every existing caller keeps working.  Only the module
header (imports) is new.  Uses AST source spans so the cut is exact.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "sparkii_cli" / "auth.py"
DST = ROOT / "core" / "auth_store.py"

TARGETS = [
    "AUTH_STORE_VERSION",
    "AUTH_LOCK_TIMEOUT_SECONDS",
    "DEFAULT_NOUS_PORTAL_URL",
    "_NOUS_STALE_PORTAL_HOSTS",
    "_auth_target_lock_holders",
    "_auth_target_lock_holders_guard",
    "_auth_file_path",
    "_auth_lock_path",
    "_same_path",
    "_auth_lock_holder_for",
    "_file_lock",
    "_auth_store_lock",
    "_load_auth_store",
    "_save_auth_store",
    "_migrate_stale_nous_portal_url",
]

HEADER = '''"""Credential store persistence primitives for Sparkii core.

Extracted verbatim from ``sparkii_cli.auth`` during the Phase 0 trim.  Holds the
auth.json load/save, cross-process file locking, and the Nous portal URL
migration.  OAuth login/token flows remain in ``sparkii_cli.auth``.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional
from urllib.parse import urlparse

from sparkii_constants import get_sparkii_home, secure_parent_dir
from utils import atomic_replace

logger = logging.getLogger(__name__)


'''


def _target_name(node: ast.stmt) -> str | None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                return t.id
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def main() -> int:
    src = AUTH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)

    spans: list[tuple[int, int, str]] = []
    for node in tree.body:
        name = _target_name(node)
        if name in TARGETS:
            spans.append((node.lineno, node.end_lineno, name))
    spans.sort()

    missing = [t for t in TARGETS if t not in {n for _, _, n in spans}]
    if missing:
        print(f"MISSING TARGETS: {missing}")
        return 1

    body: list[str] = []
    for lo, hi, name in spans:
        body.append(f"# ---- {name} ----\n")
        body.extend(lines[lo - 1 : hi])
        body.append("\n")
    DST.write_text(HEADER + "".join(body), encoding="utf-8")

    # Remove extracted spans from auth.py and re-export them at the first cut.
    new_lines = list(lines)
    first_lo = spans[0][0]
    for lo, hi, _ in reversed(spans):
        del new_lines[lo - 1 : hi]

    names = [n for _, _, n in spans]
    reexport = (
        "from core.auth_store import (\n    "
        + ",\n    ".join(names)
        + ",\n)\n\n"
    )
    new_lines.insert(first_lo - 1, reexport)
    AUTH.write_text("".join(new_lines), encoding="utf-8")

    print(f"extracted {len(spans)} symbol(s) into core/auth_store.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
