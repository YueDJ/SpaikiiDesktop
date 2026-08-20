#!/usr/bin/env python3
"""S2c: move the config cluster (config / config_migrations / credential_lifecycle
/ managed_scope) from sparkii_cli into core/.

The four modules move together because they import each other.  Backward-compat
shims re-export the full public + private API.  ``credential_lifecycle`` keeps a
single lazy, best-effort ``sparkii_cli.models`` import (clearing a provider model
cache) as a documented temporary edge to invert later.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("config", "config_migrations", "credential_lifecycle", "managed_scope")
SCAN_DIRS = (
    "agent", "tools", "gateway", "sparkii_cli", "tui_gateway", "acp_adapter",
    "cron", "providers", "plugins", "scripts", "tests",
)
SKIP = {"node_modules", ".venv", "__pycache__", "dist", "build", ".git"}

# Ordered: more-specific module names before the bare ``config``.
_DOTTED = (
    ("core.config_migrations", "core.config_migrations"),
    ("core.config_defaults", "core.config_defaults"),
    ("core.credential_lifecycle", "core.credential_lifecycle"),
    ("core.managed_scope", "core.managed_scope"),
    ("core.config", "core.config"),
)
_FROM_IMPORT = (
    ("from sparkii_cli import config", "from core import config"),
    ("from sparkii_cli import managed_scope", "from core import managed_scope"),
)


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _shim_text(name: str) -> str:
    return (
        f'"""Backward-compatibility shim for ``sparkii_cli.{name}``.\n\n'
        f'Moved into ``core.{name}`` during the Phase 0 trim.  Re-exports the full\n'
        f'public + private API so existing importers keep working.\n'
        '"""\n\n'
        f'import core.{name} as _impl\n\n'
        'globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})\n'
    )


def main() -> int:
    moved = 0
    for name in NAMES:
        src = ROOT / "sparkii_cli" / f"{name}.py"
        dst = ROOT / "core" / f"{name}.py"
        if src.exists() and not dst.exists():
            shutil.move(str(src), str(dst))
            moved += 1
        (ROOT / "sparkii_cli" / f"{name}.py").write_text(_shim_text(name), encoding="utf-8")

    files = set(ROOT.glob("*.py"))
    for d in SCAN_DIRS:
        files.update((ROOT / d).rglob("*.py"))

    files_changed = lines_changed = 0
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
            stripped = new.lstrip()
            if stripped.startswith("from ") or stripped.startswith("import "):
                for old, newval in _DOTTED:
                    new = new.replace(old, newval)
                for old, newval in _FROM_IMPORT:
                    new = re.sub(rf"{re.escape(old)}\b", newval, new)
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
                    import time
                    time.sleep(0.3 * (attempt + 1))
            files_changed += 1
            lines_changed += changed

    print(f"moved {moved} module(s) into core/")
    print(f"rewrote {lines_changed} import line(s) across {files_changed} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
