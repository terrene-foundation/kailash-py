# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Cost tracking for PactEngine -- budget management and consumption history.

CostTracker wraps budget allocation, consumption recording, and utilization
queries into a simple progressive-disclosure API. Thread-safe per
pact-governance.md rule 8. NaN/Inf validation follows pact-governance.md
rule 6 and trust-plane-security.md rule 3.
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["CostTracker"]


class CostTracker:
    """Tracks cost consumption against an optional budget. Thread-safe.

    Progressive disclosure:
    - Layer 1: tracker = CostTracker(budget_usd=50.0); tracker.record(1.5)
    - Layer 2: tracker.spent, tracker.remaining, tracker.utilization
    - Layer 3: tracker.history, tracker.cost_model

    Args:
        budget_usd: Optional maximum budget in USD. None means unlimited.
        cost_model: Optional CostModel for computing LLM token costs.

    Raises:
        ValueError: If budget_usd is NaN, Inf, or negative.
    """

    def __init__(
        self,
        budget_usd: float | None = None,
        cost_model: Any | None = None,
    ) -> None:
        if budget_usd is not None:
            if not math.isfinite(budget_usd):
                raise ValueError(f"budget_usd must be finite, got {budget_usd!r}")
            if budget_usd < 0:
                raise ValueError(
                    f"budget_usd must be finite and non-negative, got {budget_usd}"
                )

        self._budget = budget_usd
        self._spent = 0.0
        self._cost_model = cost_model
        self._history: deque[dict[str, Any]] = deque(maxlen=10000)
        self._lock = threading.Lock()

    def record(
        self,
        amount: float,
        description: str = "",
        *,
        envelope_id: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        """Record a cost against the budget. Thread-safe.

        Args:
            amount: Cost in USD (must be finite and non-negative).
            description: Human-readable description of what incurred the cost.
            envelope_id: Optional governance envelope ID for per-envelope
                rollups (see future ``consumption_report(envelope_id=...)``).
            agent_id: Optional agent or D/T/R role address for per-agent
                rollups. In PACT usage this is typically the submitting
                role's address (e.g. ``"D1-R1-D2-R2"``).

        Raises:
            ValueError: If amount is NaN, Inf, or negative.
        """
        if not math.isfinite(amount):
            raise ValueError(f"Cost amount must be finite, got {amount!r}")
        if amount < 0:
            raise ValueError(
                f"Cost amount must be finite and non-negative, got {amount}"
            )

        with self._lock:
            self._spent += amount
            self._history.append(
                {
                    "amount": amount,
                    "description": description,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "cumulative": self._spent,
                    "envelope_id": envelope_id,
                    "agent_id": agent_id,
                }
            )

        logger.debug(
            "CostTracker: recorded $%.4f (%s) envelope=%s agent=%s total=$%.4f",
            amount,
            description or "unnamed",
            envelope_id or "-",
            agent_id or "-",
            self._spent,
        )

    @property
    def spent(self) -> float:
        """Total cost consumed so far in USD."""
        with self._lock:
            return self._spent

    @property
    def remaining(self) -> float | None:
        """Remaining budget in USD, or None if no budget is configured."""
        if self._budget is None:
            return None
        with self._lock:
            return max(0.0, self._budget - self._spent)

    @property
    def utilization(self) -> float | None:
        """Budget utilization as a fraction (0.0 to 1.0+), or None if no budget."""
        if self._budget is None:
            return None
        with self._lock:
            if self._budget == 0.0:
                return 1.0 if self._spent > 0 else 0.0
            return self._spent / self._budget

    @property
    def history(self) -> list[dict[str, Any]]:
        """List of all cost records (bounded to most recent 10000)."""
        with self._lock:
            return list(self._history)

    @property
    def cost_model(self) -> Any | None:
        """The LLM token cost model, or None if not configured."""
        return self._cost_model
