#!/usr/bin/env python3
"""Block 4 Step 2 rewrite pass: remap intra-cluster imports to core.

After the sink copied sparkii_cli service modules into core/, this pass fixes
the remaining cross-references inside the moved files:

  * ``from sparkii_cli.auth import ...`` — symbol-level split into
    core.credentials / core.auth_store / core.provider_registry (the four
    dead Nous/Codex symbols are removed separately by hand);
  * ``from sparkii_cli.<mod> import ...`` → ``from core.<mod> import ...``;
  * kanban_db's gateway memory helpers → core.mem_trim.

Uses AST node spans so single-line and parenthesized multi-line imports are
rewritten correctly.
"""

from __future__ import annotations

import ast
import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FILES = [
    "core/runtime_provider.py",
    "core/model_switch.py",
    "core/kanban_db.py",
    "core/models.py",
    "core/inventory.py",
    "core/tools_config.py",
    "agent/agent_init.py",
    "agent/agent_runtime_helpers.py",
    "agent/anthropic_adapter.py",
    "agent/auxiliary_client.py",
    "agent/chat_completion_helpers.py",
    "agent/coding_context.py",
    "agent/context_breakdown.py",
    "agent/conversation_compression.py",
    "agent/conversation_loop.py",
    "agent/credential_pool.py",
    "agent/error_classifier.py",
    "agent/gemini_native_adapter.py",
    "agent/lsp/install.py",
    "agent/moa_loop.py",
    "agent/model_metadata.py",
    "agent/monitoring/gateway_health.py",
    "agent/monitoring/gateway_health_export.py",
    "agent/plugin_llm.py",
    "agent/plugin_stream_hooks.py",
    "agent/prompt_builder.py",
    "agent/skill_commands.py",
    "agent/system_prompt.py",
    "agent/tool_executor.py",
    "agent/turn_finalizer.py",
    "core/credential_lifecycle.py",
    "core/models.py",
    "core/providers.py",
    "core/observability/shared_metrics_contract.py",
    "model_tools.py",
    "run_agent.py",
    "sparkii_state.py",
    "tools/approval.py",
    "tools/browser_use_cli.py",
    "tools/computer_use/cua_backend.py",
    "tools/cronjob_tools.py",
    "tools/delegate_tool.py",
    "tools/environments/docker.py",
    "tools/kanban_tools.py",
    "tools/lazy_deps.py",
    "tools/mcp_tool.py",
    "tools/project_tools.py",
    "tools/session_search_tool.py",
    "tools/transcription_tools.py",
    "tools/tts_tool.py",
    "tools/wake_word.py",
    "tools/xai_http.py",
    "plugins/context_engine/__init__.py",
    "plugins/cron_providers/chronos/__init__.py",
    "plugins/cron_providers/chronos/_nas_client.py",
    "plugins/google_meet/cli.py",
    "plugins/image_gen/deepinfra/__init__.py",
    "plugins/image_gen/openrouter/__init__.py",
    "plugins/kanban/dashboard/plugin_api.py",
    "plugins/memory/__init__.py",
    "plugins/memory/hindsight/__init__.py",
    "plugins/memory/honcho/cli.py",
    "plugins/memory/honcho/client.py",
    "plugins/memory/mem0/_setup.py",
    "plugins/memory/openviking/__init__.py",
    "plugins/memory/supermemory/__init__.py",
    "plugins/video_gen/deepinfra/__init__.py",
]

# sparkii_cli.auth -> (symbol -> home); anything not listed goes to core.credentials.
AUTH_HOME = {
    "PROVIDER_REGISTRY": "core.provider_registry",
    "_load_auth_store": "core.auth_store",
}

# Whole-module remaps (module name only; symbol lists untouched).
MODULE_MAP = {
    "sparkii_cli.models": "core.models",
    "sparkii_cli.model_normalize": "core.model_normalize",
    "sparkii_cli.runtime_provider": "core.runtime_provider",
    "sparkii_cli.model_catalog": "core.model_catalog",
    "sparkii_cli.providers": "core.providers",
    "sparkii_cli.model_switch": "core.model_switch",
    "sparkii_cli.middleware": "core.middleware",
    "sparkii_cli.heartbeat": "core.heartbeat",
    "sparkii_cli.loops": "core.loops",
    "sparkii_cli.copilot_auth": "core.copilot_auth",
    "sparkii_cli.inventory": "core.inventory",
    "sparkii_cli.tools_config": "core.tools_config",
    "sparkii_cli.goals": "core.goals",
    "sparkii_cli.profiles": "core.profiles",
    "sparkii_cli.lifecycle": "core.lifecycle",
    "sparkii_cli.plugins": "core.plugins",
    "sparkii_cli.platforms": "core.platforms",
    "sparkii_cli.managed_uv": "core.managed_uv",
    "sparkii_cli.prompt_size": "core.prompt_size",
    "sparkii_cli.approval_transport": "core.approval_transport",
    "sparkii_cli.lifecycle": "core.lifecycle",
    "sparkii_cli.copilot_auth": "core.copilot_auth",
    "sparkii_cli.observability.relay_shared_metrics": "core.observability.relay_shared_metrics",
    "sparkii_cli.kanban_db": "core.kanban_db",
    "sparkii_cli.kanban_diagnostics": "core.kanban_diagnostics",
    "sparkii_cli.memory_setup": "core.memory_setup",
}

