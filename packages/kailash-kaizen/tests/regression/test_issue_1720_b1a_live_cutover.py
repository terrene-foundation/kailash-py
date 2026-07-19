# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-B1a — LLMAgentNode live-cutover regression (behavioral).

Wave-B1a promoted ``LLMAgentNode._provider_llm_response`` from the legacy
``get_provider(...).chat(...)`` path to the four-axis ``kaizen.llm.client.
LlmClient`` path (mapped onto the legacy response shape via
``kaizen.llm._legacy_shape.to_legacy_shape``). These tests DRIVE the method
(never grep source), Tier-1 offline + deterministic, using the SAME shared
canned-bytes injection the parity harness uses (``tests/parity/_harness.py``):

* (a) an openai-family provider returns the FOUR-AXIS-mapped shape parsed from
  shared canned bytes through the real ``openai_chat`` wire → ``to_legacy_shape``;
* (b) ``azure_ai_foundry`` (no confirmed four-axis wire) STILL routes to the
  legacy ``get_provider(...).chat(...)`` path;
* (c) the #487 usage total-coercion still fires on the four-axis path (a falsy
  ``total_tokens`` is recomputed from the parts);
* (d) the stream-aware per-provider ``tool_choice`` default still yields
  ``"required"`` for openai + tools present + no explicit choice.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from kaizen.llm import LlmClient, resolve_deployment_for
from kaizen.nodes.ai.llm_agent import LLMAgentNode
from tests.parity._harness import CapturingTransport, load_fixture

pytestmark = pytest.mark.regression

_MSGS = [{"role": "user", "content": "What is the capital of France?"}]
_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]


def _fake_four_axis_client(complete_impl) -> MagicMock:
    """A fake ``LlmClient`` whose ``complete`` is the supplied async callable."""
    client = MagicMock()
    client.complete = complete_impl
    return client


# ---------------------------------------------------------------------------
# (a) openai-family provider -> four-axis-mapped shape from shared canned bytes.
# ---------------------------------------------------------------------------


def test_provider_llm_response_returns_four_axis_mapped_shape_for_openai(monkeypatch):
    """`_provider_llm_response(provider="openai")` returns the four-axis result
    mapped onto the legacy shape, parsed from shared canned openai bytes through
    the REAL openai_chat wire routed via CapturingTransport (offline)."""
    canned = load_fixture("openai_response")

    # Build a REAL four-axis client for the openai deployment, then route its
    # send path through the offline CapturingTransport (the harness's injection
    # style). A placeholder api_key satisfies the resolver (no secret; never
    # sent — the transport is stubbed). rules/security.md § No Hardcoded Secrets.
    deployment = resolve_deployment_for(
        "openai", "gpt-4o-mini", api_key="sk-b1a-parity-placeholder"
    )
    assert deployment is not None
    real_client = LlmClient.from_deployment(deployment)
    transport = CapturingTransport(canned)
    orig_complete = real_client.complete

    async def _complete_via_transport(messages: List[Dict[str, Any]], **kw: Any):
        kw.pop("http_client", None)
        return await orig_complete(messages, http_client=transport, **kw)

    monkeypatch.setattr(real_client, "complete", _complete_via_transport)
    monkeypatch.setattr(
        "kaizen.llm.client.LlmClient.from_deployment_sync",
        classmethod(lambda cls, *a, **kw: real_client),
    )

    agent = LLMAgentNode()
    response = agent._provider_llm_response(
        provider="openai",
        model="gpt-4o-mini",
        messages=_MSGS,
        tools=[],
        generation_config={},
        # Same placeholder as the up-front `resolve_deployment_for` call above:
        # `_provider_llm_response` re-resolves the deployment internally (its
        # own `resolve_deployment_for(provider, model, api_key=api_key, ...)`
        # call), so without an explicit override it falls back to the
        # provider's env var (`OPENAI_API_KEY`) — which #1845's cost-guard
        # withholds by default in a bare pytest run. The placeholder keeps this
        # offline/canned-bytes test hermetic regardless of ambient env state
        # (no secret; never sent — the transport is stubbed).
        api_key="sk-b1a-parity-placeholder",
    )

    # The canned openai bytes parsed through the four-axis wire + to_legacy_shape.
    assert response["content"] == "The capital of France is Paris."
    assert response["finish_reason"] == "stop"
    assert response["usage"] == {
        "prompt_tokens": 12,
        "completion_tokens": 7,
        "total_tokens": 19,
    }
    # The offline transport actually served the request (no network occurred).
    assert len(transport.calls) == 1


# ---------------------------------------------------------------------------
# (b) azure_ai_foundry STILL routes to the legacy get_provider chat path.
# ---------------------------------------------------------------------------


