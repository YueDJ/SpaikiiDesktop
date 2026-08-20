#!/usr/bin/env python3
"""Phase 0 S3-D: migrate sparkii_cli/auth.py generic api-key credential parsing
into core/credentials.py.

Closure analysis outcome (Block 3 of the foundation trim):
- CORE_NAMES: generic api-key credential parsing, provider-state persistence,
  auth-error mapping, small environment helpers. These move to core/credentials.
- SURFACE_NAMES: interactive CLI-only helpers (login/logout stubs, model
  selection prompts, config provider reset). These stay in sparkii_cli/auth.py
  as the CLI shim, importing from core.credentials.
- Everything else (Spotify OAuth leftovers, dead helpers) is dropped.

Writes core/credentials.py and rewrites sparkii_cli/auth.py, then validates
syntax. Run after review:

    .venv/Scripts/python.exe scripts/phase0_s3d_migrate_auth_credentials.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "sparkii_cli" / "auth.py"
CORE_OUT = ROOT / "core" / "credentials.py"
SHIM_OUT = ROOT / "sparkii_cli" / "auth.py"

CORE_NAMES = {
    "ACTUAL_LOCAL_NOAUTH_PLACEHOLDER",
    "AuthError",
    "CODEX_RATE_LIMITED_CODE",
    "KIMI_CODE_BASE_URL",
    "LMSTUDIO_NOAUTH_PLACEHOLDER",
    "STEPFUN_STEP_PLAN_CN_BASE_URL",
    "ZAI_ENDPOINTS",
    "_CONSOLE_BROWSER_NAMES",
    "_PLACEHOLDER_SECRET_VALUES",
    "_POOL_STATUS_FIELDS",
    "_can_open_graphical_browser",
    "_decode_jwt_claims",
    "_get_azure_foundry_auth_status",
    "_get_config_hint_for_unknown_provider",
    "_global_auth_file_path",
    "_is_remote_session",
    "_load_global_auth_store",
    "_load_provider_state",
    "_load_provider_state_with_source",
    "_merge_disk_cooldown_state",
    "_normalize_lmstudio_runtime_base_url",
    "_parse_iso_timestamp",
    "_persist_provider_state_to_store",
    "_probe_single_zai_endpoint",
    "_resolve_api_key_provider_secret",
    "_resolve_kimi_base_url",
    "_resolve_zai_base_url",
    "_save_provider_state",
    "_save_provider_state_to_source",
    "_store_provider_state",
    "clear_provider_auth",
    "deactivate_provider",
    "detect_zai_endpoint",
    "format_auth_error",
    "get_active_provider",
    "get_anthropic_key",
    "get_api_key_provider_status",
    "get_auth_provider_display_name",
    "get_auth_status",
    "get_provider_auth_state",
    "has_usable_secret",
    "is_actual_local_base_url",
    "is_known_auth_provider",
    "is_provider_explicitly_configured",
    "is_rate_limited_auth_error",
    "is_runtime_provider_routable",
    "mark_provider_active_if_unset",
    "normalize_actual_base_url",
    "read_credential_pool",
    "resolve_api_key_provider_credentials",
    "resolve_provider",
    "write_credential_pool",
}

SURFACE_NAMES = {
    "_config_provider_matches",
    "_confirm_expensive_model_selection",
    "_get_config_provider",
    "_prompt_model_selection",
    "_reset_config_provider",
    "_save_model_choice",
    "_should_reset_config_provider_on_logout",
    "_update_config_for_provider",
    "login_command",
    "logout_command",
}


def spans_for(src: str, tree: ast.Module, names: set[str]) -> list[tuple[int, int, str]]:
    """Return (start, end, name) spans for top-level nodes whose name is in set."""
    offsets = [0]
    for line in src.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))

    out: list[tuple[int, int, str]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
            start_node = node.decorator_list[0] if node.decorator_list else node
            start = offsets[start_node.lineno - 1]
            end = offsets[node.end_lineno - 1] + node.end_col_offset
            # swallow trailing blank lines (one newline past the node end)
            i = end
            while i < len(src) and src[i] in " \t":
                i += 1
            if i < len(src) and src[i] == "\n":
                i += 1
            if name in names:
                out.append((start, i, name))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name) and t.id in names:
                    start = offsets[node.lineno - 1]
                    end = offsets[node.end_lineno - 1] + node.end_col_offset
                    i = end
                    while i < len(src) and src[i] in " \t":
                        i += 1
                    if i < len(src) and src[i] == "\n":
                        i += 1
                    out.append((start, i, t.id))
                    break
    return sorted(out)


def extract(src: str, spans: list[tuple[int, int, str]]) -> str:
    return "".join(src[s:e] for s, e, _ in spans)


def main() -> int:
    src = AUTH.read_text(encoding="utf-8")
    tree = ast.parse(src)

    core_spans = spans_for(src, tree, CORE_NAMES)
    surface_spans = spans_for(src, tree, SURFACE_NAMES)
    extracted_core = {n for _, _, n in core_spans}
    extracted_surface = {n for _, _, n in surface_spans}

    missing_core = CORE_NAMES - extracted_core
    missing_surface = SURFACE_NAMES - extracted_surface
    if missing_core or missing_surface:
        print("MISSING core:", sorted(missing_core))
        print("MISSING surface:", sorted(missing_surface))
        return 1

    core_body = extract(src, core_spans)
    surface_body = extract(src, surface_spans)

    # ---- targeted fixes on the core body ----
    # 1) get_auth_status: drop the dead Spotify dispatch branch.
    core_body = re.sub(
        r"\n    if target == \"spotify\":\n        return get_spotify_auth_status\(\)\n",
        "\n",
        core_body,
    )
    # 2) is_known_auth_provider: drop SERVICE_PROVIDER_NAMES (Spotify-only).
    core_body = re.sub(
        r"return normalized in PROVIDER_REGISTRY or normalized in SERVICE_PROVIDER_NAMES",
        "return normalized in PROVIDER_REGISTRY",
        core_body,
    )
    # 3) get_auth_provider_display_name: drop SERVICE_PROVIDER_NAMES fallback.
    core_body = re.sub(
        r"return SERVICE_PROVIDER_NAMES\.get\(normalized, provider_id\)",
        "return provider_id",
        core_body,
    )
    # 4) is_provider_explicitly_configured: replace surface provider lookup
    #    with the injected core hook (see set_provider_lookup).
    core_body = re.sub(
        r"        from sparkii_cli\.providers import get_provider\n"
        r"        pconfig = get_provider\(normalized\)",
        "        lookup = get_provider_lookup()\n"
        "        pconfig = lookup(normalized) if lookup else None",
        core_body,
    )
    # 5) Drop the dead Copilot OAuth branches (copilot not in PROVIDER_REGISTRY;
    #    both branches are unreachable and imported surface copilot_auth).
    core_body = re.sub(
        re.escape(
            "    if provider_id == \"copilot\":\n"
            "        # Use the dedicated copilot auth module for proper token validation\n"
            "        try:\n"
            "            from sparkii_cli.copilot_auth import resolve_copilot_token, get_copilot_api_token\n"
            "            token, source = resolve_copilot_token()\n"
            "            if token:\n"
            "                api_token, _base_url = get_copilot_api_token(token)\n"
            "                return api_token, source\n"
            "        except ValueError as exc:\n"
            "            logger.warning(\"Copilot token validation failed: %s\", exc)\n"
            "        except Exception:\n"
            "            pass\n"
            "        return \"\", \"\"\n"
            "\n"
        ),
        "",
        core_body,
    )
    core_body = re.sub(
        re.escape(
            "    elif provider_id == \"copilot\":\n"
            "        # Resolve the Copilot API base URL from the token-exchange response\n"
            "        # (endpoints.api, with a proxy-ep fallback), which is authoritative\n"
            "        # for Enterprise / proxied accounts. Falls back to the registry\n"
            "        # default and is guarded non-empty below so chat inference never\n"
            "        # resolves an empty base URL (#50252).\n"
            "        base_url = env_url.rstrip(\"/\") if env_url else pconfig.inference_base_url\n"
            "        try:\n"
            "            from sparkii_cli.copilot_auth import (\n"
            "                resolve_copilot_token,\n"
            "                get_copilot_api_token,\n"
            "            )\n"
            "            raw_token, _ = resolve_copilot_token()\n"
            "            if raw_token:\n"
            "                _, resolved = get_copilot_api_token(raw_token)\n"
            "                resolved = (resolved or \"\").strip()\n"
            "                if resolved:\n"
            "                    base_url = resolved\n"
            "        except Exception as exc:\n"
            "            logger.debug(\"Copilot base URL resolution fell back to default: %s\", exc)\n"
        ),
        "",
        core_body,
    )
    ast.parse(core_body)
    ast.parse(surface_body)

    # ---- Write core/credentials.py (header crafted by the migration author) ----
    CORE_HEADER = '''\
"""
Core credential resolution.

