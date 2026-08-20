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
    _auth_lock_holder_for,
    _auth_lock_path,
    _auth_target_lock_holders,
    _auth_target_lock_holders_guard,
    _auth_store_lock,
    _file_lock,
    _load_auth_store,
    _same_path,
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

