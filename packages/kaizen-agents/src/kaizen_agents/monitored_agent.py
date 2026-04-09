# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""MonitoredAgent -- cost tracking and budget enforcement wrapper.

Sits between governance and streaming in the canonical stacking order::

    BaseAgent -> L3GovernedAgent -> MonitoredAgent -> StreamingAgent

Cost tracking sees only approved work (governance already rejected invalid
requests at the layer below).

Uses ``CostTracker`` from ``kaizen.providers.cost`` for thread-safe cost
accumulation with per-model pricing.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from kaizen.core.base_agent import BaseAgent
from kaizen.providers.cost import CostConfig, CostTracker
from kaizen_agents.wrapper_base import WrapperBase

logger = logging.getLogger(__name__)

__all__ = [
    "MonitoredAgent",
    "BudgetExhaustedError",
]


class BudgetExhaustedError(RuntimeError):
    """Raised when the execution budget has been exceeded.

    Attributes:
        budget_usd: The total budget that was set.
        consumed_usd: The amount consumed before the budget was exceeded.
    """

    def __init__(self, budget_usd: float, consumed_usd: float) -> None:
        self.budget_usd = budget_usd
        self.consumed_usd = consumed_usd
        super().__init__(
            f"Budget exhausted: ${consumed_usd:.4f} consumed of "
            f"${budget_usd:.4f} budget."
        )


class MonitoredAgent(WrapperBase):
    """Cost monitoring wrapper -- tracks token usage and enforces budgets.

    Parameters
    ----------
    inner:
        The agent to wrap.
    cost_config:
        Optional ``CostConfig`` with per-model pricing data.
        Defaults to tracking enabled with no pricing (zero-cost).
    budget_usd:
        Optional maximum spend in USD.  When the cumulative cost reaches
        or exceeds this threshold, further calls are rejected with
        ``BudgetExhaustedError``.
    model:
        Model name for cost tracking.  If not provided, uses the inner
        agent's config model or ``"unknown"``.
    """

    def __init__(
        self,
        inner: BaseAgent,
        *,
        cost_config: CostConfig | None = None,
        budget_usd: float | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(inner, **kwargs)
        self._cost_tracker = CostTracker(config=cost_config)
        self._budget_usd = budget_usd
        self._model = model or getattr(inner.config, "model", None) or "unknown"

        # Validate budget is finite (per trust-plane-security rules)
        if budget_usd is not None and not math.isfinite(budget_usd):
            raise ValueError(
                f"budget_usd must be finite, got {budget_usd!r}. "
                f"NaN/Inf values bypass budget checks."
            )

    @property
    def cost_tracker(self) -> CostTracker:
        """The underlying cost tracker."""
        return self._cost_tracker

    @property
    def budget_usd(self) -> float | None:
        """The budget limit in USD, or None if unlimited."""
        return self._budget_usd

    @property
    def total_cost_usd(self) -> float:
        """Current total accumulated cost in USD."""
        return self._cost_tracker.total_cost_usd

    @property
    def budget_remaining_usd(self) -> float | None:
        """Remaining budget in USD, or None if no budget is set."""
        if self._budget_usd is None:
            return None
        remaining = self._budget_usd - self._cost_tracker.total_cost_usd
        return max(0.0, remaining)

    def _check_budget(self) -> None:
        """Raise BudgetExhaustedError if the budget is exceeded."""
        if self._budget_usd is None:
            return
        consumed = self._cost_tracker.total_cost_usd
        if consumed >= self._budget_usd:
            raise BudgetExhaustedError(
                budget_usd=self._budget_usd,
                consumed_usd=consumed,
            )

    def _record_usage(self, result: dict[str, Any]) -> None:
        """Extract token usage from a result dict and record it.

        Looks for usage information in standard locations:
        - ``result["usage"]`` — direct usage dict
        - ``result["prompt_tokens"]`` / ``result["completion_tokens"]`` — flat
        """
        usage = result.get("usage", {})
        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
        else:
            prompt_tokens = result.get("prompt_tokens", 0)
            completion_tokens = result.get("completion_tokens", 0)

        if prompt_tokens or completion_tokens:
            self._cost_tracker.record(
                self._model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

    def run(self, **inputs: Any) -> dict[str, Any]:
        """Execute with budget check and cost tracking (synchronous)."""
        self._check_budget()
        self._inner_called = True
        result = self._inner.run(**inputs)
        self._record_usage(result)
        return result

    async def run_async(self, **inputs: Any) -> dict[str, Any]:
        """Execute with budget check and cost tracking (asynchronous)."""
        self._check_budget()
        self._inner_called = True
        result = await self._inner.run_async(**inputs)
        self._record_usage(result)
        return result
