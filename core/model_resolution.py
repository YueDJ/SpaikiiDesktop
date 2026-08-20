"""Provider identity resolution (core).

Extracted verbatim from ``sparkii_cli.models`` during the Phase 0 trim.  Holds
provider grouping and provider-slug canonicalization only.  Catalog fetching and
provider detection remain in ``sparkii_cli.models``.
"""

from __future__ import annotations

from typing import Dict, List, Optional


PROVIDER_GROUPS: dict[str, tuple[str, str, list[str]]] = {
    "openai":   ("OpenAI",          "ChatGPT/Codex subscription or direct OpenAI API", ["openai-api"]),
    }

_SLUG_TO_GROUP: dict[str, str] = {
    slug: gid for gid, (_label, _desc, members) in PROVIDER_GROUPS.items() for slug in members
}

def provider_group_for_slug(slug: str) -> str:
    """Return the group_id a provider slug belongs to, or "" if ungrouped."""
    return _SLUG_TO_GROUP.get(str(slug or "").strip().lower(), "")

def group_providers(slugs):
    """Fold a flat ordered slug iterable into picker rows by provider group.

    DISPLAY ONLY. Used by every interactive picker (``sparkii model``, the
    setup wizard, the Telegram ``/model`` keyboard) so grouping is identical
    across surfaces.

    Each returned row is a dict::

        {"kind": "single", "slug": <slug>}                       # ungrouped, or
                                                                  # 1-member group
        {"kind": "group", "group_id": <gid>, "label": <label>,
         "description": <desc>, "members": [<slug>, ...]}        # 2+ members

    Rules:
      * A group row appears at the position of its FIRST present member, in
        the input order. Subsequent members fold into that row (and are not
        emitted again).
      * Member order inside a group follows ``PROVIDER_GROUPS`` declaration,
        restricted to the members actually present in ``slugs``.
      * A group reduced to a single present member degrades to a ``single``
        row — no pointless one-item submenu.
      * Slugs not in any group pass through as ``single`` rows, order
        preserved.
      * Duplicate slugs in the input are ignored after first sight.
    """
    seen: set[str] = set()
    # Which present members each group has, in declaration order.
    group_members: dict[str, list[str]] = {}
    for gid, (_label, _desc, members) in PROVIDER_GROUPS.items():
        present = [m for m in members if m in set(slugs)]
        if present:
            group_members[gid] = present

    rows = []
    emitted_groups: set[str] = set()
    for slug in slugs:
        s = str(slug or "").strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        gid = _SLUG_TO_GROUP.get(s, "")
        if not gid:
            rows.append({"kind": "single", "slug": s})
            continue
        if gid in emitted_groups:
            continue  # already folded at the first member's position
        emitted_groups.add(gid)
        members = group_members.get(gid, [s])
        if len(members) <= 1:
            rows.append({"kind": "single", "slug": members[0]})
        else:
            label, desc, _ = PROVIDER_GROUPS[gid]
            rows.append(
                {"kind": "group", "group_id": gid, "label": label,
                 "description": desc, "members": list(members)}
            )
    return rows

_PROVIDER_ALIASES = {
    "claude": "anthropic",
    "claude-code": "anthropic",
    "tencent": "tencent-tokenhub",
    "tokenhub": "tencent-tokenhub",
    "tencent-cloud": "tencent-tokenhub",
    "tencentmaas": "tencent-tokenhub",
    "lmstudio": "lmstudio",
    "lm-studio": "lmstudio",
    "lm_studio": "lmstudio",
    "ollama": "custom",  # bare "ollama" = local; use "ollama-cloud" for cloud
    }

def normalize_provider(provider: Optional[str]) -> str:
    """Normalize provider aliases to Sparkii' canonical provider ids.

    Note: ``"auto"`` passes through unchanged — use
    ``sparkii_cli.auth.resolve_provider()`` to resolve it to a concrete
    provider based on credentials and environment.
    """
    normalized = (provider or "openrouter").strip().lower()
    return _PROVIDER_ALIASES.get(normalized, normalized)

