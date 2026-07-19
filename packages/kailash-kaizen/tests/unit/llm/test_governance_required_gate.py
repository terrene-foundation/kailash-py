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

import kailash
import pytest
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


def test_agent_ungoverned_reaches_runpath_node_config() -> None:
    """Redteam round-5 F1/F2: the PRIMARY agent run path builds its LLMAgentNode
    node_config via workflow_generator (NOT base_agent.to_workflow). This test
    asserts ungoverned reaches THAT node_config — the config-only assertion the
    round-1 test used masked the broken wiring for four rounds."""
    kailash.set_governance_required(None)
    a = Agent(model=_MODEL, ungoverned=True, show_startup_banner=False)
    assert a.base_agent.config.ungoverned is True
    # The real run path: strategy -> workflow_generator.generate_signature_workflow.
    wf = a.base_agent.workflow_generator.generate_signature_workflow()
    assert wf.nodes["agent_exec"]["config"].get("ungoverned") is True
    # Default agent (no opt-out): node_config carries ungoverned=False.
    b = Agent(model=_MODEL, show_startup_banner=False)
    wfb = b.base_agent.workflow_generator.generate_signature_workflow()
    assert wfb.nodes["agent_exec"]["config"].get("ungoverned") is False


def test_agent_ungoverned_reaches_fallback_node_config() -> None:
    """The fallback builder (generate_fallback_workflow) is the second run-path
    node_config surface — it must thread ungoverned too (round-5 F1)."""
    kailash.set_governance_required(None)
    a = Agent(model=_MODEL, ungoverned=True, show_startup_banner=False)
    wf = a.base_agent.workflow_generator.generate_fallback_workflow()
    assert wf.nodes["agent_fallback"]["config"].get("ungoverned") is True


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


