"""Tests for the Nous-Sparkii-3/4 non-agentic warning detector.

Prior to this check, the warning fired on any model whose name contained
``"sparkii"`` anywhere (case-insensitive). That false-positived on unrelated
local Modelfiles such as ``sparkii-brain:qwen3-14b-ctx16k`` — a tool-capable
Qwen3 wrapper that happens to live under the "sparkii" tag namespace.

``is_nous_sparkii_non_agentic`` should only match the actual Nous Research
Sparkii-3 / Sparkii-4 chat family.
"""

from __future__ import annotations

import pytest

from sparkii_cli.model_switch import (
    _SPARKII_MODEL_WARNING,
    _check_sparkii_model_warning,
    is_nous_sparkii_non_agentic,
)


@pytest.mark.parametrize(
    "model_name",
    [
        "NousResearch/Sparkii-3-Llama-3.1-70B",
        "NousResearch/Sparkii-3-Llama-3.1-405B",
        "sparkii-3",
        "Sparkii-3",
        "sparkii-4",
        "sparkii-4-405b",
        "sparkii_4_70b",
        "openrouter/sparkii3:70b",
        "openrouter/nousresearch/sparkii-4-405b",
        "NousResearch/Sparkii3",
        "sparkii-3.1",
    ],
)
def test_matches_real_nous_sparkii_chat_models(model_name: str) -> None:
    assert is_nous_sparkii_non_agentic(model_name), (
        f"expected {model_name!r} to be flagged as Nous Sparkii 3/4"
    )
    assert _check_sparkii_model_warning(model_name) == _SPARKII_MODEL_WARNING