def test_azure_ai_foundry_routes_legacy_provider_chat(monkeypatch):
    """`azure_ai_foundry` has no confirmed four-axis wire (resolve raises
    UnsupportedDeploymentProvider), so `_provider_llm_response` falls back to
    the legacy `get_provider(...).chat(...)` path for that provider ONLY."""
    legacy_calls: dict = {}

    class _FoundryStub:
        def is_available(self) -> bool:
            return True

        def chat(self, **kwargs: Any) -> dict:
            legacy_calls["chat"] = kwargs
            return {
                "content": "legacy foundry answer",
                "role": "assistant",
                "model": kwargs["model"],
                "tool_calls": [],
                "finish_reason": "stop",
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                },
            }

    monkeypatch.setattr(
        "kaizen.providers.registry.get_provider",
        lambda name, **kw: _FoundryStub(),
    )
    # If the four-axis path were (wrongly) taken, this would blow up loudly.
    monkeypatch.setattr(
        "kaizen.llm.client.LlmClient.from_deployment_sync",
        classmethod(
            lambda cls, *a, **kw: (_ for _ in ()).throw(
                AssertionError("four-axis path taken for azure_ai_foundry")
            )
        ),
    )

    agent = LLMAgentNode()
    response = agent._provider_llm_response(
        provider="azure_ai_foundry",
        model="phi-4",
        messages=_MSGS,
        tools=[],
        generation_config={},
    )

    assert legacy_calls, "legacy get_provider(...).chat(...) was never called"
    assert response["content"] == "legacy foundry answer"


# ---------------------------------------------------------------------------
# (c) #487 usage total-coercion still fires on the four-axis path.
# ---------------------------------------------------------------------------


def test_usage_total_coercion_fires_on_four_axis_path(monkeypatch):
    """A four-axis response with a FALSY `total_tokens` gets it recomputed from
    the parts by the #487 coercion, AFTER `to_legacy_shape` (invariant #2)."""

    async def _complete(*_a: Any, **_kw: Any) -> dict:
        return {
            "text": "coerced",
            "stop_reason": "stop",
            "model": "gpt-4o-mini",
            # total_tokens is 0 (falsy, not None) -> to_legacy_shape keeps 0 ->
            # _provider_llm_response's #487 coercion sets it to 8 + 4 = 12.
            "usage": {"input_tokens": 8, "output_tokens": 4, "total_tokens": 0},
        }

    monkeypatch.setattr(
        "kaizen.llm.deployment_resolver.resolve_deployment_for",
        lambda *a, **kw: object(),
    )
    monkeypatch.setattr(
        "kaizen.llm.client.LlmClient.from_deployment_sync",
        classmethod(lambda cls, *a, **kw: _fake_four_axis_client(_complete)),
    )

    agent = LLMAgentNode()
    response = agent._provider_llm_response(
        provider="openai",
        model="gpt-4o-mini",
        messages=_MSGS,
        tools=[],
        generation_config={},
    )

    assert response["usage"]["prompt_tokens"] == 8
    assert response["usage"]["completion_tokens"] == 4
    assert response["usage"]["total_tokens"] == 12  # recomputed, not the 0


# ---------------------------------------------------------------------------
# (d) stream-aware tool_choice default -> "required" for openai + tools + unset.
# ---------------------------------------------------------------------------


def test_tool_choice_default_required_for_openai_tools_present_unset(monkeypatch):
    """Legacy `.chat()` injects tool_choice="required" for openai when tools are
    present and no explicit choice is given; the cutover reproduces it via the
    shared `_legacy_tool_choice_default` helper (invariant #3)."""
    captured: dict = {}

    async def _complete(messages: List[Dict[str, Any]], **kw: Any) -> dict:
        captured.update(kw)
        return {
            "text": "ok",
            "stop_reason": "stop",
            "model": "gpt-4o-mini",
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }

    monkeypatch.setattr(
        "kaizen.llm.deployment_resolver.resolve_deployment_for",
        lambda *a, **kw: object(),
    )
    monkeypatch.setattr(
        "kaizen.llm.client.LlmClient.from_deployment_sync",
        classmethod(lambda cls, *a, **kw: _fake_four_axis_client(_complete)),
    )

    agent = LLMAgentNode()
    agent._provider_llm_response(
        provider="openai",
        model="gpt-4o-mini",
        messages=_MSGS,
        tools=_TOOLS,
        generation_config={},  # no explicit tool_choice
    )

    assert captured.get("tool_choice") == "required"


def test_tool_choice_default_none_when_no_tools(monkeypatch):
    """No tools present -> no tool_choice is injected (legacy skips the block)."""
    captured: dict = {"sentinel": True}

    async def _complete(messages: List[Dict[str, Any]], **kw: Any) -> dict:
        captured["kw"] = kw
        return {
            "text": "ok",
            "stop_reason": "stop",
            "model": "gpt-4o-mini",
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }

    monkeypatch.setattr(
        "kaizen.llm.deployment_resolver.resolve_deployment_for",
        lambda *a, **kw: object(),
    )
    monkeypatch.setattr(
        "kaizen.llm.client.LlmClient.from_deployment_sync",
        classmethod(lambda cls, *a, **kw: _fake_four_axis_client(_complete)),
    )

    agent = LLMAgentNode()
    agent._provider_llm_response(
        provider="openai",
        model="gpt-4o-mini",
        messages=_MSGS,
        tools=[],
        generation_config={},
    )

    assert "tool_choice" not in captured["kw"]