def test_embedding_node_run_propagates_typed_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redteam round-7: the PUBLIC run() entry must propagate UngovernedEgressRefused
    unwrapped, not swallow it into a {success: False} dict (invariant 4)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    kailash.set_governance_required(True)
    node = _make_embedding_node()
    with pytest.raises(UngovernedEgressRefused):
        node.run(
            operation="embed_text",
            input_text="hi",
            provider="openai",
            model="text-embedding-3-small",
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


# --------------------------------------------------------------------------- #
# Fail-closed: a posture-read error is treated as ACTIVE (invariant 5)
# --------------------------------------------------------------------------- #


def test_enforce_fail_closed_when_posture_read_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # If is_governance_required() raises, the gate MUST treat the posture as
    # ACTIVE and refuse — never silently allow ungoverned egress (invariant 5,
    # governance_gate.py:99-108). Security-reviewer flagged this branch as the
    # one release-cycle test gap; here is the direct coverage.
    from kaizen.llm.governance_gate import enforce_governance_posture

    def _boom() -> bool:
        raise RuntimeError("posture backend unavailable")

    monkeypatch.setattr(kailash, "is_governance_required", _boom)
    with pytest.raises(UngovernedEgressRefused):
        enforce_governance_posture(is_mock=False, ungoverned=False, surface="LlmClient")


def test_enforce_fail_closed_exemptions_short_circuit_before_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ungoverned=True and is_mock=True short-circuit BEFORE the posture read, so
    # a raising reader is never reached — the exemptions still allow even when
    # the posture backend is unavailable.
    from kaizen.llm.governance_gate import enforce_governance_posture

    def _boom() -> bool:
        raise RuntimeError("must not be reached when exempt")

    monkeypatch.setattr(kailash, "is_governance_required", _boom)
    # Neither raises despite the poisoned reader (exemptions short-circuit).
    enforce_governance_posture(is_mock=False, ungoverned=True, surface="LlmClient")
    enforce_governance_posture(is_mock=True, ungoverned=False, surface="Agent")


# --------------------------------------------------------------------------- #
# #1803 — AzureAIFoundryProvider direct standalone use (the only legacy chat
# provider still constructible after #1720 Wave-2 retired openai / anthropic /
# google / ollama / docker / perplexity / mock; #1820 retired the embedding-
# legacy + unified-azure stacks). Previously gated ONLY when reached through
# LLMAgentNode._legacy_provider_chat; direct construction bypassed the gate
# entirely. Gate lives at each egress method (chat/chat_async/stream_chat/
# embed/embed_async), NOT __init__ -- construction and metadata-only methods
# (is_available/get_capabilities/get_available_providers) must never gate.
# --------------------------------------------------------------------------- #


def test_azure_foundry_construction_and_metadata_never_gated() -> None:
    """Bare construction and metadata-only introspection must NOT gate --
    only the real-egress methods do (mirrors the deployment-less LlmClient
    exemption: is_available()/get_available_providers() are not egress)."""
    from kaizen.providers.llm.azure import AzureAIFoundryProvider

    kailash.set_governance_required(True)
    provider = AzureAIFoundryProvider()  # must not raise
    assert provider is not None
    assert provider.is_available() in (True, False)  # must not raise
    assert provider.capabilities is not None


def test_azure_foundry_standalone_chat_refused_under_posture_on() -> None:
    from kaizen.providers.llm.azure import AzureAIFoundryProvider

    kailash.set_governance_required(True)
    provider = AzureAIFoundryProvider()
    with pytest.raises(UngovernedEgressRefused):
        provider.chat([{"role": "user", "content": "hi"}])


def test_azure_foundry_standalone_ungoverned_bypasses() -> None:
    from kaizen.providers.llm.azure import AzureAIFoundryProvider

    kailash.set_governance_required(True)
    provider = AzureAIFoundryProvider(ungoverned=True)
    try:
        provider.chat([{"role": "user", "content": "hi"}])
    except UngovernedEgressRefused:
        raise AssertionError("ungoverned=True must bypass the standalone gate")
    except Exception:
        pass  # missing azure-ai-inference credentials/endpoint is acceptable


def test_azure_foundry_off_posture_byte_identical() -> None:
    from kaizen.providers.llm.azure import AzureAIFoundryProvider

    kailash.set_governance_required(None)
    provider = AzureAIFoundryProvider()
    try:
        provider.chat([{"role": "user", "content": "hi"}])
    except UngovernedEgressRefused:
        raise AssertionError("OFF posture must not gate")
    except Exception:
        pass


@pytest.mark.asyncio
async def test_azure_foundry_chat_async_refused() -> None:
    from kaizen.providers.llm.azure import AzureAIFoundryProvider

    kailash.set_governance_required(True)
    provider = AzureAIFoundryProvider()
    with pytest.raises(UngovernedEgressRefused):
        await provider.chat_async([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_azure_foundry_stream_chat_refused() -> None:
    from kaizen.providers.llm.azure import AzureAIFoundryProvider

    kailash.set_governance_required(True)
    provider = AzureAIFoundryProvider()
    with pytest.raises(UngovernedEgressRefused):
        async for _ in provider.stream_chat([{"role": "user", "content": "hi"}]):
            pass


def test_azure_foundry_embed_refused() -> None:
    from kaizen.providers.llm.azure import AzureAIFoundryProvider

    kailash.set_governance_required(True)
    provider = AzureAIFoundryProvider()
    with pytest.raises(UngovernedEgressRefused):
        provider.embed(["hello"])


@pytest.mark.asyncio
async def test_azure_foundry_embed_async_refused() -> None:
    from kaizen.providers.llm.azure import AzureAIFoundryProvider

    kailash.set_governance_required(True)
    provider = AzureAIFoundryProvider()
    with pytest.raises(UngovernedEgressRefused):
        await provider.embed_async(["hello"])


def test_get_provider_threads_ungoverned_so_node_and_instance_agree() -> None:
    """registry.get_provider(ungoverned=...) must reach the constructed
    instance's own gate, so LLMAgentNode._legacy_provider_chat's outer gate
    and AzureAIFoundryProvider's inner gate agree instead of double-refusing
    when ungoverned=True."""
    from kaizen.providers.registry import get_provider

    kailash.set_governance_required(True)
    provider = get_provider("azure_ai_foundry", ungoverned=True)
    try:
        provider.chat([{"role": "user", "content": "hi"}])
    except UngovernedEgressRefused:
        raise AssertionError(
            "get_provider(ungoverned=True) must construct an ungoverned instance"
        )
    except Exception:
        pass


def test_get_provider_default_ungoverned_false_still_gates() -> None:
    from kaizen.providers.registry import get_provider

    kailash.set_governance_required(True)
    provider = get_provider("azure_ai_foundry")
    with pytest.raises(UngovernedEgressRefused):
        provider.chat([{"role": "user", "content": "hi"}])


# --------------------------------------------------------------------------- #
# #1803 — document / vision providers (kaizen.providers.document.*). No mock
# concept exists for these providers (is_mock=False always); the gate fires
# at the top of extract(), before file validation, so a nonexistent path
# still surfaces UngovernedEgressRefused rather than FileNotFoundError.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_openai_vision_provider_refused_under_posture_on() -> None:
    from kaizen.providers.document.openai_vision_provider import OpenAIVisionProvider

    kailash.set_governance_required(True)
    provider = OpenAIVisionProvider(api_key="sk-test")
    with pytest.raises(UngovernedEgressRefused):
        await provider.extract("nonexistent.pdf", "pdf")


@pytest.mark.asyncio
async def test_openai_vision_provider_ungoverned_bypasses() -> None:
    from kaizen.providers.document.openai_vision_provider import OpenAIVisionProvider

    kailash.set_governance_required(True)
    provider = OpenAIVisionProvider(api_key="sk-test", ungoverned=True)
    try:
        await provider.extract("nonexistent.pdf", "pdf")
    except UngovernedEgressRefused:
        raise AssertionError("ungoverned=True must bypass the extract() gate")
    except Exception:
        pass  # FileNotFoundError past the gate is expected


@pytest.mark.asyncio
async def test_landing_ai_provider_refused_under_posture_on() -> None:
    from kaizen.providers.document.landing_ai_provider import LandingAIProvider

    kailash.set_governance_required(True)
    provider = LandingAIProvider(api_key="test-key")
    with pytest.raises(UngovernedEgressRefused):
        await provider.extract("nonexistent.pdf", "pdf")


@pytest.mark.asyncio
async def test_landing_ai_provider_ungoverned_bypasses() -> None:
    from kaizen.providers.document.landing_ai_provider import LandingAIProvider

    kailash.set_governance_required(True)
    provider = LandingAIProvider(api_key="test-key", ungoverned=True)
    try:
        await provider.extract("nonexistent.pdf", "pdf")
    except UngovernedEgressRefused:
        raise AssertionError("ungoverned=True must bypass the extract() gate")
    except Exception:
        pass  # FileNotFoundError past the gate is expected


@pytest.mark.asyncio
async def test_ollama_vision_document_provider_refused_under_posture_on() -> None:
    """Locality is NOT a governance exemption -- a local base_url is still
    real network egress, gated the same as any other provider."""
    from kaizen.providers.document.ollama_vision_provider import OllamaVisionProvider

    kailash.set_governance_required(True)
    provider = OllamaVisionProvider()
    with pytest.raises(UngovernedEgressRefused):
        await provider.extract("nonexistent.pdf", "pdf")


@pytest.mark.asyncio
async def test_ollama_vision_document_provider_ungoverned_bypasses() -> None:
    from kaizen.providers.document.ollama_vision_provider import OllamaVisionProvider

    kailash.set_governance_required(True)
    provider = OllamaVisionProvider(ungoverned=True)
    try:
        await provider.extract("nonexistent.pdf", "pdf")
    except UngovernedEgressRefused:
        raise AssertionError("ungoverned=True must bypass the extract() gate")
    except Exception:
        pass  # FileNotFoundError past the gate is expected


def test_provider_manager_forwards_ungoverned_to_all_sub_providers() -> None:
    from kaizen.providers.document.provider_manager import ProviderManager

    manager = ProviderManager(ungoverned=True)
    assert manager.providers["landing_ai"]._ungoverned is True
    assert manager.providers["openai_vision"]._ungoverned is True
    assert manager.providers["ollama_vision"]._ungoverned is True


def test_provider_manager_default_ungoverned_false() -> None:
    from kaizen.providers.document.provider_manager import ProviderManager

    manager = ProviderManager()
    assert manager.providers["landing_ai"]._ungoverned is False
    assert manager.providers["openai_vision"]._ungoverned is False
    assert manager.providers["ollama_vision"]._ungoverned is False


# --------------------------------------------------------------------------- #
# #1803 — legacy standalone OllamaProvider (kaizen.providers.ollama_provider,
# re-exported as kaizen.providers.LegacyOllamaProvider). Gate lives at
# __init__, BEFORE _check_ollama_available()'s unconditional real egress
# (ollama.list()) -- there is no way to obtain a constructed instance
# without passing through it, so a single construction-time gate covers
# every egress method transitively.
# --------------------------------------------------------------------------- #


def test_ollama_provider_refused_under_posture_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    from unittest.mock import MagicMock

    from kaizen.providers.ollama_provider import OllamaProvider

    mock_ollama = MagicMock()
    mock_ollama.list.return_value = {"models": []}
    monkeypatch.setitem(sys.modules, "ollama", mock_ollama)

    kailash.set_governance_required(True)
    with pytest.raises(UngovernedEgressRefused):
        OllamaProvider()


def test_ollama_provider_ungoverned_bypasses(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from unittest.mock import MagicMock

    from kaizen.providers.ollama_provider import OllamaConfig, OllamaProvider

    mock_ollama = MagicMock()
    mock_ollama.list.return_value = {"models": []}
    monkeypatch.setitem(sys.modules, "ollama", mock_ollama)

    kailash.set_governance_required(True)
    provider = OllamaProvider(config=OllamaConfig(ungoverned=True))
    assert provider is not None


def test_ollama_provider_off_posture_byte_identical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    from unittest.mock import MagicMock

    from kaizen.providers.ollama_provider import OllamaProvider

    mock_ollama = MagicMock()
    mock_ollama.list.return_value = {"models": []}
    monkeypatch.setitem(sys.modules, "ollama", mock_ollama)

    kailash.set_governance_required(None)
    assert OllamaProvider() is not None


# --------------------------------------------------------------------------- #
# #1803 — multi-modal adapters (kaizen.providers.multi_modal_adapter). The
# Ollama adapter's gate lives transitively at OllamaProvider.__init__ (via
# _get_ollama_vision_provider's lazy construction); the OpenAI adapter's
# gate is explicit at the top of process_multi_modal (all 3 of its internal
# branches -- vision/whisper/text -- construct openai.OpenAI() only after
# that dispatch point).
# --------------------------------------------------------------------------- #


def test_openai_multi_modal_adapter_refused_under_posture_on() -> None:
    from kaizen.providers.multi_modal_adapter import OpenAIMultiModalAdapter

    kailash.set_governance_required(True)
    adapter = OpenAIMultiModalAdapter(api_key="sk-test")
    with pytest.raises(UngovernedEgressRefused):
        adapter.process_multi_modal(text="hello", prompt="hi")


def test_openai_multi_modal_adapter_ungoverned_bypasses() -> None:
    from unittest.mock import MagicMock, patch

    from kaizen.providers.multi_modal_adapter import OpenAIMultiModalAdapter

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="ok"))
    ]
    kailash.set_governance_required(True)
    adapter = OpenAIMultiModalAdapter(api_key="sk-test", ungoverned=True)
    with patch("openai.OpenAI", return_value=mock_client):
        try:
            adapter.process_multi_modal(text="hello", prompt="hi")
        except UngovernedEgressRefused:
            raise AssertionError(
                "ungoverned=True must bypass process_multi_modal's gate"
            )


def test_openai_multi_modal_adapter_off_posture_byte_identical() -> None:
    from unittest.mock import MagicMock, patch

    from kaizen.providers.multi_modal_adapter import OpenAIMultiModalAdapter

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="ok"))
    ]
    kailash.set_governance_required(None)
    adapter = OpenAIMultiModalAdapter(api_key="sk-test")
    with patch("openai.OpenAI", return_value=mock_client):
        try:
            adapter.process_multi_modal(text="hello", prompt="hi")
        except UngovernedEgressRefused:
            raise AssertionError("OFF posture must not gate")


