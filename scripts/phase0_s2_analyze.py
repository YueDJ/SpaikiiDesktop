#!/usr/bin/env python3
"""S2 pre-flight: map the dependency surface of the sparkii_cli service layer.

Read-only.  Before moving the 21 S2 service modules into ``core/`` we must know
exactly (a) which ``sparkii_cli`` submodules the core actually imports, and
(b) what the S2 modules themselves import from ``sparkii_cli`` (both each other
and any surface module that must NOT come along).
"""

from __future__ import annotations

import ast
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

S2_FILES = {
    "env_loader.py", "timeouts.py", "timefmt.py", "profiles.py",
    "config.py", "config_defaults.py", "config_migrations.py",
    "models.py", "model_catalog.py", "model_normalize.py",
    "codex_models.py", "fallback_config.py", "build_info.py",
    "sqlite_runtime.py", "sqlite_util.py", "sqlite_safe_read.py",
    "tools_config.py", "toolset_validation.py", "credential_lifecycle.py",
    "route_identity.py", "runtime_provider.py",
}

CORE_DIRS = ("agent", "tools", "providers", "core")
CORE_TOP_FILES = {
    "run_agent.py", "model_tools.py", "toolsets.py", "toolset_distributions.py",
    "batch_runner.py", "registration_lifecycle.py",
    "sparkii_state.py", "sparkii_state_common.py", "sparkii_state_portability.py",
    "sparkii_state_schema.py", "sparkii_state_search.py",
    "sparkii_constants.py", "sparkii_logging.py", "sparkii_time.py", "utils.py",
    "trajectory_compressor.py",
}
SKIP_DIRS = {
    ".git", ".venv", ".venv-311-broken", "node_modules", "__pycache__", "dist",
    "build", ".next", ".turbo", ".qoder", "tests", "tests-js", "website", "evals",
    "native", "assets", "contributors", "locales", "logo-concepts", ".plans",
    ".github", ".agents", ".codex", "docker", "nix", "mcp-research-data",
    "optional-mcps", "datagen-config-examples", "sparkii_agent.egg-info",
}


def iter_py(root: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                out.append(Path(dirpath) / fn)
    return out


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def collect(path: Path) -> list[tuple[str, str]]:
    """Return list of (module_path, symbols) for absolute imports in *path*."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    out: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.append((a.name, ""))
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            syms = ",".join(a.name for a in node.names)
            out.append((node.module, syms))
    return out


def is_core(path: Path) -> bool:
    r = rel(path)
    return r in CORE_TOP_FILES or r.split("/", 1)[0] in CORE_DIRS


def main() -> int:
    # (a) what the 21 S2 modules import from sparkii_cli (each other vs S7).
    print("=" * 78)
    print("S2 modules: their own sparkii_cli imports")
    print("=" * 78)
    for fn in sorted(S2_FILES):
        p = ROOT / "sparkii_cli" / fn
        if not p.exists():
            print(f"  {fn}: MISSING")
            continue
        deps = []
        for mod, syms in collect(p):
            if mod.startswith("sparkii_cli"):
                sub = mod[len("sparkii_cli."):] if mod != "sparkii_cli" else "(pkg root)"
                kind = "S2" if (sub + ".py") in S2_FILES else "S7"
                deps.append(f"{kind}:{mod}:{syms}" if syms else f"{kind}:{mod}")
        if deps:
            print(f"\n  {fn}:")
            for d in sorted(set(deps)):
                print(f"    - {d}")
        else:
            print(f"\n  {fn}: (no sparkii_cli imports)")

    # (b) which sparkii_cli submodules the whole core imports.
    print()
    print("=" * 78)
    print("core -> sparkii_cli.<submodule> map")
    print("=" * 78)
    hits: dict[str, set[str]] = defaultdict(set)
    for p in iter_py(ROOT):
        if not is_core(p):
            continue
        r = rel(p)
        for mod, _ in collect(p):
            if mod == "sparkii_cli" or mod.startswith("sparkii_cli."):
                hits[mod].add(r)
    for mod in sorted(hits):
        sub = mod.split(".", 1)[1] if "." in mod else "(pkg root)"
        kind = "S2" if (sub + ".py") in S2_FILES else "S7"
        files = sorted(hits[mod])
        print(f"\n{kind}  {mod}  ({len(files)} files)")
        for f in files:
            print(f"    {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
