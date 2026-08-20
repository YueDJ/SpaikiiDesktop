"""Fast-path fixtures shared across tests/run_agent/.

Many tests in this directory exercise the retry/backoff paths in the
agent loop. Production code uses ``jittered_backoff(base_delay=5.0)``
with a ``while time.time() < sleep_end`` loop — a single retry test
spends 5+ seconds of real wall-clock time on backoff waits.

Mocking ``jittered_backoff`` to return 0.0 collapses the while-loop
to a no-op (``time.time() < time.time() + 0`` is false immediately),
which handles the most common case without touching ``time.sleep``.

We deliberately DO NOT mock ``time.sleep`` here — some tests
(test_interrupt_propagation, test_primary_runtime_restore, etc.) use
the real ``time.sleep`` for threading coordination or assert that it
was called with specific values. Tests that want to additionally
fast-path direct ``time.sleep(N)`` calls in production code should
monkeypatch ``run_agent.time.sleep`` locally (see
``test_anthropic_error_handling.py`` for the pattern).
"""

from __future__ import annotations

import pytest

# Register the product-layer background-review provider once for the whole
# test session: the core AIAgent gets the review harness injected rather than
# importing it (dependency inversion). Registration is session-stable — like
# the CLI/gateway/TUI surfaces — so every test in this directory sees the
# provider regardless of collection order.
try:
    from run_agent import set_background_review_provider
    from sparkii_cli.background_review import build_background_review_provider

    set_background_review_provider(build_background_review_provider())
except Exception:
    pass


@pytest.fixture(autouse=True)
def _fast_retry_backoff(monkeypatch):
    """Short-circuit retry backoff for all tests in this directory."""
    try:
        import run_agent
    except ImportError:
        return

    monkeypatch.setattr(run_agent, "jittered_backoff", lambda *a, **k: 0.0)
    # The conversation loop was extracted out of run_agent.py into
    # ``agent.conversation_loop``, which imports ``jittered_backoff``
    # directly (``from agent.retry_utils import jittered_backoff``).
    # Patching ``run_agent.jittered_backoff`` alone misses every retry
    # path under the new module — tests that exercise rate-limit /
    # invalid-response / server-error retries burn real wall-clock
    # seconds per retry. Patch both for full coverage.
    try:
        from agent import conversation_loop as _conv_loop
        monkeypatch.setattr(_conv_loop, "jittered_backoff", lambda *a, **k: 0.0)
    except ImportError:
        pass