def test_ollama_multi_modal_adapter_refused_under_posture_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    from unittest.mock import MagicMock

    from kaizen.providers.multi_modal_adapter import OllamaMultiModalAdapter

    mock_ollama = MagicMock()
    mock_ollama.list.return_value = {"models": []}
    monkeypatch.setitem(sys.modules, "ollama", mock_ollama)

    kailash.set_governance_required(True)
    adapter = OllamaMultiModalAdapter()
    with pytest.raises(UngovernedEgressRefused):
        adapter.process_multi_modal(text="hello", prompt="hi")


def test_ollama_multi_modal_adapter_ungoverned_bypasses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    from unittest.mock import MagicMock

    from kaizen.providers.multi_modal_adapter import OllamaMultiModalAdapter

    mock_ollama = MagicMock()
    mock_ollama.list.side_effect = Exception("Connection refused")
    monkeypatch.setitem(sys.modules, "ollama", mock_ollama)

    kailash.set_governance_required(True)
    adapter = OllamaMultiModalAdapter(ungoverned=True)
    try:
        adapter.process_multi_modal(text="hello", prompt="hi")
    except UngovernedEgressRefused:
        raise AssertionError(
            "ungoverned=True must bypass the underlying OllamaProvider gate"
        )
    except Exception:
        pass  # Ollama unavailable downstream is acceptable


