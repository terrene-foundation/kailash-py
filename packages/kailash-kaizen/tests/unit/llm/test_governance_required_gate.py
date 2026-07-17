# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""#1779 governance_required posture — Kaizen-side enforcement gate.

Covers design-doc acceptance:
  (b) posture ON + bare real client   → UngovernedEgressRefused (both remedies)
  (c) posture ON + ungoverned=True    → allowed
  (d) posture ON + mock/deterministic → allowed (exempt)
  (e) posture ON + installed pair     → allowed (not re-gated)
  (f) posture OFF                      → byte-identical to today (all construct)
plus Agent-surface variants, the lazy defense-in-depth re-check (posture flipped
ON after construction), and the __del__-safety regression (a gate-refused
partial construction must not AttributeError in the GC finalizer).

Tier-1 unit: offline. Real egress is never attempted — the gate refuses BEFORE
transport binding, and exempt paths use MockLlmHttpClient (a Protocol-satisfying
deterministic adapter, NOT a mock per rules/testing.md § Protocol Adapters).
The posture override is a process global; a module lock + reset fixture
serialize it per rules/testing.md § "Serialize Env-Var-Mutating Tests".
"""

from __future__ import annotations

import gc
import os
import threading

import pytest

import kailash
from kailash.trust.pact import UngovernedEgressRefused
from kaizen.agent import Agent
from kaizen.llm import LlmClient
from kaizen.llm.deployment import LlmDeployment
from kaizen.llm.testing import MockLlmHttpClient, mock_preset

_POSTURE_LOCK = threading.Lock()

# Model name is IRRELEVANT to the gate (it keys on preset_name, never the
# model) — sourced from .env per rules/env-models.md; no real call is ever made.
_MODEL = os.environ.get("OPENAI_PROD_MODEL") or os.environ.get(
    "DEFAULT_LLM_MODEL", "gpt-test"
)


@pytest.fixture(autouse=True)
def _serialized_posture():
    with _POSTURE_LOCK:
        kailash.set_governance_required(None)
        try:
            yield
        finally:
            kailash.set_governance_required(None)


def _real() -> LlmDeployment:
    return LlmDeployment.openai("sk-test", model=_MODEL)


# --------------------------------------------------------------------------- #
# (f) posture OFF — byte-identical to today
# --------------------------------------------------------------------------- #


def test_off_real_and_mock_both_construct() -> None:
    kailash.set_governance_required(None)
    assert LlmClient.from_deployment(_real()) is not None
    assert LlmClient.from_deployment(mock_preset()) is not None
    # deployment-less client is never gated (cannot egress)
    assert LlmClient() is not None


# --------------------------------------------------------------------------- #
# (b) posture ON + bare real client → refused, both remedies named
# --------------------------------------------------------------------------- #


def test_on_real_client_refused_at_construction() -> None:
    kailash.set_governance_required(True)
    with pytest.raises(UngovernedEgressRefused) as ei:
        LlmClient.from_deployment(_real())
    msg = str(ei.value)
    # Both remedies named; must NOT falsely promise install_interceptor (CRITICAL fix).
    assert "ungoverned=True" in msg and "GovernedProvider" in msg
    assert "install_interceptor(" not in msg


def test_on_direct_init_with_real_deployment_refused() -> None:
    kailash.set_governance_required(True)
    with pytest.raises(UngovernedEgressRefused):
        LlmClient(deployment=_real())


def test_on_from_env_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    kailash.set_governance_required(True)
    # Use the non-deprecated selector tier (KAILASH_LLM_PROVIDER) so the test
    # does not trip the legacy-auto-detect DeprecationWarning.
    monkeypatch.setenv("KAILASH_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_PROD_MODEL", _MODEL)
    with pytest.raises(UngovernedEgressRefused):
        LlmClient.from_env()


def test_on_deploymentless_client_not_gated() -> None:
    # A client with no deployment cannot egress, so construction is allowed
    # even under the ON posture (the lazy check never fires without egress).
    kailash.set_governance_required(True)
    assert LlmClient() is not None


# --------------------------------------------------------------------------- #
# (c) posture ON + ungoverned=True → allowed (every constructor)
# --------------------------------------------------------------------------- #


def test_on_ungoverned_optout_allowed_all_constructors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kailash.set_governance_required(True)
    assert LlmClient(deployment=_real(), ungoverned=True) is not None
    assert LlmClient.from_deployment(_real(), ungoverned=True) is not None
    assert LlmClient.from_deployment_sync(_real(), ungoverned=True) is not None
    monkeypatch.setenv("KAILASH_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_PROD_MODEL", _MODEL)
    assert LlmClient.from_env(ungoverned=True) is not None


def test_with_deployment_inherits_ungoverned() -> None:
    kailash.set_governance_required(True)
    base = LlmClient.from_deployment(_real(), ungoverned=True)
    # re-deploying to another real deployment must not re-gate
    assert base.with_deployment(_real()) is not None


# --------------------------------------------------------------------------- #
# (d) posture ON + mock/deterministic → allowed (exempt)
# --------------------------------------------------------------------------- #


def test_on_mock_preset_exempt() -> None:
    kailash.set_governance_required(True)
    assert LlmClient.from_deployment(mock_preset()) is not None


# --------------------------------------------------------------------------- #
# (e) posture ON + installed interceptor does NOT exempt (redteam CRITICAL fix)
# --------------------------------------------------------------------------- #


def test_on_installed_interceptor_does_NOT_exempt() -> None:
    """Redteam CRITICAL (PACT-1779-01): a merely-installed process-global
    interceptor does NOT govern the four-axis LlmClient (its egress calls
    http_client.post directly, never routing through the interceptor). So
    interceptor-presence MUST NOT waive the refusal — that was fail-open.
    The only opt-out is ungoverned=True."""
    from kailash.trust.pact import (
        EffectGovernor,
        OutboundEffect,
        OutboundEffectInterceptor,
        OutboundVerdict,
        clear_interceptor,
        install_interceptor,
    )

    class _AllowGovernor(EffectGovernor):
        def evaluate(self, effect: OutboundEffect) -> OutboundVerdict:
            return OutboundVerdict(
                allowed=True, level="auto_approved", reason="test", effect=effect
            )

    kailash.set_governance_required(True)
    install_interceptor(OutboundEffectInterceptor(_AllowGovernor()))
    try:
        # Fail-closed: a bare real client is STILL refused despite the
        # installed interceptor (it does not govern the four-axis client).
        with pytest.raises(UngovernedEgressRefused):
            LlmClient.from_deployment(_real())
        # The working opt-out remains available.
        assert LlmClient.from_deployment(_real(), ungoverned=True) is not None
    finally:
        clear_interceptor()


def test_error_message_does_not_promise_install_interceptor() -> None:
    """The message must not tell users install_interceptor fixes a four-axis
    refusal (it does not — redteam CRITICAL). ungoverned=True is the opt-out."""
    err = UngovernedEgressRefused("LlmClient")
    msg = str(err)
    assert "ungoverned=True" in msg
    assert "does NOT govern" in msg  # explicit non-coverage disclosure
    assert "install_interceptor(" not in msg


# --------------------------------------------------------------------------- #
# Lazy defense-in-depth: posture flipped ON AFTER construction
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_lazy_refuses_when_posture_flipped_after_construction() -> None:
    kailash.set_governance_required(None)
    client = LlmClient.from_deployment(_real())  # constructed under OFF
    kailash.set_governance_required(True)
    # http_client=None → about to build a REAL transport → refuse BEFORE network
    with pytest.raises(UngovernedEgressRefused):
        await client.complete([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_lazy_exempt_with_injected_mock_transport() -> None:
    kailash.set_governance_required(True)
    client = LlmClient.from_deployment(mock_preset())
    result = await client.complete(
        [{"role": "user", "content": "hi"}], http_client=MockLlmHttpClient()
    )
    assert result is not None


def test_lazy_exempt_when_ungoverned_real_transport_path() -> None:
    """Redteam round-2 spec-F3: exercise the ungoverned lazy exemption on the
    REAL-transport path (http_client=None), NOT via the mock-transport marker
    short-circuit — so the test actually proves the lazy check honors
    self._ungoverned. Calls the lazy gate directly to avoid real network."""
    kailash.set_governance_required(None)
    client = LlmClient.from_deployment(_real(), ungoverned=True)
    kailash.set_governance_required(True)
    # http_client=None => real-transport branch; must NOT raise because the
    # client is ungoverned. (Bare real client here WOULD raise — see
    # test_lazy_refuses_when_posture_flipped_after_construction.)
    client._enforce_lazy_governance(None)  # no exception == pass


def test_lazy_refuses_real_transport_when_not_ungoverned() -> None:
    """Companion to the above: the same real-transport lazy check DOES refuse a
    non-ungoverned real client (proves the exemption above is load-bearing)."""
    kailash.set_governance_required(None)
    client = LlmClient.from_deployment(_real())
    kailash.set_governance_required(True)
    with pytest.raises(UngovernedEgressRefused):
        client._enforce_lazy_governance(None)


def test_mock_transport_carries_marker() -> None:
    assert MockLlmHttpClient.is_mock_transport is True
    assert getattr(MockLlmHttpClient(), "is_mock_transport", False) is True


# --------------------------------------------------------------------------- #
# Regression: __del__ safety after a gate-refused partial construction
# --------------------------------------------------------------------------- #


def test_del_safe_after_refused_construction() -> None:
    kailash.set_governance_required(True)
    for _ in range(5):
        with pytest.raises(UngovernedEgressRefused):
            LlmClient.from_deployment(_real())
    # Force finalizers to run; a partial construction must not AttributeError.
    gc.collect()


# --------------------------------------------------------------------------- #
# Agent surface
# --------------------------------------------------------------------------- #


def test_agent_on_real_provider_refused() -> None:
    kailash.set_governance_required(True)
    with pytest.raises(UngovernedEgressRefused) as ei:
        Agent(model=_MODEL, show_startup_banner=False)
    assert "Agent" in str(ei.value)


def test_agent_on_mock_provider_exempt() -> None:
    kailash.set_governance_required(True)
    agent = Agent(model="mock-model", llm_provider="mock", show_startup_banner=False)
    assert agent is not None


def test_agent_on_ungoverned_optout_allowed() -> None:
    kailash.set_governance_required(True)
    agent = Agent(model=_MODEL, ungoverned=True, show_startup_banner=False)
    assert agent is not None


def test_agent_ungoverned_is_threaded_not_dead_state() -> None:
    """Redteam HIGH (F1/PACT-1779-02/spec-F1): Agent._ungoverned MUST reach the
    egressing BaseAgent config (it was dead state — written, never read). This
    is the compositional proof the opt-out works end-to-end: config.ungoverned
    is True, and LlmClient.from_deployment(..., ungoverned=True) is proven
    not-refused by test_on_ungoverned_optout_allowed_all_constructors."""
    kailash.set_governance_required(None)
    a = Agent(model=_MODEL, ungoverned=True, show_startup_banner=False)
    assert a.base_agent is not None
    assert a.base_agent.config.ungoverned is True
    b = Agent(model=_MODEL, show_startup_banner=False)
    assert b.base_agent.config.ungoverned is False


# --------------------------------------------------------------------------- #
# Fix C — legacy _legacy_provider_chat fallback (no-four-axis-wire providers)
# is gated (the only legacy egress not routed through the four-axis LlmClient)
# --------------------------------------------------------------------------- #


def _make_llm_agent_node(**kw):
    from kaizen.nodes.ai.llm_agent import LLMAgentNode

    return LLMAgentNode(**kw)


def test_llm_agent_node_ungoverned_param_stored() -> None:
    assert _make_llm_agent_node(ungoverned=True)._ungoverned is True
    assert _make_llm_agent_node()._ungoverned is False


def test_legacy_provider_chat_refused_under_posture_on() -> None:
    """azure_ai_foundry (no four-axis wire) egresses via _legacy_provider_chat,
    which does NOT construct an LlmClient — so it needs its own explicit gate."""
    kailash.set_governance_required(True)
    node = _make_llm_agent_node()
    with pytest.raises(UngovernedEgressRefused):
        node._legacy_provider_chat(
            "azure_ai_foundry", _MODEL, [{"role": "user", "content": "hi"}], [], {}
        )


def test_legacy_provider_chat_ungoverned_bypasses_gate() -> None:
    kailash.set_governance_required(True)
    node = _make_llm_agent_node(ungoverned=True)
    # The gate must NOT raise UngovernedEgressRefused; any downstream error
    # (provider unavailable) is fine — we only assert the gate is bypassed.
    try:
        node._legacy_provider_chat(
            "azure_ai_foundry", _MODEL, [{"role": "user", "content": "hi"}], [], {}
        )
    except UngovernedEgressRefused:
        raise AssertionError("ungoverned=True must bypass the legacy gate")
    except Exception:
        pass  # provider-unavailable / import error is acceptable here


def test_legacy_provider_chat_mock_exempt() -> None:
    kailash.set_governance_required(True)
    node = _make_llm_agent_node()
    try:
        node._legacy_provider_chat(
            "mock", _MODEL, [{"role": "user", "content": "hi"}], [], {}
        )
    except UngovernedEgressRefused:
        raise AssertionError("mock provider must be exempt at the legacy gate")
    except Exception:
        pass


def test_agent_off_real_provider_constructs() -> None:
    kailash.set_governance_required(None)
    agent = Agent(model=_MODEL, show_startup_banner=False)
    assert agent is not None


# --------------------------------------------------------------------------- #
# Round-2 T1 — the node egress must propagate UngovernedEgressRefused UNWRAPPED
# (not re-typed to RuntimeError by the broad except; invariant 4)
# --------------------------------------------------------------------------- #


def test_provider_llm_response_propagates_typed_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_PROD_MODEL", _MODEL)
    kailash.set_governance_required(True)
    node = _make_llm_agent_node()
    # The four-axis construction inside _provider_llm_response raises the typed
    # refusal; the broad `except Exception` must re-raise it, NOT wrap as RuntimeError.
    with pytest.raises(UngovernedEgressRefused):
        node._provider_llm_response(
            "openai", _MODEL, [{"role": "user", "content": "hi"}], [], {}
        )


# --------------------------------------------------------------------------- #
# Round-2 T2 — EmbeddingGeneratorNode (sibling four-axis egress) honors the
# posture + carries an ungoverned opt-out (parity with LLMAgentNode)
# --------------------------------------------------------------------------- #


def _make_embedding_node():
    from kaizen.nodes.ai.embedding_generator import EmbeddingGeneratorNode

    return EmbeddingGeneratorNode()


def test_embedding_node_declares_ungoverned_param() -> None:
    assert "ungoverned" in _make_embedding_node().get_parameters()


def test_embedding_node_real_provider_refused_and_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    kailash.set_governance_required(True)
    node = _make_embedding_node()  # _ungoverned unset => getattr default False
    with pytest.raises(UngovernedEgressRefused):
        node._generate_provider_embedding(
            "hello", "openai", "text-embedding-3-small", None, 60, 3
        )


def test_embedding_node_ungoverned_bypasses_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    kailash.set_governance_required(True)
    node = _make_embedding_node()
    node._ungoverned = True  # run() sets this from the node param
    try:
        node._generate_provider_embedding(
            "hello", "openai", "text-embedding-3-small", None, 60, 3
        )
    except UngovernedEgressRefused:
        raise AssertionError("ungoverned=True must bypass the embed gate")
    except Exception:
        pass  # downstream provider/network error is acceptable here


# --------------------------------------------------------------------------- #
# Round-3 — BaseAgent four-axis path (third T1 sibling): a lazy-re-check
# refusal from complete() must propagate UNWRAPPED, not re-typed to RuntimeError
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_base_agent_simple_execute_propagates_typed_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_PROD_MODEL", _MODEL)
    # Posture OFF at construction (line 400 passes); simulate the lazy re-check
    # refusal by making complete() raise the typed error, then assert the
    # except block re-raises it unwrapped (not RuntimeError).
    kailash.set_governance_required(None)
    from kaizen.core.base_agent import BaseAgent
    from kaizen.llm.client import LlmClient

    async def _raise_refusal(self, *a, **k):
        raise UngovernedEgressRefused("LlmClient")

    monkeypatch.setattr(LlmClient, "complete", _raise_refusal)
    base = BaseAgent(config={"model": _MODEL})
    with pytest.raises(UngovernedEgressRefused):
        await base._simple_execute_async({"query": "hi"})


# --------------------------------------------------------------------------- #
# Round-4 — EmbeddingGeneratorNode ollama legacy fallback (the last non-four-axis
# egress chokepoint) must be gated (enforcement-surface parity with _legacy_provider_chat)
# --------------------------------------------------------------------------- #


def test_embedding_fallback_ollama_refused_under_posture_on() -> None:
    """The ollama fallback (_fallback_provider_embedding) egresses directly via
    ollama.embeddings with NO four-axis LlmClient, so it needs its own explicit
    gate — the sibling of the LLMAgentNode._legacy_provider_chat fix."""
    kailash.set_governance_required(True)
    node = _make_embedding_node()  # _ungoverned unset => default False
    with pytest.raises(UngovernedEgressRefused):
        node._fallback_provider_embedding(
            "hello", "ollama", "nomic-embed-text", None, 60, 3
        )


def test_embedding_fallback_ollama_ungoverned_bypasses() -> None:
    kailash.set_governance_required(True)
    node = _make_embedding_node()
    node._ungoverned = True
    try:
        node._fallback_provider_embedding(
            "hello", "ollama", "nomic-embed-text", None, 60, 3
        )
    except UngovernedEgressRefused:
        raise AssertionError("ungoverned=True must bypass the ollama fallback gate")
    except Exception:
        pass  # ollama-not-installed / provider error is acceptable


def test_embedding_fallback_off_posture_byte_identical() -> None:
    # OFF posture: the gate is a no-op; the method proceeds to its normal
    # (ollama-not-installed) RuntimeError, NOT UngovernedEgressRefused.
    kailash.set_governance_required(None)
    node = _make_embedding_node()
    try:
        node._fallback_provider_embedding(
            "hello", "ollama", "nomic-embed-text", None, 60, 3
        )
    except UngovernedEgressRefused:
        raise AssertionError("OFF posture must not gate")
    except Exception:
        pass
