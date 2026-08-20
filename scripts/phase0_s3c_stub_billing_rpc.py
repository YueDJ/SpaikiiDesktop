#!/usr/bin/env python3
"""Stub the TUI billing/subscription RPC handlers after the Nous product removal."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "tui_gateway" / "methods_session.py"

METHODS = (
    "billing.state",
    "usage.bars",
    "subscription.state",
    "subscription.preview",
    "subscription.change",
    "subscription.resume",
    "subscription.upgrade",
    "billing.charge",
    "billing.charge_status",
    "billing.auto_reload",
    "billing.step_up",
)


def method_name(node):
    for d in node.decorator_list:
        if (
            isinstance(d, ast.Call)
            and getattr(d.func, "id", "") == "method"
            and d.args
            and isinstance(d.args[0], ast.Constant)
        ):
            return d.args[0].value
    return None


def main():
    text = P.read_text(encoding="utf-8")
    tree = ast.parse(text)
    offs = [0]
    for line in text.splitlines(keepends=True):
        offs.append(offs[-1] + len(line))

    def span(node):
        return (offs[node.lineno - 1], offs[node.end_lineno - 1] + node.end_col_offset)

    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            m = method_name(node)
            if m in METHODS:
                found[m] = span(node)

    items = sorted(found.items(), key=lambda kv: kv[1][0])
    if not items:
        print("no billing handlers found")
        return 1
    first_start = items[0][1][0]
    last_end = items[-1][1][1]

    stubs = []
    for m, _sp in items:
        stubs.append(
            '@method(%r)\n'
            'def _(rid, params):\n'
            '    return _ok(rid, {"ok": False, "error": "removed", '
            '"message": "Nous billing was removed with the Nous product line."})\n'
            "\n\n" % (m,)
        )
    new_text = text[:first_start] + "".join(stubs) + text[last_end:]
    ast.parse(new_text)
    P.write_text(new_text, encoding="utf-8")
    print("stubbed %d handlers" % len(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