# --------------------------------------------------------------------------- #
# #1803 — mechanical parity sweep (acceptance criterion): every real LLM/
# vision-egress client-construction site under kaizen/ lives in a file that
# also calls enforce_governance_posture, OR is core four-axis LlmClient wire
# machinery (kaizen/llm/**, gated once at LlmClient.__init__ /
# _enforce_lazy_governance rather than per internal call site). A structural
# grep sweep, not a probe -- rules/probe-driven-verification.md Rule 3: no
# LLM judge is needed to answer "does this file contain both a construction
# site and a gate call".
# --------------------------------------------------------------------------- #


def test_no_ungated_egress_construction_site_outside_known_files() -> None:
    import re
    from pathlib import Path

    kaizen_src = Path(__file__).resolve().parents[3] / "src" / "kaizen"
    assert kaizen_src.is_dir(), f"expected kaizen src at {kaizen_src}"

    construction_re = re.compile(
        r"openai\.(Async)?OpenAI\("
        r"|anthropic\.(Async)?Anthropic\("
        r"|genai\."
        r"|httpx\.(Async)?Client\("
        r"|ChatCompletionsClient\("
        r"|EmbeddingsClient\("
        r"|ollama\.(chat|list|embeddings|generate)\("
        # #1803 security-review MEDIUM: the initial pattern set missed
        # aiohttp/requests-based egress entirely (caught SimpleEmbeddingProvider
        # ungated -- HIGH, fixed same session). Broadened so the sweep proves
        # more than "the sites I already know how to recognize are gated".
        # aiohttp's CONSTRUCTION site (ClientSession()) is the chokepoint --
        # a generic `session.post/get(` pattern was tried and dropped: "session"
        # is an extremely common non-HTTP variable name (dict.get() on a
        # conversation/approval-request session both false-matched). The
        # negative lookbehind on `requests\.` avoids matching `self._requests.get(`
        # (an approval-request STORE, not the requests HTTP library) as a substring.
        r"|aiohttp\.ClientSession\("
        r"|(?<!\w)requests\.(post|get)\("
    )
    gate_re = re.compile(r"enforce_governance_posture\(")

    # kaizen/llm/** is the four-axis LlmClient's OWN wire-transport
    # implementation: gated once, structurally, at LlmClient.__init__ /
    # _enforce_lazy_governance (client.py) -- not per internal call site
    # inside the wire adapters (http_client.py, wire/*). This is the
    # documented Wave-C-retiring-adjacent exemption: kaizen/llm/* is the
    # governed path itself, not a gap.
    exempt_prefixes = ("llm/",)

    # Explicit per-file exemptions, each with a load-bearing reason (#1803
    # audit finding -- verified, not assumed): construction-time gating that
    # covers the file transitively via inheritance, model-lifecycle
    # administration outside the posture's user-data-egress scope, or a
    # false-positive match inside prose/docstring text.
    exempt_files = {
        # OllamaVisionProvider.analyze_images() calls ollama.chat() directly
        # for the multi-image path, but __init__ inherits OllamaProvider's
        # gate (providers/ollama_provider.py) via super().__init__() -- no
        # instance can exist without passing through it first.
        "providers/ollama_vision_provider.py",
        # Model lifecycle administration (list/pull installed models), NOT
        # user-data LLM egress -- outside the governance_required posture's
        # scope (kaizen/llm/governance_gate.py docstring: "a real,
        # un-governed LLM call").
        "providers/ollama_model_manager.py",
        # BYOKClientCache is orphaned (#1803 audit: zero production call
        # sites anywhere in kaizen; only its own regression tests construct
        # it). The regex match is the module docstring's USAGE EXAMPLE
        # (`factory=lambda: openai.OpenAI(...)`), not executable code -- the
        # cache itself never constructs a client (the factory is opaque and
        # caller-supplied). No live construction to gate.
        "nodes/ai/client_cache.py",
        # --- security-review follow-up (same session): broadening the regex
        # to catch aiohttp/requests egress (the SimpleEmbeddingProvider HIGH
        # fix) surfaced these additional real HTTP call sites. None are LLM/
        # vision PROVIDER egress (no prompt/conversation content sent to an
        # LLM API) -- each is out of THIS posture's stated scope (governance_
        # gate.py docstring: "a real, un-governed LLM call") and is a
        # different governance surface entirely:
        #
        # Availability/administration check (requests.get to /api/tags),
        # same class as the ollama_model_manager.py exemption above.
        "config/providers.py",
        # ImageField.from_url() / AudioField.from_url() fetch raw input BYTES
        # from a caller-supplied URL -- input loading, not provider egress
        # (no prompt/conversation data is sent anywhere).
        "signatures/multi_modal.py",
        # AlertManager posts to a monitoring/alerting webhook (Slack/PagerDuty-
        # style) -- operational alerting, not LLM/vision provider egress.
        "monitoring/alert_manager.py",
        # WebSearchTool / WebFetchTool are dumb data-fetch TOOLS an agent may
        # invoke (rules/agent-reasoning.md "tools are dumb data endpoints") --
        # they fetch public web content FOR the agent, they do not send
        # conversation data TO an LLM/vision provider.
        "tools/native/search_tools.py",
        # HTTPTransport is the Control Protocol's bidirectional transport
        # (ADR-011, human-in-the-loop question/approval channel over SSE) --
        # control-plane communication, not LLM/vision provider egress.
        "core/autonomy/control/transports/http.py",
    }

    violations = []
    for path in kaizen_src.rglob("*.py"):
        rel = path.relative_to(kaizen_src).as_posix()
        if rel.startswith(exempt_prefixes) or rel in exempt_files:
            continue
        text = path.read_text()
        if not construction_re.search(text):
            continue
        if gate_re.search(text):
            continue
        violations.append(rel)

    assert not violations, (
        "Ungated LLM/vision-egress construction site(s) found -- no "
        "enforce_governance_posture call in the same file (#1803 parity "
        f"sweep): {violations}. Gate at construction or the real-egress "
        "method (mirroring #1779/#1803), or extend the allowlist above if "
        "this is documented Wave-C-retiring code or core four-axis wire "
        "machinery."
    )


