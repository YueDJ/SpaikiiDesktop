#!/usr/bin/env python3
"""Block 4 import-graph scanner: frontend surfaces -> core package cut.

Read-only. Measures the coupling between the six frontend surfaces that must
move to a standalone repo (cli.py, gateway/, ui-tui/, apps/, website/,
acp_adapter/) and the Python core package they will consume as a dependency.

Run:
    .venv/Scripts/python.exe scripts/phase0_block4_scan.py

Outputs:
  * core -> move  : every CORE module importing a MOVE package (the arrows that
                    must be eliminated or inverted before the split).
  * move -> core  : every MOVE module's top-level core imports (the dependency
                    surface the new repo consumes).
  * tests         : test files importing MOVE packages (candidates to move).
  * TS references : TypeScript imports that cross the ui-tui/apps/website
                    boundary in either direction.

It writes nothing (stdout + an optional --csv docs/foundation-block4-scan.csv).
"""

from __future__ import annotations

import ast
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# The cut.  MOVE = frontend surfaces leaving the repo.  Everything else Python
# under ROOT (excluding tests and vendored dirs) is treated as CORE.
# ---------------------------------------------------------------------------
MOVE_TOP = {"cli.py", "gateway", "acp_adapter", "sparkii_cli", "tui_gateway", "apps", "ui-tui", "website"}
TS_MOVE = {"ui-tui", "apps", "website"}

SKIP_DIRS = {
    ".git", ".venv", ".venv-311-broken", "node_modules", "__pycache__", "dist",
    "build", ".next", ".turbo", ".docusaurus", "sparkii_agent.egg-info",
    ".plans", ".github", ".qoder", ".agents", ".codex", "docker", "nix",
    "mcp-research-data", "optional-mcps", "datagen-config-examples", "evals",
    "native", "assets", "locales", "logo-concepts", "tests-js",
    "website",  # TS docs site — not a Python package
}


def iter_py_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in root.walk():
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                out.append(Path(dirpath) / filename)
    return out


