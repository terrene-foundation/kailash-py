"""Tier-1 offline LLM-provider stub for ``tests/unit/strategies/`` (issue #1736).

Several tests in this directory construct a real ``BaseAgent`` + strategy
(e.g. ``MultiCycleStrategy``, ``SingleShotStrategy``) and call
``strategy.execute(agent, inputs)`` with zero LLM mocking. That call reaches
``LocalRuntime().execute(workflow.build(), ...)``, which runs a real
``LLMAgentNode``. ``LLMAgentNode._provider_llm_response()`` resolves the
provider via ``kaizen.providers.registry.get_provider(name)`` and calls
``provider.chat(...)`` -- a genuine outbound network call whenever a real
API key is configured (as this environment's ``.env`` does, per
``rules/env-models.md``), because ``WorkflowGenerator.generate_signature_
workflow()`` defaults ``provider`` to ``"openai"`` whenever
``BaseAgentConfig.llm_provider`` is unset (the common case in these tests).
pytest-timeout's signal-based ``--timeout`` does not reliably abort the
resulting hang inside the C-level socket read (300s+ hangs pre-fix).

Per ``rules/testing.md`` "3-Tier Testing" (Tier 1: mocking allowed, MUST be
offline + deterministic) and the "Tier-1 Conftest Stub for Newly-Side-
Effecting Internal Methods" pattern (canonical for ~10+ shared call sites),
this autouse, directory-scoped fixture stubs the provider seam so every test
under ``tests/unit/strategies/`` resolves fast and offline -- without
weakening any behavioral assertion (cycle counts, dict shape, tool-call
handling, termination logic all still exercise real strategy code against a
real, deterministic completion).

Three independent call paths reach a live provider from this test directory
and are all stubbed:

1. **Four-axis path (#1720 Wave-B1a live cutover)** --
   ``LLMAgentNode._provider_llm_response()`` now resolves a four-axis
   deployment via ``kaizen.llm.deployment_resolver.resolve_deployment_for``
   and calls ``kaizen.llm.client.LlmClient.complete(...)`` (the legacy
   ``get_provider(...).chat(...)`` seam is retained only for
   ``azure_ai_foundry``). Stubbed by patching ``resolve_deployment_for`` to a
   sentinel deployment and ``LlmClient.from_deployment_sync`` to a fake client
   whose ``complete()`` returns a deterministic four-axis response.
2. **Registry path** -- ``kaizen.providers.registry.get_provider(name)`` ->
   ``provider.chat(...)``. Retained for the azure_ai_foundry legacy branch and
   any other code path still resolving through the registry.
3. **Legacy direct-instantiation path** -- ``BaseAgent._simple_execute_async``
   imports ``kaizen.providers.llm.openai.OpenAIProvider`` directly and calls
   ``.chat_async()``, bypassing the registry entirely.

Tests that already mock their own network boundary (e.g.
``test_single_shot_mcp.py`` patches ``kaizen.strategies.single_shot.
LocalRuntime`` per-test) never reach this seam, so this fixture is a no-op
for them -- it changes NOTHING about their behavior.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

# A single JSON payload that is a superset of every shape the strategies
# under test parse (ReAct thought/action/observation, "response"/"answer"
# keys, RAG-style fields). Each parser extracts only the keys it needs via
# `.get(...)`, so one deterministic payload satisfies every call site
# without per-test/per-node customization.
_MOCK_CONTENT = json.dumps(
    {
        "thought": "Mocked reasoning step for deterministic Tier-1 testing (issue #1736).",
        "action": "FINAL ANSWER: mocked result",
        "observation": "Mocked observation.",
        "response": "Mocked final response.",
        "answer": "Mocked answer.",
    }
)


def _fake_chat_response(**_: Any) -> dict:
    """A deterministic, well-formed provider ``chat()`` response."""
    return {
        "id": "test-1736-mock",
        "content": _MOCK_CONTENT,
        "role": "assistant",
        "model": "mock-model",
        "created": 0,
        "tool_calls": [],
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _make_fake_provider(*_args: Any, **_kwargs: Any) -> MagicMock:
    """Build a fresh fake provider satisfying the ``BaseProvider`` surface."""
    provider = MagicMock()
    provider.is_available.return_value = True
    provider.chat.side_effect = _fake_chat_response

    async def _chat_async(**kwargs: Any) -> dict:
        return _fake_chat_response(**kwargs)

    provider.chat_async.side_effect = _chat_async
    return provider


def _fake_four_axis_response(**_: Any) -> dict:
    """A deterministic four-axis ``LlmClient.complete()`` response.

    ``kaizen.llm._legacy_shape.to_legacy_shape`` maps ``text`` -> ``content`` and
    ``input_tokens``/``output_tokens`` -> ``prompt_tokens``/``completion_tokens``,
    so this yields the same normalized shape ``_fake_chat_response`` did on the
    legacy path (issue #1736 offline determinism, preserved across the #1720
    Wave-B1a four-axis cutover).
    """
    return {
        "text": _MOCK_CONTENT,
        "stop_reason": "stop",
        "model": "mock-model",
        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
    }


def _make_fake_four_axis_client(*_args: Any, **_kwargs: Any) -> MagicMock:
    """A fake ``LlmClient`` whose async ``complete()`` returns the canned dict."""
    client = MagicMock()

    async def _complete(*_a: Any, **_kw: Any) -> dict:
        return _fake_four_axis_response()

    client.complete = _complete
    return client


@pytest.fixture(autouse=True)
def _stub_llm_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the four-axis seam, the registry seam, and the legacy direct-
    instantiation seam so every strategy test runs offline + deterministic."""
    # #1720 Wave-B1a — the four-axis live path is what LLMAgentNode now drives.
    # Sentinel deployment + fake client keeps it offline regardless of env keys.
    monkeypatch.setattr(
        "kaizen.llm.deployment_resolver.resolve_deployment_for",
        lambda *a, **kw: object(),
    )
    monkeypatch.setattr(
        "kaizen.llm.client.LlmClient.from_deployment_sync",
        classmethod(_make_fake_four_axis_client),
    )

    monkeypatch.setattr(
        "kaizen.providers.registry.get_provider",
        _make_fake_provider,
    )

    from kaizen.providers.llm.openai import OpenAIProvider

    async def _openai_chat_async(self: Any, **kwargs: Any) -> dict:
        return _fake_chat_response(**kwargs)

    monkeypatch.setattr(OpenAIProvider, "is_available", lambda self: True)
    monkeypatch.setattr(
        OpenAIProvider, "chat", lambda self, **kwargs: _fake_chat_response(**kwargs)
    )
    monkeypatch.setattr(OpenAIProvider, "chat_async", _openai_chat_async)
