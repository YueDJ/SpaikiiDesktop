"""
Multi-provider authentication system for Sparkii Agent.

Supports OAuth device code flows (Nous Portal, future: OpenAI Codex) and
traditional API key providers (OpenRouter, custom endpoints). Auth state
is persisted in ~/.sparkii/auth.json with cross-process file locking.

Architecture:
- ProviderConfig registry defines known OAuth providers
- Auth store (auth.json) holds per-provider credential state
- resolve_provider() picks the active provider via priority chain
- resolve_*_runtime_credentials() handles token refresh and runtime keys
- logout_command() is the CLI entry point for clearing auth

Nous authentication paths:
- Invoke JWT (preferred): use a scoped access_token directly for inference.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import shlex
import ssl
import stat
import sys
import base64
import hashlib
import subprocess
import threading
import time
import uuid
import webbrowser

# httpx is imported lazily: it costs ~30ms at import time and sparkii_cli.auth
# is on the interactive-CLI startup path via credential_pool → auxiliary_client
# → cli_commands_mixin, where no HTTP request is ever made before first use.
# The proxy resolves to the real module on first attribute access; every
# consumer in this file uses `httpx.<attr>` so the swap is transparent.
# Annotations like ``httpx.Client`` stay valid: `from __future__ import
# annotations` (above) keeps them unevaluated at runtime, and the
# TYPE_CHECKING import gives static checkers the real module.
import importlib as _importlib
from typing import TYPE_CHECKING

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
        # ("sparkii_cli.auth.httpx.Client", ...) keeps working in tests.
        def __setattr__(self, name, value):
            setattr(self._resolve(), name, value)

        def __delattr__(self, name):
            delattr(self._resolve(), name)

    httpx = _LazyHttpx()
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse

from core.config import (
    get_sparkii_home,
    get_config_path,
    read_raw_config,
    require_readable_config_before_write,
)
from sparkii_constants import OPENROUTER_BASE_URL, secure_parent_dir
from agent.credential_persistence import sanitize_borrowed_credential_payload
from utils import atomic_replace, atomic_yaml_write, env_float, is_truthy_value

logger = logging.getLogger(__name__)

try:
    import fcntl
except Exception:
    fcntl = None
try:
    import msvcrt
except Exception:
    msvcrt = None

# =============================================================================
# Constants
# =============================================================================

from core.auth_store import (
    AUTH_STORE_VERSION,
    AUTH_LOCK_TIMEOUT_SECONDS,
    DEFAULT_NOUS_PORTAL_URL,
    _auth_file_path,
    _auth_lock_path,
    _auth_target_lock_holders,
    _auth_target_lock_holders_guard,
    _same_path,
    _auth_lock_holder_for,
    _file_lock,
    _auth_store_lock,
    _load_auth_store,
    _save_auth_store,
)


from core.provider_registry import (
    ProviderConfig,
    PROVIDER_REGISTRY,
    DEFAULT_ACTUAL_BASE_URL,
)

ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 120       # refresh 2 min before expiry
DEFAULT_ACTUAL_LOCAL_BASE_URL = "http://127.0.0.1:8080/v1"
STEPFUN_STEP_PLAN_CN_BASE_URL = "https://api.stepfun.com/step_plan/v1"
# xAI/Grok OAuth access tokens are intentionally short-lived (about 6h in
# current SuperGrok flows). A two-minute refresh window is too narrow for
# gateway/cron workloads that may only touch the provider every 30 minutes,
# leaving brief but noisy credential-expiry gaps. Refresh up to one hour
# early so ordinary runtime calls keep the token warm without user reauth.
DEFAULT_SPOTIFY_ACCOUNTS_BASE_URL = "https://accounts.spotify.com"
DEFAULT_SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"
DEFAULT_SPOTIFY_REDIRECT_URI = "http://127.0.0.1:43827/spotify/callback"
SPOTIFY_DOCS_URL = "https://sparkii-agent.nousresearch.com/docs/user-guide/features/spotify"
SPOTIFY_DASHBOARD_URL = "https://developer.spotify.com/dashboard"
SPOTIFY_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 120

OAUTH_OVER_SSH_DOCS_URL = "https://sparkii-agent.nousresearch.com/docs/guides/oauth-over-ssh"
DEFAULT_SPOTIFY_SCOPE = " ".join((
    "user-modify-playback-state",
    "user-read-playback-state",
    "user-read-currently-playing",
    "user-read-recently-played",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    "user-library-read",
    "user-library-modify",
))
SERVICE_PROVIDER_NAMES: Dict[str, str] = {
    "spotify": "Spotify",
}

# LM Studio's default no-auth mode still requires *some* non-empty bearer for
# the API-key code paths (auxiliary_client, runtime resolver) to treat the
# provider as configured. This sentinel is sent only to LM Studio, never to
# any remote service.
LMSTUDIO_NOAUTH_PLACEHOLDER = "dummy-lm-api-key"
ACTUAL_LOCAL_NOAUTH_PLACEHOLDER = "dummy-actual-local-api-key"


def is_actual_local_base_url(base_url: str) -> bool:
    """Return True for Actual's loopback local API endpoint."""
    try:
        host = (urlparse(base_url or "").hostname or "").lower().rstrip(".")
    except Exception:
        return False
    return host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def normalize_actual_base_url(base_url: str) -> str:
    """Return Actual's OpenAI-compatible base URL.

    Actual hosted inference is exposed at api.actual.inc, while the Actual
    client's offline local server binds a loopback host. Both use a /v1 API
    surface for Sparkii' Responses transport.
    """
    url = str(base_url or "").strip().rstrip("/")
    if not url:
        return DEFAULT_ACTUAL_BASE_URL
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        path = parsed.path.rstrip("/")
    except Exception:
        return url
    if host == "api.actual.inc" and path in {"", "/"}:
        return url + "/v1"
    if is_actual_local_base_url(url) and path in {"", "/"}:
        return url + "/v1"
    return url


# =============================================================================
# Provider Registry
# =============================================================================

# =============================================================================
# Anthropic Key Helper
# =============================================================================

def get_anthropic_key() -> str:
    """Return the first usable Anthropic credential, or ``""``.

    Checks both the ``.env`` file and the process environment, preferring
    ``~/.sparkii/.env`` so a deliberate key rotation isn't shadowed by a stale
    shell export (matches the api-key resolution path — see #20591).  The
    order mirrors the ``PROVIDER_REGISTRY["anthropic"].api_key_env_vars``
    tuple:

        ANTHROPIC_API_KEY -> ANTHROPIC_TOKEN -> CLAUDE_CODE_OAUTH_TOKEN
    """
    from core.config import get_env_value_prefer_dotenv

    for var in PROVIDER_REGISTRY["anthropic"].api_key_env_vars:
        value = get_env_value_prefer_dotenv(var) or ""
        if value:
            return value
    return ""


# =============================================================================
# Kimi Code Endpoint Detection
# =============================================================================

# Kimi Code (kimi.com/code) issues keys prefixed "sk-kimi-" that only work
# on api.kimi.com/coding.  Legacy keys from platform.moonshot.ai work on
# api.moonshot.ai/v1 (the old default).  Auto-detect when user hasn't set
# KIMI_BASE_URL explicitly.
#
# Note: the base URL intentionally has NO /v1 suffix.  The /coding endpoint
# speaks the Anthropic Messages protocol, and the anthropic SDK appends
# "/v1/messages" internally — so "/coding" + SDK suffix → "/coding/v1/messages"
# (the correct target). Using "/coding/v1" here would produce
# "/coding/v1/v1/messages" (a 404).
KIMI_CODE_BASE_URL = "https://api.kimi.com/coding"


def _resolve_kimi_base_url(api_key: str, default_url: str, env_override: str) -> str:
    """Return the correct Kimi base URL based on the API key prefix.

    If the user has explicitly set KIMI_BASE_URL, that always wins.
    Otherwise, sk-kimi- prefixed keys route to api.kimi.com/coding/v1.
    """
    if env_override:
        return env_override
    # No key → nothing to infer from.  Return default without inspecting.
    if not api_key:
        return default_url
    if api_key.startswith("sk-kimi-"):
        return KIMI_CODE_BASE_URL
    return default_url



_PLACEHOLDER_SECRET_VALUES = {
    "*",
    "**",
    "***",
    "changeme",
    "your_api_key",
    "your_api_key_here",
    "your-api-key",
    "placeholder",
    "example",
    "dummy",
    "null",
    "none",
}


def has_usable_secret(value: Any, *, min_length: int = 4) -> bool:
    """Return True when a configured secret looks usable, not empty/placeholder."""
    if not isinstance(value, str):
        return False
    cleaned = value.strip()
    if len(cleaned) < min_length:
        return False
    if cleaned.lower() in _PLACEHOLDER_SECRET_VALUES:
        return False
    return True


def _resolve_api_key_provider_secret(
    provider_id: str, pconfig: ProviderConfig
) -> tuple[str, str]:
    """Resolve an API-key provider's token and indicate where it came from."""
    if provider_id == "copilot":
        # Use the dedicated copilot auth module for proper token validation
        try:
            from sparkii_cli.copilot_auth import resolve_copilot_token, get_copilot_api_token
            token, source = resolve_copilot_token()
            if token:
                api_token, _base_url = get_copilot_api_token(token)
                return api_token, source
        except ValueError as exc:
            logger.warning("Copilot token validation failed: %s", exc)
        except Exception:
            pass
        return "", ""

    from core.config import get_env_value_prefer_dotenv
    for env_var in pconfig.api_key_env_vars:
        # Prefer ~/.sparkii/.env over os.environ so a deliberate key rotation
        # in the user's .env file isn't shadowed by a stale shell export
        # inherited from a parent process (Codex CLI, test runners, etc.).
        val = (get_env_value_prefer_dotenv(env_var) or "").strip()
        if has_usable_secret(val):
            return val, env_var

    # Fallback: try credential pool (e.g. zai key stored via auth.json)
    try:
        from agent.credential_pool import load_pool
        pool = load_pool(provider_id)
        if pool and pool.has_credentials():
            entry = pool.peek()
            if entry:
                key = getattr(entry, "access_token", "") or getattr(entry, "runtime_api_key", "")
                key = str(key).strip()
                if has_usable_secret(key):
                    return key, f"credential_pool:{provider_id}"
    except Exception:
        pass

    return "", ""


# =============================================================================
# Z.AI Endpoint Detection
# =============================================================================

# Z.AI has separate billing for general vs coding plans, and global vs China
# endpoints.  A key that works on one may return "Insufficient balance" on
# another.  We probe at setup time and store the working endpoint.
# Each entry lists candidate models to try in order — newer coding plan accounts
# may only have access to recent models (glm-5.1, glm-5v-turbo) while older
# ones still use glm-4.7.

ZAI_ENDPOINTS = [
    # (id, base_url, probe_models, label)
    ("global",        "https://api.z.ai/api/paas/v4",        ["glm-5"],   "Global"),
    ("cn",            "https://open.bigmodel.cn/api/paas/v4", ["glm-5"],   "China"),
    ("coding-global", "https://api.z.ai/api/coding/paas/v4",  ["glm-5.2", "glm-5.1", "glm-5v-turbo", "glm-4.7"], "Global (Coding Plan)"),
    ("coding-cn",     "https://open.bigmodel.cn/api/coding/paas/v4", ["glm-5.2", "glm-5.1", "glm-5v-turbo", "glm-4.7"], "China (Coding Plan)"),
]


def _probe_single_zai_endpoint(
    api_key: str, endpoint: tuple, timeout: float,
) -> Optional[Dict[str, str]]:
    """Probe a single Z.AI endpoint. Returns endpoint info dict or None.

    Preserves the per-endpoint candidate-model loop: endpoints carry a
    ``probe_models`` LIST and each model is tried in order until one
    succeeds (some plans only accept newer/older GLM slugs).
    """
    ep_id, base_url, probe_models, label = endpoint
    for model in probe_models:
        try:
            resp = httpx.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "stream": False,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "ping"}],
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                logger.debug("Z.AI endpoint probe: %s (%s) model=%s OK", ep_id, base_url, model)
                return {
                    "id": ep_id,
                    "base_url": base_url,
                    "model": model,
                    "label": label,
                }
            logger.debug("Z.AI endpoint probe: %s model=%s returned %s", ep_id, model, resp.status_code)
        except Exception as exc:
            logger.debug("Z.AI endpoint probe: %s model=%s failed: %s", ep_id, model, exc)
    return None


