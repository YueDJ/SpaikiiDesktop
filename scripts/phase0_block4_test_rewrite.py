#!/usr/bin/env python3
"""Block 4 Step 2: point test patch/import targets at the moved core modules.

After the service modules moved from sparkii_cli/ to core/, tests that patch
or import them must target ``core.<name>`` so test doubles are seen by core
consumers (the established convention from Blocks 1-3).  Only the moved
module names are rewritten; surface tests keep working through the shims.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MOVED = [
    "approval_transport", "copilot_auth", "projects_db", "managed_uv",
    "providers", "middleware", "lifecycle", "model_catalog", "model_normalize",
    "model_switch", "models", "heartbeat", "loops", "profiles", "goals",
    "kanban_db", "runtime_provider", "inventory", "platforms", "tools_config",
    "prompt_size", "resource_limits", "kanban_diagnostics", "kanban_specify",
    "kanban_decompose", "profile_describer", "memory_setup", "observability",
]


def main() -> int:
    changed = 0
    for p in sorted((ROOT / "tests").rglob("*.py")):
        text = p.read_text(encoding="utf-8")
        original = text
        for name in MOVED:
            text = text.replace(f"sparkii_cli.{name}", f"core.{name}")
            text = text.replace(
                f"from sparkii_cli import {name}",
                f"from core import {name}",
            )
            text = text.replace(
                f"import sparkii_cli.{name}",
                f"import core.{name}",
            )
        if text != original:
            p.write_text(text, encoding="utf-8")
            changed += 1
    print(f"updated {changed} test files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
