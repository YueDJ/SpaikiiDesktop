"""Tests for API-key provider support (z.ai/GLM, Kimi, MiniMax, AI Gateway)."""

import json
import os

import pytest

from sparkii_cli.auth import (
    PROVIDER_REGISTRY,
    resolve_provider,
    get_api_key_provider_status,
    resolve_api_key_provider_credentials,
    get_auth_status,
    AuthError,
    KIMI_CODE_BASE_URL,
    STEPFUN_STEP_PLAN_CN_BASE_URL,
    _resolve_kimi_base_url,
)
from sparkii_cli.copilot_auth import _try_gh_cli_token


# =============================================================================
# Provider Registry tests
# =============================================================================

class TestResolveProvider:
    """Test resolve_provider() with new providers."""





















































    def test_unknown_provider_raises(self):
        with pytest.raises(AuthError):
            resolve_provider("nonexistent-provider-xyz")























    def test_openrouter_takes_priority_over_glm(self, monkeypatch):
        """OpenRouter API key should win over GLM in auto-detection."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
        monkeypatch.setenv("GLM_API_KEY", "glm-key")
        assert resolve_provider("auto") == "openrouter"

    def test_auto_does_not_select_copilot_from_github_token(self, monkeypatch):
        # AWS Bedrock auto-detection (via boto3's credential chain) runs at
        # the tail of resolve_provider("auto") and will silently pick up
        # ~/.aws/credentials on developer machines that aren't blanked by
        # the hermetic conftest. Force-disable it so this test exercises
        # the specific "GitHub token alone shouldn't auto-pick copilot"
        # behavior, not the Bedrock fallback.
        monkeypatch.setattr(
            "agent.bedrock_adapter.has_aws_credentials",
            lambda env=None: False,
        )
        monkeypatch.setenv("GITHUB_TOKEN", "gh-test-token")
        with pytest.raises(AuthError, match="No inference provider configured"):
            resolve_provider("auto")


# =============================================================================
# API Key Provider Status tests
# =============================================================================




# =============================================================================
# Credential Resolution tests
# =============================================================================

class TestResolveApiKeyProviderCredentials:





    def test_try_gh_cli_token_uses_homebrew_path_when_not_on_path(self, monkeypatch):
        monkeypatch.setattr("sparkii_cli.copilot_auth.shutil.which", lambda command: None)
        monkeypatch.setattr(
            "sparkii_cli.copilot_auth.os.path.isfile",
            lambda path: path == "/opt/homebrew/bin/gh",
        )
        monkeypatch.setattr(
            "sparkii_cli.copilot_auth.os.access",
            lambda path, mode: path == "/opt/homebrew/bin/gh" and mode == os.X_OK,
        )

        calls = []

        class _Result:
            returncode = 0
            stdout = "gh-cli-secret\n"

        def _fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _Result()

        monkeypatch.setattr("sparkii_cli.copilot_auth.subprocess.run", _fake_run)

        assert _try_gh_cli_token() == "gh-cli-secret"
        assert calls == [["/opt/homebrew/bin/gh", "auth", "token"]]
















# =============================================================================
# Runtime Provider Resolution tests
# =============================================================================




# =============================================================================
# _has_any_provider_configured tests
# =============================================================================

class TestHasAnyProviderConfigured:




    def test_claude_code_creds_ignored_on_fresh_install(self, monkeypatch, tmp_path):
        """Claude Code credentials should NOT skip the wizard when Sparkii is unconfigured."""
        from core import config as config_module
        from sparkii_cli.auth import PROVIDER_REGISTRY
        sparkii_home = tmp_path / ".sparkii"
        sparkii_home.mkdir()
        monkeypatch.setattr(config_module, "get_env_path", lambda: sparkii_home / ".env")
        monkeypatch.setattr(config_module, "get_sparkii_home", lambda: sparkii_home)
        monkeypatch.setattr("sparkii_cli.copilot_auth.resolve_copilot_token", lambda: ("", ""))
        # Clear all provider env vars so earlier checks don't short-circuit
        _all_vars = {"OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                      "ANTHROPIC_TOKEN", "OPENAI_BASE_URL"}
        for pconfig in PROVIDER_REGISTRY.values():
            if pconfig.auth_type == "api_key":
                _all_vars.update(pconfig.api_key_env_vars)
        for var in _all_vars:
            monkeypatch.delenv(var, raising=False)
        # Prevent gh-cli / copilot auth fallback from leaking in
        monkeypatch.setattr("sparkii_cli.auth.get_auth_status", lambda _pid: {})
        # Simulate valid Claude Code credentials
        monkeypatch.setattr(
            "agent.anthropic_adapter.read_claude_code_credentials",
            lambda: {"accessToken": "sk-ant-test", "refreshToken": "ref-tok"},
        )
        monkeypatch.setattr(
            "agent.anthropic_adapter.is_claude_code_token_valid",
            lambda creds: True,
        )
        from sparkii_cli.main import _has_any_provider_configured
        assert _has_any_provider_configured() is False

    def test_config_provider_counts(self, monkeypatch, tmp_path):
        """config.yaml with model.provider set should count as configured."""
        import yaml
        from core import config as config_module
        sparkii_home = tmp_path / ".sparkii"
        sparkii_home.mkdir()
        config_file = sparkii_home / "config.yaml"
        config_file.write_text(yaml.dump({
            "model": {"default": "anthropic/claude-opus-4.6", "provider": "openrouter"},
        }))
        monkeypatch.setattr(config_module, "get_env_path", lambda: sparkii_home / ".env")
        monkeypatch.setattr(config_module, "get_sparkii_home", lambda: sparkii_home)
        monkeypatch.setenv("SPARKII_HOME", str(sparkii_home))
        # Clear all provider env vars
        for var in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                     "ANTHROPIC_TOKEN", "OPENAI_BASE_URL"):
            monkeypatch.delenv(var, raising=False)
        from sparkii_cli.main import _has_any_provider_configured
        assert _has_any_provider_configured() is True

    @staticmethod
    def _clear_provider_env(monkeypatch):
        """Clear every provider env var so early checks can't short-circuit."""
        from sparkii_cli.auth import PROVIDER_REGISTRY
        _all_vars = {"OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                     "ANTHROPIC_TOKEN", "OPENAI_BASE_URL"}
        for pconfig in PROVIDER_REGISTRY.values():
            if pconfig.auth_type == "api_key":
                _all_vars.update(pconfig.api_key_env_vars)
        for var in _all_vars:
            monkeypatch.delenv(var, raising=False)

    def _setup_home(self, monkeypatch, tmp_path):
        from core import config as config_module
        sparkii_home = tmp_path / ".sparkii"
        sparkii_home.mkdir()
        monkeypatch.setattr(config_module, "get_env_path", lambda: sparkii_home / ".env")
        monkeypatch.setattr(config_module, "get_sparkii_home", lambda: sparkii_home)
        monkeypatch.setenv("SPARKII_HOME", str(sparkii_home))
        self._clear_provider_env(monkeypatch)
        return sparkii_home

    def test_config_provider_skips_registry_sweep(self, monkeypatch, tmp_path):
        """model.provider in config.yaml must short-circuit BEFORE the slow
        provider-registry sweep (gh subprocess etc.) is ever invoked.

        Regression test for the auth-first ordering: get_auth_status is
        booby-trapped to fail loudly if the sweep runs. The sweep wraps its
        loop in ``except Exception``, so we also record every call — any
        recorded call proves the sweep ran even if the raise was swallowed.
        """
        import yaml
        sparkii_home = self._setup_home(monkeypatch, tmp_path)
        (sparkii_home / "config.yaml").write_text(yaml.dump({
            "model": {"default": "anthropic/claude-opus-4.6", "provider": "openrouter"},
        }))
        sweep_calls = []

        def _trap(provider_id):
            sweep_calls.append(provider_id)
            raise AssertionError("sweep must be skipped")

        monkeypatch.setattr("sparkii_cli.auth.get_auth_status", _trap)
        from sparkii_cli.main import _has_any_provider_configured
        assert _has_any_provider_configured() is True
        assert sweep_calls == [], (
            f"provider registry sweep ran before config short-circuit: {sweep_calls}"
        )

    def test_config_base_url_api_key_skips_registry_sweep(self, monkeypatch, tmp_path):
        """Custom endpoint (base_url/api_key in config, no provider) must also
        short-circuit before the registry sweep."""
        import yaml
        sparkii_home = self._setup_home(monkeypatch, tmp_path)
        (sparkii_home / "config.yaml").write_text(yaml.dump({
            "model": {
                "default": "local/custom-model",
                "base_url": "http://localhost:8000/v1",
                "api_key": "sk-local-test",
            },
        }))
        sweep_calls = []

        def _trap(provider_id):
            sweep_calls.append(provider_id)
            raise AssertionError("sweep must be skipped")

        monkeypatch.setattr("sparkii_cli.auth.get_auth_status", _trap)
        from sparkii_cli.main import _has_any_provider_configured
        assert _has_any_provider_configured() is True
        assert sweep_calls == [], (
            f"provider registry sweep ran before config short-circuit: {sweep_calls}"
        )

    def test_auth_json_skips_registry_sweep(self, monkeypatch, tmp_path):
        """auth.json with a logged-in active provider must short-circuit before
        the registry sweep. get_auth_status may be called ONLY for the active
        provider from auth.json — any other provider id means the sweep ran.
        """
        import json
        sparkii_home = self._setup_home(monkeypatch, tmp_path)
        (sparkii_home / "auth.json").write_text(json.dumps({
            "active_provider": "nous",
        }))
        calls = []

        def _guarded_status(provider_id):
            calls.append(provider_id)
            assert provider_id == "nous", "sweep must be skipped"
            return {"logged_in": True}

        monkeypatch.setattr("sparkii_cli.auth.get_auth_status", _guarded_status)
        from sparkii_cli.main import _has_any_provider_configured
        assert _has_any_provider_configured() is True
        assert calls == ["nous"], (
            f"provider registry sweep ran before auth.json short-circuit: {calls}"
        )


# =============================================================================
# Kimi Code auto-detection tests
# =============================================================================

MOONSHOT_DEFAULT_URL = "https://api.moonshot.ai/v1"


class TestResolveKimiBaseUrl:
    """Test _resolve_kimi_base_url() helper for key-prefix auto-detection."""

    def test_sk_kimi_prefix_routes_to_kimi_code(self):
        url = _resolve_kimi_base_url("sk-kimi-abc123", MOONSHOT_DEFAULT_URL, "")
        assert url == KIMI_CODE_BASE_URL


    def test_env_override_wins_over_legacy(self):
        custom = "https://custom.example.com/v1"
        url = _resolve_kimi_base_url("sk-abc123", MOONSHOT_DEFAULT_URL, custom)
        assert url == custom











class TestZaiParallelProbe:
    """detect_zai_endpoint probes endpoints in parallel workers.

    Contract under test: (1) each endpoint worker preserves the per-endpoint
    candidate-model fallback loop, (2) when several endpoints succeed the
    winner is chosen by ZAI_ENDPOINTS priority order (not completion order).
    """

    def _mock_post(self, ok):
        """Return an httpx.post replacement; `ok` maps (base_url, model) -> bool."""
        import httpx as _httpx

        def _post(url, headers=None, json=None, timeout=None):
            base = url.rsplit("/chat/completions", 1)[0]
            code = 200 if ok.get((base, json["model"])) else 401
            request = _httpx.Request("POST", url)
            return _httpx.Response(code, request=request, json={})

        return _post

    def test_candidate_model_fallback_within_endpoint(self, monkeypatch):
        """A worker must try its endpoint's later candidate models when the
        first ones fail — the fallback the scalar-model version dropped."""
        from sparkii_cli.auth import ZAI_ENDPOINTS, detect_zai_endpoint

        coding_global = next(ep for ep in ZAI_ENDPOINTS if ep[0] == "coding-global")
        base = coding_global[1]
        last_model = coding_global[2][-1]
        # Only the LAST candidate model of coding-global succeeds.
        monkeypatch.setattr(
            "sparkii_cli.auth.httpx.post",
            self._mock_post({(base, last_model): True}),
        )
        result = detect_zai_endpoint("test-key", timeout=1.0)
        assert result is not None
        assert result["id"] == "coding-global"
        assert result["model"] == last_model

    def test_priority_order_wins_over_completion_order(self, monkeypatch):
        """When multiple endpoints accept the key, the FIRST in
        ZAI_ENDPOINTS order must win, even if another finishes earlier."""
        import time as _time

        from sparkii_cli.auth import ZAI_ENDPOINTS, detect_zai_endpoint

        first = ZAI_ENDPOINTS[0]
        last = ZAI_ENDPOINTS[-1]
        ok = {
            (first[1], first[2][0]): True,
            (last[1], last[2][0]): True,
        }
        inner = self._mock_post(ok)

        def _slow_first(url, headers=None, json=None, timeout=None):
            if url.startswith(first[1]):
                _time.sleep(0.15)  # first-priority endpoint finishes LAST
            return inner(url, headers=headers, json=json, timeout=timeout)

        monkeypatch.setattr("sparkii_cli.auth.httpx.post", _slow_first)
        result = detect_zai_endpoint("test-key", timeout=1.0)
        assert result is not None
        assert result["id"] == first[0]

    def test_all_fail_returns_none(self, monkeypatch):
        from sparkii_cli.auth import detect_zai_endpoint

        monkeypatch.setattr("sparkii_cli.auth.httpx.post", self._mock_post({}))
        assert detect_zai_endpoint("bad-key", timeout=1.0) is None

    def test_early_exit_does_not_wait_for_slow_losers(self, monkeypatch):
        """When the highest-priority endpoint succeeds fast, the caller must
        return without waiting for slow lower-priority probes to finish."""
        import time as _time

        from sparkii_cli.auth import ZAI_ENDPOINTS, detect_zai_endpoint

        first = ZAI_ENDPOINTS[0]
        inner = self._mock_post({(first[1], first[2][0]): True})

        def _slow_losers(url, headers=None, json=None, timeout=None):
            if not url.startswith(first[1]):
                _time.sleep(2.0)  # slow lower-priority endpoints
            return inner(url, headers=headers, json=json, timeout=timeout)

        monkeypatch.setattr("sparkii_cli.auth.httpx.post", _slow_losers)
        t0 = _time.perf_counter()
        result = detect_zai_endpoint("test-key", timeout=5.0)
        elapsed = _time.perf_counter() - t0
        assert result is not None and result["id"] == first[0]
        assert elapsed < 1.5, f"early exit failed: waited {elapsed:.2f}s for losers"


# =============================================================================
# Kimi / Moonshot model list isolation tests
# =============================================================================

# =============================================================================
# Hugging Face provider model list tests
# =============================================================================




# =============================================================================
# NovitaAI provider tests (added by feat/add-novita-provider)
# =============================================================================




# =============================================================================
# MiniMax OAuth provider tests (added by feat/minimax-oauth-provider)
# =============================================================================




# =============================================================================
# DeepInfra provider tests
# =============================================================================
# Registration / alias / env-var invariants are asserted in
# TestProviderRegistry + TestResolveProvider above. The classes below
# cover the catalog/tag/pricing/profile machinery added on top of the
# baseline provider wiring.


@pytest.fixture
def _deepinfra_cache_isolation(monkeypatch):
    """Reset the module-level catalog cache around each DeepInfra test.

    The cache is keyed by base URL and would otherwise leak fixture data
    from one test into the next in the same session. The negative cache is
    reset too, so a test that simulates an unreachable catalog can't suppress
    a later test's fetch within the failure TTL.
    """
    import sparkii_cli.models as _models_mod
    monkeypatch.setattr(_models_mod, "_deepinfra_catalog_cache", {})
    monkeypatch.setattr(_models_mod, "_deepinfra_catalog_neg_cache", {})
    yield


@pytest.mark.usefixtures("_deepinfra_cache_isolation")
class TestFetchDeepInfraModels:
    """Tests for _fetch_deepinfra_models() live model discovery."""

    def test_returns_filtered_models_on_success(self, monkeypatch):
        monkeypatch.setenv("DEEPINFRA_API_KEY", "test-key")

        class _Resp:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def read(self):
                return json.dumps({"data": [
                    {"id": "meta-llama/Llama-3-70B-Instruct", "metadata": {}},
                    {"id": "mistralai/Mistral-Nemo-Instruct-2407", "metadata": {}},
                    {"id": "BAAI/bge-large-en-v1.5-embed", "metadata": {}},
                    {"id": "stabilityai/stable-diffusion-xl-base-1.0", "metadata": {}},
                ]}).encode()

        import sparkii_cli.models as models
        monkeypatch.setattr(
            models, "_urlopen_model_catalog_request", lambda *a, **kw: _Resp()
        )
        from sparkii_cli.models import _fetch_deepinfra_models
        result = _fetch_deepinfra_models()

        assert result is not None
        assert "meta-llama/Llama-3-70B-Instruct" in result
        assert "mistralai/Mistral-Nemo-Instruct-2407" in result
        # Embedding and image models should be excluded
        assert not any("embed" in m.lower() for m in result)
        assert not any("stable-diffusion" in m.lower() for m in result)



    def test_catalog_uses_credential_safe_opener(self, monkeypatch):
        import sparkii_cli.models as models

        seen = {}

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"data": []}).encode()

        def _safe_open(request, *, timeout):
            seen["authorization"] = request.get_header("Authorization")
            seen["timeout"] = timeout
            return _Resp()

        monkeypatch.setenv("DEEPINFRA_API_KEY", "test-key")
        monkeypatch.setattr(models, "_urlopen_model_catalog_request", _safe_open)

        assert models._fetch_deepinfra_catalog(force_refresh=True) == []
        assert seen == {"authorization": "Bearer test-key", "timeout": 5.0}




