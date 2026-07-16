# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 tool_choice="required" parity — the load-bearing behavioral invariant.

The legacy OpenAI-family providers (``providers/llm/openai.py::OpenAIProvider.chat``
line ``default_choice = "required" if tools else "auto"``; same in azure.py /
docker.py) FORCE ``tool_choice="required"`` when tools are present and the caller
gave no explicit choice. The four-axis ``LlmClient.complete`` defaults
``tool_choice=None`` (emits nothing -> provider defaults to "auto").

Wave-A added ``kaizen.llm.legacy_tool_choice_default`` and wired it into the
dual-run shadow so the four-axis path reproduces the legacy forced-tool-calling
default; the Wave-B live migration reuses the same helper. Without it, every
tool-using agent silently flips forced -> optional tool-calling on cutover (and
the Wave-2 shadow logged FALSE divergences). These tests pin that contract.
"""

from __future__ import annotations

import pytest

from kaizen.llm import legacy_tool_choice_default

_TOOLS = [{"type": "function", "function": {"name": "get_weather"}}]


@pytest.mark.regression
def test_tools_present_unset_defaults_to_required():
    """tools present + no explicit choice -> "required" (matches legacy default)."""
    assert legacy_tool_choice_default(_TOOLS, None) == "required"


@pytest.mark.regression
@pytest.mark.parametrize("explicit", ["auto", "none", "required"])
def test_explicit_choice_is_honored(explicit):
    """An explicit tool_choice is passed through unchanged (never overridden)."""
    assert legacy_tool_choice_default(_TOOLS, explicit) == explicit


@pytest.mark.regression
@pytest.mark.parametrize("tools", [[], None])
def test_no_tools_emits_no_tool_choice(tools):
    """No tools -> None (four-axis emits no tool_choice; legacy sets none either)."""
    assert legacy_tool_choice_default(tools, None) is None


@pytest.mark.regression
def test_helper_matches_legacy_openai_default_choice_logic():
    """Cross-check against the legacy `default_choice = "required" if tools else "auto"`.

    Legacy sets tool_choice only inside its `if tools:` block, so the meaningful
    forced-default is the tools-present case; the helper reproduces it exactly.
    """
    # tools present, unset -> legacy default_choice "required"
    assert legacy_tool_choice_default(_TOOLS, None) == "required"
    # explicit wins over the default on the legacy side too (generation_config.get)
    assert legacy_tool_choice_default(_TOOLS, "auto") == "auto"