Migrated from ``sparkii_cli/auth.py`` during the Phase 0 foundation trim
(Block 3).  OAuth login/refresh flows (Nous / Codex / xAI / Qwen / MiniMax /
Spotify / Copilot) were removed; this module keeps the generic **api-key
credential parsing**, provider-state persistence, and auth-error mapping that
the agent core and every surface share.

Layout:
- Provider metadata lives in :mod:`core.provider_registry`.
- The auth.json store (``~/.sparkii/auth.json``) lives in :mod:`core.auth_store`.
- Credential-source suppression lives in :mod:`core.credential_sources`.
- This module owns the resolution/status logic and the credential pool
  read/write merge on top of those primitives.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from typing import TYPE_CHECKING

# httpx is imported lazily: it costs ~30ms at import time and core.credentials
# is on the interactive-CLI startup path via credential_pool -> auxiliary_client
# -> cli_commands_mixin, where no HTTP request is ever made before first use.
# The proxy resolves to the real module on first attribute access; every
# consumer in this module uses ``httpx.<attr>`` so the swap is transparent.
import importlib as _importlib

if TYPE_CHECKING:
    import httpx
else:
    class _LazyHttpx:
        __slots__ = ("_mod",)

        def __init__(self) -> None:
            object.__setattr__(self, "_mod", None)

        def _resolve(self):
            mod = object.__getattribute__(self, "_mod")
            if mod is None:
                mod = _importlib.import_module("httpx")
                object.__setattr__(self, "_mod", mod)
            return mod

        def __getattr__(self, name):
            return getattr(self._resolve(), name)

        # Forward set/del to the real module so monkeypatch.setattr
        # ("core.credentials.httpx.Client", ...) keeps working in tests.
        def __setattr__(self, name, value):
            setattr(self._resolve(), name, value)

        def __delattr__(self, name):
            delattr(self._resolve(), name)

    httpx = _LazyHttpx()

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Optional,
    Tuple,
)
from urllib.parse import urlparse

