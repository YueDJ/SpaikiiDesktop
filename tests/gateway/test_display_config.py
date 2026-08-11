"""Tests for gateway.display_config — per-platform display/verbosity resolver."""


# ---------------------------------------------------------------------------
# Resolver: resolution order
# ---------------------------------------------------------------------------

class TestResolveDisplaySetting:
    """resolve_display_setting() resolves with correct priority."""

    def test_explicit_platform_override_wins(self):
        """display.platforms.<plat>.<key> takes top priority."""
        from gateway.display_config import resolve_display_setting

        config = {
            "display": {
                "tool_progress": "all",
                "platforms": {
                    "telegram": {"tool_progress": "verbose"},
                },
            }
        }
        assert resolve_display_setting(config, "telegram", "tool_progress") == "verbose"

    def test_global_setting_when_no_platform_override(self):
        """Falls back to display.<key> when no platform override exists."""
        from gateway.display_config import resolve_display_setting

        config = {
            "display": {
                "tool_progress": "new",
                "platforms": {},
            }
        }
        assert resolve_display_setting(config, "telegram", "tool_progress") == "new"


    def test_platform_override_only_affects_that_platform(self):
        """Other platforms are unaffected by a specific platform override."""
        from gateway.display_config import resolve_display_setting

        config = {
            "display": {
                "tool_progress": "all",
                "platforms": {
                    "slack": {"tool_progress": "off"},
                },
            }
        }
        assert resolve_display_setting(config, "slack", "tool_progress") == "off"
        assert resolve_display_setting(config, "telegram", "tool_progress") == "all"


# ---------------------------------------------------------------------------
# Backward compatibility: tool_progress_overrides
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    """Legacy tool_progress_overrides is still respected as a fallback."""

    def test_legacy_overrides_read(self):
        """tool_progress_overrides is read when no platforms entry exists."""
        from gateway.display_config import resolve_display_setting

        config = {
            "display": {
                "tool_progress": "all",
                "tool_progress_overrides": {
                    "signal": "off",
                    "telegram": "verbose",
                },
            }
        }
        assert resolve_display_setting(config, "signal", "tool_progress") == "off"
        assert resolve_display_setting(config, "telegram", "tool_progress") == "verbose"


# ---------------------------------------------------------------------------
# YAML normalisation
# ---------------------------------------------------------------------------

class TestYAMLNormalisation:
    """YAML 1.1 quirks (bare off → False, on → True) are handled."""

    def test_tool_progress_false_normalised_to_off(self):
        """YAML's bare `off` parses as False — normalised to 'off' string."""
        from gateway.display_config import resolve_display_setting

        config = {"display": {"tool_progress": False}}
        assert resolve_display_setting(config, "telegram", "tool_progress") == "off"


    def test_only_long_running_visibility_accepts_generic_mode(self):
        from gateway.display_config import resolve_display_setting

        config = {
            "display": {
                "platforms": {
                    "whatsapp": {
                        "thinking_progress": "generic",
                        "interim_assistant_messages": "generic",
                        "long_running_notifications": "generic",
                    }
                }
            }
        }
        assert resolve_display_setting(config, "whatsapp", "thinking_progress") is False
        assert resolve_display_setting(config, "whatsapp", "interim_assistant_messages") is False
        assert resolve_display_setting(config, "whatsapp", "long_running_notifications") == "generic"

    def test_thinking_progress_string_false_normalised_to_false(self):
        from gateway.display_config import resolve_display_setting

        config = {"display": {"platforms": {"whatsapp": {"thinking_progress": "false"}}}}
        assert resolve_display_setting(config, "whatsapp", "thinking_progress") is False


# ---------------------------------------------------------------------------
# Built-in platform defaults (tier system)
# ---------------------------------------------------------------------------

class TestPlatformDefaults:
    """Built-in defaults reflect platform capability tiers."""

    def test_core_platform_defaults(self):
        """Core platforms (webhook, api_server) have correct defaults."""
        from gateway.display_config import resolve_display_setting

        # Webhook: minimal tier
        assert resolve_display_setting({}, "webhook", "tool_progress") == "off"
        # API server: high tier but no tool preview
        assert resolve_display_setting({}, "api_server", "tool_preview_length") == 0

    def test_global_defaults_apply_to_unknown_platforms(self):
        """Unknown platforms fall through to global defaults."""
        from gateway.display_config import resolve_display_setting

        # Global default for tool_progress is "all"
        assert resolve_display_setting({}, "unknown_platform", "tool_progress") == "all"


