#!/usr/bin/env python3
"""One-off repair for the Block 4 Step 2 sink: strip the duplicated header and
fix the profiles try/except block produced by the first script run."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODS = [
    "approval_transport", "copilot_auth", "projects_db", "managed_uv",
    "providers", "middleware", "model_catalog", "model_normalize",
    "model_switch", "heartbeat", "loops", "profiles", "goals", "kanban_db",
    "runtime_provider",
]

MARKER = '"""Core-owned module (moved from sparkii_cli during the Block 4 split).'


def main() -> int:
    for name in MODS:
        p = ROOT / "core" / f"{name}.py"
        text = p.read_text(encoding="utf-8")
        if text.startswith(MARKER):
            end = text.index('"""', len(MARKER))
            text = text[end + 3:].lstrip("\n")
        if name == "profiles":
            old = (
                "    try:\n"
                "        from core.process_utils import is_profile_gateway_live\n"
                "        return is_profile_gateway_live(profile_dir)\n"
            )
            new = old + "    except Exception:\n        return False\n"
            if old in text and new not in text:
                text = text.replace(old, new, 1)
        p.write_text(text, encoding="utf-8")
        print(f"repaired {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