from core.config import get_sparkii_home
from core.auth_store import (
    _auth_store_lock,
    _load_auth_store,
    _save_auth_store,
)
from core.provider_registry import (
    DEFAULT_ACTUAL_BASE_URL,
    PROVIDER_REGISTRY,
    ProviderConfig,
)
from agent.credential_persistence import sanitize_borrowed_credential_payload

logger = logging.getLogger(__name__)

# Optional surface-provided provider lookup (e.g. models.dev catalog) for
# providers outside the core registry.  Set by the CLI/gateway at startup via
# set_provider_lookup(); core-only processes simply skip the fallback.
_provider_lookup: Optional[Callable[[str], Any]] = None


def set_provider_lookup(fn: Optional[Callable[[str], Any]]) -> None:
    """Install an optional provider-lookup hook for catalog providers.

    ``is_provider_explicitly_configured`` consults this hook when a provider
    is absent from :data:`PROVIDER_REGISTRY` (e.g. ``openrouter``, which is
    intentionally excluded from the registry).  The hook must accept a
    normalized provider id and return an object exposing ``auth_type`` and
    ``api_key_env_vars`` (ProviderConfig shape), or ``None``.
    """
    global _provider_lookup
    _provider_lookup = fn


def get_provider_lookup() -> Optional[Callable[[str], Any]]:
    """Return the installed provider-lookup hook, or ``None``."""
    return _provider_lookup


