"""Regression coverage for #58720 / #55924 — cron scheduling races
interpreter finalization.

When the gateway tears down (SIGTERM from ``sparkii update`` /
``sparkii gateway stop`` / systemd restart, or an OOM-kill), a cron tick can
still fire. Once the Python interpreter is finalizing, ``concurrent.futures``
refuses new work with ``RuntimeError: cannot schedule new futures after
interpreter shutdown`` and asyncio's default executor is gone. The cron
delivery + dispatch paths used to hit that unguarded, crashing the tick and
spraying a traceback into ``errors.log`` on every restart-race.

The fix adds ``_interpreter_shutting_down()`` and guards the scheduling
sites so they skip gracefully with a warning instead of raising.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestInterpreterShuttingDownHelper:
    def test_true_when_finalizing(self):
        from cron.scheduler import _interpreter_shutting_down

        with patch("sys.is_finalizing", return_value=True):
            assert _interpreter_shutting_down() is True

    def test_false_when_not_finalizing_and_no_exc(self):
        from cron.scheduler import _interpreter_shutting_down

        with patch("sys.is_finalizing", return_value=False):
            assert _interpreter_shutting_down() is False

    def test_matches_shutdown_error_text_as_fallback(self):
        """The concurrent.futures module-global flag can be set a hair before
        ``sys.is_finalizing()`` flips — matching the error text catches that
        race so a shutdown RuntimeError isn't misread as a real failure."""
        from cron.scheduler import _interpreter_shutting_down

        exc = RuntimeError("cannot schedule new futures after interpreter shutdown")
        with patch("sys.is_finalizing", return_value=False):
            assert _interpreter_shutting_down(exc) is True

    def test_unrelated_error_is_not_shutdown(self):
        from cron.scheduler import _interpreter_shutting_down

        exc = RuntimeError("some other problem")
        with patch("sys.is_finalizing", return_value=False):
            assert _interpreter_shutting_down(exc) is False


class TestStandaloneDeliverySkipsDuringShutdown:
    def _telegram_cfg(self):
        from gateway.config import Platform

        pconfig = MagicMock()
        pconfig.enabled = True
        mock_cfg = MagicMock()
        mock_cfg.platforms = {Platform.TELEGRAM: pconfig}
        return mock_cfg




class TestSourceGuardrail:
    @pytest.fixture
    def source(self) -> str:
        from pathlib import Path

        return (
            Path(__file__).resolve().parents[2] / "cron" / "scheduler.py"
        ).read_text(encoding="utf-8")

    def test_helper_defined(self, source):
        assert "def _interpreter_shutting_down(" in source
        assert "#58720" in source


