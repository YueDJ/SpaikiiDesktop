"""Upstream adapter registry for the local proxy server.

All OAuth upstream adapters (Nous Portal, xAI Grok) were removed with their
providers.  The registry stays empty; the proxy command degrades gracefully
until a future OAuth provider ships a new adapter.
"""

from typing import Dict, Type

from sparkii_cli.proxy.adapters.base import UpstreamAdapter

# Registry of available adapter classes keyed by provider name as used on
# the ``sparkii proxy start --provider <name>`` CLI flag.
ADAPTERS: Dict[str, Type[UpstreamAdapter]] = {}


def get_adapter(name: str) -> UpstreamAdapter:
    """Instantiate an adapter by provider name.

    Raises:
        ValueError: if ``name`` is not a registered adapter.
    """
    key = (name or "").strip().lower()
    if key not in ADAPTERS:
        available = ", ".join(sorted(ADAPTERS)) or "(none)"
        raise ValueError(
            f"Unknown proxy upstream provider: {name!r}. Available: {available}"
        )
    return ADAPTERS[key]()


__all__ = ["UpstreamAdapter", "ADAPTERS", "get_adapter"]
