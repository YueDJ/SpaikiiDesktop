"""Core plugin-platform contract.

``PlatformEntry`` describes a gateway platform adapter registered by a plugin
via ``PluginContext.register_platform()``.  It lives in core so the plugin
loader can construct entries without importing ``gateway``; the gateway's
``PlatformRegistry`` imports it from here (surface -> core).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional


@dataclass
class PlatformEntry:
    """Metadata and factory for a single platform adapter."""

    # Identifier used in config.yaml (e.g. "irc", "viber").
    name: str

    # Human-readable label (e.g. "IRC", "Viber").
    label: str

    # Factory callable: receives a PlatformConfig, returns an adapter instance.
    # Using a factory instead of a bare class lets plugins do custom init
    # (e.g. passing extra kwargs, wrapping in try/except).
    adapter_factory: Callable[[Any], Any]

    # PASSIVE dependency probe: returns True when the platform's dependencies
    # are available RIGHT NOW.  Must be side-effect free — it is called from
    # status displays (``sparkii setup``, ``sparkii status``, the dashboard
    # readiness probe) and the config enablement pass, none of which may
    # trigger a pip install.  Put install logic in ``ensure_deps_fn`` instead.
    check_fn: Callable[[], bool]

    # Optional: given a PlatformConfig, is it properly configured?
    # If None, the registry skips config validation and lets the adapter
    # fail at connect() time with a descriptive error.
    validate_config: Optional[Callable[[Any], bool]] = None

    # ACTIVE dependency installer: make the platform's dependencies available,
    # installing them (pip / lazy_deps) if needed.  Returns True once deps are
    # importable, False if they could not be installed.  Called by
    # ``create_adapter()`` when ``check_fn`` returns False — i.e. exactly at
    # the moment the gateway is about to bring the platform up and the user
    # has it enabled/configured.  None = no auto-install; a False ``check_fn``
    # is then a hard block (correct for platforms with no optional deps).
    #
    # Why two fields (#79812): when the ACTIVE installer was registered as
    # ``check_fn``, every status display pip-installed SDKs as a side effect
    # (desktop boot-loop at 94%, see gateway/config.py enablement comments);
    # when the PASSIVE probe was registered instead, ``create_adapter()``
    # returned None before ``connect()`` could lazy-install, so the deps
    # never installed at all (Teams deadlock).  Splitting the two roles makes
    # both call sites correct by construction.
    ensure_deps_fn: Optional[Callable[[], bool]] = None

    # Optional: given a PlatformConfig, is the platform connected/enabled?
    # Used by ``GatewayConfig.get_connected_platforms()`` and setup UI status.
    # If None, falls back to ``validate_config`` or ``check_fn``.
    is_connected: Optional[Callable[[Any], bool]] = None

    # Env vars this platform needs (for ``sparkii setup`` display).
    required_env: list = field(default_factory=list)

    # Hint shown when check_fn returns False.
    install_hint: str = ""

    # Optional setup function for interactive configuration.
    # Signature: () -> None (prompts user, saves env vars).
    # If None, falls back to _setup_standard_platform (needs token_var + vars)
    # or a generic "set these env vars" display.
    setup_fn: Optional[Callable[[], None]] = None

    # "builtin" or "plugin"
    source: str = "plugin"

    # Name of the plugin manifest that registered this entry (empty for
    # built-ins).  Used by ``sparkii gateway setup`` to auto-enable the
    # owning plugin when the user configures its platform.
    plugin_name: str = ""

    # ── Auth env var names (for _is_user_authorized integration) ──
    # E.g. "IRC_ALLOWED_USERS" — checked for comma-separated user IDs.
    allowed_users_env: str = ""
    # E.g. "IRC_ALLOW_ALL_USERS" — if truthy, all users authorized.
    allow_all_env: str = ""

    # ── Message limits ──
    # Max message length for smart-chunking.  0 = no limit.
    max_message_length: int = 0

    # ── Privacy ──
    # If True, session descriptions redact PII (phone numbers, etc.)
    pii_safe: bool = False

    # ── Display ──
    # Emoji for CLI/gateway display (e.g. "💬")
    emoji: str = "🔌"

    # Whether this platform should appear in _UPDATE_ALLOWED_PLATFORMS
    # (allows /update command from this platform).
    allow_update_command: bool = True

    # ── LLM guidance ──
    # Platform hint injected into the system prompt (e.g. "You are on IRC.
    # Do not use markdown.").  Empty string = no hint.
    platform_hint: str = ""

    # ── Env-driven auto-configuration ──
    # Optional: read env vars, return a dict of ``PlatformConfig.extra`` fields
    # to seed when the platform is auto-enabled.  Called during
    # ``_apply_env_overrides`` BEFORE the adapter is constructed, so
    # ``gateway status`` etc. can reflect env-only configuration without
    # instantiating the adapter.  Return ``None`` (or an empty dict) to skip.
    # Signature: () -> Optional[dict[str, Any]]
    env_enablement_fn: Optional[Callable[[], Optional[dict]]] = None

    # ── YAML→env config bridge ──
    # Optional: translate this platform's ``config.yaml`` keys into env vars
    # and/or seed ``PlatformConfig.extra`` directly.  Lets a plugin own its
    # YAML config translation instead of forcing core ``gateway/config.py``
    # to know every platform's schema.
    #
    # Signature: (yaml_cfg: dict, platform_cfg: dict) -> Optional[dict]
    # Called from ``load_gateway_config()`` after the generic shared-key loop
    # and before ``_apply_env_overrides``.  Mutating ``os.environ`` is allowed
    # (use ``not os.getenv(...)`` guards to preserve env > YAML precedence);
    # any returned dict is merged into ``PlatformConfig.extra``.  Exceptions
    # are caught and logged at debug level.
    # See website/docs/developer-guide/adding-platform-adapters.md for the
    # full contract and a worked example.
    apply_yaml_config_fn: Optional[Callable[[dict, dict], Optional[dict]]] = None

    # Optional: home-channel env var name for cron/notification delivery
    # (e.g. ``"IRC_HOME_CHANNEL"``).  When set, ``cron.scheduler`` treats this
    # platform as a valid ``deliver=<name>`` target and reads the env var to
    # resolve the default chat/room ID.  Empty = no cron home-channel support.
    cron_deliver_env_var: str = ""

    # ── Target parsing ──
    # Optional: callable that parses a raw target string for this platform into
    # a (chat_id, thread_id) tuple, or None if the string is not a recognized
    # explicit target.  Invoked by ``tools/send_message_tool._parse_target_ref``
    # before channel-directory fallback so plugin platforms can declare their
    # own native target syntax (e.g. ``fmsg:@alice@example.com``) without
    # hard-casing in Sparkii core.
    #
    # Signature:
    #     (target_ref: str) -> Optional[tuple[str, Optional[str]]]
    #
    # If the callable returns None the target proceeds to channel-directory
    # resolution. No opaque fallback is applied.
    parse_target_ref_fn: Optional[Callable[[str], Optional[tuple[str, Optional[str]]]]] = None

    # Optional validation applied after parsing/normalization or
    # channel-directory resolution. Return True to accept, False to reject, or
    # a non-empty string to reject with that diagnostic.
    validate_target_ref_fn: Optional[Callable[[str], bool | str]] = None

    # Optional whole-request handler for custom platform delivery. Receives
    # (args, normalized_chat_id, platform_name, pconfig) and may be sync/async.
    # Prefer standalone_sender_fn when the standard send contract is enough.
    send_message_handler: Optional[Callable[[dict, str, str, Any], Any]] = None

    # ── Standalone (out-of-process) sending ──
    # Optional: async coroutine that delivers a message without a live
    # gateway adapter.  Called by ``tools/send_message_tool._send_via_adapter``
    # when ``cron`` runs in a separate process from the gateway and the
    # in-process adapter weakref is therefore ``None``.
    #
    # Signature:
    #     async (pconfig, chat_id, message, *, thread_id=None,
    #            media_files=None, force_document=False) -> dict
    #
    # Returns ``{"success": True, "message_id": ...}`` on success or
    # ``{"error": str}`` on failure.  Plugin authors typically open an
    # ephemeral connection / acquire a fresh OAuth token, send, and close.
    # Without this hook, plugin platforms cannot serve as cron ``deliver=``
    # targets when the gateway is not co-resident with the cron process.
    standalone_sender_fn: Optional[Callable[..., Awaitable[dict]]] = None
