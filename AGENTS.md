# Sparkii Agent — Core Kernel Engineering Guide

Instructions for AI coding assistants and developers working on the
sparkii-agent **core kernel**.

**Never give up on the right solution.**

## What the core is

Sparkii is a personal AI agent that runs the same agent core across a CLI, a
messaging gateway (Telegram, Discord, Slack, and ~20 other platforms), a TUI,
and an Electron desktop app. The **core kernel in this repository** owns the
agent loop, the tool registry, the session store, the scheduler, and the
extension (plugin/skill) machinery. The frontend surfaces
(`cli.py`, `gateway/`, `sparkii_cli/`, `tui_gateway/`, `acp_adapter/`,
`ui-tui/`, `apps/`, `website/`) live in the separate
**sparkii-frontends** repository and consume this package as a library.

Two properties shape almost every design decision and are the lens for
reviewing any change:

- **Per-conversation prompt caching is sacred.** A long-lived conversation
  reuses a cached prefix every turn. Anything that mutates past context,
  swaps toolsets, or rebuilds the system prompt mid-conversation invalidates
  that cache and multiplies the user's cost. We do not do it (the one
  exception is context compression).
- **The core is a narrow waist; capability lives at the edges.** Every model
  tool we add is sent on every API call, so the bar for a new *core* tool is
  high. Most new capability should arrive as a CLI command + skill, a
  service-gated tool, a plugin, or an MCP server — not as core surface.

## The boundary (enforced)

The core package must **never import the frontend packages** (`gateway`,
`sparkii_cli`, `tui_gateway`, `acp_adapter`, `cli`). When the kernel needs a
frontend-owned capability:

1. Extract the shared implementation into `core/` and have the frontend
   re-export it (preferred for pure functions and data contracts), or
2. Define a provider hook in `core/` (`set_*_provider()` / `get_*()`) that the
   frontend registers at import time, with a graceful core-only default.

Verification:

```bash
.venv/Scripts/python.exe scripts/phase0_import_scan.py    # core → surface: must be 0
.venv/Scripts/python.exe scripts/phase0_block4_scan.py    # core repo → frontends: only dev scripts may remain
```

## Contribution Rubric — What We Want / What We Don't

### What we want

- **Fix real bugs, well.** A good fix reproduces the symptom on current
  `main`, points to the exact line where it manifests, and fixes the whole bug
  class — sibling call paths included — not just the one site the reporter hit.
- **Keep the core narrow.** Prefer, in order: extend existing code → CLI
  command + skill → service-gated tool (`check_fn`) → plugin → MCP server in
  the catalog → new core tool (last resort). See "The Footprint Ladder".
- **Extend, don't duplicate.** Before adding a module/manager/hook, check
  whether existing infrastructure already covers the use case.
- **Behavior contracts over snapshots.** Tests should assert how two pieces of
  data must relate (invariants), not freeze a current value.
- **E2E validation, not just green unit mocks.** For anything touching
  resolution chains, config propagation, security boundaries, remote
  backends, or file/network I/O, exercise the real path with real imports
  against a temp `SPARKII_HOME`.
- **Cache-, alternation-, and invariant-safe.** Preserve prompt caching, strict
  message role alternation (never two same-role messages in a row; never a
  synthetic user message injected mid-loop), and a system prompt that is
  byte-stable for the life of a conversation.

### What we don't want (rejected even when well-built)

- **Speculative infrastructure.** Hooks, callbacks, or extension points with no
  concrete consumer.
- **New `SPARKII_*` env vars for non-secret config.** `.env` is for secrets
  only (API keys, tokens, passwords). Behavioral settings go in `config.yaml`.
- **A new core tool when terminal + file already do the job, or when a skill
  would.**
- **"Fixes" that destroy the feature they secure.** Read the original commit's
  intent (`git log -p -S`) before restricting behavior.
- **Outbound telemetry / usage attribution without opt-in gating.**
- **Change-detector tests, cache-breaking mid-conversation, dead code wired in
  without E2E proof, and plugins that touch core files.**

