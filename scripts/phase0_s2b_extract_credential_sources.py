#!/usr/bin/env python3
"""S2b: extract credential-source suppression markers from auth.py into core.

Verbatim move of three functions that depend only on core.auth_store.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "sparkii_cli" / "auth.py"
DST = ROOT / "core" / "credential_sources.py"

TARGETS = [
    "suppress_credential_source",
    "is_source_suppressed",
    "unsuppress_credential_source",
]

HEADER = '''"""Credential-source suppression markers for Sparkii core.

Extracted verbatim from ``sparkii_cli.auth`` during the Phase 0 trim.  A user can
suppress a credential source (e.g. an env var) so it is not re-seeded into the
credential pool on the next load.
"""

from core.auth_store import _auth_store_lock, _load_auth_store, _save_auth_store

__all__ = [
    "is_source_suppressed",
    "suppress_credential_source",
    "unsuppress_credential_source",
]


'''


def main() -> int:
    src = AUTH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)

    spans: list[tuple[int, int, str]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in TARGETS:
            spans.append((node.lineno, node.end_lineno, node.name))
    spans.sort()

    missing = [t for t in TARGETS if t not in {n for _, _, n in spans}]
    if missing:
        print(f"MISSING: {missing}")
        return 1

    body: list[str] = []
    for lo, hi, name in spans:
        body.extend(lines[lo - 1 : hi])
        body.append("\n\n")
    DST.write_text(HEADER + "".join(body), encoding="utf-8")

    new_lines = list(lines)
    first_lo = spans[0][0]
    for lo, hi, _ in reversed(spans):
        del new_lines[lo - 1 : hi]
    reexport = (
        "from core.credential_sources import (\n"
        "    is_source_suppressed,\n"
        "    suppress_credential_source,\n"
        "    unsuppress_credential_source,\n"
        ")\n\n"
    )
    new_lines.insert(first_lo - 1, reexport)
    AUTH.write_text("".join(new_lines), encoding="utf-8")

    print(f"extracted {len(spans)} function(s) into core/credential_sources.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