def collect_imports(path: Path) -> tuple[set[str], set[str], set[str]]:
    """Return (top_level_roots, nested_roots, all_roots) for one module."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return set(), set(), set()
    top: set[str] = set()
    nested: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            if not node.module:
                continue
            roots = [node.module.split(".")[0]]
        else:
            continue
        (top if node.col_offset == 0 else nested).update(roots)
    return top, nested, top | nested


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def is_move(path: Path) -> bool:
    r = rel(path)
    if r == "cli.py":
        return True
    first = r.split("/", 1)[0]
    return first in {"gateway", "acp_adapter", "sparkii_cli", "tui_gateway", "apps", "ui-tui", "website"}


def is_test(path: Path) -> bool:
    r = rel(path)
    return r.startswith("tests/") or "/tests/" in r


def main() -> int:
    files = iter_py_files(ROOT)
    move_files = [f for f in files if is_move(f)]
    core_files = [f for f in files if not is_move(f) and not is_test(f)]
    test_files = [f for f in files if is_test(f)]

    core_to_move: dict[str, set[str]] = defaultdict(set)   # core file -> move roots
    move_to_core_top: dict[str, set[str]] = defaultdict(set)  # move file -> core roots (top-level)
    move_to_core_all: dict[str, set[str]] = defaultdict(set)  # move file -> core roots (any)
    tests_importing_move: dict[str, set[str]] = defaultdict(set)

    for path in core_files + test_files:
        top, nested, all_roots = collect_imports(path)
        hits = all_roots & MOVE_TOP
        if hits:
            target = core_to_move if path in core_files else tests_importing_move
            target[rel(path)] |= hits

    for path in move_files:
        top, nested, all_roots = collect_imports(path)
        for root in top:
            if root not in MOVE_TOP:
                move_to_core_top[rel(path)].add(root)
        move_to_core_all[rel(path)] |= all_roots - MOVE_TOP

    # -- TS cross-boundary references --------------------------------------
    ts_pat = re.compile(
        r"(?:from\s+['\"]([^'\"]+)['\"]|import\s*\(\s*['\"]([^'\"]+)['\"]\s*\))"
    )
    ts_core_roots = {"@sparkii/shared", "sparkii-shared", "../../../shared", "../../shared"}
    ts_edges: list[tuple[str, str]] = []  # (file, imported specifier)

    def walk_ts(dirname: str) -> None:
        base = ROOT / dirname
        for p in base.rglob("*"):
            if p.is_dir():
                continue
            if p.suffix not in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in ts_pat.finditer(text):
                spec = m.group(1) or m.group(2)
                if not spec:
                    continue
                r = rel(p)
                if dirname == "ui-tui" and ("/apps/" in spec or spec.startswith("apps/") or "@sparkii/shared" in spec):
                    ts_edges.append((r, spec))
                elif dirname in ("apps", "website") and "ui-tui" in spec:
                    ts_edges.append((r, spec))
                elif dirname == "website" and "/apps/" in spec:
                    ts_edges.append((r, spec))

    for d in TS_MOVE:
        walk_ts(d)

    # -- reporting ----------------------------------------------------------
    print("=" * 78)
    print("BLOCK 4 SCAN — frontend surfaces vs core package")
    print("=" * 78)
    print(f"move python files : {len(move_files)}")
    print(f"core python files : {len(core_files)}")
    print(f"test files        : {len(test_files)}")
    print()

    print("-" * 78)
    print("1) CORE -> MOVE offenders (must be eliminated / inverted)")
    print("-" * 78)
    print(f"core files importing move packages: {len(core_to_move)}")
    by_pkg: dict[str, list[str]] = defaultdict(list)
    for cf, roots in sorted(core_to_move.items()):
        for r in sorted(roots):
            by_pkg[r].append(cf)
    for pkg in sorted(by_pkg):
        print(f"\n[{pkg}] {len(by_pkg[pkg])} file(s)")
        for cf in sorted(by_pkg[pkg]):
            print(f"  {cf}")

    print()
    print("-" * 78)
    print("2) MOVE -> CORE top-level imports (consumed surface)")
    print("-" * 78)
    consumed: dict[str, int] = defaultdict(int)
    for mf, roots in sorted(move_to_core_top.items()):
        for root in sorted(roots):
            consumed[root] += 1
    print("top-level core roots consumed by move files:")
    for root in sorted(consumed, key=lambda r: -consumed[r]):
        print(f"  {root:<28} {consumed[root]} file(s)")

    print()
    print("-" * 78)
    print("3) Tests importing move packages (move candidates)")
    print("-" * 78)
    by_pkg_t: dict[str, list[str]] = defaultdict(list)
    for tf, roots in sorted(tests_importing_move.items()):
        for r in sorted(roots):
            by_pkg_t[r].append(tf)
    for pkg in sorted(by_pkg_t):
        print(f"\n[{pkg}] {len(by_pkg_t[pkg])} test file(s)")
        for tf in sorted(by_pkg_t[pkg]):
            print(f"  {tf}")

    print()
    print("-" * 78)
    print("4) TS cross-boundary references")
    print("-" * 78)
    print(f"edges: {len(ts_edges)}")
    for r, spec in sorted(ts_edges)[:80]:
        print(f"  {r:<58} -> {spec}")
    if len(ts_edges) > 80:
        print(f"  ... {len(ts_edges) - 80} more")

    if "--csv" in sys.argv:
        out = ROOT / "docs" / "foundation-block4-scan.csv"
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["kind", "source", "target"])
            for cf, roots in sorted(core_to_move.items()):
                for r in sorted(roots):
                    w.writerow(["core_to_move", cf, r])
            for mf, roots in sorted(move_to_core_all.items()):
                for r in sorted(roots):
                    w.writerow(["move_to_core", mf, r])
            for tf, roots in sorted(tests_importing_move.items()):
                for r in sorted(roots):
                    w.writerow(["test_to_move", tf, r])
            for r, spec in sorted(ts_edges):
                w.writerow(["ts_edge", r, spec])
        print(f"\ncsv -> {rel(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
