# Sparkii CLI Reference

Live sources when anything looks stale: `sparkii --help`, `sparkii <command> --help`,
https://sparkii-agent.nousresearch.com/docs/reference/cli-commands

### Global Flags

```
sparkii [flags] [command]        (no subcommand = interactive chat)

  --version, -V             Show version
  -z, --oneshot PROMPT      One-shot: print ONLY the final response (for scripts/pipes)
  -m MODEL  --provider P    Model/provider override for this invocation
  -t, --toolsets LIST       Comma-separated toolsets for this invocation
  --resume, -r SESSION      Resume session by ID or title
  --continue, -c [NAME]     Resume by name, or most recent session
  --worktree, -w            Isolated git worktree mode (parallel agents)
  --skills, -s SKILL        Preload skills (comma-separate or repeat)
  --profile, -p NAME        Use a named profile
  --yolo                    Skip dangerous command approval
  --tui / --cli             Force the Ink TUI / classic REPL
  --ignore-rules            Skip AGENTS.md/SOUL.md/memory/skill injection
  --safe-mode               Disable ALL customizations (troubleshooting)
  --pass-session-id         Include session ID in system prompt
```

### Chat

```
sparkii chat [flags]
  -q, --query TEXT          Single query, non-interactive
  --image PATH              Attach a local image to a single query
  -Q, --quiet               Suppress banner, spinner, tool previews
  --checkpoints             Enable filesystem checkpoints (/rollback)
  --max-turns N             Cap tool-calling iterations
  --source TAG              Session source tag (default: cli)
```
(plus the global flags above)

### Configuration

```
sparkii setup [section]      Wizard (model|tts|terminal|gateway|tools|agent)
sparkii model                Interactive model/provider picker
sparkii fallback [add|remove|list]  Fallback provider chain
sparkii config [show|edit|get|set|unset|path|env-path|check|migrate]
sparkii login / logout       OAuth sign-in / clear stored auth
sparkii doctor [--fix]       Check dependencies and config
sparkii status [--all]       Component status
```

### Tools & Skills

```
sparkii tools [list|enable NAME|disable NAME]   Per-platform toolsets (curses UI with no args)

sparkii skills list|browse|search QUERY|inspect ID
sparkii skills install ID    Hub identifier OR a direct https://…/SKILL.md URL
sparkii skills config        Enable/disable skills per platform
sparkii skills check|update|uninstall|publish PATH
sparkii skills tap add REPO  Add a GitHub repo as a skill source
sparkii bundles              Skill bundles (one /<name> alias loads several skills)
```

### MCP Servers

```
sparkii mcp add NAME (--url or --command) | remove | list | test NAME
sparkii mcp catalog | install NAME     Curated catalog install
sparkii mcp configure NAME             Toggle tool selection
sparkii mcp serve                      Run Sparkii as an MCP server
```
Details (transport, tool discovery, catalog): `references/native-mcp.md`.

### Gateway (Messaging Platforms)

```
sparkii gateway run|install|start|stop|restart|status|setup
```

20+ platforms: Telegram, Discord, Slack, WhatsApp (Baileys + Business Cloud API), iMessage (Photon — `sparkii photon setup`), Signal, Email, SMS, Matrix, Mattermost, Teams, LINE, SimpleX, ntfy, Google Chat, Home Assistant, DingTalk, Feishu, WeCom, Weixin, API Server, Webhooks. Open WebUI connects via the API Server adapter. Most adapters ship under `plugins/platforms/`.
Docs: https://sparkii-agent.nousresearch.com/docs/user-guide/messaging/

### Sessions

```
sparkii sessions list|browse|rename ID TITLE|delete ID|export OUT|prune|stats
```

### Cron / Webhooks

```
sparkii cron list|create SCHED|edit ID|pause|resume|run ID|remove|status
    Schedules: '30m', 'every 2h', '0 9 * * *', ISO timestamp
sparkii webhook subscribe NAME|list|remove NAME|test NAME
```
Webhook payloads/routes: `references/webhooks.md`.

### Profiles

```
sparkii profile list|create NAME (--clone|--clone-all|--clone-from)|use|show|delete
sparkii profile rename A B | alias NAME | export NAME | import FILE
```

### Credentials & Pools

```
sparkii auth                 Interactive credential manager
sparkii auth add [PROVIDER]  Add OAuth or API-key credential (nous, openai-codex, qwen-oauth, …)
sparkii auth list|remove P IDX|reset PROVIDER|status
```
Multiple credentials per provider form a pool that rotates automatically and skips exhausted keys.

### Other

```
sparkii desktop / gui        Native desktop app
sparkii dashboard            Web admin panel + embedded chat (--stop / --status)
sparkii proxy                OpenAI-compatible local proxy backed by an OAuth provider
sparkii portal               Quick setup / sign in via Nous Portal
sparkii kanban <verb>        Multi-agent work-queue board
sparkii project              Named multi-folder workspaces
sparkii skin list|use|set    Switch/tweak skins (see references/themes.md)
sparkii pets <verb>          Pet mascots (see references/petdex.md)
sparkii memory setup|status|off|reset   Memory provider
sparkii secrets bitwarden|onepassword   External secret stores
sparkii moa                  Mixture-of-Agents slots
sparkii hooks / security / backup / import / checkpoints / console
sparkii logs [-f] [errors]   View agent/error logs
sparkii send                 One-off message through a gateway platform
sparkii pairing / plugins / insights / journey / computer-use
sparkii acp                  ACP server (IDE integration)
sparkii completion bash|zsh|fish
sparkii update / uninstall / claw migrate
```

Plugin- and provider-supplied subcommands (e.g. `sparkii photon setup`) only appear once their plugin is installed/active.

### Where to Find Things

| Looking for... | Location |
|---|---|
| Config options | `sparkii config edit` · [Configuration docs](https://sparkii-agent.nousresearch.com/docs/user-guide/configuration) |
| Tools / toolsets | `sparkii tools list` · [Tools reference](https://sparkii-agent.nousresearch.com/docs/reference/tools-reference) |
| Skills catalog | `sparkii skills browse` · [Skills catalog](https://sparkii-agent.nousresearch.com/docs/reference/skills-catalog) |
| Provider setup | `sparkii model` · [Providers guide](https://sparkii-agent.nousresearch.com/docs/integrations/providers) |
| Env variables | `sparkii config env-path` · [Env vars reference](https://sparkii-agent.nousresearch.com/docs/reference/environment-variables) |
| Gateway logs | `~/.sparkii/logs/gateway.log` (or `sparkii logs`) |
| Sessions | `sparkii sessions browse` (reads state.db) |