def detect_zai_endpoint(api_key: str, timeout: float = 8.0) -> Optional[Dict[str, str]]:
    """Probe z.ai endpoints in parallel to find one that accepts this API key.

    Returns {"id": ..., "base_url": ..., "model": ..., "label": ...} for the
    first working endpoint (in ZAI_ENDPOINTS priority order), or None if all
    fail.  For endpoints with multiple candidate models, each worker tries
    its endpoint's models in order and returns the first that succeeds.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # No `with` block: a context manager would join ALL probe threads on
    # exit, defeating the early return below. shutdown(wait=False) lets the
    # surviving daemon-style probes drain in the background instead of
    # blocking the caller on slow/unreachable endpoints.
    pool = ThreadPoolExecutor(max_workers=len(ZAI_ENDPOINTS))
    try:
        futures = {
            pool.submit(_probe_single_zai_endpoint, api_key, ep, timeout): ep[0]
            for ep in ZAI_ENDPOINTS
        }
        by_id = {ep_id: f for f, ep_id in futures.items()}
        results: Dict[str, Dict[str, str]] = {}
        for future in as_completed(futures):
            ep_id = futures[future]
            try:
                result = future.result()
                if result is not None:
                    results[ep_id] = result
            except Exception:
                pass
            # Early exit in PRIORITY order: walk endpoints highest-priority
            # first; if one has succeeded and every higher-priority probe
            # has already finished (without success), no later completion
            # can win — return now instead of waiting out slow endpoints
            # (main's sequential loop also stopped at first success).
            for ep in ZAI_ENDPOINTS:
                if not by_id[ep[0]].done():
                    break  # a higher-priority probe is still in flight
                if ep[0] in results:
                    return results[ep[0]]

        # All probes finished: first match in priority order, if any.
        for ep in ZAI_ENDPOINTS:
            if ep[0] in results:
                return results[ep[0]]
        return None
    finally:
        pool.shutdown(wait=False)


def _resolve_zai_base_url(api_key: str, default_url: str, env_override: str) -> str:
    """Return the correct Z.AI base URL by probing endpoints.

    If the user has explicitly set GLM_BASE_URL, that always wins.
    Otherwise, probe the candidate endpoints to find one that accepts the
    key.  The detected endpoint is cached in provider state (auth.json) keyed
    on a hash of the API key so subsequent starts skip the probe.
    """
    if env_override:
        return env_override

    # No API key set → don't probe (would fire N×M HTTPS requests with an
    # empty Bearer token, all returning 401).  This path is hit during
    # auxiliary-client auto-detection when the user has no Z.AI credentials
    # at all — the caller discards the result immediately, so the probe is
    # pure latency for every AIAgent construction.
    if not api_key:
        return default_url

    # Check provider-state cache for a previously-detected endpoint.
    auth_store = _load_auth_store()
    state = _load_provider_state(auth_store, "zai") or {}
    cached = state.get("detected_endpoint")
    if isinstance(cached, dict) and cached.get("base_url"):
        key_hash = cached.get("key_hash", "")
        if key_hash == hashlib.sha256(api_key.encode()).hexdigest()[:16]:
            logger.debug("Z.AI: using cached endpoint %s", cached["base_url"])
            return cached["base_url"]

    # Probe — may take up to ~8s per endpoint.
    detected = detect_zai_endpoint(api_key)
    if detected and detected.get("base_url"):
        # Persist the detection result keyed on the API key hash.
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        detected_endpoint = {
            "base_url": detected["base_url"],
            "endpoint_id": detected.get("id", ""),
            "model": detected.get("model", ""),
            "label": detected.get("label", ""),
            "key_hash": key_hash,
        }
        # Persist failure (disk full, permissions, lock timeout) must not
        # break resolution — detection already succeeded; worst case the
        # next start re-probes.
        try:
            with _auth_store_lock():
                # Reload auth_store under lock to avoid overwriting concurrent changes
                auth_store = _load_auth_store()
                state_under_lock = _load_provider_state(auth_store, "zai") or {}
                state_under_lock["detected_endpoint"] = detected_endpoint
                # set_active=False: this runs from credential-pool env seeding
                # (agent/credential_pool.py) for ANY user with a Z.AI key in env,
                # and caching a probe result must not flip their active provider.
                _store_provider_state(auth_store, "zai", state_under_lock, set_active=False)
                _save_auth_store(auth_store)
        except Exception as exc:
            logger.warning("Z.AI: could not persist detected endpoint (%s); will re-probe next start", exc)
        logger.info("Z.AI: auto-detected endpoint %s (%s)", detected["label"], detected["base_url"])
        return detected["base_url"]

    logger.debug("Z.AI: probe failed, falling back to default %s", default_url)
    return default_url


def _normalize_lmstudio_runtime_base_url(base_url: str) -> str:
    """Return the OpenAI-compatible LM Studio runtime base URL.

    LM Studio's native management API lives under ``/api/v1`` while its
    OpenAI-compatible chat endpoint lives under ``/v1``. Users often paste
    either form into ``LM_BASE_URL`` or ``model.base_url``; normalize before
    the OpenAI SDK appends ``/chat/completions``.
    """
    root = str(base_url or "").strip().rstrip("/")
    for suffix in ("/api/v1", "/api", "/v1"):
        if root.endswith(suffix):
            root = root[: -len(suffix)].rstrip("/")
            break
    return (root or "http://127.0.0.1:1234") + "/v1"


# =============================================================================
# Error Types
# =============================================================================

# Error code marking upstream rate-limit / usage-quota exhaustion (HTTP 429).
# Such failures are transient and re-authenticating cannot resolve them, so
# they must be kept distinct from missing/expired-credential errors.
CODEX_RATE_LIMITED_CODE = "codex_rate_limited"


class AuthError(RuntimeError):
    """Structured auth error with UX mapping hints."""

    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        code: Optional[str] = None,
        relogin_required: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.relogin_required = relogin_required


def is_rate_limited_auth_error(error: Exception) -> bool:
    """True when an :class:`AuthError` represents upstream rate-limiting / quota
    exhaustion rather than missing or invalid credentials.

    These failures are transient — re-authenticating cannot resolve them — so
    callers should surface a "retry later" notice and prefer a fallback chain
    instead of prompting the operator to run ``sparkii auth``.
    """
    return (
        isinstance(error, AuthError)
        and not error.relogin_required
        and error.code == CODEX_RATE_LIMITED_CODE
    )


def _parse_retry_after_seconds(headers: Any) -> Optional[int]:
    """Best-effort parse of a ``Retry-After`` header into whole seconds.

    Thin wrapper around :func:`agent.retry_utils.parse_retry_after_seconds`
    (delta-seconds and HTTP-date forms; negatives clamp to 0; missing or
    unparseable values return ``None``).
    """
    from agent.retry_utils import parse_retry_after_seconds

    seconds = parse_retry_after_seconds(headers)
    return None if seconds is None else int(seconds)


def format_auth_error(error: Exception) -> str:
    """Map auth failures to concise user-facing guidance."""
    if not isinstance(error, AuthError):
        return str(error)

    # Rate-limit / quota errors are not credential problems — never append the
    # "re-authenticate" remediation, which would mislead the operator.
    if is_rate_limited_auth_error(error):
        return str(error)

    if error.relogin_required:
        return f"{error} Run `sparkii model` to re-authenticate."

    if error.code == "subscription_required":
        return "No active paid subscription found. Please purchase/activate a subscription, then retry."

    if error.code == "insufficient_credits":
        return "Subscription credits are exhausted. Top up/renew credits, then retry."

    if error.code in {"subscription_expired", "no_usable_credits", "account_missing", "member_spend_cap_exceeded"}:
        return "No active paid subscription found. Please purchase/activate a subscription, then retry."

    if error.code == "temporarily_unavailable":
        return f"{error} Please retry in a few seconds."

    return str(error)




def _token_fingerprint(token: Any) -> Optional[str]:
    """Return a short hash fingerprint for telemetry without leaking token bytes."""
    if not isinstance(token, str):
        return None
    cleaned = token.strip()
    if not cleaned:
        return None
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:12]


def _oauth_trace_enabled() -> bool:
    raw = os.getenv("SPARKII_OAUTH_TRACE", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _oauth_trace(event: str, *, sequence_id: Optional[str] = None, **fields: Any) -> None:
    if not _oauth_trace_enabled():
        return
    payload: Dict[str, Any] = {"event": event}
    if sequence_id:
        payload["sequence_id"] = sequence_id
    payload.update(fields)
    logger.info("oauth_trace %s", json.dumps(payload, sort_keys=True, ensure_ascii=False))


# =============================================================================
# Auth Store — persistence layer for ~/.sparkii/auth.json
# =============================================================================



def _global_auth_file_path() -> Optional[Path]:
    """Return the global-root auth.json when the process is in profile mode.

    Returns ``None`` when the profile and global root resolve to the same
    directory (classic mode, or custom SPARKII_HOME that is not a profile).
    Used by read-only fallback paths so providers authed at the root are
    visible to profile processes that haven't configured them locally.

    See issue #18594 follow-up (credential_pool shadowing).
    """
    try:
        from sparkii_constants import get_default_sparkii_root
        global_root = get_default_sparkii_root()
    except Exception:
        return None
    profile_home = get_sparkii_home()
    try:
        if profile_home.resolve(strict=False) == global_root.resolve(strict=False):
            return None
    except Exception:
        if profile_home == global_root:
            return None
    # No pytest seat belt here: this is a pure read-only path, and
    # ``_load_global_auth_store()`` wraps the read in a try/except so an
    # unreadable global file can never break the profile process.  The
    # write-side seat belt still lives on ``_auth_file_path()`` where it
    # belongs (that's what protects the real user's auth store from being
    # corrupted by a mis-configured test).
    return global_root / "auth.json"


def _load_global_auth_store() -> Dict[str, Any]:
    """Load the global-root auth store (read-only fallback).

    Returns an empty dict when no global fallback exists (classic mode,
    or the global auth.json is absent). Never raises on missing file.

    Seat belt: under pytest, refuses to read the real user's
    ``~/.sparkii/auth.json`` even when SPARKII_HOME is set to a profile
    path. The hermetic conftest does not redirect ``HOME``, so
    ``get_default_sparkii_root()`` for a profile-shaped SPARKII_HOME can
    still resolve to the real user's home on a dev machine. That would
    leak real credentials into tests. This guard uses the unmodified
    ``HOME`` env var (what ``os.path.expanduser('~')`` would resolve to),
    not ``Path.home()``, because ``Path.home`` is sometimes monkeypatched
    by fixtures that want to relocate the global root to a tmp path.
    """
    global_path = _global_auth_file_path()
    if global_path is None or not global_path.exists():
        return {}
    if os.environ.get("PYTEST_CURRENT_TEST"):
        real_home_env = os.environ.get("HOME", "")
        if real_home_env:
            real_root = Path(real_home_env) / ".sparkii" / "auth.json"
            try:
                if global_path.resolve(strict=False) == real_root.resolve(strict=False):
                    return {}
            except Exception:
                pass
    try:
        return _load_auth_store(global_path)
    except Exception:
        # A malformed global store must not break profile reads. The
        # profile's own auth store is still authoritative.
        return {}










def _load_provider_state_with_source(
    auth_store: Dict[str, Any],
    provider_id: str,
) -> tuple[Optional[Dict[str, Any]], Optional[Path]]:
    """Return a provider state plus the auth.json path it came from.

    Most callers only need the state, but refresh paths that rotate single-use
    OAuth refresh tokens must write the updated token chain back to the same
    store they read. In profile mode ``_load_provider_state`` can read a
    global-root fallback state; persisting a rotated Nous refresh token only to
    the profile would leave the global/root store stale and cause the next
    process to replay an already-consumed refresh token.
    """
    providers = auth_store.get("providers")
    if isinstance(providers, dict):
        state = providers.get(provider_id)
        if isinstance(state, dict):
            return dict(state), _auth_file_path()

    global_path = _global_auth_file_path()
    global_store = _load_global_auth_store()
    if global_store:
        global_providers = global_store.get("providers")
        if isinstance(global_providers, dict):
            global_state = global_providers.get(provider_id)
            if isinstance(global_state, dict):
                return dict(global_state), global_path
    return None, None


@contextmanager
def _provider_state_transaction(provider_id: str):
    """Lock the active auth store and any global fallback source in order.

    Profile-backed refresh paths must take the global auth-store lock before
    any provider-specific shared-store lock. Re-reading the source after the
    target lock is acquired prevents both stale refreshes and whole-file lost
    updates without inverting the documented auth -> shared lock order.
    """
    with _auth_store_lock():
        auth_store = _load_auth_store()
        state, source_path = _load_provider_state_with_source(
            auth_store,
            provider_id,
        )
        active_path = _auth_file_path()
        if source_path is None or _same_path(source_path, active_path):
            yield auth_store, state, source_path
            return

        with _auth_store_lock(target_path=source_path):
            source_store = _load_auth_store(source_path)
            source_providers = source_store.get("providers")
            source_state = None
            if isinstance(source_providers, dict):
                raw_state = source_providers.get(provider_id)
                if isinstance(raw_state, dict):
                    source_state = dict(raw_state)
            yield auth_store, source_state, source_path


def _load_provider_state(auth_store: Dict[str, Any], provider_id: str) -> Optional[Dict[str, Any]]:
    """Return a provider's persisted state.

    In profile mode, falls back to the global-root ``auth.json`` when the
    profile has no entry for ``provider_id``. This mirrors the per-provider
    shadowing already used by ``read_credential_pool``: workers spawned in a
    profile can see providers (e.g. ``nous``) that were only authenticated at
    global scope. Once the user runs ``sparkii auth login <provider>`` inside
    the profile, the profile state fully shadows the global state on the next
    read. See issue #18594 follow-up.
    """
    state, _source_path = _load_provider_state_with_source(auth_store, provider_id)
    return state


def _save_provider_state(auth_store: Dict[str, Any], provider_id: str, state: Dict[str, Any]) -> None:
    providers = auth_store.setdefault("providers", {})
    if not isinstance(providers, dict):
        auth_store["providers"] = {}
        providers = auth_store["providers"]
    providers[provider_id] = state
    auth_store["active_provider"] = provider_id


def _save_provider_state_to_source(
    auth_store: Dict[str, Any],
    provider_id: str,
    state: Dict[str, Any],
    source_path: Optional[Path],
) -> None:
    """Persist provider state back to the auth store it was read from."""
    active_path = _auth_file_path()
    if source_path is None:
        source_path = active_path
    try:
        same_store = source_path.resolve(strict=False) == active_path.resolve(strict=False)
    except Exception:
        same_store = source_path == active_path
    if same_store:
        _save_provider_state(auth_store, provider_id, state)
        _save_auth_store(auth_store)
        return

    _persist_provider_state_to_store(
        provider_id,
        state,
        source_path,
        set_active=True,
    )


def _store_provider_state(
    auth_store: Dict[str, Any],
    provider_id: str,
    state: Dict[str, Any],
    *,
    set_active: bool = True,
) -> None:
    providers = auth_store.setdefault("providers", {})
    if not isinstance(providers, dict):
        auth_store["providers"] = {}
        providers = auth_store["providers"]
    providers[provider_id] = state
    if set_active:
        auth_store["active_provider"] = provider_id


def _persist_provider_state_to_store(
    provider_id: str,
    state: Dict[str, Any],
    target_path: Path,
    *,
    set_active: bool = False,
) -> Path:
    """Merge one provider into a specific auth store under that store's lock."""
    with _auth_store_lock(target_path=target_path):
        auth_store = _load_auth_store(target_path)
        _store_provider_state(
            auth_store,
            provider_id,
            dict(state),
            set_active=set_active,
        )
        return _save_auth_store(auth_store, target_path=target_path)


