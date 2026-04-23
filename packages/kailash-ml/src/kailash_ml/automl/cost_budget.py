# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""CostTracker -- microdollar-granularity budget accounting for AutoML trials.

W27a delivers the interface and a deterministic in-memory implementation.
W32 32a replaces the in-memory backing store with a durable
(ConnectionManager-backed) persister that survives process restart and
participates in the shared tenant-scoped audit chain. Until then, the
in-memory tracker is authoritative for a single-process AutoML run.

Contract guarantees that hold across both W27a and W32 32a:

- **Microdollar integers.** All monetary values flow as ``int``
  microdollars (1 USD == 1_000_000 microdollars). Floating-point USD is
  rejected at the API boundary per ``rules/zero-tolerance.md`` Rule 2 —
  silent rounding drift across strategies is BLOCKED.
- **Monotonic cumulative spend.** ``record(...)`` only adds; there is
  no rollback primitive in the public surface. Mis-recorded trials are
  corrected via a new audit row with a negative-cost compensating entry
  (same pattern as PACT audit correction; see
  ``specs/pact-ml-integration.md`` §5).
- **Budget check is race-free under a single event loop.** Callers MAY
  share a single ``CostTracker`` across concurrent trials within one
  AutoML run; the check+record pair is atomic under ``asyncio.Lock``.
  Cross-process sharing is deferred to W32 32a.
- **Non-finite budgets are rejected.** ``math.isfinite`` on the USD
  ceiling at construction prevents NaN/Inf bypass (see
  ``rules/zero-tolerance.md`` Rule 2, ``specs/ml-automl.md`` §2.3 MUST 2).

See :class:`BudgetExceeded` for the typed error raised when a proposed
spend would take cumulative cost over the configured ceiling.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = [
    "CostTracker",
    "CostRecord",
    "BudgetExceeded",
    "usd_to_microdollars",
    "microdollars_to_usd",
]


_MICRO_PER_USD: int = 1_000_000


def usd_to_microdollars(amount_usd: float) -> int:
    """Convert an explicit USD amount to integer microdollars.

    ``math.isfinite`` guard rejects NaN / Inf so a misconfigured budget
    cannot bypass downstream comparisons.
    """
    if not isinstance(amount_usd, (int, float)):
        raise TypeError(f"amount_usd must be numeric, got {type(amount_usd).__name__}")
    if not math.isfinite(float(amount_usd)):
        raise ValueError(f"amount_usd must be finite, got {amount_usd!r}")
    if amount_usd < 0:
        raise ValueError(f"amount_usd must be non-negative, got {amount_usd!r}")
    return int(round(float(amount_usd) * _MICRO_PER_USD))


def microdollars_to_usd(microdollars: int) -> float:
    """Convert integer microdollars back to USD (presentation only)."""
    return microdollars / _MICRO_PER_USD


class BudgetExceeded(Exception):
    """Proposed spend would push cumulative cost over the configured ceiling.

    Carries the three numbers the caller needs to render an actionable
    error message: remaining budget before the call, the proposed cost,
    and the configured ceiling. Microdollars throughout.
    """

    def __init__(
        self,
        *,
        proposed_microdollars: int,
        remaining_microdollars: int,
        ceiling_microdollars: int,
    ) -> None:
        self.proposed_microdollars = proposed_microdollars
        self.remaining_microdollars = remaining_microdollars
        self.ceiling_microdollars = ceiling_microdollars
        super().__init__(
            f"budget exceeded: proposed ${microdollars_to_usd(proposed_microdollars):.6f}"
            f" remaining ${microdollars_to_usd(remaining_microdollars):.6f}"
            f" ceiling ${microdollars_to_usd(ceiling_microdollars):.6f}"
        )


@dataclass(frozen=True)
class CostRecord:
    """One recorded charge against the budget.

    ``kind`` is a free-form tag ("trial" / "llm_suggestion" /
    "baseline") that the downstream audit pipeline uses to split costs
    across the agent vs baseline streams (per
    ``specs/ml-automl.md`` §8.3 MUST 1 — baseline-counterfactual).
    """

    timestamp: float
    microdollars: int
    kind: str
    trial_number: Optional[int] = None
    note: str = ""


