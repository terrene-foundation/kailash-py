# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for L3GovernedAgent wrapper — envelope enforcement.

Covers:
- Financial constraint rejection
- Operational constraint (allowed/blocked actions)
- Posture ceiling clamping and enforcement
- Protected inner proxy blocks _inner access
- NaN/Inf cost rejection
- Rejection count tracking
"""

from __future__ import annotations

from typing import Any

import pytest

from kailash.trust.envelope import (
    AgentPosture,
    ConstraintEnvelope,
    FinancialConstraint,
    OperationalConstraint,
)
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen_agents.governed_agent import GovernanceRejectedError, L3GovernedAgent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubAgent(BaseAgent):
    """Minimal agent for governance tests."""

    def run(self, **inputs: Any) -> dict[str, Any]:
        return {"answer": "executed"}

    async def run_async(self, **inputs: Any) -> dict[str, Any]:
        return {"answer": "executed-async"}


def _make_agent() -> _StubAgent:
    return _StubAgent(config=BaseAgentConfig(), mcp_servers=[])


# ---------------------------------------------------------------------------
# Financial constraints
# ---------------------------------------------------------------------------


class TestFinancialConstraints:
    def test_budget_exceeded_rejects(self) -> None:
        envelope = ConstraintEnvelope(
            financial=FinancialConstraint(budget_limit=1.0, max_cost_per_action=0.5)
        )
        agent = _make_agent()
        governed = L3GovernedAgent(agent, envelope=envelope, mcp_servers=[])

        with pytest.raises(GovernanceRejectedError, match="financial"):
            governed.run(_estimated_cost_usd=2.0)

    def test_per_action_limit_rejects(self) -> None:
        envelope = ConstraintEnvelope(
            financial=FinancialConstraint(budget_limit=100.0, max_cost_per_action=0.5)
        )
        agent = _make_agent()
        governed = L3GovernedAgent(agent, envelope=envelope, mcp_servers=[])

        with pytest.raises(GovernanceRejectedError, match="per-action"):
            governed.run(_estimated_cost_usd=1.0)

    def test_within_budget_allows(self) -> None:
        envelope = ConstraintEnvelope(
            financial=FinancialConstraint(budget_limit=100.0, max_cost_per_action=10.0)
        )
        agent = _make_agent()
        governed = L3GovernedAgent(agent, envelope=envelope, mcp_servers=[])

        result = governed.run(_estimated_cost_usd=0.5)
        assert result["answer"] == "executed"

    def test_nan_cost_rejected(self) -> None:
        envelope = ConstraintEnvelope(financial=FinancialConstraint(budget_limit=100.0))
        agent = _make_agent()
        governed = L3GovernedAgent(agent, envelope=envelope, mcp_servers=[])

        with pytest.raises(GovernanceRejectedError, match="non-finite"):
            governed.run(_estimated_cost_usd=float("nan"))

    def test_no_financial_constraint_allows(self) -> None:
        envelope = ConstraintEnvelope()
        agent = _make_agent()
        governed = L3GovernedAgent(agent, envelope=envelope, mcp_servers=[])
        result = governed.run(_estimated_cost_usd=999.0)
        assert result["answer"] == "executed"


# ---------------------------------------------------------------------------
# Operational constraints
# ---------------------------------------------------------------------------


class TestOperationalConstraints:
    def test_blocked_action_rejects(self) -> None:
        envelope = ConstraintEnvelope(
            operational=OperationalConstraint(blocked_actions=("delete_all",))
        )
        agent = _make_agent()
        governed = L3GovernedAgent(agent, envelope=envelope, mcp_servers=[])

        with pytest.raises(GovernanceRejectedError, match="blocked"):
            governed.run(_action="delete_all")

    def test_allowed_action_permits(self) -> None:
        envelope = ConstraintEnvelope(
            operational=OperationalConstraint(allowed_actions=("read", "list"))
        )
        agent = _make_agent()
        governed = L3GovernedAgent(agent, envelope=envelope, mcp_servers=[])

        result = governed.run(_action="read")
        assert result["answer"] == "executed"

    def test_action_not_in_allowlist_rejects(self) -> None:
        envelope = ConstraintEnvelope(
            operational=OperationalConstraint(allowed_actions=("read",))
        )
        agent = _make_agent()
        governed = L3GovernedAgent(agent, envelope=envelope, mcp_servers=[])

        with pytest.raises(GovernanceRejectedError, match="not in the allowed"):
            governed.run(_action="write")


# ---------------------------------------------------------------------------
# Posture ceiling
# ---------------------------------------------------------------------------


class TestPostureCeiling:
    def test_posture_clamped_to_ceiling(self) -> None:
        envelope = ConstraintEnvelope(posture_ceiling="supervised")
        agent = _make_agent()
        governed = L3GovernedAgent(
            agent,
            envelope=envelope,
            posture=AgentPosture.DELEGATED,
            mcp_servers=[],
        )
        # Posture should be clamped down to supervised
        assert governed.posture is not None
        assert governed.posture.fits_ceiling(AgentPosture.SUPERVISED)


# ---------------------------------------------------------------------------
# Protected inner proxy
# ---------------------------------------------------------------------------


class TestProtectedProxy:
    def test_inner_blocks_direct_access(self) -> None:
        envelope = ConstraintEnvelope()
        agent = _make_agent()
        governed = L3GovernedAgent(agent, envelope=envelope, mcp_servers=[])

        with pytest.raises(AttributeError, match="blocked by governance"):
            _ = governed.inner._inner  # type: ignore[union-attr]

    def test_inner_allows_safe_attrs(self) -> None:
        envelope = ConstraintEnvelope()
        agent = _make_agent()
        governed = L3GovernedAgent(agent, envelope=envelope, mcp_servers=[])

        # These should not raise
        assert governed.inner.config is not None  # type: ignore[union-attr]
        assert governed.inner.get_parameters is not None  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Rejection count
# ---------------------------------------------------------------------------


class TestRejectionCount:
    def test_rejection_count_increments(self) -> None:
        envelope = ConstraintEnvelope(
            operational=OperationalConstraint(blocked_actions=("bad",))
        )
        agent = _make_agent()
        governed = L3GovernedAgent(agent, envelope=envelope, mcp_servers=[])

        assert governed.rejection_count == 0

        with pytest.raises(GovernanceRejectedError):
            governed.run(_action="bad")
        assert governed.rejection_count == 1

        with pytest.raises(GovernanceRejectedError):
            governed.run(_action="bad")
        assert governed.rejection_count == 2

    async def test_async_rejection_counted(self) -> None:
        envelope = ConstraintEnvelope(
            operational=OperationalConstraint(blocked_actions=("bad",))
        )
        agent = _make_agent()
        governed = L3GovernedAgent(agent, envelope=envelope, mcp_servers=[])

        with pytest.raises(GovernanceRejectedError):
            await governed.run_async(_action="bad")
        assert governed.rejection_count == 1
