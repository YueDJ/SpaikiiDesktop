# Upstream Sync Plan — NousResearch/hermes-agent → Sparkii

**Date:** 2026-08-11  
**Base:** `YueDJ/SpaikiiDesktop` `main` @ `e69aafb7a`  
**Upstream tip:** `NousResearch/hermes-agent` `main` @ `a31be4803`  
**Last synced upstream:** `8359e760b` (via PR #1 / `0ee1e6181`)  
**Delta:** **163 commits**, ~319 files, +22808 / -3563 lines

## Method (same as PR #1)

Direct merge of upstream into Sparkii conflicts on nearly every renamed path
(`hermes_*` ↔ `sparkii_*`). Repeat the proven approach:

1. Branch from current Sparkii `main`: `cursor/sync-sparkii-upstream-7bdc`
2. Detached worktree / temp branch at `upstream/main`
3. Mechanical Hermes→Sparkii rebrand commit on that tip
4. Merge rebranded tip into the Sparkii feature branch
5. Resolve conflicts + re-apply Sparkii-only invariants
6. Targeted tests → commit → push → draft PR

## Upstream themes to absorb (functional / security parity)

| Area | Highlights |
|------|------------|
| **Security** | Remove compromised blender MCP; `cryptography>=50`; npm advisory patches; profile export secret scrubbing; browser_exec secret stripping |
| **Desktop** | Orphan serve/gateway reap; renderer crash logging; custom provider profile scoping; sidebar all-profiles; HUD/titlebar/perf fixes; Fireworks disclosure |
| **Gateway / state** | Routed-profile busy modes; SessionDB read connection pooling; delegation callback / frozen-preview fixes; prompt.submit ordinal guards; rewind truncation recovery |
| **Kanban** | First-class review handoff lifecycle + many invariant fixes |
| **Browser** | Browser Use CLI 3.0 integration (default backend) |
| **File tools** | read_file guards (special files, unicode retry, jq/notebook), binary magic-byte naming |
| **Runtime / CLI** | Configurable `RLIMIT_NOFILE`; warm startup perf; AI_AGENT env attribution |
| **Skills / docs** | merge-reconciler skill; SDLC review lenses; session repair docs |

## Sparkii invariants to preserve (must not regress)

1. **Branding:** `sparkii` / `Sparkii` / `SPARKII_*` / `@sparkii/*` / `~/.sparkii` / launcher `sparkii`
2. **Port 9219** (coexist with Sparkii 9119) — `sparkii_cli/web_server.py`, `main.py`, dashboard defaults, desktop tests
3. **Default UI language `zh`** — `sparkii_cli/config_defaults.py` `display.language`, `apps/desktop/src/i18n/languages.ts` `DEFAULT_LOCALE`
4. **Third-party `HermesClaw` links** in READMEs (do not rename the product name)
5. **Feature cuts (keep deleted):**
   - Messaging platform adapters under `gateway/platforms/` (signal/weixin/whatsapp/yuanbao/qqbot/…)
   - Messaging platform plugins (`plugins/platforms/*` telegram/discord/…)
   - `plugins/sparkii-achievements`, `plugins/spotify`, `plugins/teams_pipeline`
   - `web/` dashboard frontend
   - Desktop messaging nav/route + HUD mode button + Noto Sans SC fonts
6. **Sparkii assets:** icons/logos, `.qoder` wiki, font/wordmark tweaks on empty/new session pages

## Known conflict hotspots

Upstream touched files we deleted (keep **ours = deleted**):

- `plugins/platforms/discord/adapter.py`
- `plugins/platforms/telegram/telegram_network.py`
- `plugins/platforms/photon/sidecar/package*.json`

Upstream `web/` has **no** new commits since last sync → deletion should stick cleanly.

HUD-related upstream fixes still apply to remaining HUD code paths; do **not** re-add the removed HUD mode button / messaging nav.

## Conflict resolution policy

| Conflict type | Resolution |
|---------------|------------|
| Branding / path / package renames | Prefer Sparkii naming |
| Port / locale defaults | Prefer Sparkii (9219, zh) |
| Deleted messaging/web/plugins vs upstream edits | Keep deletion |
| Pure functional/security/code fixes | Prefer upstream (after rebrand) |
| Mixed branding + logic | Take upstream logic, rewrite identifiers to Sparkii |

## Verification checklist

- [ ] `git merge-base --is-ancestor upstream/main HEAD` (via rebranded tip ancestry / content parity of upstream changes)
- [ ] No accidental reintroduction of removed messaging/`web`/achievements/spotify/teams_pipeline
- [ ] Port 9219 + `DEFAULT_LOCALE='zh'` + `display.language: zh` intact
- [ ] HermesClaw README refs intact
- [ ] Spot-check: no widespread `SPARKII_` / `hermes_cli` / `@sparkii/` regressions in code paths
- [ ] Targeted `scripts/run_tests.sh` on high-churn areas (state pooling, kanban review, browser use, profile export, desktop orphan reap, gateway busy modes)

## Out of scope

- Re-adding intentionally removed messaging platforms or web dashboard
- Changing Sparkii product branding back toward Hermes
- Full CI suite green gate (run targeted high-signal tests; note remaining risk)
