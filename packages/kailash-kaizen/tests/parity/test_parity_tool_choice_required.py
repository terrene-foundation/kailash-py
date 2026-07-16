# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 tool_choice parity — the PER-PROVIDER legacy default invariant.

The legacy tools-present ``tool_choice`` default is PROVIDER-SPECIFIC — the
providers do NOT agree, so a provider-agnostic default is wrong:

* ``openai`` (``providers/llm/openai.py`` ``default_choice = "required" if tools
  else "auto"``) forces ``"required"`` when tools are present and unset;
* ``azure`` / ``azure_openai`` (``azure.py`` ``"tool_choice", "auto"``) and
  ``docker`` (``docker.py`` ``"tool_choice", "auto"``) default to ``"auto"``;
* every other legacy provider (perplexity/pplx, ollama, google/gemini,
  anthropic, cohere, huggingface) sets NO ``tool_choice`` at all.

Wave-A's ``kaizen.llm.legacy_tool_choice_default(provider, tools, choice)``
reproduces this PER-PROVIDER default (wired into the dual-run shadow, reused by
the Wave-B live path). A provider-agnostic ``"required"`` was the original
Wave-A bug — it over-injected ``"required"`` for azure/docker, whose legacy
path sends ``"auto"``; caught by the Wave-A holistic redteam and fixed here.
"""

from __future__ import annotations

import pytest

from kaizen.llm import legacy_tool_choice_default

_TOOLS = [{"type": "function", "function": {"name": "get_weather"}}]


@pytest.mark.regression
@pytest.mark.parametrize(
    "provider, expected",
    [
        ("openai", "required"),  # only openai forces required
        ("azure", "auto"),
        ("azure_openai", "auto"),
        ("docker", "auto"),
        ("perplexity", None),  # legacy sets no tool_choice
        ("pplx", None),
        ("ollama", None),
        ("google", None),
        ("gemini", None),
        ("anthropic", None),
        ("cohere", None),
        ("huggingface", None),
    ],
)
def test_per_provider_tools_present_unset_default(provider, expected):
    """tools present + no explicit choice -> the PROVIDER's legacy default."""
    assert legacy_tool_choice_default(provider, _TOOLS, None) == expected


@pytest.mark.regression
@pytest.mark.parametrize("provider", ["openai", "azure", "docker", "cohere"])
@pytest.mark.parametrize("explicit", ["auto", "none", "required"])
def test_explicit_choice_is_honored_for_every_provider(provider, explicit):
    """An explicit tool_choice is passed through unchanged for any provider."""
    assert legacy_tool_choice_default(provider, _TOOLS, explicit) == explicit


@pytest.mark.regression
@pytest.mark.parametrize("provider", ["openai", "azure", "docker", "anthropic"])
@pytest.mark.parametrize("tools", [[], None])
def test_no_tools_emits_no_tool_choice(provider, tools):
    """No tools -> None for every provider (legacy skips the tool_choice block)."""
    assert legacy_tool_choice_default(provider, tools, None) is None


@pytest.mark.regression
def test_unknown_provider_emits_no_tool_choice():
    """A provider absent from the legacy default map emits None (no over-inject)."""
    assert legacy_tool_choice_default("some-future-provider", _TOOLS, None) is None