# Simple textual rewrites for from-import aliases / version imports.
ALIAS_REWRITES = [
    (
        "from sparkii_cli import __version__ as _SPARKII_VERSION",
        "from core.version import __version__ as _SPARKII_VERSION",
    ),
    (
        "from sparkii_cli import __version__",
        "from core.version import __version__",
    ),
    (
        "from sparkii_cli import kanban_db as",
        "from core import kanban_db as",
    ),
    (
        "from sparkii_cli import kanban_db",
        "from core import kanban_db",
    ),
    (
        "from sparkii_cli import projects_db as",
        "from core import projects_db as",
    ),
    (
        "from sparkii_cli import profiles as",
        "from core import profiles as",
    ),
    (
        "from sparkii_cli import lifecycle as",
        "from core import lifecycle as",
    ),
    (
        "from sparkii_cli import kanban_diagnostics as",
        "from core import kanban_diagnostics as",
    ),
    (
        "from sparkii_cli import kanban_specify as",
        "from core import kanban_specify as",
    ),
    (
        "from sparkii_cli import kanban_decompose as",
        "from core import kanban_decompose as",
    ),
    (
        "from sparkii_cli import profile_describer as",
        "from core import profile_describer as",
    ),
    (
        "from sparkii_cli import kanban_specify",
        "from core import kanban_specify",
    ),
    (
        "from sparkii_cli import profile_describer",
        "from core import profile_describer",
    ),
    (
        "from sparkii_cli import kanban_decompose",
        "from core import kanban_decompose",
    ),
    (
        "from sparkii_cli.backup import is_zeroed_sqlite_file",
        "from core.sqlite_util import is_zeroed_sqlite_file",
    ),
]


def _replace_span(lines: list[str], start: tuple[int, int], end: tuple[int, int], text: str) -> None:
    """Splice *text* over the byte-ish (line, col) span."""
    start_line, start_col = start
    end_line, end_col = end
    head = lines[start_line - 1][:start_col]
    tail = lines[end_line - 1][end_col:]
    lines[start_line - 1] = head + text + tail
    if end_line > start_line:
        del lines[start_line:end_line]


def rewrite_auth_imports(text: str) -> str:
    tree = ast.parse(text)
    nodes = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module == "sparkii_cli.auth"
    ]
    if not nodes:
        return text
    lines = text.splitlines(keepends=True)
    for node in sorted(nodes, key=lambda n: (n.lineno, n.col_offset), reverse=True):
        indent = lines[node.lineno - 1][: node.col_offset]
        groups: dict[str, list[str]] = {}
        for alias in node.names:
            home = AUTH_HOME.get(alias.name, "core.credentials")
            groups.setdefault(home, []).append(alias.name)
        stmts = [
            f"from {home} import {', '.join(names)}"
            for home, names in groups.items()
        ]
        # ``head`` already carries the statement indent; align continuation
        # statements under it.
        continuation = " " * len(indent)
        replacement = ("\n" + continuation).join(stmts)
        end_lineno = node.end_lineno or node.lineno
        end_col = node.end_col_offset if node.end_col_offset is not None else len(lines[end_lineno - 1].rstrip("\n"))
        _replace_span(
            lines,
            (node.lineno, node.col_offset),
            (end_lineno, end_col),
            replacement,
        )
    return "".join(lines)


def rewrite_module_imports(text: str) -> str:
    for old, new in MODULE_MAP.items():
        text = text.replace(f"from {old} import", f"from {new} import")
    for old, new in ALIAS_REWRITES:
        text = text.replace(old, new)
    return text


def main() -> int:
    for rel in FILES:
        p = ROOT / rel
        text = _read_retry(p)
        original = text
        text = rewrite_module_imports(text)
        text = rewrite_auth_imports(text)
        # kanban_db memory helpers moved to core.mem_trim.
        text = text.replace(
            "from gateway.lifecycle_ledger import sample_memory",
            "from core.mem_trim import sample_memory",
        )
        text = text.replace(
            "from gateway.memory_status import classify_pressure",
            "from core.mem_trim import classify_pressure",
        )
        if text != original:
            _write_retry(p, text)
            print(f"REWROTE {rel}")
        else:
            print(f"unchanged {rel}")
    return 0


def _read_retry(p: Path) -> str:
    for _ in range(5):
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            time.sleep(0.2)
    return p.read_text(encoding="utf-8")


def _write_retry(p: Path, text: str) -> None:
    for _ in range(5):
        try:
            p.write_text(text, encoding="utf-8")
            return
        except OSError:
            time.sleep(0.25)
    p.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
