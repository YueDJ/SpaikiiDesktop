# Upstream Sync Plan — NousResearch/hermes-agent → Sparkii

**Date:** 2026-08-20  
**Base:** `YueDJ/SparkiiDesktop` `main` @ `ece88d929` (+ rebrand-helper commit)  
**Upstream tip:** `NousResearch/hermes-agent` `main` @ `fab8479aa0`  
**Last synced upstream:** `a31be4803` (via PR #2 / `5cd730c5d`)  
**Delta:** **~2260 commits**, ~2600 files, +327k / -26k lines (pre-rebrand)

## Method (same as PR #1 / #2)

1. Branch from current Sparkii `main`: `cursor/sync-hermes-upstream-7739`
2. Worktree at `upstream/main`
3. Mechanical Hermes→Sparkii rebrand (strengthened helper: `hermes_*`, CamelCase, HermesBench protect, skip `.git`)
4. Merge rebranded tip into the Sparkii feature branch
5. Resolve conflicts + re-apply Sparkii-only invariants / feature cuts
6. Targeted tests → commit → push → draft PR

## Sparkii invariants preserved

1. Branding: `sparkii` / `Sparkii` / `SPARKII_*` / `@sparkii/*` / `~/.sparkii` / launcher `sparkii`
2. Port **9219** (coexist with Hermes 9119)
3. Default UI language **zh** — `display.language`, `DEFAULT_LOCALE`
4. Third-party **HermesClaw** / **HermesBench** names preserved
5. Feature cuts kept deleted: messaging adapters/plugins, `web/`, achievements, spotify, teams_pipeline, desktop messaging UI / HUD mode button / Noto Sans SC
6. Desktop bundle id `com.yuedj.sparkiidesktop`

## Conflict resolution policy used

| Conflict type | Resolution |
|---------------|------------|
| modify/delete (ours deleted) | Keep deletion |
| Branding / path / package renames | Prefer Sparkii naming |
| Port / locale / bundle id | Prefer Sparkii (9219, zh, com.yuedj.sparkiidesktop) |
| Pure functional upstream in non-cut files | Prefer rebranded upstream |
| Cut-centric modules (auth spotify, cron delivery stubs, toolsets messaging, pyproject extras) | Prefer Sparkii cut |
| Mixed gateway/run adapter factory | Keep upstream body; restore Sparkii built-in adapter fallthrough (api_server/webhook only) |

## Out of scope

- Re-adding intentionally removed messaging platforms or web dashboard
- Changing Sparkii product branding back toward Hermes