# ---------------------------------------------------------------------------
# Config migration: tool_progress_overrides → display.platforms
# ---------------------------------------------------------------------------

class TestConfigMigration:
    """Version 16 migration moves tool_progress_overrides into display.platforms."""

    def test_migration_creates_platforms_entries(self, tmp_path, monkeypatch):
        """Old overrides are migrated into display.platforms.<plat>.tool_progress."""
        import yaml

        config_path = tmp_path / "config.yaml"
        config = {
            "_config_version": 15,
            "display": {
                "tool_progress_overrides": {
                    "signal": "off",
                    "telegram": "all",
                },
            },
        }
        config_path.write_text(yaml.dump(config), encoding="utf-8")

        monkeypatch.setenv("SPARKII_HOME", str(tmp_path))
        # Re-import to pick up the new SPARKII_HOME
        import importlib
        import sparkii_cli.config as cfg_mod
        importlib.reload(cfg_mod)

        result = cfg_mod.migrate_config(interactive=False, quiet=True)
        # Re-read config
        updated = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        platforms = updated.get("display", {}).get("platforms", {})
        assert platforms.get("signal", {}).get("tool_progress") == "off"
        assert platforms.get("telegram", {}).get("tool_progress") == "all"


# ---------------------------------------------------------------------------
# Streaming per-platform (None = follow global)
# ---------------------------------------------------------------------------

class TestStreamingPerPlatform:
    """Streaming per-platform override semantics."""


    def test_explicit_false_disables(self):
        """Explicit False disables streaming for that platform."""
        from gateway.display_config import resolve_display_setting

        config = {
            "display": {
                "platforms": {"telegram": {"streaming": False}},
            }
        }
        assert resolve_display_setting(config, "telegram", "streaming") is False


# ---------------------------------------------------------------------------
# cleanup_progress — opt-in deletion of temporary progress bubbles
# ---------------------------------------------------------------------------

class TestCleanupProgress:
    """``cleanup_progress`` is off by default and resolvable per-platform."""

    def test_default_off_for_all_platforms(self):
        """No config set → cleanup_progress resolves to False everywhere."""
        from gateway.display_config import resolve_display_setting

        for plat in ("telegram", "discord", "slack", "email"):
            assert resolve_display_setting({}, plat, "cleanup_progress") is False


    def test_yaml_true_string_normalises_to_true(self):
        """String 'true'/'yes'/'on' all resolve to True."""
        from gateway.display_config import resolve_display_setting

        for val in ("true", "yes", "on", "1"):
            config = {
                "display": {
                    "platforms": {"telegram": {"cleanup_progress": val}},
                }
            }
            assert resolve_display_setting(config, "telegram", "cleanup_progress") is True, val


class TestToolProgressGrouping:
    """resolve_display_setting() for the tool_progress_grouping knob."""

    def test_default_is_accumulate(self):
        """No config anywhere → global default 'accumulate'."""
        from gateway.display_config import resolve_display_setting

        assert (
            resolve_display_setting({}, "telegram", "tool_progress_grouping")
            == "accumulate"
        )

    def test_global_separate(self):
        from gateway.display_config import resolve_display_setting

        config = {"display": {"tool_progress_grouping": "separate"}}
        assert (
            resolve_display_setting(config, "discord", "tool_progress_grouping")
            == "separate"
        )


class TestReasoningStyle:
    """Per-platform reasoning render style (code | blockquote | subtext)."""

    def test_global_default_reasoning_style_is_code(self):
        from gateway.display_config import resolve_display_setting

        # All platforms default to "code" reasoning style
        for plat in ("api_server", "webhook", "unknown"):
            assert (
                resolve_display_setting({}, plat, "reasoning_style") == "code"
            ), plat


class TestLiveStatusSetting:
    """display.live_status — tri-state normalisation + platform overrides."""

    def test_default_is_full(self):
        from gateway.display_config import resolve_display_setting

        assert resolve_display_setting({}, "slack", "live_status") == "full"