### Verify the premise before calling it a bug

- "Intentional design, not a gap." A limitation that looks like an oversight is
  often deliberate (e.g. profiles are independent islands on purpose).
- "The premise doesn't hold against how X actually works." Trace the real
  code/runtime before accepting a rationale. If you can't point to the exact
  line where the bug manifests AND show the fix changes that line's behavior,
  you haven't verified the premise.

The throughline: **verify the claim AND the intent against the codebase before
writing or merging a fix.**

## The Footprint Ladder (new capability decision)

Each rung adds more permanent surface than the one above. Choose the highest
(least-footprint) rung that correctly solves the problem:

1. **Extend existing code** — zero new surface.
2. **CLI command + skill** — manages config/state/infra expressible as shell
   commands; zero model-tool footprint.
3. **Service-gated tool (`check_fn`)** — needs structured params/returns AND
   only appears when a prerequisite is configured.
4. **Plugin** — third-party/niche/user-specific capability in
   `~/.sparkii/plugins/` or a pip package.
5. **MCP server (in the catalog)** — structured I/O the agent invokes, not
   core-fundamental.
6. **New core tool** — only when the capability is fundamental, broadly useful
   to nearly every user, and unreachable via terminal + file (or an MCP
   server).

## Project Structure (kernel)

```
run_agent.py          # AIAgent class — core conversation loop (~12k LOC)
model_tools.py        # Tool orchestration, discover_builtin_tools(), handle_function_call()
toolsets.py           # Toolset definitions, _SPARKII_CORE_TOOLS list
sparkii_state*.py     # SessionDB — SQLite session store (FTS5 search)
agent/                # Agent internals (provider adapters, memory, caching, compression, …)
tools/                # Tool implementations — auto-discovered via tools/registry.py
core/                 # Shared kernel services (config, credentials, plugins, models, …)
providers/            # Provider abstraction
cron/                 # Scheduler — jobs.py, scheduler.py
plugins/              # Extension providers (memory, image-gen, kanban, observability, …)
skills/, optional-skills/   # Built-in skills
```

## File Dependency Chain

```
tools/registry.py  (no deps — imported by all tool files)
       ↑
tools/*.py  (each calls registry.register() at import time)
       ↑
model_tools.py  (imports tools/registry + triggers tool discovery)
       ↑
run_agent.py, batch_runner.py, cron/, agent/
```

## AIAgent Class (run_agent.py)

`AIAgent.__init__` takes ~60 parameters (credentials, routing, callbacks,
session context, budget, credential pool, etc.). The core loop inside
`run_conversation()` is entirely synchronous, with interrupt checks, budget
tracking, and a one-turn grace call:

```python
while (api_call_count < self.max_iterations and self.iteration_budget.remaining > 0) \
        or self._budget_grace_call:
    if self._interrupt_requested: break
    response = client.chat.completions.create(model=model, messages=messages, tools=tool_schemas)
    if response.tool_calls:
        for tool_call in response.tool_calls:
            result = handle_function_call(tool_call.name, tool_call.args, task_id)
            messages.append(tool_result_message(result))
        api_call_count += 1
    else:
        return response.content
```

Messages follow OpenAI format: `{"role": "system/user/assistant/tool", ...}`.
Reasoning content is stored in `assistant_msg["reasoning"]`.

## Development Environment

```bash
# Prefer .venv; fall back to venv.
source .venv/bin/activate   # or: source venv/bin/activate
```

`scripts/run_tests.sh` probes `.venv` first, then `venv`, then
`$HOME/.sparkii/sparkii-agent/venv`.

## Tests

```bash
.venv/Scripts/python.exe -m pytest <paths> -q -p no:cacheprovider --basetemp=.pytest-tmp
```

Known environment-only failures (do not fix): Chinese-Windows GBK encoding,
`~/.sparkii` vs `AppData/Local/sparkii` path differences, `/proc`-only tests,
POSIX/PTY tests on Windows, and tests for retired platforms/providers.