def _make_urlopen_returning(payload):
    """Helper: build a urlopen() shim returning a fixed JSON payload."""
    import json as _json

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return _json.dumps(payload).encode()

    return lambda *a, **kw: _Resp()


@pytest.mark.usefixtures("_deepinfra_cache_isolation")
class TestDeepInfraTagFiltering:
    """Contract tests for the shared _fetch_deepinfra_models_by_tag helper."""

    def test_filters_by_surface_tag_and_handles_rollout_states(self, monkeypatch):
        # One payload, several invariants in one test:
        #  - explicit surface tags are honored (chat / image-gen / tts / stt / embed)
        #  - capability-tags-only items fall through to the regex fallback
        #    (used during the surface-tag rollout)
        #  - the regex excludes id-name matches (whisper, embed, …)
        #  - a surface tag takes priority over the regex
        #  - ``metadata: None`` stubs are dropped
        payload = {"data": [
            {"id": "vendor/chat-tagged", "metadata": {"tags": ["chat"]}},
            {"id": "vendor/image-tagged", "metadata": {"tags": ["image-gen"]}},
            {"id": "vendor/tts-tagged", "metadata": {"tags": ["tts"]}},
            {"id": "vendor/stt-tagged", "metadata": {"tags": ["stt"]}},
            {"id": "vendor/embed-tagged", "metadata": {"tags": ["embed"]}},
            # capability-only — rolls through regex fallback
            {"id": "Qwen/Qwen3-30B", "metadata": {"tags": ["reasoning", "vision"]}},
            {"id": "openai/whisper-large", "metadata": {"tags": ["reasoning"]}},
            # surface tag overrides legacy regex exclusion
            {"id": "some-org/whisper-finetune-chat", "metadata": {"tags": ["chat"]}},
            # null metadata — stub model, must be skipped
            {"id": "stub-model", "metadata": None},
        ]}
        from sparkii_cli.models import _fetch_deepinfra_models_by_tag
        import sparkii_cli.models as _m

        for surface in ("chat", "image-gen", "tts", "stt", "embed"):
            monkeypatch.setattr(
                _m,
                "_urlopen_model_catalog_request",
                _make_urlopen_returning(payload),
            )
            # Reset cache between iterations so each surface re-parses the payload.
            _m._deepinfra_catalog_cache.clear()
            got = _fetch_deepinfra_models_by_tag(surface)
            assert got is not None
            ids = {item["id"] for item in got}
            assert "stub-model" not in ids  # null-metadata always skipped
            if surface == "chat":
                # explicit chat + capability-only (Qwen) + surface-tag-over-regex
                assert "vendor/chat-tagged" in ids
                assert "Qwen/Qwen3-30B" in ids
                assert "some-org/whisper-finetune-chat" in ids
                # regex still excludes capability-only items that match the excluder
                assert "openai/whisper-large" not in ids
            else:
                # non-chat surfaces only see explicit surface-tagged items
                for item in got:
                    assert surface in item["metadata"]["tags"]


