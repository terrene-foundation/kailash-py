# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""#1779 governance_required posture — kaizen-agents orchestration egress gate.

The orchestration subsystem (planner / recovery / protocols / monitor / context)
egresses via ``kaizen_agents.llm.LLMClient`` (raw OpenAI SDK), NOT the gated
four-axis ``kaizen.llm.LlmClient``. Every orchestration component INJECTS a single
LLMClient (dependency injection), so gating the LLMClient construction chokepoint +
its ``ungoverned`` opt-out covers all orchestration egress. Redteam round-5 F3.

Tier-1 unit: offline. No real egress — the gate refuses at construction before the
OpenAI client is built. Posture is a process global; a module lock + reset fixture
serialize it per rules/testing.md § "Serialize Env-Var-Mutating Tests".
"""

from __future__ import annotations

import threading

import pytest

import kailash
from kailash.trust.pact import UngovernedEgressRefused
from kaizen_agents.llm import LLMClient

_POSTURE_LOCK = threading.Lock()


@pytest.fixture(autouse=True)
def _serialized_posture(monkeypatch: pytest.MonkeyPatch):
    with _POSTURE_LOCK:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        kailash.set_governance_required(None)
        try:
            yield
        finally:
            kailash.set_governance_required(None)


def test_off_posture_constructs() -> None:
    kailash.set_governance_required(None)
    assert LLMClient() is not None


def test_on_posture_bare_client_refused() -> None:
    kailash.set_governance_required(True)
    with pytest.raises(UngovernedEgressRefused) as ei:
        LLMClient()
    assert "ungoverned=True" in str(ei.value)


def test_on_posture_ungoverned_optout_allowed() -> None:
    kailash.set_governance_required(True)
    assert LLMClient(ungoverned=True) is not None


def test_env_posture_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KAILASH_GOVERNANCE_REQUIRED", "1")
    with pytest.raises(UngovernedEgressRefused):
        LLMClient()
