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


STEPFUN_STEP_PLAN_CN_BASE_URL = "https://api.stepfun.com/step_plan/v1"
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
    return normalized in PROVIDER_REGISTRY
def get_auth_provider_display_name(provider_id: str) -> str:
    normalized = (provider_id or "").strip().lower()
    if normalized in PROVIDER_REGISTRY:
        return PROVIDER_REGISTRY[normalized].name
    return provider_id
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
        lookup = get_provider_lookup()
        pconfig = lookup(normalized) if lookup else None
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

