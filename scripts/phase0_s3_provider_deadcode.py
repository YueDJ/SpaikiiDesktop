#!/usr/bin/env python3
"""Phase 0 S3: strip baked-in entries for deleted inference providers.

Block A of the provider trim.  Removes *data entries* (dict keys/values,
set members, list items) that reference providers whose plugin directories
were deleted, from the files listed in docs/foundation-trim-todo.md.

Deletion is AST-anchored: each removed span runs from the entry's start
through its value end (plus the trailing comma), so multi-line dict blocks
and single-line set members are both handled without touching other code.

    .venv/Scripts/python.exe scripts/phase0_s3_provider_deadcode.py [--dry-run]

Always re-validates every edited file with ast.parse before writing.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Deleted provider identities.
#
# Canonical ids and alias targets of the 34 deleted plugins/
# model-providers/ directories, plus OAuth/vendor identities that only
# existed to serve those providers (xai-oauth, minimax-oauth, minimax-cn,
# opencode-go, kimi-coding-cn, commandcode-anthropic) and the vendor slugs
# used by deleted families in model-alias tables.
# ---------------------------------------------------------------------------
DELETED_PROVIDERS: frozenset[str] = frozenset({
    # deleted plugin dirs (canonical ids)
    "actual", "ai-gateway", "alibaba", "alibaba-coding-plan", "arcee",
    "azure-foundry", "bedrock", "commandcode", "copilot", "copilot-acp",
    "deepinfra", "deepseek", "fireworks", "gemini", "gmi", "huggingface",
    "kilocode", "kimi-coding", "meta-ai", "minimax", "nous", "novita",
    "nvidia", "ollama-cloud", "openai-codex", "opencode-zen", "openrouter",
    "qwen-oauth", "stepfun", "upstage", "vertex", "xai", "xiaomi", "zai",
    # ids registered by deleted plugins / OAuth flows
    "commandcode-anthropic", "kimi-coding-cn", "minimax-cn", "minimax-oauth",
    "opencode-go", "xai-oauth",
    # alias targets of deleted providers
    "github-copilot", "kimi-for-coding", "vercel",
    # models.dev canonical ids whose plugins were deleted
    "kilo", "opencode",
    # vendor slugs that only map to deleted families
    "dashscope", "google", "meta-llama", "moonshot", "moonshotai", "qwen",
    "x-ai", "z-ai",
})

# Env vars owned by deleted providers (OPTIONAL_ENV_VARS + doctor hints).
DELETED_ENV_KEYS: frozenset[str] = frozenset({
    "ACTUAL_API_KEY", "ACTUAL_BASE_URL",
    "AI_GATEWAY_API_KEY", "AI_GATEWAY_BASE_URL",
    "AWS_PROFILE", "AWS_REGION",
    "AZURE_FOUNDRY_API_KEY", "AZURE_FOUNDRY_BASE_URL",
    "COMMANDCODE_API_KEY",
    "DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL",
    "DEEPINFRA_API_KEY",
    "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL",
    "FIREWORKS_API_KEY",
    "GEMINI_API_KEY", "GEMINI_BASE_URL", "GLM_API_KEY", "GLM_BASE_URL",
    "GOOGLE_API_KEY",
    "GMI_API_KEY", "GMI_BASE_URL",
    "HF_BASE_URL", "HF_TOKEN",
    "KILOCODE_API_KEY",
    "KIMI_API_KEY", "KIMI_BASE_URL", "KIMI_CN_API_KEY",
    "MINIMAX_API_KEY", "MINIMAX_BASE_URL", "MINIMAX_CN_API_KEY",
    "MINIMAX_CN_BASE_URL",
    "NOUS_API_KEY", "NOUS_BASE_URL",
    "NVIDIA_API_KEY", "NVIDIA_BASE_URL",
    "OLLAMA_API_KEY", "OLLAMA_BASE_URL",
    "OPENCODE_GO_API_KEY", "OPENCODE_GO_BASE_URL",
    "OPENCODE_ZEN_API_KEY", "OPENCODE_ZEN_BASE_URL",
    "OPENROUTER_API_KEY",
    "SPARKII_QWEN_BASE_URL",
    "STEPFUN_API_KEY", "STEPFUN_BASE_URL",
    "UPSTAGE_API_KEY", "UPSTAGE_BASE_URL",
    "VERTEX_CREDENTIALS_PATH",
    "XAI_API_KEY", "XAI_BASE_URL",
    "XIAOMI_API_KEY", "XIAOMI_BASE_URL",
    "ZAI_API_KEY", "Z_AI_API_KEY",
})

# Display labels in doctor.py's static health-check tuple list that belong
# to deleted providers.
DELETED_DOCTOR_LABELS: frozenset[str] = frozenset({
    "Z.AI / GLM", "Kimi / Moonshot", "StepFun Step Plan",
    "Kimi / Moonshot (China)", "GMI Cloud", "DeepSeek", "Hugging Face",
    "NVIDIA NIM", "Alibaba/DashScope", "MiniMax", "MiniMax (China)",
    "Vercel AI Gateway", "Kilo Code", "OpenCode Zen", "OpenCode Go",
})


# ---------------------------------------------------------------------------
# Span collection
#
# Every collector is anchored to a *named assignment* so we only touch the
# data tables Block A targets — never inline logic sets like
# ``if provider in {"copilot", "copilot-acp"}`` or auth-type sets.
# ---------------------------------------------------------------------------

def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _named_assignment(tree: ast.AST, name: str):
    """Yield (target, value) for every assignment to module/function *name*."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    yield node, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name and node.value is not None:
                yield node, node.value


