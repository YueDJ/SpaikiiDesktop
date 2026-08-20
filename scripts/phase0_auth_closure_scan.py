#!/usr/bin/env python3
"""Closure graph for sparkii_cli/auth.py: transitive closure from external roots."""
from __future__ import annotations
import ast, re, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "sparkii_cli" / "auth.py"

def top_level_nodes(src):
    return ast.parse(src).body

def top_names(src):
    out = {}
    for node in top_level_nodes(src):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    out[t.id] = node
    return out

def body_text(src, node):
    lines = src.splitlines(keepends=True)
    start = node.lineno - 1
    end = node.end_lineno
    return "".join(lines[start:end])

def referenced_names(src, node):
    """Names referenced in a node that are top-level names of the module."""
    try:
        subtree = ast.parse(body_text(src, node))
    except SyntaxError:
        return set()
    used = set()
    for n in ast.walk(subtree):
        if isinstance(n, ast.Name):
            used.add(n.id)
    return used

def main():
    src = AUTH.read_text(encoding="utf-8")
    names = top_names(src)
    # external roots (from the import scan)
    roots = set(sys.argv[1:]) if len(sys.argv) > 1 else set()
    graph = {name: referenced_names(src, node) & set(names) for name, node in names.items()}
    # transitive closure
    closure = set(roots)
    changed = True
    while changed:
        changed = False
        for name in list(closure):
            for dep in graph.get(name, ()):
                if dep not in closure:
                    closure.add(dep)
                    changed = True
    dead = set(names) - closure
    print(f"module names: {len(names)}")
    print(f"external roots: {sorted(roots)}")
    print(f"closure size: {len(closure)}")
    print("\n== CLOSURE (move to core/credentials) ==")
    print(" ".join(sorted(closure)))
    print("\n== DEAD / NOT-IN-CLOSURE ==")
    print(" ".join(sorted(dead)))

if __name__ == "__main__":
    main()
