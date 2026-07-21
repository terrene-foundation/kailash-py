# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 — legacy azure_ai_foundry provider-path deprecation shim (behavioral).

`azure_ai_foundry` is the LAST provider still served by the legacy
`get_provider(...).chat(...)` fallback in
`LLMAgentNode._provider_llm_response` (every other provider is on the four-axis
`kaizen.llm.LlmClient`). Per the deprecate-and-remove disposition on #1720,
STEP 1 is the deprecation shim: when a deployment resolves to that legacy path
the node emits a ONE-TIME `DeprecationWarning` + one-time `logger.warning`
naming the migration, while the path STILL functions (removal is a future
minor). These tests DRIVE the method (never grep source), Tier-1 offline +
deterministic, following the existing B1a cutover regression conventions
(`test_issue_1720_b1a_live_cutover.py::test_azure_ai_foundry_routes_legacy_provider_chat`):

* the DeprecationWarning fires when the azure_ai_foundry legacy path is taken;
* it fires ONCE per process, not per call (module-level `_warned` flag);
* the legacy path STILL WORKS — the deprecation warns but does not break it.
"""

from __future__ import annotations

from typing import Any

import pytest

import kaizen.nodes.ai.llm_agent as llm_agent_mod
from kaizen.nodes.ai.llm_agent import LLMAgentNode

pytestmark = pytest.mark.regression

_MSGS = [{"role": "user", "content": "What is the capital of France?"}]


class _FoundryStub:
    """Legacy provider stub mirroring the B1a cutover test's convention —
    is_available() True + a deterministic chat() return in the legacy shape."""

    def __init__(self) -> None:
        self.chat_calls: list[dict] = []

    def is_available(self) -> bool:
        return True

    def chat(self, **kwargs: Any) -> dict:
        self.chat_calls.append(kwargs)
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


@pytest.fixture
def _reset_deprecation_flag():
    """Reset the module-level one-time-warning flag so each test observes the
    first-fire behavior deterministically regardless of collection order."""
    original = llm_agent_mod._AZURE_AI_FOUNDRY_DEPRECATION_WARNED
    llm_agent_mod._AZURE_AI_FOUNDRY_DEPRECATION_WARNED = False
    try:
        yield
    finally:
        llm_agent_mod._AZURE_AI_FOUNDRY_DEPRECATION_WARNED = original


def _wire_legacy_foundry(monkeypatch, stub: _FoundryStub) -> None:
    """Route get_provider to the stub AND make the four-axis path blow up loudly
    if (wrongly) taken — identical to the B1a cutover test's guard."""
    monkeypatch.setattr(
        "kaizen.providers.registry.get_provider",
        lambda name, **kw: stub,
    )
    monkeypatch.setattr(
        "kaizen.llm.client.LlmClient.from_deployment_sync",
        classmethod(
            lambda cls, *a, **kw: (_ for _ in ()).throw(
                AssertionError("four-axis path taken for azure_ai_foundry")
            )
        ),
    )


def test_deprecation_warning_fires_on_legacy_azure_ai_foundry_path(
    monkeypatch, _reset_deprecation_flag
):
    """Taking the legacy azure_ai_foundry fallback emits a DeprecationWarning
    that names the retirement + the migration."""
    stub = _FoundryStub()
    _wire_legacy_foundry(monkeypatch, stub)

    agent = LLMAgentNode()
    with pytest.warns(DeprecationWarning, match="azure_ai_foundry"):
        response = agent._provider_llm_response(
            provider="azure_ai_foundry",
            model="phi-4",
            messages=_MSGS,
            tools=[],
            generation_config={},
        )

    # Deprecation warns but does NOT break the legacy path — it still works.
    assert response["content"] == "legacy foundry answer"
    assert stub.chat_calls, "legacy get_provider(...).chat(...) was never called"


def test_deprecation_warning_fires_once_not_per_call(
    monkeypatch, _reset_deprecation_flag
):
    """The DeprecationWarning is guarded by a module-level flag: it fires on the
    FIRST legacy call and stays silent on subsequent calls (no hot-loop spam)."""
    stub = _FoundryStub()
    _wire_legacy_foundry(monkeypatch, stub)
    agent = LLMAgentNode()

    def _call() -> None:
        agent._provider_llm_response(
            provider="azure_ai_foundry",
            model="phi-4",
            messages=_MSGS,
            tools=[],
            generation_config={},
        )

    # First call: exactly one azure_ai_foundry DeprecationWarning.
    with pytest.warns(DeprecationWarning) as first:
        _call()
    foundry_first = [w for w in first if "azure_ai_foundry" in str(w.message)]
    assert len(foundry_first) == 1

    # Subsequent calls: the guard flag is set, so NO further warning is emitted.
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        _call()  # would raise if a second azure_ai_foundry warning fired
        _call()

    # The legacy path kept functioning across all three calls.
    assert len(stub.chat_calls) == 3


def test_deprecation_warning_absent_for_four_axis_providers(monkeypatch):
    """A four-axis provider (openai) never touches the legacy fallback, so no
    azure_ai_foundry DeprecationWarning is emitted for it."""

    async def _complete(*_a: Any, **_kw: Any) -> dict:
        return {
            "text": "ok",
            "stop_reason": "stop",
            "model": "gpt-4o-mini",
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }

    from unittest.mock import MagicMock

    client = MagicMock()
    client.complete = _complete
    monkeypatch.setattr(
        "kaizen.llm.deployment_resolver.resolve_deployment_for",
        lambda *a, **kw: object(),
    )
    monkeypatch.setattr(
        "kaizen.llm.client.LlmClient.from_deployment_sync",
        classmethod(lambda cls, *a, **kw: client),
    )

    import warnings

    agent = LLMAgentNode()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        agent._provider_llm_response(
            provider="openai",
            model="gpt-4o-mini",
            messages=_MSGS,
            tools=[],
            generation_config={},
        )

    assert not [
        w
        for w in caught
        if issubclass(w.category, DeprecationWarning)
        and "azure_ai_foundry" in str(w.message)
    ]
