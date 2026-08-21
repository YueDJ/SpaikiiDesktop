# Sparkii Agent — Core Kernel

The agent kernel of Sparkii: a self-improving AI agent that creates skills from
experience, searches its own past conversations, and runs the same core across
every surface.

This repository is the **core package** (`sparkii-agent`). The frontend
surfaces — CLI, messaging gateway, TUI, desktop app, and docs site — consume
it as a library and live in the separate
[sparkii-frontends](https://github.com/YueDJ/SparkiiDesktop-Frontends)
repository.

## Layout

```
agent/       Conversation loop, provider adapters, memory, compression
tools/       The tool registry and tool implementations
providers/   Provider abstraction layer
core/        Shared services (config, credentials, plugins, models, media, …)
cron/        The cron scheduler
plugins/     Extension providers (memory, image-gen, kanban, observability, …)
skills/      Built-in skills
optional-skills/  Heavier / niche skills (not active by default)
tests/       Kernel tests
```

Top-level modules are the public kernel surface: `run_agent.py` (the
`AIAgent` class), `model_tools.py` (tool orchestration), `toolsets.py`,
`batch_runner.py`, the `sparkii_state*` session store, and shared leaf
helpers (`sparkii_constants.py`, `sparkii_logging.py`, `utils.py`, …).

## Install

```bash
pip install -e .        # editable — wheel/sdist builds are blocked outside
                        # Nix on purpose (see setup.py)
```

`sparkii-frontends` declares `sparkii-agent` as a dependency; in development
install this repo first, then the frontends repo.

## Test

```bash
pytest tests -q -p no:cacheprovider --basetemp=.pytest-tmp
```

The core→surface boundary is enforced by
`scripts/phase0_import_scan.py` and `scripts/phase0_block4_scan.py`
(core modules must never import the frontend packages).