from core.credential_sources import (
    is_source_suppressed,
    suppress_credential_source,
    unsuppress_credential_source,
)

'''
    CORE_OUT.write_text(CORE_HEADER + core_body + "\n", encoding="utf-8")

    # ---- Rewrite sparkii_cli/auth.py as the CLI shim ----
    SHIM_HEADER = '''\
"""
CLI-facing auth shim.

The generic api-key credential parsing and provider-state persistence moved to
:mod:`core.credentials` during the Phase 0 foundation trim (Block 3).  This
module keeps the interactive CLI-only helpers (login/logout command stubs,
model-selection prompts, config provider reset) and re-exports the core
credential API so existing surface imports keep working.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Re-export the core credential API for surface/test compatibility.
from core.credentials import (
    ACTUAL_LOCAL_NOAUTH_PLACEHOLDER,
    AuthError,
    CODEX_RATE_LIMITED_CODE,
    KIMI_CODE_BASE_URL,
    LMSTUDIO_NOAUTH_PLACEHOLDER,
    STEPFUN_STEP_PLAN_CN_BASE_URL,
    ZAI_ENDPOINTS,
    _can_open_graphical_browser,
    _decode_jwt_claims,
    _get_azure_foundry_auth_status,
    _get_config_hint_for_unknown_provider,
    _global_auth_file_path,
    _is_remote_session,
    _load_global_auth_store,
    _load_provider_state,
    _load_provider_state_with_source,
    _merge_disk_cooldown_state,
    _normalize_lmstudio_runtime_base_url,
    _parse_iso_timestamp,
    _persist_provider_state_to_store,
    _probe_single_zai_endpoint,
    _resolve_api_key_provider_secret,
    _resolve_kimi_base_url,
    _resolve_zai_base_url,
    _save_provider_state,
    _save_provider_state_to_source,
    _store_provider_state,
    clear_provider_auth,
    deactivate_provider,
    detect_zai_endpoint,
    format_auth_error,
    get_active_provider,
    get_anthropic_key,
    get_api_key_provider_status,
    get_auth_provider_display_name,
    get_auth_status,
    get_provider_auth_state,
    has_usable_secret,
    is_actual_local_base_url,
    is_known_auth_provider,
    is_provider_explicitly_configured,
    is_rate_limited_auth_error,
    is_runtime_provider_routable,
    mark_provider_active_if_unset,
    normalize_actual_base_url,
    read_credential_pool,
    resolve_api_key_provider_credentials,
    resolve_provider,
    write_credential_pool,
)
from core.auth_store import (
    AUTH_STORE_VERSION,
    AUTH_LOCK_TIMEOUT_SECONDS,
    DEFAULT_NOUS_PORTAL_URL,
    _auth_file_path,
    _auth_lock_path,
    _auth_store_lock,
    _load_auth_store,
    _save_auth_store,
)
from core.provider_registry import (
    DEFAULT_ACTUAL_BASE_URL,
    PROVIDER_REGISTRY,
    ProviderConfig,
)
from core.credential_sources import (
    is_source_suppressed,
    suppress_credential_source,
    unsuppress_credential_source,
)
from sparkii_constants import OPENROUTER_BASE_URL
from core.config import get_config_path, read_raw_config, require_readable_config_before_write
from utils import atomic_yaml_write

logger = __import__("logging").getLogger(__name__)

'''
    SHIM_OUT.write_text(SHIM_HEADER + surface_body + "\n", encoding="utf-8")

    ast.parse(CORE_OUT.read_text(encoding="utf-8"))
    ast.parse(SHIM_OUT.read_text(encoding="utf-8"))
    print(f"core/credentials.py: {len(core_body.splitlines())} body lines")
    print(f"sparkii_cli/auth.py: {len(surface_body.splitlines())} body lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