def mark_provider_active_if_unset(provider_id: str) -> None:
    """Set ``active_provider`` to *provider_id* only when none is set yet.

    Used by ``sparkii auth add`` OAuth paths that create credential-pool
    entries directly (no singleton ``providers.<id>`` block). Adding the
    very first credential for a provider should make it the active provider
    so the setup wizard's ``_model_section_has_credentials()`` check (which
    consults ``get_active_provider()``) does not report "No inference
    provider configured". Subsequent adds for an already-active setup leave
    the user's chosen active provider untouched.
    """
    with _auth_store_lock():
        auth_store = _load_auth_store()
        if not (auth_store.get("active_provider") or "").strip():
            auth_store["active_provider"] = provider_id
            _save_auth_store(auth_store)


def is_known_auth_provider(provider_id: str) -> bool:
    normalized = (provider_id or "").strip().lower()
    return normalized in PROVIDER_REGISTRY or normalized in SERVICE_PROVIDER_NAMES


def get_auth_provider_display_name(provider_id: str) -> str:
    normalized = (provider_id or "").strip().lower()
    if normalized in PROVIDER_REGISTRY:
        return PROVIDER_REGISTRY[normalized].name
    return SERVICE_PROVIDER_NAMES.get(normalized, provider_id)


def is_runtime_provider_routable(provider_id: str) -> bool:
    """Return whether runtime resolution recognizes a provider identity.

    This is a capability check, not a credential check. It follows the same
    alias/plugin-aware normalization as ``resolve_provider`` while preserving
    special runtime identities that intentionally live outside the registry.
    """
    normalized = (provider_id or "").strip().lower()
    if not normalized:
        return False
    if normalized in {"auto", "openrouter", "custom", "moa"}:
        return True
    if normalized.startswith("custom:"):
        return True
    try:
        resolve_provider(normalized)
    except AuthError:
        return False
    return True


def read_credential_pool(provider_id: Optional[str] = None) -> Dict[str, Any]:
    """Return the persisted credential pool, or one provider slice.

    In profile mode, the profile's credential pool is authoritative. If a
    provider has no entries in the profile, entries from the global-root
    ``auth.json`` are used as a read-only fallback — so workers spawned in a
    profile can see providers that were only authenticated at global scope.

    Profile entries always win: the global fallback only applies per-provider
    when the profile has zero entries for that provider. Once the user runs
    ``sparkii auth add <provider>`` inside the profile, profile entries
    fully shadow global for that provider on the next read.

    Writes always go to the profile (``write_credential_pool`` is unchanged).
    See issue #18594 follow-up.
    """
    auth_store = _load_auth_store()
    pool = auth_store.get("credential_pool")
    if not isinstance(pool, dict):
        pool = {}

    global_pool: Dict[str, Any] = {}
    global_store = _load_global_auth_store()
    maybe_global_pool = global_store.get("credential_pool") if global_store else None
    if isinstance(maybe_global_pool, dict):
        global_pool = maybe_global_pool

    if provider_id is None:
        merged = dict(pool)
        for gp_key, gp_entries in global_pool.items():
            if not isinstance(gp_entries, list) or not gp_entries:
                continue
            # Per-provider shadowing: profile wins whenever it has ANY entries.
            existing = merged.get(gp_key)
            if isinstance(existing, list) and existing:
                continue
            merged[gp_key] = list(gp_entries)
        return merged

    provider_entries = pool.get(provider_id)
    if isinstance(provider_entries, list) and provider_entries:
        return list(provider_entries)
    # Profile has no entries for this provider — fall back to global.
    global_entries = global_pool.get(provider_id)
    return list(global_entries) if isinstance(global_entries, list) else []


_POOL_STATUS_FIELDS = (
    "last_status",
    "last_status_at",
    "last_error_code",
    "last_error_reason",
    "last_error_message",
    "last_error_reset_at",
)


def _merge_disk_cooldown_state(
    entry: Dict[str, Any],
    disk_entry: Optional[Dict[str, Any]],
    provider_id: str,
) -> Dict[str, Any]:
    """Keep a newer on-disk cooldown/quarantine over a stale in-memory one.

    ``write_credential_pool`` callers persist an in-memory snapshot that may
    predate another process marking the same credential exhausted or dead
    (last-writer-wins lost update).  Without this merge, process B's later
    rewrite resurrects a rate-limited key as healthy and both processes
    resume hammering it.  Adopt the on-disk status fields only when they are
    strictly more recent (by ``last_status_at``) AND still binding — a DEAD
    marker, or an EXHAUSTED cooldown that has not yet expired.  Expired
    cooldowns are not resurrected, so the pool's own expiry-clear (which
    resets ``last_status_at`` to None) is never overridden.
    """
    if not isinstance(disk_entry, dict):
        return entry
    try:
        from agent.credential_pool import (
            PooledCredential,
            STATUS_DEAD,
            STATUS_EXHAUSTED,
            _exhausted_until,
            _parse_absolute_timestamp,
        )

        disk_status = disk_entry.get("last_status")
        if disk_status not in (STATUS_DEAD, STATUS_EXHAUSTED):
            return entry
        # A token change means the caller re-authed/refreshed this entry and
        # intentionally cleared its status (e.g. _sync_codex_entry_from_
        # auth_store after a fresh device-code login) — never resurrect the
        # old cooldown onto fresh credentials.
        mem_access = entry.get("access_token") or ""
        disk_access = disk_entry.get("access_token") or ""
        if mem_access and disk_access and mem_access != disk_access:
            return entry
        disk_ts = _parse_absolute_timestamp(disk_entry.get("last_status_at")) or 0.0
        mem_ts = _parse_absolute_timestamp(entry.get("last_status_at")) or 0.0
        if disk_ts <= mem_ts:
            return entry
        if disk_status == STATUS_EXHAUSTED:
            until = _exhausted_until(
                PooledCredential.from_dict(provider_id, disk_entry)
            )
            if until is None or until <= time.time():
                return entry
        merged_entry = dict(entry)
        for status_field in _POOL_STATUS_FIELDS:
            merged_entry[status_field] = disk_entry.get(status_field)
        return merged_entry
    except Exception:  # pragma: no cover - best-effort merge
        return entry


def write_credential_pool(
    provider_id: str,
    entries: List[Dict[str, Any]],
    *,
    removed_ids: Optional[Iterable[str]] = None,
) -> Path:
    """Persist one provider's credential pool under auth.json.

    This is the final disk-boundary guard for borrowed/reference-only
    credentials. Callers may pass raw dictionaries, so sanitize here even when
    ``PooledCredential.to_dict()`` already did the same work upstream.

    Re-read the on-disk pool under the same lock and merge entries present on
    disk but missing from ``entries``. Those were added by another process after
    the caller loaded its in-memory snapshot; without this merge a later
    rotation/exhaustion rewrite drops the concurrent credential.

    For entries present on BOTH sides, status fields are merged by
    ``last_status_at`` recency via ``_merge_disk_cooldown_state`` so a stale
    snapshot cannot erase a cooldown/quarantine another process just wrote.

    Pass ``removed_ids`` for entries the caller intentionally removed, so the
    merge does not resurrect them from the on-disk copy.
    """
    removed = {rid for rid in (removed_ids or ()) if rid}
    with _auth_store_lock():
        auth_store = _load_auth_store()
        pool = auth_store.get("credential_pool")
        if not isinstance(pool, dict):
            pool = {}
            auth_store["credential_pool"] = pool
        sanitized_entries = [
            sanitize_borrowed_credential_payload(entry, provider_id)
            if isinstance(entry, dict) else entry
            for entry in entries
        ]
        existing = pool.get(provider_id)
        existing_list = existing if isinstance(existing, list) else []
        existing_by_id = {
            entry.get("id"): entry
            for entry in existing_list
            if isinstance(entry, dict) and entry.get("id")
        }
        new_ids = {
            entry.get("id")
            for entry in sanitized_entries
            if isinstance(entry, dict) and entry.get("id")
        }
        merged: List[Dict[str, Any]] = [
            _merge_disk_cooldown_state(
                entry, existing_by_id.get(entry.get("id")), provider_id
            )
            if isinstance(entry, dict)
            else entry
            for entry in sanitized_entries
        ]
        for disk_entry in existing_list:
            if not isinstance(disk_entry, dict):
                continue
            disk_id = disk_entry.get("id")
            if not disk_id or disk_id in new_ids or disk_id in removed:
                continue
            merged.append(sanitize_borrowed_credential_payload(disk_entry, provider_id))
        pool[provider_id] = merged
        return _save_auth_store(auth_store)


from core.credential_sources import (
    is_source_suppressed,
    suppress_credential_source,
    unsuppress_credential_source,
)







def get_provider_auth_state(provider_id: str) -> Optional[Dict[str, Any]]:
    """Return persisted auth state for a provider, or None.

    In profile mode, ``_load_provider_state`` already falls back to the
    global-root ``auth.json`` per-provider when the profile has no entry —
    so this is now a thin convenience wrapper. Profile state always wins
    when present. Writes (``_save_auth_store`` / ``persist_*_credentials``)
    are unchanged — they still target the profile only. This mirrors
    ``read_credential_pool``'s per-provider shadowing semantics so that
    ``_seed_from_singletons`` can reseed a profile's credential pool from
    global-scope provider state (e.g. a globally-authenticated Anthropic
    OAuth or Nous device-code session). See issue #18594 follow-up.
    """
    auth_store = _load_auth_store()
    return _load_provider_state(auth_store, provider_id)


def get_active_provider() -> Optional[str]:
    """Return the currently active provider ID from auth store."""
    auth_store = _load_auth_store()
    return auth_store.get("active_provider")


def is_provider_explicitly_configured(provider_id: str) -> bool:
    """Return True only if the user has explicitly configured this provider.

    Checks:
      1. active_provider in auth.json matches
      2. model.provider in config.yaml matches
      3. Provider-specific env vars are set (e.g. ANTHROPIC_API_KEY)

    This is used to gate auto-discovery of external credentials (e.g.
    Claude Code's ~/.claude/.credentials.json) so they are never used
    without the user's explicit choice.  See PR #4210 for the same
    pattern applied to the setup wizard gate.
    """
    normalized = (provider_id or "").strip().lower()

    # 1. Check auth.json active_provider
    try:
        auth_store = _load_auth_store()
        active = (auth_store.get("active_provider") or "").strip().lower()
        if active and active == normalized:
            return True
    except Exception:
        pass

    # 2. Check config.yaml model.provider and other explicit provider slots.
    try:
        from core.config import load_config
        cfg = load_config()
        model_cfg = cfg.get("model")
        if isinstance(model_cfg, dict):
            cfg_provider = (model_cfg.get("provider") or "").strip().lower()
            if cfg_provider == normalized:
                return True

        # MoA presets are explicit model selections too.  A user who configured
        # ``provider: anthropic`` as a MoA advisor/aggregator has opted Sparkii
        # into using Anthropic credentials for that slot even when the main
        # session model is another provider.  Without this, Claude Code OAuth
        # entries are pruned/ignored by credential_pool.load_pool("anthropic"),
        # so MoA Anthropic advisors fail with "no ANTHROPIC_API_KEY" while the
        # normal model picker says Anthropic is logged in.
        def _slot_matches_provider(slot):
            return (
                isinstance(slot, dict)
                and (slot.get("provider") or "").strip().lower() == normalized
            )

        moa_cfg = cfg.get("moa")
        if isinstance(moa_cfg, dict):
            for slot in moa_cfg.get("reference_models") or []:
                if _slot_matches_provider(slot):
                    return True
            if _slot_matches_provider(moa_cfg.get("aggregator")):
                return True
            presets = moa_cfg.get("presets")
            if isinstance(presets, dict):
                for preset in presets.values():
                    if not isinstance(preset, dict):
                        continue
                    for slot in preset.get("reference_models") or []:
                        if _slot_matches_provider(slot):
                            return True
                    if _slot_matches_provider(preset.get("aggregator")):
                        return True
    except Exception:
        pass

    # 3. Check provider-specific env vars
    # Exclude CLAUDE_CODE_OAUTH_TOKEN — it's set by Claude Code itself,
    # not by the user explicitly configuring anthropic in Sparkii.
    _IMPLICIT_ENV_VARS = {"CLAUDE_CODE_OAUTH_TOKEN"}
    pconfig = PROVIDER_REGISTRY.get(normalized)
    # Fallback to ProviderDef from models.dev catalog when the provider
    # isn't in the manually-maintained PROVIDER_REGISTRY (e.g. openrouter).
    # Both expose .auth_type and .api_key_env_vars with the same shape.
    if pconfig is None:
        from sparkii_cli.providers import get_provider
        pconfig = get_provider(normalized)
    if pconfig and pconfig.auth_type == "api_key":
        for env_var in pconfig.api_key_env_vars:
            if env_var in _IMPLICIT_ENV_VARS:
                continue
            if has_usable_secret(os.getenv(env_var, "")):
                return True

    # 4. Check persisted credential-pool entries that came from EXPLICIT flows
    # the user initiated inside Sparkii (manual add / device-code / PKCE), plus
    # env-backed pool entries. This intentionally excludes ambient borrowed
    # sources like gh_cli / claude_code / qwen-cli.
    try:
        for entry in read_credential_pool(normalized):
            if not isinstance(entry, dict):
                continue
            source = str(entry.get("source") or "").strip().lower()
            if not source:
                continue
            if source.startswith("env:"):
                # A stale env-seeded pool entry survives in auth.json after
                # the user deletes the env var (#55790) — only count it when
                # the referenced var still resolves to a usable secret NOW.
                env_var = entry.get("source", "").split(":", 1)[1].strip()
                if env_var and has_usable_secret(os.getenv(env_var, "")):
                    return True
                continue
            if (
                source in {"device_code", "loopback_pkce", "sparkii_pkce", "manual"}
                or source.startswith("manual:")
            ):
                return True
    except Exception:
        pass

    return False