def named_dict(tree: ast.AST, name: str) -> ast.Dict | None:
    for _node, value in _named_assignment(tree, name):
        if isinstance(value, ast.Dict):
            return value
    return None


def named_frozenset_set(tree: ast.AST, name: str) -> ast.Set | None:
    """Return the Set literal inside ``<name>: frozenset({...})``."""
    for _node, value in _named_assignment(tree, name):
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "frozenset"
            and value.args
            and isinstance(value.args[0], ast.Set)
        ):
            return value.args[0]
    return None


def dict_entries_by_key(dct: ast.Dict, names: frozenset[str]):
    for key, value in zip(dct.keys, dct.values):
        if key is not None and _const_str(key) in names:
            yield key, value


def dict_entries_by_value(dct: ast.Dict, names: frozenset[str]):
    for key, value in zip(dct.keys, dct.values):
        if key is not None and _const_str(value) in names:
            yield key, value


def dict_entries_by_call_first_arg(dct: ast.Dict, names: frozenset[str]):
    for key, value in zip(dct.keys, dct.values):
        if key is None or not isinstance(value, ast.Call) or not value.args:
            continue
        if _const_str(value.args[0]) in names:
            yield key, value


def group_entries(dct: ast.Dict, names: frozenset[str]):
    """PROVIDER_GROUPS-style entries: tuples whose trailing list holds slugs."""
    for key, value in zip(dct.keys, dct.values):
        if key is None or not isinstance(value, ast.Tuple) or not value.elts:
            continue
        last = value.elts[-1]
        if not isinstance(last, ast.List):
            continue
        members = [_const_str(el) for el in last.elts]
        deleted = [el for el, m in zip(last.elts, members) if m in names]
        if len(deleted) == len(last.elts):
            yield ("entry", key, value)
        else:
            for el in deleted:
                yield ("member", el, None)


def tuple_members(tup: ast.Tuple, names: frozenset[str]):
    for el in tup.elts:
        if _const_str(el) in names:
            yield el


def set_members(s: ast.Set, names: frozenset[str]):
    for el in s.elts:
        if _const_str(el) in names:
            yield el


def list_tuples_by_first(lst: ast.List, names: frozenset[str]):
    """Yield Tuple elements whose first string element is in *names*."""
    for el in lst.elts:
        if isinstance(el, ast.Tuple) and el.elts and _const_str(el.elts[0]) in names:
            yield el


def list_constants(lst: ast.List, names: frozenset[str]):
    for el in lst.elts:
        if _const_str(el) in names:
            yield el


