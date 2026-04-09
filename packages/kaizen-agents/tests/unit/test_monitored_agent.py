# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for MonitoredAgent wrapper — cost tracking and budget enforcement.

Covers:
- Cost tracking records usage from result dicts
- Budget enforcement raises BudgetExhaustedError
- NaN/Inf budget rejection
- Budget remaining calculation
"""

from __future__ import annotations

from typing import Any

import pytest

from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen_agents.monitored_agent import BudgetExhaustedError, MonitoredAgent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _UsageAgent(BaseAgent):
    """Agent that returns a result with token usage."""

    def __init__(self, usage: dict[str, int] | None = None) -> None:
        config = BaseAgentConfig()
        super().__init__(config=config, mcp_servers=[])
        self._usage = (
            usage
            if usage is not None
            else {"prompt_tokens": 100, "completion_tokens": 50}
        )

    def run(self, **inputs: Any) -> dict[str, Any]:
        return {"answer": "ok", "usage": self._usage}

    async def run_async(self, **inputs: Any) -> dict[str, Any]:
        return {"answer": "ok", "usage": self._usage}


def _make_monitored(
    budget_usd: float | None = None,
    usage: dict[str, int] | None = None,
) -> MonitoredAgent:
    agent = _UsageAgent(usage=usage)
    return MonitoredAgent(agent, budget_usd=budget_usd, mcp_servers=[])


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------


class TestCostTracking:
    def test_records_usage_from_result(self) -> None:
        monitored = _make_monitored()
        monitored.run(prompt="test")
        # Cost tracker should have recorded the tokens
        assert monitored.cost_tracker._total_prompt_tokens == 100
        assert monitored.cost_tracker._total_completion_tokens == 50

    async def test_records_usage_async(self) -> None:
        monitored = _make_monitored()
        await monitored.run_async(prompt="test")
        assert monitored.cost_tracker._total_prompt_tokens == 100

    def test_no_usage_in_result_records_zero(self) -> None:
        agent = _UsageAgent(usage={})
        monitored = MonitoredAgent(agent, mcp_servers=[])
        monitored.run(prompt="test")
        assert monitored.cost_tracker._total_prompt_tokens == 0


# ---------------------------------------------------------------------------
# Budget enforcement
# ---------------------------------------------------------------------------


class TestBudgetEnforcement:
    def test_budget_exhausted_raises(self) -> None:
        monitored = _make_monitored(budget_usd=0.0001)
        # First call succeeds but records cost
        monitored.run(prompt="test")
        # Second call should fail if budget is exceeded
        # (depends on pricing — with zero cost config, cost may be 0)
        # So let's directly set cost for deterministic test
        monitored._cost_tracker._total_cost_usd = 0.001
        with pytest.raises(BudgetExhaustedError):
            monitored.run(prompt="test2")

    async def test_budget_exhausted_async(self) -> None:
        monitored = _make_monitored(budget_usd=0.0001)
        monitored._cost_tracker._total_cost_usd = 0.001
        with pytest.raises(BudgetExhaustedError):
            await monitored.run_async(prompt="test")

    def test_no_budget_allows_unlimited(self) -> None:
        monitored = _make_monitored(budget_usd=None)
        # Should not raise
        monitored.run(prompt="test")
        assert monitored.budget_remaining_usd is None


# ---------------------------------------------------------------------------
# NaN/Inf rejection
# ---------------------------------------------------------------------------


class TestNanInfRejection:
    def test_nan_budget_rejected(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _make_monitored(budget_usd=float("nan"))

    def test_inf_budget_rejected(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _make_monitored(budget_usd=float("inf"))

    def test_negative_inf_budget_rejected(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _make_monitored(budget_usd=float("-inf"))


# ---------------------------------------------------------------------------
# Budget remaining
# ---------------------------------------------------------------------------


class TestBudgetRemaining:
    def test_budget_remaining_decreases(self) -> None:
        monitored = _make_monitored(budget_usd=10.0)
        assert monitored.budget_remaining_usd == 10.0
        # Simulate cost
        monitored._cost_tracker._total_cost_usd = 3.5
        assert monitored.budget_remaining_usd == 6.5

    def test_budget_remaining_floors_at_zero(self) -> None:
        monitored = _make_monitored(budget_usd=1.0)
        monitored._cost_tracker._total_cost_usd = 5.0
        assert monitored.budget_remaining_usd == 0.0
