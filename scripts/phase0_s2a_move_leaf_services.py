#!/usr/bin/env python3
"""S2a migration: move the 10 zero-dependency sparkii_cli service leaves into core/.

These modules are pure-stdlib leaves (verified by ``phase0_s2_analyze.py``): they
import nothing from ``sparkii_cli``, ``agent``, or ``gateway``.  This script
renames each file, writes a backward-compat shim at the old path, and rewrites
absolute import sites ``sparkii_cli.<name>`` -> ``core.<name>`` across the tree.

Idempotent: re-running after the migration is a no-op.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NAMES = (
    "build_info",
    "codex_models",
    "config_defaults",
    "fallback_config",
    "route_identity",
    "sqlite_runtime",
    "sqlite_safe_read",
    "sqlite_util",
    "timefmt",
    "toolset_validation",
)

SCAN_DIRS = (
    "agent", "tools", "gateway", "sparkii_cli", "tui_gateway", "acp_adapter",
    "cron", "providers", "plugins", "scripts", "tests",
)
SKIP_DIR_PARTS = {"node_modules", ".venv", "__pycache__", "dist", "build", ".git"}


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _rewrite_imports() -> tuple[int, int]:
    """Rewrite sparkii_cli.<name> -> core.<name> on import lines only."""
    files = set(ROOT.glob("*.py"))
    for d in SCAN_DIRS:
        files.update((ROOT / d).rglob("*.py"))

    patterns = [
        (re.compile(rf"^(\s*)from\s+sparkii_cli\.{n}\s+import\b"), rf"\1from core.{n} import")
        for n in NAMES
    ]
    patterns += [
        (re.compile(rf"^(\s*)import\s+sparkii_cli\.{n}\b"), rf"\1import core.{n}")
        for n in NAMES
    ]

    files_changed = 0
    lines_changed = 0
    for path in sorted(files):
        relp = _rel(path)
        if relp.startswith("core/") or relp in {f"sparkii_cli/{n}.py" for n in NAMES}:
            continue
        if any(part in SKIP_DIR_PARTS for part in path.parts):
            continue
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                text = fh.read()
        except (UnicodeDecodeError, OSError):
            continue
        lines = text.splitlines(keepends=True)
        changed = 0
        for i, line in enumerate(lines):
            new = line
            for pat, rep in patterns:
                new = pat.sub(rep, new)
            if new != line:
                lines[i] = new
                changed += 1
        if changed:
            with path.open("w", encoding="utf-8", newline="") as fh:
                fh.write("".join(lines))
            files_changed += 1
            lines_changed += changed
    return files_changed, lines_changed


def main() -> int:
    moved = 0
    for name in NAMES:
        src = ROOT / "sparkii_cli" / f"{name}.py"
        dst = ROOT / "core" / f"{name}.py"
        if not src.exists():
            continue
        shutil.move(str(src), str(dst))
        moved += 1
        shim = ROOT / "sparkii_cli" / f"{name}.py"
        shim.write_text(
            '"""Backward-compatibility shim for ``sparkii_cli.%(n)s``.\n\n'
            "Moved into ``core.%(n)s`` during the Phase 0 trim.  New code should\n"
            "import from ``core.%(n)s``.\n"
            '"""\n\n'
            "from core.%(n)s import *  # noqa: F401,F403\n"
            % {"n": name},
            encoding="utf-8",
        )

    files_changed, lines_changed = _rewrite_imports()
    print(f"moved {moved} file(s) into core/")
    print(f"rewrote {lines_changed} import line(s) across {files_changed} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
