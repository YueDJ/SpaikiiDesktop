"""Gateway-side registration of cron delivery providers (Block 4 Step 2b).

The cron scheduler (core) delivers job output through gateway machinery; it
must not import the gateway package.  This module registers a lazy namespace
with the core bridge.  Importing it is the wiring point — ``gateway/__init__``
does so, so every gateway process (and any frontend process that imports the
gateway, including standalone ``sparkii cron run``) gets cron delivery.
"""

from __future__ import annotations

from types import SimpleNamespace

from core.cron_delivery import set_cron_delivery_provider


def _cron_delivery_context() -> SimpleNamespace:
    """Build the delivery namespace (lazy so imports cannot cycle at startup)."""
    from core.response_filters import is_autonomous_silence_response
    from gateway.config import Platform, PlatformConfig
    from gateway.delivery import (
        DeliveryRouter,
        DeliveryTarget,
        _looks_like_int,
        looks_like_telegram_private_chat_id,
        resolve_delivery_transport,
    )
    from gateway.media_policy import apply_media_policy_env
    from gateway.mirror import mirror_to_session
    from gateway.platforms.base import (
        BasePlatformAdapter,
        should_send_media_as_audio,
        validate_media_delivery_path,
    )
    from gateway.relay import relay_fronted_platforms
    from gateway.session import SessionSource

    return SimpleNamespace(
        Platform=Platform,
        PlatformConfig=PlatformConfig,
        SessionSource=SessionSource,
        BasePlatformAdapter=BasePlatformAdapter,
        DeliveryRouter=DeliveryRouter,
        DeliveryTarget=DeliveryTarget,
        _looks_like_int=_looks_like_int,
        apply_media_policy_env=apply_media_policy_env,
        is_autonomous_silence_response=is_autonomous_silence_response,
        looks_like_telegram_private_chat_id=looks_like_telegram_private_chat_id,
        mirror_to_session=mirror_to_session,
        relay_fronted_platforms=relay_fronted_platforms,
        resolve_delivery_transport=resolve_delivery_transport,
        should_send_media_as_audio=should_send_media_as_audio,
        validate_media_delivery_path=validate_media_delivery_path,
    )


set_cron_delivery_provider(_cron_delivery_context)
