#!/usr/bin/env python3
"""Block 4 Step 2 helper: sink sparkii_cli service modules into core/.

For each module in ``MOVE``: copies ``sparkii_cli/<mod>.py`` to
``core/<mod>.py`` (applying the per-module import rewrite table so the moved
file only depends on core), then replaces ``sparkii_cli/<mod>.py`` with a
``__getattr__`` forwarding shim so surface-side callers keep working.

Usage:
    .venv/Scripts/python.exe scripts/phase0_block4_sink.py

This performs mechanical file moves + text rewrites only; every moved module
must then be import-verified individually.  Bespoke surgery (provider hooks,
dead-code removal) is done by hand in follow-up edits.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (module, [ (old_substring, new_substring), ... ])
MOVE: dict[str, list[tuple[str, str]]] = {
    "approval_transport": [],
    "copilot_auth": [],
    "projects_db": [],
    "managed_uv": [],
    "providers": [],
    "middleware": [
        ("from sparkii_cli.plugins import", "from core.plugins import"),
    ],
    "model_catalog": [
        (
            "from sparkii_cli import __version__ as _SPARKII_VERSION",
            "from core.version import __version__ as _SPARKII_VERSION",
        ),
    ],
    "model_normalize": [
        ("from sparkii_cli.models import", "from core.models import"),
    ],
    "model_switch": [
        ("from sparkii_cli.providers import", "from core.providers import"),
        ("from sparkii_cli.model_normalize import", "from core.model_normalize import"),
    ],
    "heartbeat": [
        ("from sparkii_cli.goals import", "from core.goals import"),
    ],
    "loops": [
        ("from sparkii_cli.goals import", "from core.goals import"),
    ],
    "profiles": [
        (
            '        from gateway.status import get_running_pid\n'
            '        if (\n'
            '            get_running_pid(profile_dir / "gateway.pid", cleanup_stale=False)\n'
            '            is not None\n'
            '        ):\n'
            '            return True\n'
            '    except Exception:\n'
            '        pass\n'
            '    try:\n'
            '        from gateway.status import (\n'
            '            get_runtime_status_running_pid,\n'
            '            read_runtime_status,\n'
            '        )\n'
            '        runtime = read_runtime_status(profile_dir / "gateway_state.json")\n'
            '        return get_runtime_status_running_pid(runtime, expected_home=profile_dir) is not None\n'
            '    except Exception:\n'
            '        return False',
            '        from core.process_utils import is_profile_gateway_live\n'
            '        return is_profile_gateway_live(profile_dir)\n'
            '    except Exception:\n'
            '        return False',
        ),
        ("from gateway.status import _pid_exists, terminate_pid as _terminate_pid", "from core.process_utils import _pid_exists, terminate_pid as _terminate_pid"),
        ("from gateway.status import terminate_pid as _terminate_pid", "from core.process_utils import terminate_pid as _terminate_pid"),
        ("from gateway.status import _pid_exists", "from core.process_utils import _pid_exists"),
    ],
    "goals": [
        ("from gateway.status import _pid_exists", "from core.process_utils import _pid_exists"),
    ],
    "kanban_db": [
        ("from sparkii_cli.lifecycle import", "from core.lifecycle import"),
        ("from sparkii_cli.profiles import", "from core.profiles import"),
        ("from sparkii_cli import projects_db as _pdb", "from core import projects_db as _pdb"),
        ("from cli import _worktree_has_unpushed_commits, _worktree_is_dirty", "from core.git_worktree import _worktree_has_unpushed_commits, _worktree_is_dirty"),
        ("from gateway.status import _pid_exists", "from core.process_utils import _pid_exists"),
    ],
    "runtime_provider": [
        ("from sparkii_cli import auth as auth_mod", "import core.credentials as auth_mod"),
        ("from sparkii_cli.providers import", "from core.providers import"),
    ],
    "models": [
        (
            "from sparkii_cli import __version__ as _SPARKII_VERSION",
            "from core.version import __version__ as _SPARKII_VERSION",
        ),
        ("from sparkii_cli.copilot_auth import", "from core.copilot_auth import"),
        ("from sparkii_cli.model_catalog import", "from core.model_catalog import"),
        ("from sparkii_cli.model_switch import", "from core.model_switch import"),
        ("from sparkii_cli.providers import", "from core.providers import"),
    ],
    "inventory": [
        ("from sparkii_cli.model_switch import", "from core.model_switch import"),
        ("from sparkii_cli.providers import", "from core.providers import"),
        ("from sparkii_cli.models import", "from core.models import"),
    ],
    "platforms": [
        (
            "from gateway.platform_registry import platform_registry",
            "from core.plugins import get_platform_registry\n"
            "        platform_registry = get_platform_registry()",
        ),
    ],
    "tools_config": [
        ("from sparkii_cli.platforms import", "from core.platforms import"),
    ],
    "prompt_size": [
        ("from sparkii_cli.tools_config import", "from core.tools_config import"),
    ],
    "resource_limits": [],
    "kanban_diagnostics": [],
    "kanban_specify": [
        ("from sparkii_cli import kanban_db as kb", "from core import kanban_db as kb"),
    ],
    "kanban_decompose": [
        ("from sparkii_cli import kanban_db as kb", "from core import kanban_db as kb"),
        ("from sparkii_cli import profiles as profiles_mod", "from core import profiles as profiles_mod"),
    ],
    "profile_describer": [
        ("from sparkii_cli import profiles as profiles_mod", "from core import profiles as profiles_mod"),
    ],
    "memory_setup": [
        ("from sparkii_cli.tools_config import", "from core.tools_config import"),
    ],
}

# Whole subpackages to move: (src_dir, dst_dir, [rewrites])
PACKAGE_MOVE: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "sparkii_cli/observability",
        "core/observability",
        [
            (
                "from sparkii_cli import __version__",
                "from core.version import __version__",
            ),
        ],
    ),
]


def shim_for(name: str) -> str:
    return f'''"""CLI-facing shim for :mod:`core.{name}`.