@pytest.mark.usefixtures("_deepinfra_cache_isolation")
class TestDeepInfraPricingFetcher:
    """_fetch_deepinfra_pricing reshapes $/MTok values into per-token strings
    and is wired into the get_pricing_for_provider dispatch."""

    def test_pricing_shape_and_dispatch(self, monkeypatch):
        payload = {"data": [
            {
                "id": "vendor/model-a",
                "metadata": {
                    "tags": ["chat", "prompt_cache"],
                    "pricing": {
                        "input_tokens": 0.1,
                        "output_tokens": 0.3,
                        "cache_read_tokens": 0.02,
                    },
                },
            },
            {
                "id": "vendor/model-b",
                "metadata": {"tags": ["chat"], "pricing": {"input_tokens": 1.0, "output_tokens": 5.0}},
            },
            # non-chat — must not appear
            {"id": "vendor/model-image", "metadata": {"tags": ["image-gen"], "pricing": {"per_image_unit": 0.05}}},
        ]}
        import sparkii_cli.models as models
        monkeypatch.setattr(
            models,
            "_urlopen_model_catalog_request",
            _make_urlopen_returning(payload),
        )
        from sparkii_cli.models import get_pricing_for_provider

        # get_pricing_for_provider → _fetch_deepinfra_pricing dispatch path
        result = get_pricing_for_provider("deepinfra")
        assert set(result) == {"vendor/model-a", "vendor/model-b"}
        # Picker-shape: per-token strings under prompt/completion (+ cache_read when source had it)
        assert float(result["vendor/model-a"]["prompt"]) == pytest.approx(0.1 / 1_000_000)
        assert float(result["vendor/model-a"]["completion"]) == pytest.approx(0.3 / 1_000_000)
        assert "input_cache_read" in result["vendor/model-a"]
        assert "input_cache_read" not in result["vendor/model-b"]




