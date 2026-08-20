#!/usr/bin/env python3
"""M1: extract the clean provider-resolution core out of models.py.

Only the six self-contained symbols move (provider groups + provider-slug
canonicalization).  They import nothing from sparkii_cli surface packages.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "sparkii_cli" / "models.py"
DST = ROOT / "core" / "model_resolution.py"

SEEDS = ["normalize_provider", "_PROVIDER_ALIASES", "provider_group_for_slug", "group_providers"]

HEADER = '''"""Provider identity resolution (core).

Extracted verbatim from ``sparkii_cli.models`` during the Phase 0 trim.  Holds
provider grouping and provider-slug canonicalization only.  Catalog fetching and
provider detection remain in ``sparkii_cli.models``.
"""

from __future__ import annotations

from typing import Dict, List, Optional


'''


def _name(node: ast.stmt) -> str | None:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                return t.id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    if isinstance(node, ast.FunctionDef):
        return node.name
    return None


def _refs(node: ast.AST) -> set[str]:
    return {s.id for s in ast.walk(node) if isinstance(s, ast.Name) and isinstance(s.ctx, ast.Load)}


def main() -> int:
    src = MODELS.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)

    defs: dict[str, ast.stmt] = {}
    for n in tree.body:
        name = _name(n)
        if name:
            defs[name] = n

    closure: set[str] = set()
    stack = list(SEEDS)
    while stack:
        n = stack.pop()
        if n in closure or n not in defs:
            continue
        closure.add(n)
        stack.extend(x for x in _refs(defs[n]) if x in defs)

    spans = sorted((defs[n].lineno, defs[n].end_lineno) for n in closure)
    merged: list[list[int]] = []
    for lo, hi in spans:
        if merged and lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])

    body: list[str] = []
    for lo, hi in merged:
        body.extend(lines[lo - 1 : hi])
        body.append("\n")
    DST.write_text(HEADER + "".join(body), encoding="utf-8")

    new_lines = list(lines)
    for lo, hi in reversed(merged):
        del new_lines[lo - 1 : hi]
    names = sorted(closure)
    reexport = "from core.model_resolution import (\n    " + ",\n    ".join(names) + ",\n)\n\n"
    new_lines.insert(merged[0][0] - 1, reexport)
    MODELS.write_text("".join(new_lines), encoding="utf-8")

    print(f"extracted {len(closure)} symbol(s) into core/model_resolution.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
