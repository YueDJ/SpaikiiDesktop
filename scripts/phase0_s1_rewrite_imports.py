#!/usr/bin/env python3
"""S1 migration: rewrite ``gateway.session_context`` imports to ``core.session_context``.

This is a bulk mechanical rewrite performed once during the Phase 0 trim.  It
only rewrites import lines; comments and docstrings are left untouched.  Encoding
and line endings are preserved.  The script is idempotent: re-running it after the
migration finds nothing to change.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = (
    "agent", "tools", "gateway", "sparkii_cli", "tui_gateway", "acp_adapter",
    "cron", "providers", "plugins", "scripts", "tests",
)
SKIP = {"core/session_context.py", "gateway/session_context.py"}

_PATTERNS = (
    re.compile(r"^(\s*)from\s+gateway\.session_context\s+import\b"),
    re.compile(r"^(\s*)import\s+gateway\.session_context\b"),
    re.compile(r"^(\s*)from\s+gateway\s+import\s+session_context\b"),
)
_REPLACEMENTS = (
    r"\1from core.session_context import",
    r"\1import core.session_context",
    r"\1from core import session_context",
)


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _rewrite(path: Path) -> int:
    relp = _rel(path)
    if relp in SKIP:
        return 0
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            text = fh.read()
    except (UnicodeDecodeError, OSError):
        return 0

    lines = text.splitlines(keepends=True)
    changed = 0
    for i, line in enumerate(lines):
        new = line
        for pat, rep in zip(_PATTERNS, _REPLACEMENTS):
            new = pat.sub(rep, new)
        if new != line:
            lines[i] = new
            changed += 1

    if changed:
        with path.open("w", encoding="utf-8", newline="") as fh:
            fh.write("".join(lines))
    return changed


def main() -> int:
    files = set(ROOT.glob("*.py"))
    for d in SCAN_DIRS:
        files.update((ROOT / d).rglob("*.py"))

    total_files = 0
    total_lines = 0
    for path in sorted(files):
        if any(part in {"node_modules", ".venv", "__pycache__", "dist", "build"} for part in path.parts):
            continue
        changed = _rewrite(path)
        if changed:
            total_files += 1
            total_lines += changed
            print(f"{_rel(path)}: {changed} line(s)")

    print(f"\nrewrote {total_lines} import line(s) across {total_files} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
