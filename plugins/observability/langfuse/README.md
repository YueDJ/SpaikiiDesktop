# Langfuse Observability Plugin

This plugin ships bundled with Sparkii but is **opt-in** — it only loads when
you explicitly enable it.

## Enable

Pick one:

```bash
# Interactive: walks you through credentials + SDK install + enable
sparkii tools  # → Langfuse Observability

# Manual
pip install langfuse
sparkii plugins enable observability/langfuse
```

## Required credentials

Set these in `~/.sparkii/.env` (or via `sparkii tools`):

```bash
SPARKII_LANGFUSE_PUBLIC_KEY=pk-lf-...
SPARKII_LANGFUSE_SECRET_KEY=sk-lf-...
SPARKII_LANGFUSE_BASE_URL=https://cloud.langfuse.com   # or your self-hosted URL
```

Without the SDK or credentials the hooks no-op silently — the plugin fails
open.

## Verify

```bash
sparkii plugins list                 # observability/langfuse should show "enabled"
sparkii chat -q "hello"              # then check Langfuse for a "Sparkii turn" trace
```

## Optional tuning

```bash
SPARKII_LANGFUSE_ENV=production       # environment tag
SPARKII_LANGFUSE_RELEASE=v1.0.0       # release tag
SPARKII_LANGFUSE_SAMPLE_RATE=0.5      # sample 50% of traces
SPARKII_LANGFUSE_MAX_CHARS=12000      # max chars per field (default: 12000)
SPARKII_LANGFUSE_DEBUG=true           # verbose plugin logging
```

## Disable

```bash
sparkii plugins disable observability/langfuse
```
