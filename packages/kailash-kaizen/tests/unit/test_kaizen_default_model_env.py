# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 — KAIZEN_DEFAULT_MODEL env var contract.

Covers W6-001 / findings F-D-02 + F-D-50: model identifiers must come from
``.env`` (rules/env-models.md). Two top-level public-API constructors —
``CoreAgent`` (kaizen.core.agents.Agent) and ``GovernedSupervisor``
(kaizen_agents.supervisor.GovernedSupervisor) — must read
``KAIZEN_DEFAULT_MODEL`` when the caller did not supply ``model=`` and raise
:class:`kaizen.errors.EnvModelMissing` when the env var is unset.

Env-var test isolation (rules/testing.md § Env-Var Test Isolation MUST):
every test that mutates ``KAIZEN_DEFAULT_MODEL`` acquires the module-scope
``_ENV_LOCK`` via the ``_env_serialized`` fixture so xdist-parallel runs
cannot observe a mid-monkeypatch state. ``monkeypatch.setenv`` /
``monkeypatch.delenv`` restore at fixture teardown — the lock holds across
the read-then-mutate so siblings cannot race in.
"""

from __future__ import annotations

import threading
from typing import Iterator

import pytest

from kaizen.core.agents import Agent as CoreAgent
from kaizen.errors import EnvModelMissing

# Module-scope lock per rules/testing.md § Env-Var Test Isolation MUST.
# Every test that mutates KAIZEN_DEFAULT_MODEL holds this lock across the
# monkeypatch + body so xdist/pytest-parallel siblings cannot observe the
# transient value or the unset window during teardown.
_ENV_LOCK = threading.Lock()


@pytest.fixture
def _env_serialized() -> Iterator[None]:
    """Acquire the module-scope env lock for the duration of the test body."""
    with _ENV_LOCK:
        yield


# ---------------------------------------------------------------------------
# CoreAgent (kaizen.core.agents.Agent) — F-D-02
# ---------------------------------------------------------------------------


def test_core_agent_uses_env_model_when_caller_omits_model(
    monkeypatch: pytest.MonkeyPatch,
    _env_serialized: None,
) -> None:
    """Caller did not supply model=; KAIZEN_DEFAULT_MODEL is set; agent
    config["model"] reflects the env value (no hardcoded fallback)."""
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")

    agent = CoreAgent(agent_id="env-test-1", config={})

    assert agent.config["model"] == "gpt-4o-mini"


def test_core_agent_caller_explicit_model_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
    _env_serialized: None,
) -> None:
    """Caller-supplied model= beats KAIZEN_DEFAULT_MODEL; the env var is a
    default, not an enforcer. This protects per-call provider routing."""
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")

    agent = CoreAgent(
        agent_id="env-test-2",
        config={"model": "claude-3-5-sonnet"},
    )

    assert agent.config["model"] == "claude-3-5-sonnet"


def test_core_agent_raises_env_model_missing_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
    _env_serialized: None,
) -> None:
    """No model= AND no env var — raise the typed error with an actionable
    message naming the env var. Silent fallback to a hardcoded literal is
    BLOCKED per rules/env-models.md."""
    monkeypatch.delenv("KAIZEN_DEFAULT_MODEL", raising=False)

    with pytest.raises(EnvModelMissing) as exc_info:
        CoreAgent(agent_id="env-test-3", config={})

    err = exc_info.value
    assert err.env_var == "KAIZEN_DEFAULT_MODEL"
    assert err.component == "CoreAgent"
    assert "KAIZEN_DEFAULT_MODEL" in str(err)
    # Message must instruct the user — not just name the gap.
    assert ".env" in str(err)


def test_core_agent_treats_empty_env_as_unset(
    monkeypatch: pytest.MonkeyPatch,
    _env_serialized: None,
) -> None:
    """An empty-string value of KAIZEN_DEFAULT_MODEL is functionally unset —
    sending an empty model identifier to a provider produces opaque
    400/401 errors. Raise with the same actionable error."""
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "")

    with pytest.raises(EnvModelMissing):
        CoreAgent(agent_id="env-test-4", config={})


# ---------------------------------------------------------------------------
# GovernedSupervisor (kaizen_agents.supervisor.GovernedSupervisor) — F-D-50
# ---------------------------------------------------------------------------
#
# GovernedSupervisor lives in the optional kaizen-agents sub-package; if it
# is not editable-installed in the test venv, skip the supervisor block
# rather than failing collection. Test runner per rules/python-environment.md
# expects kaizen-agents installed alongside kaizen for the full suite.


supervisor_module = pytest.importorskip(
    "kaizen_agents.supervisor",
    reason="kaizen-agents not installed; GovernedSupervisor tests skipped",
)
GovernedSupervisor = supervisor_module.GovernedSupervisor


def test_governed_supervisor_uses_env_model_when_caller_omits_model(
    monkeypatch: pytest.MonkeyPatch,
    _env_serialized: None,
) -> None:
    """Caller did not supply model=; KAIZEN_DEFAULT_MODEL is set; supervisor
    stores the env value (no hardcoded "claude-sonnet-4-6" fallback)."""
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")

    supervisor = GovernedSupervisor(budget_usd=1.0)

    assert supervisor._model == "gpt-4o-mini"


def test_governed_supervisor_caller_explicit_model_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
    _env_serialized: None,
) -> None:
    """Caller-supplied model= beats KAIZEN_DEFAULT_MODEL on supervisor."""
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")

    supervisor = GovernedSupervisor(model="claude-3-5-sonnet", budget_usd=1.0)

    assert supervisor._model == "claude-3-5-sonnet"


def test_governed_supervisor_raises_env_model_missing_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
    _env_serialized: None,
) -> None:
    """No model= AND no env var — raise EnvModelMissing with component
    set to "GovernedSupervisor" so multi-call-site triage can disambiguate."""
    monkeypatch.delenv("KAIZEN_DEFAULT_MODEL", raising=False)

    with pytest.raises(EnvModelMissing) as exc_info:
        GovernedSupervisor(budget_usd=1.0)

    err = exc_info.value
    assert err.env_var == "KAIZEN_DEFAULT_MODEL"
    assert err.component == "GovernedSupervisor"
    assert "KAIZEN_DEFAULT_MODEL" in str(err)


def test_governed_supervisor_treats_empty_env_as_unset(
    monkeypatch: pytest.MonkeyPatch,
    _env_serialized: None,
) -> None:
    """Empty-string KAIZEN_DEFAULT_MODEL on supervisor is also unset."""
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "")

    with pytest.raises(EnvModelMissing):
        GovernedSupervisor(budget_usd=1.0)
