# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-B1c — BaseAgent._simple_execute_async four-axis cutover.

``BaseAgent._simple_execute_async`` used to construct the legacy
``OpenAIProvider(use_async=True)`` directly and call ``provider.chat_async``.
Wave-B1c cuts it over to the four-axis path:
``resolve_deployment_for("openai", ...)`` -> ``LlmClient.from_deployment(...)``
-> ``await client.complete(messages, model=..., **sampling_kwargs)`` and reads
the assistant text via ``to_legacy_shape(result)["content"]``.

These regression tests PIN the invariants the cutover MUST preserve, offline +
deterministic (no network, no live keys) by injecting a fake ``LlmClient`` and
a sentinel deployment:

* (a) return shape — ``{"response": text}`` with no signature output fields,
  ``{output_fields[0]: text}`` with a signature — sourced from the four-axis
  ``complete()`` result's ``text`` via ``to_legacy_shape`` (real, un-patched);
* (b) multimodal input still produces a structured content list in the user
  ``messages`` entry fed to ``complete`` (the ``_classify_input_value`` loop is
  unchanged);
* (c) model resolution honours ``config.model`` -> ``DEFAULT_LLM_MODEL`` ->
  ``OPENAI_PROD_MODEL``.

Behavioral asserts (call the method, assert the returned/forwarded values) per
rules/testing.md § "Behavioral Regression Tests Over Source-Grep".
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

import kaizen.llm.client as llm_client_mod
import kaizen.llm.deployment_resolver as resolver_mod
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature

# Env vars the model-resolution chain reads; serialize mutation of them through
# one module-scope lock per rules/testing.md § "Serialize Env-Var-Mutating
# Tests Via Module Lock".
_ENV_LOCK = threading.Lock()
_MODEL_ENV_VARS = ("DEFAULT_LLM_MODEL", "OPENAI_PROD_MODEL")

# 1x1 PNG magic-byte prefix — _classify_input_value guesses image/png from this,
# producing an image_url content part (offline; no real image needed).
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


class _AnswerSignature(Signature):
    """A signature with one output field, to pin the field-keyed return shape."""

    question: str = InputField(desc="A question")
    answer: str = OutputField(desc="The answer")


