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
    assert "ungoverned=True" in msg and "install_interceptor" in msg


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
# (e) posture ON + installed interceptor pair → allowed (not re-gated)
# --------------------------------------------------------------------------- #


def test_on_installed_interceptor_exempt() -> None:
    from kailash.trust.pact import (
        EffectGovernor,
        OutboundEffect,
        OutboundEffectInterceptor,
        OutboundVerdict,
        clear_interceptor,
        install_interceptor,
    )

    class _AllowGovernor(EffectGovernor):
        """Minimal allow-everything governor — the gate only checks that an
        interceptor is installed (a governance pair is present), never runs it."""

        def evaluate(self, effect: OutboundEffect) -> OutboundVerdict:
            return OutboundVerdict(
                allowed=True,
                level="auto_approved",
                reason="test",
                effect=effect,
            )

    kailash.set_governance_required(True)
    install_interceptor(OutboundEffectInterceptor(_AllowGovernor()))
    try:
        # A real deployment that would normally be refused is exempt because a
        # process-global interceptor carries the governance pair.
        assert LlmClient.from_deployment(_real()) is not None
    finally:
        clear_interceptor()


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


@pytest.mark.asyncio
async def test_lazy_exempt_when_ungoverned() -> None:
    kailash.set_governance_required(None)
    client = LlmClient.from_deployment(_real(), ungoverned=True)
    kailash.set_governance_required(True)
    # ungoverned client stays exempt at the lazy check too (mock transport
    # keeps it offline)
    result = await client.complete(
        [{"role": "user", "content": "hi"}], http_client=MockLlmHttpClient()
    )
    assert result is not None


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


def test_agent_off_real_provider_constructs() -> None:
    kailash.set_governance_required(None)
    agent = Agent(model=_MODEL, show_startup_banner=False)
    assert agent is not None