# --------------------------------------------------------------------------- #
# #1803 security-review follow-up (same session, HIGH finding fixed) --
# kaizen.nodes.ai.semantic_memory.SimpleEmbeddingProvider makes real aiohttp
# egress to an embedding host (default localhost, but caller-configurable)
# with NO four-axis LlmClient in the path. Gate lives at the top of
# embed_text(), before the cache check or the aiohttp session. ungoverned is
# threaded from every consumer: SemanticMemoryStoreNode, SemanticMemorySearchNode,
# SemanticAgentMatchingNode (semantic_memory.py), and SemanticHybridSearchNode /
# AdaptiveSearchNode (hybrid_search.py, the latter composing the former).
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_simple_embedding_provider_refused_under_posture_on() -> None:
    from kaizen.nodes.ai.semantic_memory import SimpleEmbeddingProvider

    kailash.set_governance_required(True)
    provider = SimpleEmbeddingProvider()
    with pytest.raises(UngovernedEgressRefused):
        await provider.embed_text("hello")


@pytest.mark.asyncio
async def test_simple_embedding_provider_ungoverned_bypasses() -> None:
    from kaizen.nodes.ai.semantic_memory import SimpleEmbeddingProvider

    kailash.set_governance_required(True)
    provider = SimpleEmbeddingProvider(ungoverned=True)
    try:
        await provider.embed_text("hello")
    except UngovernedEgressRefused:
        raise AssertionError("ungoverned=True must bypass embed_text's gate")
    except Exception:
        pass  # numpy-missing / connection-refused past the gate is acceptable