def clear_provider_auth(provider_id: Optional[str] = None) -> bool:
    """
    Clear auth state for a provider. Used by `sparkii logout`.
    If provider_id is None, clears the active provider.
    Returns True if something was cleared.
    """
    with _auth_store_lock():
        auth_store = _load_auth_store()
        target = provider_id or auth_store.get("active_provider")
        if not target:
            return False

        providers = auth_store.get("providers", {})
        if not isinstance(providers, dict):
            providers = {}
            auth_store["providers"] = providers

        pool = auth_store.get("credential_pool")
        if not isinstance(pool, dict):
            pool = {}
            auth_store["credential_pool"] = pool

        cleared = False
        if target in providers:
            del providers[target]
            cleared = True
        if target in pool:
            del pool[target]
            cleared = True

        if auth_store.get("active_provider") == target:
            auth_store["active_provider"] = None
            cleared = True

        if not cleared:
            return False
        _save_auth_store(auth_store)
    return True


def deactivate_provider() -> None:
    """
    Clear active_provider in auth.json without deleting credentials.
    Used when the user switches to a non-OAuth provider (OpenRouter, custom)
    so auto-resolution doesn't keep picking the OAuth provider.
    """
    with _auth_store_lock():
        auth_store = _load_auth_store()
        auth_store["active_provider"] = None
        _save_auth_store(auth_store)


# =============================================================================
# Provider Resolution — picks which provider to use
# =============================================================================


def _get_config_hint_for_unknown_provider(provider_name: str) -> str:
    """Return a helpful hint string when provider resolution fails.

    Checks for common config.yaml mistakes (malformed custom_providers, etc.)
    and returns a human-readable diagnostic, or empty string if nothing found.
    """
    try:
        from core.config import validate_config_structure
        issues = validate_config_structure()
        if not issues:
            return ""

        lines = ["Config issue detected — run 'sparkii doctor' for full diagnostics:"]
        for ci in issues:
            prefix = "ERROR" if ci.severity == "error" else "WARNING"
            lines.append(f"  [{prefix}] {ci.message}")
            # Show first line of hint
            first_hint = ci.hint.splitlines()[0] if ci.hint else ""
            if first_hint:
                lines.append(f"    → {first_hint}")
        return "\n".join(lines)
    except Exception:
        return ""


def resolve_provider(
    requested: Optional[str] = None,
    *,
    explicit_api_key: Optional[str] = None,
    explicit_base_url: Optional[str] = None,
) -> str:
    """
    Determine which inference provider to use.

    Priority (when requested="auto" or None) — explicit user intent wins over a
    stale logged-in OAuth provider (#29285):
    1. Explicit CLI api_key/base_url -> "openrouter"
    2. config.yaml `model.provider`
    3. OPENAI_API_KEY / OPENROUTER_API_KEY env vars -> "openrouter"
    4. OpenRouter credential pool
    5. Provider-specific API keys (GLM, Kimi, MiniMax, ...) -> that provider
    6. auth.json `active_provider` (logged-in OAuth) — last-resort fallback
    7. AWS Bedrock credential chain
    8. Error (no provider configured)
    """
    normalized = (requested or "auto").strip().lower()

    # Normalize provider aliases
    _PROVIDER_ALIASES = {
        "claude": "anthropic", "claude-code": "anthropic",
        "tencent": "tencent-tokenhub", "tokenhub": "tencent-tokenhub",
        "tencent-cloud": "tencent-tokenhub", "tencentmaas": "tencent-tokenhub",
        "lmstudio": "lmstudio", "lm-studio": "lmstudio", "lm_studio": "lmstudio",
        # Local server aliases — route through the generic custom provider
        "ollama": "custom", "vllm": "custom", "llamacpp": "custom",
        "llama.cpp": "custom", "llama-cpp": "custom",
    }
    # Extend with aliases declared in plugins/model-providers/<name>/ that aren't already mapped.
    # This keeps providers/ as the single source for new aliases while the
    # hardcoded dict above remains authoritative for existing ones.
    try:
        from providers import list_providers as _lp
        for _pp in _lp():
            for _alias in _pp.aliases:
                if _alias not in _PROVIDER_ALIASES:
                    _PROVIDER_ALIASES[_alias] = _pp.name
    except Exception:
        pass
    normalized = _PROVIDER_ALIASES.get(normalized, normalized)

    if normalized == "openrouter":
        return "openrouter"
    if normalized == "custom":
        return "custom"
    if normalized in PROVIDER_REGISTRY:
        return normalized
    if normalized != "auto":
        # Check for common config.yaml issues that cause this error
        _config_hint = _get_config_hint_for_unknown_provider(normalized)
        msg = f"Unknown provider '{normalized}'."
        if _config_hint:
            msg += f"\n\n{_config_hint}"
        else:
            msg += " Check 'sparkii model' for available providers, or run 'sparkii doctor' to diagnose config issues."
        raise AuthError(msg, code="invalid_provider")

    # Explicit one-off CLI creds always mean openrouter/custom
    if explicit_api_key or explicit_base_url:
        return "openrouter"

    # Provider precedence for the auto-path (#29285): explicit user intent must
    # win over a stale logged-in OAuth `active_provider`. Order matches the
    # docstring: 1. explicit CLI creds  2. config.yaml `model.provider`
    # 3. OPENAI/OPENROUTER env keys  4. OpenRouter pool  5. provider-specific
    # env keys  6. auth.json `active_provider` (OAuth)  7. Bedrock  8. error.
    # The normal chat/gateway path resolves config.provider upstream in
    # resolve_requested_provider() before ever reaching "auto"; this duplicate
    # check is the safety net for the lone direct caller (main.py resolve_provider
    # ("auto")) and any future bypass of that stage.
    _model_cfg: Any = None
    try:
        from core.config import load_config

        _model_cfg = (load_config() or {}).get("model")
        if isinstance(_model_cfg, dict):
            _cfg_provider = _model_cfg.get("provider")
            if isinstance(_cfg_provider, str) and _cfg_provider.strip().lower() in PROVIDER_REGISTRY:
                return _cfg_provider.strip().lower()
    except Exception as e:
        logger.debug("Could not read config.yaml model.provider for auto-resolution: %s", e)

    if has_usable_secret(os.getenv("OPENAI_API_KEY")) or has_usable_secret(os.getenv("OPENROUTER_API_KEY")):
        return "openrouter"

    # Auto-detect an OpenRouter credential added via `sparkii auth add openrouter`
    # (manual pool entry, no env var). Without this, a key that only lives in
    # the credential pool is invisible to auto-detection — the user sees
    # `sparkii auth list` showing the credential while requests go out with no
    # Authorization header ("HTTP 401: Missing Authentication header"). The
    # env-var check above only covers keys exported as OPENROUTER_API_KEY /
    # OPENAI_API_KEY. See issue #42130.
    try:
        from agent.credential_pool import load_pool as _load_pool

        if _load_pool("openrouter").has_credentials():
            return "openrouter"
    except Exception as e:
        logger.debug("Could not check OpenRouter credential pool: %s", e)

    # Determine the logged-in OAuth provider up front so the env-key loop below
    # can WARN when an exported API key preempts it (#29285 transparency). The
    # actual OAuth fallback (tier 6) still happens later if nothing else matches.
    _oauth_active: Optional[str] = None
    try:
        _store = _load_auth_store()
        _maybe = _store.get("active_provider")
        if _maybe and _maybe in PROVIDER_REGISTRY and get_auth_status(_maybe).get("logged_in"):
            _oauth_active = _maybe
    except Exception as e:
        logger.debug("Could not pre-read active auth provider: %s", e)

    # Auto-detect API-key providers by checking their env vars
    for pid, pconfig in PROVIDER_REGISTRY.items():
        if pconfig.auth_type != "api_key":
            continue
        # GitHub tokens are commonly present for repo/tool access but should not
        # hijack inference auto-selection unless the user explicitly chooses
        # Copilot/GitHub Models as the provider. LM Studio is a local server
        # whose availability isn't implied by LM_API_KEY presence (it may be
        # offline, and the no-auth setup uses a placeholder value), so it
        # also requires explicit selection.
        if pid in {"copilot", "lmstudio"}:
            continue
        for env_var in pconfig.api_key_env_vars:
            if has_usable_secret(os.getenv(env_var, "")):
                # An exported API key now wins over a logged-in OAuth provider
                # (the #29285 fix). Surface that so a user who deliberately uses
                # OAuth but has a stale key in ~/.sparkii/.env isn't silently
                # switched without knowing why.
                if _oauth_active and _oauth_active != pid:
                    logger.warning(
                        "Provider resolved to %r via %s, preempting your "
                        "logged-in OAuth provider %r. If you meant to use the "
                        "OAuth login, unset %s or set `model.provider` "
                        "explicitly.",
                        pid, env_var, _oauth_active, env_var,
                    )
                return pid

    # Logged-in OAuth provider (auth.json `active_provider`) — a LAST-RESORT
    # fallback, chosen only when the user expressed no other preference above.
    # Previously this sat ABOVE the env-var/config checks, so a stale OAuth
    # login silently overrode an explicit `model.provider` or an exported API
    # key (#29285). Demoted here so explicit intent always wins.
    if _oauth_active:
        # Surface the silent-override case the issue reported: a populated
        # `model` config that lacks a `provider` key falls through to OAuth.
        if isinstance(_model_cfg, dict) and _model_cfg and not _model_cfg.get("provider"):
            logger.warning(
                "Provider resolved to logged-in OAuth provider %r because "
                "config.yaml `model` has no `provider` key. If you meant a "
                "different provider, set `model.provider` explicitly.",
                _oauth_active,
            )
        return _oauth_active

    # AWS Bedrock — detect via boto3 credential chain (IAM roles, SSO, env vars).
    # This runs after API-key providers so explicit keys always win.
    try:
        from agent.bedrock_adapter import has_aws_credentials
        if has_aws_credentials():
            return "bedrock"
    except ImportError:
        pass  # boto3 not installed — skip Bedrock auto-detection

    raise AuthError(
        "No inference provider configured. Run 'sparkii model' to choose a "
        "provider and model, or set an API key (OPENROUTER_API_KEY, "
        "OPENAI_API_KEY, etc.) in ~/.sparkii/.env.",
        code="no_provider_configured",
    )


# =============================================================================
# Timestamp / TTL helpers
# =============================================================================

def _parse_iso_timestamp(value: Any) -> Optional[float]:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _is_expiring(expires_at_iso: Any, skew_seconds: int) -> bool:
    expires_epoch = _parse_iso_timestamp(expires_at_iso)
    if expires_epoch is None:
        return True
    return expires_epoch <= (time.time() + skew_seconds)


def _coerce_ttl_seconds(expires_in: Any) -> int:
    try:
        ttl = int(expires_in)
    except Exception:
        ttl = 0
    return max(0, ttl)