class _FakeLlmClient:
    """A canned four-axis client capturing the ``complete`` call for asserts.

    ``from_deployment`` is the classmethod the method under test uses to build
    the client; it stashes the constructed instance on the class so the test
    can inspect the recorded ``complete`` call afterwards.
    """

    canned_text = "FOUR-AXIS-ASSISTANT-TEXT"
    last_instance: Optional["_FakeLlmClient"] = None

    def __init__(self) -> None:
        self.complete_calls: List[SimpleNamespace] = []

    @classmethod
    def from_deployment(cls, deployment: Any, **kwargs: Any) -> "_FakeLlmClient":
        inst = cls()
        inst.deployment = deployment
        cls.last_instance = inst
        return inst

    async def complete(
        self, messages: List[Dict[str, Any]], *, model: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        self.complete_calls.append(
            SimpleNamespace(messages=messages, model=model, kwargs=kwargs)
        )
        # Four-axis shaper result shape: to_legacy_shape maps ``text`` -> ``content``.
        return {
            "text": type(self).canned_text,
            "usage": {"input_tokens": 1, "output_tokens": 2},
            "stop_reason": "stop",
            "model": model,
        }


@dataclass
class _AgentConfig:
    """Minimal domain config; auto-converted to BaseAgentConfig by BaseAgent."""

    llm_provider: str = "openai"
    model: Optional[str] = "cfg-model"
    temperature: float = 0.3
    max_tokens: int = 128


def _make_agent(config: _AgentConfig, signature: Optional[Signature]) -> BaseAgent:
    # mcp_servers=[] keeps init fully offline (no builtin-MCP auto-discovery).
    return BaseAgent(config=config, signature=signature, mcp_servers=[])


@pytest.fixture
def _fouraxis_seam(monkeypatch):
    """Inject the fake four-axis client + a sentinel deployment resolver.

    Both are patched on their owning modules; ``_simple_execute_async`` imports
    them at call time (``from kaizen.llm.client import LlmClient`` etc.), so the
    module-attribute patch is what the method resolves.
    """
    sentinel_deployment = object()

    def _fake_resolve(provider, model, *, api_key=None, base_url=None):
        # Record nothing here; the model assert reads the forwarded complete()
        # call. Returning a non-None sentinel means "deployment resolved".
        return sentinel_deployment

    monkeypatch.setattr(resolver_mod, "resolve_deployment_for", _fake_resolve)
    monkeypatch.setattr(llm_client_mod, "LlmClient", _FakeLlmClient)
    _FakeLlmClient.last_instance = None
    return SimpleNamespace(deployment=sentinel_deployment)


@pytest.mark.regression
def test_return_shape_response_key_without_signature(_fouraxis_seam):
    """No signature output fields -> ``{"response": <assistant text>}``."""
    agent = _make_agent(_AgentConfig(), signature=None)
    # The DefaultSignature has an ``output`` field, so pass a signature-less
    # agent by clearing the signature to exercise the else-branch explicitly.
    agent.signature = None

    result = asyncio.run(agent._simple_execute_async({"question": "hi"}))

    assert result == {"response": _FakeLlmClient.canned_text}


@pytest.mark.regression
def test_return_shape_field_key_with_signature(_fouraxis_seam):
    """A signature with output fields -> ``{output_fields[0]: <assistant text>}``."""
    agent = _make_agent(_AgentConfig(), signature=_AnswerSignature())

    result = asyncio.run(agent._simple_execute_async({"question": "hi"}))

    assert list(agent.signature.output_fields.keys())[0] == "answer"
    assert result == {"answer": _FakeLlmClient.canned_text}


@pytest.mark.regression
def test_multimodal_input_builds_structured_content_list(_fouraxis_seam):
    """Multimodal input -> the user message ``content`` is a structured list."""
    agent = _make_agent(_AgentConfig(), signature=None)
    agent.signature = None

    asyncio.run(
        agent._simple_execute_async({"caption": "look at this", "image": _PNG_BYTES})
    )

    call = _FakeLlmClient.last_instance.complete_calls[0]
    user_msg = call.messages[-1]
    assert user_msg["role"] == "user"
    content = user_msg["content"]
    assert isinstance(content, list)
    # A text part for the string field + an image_url part for the PNG bytes.
    types = [part.get("type") for part in content]
    assert "text" in types
    assert "image_url" in types


@pytest.mark.regression
def test_model_resolution_honours_config_then_env_order(_fouraxis_seam, monkeypatch):
    """config.model -> DEFAULT_LLM_MODEL -> OPENAI_PROD_MODEL, in that order."""
    with _ENV_LOCK:
        for var in _MODEL_ENV_VARS:
            monkeypatch.delenv(var, raising=False)

        # 1. config.model wins.
        agent = _make_agent(_AgentConfig(model="cfg-model"), signature=None)
        agent.signature = None
        monkeypatch.setenv("DEFAULT_LLM_MODEL", "env-default")
        monkeypatch.setenv("OPENAI_PROD_MODEL", "env-prod")
        asyncio.run(agent._simple_execute_async({"q": "x"}))
        assert _FakeLlmClient.last_instance.complete_calls[0].model == "cfg-model"

        # 2. config.model None -> DEFAULT_LLM_MODEL.
        agent = _make_agent(_AgentConfig(model=None), signature=None)
        agent.signature = None
        monkeypatch.setenv("DEFAULT_LLM_MODEL", "env-default")
        monkeypatch.setenv("OPENAI_PROD_MODEL", "env-prod")
        asyncio.run(agent._simple_execute_async({"q": "x"}))
        assert _FakeLlmClient.last_instance.complete_calls[0].model == "env-default"

        # 3. config.model None + DEFAULT unset -> OPENAI_PROD_MODEL.
        agent = _make_agent(_AgentConfig(model=None), signature=None)
        agent.signature = None
        monkeypatch.delenv("DEFAULT_LLM_MODEL", raising=False)
        monkeypatch.setenv("OPENAI_PROD_MODEL", "env-prod")
        asyncio.run(agent._simple_execute_async({"q": "x"}))
        assert _FakeLlmClient.last_instance.complete_calls[0].model == "env-prod"
