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
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # type-only forward reference
    from pact.governance.results import ConsumptionReport

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
                role's address (e.g. ``"D1-R1-D2-R2"``). The forthcoming
                ``consumption_report(agent_id=...)`` filter expects the
                same convention — a D/T/R role string, NOT a kaizen-agents
                agent UUID. Consumers filtering by UUID will get zero rows
                from a PactEngine-populated tracker.

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

        # DEBUG-level per observability.md Rule 8: envelope_id and agent_id
        # are operational identifiers (envelope UUIDs / D/T/R role addresses).
        # Operators SHOULD NOT encode human names or tenant PII into role
        # address segments — if that convention is ever broken, this line
        # must re-verify that it stays at DEBUG and never upgrades to WARN.
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

    def consumption_report(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        envelope_id: str | None = None,
        agent_id: str | None = None,
    ) -> "ConsumptionReport":
        """Aggregate a frozen consumption report from ``self._history``.

        Acquires ``self._lock`` (PACT MUST Rule 8) so the aggregation is
        consistent against concurrent ``record()`` calls. Totals are in
        **microdollars** (USD * 1_000_000) for integer math safety — a
        financial rollup that accumulates float USD amounts over
        thousands of entries loses precision; integer microdollars do
        not. The returned :class:`ConsumptionReport` exposes ``total_usd``
        as a convenience float.

        PR#7 of issue #567 — replaces the rejected MLFP
        ``GovernanceDiagnostics.consumption_report`` facade with a
        first-class method on the existing ``CostTracker``.

        Args:
            since: Only include entries whose ``timestamp`` >= this UTC
                datetime (inclusive lower bound).
            until: Only include entries whose ``timestamp`` <= this UTC
                datetime (inclusive upper bound).
            envelope_id: Only include entries whose ``envelope_id`` matches
                (exact string match). ``None`` means "no envelope filter";
                ``""`` means "entries that recorded no envelope".
            agent_id: Only include entries whose ``agent_id`` matches
                (exact string match). Same None / empty-string semantics
                as ``envelope_id``. Note: in PACT usage, ``agent_id`` is
                typically a D/T/R role address; consumers filtering by
                kaizen-agents UUID will get zero rows.

        Returns:
            A frozen :class:`ConsumptionReport`.
        """
        from pact.governance.results import ConsumptionReport

        def _to_micro(value: float) -> int:
            # Banker's rounding via round() is safe because record() already
            # rejects NaN / Inf / negatives. Convert to microdollars only
            # after filtering so per-entry rounding error stays within 1 µ$.
            return int(round(value * 1_000_000))

        total_micro = 0
        entries = 0
        per_envelope: dict[str, int] = {}
        per_agent: dict[str, int] = {}

        with self._lock:
            # Iterate over a snapshot of self._history so the lock window
            # stays short. deque supports direct iteration inside `with`.
            for record in self._history:
                ts_str = record.get("timestamp")
                if isinstance(ts_str, str):
                    try:
                        ts = datetime.fromisoformat(ts_str)
                    except ValueError:  # pragma: no cover — defense-in-depth
                        continue
                else:
                    continue
                if since is not None and ts < since:
                    continue
                if until is not None and ts > until:
                    continue
                rec_env = record.get("envelope_id")
                rec_agent = record.get("agent_id")
                if envelope_id is not None and rec_env != envelope_id:
                    continue
                if agent_id is not None and rec_agent != agent_id:
                    continue

                amount = record.get("amount", 0.0)
                if not isinstance(amount, (int, float)) or not math.isfinite(
                    float(amount)
                ):
                    # record() rejects these already — defense-in-depth skip.
                    continue
                micro = _to_micro(float(amount))
                total_micro += micro
                entries += 1
                env_key = rec_env if isinstance(rec_env, str) else ""
                agent_key = rec_agent if isinstance(rec_agent, str) else ""
                per_envelope[env_key] = per_envelope.get(env_key, 0) + micro
                per_agent[agent_key] = per_agent.get(agent_key, 0) + micro

        return ConsumptionReport(
            total_microdollars=total_micro,
            entries=entries,
            per_envelope=per_envelope,
            per_agent=per_agent,
            since=since,
            until=until,
        )
