"""Shared helpers for classifying tool result payloads."""

from __future__ import annotations

import json
from typing import Any

from utils import safe_json_loads


FILE_MUTATING_TOOL_NAMES = frozenset({"write_file", "patch"})


# Tools whose interrupted/dangling execution is safe to discard because they
# cannot mutate either external state or Sparkii session state. Unknown/plugin/
# MCP tools stay effect-capable by default.
NO_EFFECT_TOOL_NAMES = frozenset({
    "read_file", "search_files", "session_search", "skill_view", "skills_list",
    "web_extract", "web_search", "vision_analyze", "browser_snapshot",
    "browser_get_images", "browser_console", "read_terminal",
})


def tool_may_have_side_effect(tool_name: str) -> bool:
    return tool_name not in NO_EFFECT_TOOL_NAMES


def file_mutation_result_landed(tool_name: str, result: Any) -> bool:
    """Return True when a file mutation result proves the write landed."""
    if tool_name not in FILE_MUTATING_TOOL_NAMES or not isinstance(result, str):
        return False
    try:
        data = json.loads(result.strip())
    except Exception:
        return False
    if not isinstance(data, dict) or data.get("error"):
        return False
    if tool_name == "write_file":
        return "bytes_written" in data
    if tool_name == "patch":
        return data.get("success") is True
    return False


_ERROR_SUFFIX_MAX_LEN = 48


def _trim_error(msg: str) -> str:
    """Shrink an error message for inline display in a tool status line.

    Strips overly long absolute paths down to just the filename so the
    suffix stays readable on narrow terminals.
    """
    msg = msg.strip()
    # Common case: "File not found: /very/long/absolute/path/foo.py"
    if "File not found:" in msg:
        _, _, tail = msg.partition("File not found:")
        tail = tail.strip()
        if "/" in tail:
            msg = f"File not found: {tail.rsplit('/', 1)[-1]}"
    if len(msg) > _ERROR_SUFFIX_MAX_LEN:
        msg = msg[: _ERROR_SUFFIX_MAX_LEN - 3] + "..."
    return msg


def _detect_tool_failure(tool_name: str, result: str | None) -> tuple[bool, str]:
    """Inspect a tool result string for signs of failure.

    Returns ``(is_failure, suffix)`` where *suffix* is a short informational
    tag like ``" [exit 1]"`` for terminal failures, ``" [full]"`` for memory
    overflow, or a trimmed error message (``" [File not found: foo.py]"``).
    On success returns ``(False, "")``.
    """
    if result is None:
        return False, ""
    if file_mutation_result_landed(tool_name, result):
        return False, ""

    data = safe_json_loads(result)

    # Terminal: non-zero exit code is the canonical failure signal.
    if tool_name == "terminal":
        if isinstance(data, dict):
            exit_code = data.get("exit_code")
            if exit_code is not None and exit_code != 0:
                err_msg = data.get("error")
                if err_msg:
                    return True, f" [{_trim_error(str(err_msg))}]"
                return True, f" [exit {exit_code}]"
        return False, ""

    # Memory: distinguish "store full" from real errors.
    if tool_name == "memory":
        if isinstance(data, dict):
            if data.get("success") is False and "exceed the limit" in data.get("error", ""):
                return True, " [full]"

    # Structured error in JSON result (any tool that surfaces {"error": ...}).
    if isinstance(data, dict):
        err = data.get("error") or data.get("message")
        if err and (data.get("success") is False or "error" in data):
            return True, f" [{_trim_error(str(err))}]"

    # Generic heuristic for non-terminal tools
    # Multimodal tool results (dicts with _multimodal=True) are not strings —
    # treat them as successes since failures would be JSON-encoded strings.
    if not isinstance(result, str):
        return False, ""
    lower = result[:500].lower()
    if '"error"' in lower or '"failed"' in lower or result.startswith("Error"):
        return True, " [error]"

    return False, ""