def _optional_base_url(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().rstrip("/")
    return cleaned if cleaned else None



# Allowlist of valid Nous Portal hosts. A portal_base_url outside this
# set is treated as a misconfiguration and falls back to the default.
# "localhost" / "127.0.0.1" are valid for local development and testing.




# Allowlist of hosts the Nous Portal proxy is willing to forward inference
# JWTs to. Sending a bearer anywhere else would leak it.
#
# This is consulted only for URLs coming from the NETWORK side (Portal
# refresh responses). User-controlled env-var overrides
# (NOUS_INFERENCE_BASE_URL) bypass validation — that's the documented
# dev/staging escape hatch and the env source is already trusted (the
# user set it themselves).








def _decode_jwt_claims(token: Any) -> Dict[str, Any]:
    if not isinstance(token, str) or token.count(".") != 2:
        return {}
    payload = token.split(".")[1]
    payload += "=" * ((4 - len(payload) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload.encode("utf-8"))
        claims = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
    return claims if isinstance(claims, dict) else {}


def _scope_values(raw_scope: Any) -> set[str]:
    # OAuth token responses normally return a space-separated string. Keep
    # collection support for JWT ``scp`` claims and older stored test fixtures.
    scopes: set[str] = set()
    if isinstance(raw_scope, str):
        for part in raw_scope.replace(",", " ").split():
            cleaned = part.strip()
            if cleaned:
                scopes.add(cleaned)
    elif isinstance(raw_scope, (list, tuple, set, frozenset)):
        for item in raw_scope:
            if isinstance(item, str):
                scopes.update(_scope_values(item))
    return scopes






































# =============================================================================
# Spotify auth — PKCE tokens stored in ~/.sparkii/auth.json
# =============================================================================


def _spotify_scope_list(raw_scope: Optional[str] = None) -> List[str]:
    scope_text = (raw_scope or DEFAULT_SPOTIFY_SCOPE).strip()
    scopes = [part for part in scope_text.split() if part]
    seen: set[str] = set()
    ordered: List[str] = []
    for scope in scopes:
        if scope not in seen:
            seen.add(scope)
            ordered.append(scope)
    return ordered


def _spotify_scope_string(raw_scope: Optional[str] = None) -> str:
    return " ".join(_spotify_scope_list(raw_scope))


def _spotify_client_id(
    explicit: Optional[str] = None,
    state: Optional[Dict[str, Any]] = None,
) -> str:
    from core.config import get_env_value

    candidates = (
        explicit,
        get_env_value("SPARKII_SPOTIFY_CLIENT_ID"),
        get_env_value("SPOTIFY_CLIENT_ID"),
        state.get("client_id") if isinstance(state, dict) else None,
    )
    for candidate in candidates:
        cleaned = str(candidate or "").strip()
        if cleaned:
            return cleaned
    raise AuthError(
        "Spotify client_id is required. Set SPARKII_SPOTIFY_CLIENT_ID or pass --client-id.",
        provider="spotify",
        code="spotify_client_id_missing",
    )


def _spotify_redirect_uri(
    explicit: Optional[str] = None,
    state: Optional[Dict[str, Any]] = None,
) -> str:
    from core.config import get_env_value

    candidates = (
        explicit,
        get_env_value("SPARKII_SPOTIFY_REDIRECT_URI"),
        get_env_value("SPOTIFY_REDIRECT_URI"),
        state.get("redirect_uri") if isinstance(state, dict) else None,
        DEFAULT_SPOTIFY_REDIRECT_URI,
    )
    for candidate in candidates:
        cleaned = str(candidate or "").strip()
        if cleaned:
            return cleaned
    return DEFAULT_SPOTIFY_REDIRECT_URI


def _spotify_api_base_url(state: Optional[Dict[str, Any]] = None) -> str:
    from core.config import get_env_value

    candidates = (
        get_env_value("SPARKII_SPOTIFY_API_BASE_URL"),
        state.get("api_base_url") if isinstance(state, dict) else None,
        DEFAULT_SPOTIFY_API_BASE_URL,
    )
    for candidate in candidates:
        cleaned = str(candidate or "").strip().rstrip("/")
        if cleaned:
            return cleaned
    return DEFAULT_SPOTIFY_API_BASE_URL


def _spotify_accounts_base_url(state: Optional[Dict[str, Any]] = None) -> str:
    from core.config import get_env_value

    candidates = (
        get_env_value("SPARKII_SPOTIFY_ACCOUNTS_BASE_URL"),
        state.get("accounts_base_url") if isinstance(state, dict) else None,
        DEFAULT_SPOTIFY_ACCOUNTS_BASE_URL,
    )
    for candidate in candidates:
        cleaned = str(candidate or "").strip().rstrip("/")
        if cleaned:
            return cleaned
    return DEFAULT_SPOTIFY_ACCOUNTS_BASE_URL


def _spotify_code_verifier(length: int = 64) -> str:
    raw = base64.urlsafe_b64encode(os.urandom(length)).decode("ascii")
    return raw.rstrip("=")[:128]


def _spotify_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _oauth_pkce_code_verifier(length: int = 64) -> str:
    raw = base64.urlsafe_b64encode(os.urandom(length)).decode("ascii")
    return raw.rstrip("=")[:128]


def _oauth_pkce_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _spotify_build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str,
    code_challenge: str,
    accounts_base_url: str,
) -> str:
    query = urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
    })
    return f"{accounts_base_url}/authorize?{query}"


def _spotify_validate_redirect_uri(redirect_uri: str) -> tuple[str, int, str]:
    parsed = urlparse(redirect_uri)
    if parsed.scheme != "http":
        raise AuthError(
            "Spotify PKCE redirect_uri must use http://localhost or http://127.0.0.1.",
            provider="spotify",
            code="spotify_redirect_invalid",
        )
    host = parsed.hostname or ""
    if host not in {"127.0.0.1", "localhost"}:
        raise AuthError(
            "Spotify PKCE redirect_uri must point to localhost or 127.0.0.1.",
            provider="spotify",
            code="spotify_redirect_invalid",
        )
    if not parsed.port:
        raise AuthError(
            "Spotify PKCE redirect_uri must include an explicit localhost port.",
            provider="spotify",
            code="spotify_redirect_invalid",
        )
    return host, parsed.port, parsed.path or "/"


def _make_spotify_callback_handler(expected_path: str) -> tuple[type[BaseHTTPRequestHandler], dict[str, Any]]:
    result: dict[str, Any] = {
        "code": None,
        "state": None,
        "error": None,
        "error_description": None,
    }

    class _SpotifyCallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != expected_path:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not found.")
                return

            params = parse_qs(parsed.query)
            result["code"] = params.get("code", [None])[0]
            result["state"] = params.get("state", [None])[0]
            result["error"] = params.get("error", [None])[0]
            result["error_description"] = params.get("error_description", [None])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if result["error"]:
                body = "<html><body><h1>Spotify authorization failed.</h1>You can close this tab.</body></html>"
            else:
                body = "<html><body><h1>Spotify authorization received.</h1>You can close this tab.</body></html>"
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    return _SpotifyCallbackHandler, result


def _spotify_wait_for_callback(
    redirect_uri: str,
    *,
    timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    host, port, path = _spotify_validate_redirect_uri(redirect_uri)
    handler_cls, result = _make_spotify_callback_handler(path)

    class _ReuseHTTPServer(HTTPServer):
        allow_reuse_address = True

    try:
        server = _ReuseHTTPServer((host, port), handler_cls)
    except OSError as exc:
        raise AuthError(
            f"Could not bind Spotify callback server on {host}:{port}: {exc}",
            provider="spotify",
            code="spotify_callback_bind_failed",
        ) from exc

    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    deadline = time.monotonic() + max(5.0, timeout_seconds)
    try:
        while time.monotonic() < deadline:
            if result["code"] or result["error"]:
                return result
            time.sleep(0.1)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1.0)
    raise AuthError(
        "Spotify authorization timed out waiting for the local callback.",
        provider="spotify",
        code="spotify_callback_timeout",
    )


