#!/usr/bin/env python3
"""S2d follow-up: redirect mock patches for the moved model-cache symbols.

``_load_provider_models_cache`` / ``_save_provider_models_cache`` /
``clear_provider_models_cache`` / ``_provider_models_cache_path`` now live in
``sparkii_cli.models``.  Tests that patch them by their old location must
target ``sparkii_cli.models`` or the patch silently no-ops.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    "_load_provider_models_cache",
    "_save_provider_models_cache",
    "clear_provider_models_cache",
    "_provider_models_cache_path",
)
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
    files = set(ROOT.glob("*.py"))
    for d in SCAN_DIRS:
        files.update((ROOT / d).rglob("*.py"))

    changed_files = 0
    for path in sorted(files):
        relp = _rel(path)
        if relp.startswith("core/"):
            continue
        if any(part in SKIP for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError):
            continue
        new = text
        for name in NAMES:
            # string-form patch / monkeypatch
            new = new.replace(f'sparkii_cli.models.{name}', f'sparkii_cli.models.{name}')
            # patch.object(<alias>, "name") -> patch.object(sparkii_cli.models, "name")
            new = re.sub(
                rf'patch\.object\(\s*\w+\s*,\s*["\']{re.escape(name)}["\']',
                f'patch.object(sparkii_cli.models, "{name}"',
                new,
            )
            # monkeypatch.setattr(<alias>, "name" -> monkeypatch.setattr(sparkii_cli.models, "name"
            new = re.sub(
                rf'monkeypatch\.setattr\(\s*\w+\s*,\s*["\']{re.escape(name)}["\']',
                f'monkeypatch.setattr(sparkii_cli.models, "{name}"',
                new,
            )
        if new != text:
            # ensure import exists
            if "import sparkii_cli.models" not in new:
                new = "import sparkii_cli.models\n" + new
            for attempt in range(5):
                try:
                    path.write_text(new, encoding="utf-8")
                    break
                except OSError:
                    if attempt == 4:
                        raise
                    import time
                    time.sleep(0.3 * (attempt + 1))
            changed_files += 1

    print(f"rewrote {changed_files} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
