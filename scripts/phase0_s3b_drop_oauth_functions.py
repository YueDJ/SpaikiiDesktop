#!/usr/bin/env python3
"""Phase 0 S3-B: drop OAuth login/refresh families from sparkii_cli/auth.py.

Block B of the provider trim.  Deletes every function belonging to the
nous / openai-codex / xai-oauth / qwen-oauth / minimax-oauth / copilot-acp
OAuth families, plus the shared device-code helpers that only those families
used (_request_device_code / _poll_for_token / _refresh_access_token /
_default_verify / _resolve_verify) and the nous helper _agent_key_is_usable.

Spans start at the first decorator line (Python 3.12 FunctionDef.lineno
does NOT include decorators) and end at the function's end_lineno.

    .venv/Scripts/python.exe scripts/phase0_s3b_drop_oauth_functions.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "sparkii_cli" / "auth.py"

# Module-level constants owned by the deleted OAuth families.  Names not on
# this list (ACCESS_TOKEN_REFRESH_SKEW_SECONDS, CODEX_RATE_LIMITED_CODE, ...)
# are still referenced by kept code and must stay.
DELETED_CONSTANTS = {
    "NOUS_BILLING_MANAGE_SCOPE",
    "NOUS_DEVICE_CODE_SOURCE",
    "NOUS_AUTH_PATH_INVOKE_JWT",
    "NOUS_INVOKE_JWT_MIN_TTL_SECONDS",
    "DEVICE_AUTH_POLL_INTERVAL_CAP_SECONDS",
    "MINIMAX_OAUTH_GRANT_TYPE",
    "MINIMAX_OAUTH_REFRESH_SKEW_SECONDS",
    "CODEX_OAUTH_CLIENT_ID",
    "CODEX_OAUTH_TOKEN_URL",
    "CODEX_OAUTH_USER_AGENT",
    "CODEX_ACCESS_TOKEN_REFRESH_SKEW_SECONDS",
    "XAI_OAUTH_ISSUER",
    "XAI_OAUTH_DISCOVERY_URL",
    "XAI_OAUTH_CLIENT_ID",
    "XAI_OAUTH_SCOPE",
    "XAI_OAUTH_DEVICE_CODE_URL",
    "XAI_ACCESS_TOKEN_REFRESH_SKEW_SECONDS",
    "QWEN_OAUTH_CLIENT_ID",
    "QWEN_OAUTH_TOKEN_URL",
    "QWEN_ACCESS_TOKEN_REFRESH_SKEW_SECONDS",
    "_NOUS_PORTAL_ALLOWED_HOSTS",
    "_ALLOWED_NOUS_INFERENCE_HOSTS",
    "_NOUS_EFFECTIVE_STATE_IGNORED_KEYS",
    "CODEX_QUOTA_PROBE_MIN_INTERVAL_SECONDS",
    "_codex_quota_probe_cache",
    "_codex_quota_probe_lock",
    "NOUS_SHARED_STORE_FILENAME",
    "_nous_shared_lock_holder",
    "_RESOLVE_TOKEN_CACHE_LOCK",
    "_RESOLVE_TOKEN_CACHE",
    "_RESOLVE_TOKEN_CACHE_TTL_S",
    "_NOUS_AUTH_STATUS_CACHE_TTL",
    "_nous_auth_status_cache",
    "NOUS_SESSION_VALID",
    "NOUS_SESSION_TERMINAL",
    "NOUS_SESSION_UNKNOWN",
    "_MINIMAX_OAUTH_ERROR_BODY_LIMIT",
}


def is_oauth_family(name: str) -> bool:
    low = name.lower()
    return (
        "nous" in low
        or "codex" in low
        or "qwen" in low
        or "minimax" in low
        or "external_process" in low
        or low.startswith("_xai_")
        or "xai_oauth" in low
        or name
        in {
            "_request_device_code",
            "_poll_for_token",
            "_refresh_access_token",
            "_default_verify",
            "_resolve_verify",
            "_agent_key_is_usable",
        }
    )


def main() -> int:
    text = AUTH.read_text(encoding="utf-8")
    tree = ast.parse(text)
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))

    spans: list[tuple[int, int]] = []
    deleted: list[str] = []

    def add_span(start: int, end: int) -> None:
        # Swallow the trailing newline so families collapse cleanly.
        while end < len(text) and text[end] in " \t":
            end += 1
        if end < len(text) and text[end] == "\n":
            end += 1
        spans.append((start, end))

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not is_oauth_family(node.name):
            continue
        start_node = node.decorator_list[0] if node.decorator_list else node
        # FunctionDef.lineno excludes decorators; a decorator always starts
        # at column 0 (the '@'), so delete the whole line.
        start = offsets[start_node.lineno - 1]
        end = offsets[node.end_lineno - 1] + node.end_col_offset
        add_span(start, end)
        deleted.append(node.name)

    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if isinstance(target, ast.Name) and target.id in DELETED_CONSTANTS:
                add_span(offsets[node.lineno - 1], offsets[node.end_lineno - 1] + node.end_col_offset)
        elif isinstance(node, ast.Try):
            # The codex version-tag import block (CODEX_OAUTH_USER_AGENT feed).
            imports = []
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.ImportFrom) and stmt.module == "sparkii_cli":
                    imports.extend(a.asname or a.name for a in stmt.names)
            if "_SPARKII_CLI_VERSION" in imports:
                add_span(offsets[node.lineno - 1], offsets[node.end_lineno - 1] + node.end_col_offset)

    merged: list[list[int]] = []
    for start, end in sorted(spans):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    out = text
    for start, end in sorted(merged, reverse=True):
        out = out[:start] + out[end:]

    try:
        ast.parse(out)
    except SyntaxError as exc:
        print(f"FAIL: syntax error after edit: {exc}")
        return 1

    AUTH.write_text(out, encoding="utf-8")
    print(f"dropped {len(deleted)} functions ({len(merged)} spans)")
    print("  " + ", ".join(sorted(deleted)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