The implementation moved to core during the Phase 0 foundation trim
(Block 4 Step 2).  This module re-exports the core module so existing surface
imports and tests keep working; new code should import from ``core.{name}``
directly.
"""

from __future__ import annotations

import core.{name} as _core_mod


def __getattr__(name):
    """Forward any attribute to the core module."""
    return getattr(_core_mod, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_core_mod)))
'''


def main() -> int:
    for name, rewrites in MOVE.items():
        src = ROOT / "sparkii_cli" / f"{name}.py"
        dst = ROOT / "core" / f"{name}.py"
        if not src.exists():
            print(f"SKIP {name}: source missing")
            continue
        text = src.read_text(encoding="utf-8")
        if "CLI-facing shim for :mod:`core." in text:
            print(f"SKIP {name}: source is already a shim (refusing to clobber)")
            continue
        for old, new in rewrites:
            if old not in text:
                print(f"WARN {name}: rewrite target not found: {old[:60]!r}")
            text = text.replace(old, new)
        dst.write_text(
            f"# Moved from sparkii_cli/{name}.py during the Block 4 split; "
            f"the CLI module is now a shim over this file.\n\n" + text,
            encoding="utf-8",
        )
        src.write_text(shim_for(name), encoding="utf-8")
        print(f"MOVED {name} ({len(text.splitlines())} lines)")
    for src_dir, dst_dir, rewrites in PACKAGE_MOVE:
        src = ROOT / src_dir
        dst = ROOT / dst_dir
        if not src.is_dir():
            print(f"SKIP package {src_dir}: missing")
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for py in sorted(src.glob("*.py")):
            text = py.read_text(encoding="utf-8")
            if "shim" in text[:300].lower() and ("core." in text[:300]):
                continue
            for old, new in rewrites:
                text = text.replace(old, new)
            (dst / py.name).write_text(text, encoding="utf-8")
            print(f"MOVED {src_dir}/{py.name}")
        # Replace the source package with sys.modules-alias shims.
        for py in sorted(src.glob("*.py")):
            if py.name == "__init__.py":
                py.write_text(
                    _package_shim_init(src_dir, dst_dir),
                    encoding="utf-8",
                )
            else:
                py.write_text(_package_shim_module(py.stem, dst_dir), encoding="utf-8")
            print(f"SHIMMED {src_dir}/{py.name}")
    return 0


def _package_shim_init(src_dir: str, dst_dir: str) -> str:
    rel = dst_dir.replace("/", ".")
    return f'''"""Shim package for :mod:`{rel}` (Block 4 split).

The implementation moved to core; this package aliases the core submodules so
existing surface imports keep working.
"""

from __future__ import annotations

import sys

import {rel} as _core_pkg

sys.modules[__name__] = _core_pkg
'''


def _package_shim_module(name: str, dst_dir: str) -> str:
    rel = f"{dst_dir.replace('/', '.')}.{name}"
    return f'''"""Shim for :mod:`{rel}` (Block 4 split)."""

from __future__ import annotations

import sys

import {rel} as _core_mod

sys.modules[__name__] = _core_mod
'''


if __name__ == "__main__":
    sys.exit(main())
