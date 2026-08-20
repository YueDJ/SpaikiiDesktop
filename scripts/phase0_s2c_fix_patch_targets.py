#!/usr/bin/env python3
"""S2c follow-up: rewrite remaining ``sparkii_cli.<config-group>`` string references
(mock patch targets, comments, docstrings) to ``core.<...>`` after the move.

Import lines were already rewritten by phase0_s2c_move_config_group.py; this pass
handles everything else that still spells the old path.  Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLACEMENTS = (
    ("core.config_migrations", "core.config_migrations"),
    ("core.config_defaults", "core.config_defaults"),
    ("core.credential_lifecycle", "core.credential_lifecycle"),
    ("core.managed_scope", "core.managed_scope"),
    ("core.config", "core.config"),
)
SCAN_DIRS = (
    "agent", "tools", "gateway", "sparkii_cli", "tui_gateway", "acp_adapter",
    "cron", "providers", "plugins", "scripts", "tests",
)
SKIP = {"node_modules", ".venv", "__pycache__", "dist", "build", ".git"}
SKIP_REL = {"core", "sparkii_cli/config.py", "sparkii_cli/config_migrations.py",
            "sparkii_cli/credential_lifecycle.py", "sparkii_cli/managed_scope.py"}


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def main() -> int:
    files = set(ROOT.glob("*.py"))
    for d in SCAN_DIRS:
        files.update((ROOT / d).rglob("*.py"))
    files_changed = lines_changed = 0
    for path in sorted(files):
        relp = _rel(path)
        if relp in SKIP_REL or relp.startswith("core/"):
            continue
        if any(part in SKIP for part in path.parts):
            continue
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                text = fh.read()
        except (UnicodeDecodeError, OSError):
            continue
        new = text
        for old, newval in REPLACEMENTS:
            new = new.replace(old, newval)
        if new != text:
            for attempt in range(5):
                try:
                    with path.open("w", encoding="utf-8", newline="") as fh:
                        fh.write(new)
                    break
                except OSError:
                    if attempt == 4:
                        raise
                    import time
                    time.sleep(0.3 * (attempt + 1))
            files_changed += 1
            lines_changed += new.count("\n") - text.count("\n")
    print(f"rewrote {files_changed} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
