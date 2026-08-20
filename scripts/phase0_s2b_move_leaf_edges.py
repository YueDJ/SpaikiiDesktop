#!/usr/bin/env python3
"""S2b step 2: move the remaining pure-leaf edges of config.py into core.

``default_soul``, ``mcp_security``, ``personality`` and ``secret_prompt`` are
pure-stdlib leaves.  Moving them removes four more of config.py's surface edges,
leaving only ``auth.get_anthropic_key`` and ``managed_scope`` before config.py
itself can move.  Idempotent.
"""

from __future__ import annotations

import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("default_soul", "mcp_security", "personality", "secret_prompt")
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
    patterns = []
    for name in NAMES:
        src = ROOT / "sparkii_cli" / f"{name}.py"
        dst = ROOT / "core" / f"{name}.py"
        if src.exists() and not dst.exists():
            shutil.move(str(src), str(dst))
        (ROOT / "sparkii_cli" / f"{name}.py").write_text(
            f'"""Backward-compatibility shim for ``sparkii_cli.{name}``.\n\n'
            f"Moved into ``core.{name}`` during the Phase 0 trim.  New code should\n"
            f'import from ``core.{name}``.\n'
            '"""\n\n'
            f"from core.{name} import *  # noqa: F401,F403\n",
            encoding="utf-8",
        )
        patterns += [
            (re.compile(rf"^(\s*)from\s+sparkii_cli\.{name}\s+import\b"), rf"\1from core.{name} import"),
            (re.compile(rf"^(\s*)import\s+sparkii_cli\.{name}\b"), rf"\1import core.{name}"),
        ]

    files = set(ROOT.glob("*.py"))
    for d in SCAN_DIRS:
        files.update((ROOT / d).rglob("*.py"))

    files_changed = 0
    lines_changed = 0
    for path in sorted(files):
        relp = _rel(path)
        if relp.startswith("core/") or relp in {f"sparkii_cli/{n}.py" for n in NAMES}:
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
            for attempt in range(5):
                try:
                    with path.open("w", encoding="utf-8", newline="") as fh:
                        fh.write("".join(lines))
                    break
                except OSError:
                    if attempt == 4:
                        raise
                    time.sleep(0.3 * (attempt + 1))
            files_changed += 1
            lines_changed += changed

    print(f"moved {len(NAMES)} file(s) into core/")
    print(f"rewrote {lines_changed} import line(s) across {files_changed} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
