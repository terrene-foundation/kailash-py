# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-B1 inter-wave redteam fixes — behavioral regressions.

Pins the fixes the holistic Wave-B1 redteam surfaced against the merged
cutover, so a future refactor cannot silently reintroduce them:

* **HIGH (F1)** — ``EmbeddingGeneratorNode._generate_provider_embedding`` on an
  UNRESOLVABLE credential provider (e.g. openai with no key -> resolver returns
  ``None``) MUST RAISE (legacy parity + matching the B1a/B1c None-deployment
  disposition), NOT silently return a mock embedding reported as a real provider
  result (zero-tolerance Rule 2 / observability Rule 3). The sanctioned mock path
  is ONLY the explicit ``provider == "mock"`` mode, which this fallback never
  serves. The ollama fallback (real ``ollama.embeddings`` call) is UNCHANGED —
  proven here to confirm the fix is scoped to credential providers.
* **MED** — both the embed error wrapper (``_generate_provider_embedding``) and
  the ``BaseAgent._simple_execute_async`` completion path route provider errors
  through ``sanitize_provider_error`` at enforcement-surface parity with the B1a
  live path (``llm_agent._provider_llm_response``) — a raw wire exception can
  echo a user-supplied ``base_url``.
* **LOW** — the google ``_map_finish_reason`` maps an absent/``None`` reason to
  ``"stop"`` (legacy ``GoogleGeminiProvider`` initialises ``"stop"`` and never
  emits ``None``), completing finish_reason parity.

Tier-1 offline + deterministic (no network, no live keys). Behavioral asserts
per ``rules/testing.md`` § "Behavioral Regression Tests Over Source-Grep".
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

import kaizen.llm as kllm
import kaizen.llm.client as llm_client_mod
import kaizen.llm.deployment_resolver as resolver_mod
import kaizen.nodes.ai.error_sanitizer as sanitizer_mod
from kaizen.core.base_agent import BaseAgent
from kaizen.llm.wire_protocols.google_generate_content import _map_finish_reason
from kaizen.nodes.ai.embedding_generator import EmbeddingGeneratorNode

_OPENAI_MODEL = "fixture-openai-embed"


# ---------------------------------------------------------------------------
# HIGH (F1) — credential provider with an unresolvable deployment RAISES,
# does NOT silently return a mock embedding.
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_embed_missing_credential_raises_not_silent_mock(monkeypatch):
    """openai with resolver -> None RAISES RuntimeError (legacy parity), never
    returns a fabricated mock vector fed into a similarity/RAG pipeline."""
    monkeypatch.setattr(kllm, "resolve_deployment_for", lambda *a, **k: None)

    node = EmbeddingGeneratorNode()
    with pytest.raises(RuntimeError):
        node._generate_provider_embedding("hello", "openai", _OPENAI_MODEL, None, 60, 3)


@pytest.mark.regression
def test_embed_ollama_fallback_preserved_when_unresolved(monkeypatch):
    """The fix is SCOPED: ollama still falls back to the real ``ollama.embeddings``
    call on an unresolved deployment (base_url legitimately unresolvable from node
    inputs) — only credential providers raise."""
    monkeypatch.setattr(kllm, "resolve_deployment_for", lambda *a, **k: None)

    class _FakeOllama:
        @staticmethod
        def embeddings(model: str, prompt: str) -> Dict[str, Any]:
            return {"embedding": [0.11, 0.22, 0.33]}

    monkeypatch.setitem(sys.modules, "ollama", _FakeOllama())

    node = EmbeddingGeneratorNode()
    vector = node._generate_provider_embedding(
        "hello", "ollama", "fixture-ollama", None, 60, 3
    )
    assert vector == [0.11, 0.22, 0.33]


# ---------------------------------------------------------------------------
# MED — provider errors are sanitized at parity on the embed + base_agent paths.
# ---------------------------------------------------------------------------


class _RaisingEmbedClient:
    @classmethod
    def from_deployment_sync(
        cls, deployment: Any, **kwargs: Any
    ) -> "_RaisingEmbedClient":
        return cls()

    async def embed(self, texts, **kwargs):  # noqa: D401
        raise RuntimeError("wire failed at http://user:pass@host:443/v1")


@pytest.mark.regression
def test_embed_error_routes_through_sanitizer(monkeypatch):
    """The embed except wrapper routes provider errors through
    ``sanitize_provider_error`` (not raw ``str(e)``)."""
    sentinel = "SANITIZED-EMBED-MESSAGE"
    monkeypatch.setattr(kllm, "resolve_deployment_for", lambda *a, **k: object())
    monkeypatch.setattr(kllm, "LlmClient", _RaisingEmbedClient)
    monkeypatch.setattr(
        sanitizer_mod, "sanitize_provider_error", lambda e, provider: sentinel
    )

    node = EmbeddingGeneratorNode()
    with pytest.raises(RuntimeError, match=sentinel):
        node._generate_provider_embedding("hi", "openai", _OPENAI_MODEL, None, 60, 3)


@dataclass
class _AgentConfig:
    llm_provider: str = "openai"
    model: Optional[str] = "cfg-model"
    temperature: float = 0.3
    max_tokens: int = 128


class _RaisingCompleteClient:
    @classmethod
    def from_deployment(
        cls, deployment: Any, **kwargs: Any
    ) -> "_RaisingCompleteClient":
        return cls()

    async def complete(self, messages: List[Dict[str, Any]], **kwargs: Any):
        raise RuntimeError("wire failed at http://user:pass@host:443/v1")


@pytest.mark.regression
def test_base_agent_error_routes_through_sanitizer(monkeypatch):
    """``BaseAgent._simple_execute_async`` sanitizes provider errors at parity
    with the B1a live path — a raw wire exception echoing config.base_url must be
    scrubbed before reaching ``_handle_error``'s log/return surface."""
    sentinel = "SANITIZED-COMPLETE-MESSAGE"
    monkeypatch.setattr(
        resolver_mod, "resolve_deployment_for", lambda *a, **k: object()
    )
    monkeypatch.setattr(llm_client_mod, "LlmClient", _RaisingCompleteClient)
    monkeypatch.setattr(
        sanitizer_mod, "sanitize_provider_error", lambda e, provider: sentinel
    )

    agent = BaseAgent(config=_AgentConfig(), signature=None, mcp_servers=[])
    agent.signature = None
    with pytest.raises(RuntimeError, match=sentinel):
        asyncio.run(agent._simple_execute_async({"q": "hi"}))


# ---------------------------------------------------------------------------
# LOW — google finish_reason None -> "stop" (legacy floor) + full value-map.
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, "stop"),
        ("STOP", "stop"),
        ("MAX_TOKENS", "length"),
        ("SAFETY", "content_filter"),
        ("tool", "tool_calls"),
        ("function_call", "tool_calls"),
        ("RECITATION", "stop"),
    ],
)
def test_google_map_finish_reason_full_parity(raw, expected):
    """The google finish_reason value-map matches legacy exactly, including the
    ``None`` -> ``"stop"`` legacy floor (legacy never emits ``None``)."""
    assert _map_finish_reason(raw) == expected
