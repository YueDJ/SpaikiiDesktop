#!/usr/bin/env python3
"""S2b step 1: move the ANSI color utility into core as a display primitive.

``colors.py`` is a pure-stdlib leaf (``os``, ``sys``) currently used only by
CLI surface files.  Moving it to ``core`` removes one of ``config.py``'s seven
surface edges (``sparkii_cli.colors`` -> ``core.colors``) so config.py can
eventually move too.  Idempotent.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "colors"
SCAN_DIRS = (
    "agent", "tools", "gateway", "sparkii_cli", "tui_gateway", "acp_adapter",
    "cron", "providers", "plugins", "scripts", "tests",
)
SKIP = {"node_modules", ".venv", "__pycache__", "dist", "build", ".git"}


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def main() -> int:
    src = ROOT / "sparkii_cli" / f"{NAME}.py"
    dst = ROOT / "core" / f"{NAME}.py"
    if src.exists():
        shutil.move(str(src), str(dst))
    (ROOT / "sparkii_cli" / f"{NAME}.py").write_text(
        '"""Backward-compatibility shim for ``sparkii_cli.colors``.\n\n'
        "Moved into ``core.colors`` during the Phase 0 trim.  New code should\n"
        'import from ``core.colors``.\n'
        '"""\n\n'
        "from core.colors import *  # noqa: F401,F403\n",
        encoding="utf-8",
    )

    patterns = (
        (re.compile(rf"^(\s*)from\s+sparkii_cli\.{NAME}\s+import\b"), rf"\1from core.{NAME} import"),
        (re.compile(rf"^(\s*)import\s+sparkii_cli\.{NAME}\b"), rf"\1import core.{NAME}"),
    )
    files = set(ROOT.glob("*.py"))
    for d in SCAN_DIRS:
        files.update((ROOT / d).rglob("*.py"))

    files_changed = 0
    lines_changed = 0
    for path in sorted(files):
        relp = _rel(path)
        if relp.startswith("core/") or relp == f"sparkii_cli/{NAME}.py":
            continue
        if any(part in SKIP for part in path.parts):
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

    print(f"moved {NAME}.py into core/")
    print(f"rewrote {lines_changed} import line(s) across {files_changed} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
