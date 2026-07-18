# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""#1779 governance_required posture -- kaizen-agents direct-LLM-egress adapters.

The flagship ``Delegate`` primitive and the whole kaizen-agents adapter layer
construct real provider clients DIRECTLY (AsyncOpenAI / anthropic.AsyncAnthropic
/ genai.Client / per-request httpx.AsyncClient), bypassing the gated four-axis
``kaizen.llm.LlmClient``. Under the ``governance_required`` posture these would
egress ungoverned with no opt-out. This suite pins the construction-time gate on
every adapter + the Delegate/AgentLoop/registry threading of the ``ungoverned``
opt-out.

Invariants (mirror the existing #1779 LLMClient gate):

* Posture OFF (default) => construction succeeds (gate is a no-op).
* Posture ON + real adapter/Delegate + not ungoverned => UngovernedEgressRefused
  at construction, BEFORE any provider client is built.
* ``ungoverned=True`` threaded from the constructor => allowed.

Tier-1 unit: offline. No real egress -- the gate refuses at construction before
the provider client is built; the "allowed" paths build a client object with a
fake key (no network call at construction). Posture is a process global; a module
lock + reset fixture serialize it per rules/testing.md
§ "Serialize Env-Var-Mutating Tests".
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from typing import Any

import pytest

import kailash
from kailash.trust.pact import UngovernedEgressRefused
from kaizen_agents import Delegate
from kaizen_agents.delegate.adapters.anthropic_adapter import AnthropicStreamAdapter
from kaizen_agents.delegate.adapters.google_adapter import GoogleStreamAdapter
from kaizen_agents.delegate.adapters.ollama_adapter import (
    OllamaEmbeddingAdapter,
    OllamaStreamAdapter,
)
from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter
from kaizen_agents.delegate.adapters.registry import (
    get_adapter_for_model,
)
from kaizen_agents.delegate.config.loader import KzConfig
from kaizen_agents.delegate.loop import AgentLoop, ToolRegistry
from kaizen_agents.orchestration.adapters import (
    AnthropicStructuredAdapter,
    OpenAIStructuredAdapter,
)
from kaizen_agents.runtime_adapters.gemini_cli import GeminiCLIAdapter
from kaizen_agents.runtime_adapters.openai_codex import OpenAICodexAdapter

_POSTURE_LOCK = threading.Lock()

# Model names are provider-ROUTING DISCRIMINATORS for these offline gate tests --
# the governance gate refuses at construction BEFORE the model reaches any
# provider, so no real egress ever occurs. Sourced from .env first (single source
# of truth per rules/env-models.md), with the repo's documented final fallbacks
# (mirroring kaizen_agents.llm._resolve_model). The prefixes (claude- / gemini-)
# are what drive provider auto-detection in get_adapter_for_model.
_OPENAI_MODEL = (
    os.environ.get("OPENAI_PROD_MODEL")
    or os.environ.get("DEFAULT_LLM_MODEL")
    or "gpt-4o"
)
_ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-20250514"
_GOOGLE_MODEL = os.environ.get("GOOGLE_MODEL") or "gemini-2.0-flash"


@pytest.fixture(autouse=True)
def _serialized_posture(monkeypatch: pytest.MonkeyPatch):
    """Serialize the process-global posture + provide fake provider keys.

    Provider keys are set so the adapters' key-presence checks pass and the
    governance gate (which runs AFTER the key check, BEFORE the client build) is
    the surface under test. A fake key never makes a network call at
    construction.
    """
    with _POSTURE_LOCK:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("GOOGLE_API_KEY", "goog-test")
        monkeypatch.setenv("GEMINI_API_KEY", "gem-test")
        kailash.set_governance_required(None)
        try:
            yield
        finally:
            kailash.set_governance_required(None)


# Each entry: (id, constructor taking `ungoverned: bool`). Every constructor
# builds a REAL adapter (is_mock=False at the gate).
_ADAPTER_CONSTRUCTORS: list[tuple[str, Callable[..., Any]]] = [
    (
        "OpenAIStreamAdapter",
        lambda ungoverned=False: OpenAIStreamAdapter(
            default_model=_OPENAI_MODEL, ungoverned=ungoverned
        ),
    ),
    (
        "AnthropicStreamAdapter",
        lambda ungoverned=False: AnthropicStreamAdapter(
            default_model=_ANTHROPIC_MODEL, ungoverned=ungoverned
        ),
    ),
    (
        "GoogleStreamAdapter",
        lambda ungoverned=False: GoogleStreamAdapter(
            default_model=_GOOGLE_MODEL, ungoverned=ungoverned
        ),
    ),
    (
        "OllamaStreamAdapter",
        lambda ungoverned=False: OllamaStreamAdapter(
            default_model="llama3.1", ungoverned=ungoverned
        ),
    ),
    (
        "OllamaEmbeddingAdapter",
        lambda ungoverned=False: OllamaEmbeddingAdapter(ungoverned=ungoverned),
    ),
    (
        "OpenAIStructuredAdapter",
        lambda ungoverned=False: OpenAIStructuredAdapter(ungoverned=ungoverned),
    ),
    (
        "AnthropicStructuredAdapter",
        lambda ungoverned=False: AnthropicStructuredAdapter(ungoverned=ungoverned),
    ),
    (
        "OpenAICodexAdapter",
        lambda ungoverned=False: OpenAICodexAdapter(ungoverned=ungoverned),
    ),
    (
        "GeminiCLIAdapter",
        lambda ungoverned=False: GeminiCLIAdapter(ungoverned=ungoverned),
    ),
]

_IDS = [name for name, _ in _ADAPTER_CONSTRUCTORS]
_CTORS = [ctor for _, ctor in _ADAPTER_CONSTRUCTORS]


@pytest.mark.parametrize("construct", _CTORS, ids=_IDS)
def test_posture_off_constructs(construct: Callable[..., Any]) -> None:
    """Posture OFF (default) => byte-identical to today: construction succeeds."""
    kailash.set_governance_required(None)
    assert construct() is not None


@pytest.mark.parametrize("construct", _CTORS, ids=_IDS)
def test_posture_on_real_refused(construct: Callable[..., Any]) -> None:
    """Posture ON + real adapter + not ungoverned => UngovernedEgressRefused."""
    kailash.set_governance_required(True)
    with pytest.raises(UngovernedEgressRefused):
        construct()


@pytest.mark.parametrize("construct", _CTORS, ids=_IDS)
def test_posture_on_ungoverned_optout_allowed(construct: Callable[..., Any]) -> None:
    """Posture ON + ungoverned=True => allowed."""
    kailash.set_governance_required(True)
    assert construct(ungoverned=True) is not None


# ---------------------------------------------------------------------------
# Factory: get_adapter_for_model threads the opt-out
# ---------------------------------------------------------------------------


def test_factory_posture_on_real_refused() -> None:
    kailash.set_governance_required(True)
    with pytest.raises(UngovernedEgressRefused):
        get_adapter_for_model(_OPENAI_MODEL)


def test_factory_posture_on_ungoverned_allowed() -> None:
    kailash.set_governance_required(True)
    assert get_adapter_for_model(_OPENAI_MODEL, ungoverned=True) is not None


def test_factory_posture_off_constructs() -> None:
    kailash.set_governance_required(None)
    assert get_adapter_for_model("gpt-4o") is not None


# ---------------------------------------------------------------------------
# AgentLoop: auto-built adapter is gated; ungoverned threads through
# ---------------------------------------------------------------------------


def test_agentloop_posture_on_real_refused() -> None:
    kailash.set_governance_required(True)
    with pytest.raises(UngovernedEgressRefused):
        AgentLoop(config=KzConfig(model=_OPENAI_MODEL), tools=ToolRegistry())


def test_agentloop_posture_on_ungoverned_allowed() -> None:
    kailash.set_governance_required(True)
    loop = AgentLoop(
        config=KzConfig(model=_OPENAI_MODEL), tools=ToolRegistry(), ungoverned=True
    )
    assert loop is not None


# ---------------------------------------------------------------------------
# Delegate: the flagship primitive. Its inner loop builds a real adapter at
# construction, so the adapter gate fires regardless of the mock _LoopAgent
# bridge (is_mock=False on the real egress path).
# ---------------------------------------------------------------------------


def test_delegate_posture_on_real_refused() -> None:
    kailash.set_governance_required(True)
    with pytest.raises(UngovernedEgressRefused):
        Delegate(model=_OPENAI_MODEL)


def test_delegate_posture_on_ungoverned_allowed() -> None:
    kailash.set_governance_required(True)
    assert Delegate(model=_OPENAI_MODEL, ungoverned=True) is not None


def test_delegate_posture_off_constructs() -> None:
    kailash.set_governance_required(None)
    assert Delegate(model="gpt-4o") is not None