def _spotify_token_payload_to_state(
    token_payload: Dict[str, Any],
    *,
    client_id: str,
    redirect_uri: str,
    requested_scope: str,
    accounts_base_url: str,
    api_base_url: str,
    previous_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    expires_in = _coerce_ttl_seconds(token_payload.get("expires_in", 0))
    expires_at = datetime.fromtimestamp(now.timestamp() + expires_in, tz=timezone.utc)
    state = dict(previous_state or {})
    state.update({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "accounts_base_url": accounts_base_url,
        "api_base_url": api_base_url,
        "scope": requested_scope,
        "granted_scope": str(token_payload.get("scope") or requested_scope).strip(),
        "token_type": str(token_payload.get("token_type", "Bearer") or "Bearer").strip() or "Bearer",
        "access_token": str(token_payload.get("access_token", "") or "").strip(),
        "refresh_token": str(
            token_payload.get("refresh_token")
            or state.get("refresh_token")
            or ""
        ).strip(),
        "obtained_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "expires_in": expires_in,
        "auth_type": "oauth_pkce",
    })
    return state


def _spotify_exchange_code_for_tokens(
    *,
    client_id: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    accounts_base_url: str,
    timeout_seconds: float = 20.0,
) -> Dict[str, Any]:
    try:
        response = httpx.post(
            f"{accounts_base_url}/api/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_id": client_id,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            timeout=timeout_seconds,
        )
    except Exception as exc:
        raise AuthError(
            f"Spotify token exchange failed: {exc}",
            provider="spotify",
            code="spotify_token_exchange_failed",
        ) from exc

    if response.status_code >= 400:
        detail = response.text.strip()
        raise AuthError(
            "Spotify token exchange failed."
            + (f" Response: {detail}" if detail else ""),
            provider="spotify",
            code="spotify_token_exchange_failed",
        )
    payload = response.json()
    if not isinstance(payload, dict) or not str(payload.get("access_token", "") or "").strip():
        raise AuthError(
            "Spotify token response did not include an access_token.",
            provider="spotify",
            code="spotify_token_exchange_invalid",
        )
    return payload


def _refresh_spotify_oauth_state(
    state: Dict[str, Any],
    *,
    timeout_seconds: float = 20.0,
) -> Dict[str, Any]:
    refresh_token = str(state.get("refresh_token", "") or "").strip()
    if not refresh_token:
        raise AuthError(
            "Spotify refresh token missing. Run `sparkii auth spotify` again.",
            provider="spotify",
            code="spotify_refresh_token_missing",
            relogin_required=True,
        )

    client_id = _spotify_client_id(state=state)
    accounts_base_url = _spotify_accounts_base_url(state)
    try:
        response = httpx.post(
            f"{accounts_base_url}/api/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
            timeout=timeout_seconds,
        )
    except Exception as exc:
        raise AuthError(
            f"Spotify token refresh failed: {exc}",
            provider="spotify",
            code="spotify_refresh_failed",
        ) from exc

    if response.status_code >= 400:
        detail = response.text.strip()
        raise AuthError(
            "Spotify token refresh failed. Run `sparkii auth spotify` again."
            + (f" Response: {detail}" if detail else ""),
            provider="spotify",
            code="spotify_refresh_failed",
            relogin_required=True,
        )

    payload = response.json()
    if not isinstance(payload, dict) or not str(payload.get("access_token", "") or "").strip():
        raise AuthError(
            "Spotify refresh response did not include an access_token.",
            provider="spotify",
            code="spotify_refresh_invalid",
            relogin_required=True,
        )

    return _spotify_token_payload_to_state(
        payload,
        client_id=client_id,
        redirect_uri=_spotify_redirect_uri(state=state),
        requested_scope=str(state.get("scope") or DEFAULT_SPOTIFY_SCOPE),
        accounts_base_url=accounts_base_url,
        api_base_url=_spotify_api_base_url(state),
        previous_state=state,
    )


def resolve_spotify_runtime_credentials(
    *,
    force_refresh: bool = False,
    refresh_if_expiring: bool = True,
    refresh_skew_seconds: int = SPOTIFY_ACCESS_TOKEN_REFRESH_SKEW_SECONDS,
) -> Dict[str, Any]:
    with _auth_store_lock():
        auth_store = _load_auth_store()
        state = _load_provider_state(auth_store, "spotify")
        if not state:
            raise AuthError(
                "Spotify is not authenticated. Run `sparkii auth spotify` first.",
                provider="spotify",
                code="spotify_auth_missing",
                relogin_required=True,
            )

        should_refresh = bool(force_refresh)
        if not should_refresh and refresh_if_expiring:
            should_refresh = _is_expiring(state.get("expires_at"), refresh_skew_seconds)
        if should_refresh:
            try:
                state = _refresh_spotify_oauth_state(state)
                _store_provider_state(auth_store, "spotify", state, set_active=False)
                _save_auth_store(auth_store)
            except AuthError as exc:
                if exc.relogin_required and state.get("refresh_token"):
                    # Terminal refresh failure — clear dead tokens from auth.json
                    # so subsequent calls fail fast without a network retry.
                    # Mirrors the Nous / xAI-OAuth / Codex-OAuth / MiniMax pattern.
                    for _k in ("access_token", "refresh_token", "expires_at", "expires_in", "obtained_at"):
                        state.pop(_k, None)
                    state["last_auth_error"] = {
                        "provider": "spotify",
                        "code": exc.code or "refresh_failed",
                        "message": str(exc),
                        "reason": "runtime_refresh_failure",
                        "relogin_required": True,
                        "at": datetime.now(timezone.utc).isoformat(),
                    }
                    try:
                        _store_provider_state(auth_store, "spotify", state, set_active=False)
                        _save_auth_store(auth_store)
                    except Exception as _save_exc:
                        logger.debug("Spotify OAuth: failed to persist quarantined state: %s", _save_exc)
                raise

    access_token = str(state.get("access_token", "") or "").strip()
    if not access_token:
        raise AuthError(
            "Spotify access token missing. Run `sparkii auth spotify` again.",
            provider="spotify",
            code="spotify_access_token_missing",
            relogin_required=True,
        )

    return {
        "provider": "spotify",
        "access_token": access_token,
        "api_key": access_token,
        "token_type": str(state.get("token_type", "Bearer") or "Bearer"),
        "base_url": _spotify_api_base_url(state),
        "scope": str(state.get("granted_scope") or state.get("scope") or "").strip(),
        "client_id": _spotify_client_id(state=state),
        "redirect_uri": _spotify_redirect_uri(state=state),
        "expires_at": state.get("expires_at"),
        "refresh_token": str(state.get("refresh_token", "") or "").strip(),
    }


def get_spotify_auth_status() -> Dict[str, Any]:
    state = get_provider_auth_state("spotify")
    if not state:
        return {"logged_in": False}

    expires_at = state.get("expires_at")
    refresh_token = str(state.get("refresh_token", "") or "").strip()
    return {
        "logged_in": bool(refresh_token or not _is_expiring(expires_at, 0)),
        "auth_type": state.get("auth_type", "oauth_pkce"),
        "client_id": state.get("client_id"),
        "redirect_uri": state.get("redirect_uri"),
        "scope": state.get("granted_scope") or state.get("scope"),
        "expires_at": expires_at,
        "api_base_url": state.get("api_base_url"),
        "has_refresh_token": bool(refresh_token),
    }


def _spotify_interactive_setup(redirect_uri_hint: str) -> str:
    """Walk the user through creating a Spotify developer app, persist the
    resulting client_id to ~/.sparkii/.env, and return it.

    Raises SystemExit if the user aborts or submits an empty value.
    """
    from core.config import save_env_value

    print()
    print("=" * 70)
    print("Spotify first-time setup")
    print("=" * 70)
    print()
    print("Spotify requires every user to register their own lightweight")
    print("developer app. This takes about two minutes and only has to be")
    print("done once per machine.")
    print()
    print(f"Full guide: {SPOTIFY_DOCS_URL}")
    print()
    print("Steps:")
    print(f"  1. Opening {SPOTIFY_DASHBOARD_URL} in your browser...")
    print("  2. Click 'Create app' and fill in:")
    print("       App name:     anything (e.g. sparkii-agent)")
    print("       Description:  anything")
    print(f"       Redirect URI: {redirect_uri_hint}")
    print("       API/SDK:      Web API")
    print("  3. Agree to the terms, click Save.")
    print("  4. Open the app's Settings page and copy the Client ID.")
    print("  5. Paste it below.")
    print()

    if not _is_remote_session():
        try:
            webbrowser.open(SPOTIFY_DASHBOARD_URL)
        except Exception:
            pass

    try:
        raw = input("Spotify Client ID: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit("Spotify setup cancelled.")

    if not raw:
        print()
        print(f"No Client ID entered. See {SPOTIFY_DOCS_URL} for the full guide.")
        raise SystemExit("Spotify setup cancelled: empty Client ID.")

    # Persist so subsequent `sparkii auth spotify` runs skip the wizard.
    save_env_value("SPARKII_SPOTIFY_CLIENT_ID", raw)
    # Only persist the redirect URI if it's non-default, to avoid pinning
    # users to a value the default might later change to.
    if redirect_uri_hint and redirect_uri_hint != DEFAULT_SPOTIFY_REDIRECT_URI:
        save_env_value("SPARKII_SPOTIFY_REDIRECT_URI", redirect_uri_hint)

    print()
    print("Saved SPARKII_SPOTIFY_CLIENT_ID to ~/.sparkii/.env")
    print()
    return raw


def login_spotify_command(args) -> None:
    existing_state = get_provider_auth_state("spotify") or {}

    # Interactive wizard: if no client_id is configured anywhere, walk the
    # user through creating the Spotify developer app instead of crashing
    # with "SPARKII_SPOTIFY_CLIENT_ID is required".
    explicit_client_id = getattr(args, "client_id", None)
    try:
        client_id = _spotify_client_id(explicit_client_id, existing_state)
    except AuthError as exc:
        if getattr(exc, "code", "") != "spotify_client_id_missing":
            raise
        client_id = _spotify_interactive_setup(
            redirect_uri_hint=getattr(args, "redirect_uri", None) or DEFAULT_SPOTIFY_REDIRECT_URI,
        )

    redirect_uri = _spotify_redirect_uri(getattr(args, "redirect_uri", None), existing_state)
    scope = _spotify_scope_string(getattr(args, "scope", None) or existing_state.get("scope"))
    accounts_base_url = _spotify_accounts_base_url(existing_state)
    api_base_url = _spotify_api_base_url(existing_state)
    open_browser = not getattr(args, "no_browser", False)

    code_verifier = _spotify_code_verifier()
    code_challenge = _spotify_code_challenge(code_verifier)
    state_nonce = uuid.uuid4().hex
    authorize_url = _spotify_build_authorize_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope,
        state=state_nonce,
        code_challenge=code_challenge,
        accounts_base_url=accounts_base_url,
    )

    print("Starting Spotify PKCE login...")
    print(f"Client ID: {client_id}")
    print(f"Redirect URI: {redirect_uri}")
    print("Make sure this redirect URI is allow-listed in your Spotify app settings.")
    print()
    print("Open this URL to authorize Sparkii:")
    print(authorize_url)
    print()
    print(f"Full setup guide: {SPOTIFY_DOCS_URL}")
    print()

    _print_loopback_ssh_hint(redirect_uri, docs_url=SPOTIFY_DOCS_URL)

    if open_browser and not _is_remote_session() and _can_open_graphical_browser():
        try:
            opened = webbrowser.open(authorize_url)
        except Exception:
            opened = False
        if opened:
            print("Browser opened for Spotify authorization.")
        else:
            print("Could not open the browser automatically; use the URL above.")

    callback = _spotify_wait_for_callback(
        redirect_uri,
        timeout_seconds=float(getattr(args, "timeout", None) or 180.0),
    )
    if callback.get("error"):
        detail = callback.get("error_description") or callback["error"]
        raise SystemExit(f"Spotify authorization failed: {detail}")
    if callback.get("state") != state_nonce:
        raise SystemExit("Spotify authorization failed: state mismatch.")

    token_payload = _spotify_exchange_code_for_tokens(
        client_id=client_id,
        code=str(callback.get("code") or ""),
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
        accounts_base_url=accounts_base_url,
        timeout_seconds=float(getattr(args, "timeout", None) or 20.0),
    )
    spotify_state = _spotify_token_payload_to_state(
        token_payload,
        client_id=client_id,
        redirect_uri=redirect_uri,
        requested_scope=scope,
        accounts_base_url=accounts_base_url,
        api_base_url=api_base_url,
    )

    with _auth_store_lock():
        auth_store = _load_auth_store()
        _store_provider_state(auth_store, "spotify", spotify_state, set_active=False)
        saved_to = _save_auth_store(auth_store)

    print("Spotify login successful!")
    print(f"  Auth state: {saved_to}")
    print("  Provider state saved under providers.spotify")
    print(f"  Docs: {SPOTIFY_DOCS_URL}")

# =============================================================================
# SSH / remote session detection
# =============================================================================

def _is_remote_session() -> bool:
    """Detect environments where loopback OAuth can't reach the local browser.

    Historically only SSH was checked, but #26923 surfaced that
    **browser-only remote consoles** (GCP Cloud Shell, GitHub
    Codespaces, AWS EC2 Instance Connect, Gitpod, Replit, etc.) hit
    the exact same problem — the user has a browser on their laptop
    but the loopback listener is bound on the remote VM that the
    laptop's browser can't reach.  These environments typically don't
    set ``SSH_CLIENT`` / ``SSH_TTY``, so the SSH-only check left
    them with no guidance and no fallback.
    """
    if os.getenv("SSH_CLIENT") or os.getenv("SSH_TTY"):
        return True
    # Browser-only remote IDEs / cloud shells.  Keep this list narrow
    # (well-known, documented env vars set by the host platform) so
    # we don't falsely trip on a developer's local shell.
    for var in (
        "CLOUD_SHELL",         # GCP Cloud Shell
        "CODESPACES",          # GitHub Codespaces
        "CODESPACE_NAME",      # GitHub Codespaces (alt)
        "GITPOD_WORKSPACE_ID", # Gitpod
        "REPL_ID",             # Replit
        "STACKBLITZ",          # StackBlitz
    ):
        if os.getenv(var):
            return True
    return False


# Console/text-mode browsers that ``webbrowser`` will happily launch INSIDE
# the terminal.  Opening one of these is worse than not opening anything —
# it hijacks the user's TTY with an unusable text browser (the xAI OAuth
# "Account Management" page rendered in w3m, reported May 2026) instead of
# letting them copy the URL to a real browser.  When the resolved browser is
# one of these we refuse to auto-open and fall back to the print-the-URL
# path, same as a remote session.
_CONSOLE_BROWSER_NAMES: FrozenSet[str] = frozenset(
    {
        "w3m",
        "lynx",
        "links",
        "links2",
        "elinks",
        "www-browser",
        "browsh",  # TUI browser — still hijacks the terminal
    }
)


def _can_open_graphical_browser() -> bool:
    """Return True only when a *graphical* browser is likely to open.

    ``webbrowser.open()`` resolves to whatever the platform offers, and on a
    headless / CLI-only Linux box with no GUI browser installed that is often
    a text-mode browser (w3m/lynx/links) which launches inside the terminal
    and takes over the user's session.  This guard distinguishes "a real
    windowed browser will pop up" from "a console browser will hijack the
    TTY", so callers can fall back to printing the URL instead.

    Heuristics:
      * Respect ``$BROWSER`` — if it names a known console browser, refuse.
      * On Linux, require a display server (``$DISPLAY`` / ``$WAYLAND_DISPLAY``)
        unless ``$BROWSER`` points at something graphical; no display server
        almost always means no GUI browser.
      * Ask ``webbrowser.get()`` what it resolved to and refuse when the
        underlying command is a known console browser.
      * macOS and Windows always have a usable default GUI browser.
    """
    import webbrowser as _webbrowser

    def _names_console_browser(value: str) -> bool:
        token = value.strip().split()[0] if value.strip() else ""
        base = os.path.basename(token).lower()
        return base in _CONSOLE_BROWSER_NAMES

    browser_env = os.environ.get("BROWSER", "")
    if browser_env and _names_console_browser(browser_env):
        return False

    if sys.platform.startswith("linux"):
        has_display = bool(
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        )
        # An explicit graphical $BROWSER can work without $DISPLAY in odd
        # setups, but a console $BROWSER already returned False above, so the
        # only way to reach here with a $BROWSER set is a graphical one.
        if not has_display and not browser_env:
            return False

    try:
        controller = _webbrowser.get()
    except Exception:
        # No browser resolvable at all → definitely don't auto-open.
        return False

    candidate = (
        getattr(controller, "name", "")
        or getattr(controller, "basename", "")
        or ""
    )
    if candidate and _names_console_browser(candidate):
        return False

    return True


def _ssh_user_at_host() -> str:
    """Return best-effort 'user@hostname' for the SSH tunnel hint command.

    Falls back to placeholder tokens when the values cannot be determined so
    the hint is always syntactically valid even if not copy-pasteable.
    """
    try:
        import socket as _socket
        hostname = _socket.gethostname() or "<this-host>"
    except OSError:
        hostname = "<this-host>"
    user = os.getenv("USER") or os.getenv("LOGNAME") or "<user>"
    return f"{user}@{hostname}"


def _print_loopback_ssh_hint(redirect_uri: str, *, docs_url: str | None = None) -> None:
    """Print an SSH tunnel hint when running a loopback-redirect OAuth flow on a
    remote host. The auth server (Spotify, MCP servers, ...) will redirect the
    user's browser to ``127.0.0.1:<port>/callback``. If the browser is on a
    different machine than the loopback listener (the usual SSH case), the
    redirect can't reach the listener without a local port forward.

    The hint is best-effort: silent if we don't think we're remote, or if we
    can't parse a host/port out of the redirect URI.

    Pass ``docs_url`` for a provider-specific guide; the generic OAuth-over-SSH
    guide is always shown after it.
    """
    if not _is_remote_session():
        return
    try:
        parsed = urlparse(redirect_uri)
    except Exception:
        return
    host = parsed.hostname or ""
    port = parsed.port
    if host not in {"127.0.0.1", "::1", "localhost"} or not port:
        return
    divider = "-" * 60
    print()
    print(divider)
    print("Remote session detected — SSH tunnel required")
    print(divider)
    print(f"Sparkii is waiting for the OAuth callback on {redirect_uri}")
    print("but your browser is on a different machine. Run this command")
    print("in a NEW terminal on your local machine BEFORE opening the URL:")
    print()
    print(f"  ssh -N -L {port}:127.0.0.1:{port} {_ssh_user_at_host()}")
    print()
    print("Then open the authorize URL above in your local browser.")
    if docs_url:
        print(f"Provider docs:      {docs_url}")
    print(f"SSH/jump-box guide: {OAUTH_OVER_SSH_DOCS_URL}")
    print(divider)
    print()


# =============================================================================
# OpenAI Codex auth — tokens stored in ~/.sparkii/auth.json (not ~/.codex/)
#
# Sparkii maintains its own Codex OAuth session separate from the Codex CLI
# and VS Code extension. This prevents refresh token rotation conflicts
# where one app's refresh invalidates the other's session.
# =============================================================================



















# Throttle for the live Codex quota probe below.  The probe runs on the hot
# credential-selection path while the pool is exhausted, so without a floor a
# busy gateway would hammer the usage endpoint on every model/auxiliary call.
# 5 minutes












# =============================================================================
# xAI Grok OAuth — tokens stored in ~/.sparkii/auth.json
# =============================================================================





























# =============================================================================
# TLS verification helper
# =============================================================================





# =============================================================================
# OAuth Device Code Flow — generic, parameterized by provider
# =============================================================================







# =============================================================================
# Nous Portal — token refresh and model discovery
# =============================================================================

# -----------------------------------------------------------------------------
# Shared Nous token store — lets OAuth credentials persist across profiles
# so a new `sparkii --profile <name> auth add nous --type oauth` can one-tap
# import instead of running the full device-code flow every time.
#
# File lives at ${SPARKII_SHARED_AUTH_DIR}/nous_auth.json, defaulting to
# ``<sparkii-root>/shared/nous_auth.json`` where ``<sparkii-root>`` is what
# ``get_default_sparkii_root()`` returns — ``~/.sparkii`` on Linux/macOS,
# ``%LOCALAPPDATA%\sparkii`` on native Windows, or the Docker/custom root.
# It is OUTSIDE any named profile's SPARKII_HOME so named profiles (which
# typically live under ``<sparkii-root>/profiles/<name>/``) all see the
# same file.
#
# Written on successful login and on every runtime refresh so the stored
# refresh_token stays current even if one profile refreshes and rotates it.
# If ever the stored refresh_token does go stale server-side, import fails
# gracefully and the user falls back to the normal device-code flow.
# -----------------------------------------------------------------------------



































# Per-process memo for resolve_nous_access_token. Startup runs
# check_tool_availability once per managed-tool check_fn (browser, image_gen,
# etc.), and each one independently triggers a ~15s blocking token-refresh
# network call when the stored token is expired. On a slow/constrained host that
# serial burst stretches startup to many minutes. A short-TTL memo collapses the
# burst into a single network round-trip; callers that need freshness use
# separate flows (force_fresh / refresh_nous_oauth_pure) and are unaffected.














# =============================================================================
# Status helpers
# =============================================================================





# ── Process-level memo for get_nous_auth_status() ──
# get_nous_auth_status() validates state by calling resolve_nous_runtime_credentials(),
# which does a synchronous OAuth refresh POST to portal.nousresearch.com. That can take
# ~350ms even on the failure path, and read-only UI surfaces (`sparkii tools`, status panels,
# subscription-feature checks) call it many times per render — `sparkii tools` → "All Platforms"
# was firing the refresh ~31× during one menu paint, racking up >13s of HTTP and burning
# single-use refresh tokens. Cache the snapshot for a few seconds, keyed on the auth.json
# path + mtime so that profile switches do not share a process memo and
# `sparkii auth login/logout/add/remove` invalidate naturally on the next call.
# seconds


def _auth_file_cache_key() -> Tuple[str, Optional[float]]:
    auth_file = _auth_file_path()
    try:
        auth_file_key = str(auth_file.resolve(strict=False))
    except Exception:
        auth_file_key = str(auth_file)
    try:
        return auth_file_key, auth_file.stat().st_mtime
    except FileNotFoundError:
        return auth_file_key, None
    except Exception:
        return auth_file_key, None










# Enum values reported on the dashboard /api/status as ``nous_session_valid``.
# NAS's health sweep re-mints the bootstrap session ONLY on "terminal"; "valid"
# and "unknown" are no-ops. Keep this set small and stable — NAS parses it with
# a permissive schema, so new members are non-breaking but should stay rare.








def get_api_key_provider_status(provider_id: str) -> Dict[str, Any]:
    """Status snapshot for API-key providers (z.ai, Kimi, MiniMax)."""
    pconfig = PROVIDER_REGISTRY.get(provider_id)
    if not pconfig or pconfig.auth_type != "api_key":
        return {"configured": False}

    api_key = ""
    key_source = ""
    api_key, key_source = _resolve_api_key_provider_secret(provider_id, pconfig)

    env_url = ""
    if pconfig.base_url_env_var:
        env_url = os.getenv(pconfig.base_url_env_var, "").strip()

    if provider_id in {"kimi-coding", "kimi-coding-cn"}:
        base_url = _resolve_kimi_base_url(api_key, pconfig.inference_base_url, env_url)
    elif env_url:
        base_url = env_url
    else:
        base_url = pconfig.inference_base_url

    if provider_id == "actual":
        base_url = normalize_actual_base_url(base_url)

    actual_local_noauth = (
        provider_id == "actual"
        and not api_key
        and is_actual_local_base_url(base_url)
    )

    return {
        "configured": bool(api_key) or actual_local_noauth,
        "provider": provider_id,
        "name": pconfig.name,
        "key_source": key_source or ("local-offline" if actual_local_noauth else ""),
        "base_url": base_url,
        "logged_in": bool(api_key) or actual_local_noauth,  # compat with OAuth status shape
    }




def get_auth_status(provider_id: Optional[str] = None) -> Dict[str, Any]:
    """Generic auth status dispatcher."""
    target = (provider_id or get_active_provider() or "").strip().lower()
    if not target:
        return {"logged_in": False}
    if target == "spotify":
        return get_spotify_auth_status()
    if target == "azure-foundry":
        return _get_azure_foundry_auth_status()
    # API-key providers
    pconfig = PROVIDER_REGISTRY.get(target)
    if pconfig and pconfig.auth_type == "api_key":
        return get_api_key_provider_status(target)
    # AWS SDK providers (Bedrock) — check via boto3 credential chain
    if pconfig and pconfig.auth_type == "aws_sdk":
        try:
            from agent.bedrock_adapter import has_aws_credentials
            return {"logged_in": has_aws_credentials(), "provider": target}
        except ImportError:
            return {"logged_in": False, "provider": target, "error": "boto3 not installed"}
    return {"logged_in": False}


def _get_azure_foundry_auth_status() -> Dict[str, Any]:
    """Return structural auth status for Azure Foundry.

    ``logged_in`` is structural, matching other non-OAuth provider status
    checks:

      * ``auth_mode == "entra_id"`` AND ``azure-identity`` is importable
        (we do NOT mint a token here; ``sparkii doctor`` runs the live
        probe and reports whether the credential chain can acquire one).
      * ``auth_mode == "api_key"`` (default) AND ``AZURE_FOUNDRY_API_KEY``
        is set with a usable value.

    Never invokes the Entra credential chain — keeps CLI startup latency
    flat regardless of token-service / az login state.
    """
    info: Dict[str, Any] = {"provider": "azure-foundry"}
    try:
        from core.config import load_config, get_env_value_prefer_dotenv
        cfg = load_config()
    except Exception:
        cfg = {}

    model_cfg = cfg.get("model") if isinstance(cfg, dict) else None
    auth_mode = "api_key"
    base_url = ""
    if isinstance(model_cfg, dict):
        auth_mode = str(model_cfg.get("auth_mode") or "api_key").strip().lower() or "api_key"
        base_url = str(model_cfg.get("base_url") or "").strip()
    info["auth_mode"] = auth_mode
    info["base_url"] = base_url

    if auth_mode == "entra_id":
        try:
            from agent.azure_identity_adapter import (
                EntraIdentityConfig,
                SCOPE_AI_AZURE_DEFAULT,
                has_azure_identity_installed,
            )
            installed = has_azure_identity_installed()
            entra_cfg = {}
            if isinstance(model_cfg, dict) and isinstance(model_cfg.get("entra"), dict):
                entra_cfg = model_cfg["entra"]
            identity_config = EntraIdentityConfig.from_dict(
                entra_cfg,
                default_scope=SCOPE_AI_AZURE_DEFAULT,
            )
            info["azure_identity_installed"] = installed
            info["scope"] = identity_config.scope
            info["credential_probe"] = "not_run"
            info["credential_verified"] = False
            info["logged_in"] = bool(installed)
            if not installed:
                info["hint"] = (
                    "azure-identity not installed. Install with: "
                    "pip install azure-identity  (or rely on Sparkii' "
                    "lazy-install at first use)."
                )
            else:
                info["hint"] = (
                    "azure-identity is installed; live credential validation "
                    "is skipped here. Run `sparkii doctor` to verify token acquisition."
                )
            return info
        except Exception as exc:
            info["logged_in"] = False
            info["error"] = f"azure-identity check failed: {exc}"
            return info

    # api_key mode (default)
    try:
        api_key = get_env_value_prefer_dotenv("AZURE_FOUNDRY_API_KEY") or ""
    except Exception:
        api_key = os.getenv("AZURE_FOUNDRY_API_KEY", "")
    info["logged_in"] = has_usable_secret(api_key)
    return info


def resolve_api_key_provider_credentials(provider_id: str) -> Dict[str, Any]:
    """Resolve API key and base URL for an API-key provider.

    Returns dict with: provider, api_key, base_url, source.
    """
    pconfig = PROVIDER_REGISTRY.get(provider_id)
    if not pconfig or pconfig.auth_type != "api_key":
        raise AuthError(
            f"Provider '{provider_id}' is not an API-key provider.",
            provider=provider_id,
            code="invalid_provider",
        )

    api_key = ""
    key_source = ""
    api_key, key_source = _resolve_api_key_provider_secret(provider_id, pconfig)

    # No-auth LM Studio: substitute a placeholder so runtime / auxiliary_client
    # see the local server as configured. doctor still reports unconfigured
    # because get_api_key_provider_status uses the raw secret resolver.
    if not api_key and provider_id == "lmstudio":
        api_key = LMSTUDIO_NOAUTH_PLACEHOLDER
        key_source = key_source or "default"

    env_url = ""
    if pconfig.base_url_env_var:
        env_url = os.getenv(pconfig.base_url_env_var, "").strip()

    if provider_id in {"kimi-coding", "kimi-coding-cn"}:
        base_url = _resolve_kimi_base_url(api_key, pconfig.inference_base_url, env_url)
    elif provider_id == "zai":
        base_url = _resolve_zai_base_url(api_key, pconfig.inference_base_url, env_url)
    elif provider_id == "copilot":
        # Resolve the Copilot API base URL from the token-exchange response
        # (endpoints.api, with a proxy-ep fallback), which is authoritative
        # for Enterprise / proxied accounts. Falls back to the registry
        # default and is guarded non-empty below so chat inference never
        # resolves an empty base URL (#50252).
        base_url = env_url.rstrip("/") if env_url else pconfig.inference_base_url
        try:
            from sparkii_cli.copilot_auth import (
                resolve_copilot_token,
                get_copilot_api_token,
            )
            raw_token, _ = resolve_copilot_token()
            if raw_token:
                _, resolved = get_copilot_api_token(raw_token)
                resolved = (resolved or "").strip()
                if resolved:
                    base_url = resolved
        except Exception as exc:
            logger.debug("Copilot base URL resolution fell back to default: %s", exc)
    elif env_url:
        base_url = env_url.rstrip("/")
    else:
        base_url = pconfig.inference_base_url

    if provider_id == "lmstudio":
        base_url = _normalize_lmstudio_runtime_base_url(base_url)

    if provider_id == "actual":
        base_url = normalize_actual_base_url(base_url)

    # Last-resort guard: an API-key provider must never hand back an empty
    # base URL (a set-but-empty COPILOT_API_BASE_URL or similar env override
    # otherwise wedges chat inference — #50252).
    if not (isinstance(base_url, str) and base_url.strip()):
        base_url = pconfig.inference_base_url

    if not api_key and provider_id == "actual" and is_actual_local_base_url(base_url):
        api_key = ACTUAL_LOCAL_NOAUTH_PLACEHOLDER
        key_source = key_source or "local-offline"

    return {
        "provider": provider_id,
        "api_key": api_key,
        "base_url": base_url.rstrip("/"),
        "source": key_source or "default",
    }




# =============================================================================
# CLI Commands — login / logout
# =============================================================================

def _update_config_for_provider(
    provider_id: str,
    inference_base_url: str,
    default_model: Optional[str] = None,
) -> Path:
    """Update config.yaml and auth.json to reflect the active provider.

    When *default_model* is provided the function also writes it as the
    ``model.default`` value.  This prevents a race condition where the
    gateway (which re-reads config per-message) picks up the new provider
    before the caller has finished model selection, resulting in a
    mismatched model/provider (e.g. ``anthropic/claude-opus-4.6`` sent to
    MiniMax's API).
    """
    # Set active_provider in auth.json so auto-resolution picks this provider
    with _auth_store_lock():
        auth_store = _load_auth_store()
        auth_store["active_provider"] = provider_id
        _save_auth_store(auth_store)

    # Update config.yaml model section
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    require_readable_config_before_write(config_path)

    config = read_raw_config()

    current_model = config.get("model")
    if isinstance(current_model, dict):
        model_cfg = dict(current_model)
    elif isinstance(current_model, str) and current_model.strip():
        model_cfg = {"default": current_model.strip()}
    else:
        model_cfg = {}

    model_cfg["provider"] = provider_id
    if inference_base_url and inference_base_url.strip():
        model_cfg["base_url"] = inference_base_url.rstrip("/")
    else:
        # Clear stale base_url to prevent contamination when switching providers
        model_cfg.pop("base_url", None)

    # Clear stale endpoint credentials left over from a previous custom provider.
    # Built-in providers resolve credentials from env/auth state, not inline
    # model.api_key.
    from core.config import clear_model_endpoint_credentials

    clear_model_endpoint_credentials(model_cfg)

    # When switching to a non-OpenRouter provider, ensure model.default is
    # valid for the new provider.  An OpenRouter-formatted name like
    # "anthropic/claude-opus-4.6" will fail on direct-API providers.
    if default_model:
        cur_default = model_cfg.get("default", "")
        if not cur_default or "/" in cur_default:
            model_cfg["default"] = default_model

    config["model"] = model_cfg

    atomic_yaml_write(config_path, config, sort_keys=False)
    return config_path


def _get_config_provider() -> Optional[str]:
    """Return model.provider from config.yaml, normalized, if present."""
    try:
        config = read_raw_config()
    except Exception:
        return None
    if not config:
        return None
    model = config.get("model")
    if not isinstance(model, dict):
        return None
    provider = model.get("provider")
    if not isinstance(provider, str):
        return None
    provider = provider.strip().lower()
    return provider or None


def _config_provider_matches(provider_id: Optional[str]) -> bool:
    """Return True when config.yaml currently selects *provider_id*."""
    if not provider_id:
        return False
    return _get_config_provider() == provider_id.strip().lower()


def _should_reset_config_provider_on_logout(provider_id: Optional[str]) -> bool:
    """Return True when logout should reset the model provider config."""
    if not provider_id:
        return False
    normalized = provider_id.strip().lower()
    return normalized in PROVIDER_REGISTRY and _config_provider_matches(normalized)


def _reset_config_provider() -> Path:
    """Reset config.yaml provider back to auto after logout."""
    config_path = get_config_path()
    if not config_path.exists():
        return config_path
    require_readable_config_before_write(config_path)

    config = read_raw_config()
    if not config:
        return config_path

    model = config.get("model")
    if isinstance(model, dict):
        model["provider"] = "auto"
        if "base_url" in model:
            model["base_url"] = OPENROUTER_BASE_URL
    atomic_yaml_write(config_path, config, sort_keys=False)
    return config_path


def _confirm_expensive_model_selection(
    model_id: str,
    *,
    provider: str = "",
    base_url: str = "",
    api_key: str = "",
) -> bool:
    """Prompt before saving a model whose known pricing exceeds guardrails."""
    try:
        from sparkii_cli.model_cost_guard import expensive_model_warning

        warning = expensive_model_warning(
            model_id,
            provider=provider,
            base_url=base_url,
            api_key=api_key,
        )
    except Exception:
        warning = None
    if warning is None:
        return True

    print()
    print("=" * 72)
    print(warning.message)
    print("=" * 72)
    try:
        response = input("Switch anyway? [y/N]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return False
    return response in {"y", "yes"}


def _prompt_model_selection(
    model_ids: List[str],
    current_model: str = "",
    pricing: Optional[Dict[str, Dict[str, str]]] = None,
    unavailable_models: Optional[List[str]] = None,
    portal_url: str = "",
    unavailable_message: str = "",
    confirm_provider: str = "",
    confirm_base_url: str = "",
    confirm_api_key: str = "",
) -> Optional[str]:
    """Interactive model selection. Puts current_model first with a marker. Returns chosen model ID or None.

    If *pricing* is provided (``{model_id: {prompt, completion}}``), a compact
    price indicator is shown next to each model in aligned columns.

    If *unavailable_models* is provided, those models are shown grayed out
    and unselectable, with an upgrade link to *portal_url*.
    """
    from sparkii_cli.models import (
        _format_price_per_mtok,
        compute_sale_discount,
    )

    _unavailable = unavailable_models or []
    # Sale chrome (★ / -N% / was) is Nous Portal-only — never for OpenRouter
    # or other providers even if pricing.original is somehow present.
    sale_chrome = (confirm_provider or "").strip().lower() == "nous"

    def _confirmed_selection(mid: str) -> Optional[str]:
        if not mid:
            return None
        if confirm_provider and not _confirm_expensive_model_selection(
            mid,
            provider=confirm_provider,
            base_url=confirm_base_url,
            api_key=confirm_api_key,
        ):
            return None
        return mid

    # Reorder: current model first, then the rest (deduplicated)
    ordered = []
    if current_model and current_model in model_ids:
        ordered.append(current_model)
    for mid in model_ids:
        if mid not in ordered:
            ordered.append(mid)

    # All models for column-width computation (selectable + unavailable)
    all_models = list(ordered) + list(_unavailable)

    # Column-aligned labels when pricing is available
    has_pricing = bool(pricing and any(pricing.get(m) for m in all_models))
    # Leave room for a leading "★ " on sale rows (Nous only).
    name_pad = 3 if sale_chrome else 2
    name_col = (
        max((len(m) for m in all_models), default=0) + name_pad
        if has_pricing
        else 0
    )

    # Pre-compute formatted prices and sale chrome.
    # (inp, out, cache, pct|None, was_inp, was_out)
    # Sale chrome is drawn as curses/ANSI segments (yellow % / dim "was"),
    # not baked into a single plain string — curses addnstr would otherwise
    # render escape bytes literally.
    _price_cache: dict[str, tuple[str, str, str, int | None, str, str]] = {}
    price_col = 3  # minimum width
    cache_col = 0  # only set if any model has cache pricing
    has_cache = False
    any_on_sale = False
    _DIM = "\033[2m"
    _RESET = "\033[0m"
    if has_pricing:
        for mid in all_models:
            p = pricing.get(mid)  # type: ignore[union-attr]
            pct: int | None = None
            was_inp = was_out = ""
            if p:
                inp = _format_price_per_mtok(p.get("prompt", ""))
                out = _format_price_per_mtok(p.get("completion", ""))
                cache_read = p.get("input_cache_read", "")
                cache = _format_price_per_mtok(cache_read) if cache_read else ""
                if cache:
                    has_cache = True
                if sale_chrome:
                    sale = compute_sale_discount(
                        p.get("prompt", ""),
                        p.get("completion", ""),
                        p.get("original"),
                    )
                    if sale is not None:
                        any_on_sale = True
                        pct, was_prompt_raw, was_out_raw = sale
                        was_inp = (
                            _format_price_per_mtok(was_prompt_raw)
                            if was_prompt_raw != ""
                            else "?"
                        )
                        was_out = (
                            _format_price_per_mtok(was_out_raw)
                            if was_out_raw != ""
                            else "?"
                        )
            else:
                inp, out, cache = "", "", ""
            _price_cache[mid] = (inp, out, cache, pct, was_inp, was_out)
            price_col = max(price_col, len(inp), len(out))
            cache_col = max(cache_col, len(cache))
        if has_cache:
            cache_col = max(cache_col, 5)  # minimum: "Cache" header

    def _label_segments(mid):
        """Build a rich radiolist row: yellow ★/% , dim was, plain prices."""
        if not has_pricing:
            segs: list[tuple[str, str | None]] = [(mid, None)]
            if mid == current_model:
                segs.append(("  ← currently in use", None))
            return segs

        inp, out, cache, pct, was_inp, was_out = _price_cache.get(
            mid, ("", "", "", None, "", "")
        )
        on_sale = pct is not None
        # Reserve 2 columns for "★ " so sale and non-sale names share alignment.
        star_w = 2
        if on_sale:
            name_segs: list[tuple[str, str | None]] = [
                ("★ ", "yellow"),
                (f"{mid:<{name_col - star_w}}", None),
            ]
        else:
            name_segs = [(f"{mid:<{name_col}}", None)]

        price_part = f" {inp:>{price_col}}  {out:>{price_col}}"
        if has_cache:
            price_part += f"  {cache:>{cache_col}}"
        segs = [*name_segs, (price_part, None)]
        if on_sale:
            segs.append((f"  -{pct}%", "yellow"))
            segs.append((f"  was {was_inp}/{was_out}", "dim"))
        if mid == current_model:
            segs.append(("  ← currently in use", None))
        return segs

    def _label(mid):
        return "".join(text for text, _style in _label_segments(mid))

    # Default cursor on the current model (index 0 if it was reordered to top)
    default_idx = 0

    # Build a pricing header hint for the menu title
    menu_title = "Select default model:"
    if has_pricing:
        # Align the header with the model column.
        # Each choice is "  {label}" (2 spaces) and we prepend
        # a 3-char cursor region ("-> " or "   "), so content starts at col 5.
        pad = " " * 5
        header = f"\n{pad}{'':>{name_col}} {'In':>{price_col}}  {'Out':>{price_col}}"
        if has_cache:
            header += f"  {'Cache':>{cache_col}}"
        # Legend lives on the column-header line so it reads as a key
        # (★ = on sale), not a fake menu row.
        menu_title += header + "  $/Mtok"
        if any_on_sale:
            menu_title += "  ★ = on sale"

    # Try arrow-key menu first, fall back to number input.
    try:
        from sparkii_cli.curses_ui import curses_radiolist

        choices = [_label_segments(mid) for mid in ordered]
        choices.append("Enter custom model name")
        choices.append("Skip (keep current)")

        _upgrade_url = (portal_url or DEFAULT_NOUS_PORTAL_URL).rstrip("/")
        unavailable_footer = unavailable_message.strip()
        if not unavailable_footer and _unavailable:
            unavailable_footer = f"Upgrade at {_upgrade_url} for paid models"

        # The pricing column header (and any unavailable-models block) is shown
        # as a multi-line description above the list so it survives the curses
        # screen clear. menu_title already embeds the aligned price header.
        desc_lines: list[str] = []
        if has_pricing:
            # menu_title is "Select default model:\n<pad><header>  $/Mtok\n…"
            # Keep only the header/legend portion for the description.
            header_part = menu_title.split("\n", 1)
            if len(header_part) > 1:
                desc_lines.extend(header_part[1].splitlines())
        if _unavailable:
            for mid in _unavailable:
                desc_lines.append(f"   {_label(mid)}")
            desc_lines.append(f"  ── {unavailable_footer} ──")
        description = "\n".join(desc_lines) if desc_lines else None

        # Search haystacks keep pricing labels visible while adding aliases
        # for brand-less wire ids (e.g. Kimi Coding `k3` ↔ query "kimi").
        from core.model_search import model_search_text

        model_search_labels = []
        for mid in ordered:
            label = _label(mid)
            haystack = model_search_text(mid)
            # model_search_text always starts with the wire id; only append when
            # aliases add tokens beyond the bare id already in the label.
            model_search_labels.append(
                label if haystack == mid else f"{label} {haystack}"
            )
        model_search_labels.append("Enter custom model name")
        model_search_labels.append("Skip (keep current)")

        idx = curses_radiolist(
            "Select default model:",
            choices,
            selected=default_idx,
            cancel_returns=-1,
            description=description,
            searchable=True,
            search_labels=model_search_labels,
        )
        if idx < 0:
            return None
        print()
        if idx < len(ordered):
            return _confirmed_selection(ordered[idx])
        elif idx == len(ordered):
            try:
                custom = input("Enter model name: ").strip()
            except (EOFError, KeyboardInterrupt):
                return None
            return _confirmed_selection(custom) if custom else None
        return None
    except (ImportError, NotImplementedError, OSError, subprocess.SubprocessError):
        pass

    # Fallback: numbered list (ANSI colors for sale chrome)
    from sparkii_cli.curses_ui import format_radio_item_ansi
    from core.colors import Colors, color

    for line in menu_title.splitlines():
        if "★" in line:
            print(line.replace("★", color("★", Colors.YELLOW), 1))
        else:
            print(line)
    num_width = len(str(len(ordered) + 2))
    for i, mid in enumerate(ordered, 1):
        print(f"  {i:>{num_width}}. {format_radio_item_ansi(_label_segments(mid))}")
    n = len(ordered)
    print(f"  {n + 1:>{num_width}}. Enter custom model name")
    print(f"  {n + 2:>{num_width}}. Skip (keep current)")

    if _unavailable:
        _upgrade_url = (portal_url or DEFAULT_NOUS_PORTAL_URL).rstrip("/")
        unavailable_footer = unavailable_message.strip() or (
            f"Unavailable models (requires paid tier — upgrade at {_upgrade_url})"
        )
        print()
        print(f"  {_DIM}── {unavailable_footer} ──{_RESET}")
        for mid in _unavailable:
            print(f"  {'':>{num_width}}  {_DIM}{_label(mid)}{_RESET}")
    print()

    while True:
        try:
            choice = input(f"Choice [1-{n + 2}] (default: skip): ").strip()
            if not choice:
                return None
            idx = int(choice)
            if 1 <= idx <= n:
                return _confirmed_selection(ordered[idx - 1])
            elif idx == n + 1:
                custom = input("Enter model name: ").strip()
                return _confirmed_selection(custom) if custom else None
            elif idx == n + 2:
                return None
            print(f"Please enter 1-{n + 2}")
        except ValueError:
            print("Please enter a number")
        except (KeyboardInterrupt, EOFError):
            return None


def _save_model_choice(model_id: str) -> None:
    """Save the selected model to config.yaml (single source of truth).

    The model is stored in config.yaml only — NOT in .env.  This avoids
    conflicts in multi-agent setups where env vars would stomp each other.
    """
    from core.config import save_config, load_config

    config = load_config()
    # Always use dict format so provider/base_url can be stored alongside
    if isinstance(config.get("model"), dict):
        config["model"]["default"] = model_id
    else:
        config["model"] = {"default": model_id}
    save_config(config)


def login_command(args) -> None:
    """Deprecated: use 'sparkii model' or 'sparkii setup' instead."""
    print("The 'sparkii login' command has been removed.")
    print("Use 'sparkii auth' to manage credentials,")
    print("'sparkii model' to select a provider, or 'sparkii setup' for full setup.")
    raise SystemExit(0)














# ==================== MiniMax Portal OAuth ====================








































def logout_command(args) -> None:
    """Clear auth state for a provider."""
    provider_id = getattr(args, "provider", None)

    if provider_id and not is_known_auth_provider(provider_id):
        print(f"Unknown provider: {provider_id}")
        raise SystemExit(1)

    active = get_active_provider()
    target = provider_id or active

    if not target:
        print("No provider is currently logged in.")
        return

    should_reset_config = _should_reset_config_provider_on_logout(target)
    provider_name = get_auth_provider_display_name(target)

    if clear_provider_auth(target) or should_reset_config:
        if should_reset_config:
            _reset_config_provider()
        print(f"Logged out of {provider_name}.")
        if should_reset_config and os.getenv("OPENROUTER_API_KEY"):
            print("Sparkii will use OpenRouter for inference.")
        elif should_reset_config:
            print("Run `sparkii model` or configure an API key to use Sparkii.")
        else:
            print("Model provider configuration was unchanged.")
    else:
        print(f"No auth state found for {provider_name}.")
