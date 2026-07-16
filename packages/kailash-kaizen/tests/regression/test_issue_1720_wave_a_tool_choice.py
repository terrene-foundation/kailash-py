# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-A invariant #1 — legacy ``tool_choice="required"`` preservation.

Regression for a SHIPPED bug: the Wave-2 dual-run shadow did NOT reproduce
the legacy chat ``tool_choice`` default (``providers/llm/openai.py`` injects
``tool_choice="required"`` when tools are present and the caller gave no
explicit choice), so the four-axis shadow ``complete()`` emitted no
``tool_choice`` (-> provider "auto") and the shadow logged FALSE
``llm.dual_run.divergence`` WARNs on every tool-using agent.

The fix threads ``legacy_tool_choice_default`` into the shadow's four-axis
call path. These are BEHAVIORAL tests — they call the function and assert the
kwargs the four-axis ``complete()`` actually receives (NOT a source grep,
per rules/testing.md § "Behavioral Regression Tests Over Source-Grep").

Sync tests driving the async shadow worker via its own internal
``asyncio.run`` (the worker `_run_llm_dual_run_shadow` is synchronous).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import kaizen.nodes.ai.llm_agent as llm_agent_mod
from kaizen.llm.deployment_resolver import legacy_tool_choice_default
from kaizen.nodes.ai.llm_agent import LLMAgentNode

_TOOLS = [{"type": "function", "function": {"name": "get_weather"}}]


# ---------------------------------------------------------------------------
# Pure-function contract.
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_helper_openai_tools_present_no_explicit_returns_required():
    # Only openai forces "required"; azure/docker default "auto"; others None.
    assert legacy_tool_choice_default("openai", _TOOLS, None) == "required"
    assert legacy_tool_choice_default("azure", _TOOLS, None) == "auto"
    assert legacy_tool_choice_default("docker", _TOOLS, None) == "auto"
    assert legacy_tool_choice_default("cohere", _TOOLS, None) is None


@pytest.mark.regression
def test_helper_explicit_choice_is_honored():
    assert legacy_tool_choice_default("openai", _TOOLS, "auto") == "auto"
    assert legacy_tool_choice_default("azure", _TOOLS, "none") == "none"
    forced = {"type": "function", "function": {"name": "get_weather"}}
    assert legacy_tool_choice_default("openai", _TOOLS, forced) == forced


@pytest.mark.regression
def test_helper_no_tools_returns_none():
    assert legacy_tool_choice_default("openai", None, None) is None
    assert legacy_tool_choice_default("openai", [], None) is None


# ---------------------------------------------------------------------------
# Wired: the four-axis complete() actually receives the right tool_choice.
# ---------------------------------------------------------------------------


def _capture_complete_kwargs(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Patch the shadow's deployment resolution + client so the four-axis
    ``complete()`` is a fake that records the kwargs it is called with."""
    captured: dict = {}

    async def _fake_complete(messages_arg, **kwargs):
        captured.update(kwargs)
        return {
            "text": "ok",
            "stop_reason": "stop",
            "model": "m",
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }

    fake_client = MagicMock()
    fake_client.complete = _fake_complete
    monkeypatch.setattr(llm_agent_mod, "_shadow_deployment_for", lambda **kw: object())
    monkeypatch.setattr(
        "kaizen.llm.client.LlmClient.from_deployment_sync",
        classmethod(lambda cls, *a, **kw: fake_client),
    )
    return captured


def _run_shadow(agent, *, tools, generation_config, provider="openai"):
    agent._run_llm_dual_run_shadow(
        provider=provider,
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        tools=tools,
        generation_config=generation_config,
        api_key="sk-test",
        base_url=None,
        legacy_response={"content": "ok"},
    )


@pytest.mark.regression
def test_shadow_emits_required_when_openai_tools_present_and_no_explicit_choice(
    monkeypatch,
):
    """THE bug fix: openai tools present + no explicit choice -> the four-axis
    complete() receives tool_choice="required" (legacy parity), not None."""
    captured = _capture_complete_kwargs(monkeypatch)
    agent = LLMAgentNode()
    _run_shadow(agent, tools=_TOOLS, generation_config={}, provider="openai")
    assert captured.get("tool_choice") == "required"


@pytest.mark.regression
@pytest.mark.parametrize("provider", ["azure", "docker"])
def test_shadow_emits_auto_for_azure_docker_not_required(monkeypatch, provider):
    """Redteam fix: azure/docker legacy default to tool_choice="auto", NOT
    "required". The provider-agnostic helper over-injected "required" here — the
    shadow must reproduce the azure/docker "auto" default so it does not
    introduce a NEW divergence on azure/docker tool-using agents."""
    captured = _capture_complete_kwargs(monkeypatch)
    agent = LLMAgentNode()
    _run_shadow(agent, tools=_TOOLS, generation_config={}, provider=provider)
    assert captured.get("tool_choice") == "auto"


@pytest.mark.regression
def test_shadow_honors_explicit_tool_choice(monkeypatch):
    captured = _capture_complete_kwargs(monkeypatch)
    agent = LLMAgentNode()
    _run_shadow(agent, tools=_TOOLS, generation_config={"tool_choice": "auto"})
    assert captured.get("tool_choice") == "auto"


@pytest.mark.regression
def test_shadow_emits_no_tool_choice_when_no_tools(monkeypatch):
    captured = _capture_complete_kwargs(monkeypatch)
    agent = LLMAgentNode()
    _run_shadow(agent, tools=[], generation_config={})
    assert "tool_choice" not in captured
