#!/usr/bin/env python3
"""S2b: extract the provider registry cluster into core/provider_registry.py.

Uses a transitive-constant closure so every module-level constant referenced by
``ProviderConfig`` + ``PROVIDER_REGISTRY`` + its plugin loop moves with it, but
OAuth-flow-only constants (and the ``sparkii_cli.__version__`` user-agent lookup)
stay in auth.py.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "sparkii_cli" / "auth.py"
DST = ROOT / "core" / "provider_registry.py"

HEADER = '''"""Provider metadata registry for Sparkii core.

Extracted verbatim from ``sparkii_cli.auth`` during the Phase 0 trim.  Holds
``ProviderConfig``, the ``PROVIDER_REGISTRY`` dict, the OAuth/base-URL constants
the registry references, and the plugin-provider dynamic registration loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict
from urllib.parse import urlparse

from core.auth_store import DEFAULT_NOUS_PORTAL_URL


'''


def _name(node: ast.stmt) -> str | None:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                return t.id
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def _referenced_names(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
            out.add(sub.id)
    return out


def main() -> int:
    src = AUTH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)

    # Constants defined at module level.
    const_nodes: dict[str, ast.stmt] = {}
    for node in tree.body:
        n = _name(node)
        if n and n.isupper():
            const_nodes[n] = node

    # Locate ProviderConfig and PROVIDER_REGISTRY.
    provider_config = None
    registry = None
    for i, node in enumerate(tree.body):
        if isinstance(node, ast.ClassDef) and node.name == "ProviderConfig":
            provider_config = (i, node)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "PROVIDER_REGISTRY":
            registry = (i, node)
    if provider_config is None or registry is None:
        print("could not locate ProviderConfig / PROVIDER_REGISTRY")
        return 1

    # The plugin loop is the statement right after PROVIDER_REGISTRY.
    reg_idx = registry[0]
    plugin_loop = tree.body[reg_idx + 1] if reg_idx + 1 < len(tree.body) else None
    if plugin_loop is None or not isinstance(plugin_loop, ast.Try):
        print("could not locate plugin loop after PROVIDER_REGISTRY")
        return 1

    # Transitive closure of referenced constants.
    seeds = (
        _referenced_names(provider_config[1])
        | _referenced_names(registry[1])
        | _referenced_names(plugin_loop)
    )
    needed: set[str] = set()
    stack = [n for n in seeds if n in const_nodes]
    while stack:
        n = stack.pop()
        if n in needed:
            continue
        needed.add(n)
        stack.extend(x for x in _referenced_names(const_nodes[n]) if x in const_nodes)

    # Build spans in source order: constants, then ProviderConfig, registry, loop.
    spans: list[tuple[int, int]] = []
    for n in sorted(needed, key=lambda x: const_nodes[x].lineno):
        node = const_nodes[n]
        spans.append((node.lineno, node.end_lineno))
    spans.append((provider_config[1].lineno, provider_config[1].end_lineno))
    spans.append((registry[1].lineno, registry[1].end_lineno))
    spans.append((plugin_loop.lineno, plugin_loop.end_lineno))
    spans.sort()

    # Merge overlapping/adjacent spans to avoid double-emit.
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

    # Rewrite auth.py: drop spans, re-export the moved public names.
    new_lines = list(lines)
    for lo, hi in reversed(merged):
        del new_lines[lo - 1 : hi]
    names = ["ProviderConfig", "PROVIDER_REGISTRY"] + sorted(needed)
    reexport = "from core.provider_registry import (\n    " + ",\n    ".join(names) + ",\n)\n\n"
    new_lines.insert(merged[0][0] - 1, reexport)
    AUTH.write_text("".join(new_lines), encoding="utf-8")

    print(f"moved {len(needed)} constant(s) + ProviderConfig + PROVIDER_REGISTRY + plugin loop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