@dataclass
class CostTracker:
    """In-memory microdollar cost tracker.

    Construct with a USD ceiling. Every :meth:`record` call adds to
    cumulative spend under an ``asyncio.Lock``; :meth:`check_would_exceed`
    is race-free against a concurrent record only when both are awaited
    from the same event loop.

    W32 32a replaces the ``_ledger`` and ``_cumulative_microdollars``
    fields with a ConnectionManager-backed persister; the public surface
    above the lock is stable.

    Attributes:
        ceiling_microdollars: The hard cap in microdollars. Set via
            :meth:`from_usd` or by passing ``ceiling_microdollars``
            directly. ``0`` disables the budget (explicit opt-out).
        tenant_id: Tenant scope per ``rules/tenant-isolation.md`` MUST
            Rule 5. Every recorded row carries the tenant; W32 32a adds
            the database persistence.
        max_ledger_entries: Bounded audit trail size (default 10_000) per
            the "bounded collections" guidance in the ml-specialist
            agent card. Older entries fall off on overflow.
    """

    ceiling_microdollars: int
    tenant_id: str
    max_ledger_entries: int = 10_000
    # Private mutable state — do not read from outside the class
    _cumulative_microdollars: int = field(default=0)
    _ledger: deque[CostRecord] = field(default_factory=deque)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        if not isinstance(self.ceiling_microdollars, int):
            raise TypeError(
                "ceiling_microdollars must be int; "
                "use CostTracker.from_usd(amount_usd=...) for USD input"
            )
        if self.ceiling_microdollars < 0:
            raise ValueError(
                f"ceiling_microdollars must be non-negative, got {self.ceiling_microdollars!r}"
            )
        if not isinstance(self.tenant_id, str) or not self.tenant_id:
            raise ValueError("tenant_id must be a non-empty string")
        if self.max_ledger_entries <= 0:
            raise ValueError("max_ledger_entries must be positive")
        # Resize the ledger deque to enforce the bounded-collection invariant
        self._ledger = deque(self._ledger, maxlen=self.max_ledger_entries)

    @classmethod
    def from_usd(
        cls,
        *,
        ceiling_usd: float,
        tenant_id: str,
        max_ledger_entries: int = 10_000,
    ) -> "CostTracker":
        """Construct from an explicit USD ceiling."""
        return cls(
            ceiling_microdollars=usd_to_microdollars(ceiling_usd),
            tenant_id=tenant_id,
            max_ledger_entries=max_ledger_entries,
        )

    @property
    def cumulative_microdollars(self) -> int:
        """Monotonically-increasing cumulative spend in microdollars."""
        return self._cumulative_microdollars

    @property
    def remaining_microdollars(self) -> int:
        """Budget remaining — may be 0 if ceiling is 0 or already spent."""
        if self.ceiling_microdollars == 0:
            # Budget is disabled; treat remaining as unlimited-sentinel via
            # a large positive integer. Downstream comparisons using
            # remaining < proposed still hold for any finite proposed.
            return 2**62  # large but not Inf so int arithmetic is safe
        return max(0, self.ceiling_microdollars - self._cumulative_microdollars)

    def check_would_exceed(self, proposed_microdollars: int) -> bool:
        """Return True if adding proposed spend would exceed the ceiling.

        Pure read; no lock acquired. Callers that need atomic check+record
        MUST use :meth:`record` which performs both under the lock.
        """
        if self.ceiling_microdollars == 0:
            return False
        return (
            self._cumulative_microdollars + proposed_microdollars
        ) > self.ceiling_microdollars

    async def record(
        self,
        *,
        microdollars: int,
        kind: str,
        trial_number: Optional[int] = None,
        note: str = "",
    ) -> CostRecord:
        """Atomically check the budget, raise on overflow, else record.

        Raises :class:`BudgetExceeded` with the three key numbers if the
        proposed spend would push cumulative cost over the ceiling.
        Compensating negative-cost entries (for reversal) are allowed
        via ``microdollars < 0`` and are NOT budget-checked (they can
        only reduce cumulative spend).
        """
        if not isinstance(microdollars, int):
            raise TypeError(
                f"microdollars must be int (not float USD), got {type(microdollars).__name__}"
            )
        if not kind:
            raise ValueError("kind must be a non-empty string")
        async with self._lock:
            if microdollars > 0 and self.check_would_exceed(microdollars):
                remaining = self.remaining_microdollars
                logger.warning(
                    "automl.cost_tracker.budget_exceeded",
                    extra={
                        "tenant_id": self.tenant_id,
                        "kind": kind,
                        "trial_number": trial_number,
                        "proposed_microdollars": microdollars,
                        "remaining_microdollars": remaining,
                        "ceiling_microdollars": self.ceiling_microdollars,
                    },
                )
                raise BudgetExceeded(
                    proposed_microdollars=microdollars,
                    remaining_microdollars=remaining,
                    ceiling_microdollars=self.ceiling_microdollars,
                )
            record = CostRecord(
                timestamp=time.time(),
                microdollars=microdollars,
                kind=kind,
                trial_number=trial_number,
                note=note,
            )
            self._cumulative_microdollars += microdollars
            # Never let cumulative spend go negative via compensation
            self._cumulative_microdollars = max(0, self._cumulative_microdollars)
            self._ledger.append(record)
            logger.info(
                "automl.cost_tracker.record",
                extra={
                    "tenant_id": self.tenant_id,
                    "kind": kind,
                    "trial_number": trial_number,
                    "microdollars": microdollars,
                    "cumulative_microdollars": self._cumulative_microdollars,
                    "remaining_microdollars": self.remaining_microdollars,
                },
            )
            return record

    def ledger(self) -> list[CostRecord]:
        """Return a snapshot of the audit trail (bounded by ``max_ledger_entries``)."""
        return list(self._ledger)