def subscript_assigns(tree: ast.AST, target_name: str, names: frozenset[str]):
    """Yield Assign statements like ``_PROVIDER_MODELS["ai-gateway"] = ...``."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == target_name
                and _const_str(target.slice) in names
            ):
                yield node


def named_list(tree: ast.AST, name: str) -> ast.List | None:
    for _node, value in _named_assignment(tree, name):
        if isinstance(value, ast.List):
            return value
    return None


def named_tuple(tree: ast.AST, name: str) -> ast.Tuple | None:
    for _node, value in _named_assignment(tree, name):
        if isinstance(value, ast.Tuple):
            return value
    return None


def main_slug_sets(tree: ast.AST, names: frozenset[str]):
    """The api-key provider slug set + --provider fallback list in main.py."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Set, ast.List)):
            for el in node.elts:
                if _const_str(el) in names:
                    yield el


# ---------------------------------------------------------------------------
# Source surgery
# ---------------------------------------------------------------------------

def _abs_offsets(text: str) -> list[int]:
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _span(node: ast.AST) -> tuple[int, int]:
    return (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)


def to_abs(offsets: list[int], span: tuple[int, int, int, int]) -> tuple[int, int]:
    start_line, start_col, end_line, end_col = span
    start = offsets[start_line - 1] + start_col
    end = offsets[end_line - 1] + end_col
    return start, end


def _extend_past_comma(text: str, end: int) -> int:
    """Extend *end* past a trailing comma and the whitespace that follows it."""
    i = end
    n = len(text)
    while i < n and text[i] in " \t":
        i += 1
    if i < n and text[i] == ",":
        i += 1
        while i < n and text[i] in " \t":
            i += 1
        if i < n and text[i] == "\n":
            i += 1
            while i < n and text[i] in " \t":
                i += 1
    return i


def collect_spans(path: Path, tree: ast.AST) -> list[tuple[int, int]]:
    """Collect absolute deletion spans for *path*."""
    spans: list[tuple[int, int]] = []
    text = path.read_text(encoding="utf-8")
    offsets = _abs_offsets(text)

    def add(start_node: ast.AST, end_node: ast.AST) -> None:
        start_line, start_col, _end_line, _end_col = _span(start_node)
        _s_line, _s_col, end_line, end_col = _span(end_node)
        start = offsets[start_line - 1] + start_col
        end = offsets[end_line - 1] + end_col
        end = _extend_past_comma(text, end)
        spans.append((start, end))

    def add_node(node: ast.AST) -> None:
        start, end = to_abs(offsets, _span(node))
        end = _extend_past_comma(text, end)
        spans.append((start, end))

    name = path.name
    if name == "providers.py":
        for dname in ("SPARKII_OVERLAYS", "_LABEL_OVERRIDES"):
            dct = named_dict(tree, dname)
            if dct is not None:
                for key, value in dict_entries_by_key(dct, DELETED_PROVIDERS):
                    add(key, value)
        dct = named_dict(tree, "ALIASES")
        if dct is not None:
            for key, value in dict_entries_by_value(dct, DELETED_PROVIDERS):
                add(key, value)
    elif name == "config_defaults.py":
        dct = named_dict(tree, "OPTIONAL_ENV_VARS")
        if dct is not None:
            for key, value in dict_entries_by_key(dct, DELETED_ENV_KEYS):
                add(key, value)
    elif name == "doctor.py":
        tup = named_tuple(tree, "_PROVIDER_ENV_HINTS")
        if tup is not None:
            for el in tuple_members(tup, DELETED_ENV_KEYS):
                add_node(el)
        dct = named_dict(tree, "_name_to_canonical")
        if dct is not None:
            for key, value in dict_entries_by_value(dct, DELETED_PROVIDERS):
                add(key, value)
        lst = named_list(tree, "_static")
        if lst is not None:
            for el in list_tuples_by_first(lst, DELETED_DOCTOR_LABELS):
                add_node(el)
    elif name == "model_normalize.py":
        dct = named_dict(tree, "_VENDOR_PREFIXES")
        if dct is not None:
            for key, value in dict_entries_by_value(dct, DELETED_PROVIDERS):
                add(key, value)
        for fname in (
            "_AGGREGATOR_PROVIDERS",
            "_DOT_TO_HYPHEN_PROVIDERS",
            "_STRIP_VENDOR_ONLY_PROVIDERS",
            "_AUTHORITATIVE_NATIVE_PROVIDERS",
            "_MATCHING_PREFIX_STRIP_PROVIDERS",
            "_CATALOGUE_PREFIX_REPAIR_PROVIDERS",
            "_LOWERCASE_MODEL_PROVIDERS",
        ):
            s = named_frozenset_set(tree, fname)
            if s is not None:
                for el in set_members(s, DELETED_PROVIDERS):
                    add_node(el)
    elif name == "model_switch.py":
        dct = named_dict(tree, "MODEL_ALIASES")
        if dct is not None:
            for key, value in dict_entries_by_call_first_arg(dct, DELETED_PROVIDERS):
                add(key, value)
        s = named_frozenset_set(tree, "_UNCAPPED_PICKER_PROVIDERS")
        if s is not None:
            for el in set_members(s, DELETED_PROVIDERS):
                add_node(el)
    elif name == "model_metadata.py":
        dct = named_dict(tree, "_URL_TO_PROVIDER")
        if dct is not None:
            for key, value in dict_entries_by_value(dct, DELETED_PROVIDERS):
                add(key, value)
    elif name == "auth.py":
        dct = named_dict(tree, "_PROVIDER_ALIASES")
        if dct is not None:
            for key, value in dict_entries_by_value(dct, DELETED_PROVIDERS):
                add(key, value)
    elif name == "model_resolution.py":
        dct = named_dict(tree, "PROVIDER_GROUPS")
        if dct is not None:
            for kind, a, b in group_entries(dct, DELETED_PROVIDERS):
                if kind == "entry":
                    add(a, b)
                else:
                    add_node(a)
        dct = named_dict(tree, "_PROVIDER_ALIASES")
        if dct is not None:
            for key, value in dict_entries_by_value(dct, DELETED_PROVIDERS):
                add(key, value)
    elif name == "main.py":
        for el in main_slug_sets(tree, DELETED_PROVIDERS):
            add_node(el)
    elif name == "setup.py":
        dct = named_dict(tree, "_DEFAULT_PROVIDER_MODELS")
        if dct is not None:
            for key, value in dict_entries_by_key(dct, DELETED_PROVIDERS):
                add(key, value)
    elif name == "models.py":
        dct = named_dict(tree, "_PROVIDER_MODELS")
        if dct is not None:
            for key, value in dict_entries_by_key(dct, DELETED_PROVIDERS):
                add(key, value)
        for stmt in subscript_assigns(tree, "_PROVIDER_MODELS", DELETED_PROVIDERS):
            add_node(stmt)
    return spans