@pytest.mark.asyncio
async def test_simple_embedding_provider_off_posture_byte_identical() -> None:
    from kaizen.nodes.ai.semantic_memory import SimpleEmbeddingProvider

    kailash.set_governance_required(None)
    provider = SimpleEmbeddingProvider()
    try:
        await provider.embed_text("hello")
    except UngovernedEgressRefused:
        raise AssertionError("OFF posture must not gate")
    except Exception:
        pass


def test_semantic_memory_nodes_thread_ungoverned_to_provider() -> None:
    """SemanticMemoryStoreNode / SemanticMemorySearchNode / SemanticAgentMatchingNode
    each construct an INSTANCE-level SimpleEmbeddingProvider on init -- assert
    the node's own ungoverned kwarg reaches it."""
    from kaizen.nodes.ai.semantic_memory import (
        SemanticAgentMatchingNode,
        SemanticMemorySearchNode,
        SemanticMemoryStoreNode,
    )

    for cls in (
        SemanticMemoryStoreNode,
        SemanticMemorySearchNode,
        SemanticAgentMatchingNode,
    ):
        node = cls(name="test_node", ungoverned=True)
        assert node._provider._ungoverned is True


def test_semantic_memory_nodes_provider_ungoverned_not_sticky_across_instances() -> (
    None
):
    """#1803 security-review MEDIUM regression: the provider was PREVIOUSLY
    cached on the CLASS (``if not hasattr(cls, "_provider")``), so the FIRST
    instance's ungoverned value silently governed every LATER instance of the
    same class in this process -- an ungoverned=True node constructed first
    would leave a later default (governed) node's embed_text() ALSO
    ungoverned. Assert two same-class instances get INDEPENDENT providers."""
    from kaizen.nodes.ai.semantic_memory import SemanticMemoryStoreNode

    opted_out = SemanticMemoryStoreNode(name="opted_out", ungoverned=True)
    governed = SemanticMemoryStoreNode(name="governed")
    assert opted_out._provider is not governed._provider
    assert opted_out._provider._ungoverned is True
    assert governed._provider._ungoverned is False


def test_semantic_hybrid_search_node_threads_ungoverned_to_provider() -> None:
    from kaizen.nodes.ai.hybrid_search import SemanticHybridSearchNode

    node = SemanticHybridSearchNode(name="hybrid_test", ungoverned=True)
    assert node.embedding_provider._ungoverned is True


def test_adaptive_search_node_forwards_ungoverned_to_hybrid_search() -> None:
    from kaizen.nodes.ai.hybrid_search import AdaptiveSearchNode

    node = AdaptiveSearchNode(name="adaptive_test", ungoverned=True)
    assert node.hybrid_search.embedding_provider._ungoverned is True


def test_semantic_memory_nodes_default_ungoverned_false() -> None:
    from kaizen.nodes.ai.semantic_memory import SemanticAgentMatchingNode

    node = SemanticAgentMatchingNode(name="match_default")
    assert node._provider._ungoverned is False
