"""Injected display provider for the core loop (dependency inversion).

The core (conversation_loop / tool_executor / model_tools) renders tool
activity through this provider instead of importing the product-layer
display module (``sparkii_cli.display``).  Surfaces — CLI, gateway, TUI —
register the real implementation via :func:`set_display_provider`; the
default provider degrades to neutral no-ops so core behavior stays safe
without a surface.

The security/failure helpers (``redact_tool_args_for_display`` and
``_detect_tool_failure``) intentionally do NOT route through this provider —
they live in core modules (``agent.redact`` / ``agent.tool_result_classification``)
so redaction and failure classification never depend on a surface registering.
"""

from __future__ import annotations


class _NoopSpinner:
    """Spinner-shaped no-op: start/stop are inert."""

    def start(self) -> None:
        pass

    def stop(self, final_message: str = "") -> None:
        pass


class _DefaultDisplayProvider:
    """No-op provider: no spinners, no previews, neutral text fallbacks."""

    def spinner(self, message: str = "", *, spinner_type: str = "dots", print_fn=None):
        return _NoopSpinner()

    def thinking_faces(self):
        return [""]

    def thinking_verbs(self):
        return [""]

    def waiting_faces(self):
        return [""]

    def build_tool_preview(self, tool_name, args, max_len=None):
        return None

    def build_tool_label(self, tool_name, args, max_len=None):
        return None

    def cute_tool_message(self, tool_name, args, duration, *, result=None):
        safe_name = tool_name[:9] if isinstance(tool_name, str) and tool_name else "tool"
        safe_duration = f"{duration:.1f}s" if isinstance(duration, (int, float)) else "done"
        return f"{safe_name} completed in {safe_duration}"

    def tool_emoji(self, tool_name, default="⚡"):
        return default


_display_provider: object = _DefaultDisplayProvider()


def get_display_provider() -> object:
    """Return the process-wide display provider (defaults to a no-op)."""
    return _display_provider


def set_display_provider(provider) -> None:
    """Register the product-layer display provider (surface side)."""
    global _display_provider
    _display_provider = provider or _DefaultDisplayProvider()