def apply_spans(text: str, spans: list[tuple[int, int]]) -> str:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    out = text
    for start, end in sorted(merged, reverse=True):
        out = out[:start] + out[end:]
    return out


TARGETS = [
    "sparkii_cli/providers.py",
    "core/config_defaults.py",
    "sparkii_cli/doctor.py",
    "sparkii_cli/model_normalize.py",
    "sparkii_cli/model_switch.py",
    "agent/model_metadata.py",
    "sparkii_cli/auth.py",
    "core/model_resolution.py",
    "sparkii_cli/main.py",
    "sparkii_cli/setup.py",
    "sparkii_cli/models.py",
]


def process(path: Path, dry_run: bool) -> int:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        print(f"  SKIP (syntax error before edit): {path} {exc}")
        return -1
    spans = collect_spans(path, tree)
    if not spans:
        print(f"  {path}: no matches")
        return 0
    new_text = apply_spans(text, spans)
    try:
        ast.parse(new_text)
    except SyntaxError as exc:
        print(f"  FAIL (syntax error after edit): {path} {exc}")
        return -1
    if dry_run:
        print(f"  {path}: {len(spans)} span(s) would be removed")
        return len(spans)
    path.write_text(new_text, encoding="utf-8")
    print(f"  {path}: removed {len(spans)} span(s)")
    return len(spans)


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    total = 0
    for rel in TARGETS:
        path = ROOT / rel
        if not path.exists():
            print(f"  MISSING: {rel}")
            continue
        count = process(path, dry_run)
        if count > 0:
            total += count
    print(f"\ntotal spans: {total} ({'dry run' if dry_run else 'applied'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
