from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Atomic budget accounting primitive using int microdollars.

1 USD = 1,000,000 microdollars. This module provides a thread-safe,
fail-closed budget tracker with two-phase reserve/record semantics,
saturating arithmetic, and threshold callbacks. Designed to match the
kailash-rs BudgetTracker semantics.

Safe direction: remaining() briefly over-reports between the two atomic
operations in record() (reserved subtracted before committed added).
This is the safe direction -- it may briefly allow a reservation that
would have been denied, but never denies one that should be allowed.
"""

import logging
import math
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, ClassVar, Dict, List, Optional

from eatp.exceptions import TrustError

logger = logging.getLogger(__name__)

__all__ = [
    "BudgetTracker",
    "BudgetSnapshot",
    "BudgetCheckResult",
    "BudgetEvent",
    "BudgetTrackerError",
    "usd_to_microdollars",
    "microdollars_to_usd",
]


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class BudgetTrackerError(TrustError):
    """Error raised by budget tracking operations.

    Inherits from TrustError to integrate with the EATP exception hierarchy.
    Always includes a `.details` dict for structured error context.
    """

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, details=details or {})


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

_VALID_EVENT_TYPES = frozenset({"threshold_80", "threshold_95", "exhausted"})


@dataclass
class BudgetSnapshot:
    """Serializable snapshot of a BudgetTracker's persistent state.

    Contains only ``allocated`` and ``committed``. In-flight reservations
    are intentionally excluded -- they are transient and lost on snapshot.
    Both fields must be non-negative integers.
    """

    allocated: int
    committed: int

    def __post_init__(self) -> None:
        if not isinstance(self.allocated, int) or self.allocated < 0:
            raise BudgetTrackerError(
                f"allocated must be a non-negative integer, got {self.allocated!r}",
                details={"allocated": self.allocated},
            )
        if not isinstance(self.committed, int) or self.committed < 0:
            raise BudgetTrackerError(
                f"committed must be a non-negative integer, got {self.committed!r}",
                details={"committed": self.committed},
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "allocated": self.allocated,
            "committed": self.committed,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BudgetSnapshot:
        """Deserialize from a plain dict.

        Raises:
            BudgetTrackerError: If required keys are missing.
        """
        if "allocated" not in data:
            raise BudgetTrackerError(
                "Missing required key 'allocated' in snapshot dict",
                details={"keys_present": list(data.keys())},
            )
        if "committed" not in data:
            raise BudgetTrackerError(
                "Missing required key 'committed' in snapshot dict",
                details={"keys_present": list(data.keys())},
            )
        return cls(
            allocated=int(data["allocated"]),
            committed=int(data["committed"]),
        )


@dataclass
class BudgetCheckResult:
    """Result of a non-mutating budget check.

    Tells the caller whether an estimated spend would fit within the
    remaining budget without actually reserving anything.
    """

    allowed: bool
    remaining_microdollars: int
    allocated_microdollars: int
    committed_microdollars: int
    reserved_microdollars: int

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "allowed": self.allowed,
            "remaining_microdollars": self.remaining_microdollars,
            "allocated_microdollars": self.allocated_microdollars,
            "committed_microdollars": self.committed_microdollars,
            "reserved_microdollars": self.reserved_microdollars,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BudgetCheckResult:
        """Deserialize from a plain dict.

        Raises:
            BudgetTrackerError: If required keys are missing.
        """
        required = {
            "allowed",
            "remaining_microdollars",
            "allocated_microdollars",
            "committed_microdollars",
            "reserved_microdollars",
        }
        missing = required - set(data.keys())
        if missing:
            raise BudgetTrackerError(
                f"Missing required keys in BudgetCheckResult dict: {missing}",
                details={"missing_keys": sorted(missing)},
            )
        return cls(
            allowed=bool(data["allowed"]),
            remaining_microdollars=int(data["remaining_microdollars"]),
            allocated_microdollars=int(data["allocated_microdollars"]),
            committed_microdollars=int(data["committed_microdollars"]),
            reserved_microdollars=int(data["reserved_microdollars"]),
        )


@dataclass
class BudgetEvent:
    """Event emitted when a budget threshold is crossed.

    ``event_type`` is one of ``"threshold_80"``, ``"threshold_95"``,
    or ``"exhausted"``.
    """

    event_type: str
    remaining_microdollars: int
    allocated_microdollars: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.event_type not in _VALID_EVENT_TYPES:
            raise BudgetTrackerError(
                f"Invalid event_type {self.event_type!r}; expected one of {sorted(_VALID_EVENT_TYPES)}",
                details={"event_type": self.event_type},
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict. Datetime is ISO-8601 string."""
        return {
            "event_type": self.event_type,
            "remaining_microdollars": self.remaining_microdollars,
            "allocated_microdollars": self.allocated_microdollars,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BudgetEvent:
        """Deserialize from a plain dict.

        Raises:
            BudgetTrackerError: If required keys are missing or timestamp is unparseable.
        """
        required = {
            "event_type",
            "remaining_microdollars",
            "allocated_microdollars",
            "timestamp",
        }
        missing = required - set(data.keys())
        if missing:
            raise BudgetTrackerError(
                f"Missing required keys in BudgetEvent dict: {missing}",
                details={"missing_keys": sorted(missing)},
            )
        ts_raw = data["timestamp"]
        if isinstance(ts_raw, datetime):
            ts = ts_raw
        elif isinstance(ts_raw, str):
            ts = datetime.fromisoformat(ts_raw)
        else:
            raise BudgetTrackerError(
                f"Cannot parse timestamp: {ts_raw!r}",
                details={"timestamp_raw": str(ts_raw)},
            )
        return cls(
            event_type=data["event_type"],
            remaining_microdollars=int(data["remaining_microdollars"]),
            allocated_microdollars=int(data["allocated_microdollars"]),
            timestamp=ts,
        )


# ---------------------------------------------------------------------------
# BudgetTracker
# ---------------------------------------------------------------------------

# Maximum number of entries in the transaction log (bounded collection per EATP rules)
_MAX_TRANSACTION_LOG: int = 10_000


class BudgetTracker:
    """Thread-safe atomic budget accounting with two-phase reserve/record.

    Uses ``int`` microdollars (1 USD = 1,000,000 microdollars) to avoid
    floating-point precision issues. All operations are guarded by a
    ``threading.Lock`` and use saturating arithmetic -- remaining balance
    never goes negative.

    Lifecycle::

        # 1. Reserve before the work
        if tracker.reserve(estimated_cost):
            # 2. Do work ...
            # 3. Record actual cost (may differ from estimated)
            tracker.record(reserved_microdollars=estimated_cost,
                           actual_microdollars=real_cost)

    Attributes:
        _allocated: Immutable total budget in microdollars.
        _reserved: Sum of currently outstanding reservations.
        _committed: Sum of finalized (recorded) spend.
        _lock: Guards all mutable state.
        _transaction_log: Bounded deque of transaction descriptions.
        _threshold_callbacks: Registered callbacks for threshold events.
        _record_callbacks: Registered callbacks fired after every record().
    """

    def __init__(
        self,
        allocated_microdollars: int,
        *,
        store: Optional[Any] = None,
        tracker_id: Optional[str] = None,
    ) -> None:
        """Create a new BudgetTracker with the given total budget.

        Args:
            allocated_microdollars: Total budget in microdollars. Must be
                a non-negative integer.
            store: Optional :class:`BudgetStore` for persistence. When
                provided, the tracker auto-saves after each ``record()``.
                If the store already contains a snapshot for ``tracker_id``,
                committed state is restored automatically (reservations are
                lost -- safe direction).
            tracker_id: Required when ``store`` is provided. Identifier
                used as the key in the persistent store.

        Raises:
            BudgetTrackerError: If ``allocated_microdollars`` is negative
                or not an integer, or if ``store`` is given without
                ``tracker_id``.
        """
        if not isinstance(allocated_microdollars, int):
            raise BudgetTrackerError(
                f"allocated_microdollars must be an integer, got {type(allocated_microdollars).__name__}",
                details={"allocated_microdollars": str(allocated_microdollars)},
            )
        if allocated_microdollars < 0:
            raise BudgetTrackerError(
                f"allocated_microdollars must be non-negative, got {allocated_microdollars}",
                details={"allocated_microdollars": allocated_microdollars},
            )
        if store is not None and not tracker_id:
            raise BudgetTrackerError(
                "tracker_id is required when store is provided",
                details={"store": type(store).__name__},
            )

        self._allocated: int = allocated_microdollars
        self._reserved: int = 0
        self._committed: int = 0
        self._lock: threading.Lock = threading.Lock()
        self._transaction_log: deque[Dict[str, Any]] = deque(
            maxlen=_MAX_TRANSACTION_LOG
        )
        self._threshold_callbacks: List[Callable[[BudgetEvent], None]] = []
        self._record_callbacks: List[Callable[[], None]] = []
        self._store = store
        self._tracker_id = tracker_id

        # Track which thresholds have already fired so we don't re-fire
        self._fired_thresholds: set[str] = set()

        # Auto-restore from store if available
        if store is not None and tracker_id is not None:
            existing = store.get_snapshot(tracker_id)
            if existing is not None:
                self._committed = existing.committed
                logger.debug(
                    "BudgetTracker restored from store: tracker_id=%s, committed=%d",
                    tracker_id,
                    existing.committed,
                )

        logger.debug(
            "BudgetTracker created: allocated=%d microdollars (%.2f USD)",
            allocated_microdollars,
            microdollars_to_usd(allocated_microdollars),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reserve(self, microdollars: int) -> bool:
        """Attempt to reserve ``microdollars`` from the remaining budget.

        Thread-safe. Returns ``False`` (fail-closed) if:
        - ``microdollars`` is negative
        - There is insufficient remaining budget
        - Any unexpected exception occurs

        Args:
            microdollars: Amount to reserve. Must be >= 0.

        Returns:
            True if the reservation succeeded, False otherwise.
        """
        # Fail-closed on invalid input
        if not isinstance(microdollars, int) or microdollars < 0:
            logger.warning(
                "reserve() called with invalid amount %r -- fail-closed, returning False",
                microdollars,
            )
            return False

        # Zero-amount reservation always succeeds
        if microdollars == 0:
            return True

        try:
            with self._lock:
                available = self._allocated - self._committed - self._reserved
                if available < microdollars:
                    logger.debug(
                        "reserve(%d) denied: available=%d (allocated=%d, committed=%d, reserved=%d)",
                        microdollars,
                        available,
                        self._allocated,
                        self._committed,
                        self._reserved,
                    )
                    self._transaction_log.append(
                        {
                            "op": "reserve",
                            "amount": microdollars,
                            "success": False,
                            "available": available,
                            "ts": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    return False

                self._reserved += microdollars
                self._transaction_log.append(
                    {
                        "op": "reserve",
                        "amount": microdollars,
                        "success": True,
                        "reserved_after": self._reserved,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }
                )
                logger.debug(
                    "reserve(%d) succeeded: reserved_total=%d, remaining=%d",
                    microdollars,
                    self._reserved,
                    self._allocated - self._committed - self._reserved,
                )
                return True
        except Exception:
            # Fail-closed: any unexpected error -> deny
            logger.exception(
                "Unexpected error in reserve() -- fail-closed, returning False"
            )
            return False

    def record(self, reserved_microdollars: int, actual_microdollars: int) -> None:
        """Finalize a reservation: release the reserved amount and commit the actual.

        Uses saturating arithmetic:
        - ``_reserved`` is decreased by ``reserved_microdollars`` but never below 0.
        - ``_committed`` is increased by ``actual_microdollars`` but never above ``_allocated``
          (although it *can* exceed allocated to track real overspend -- we only saturate
          ``_reserved`` to prevent underflow).

        After updating committed, threshold callbacks are checked and fired
        if applicable.

        Args:
            reserved_microdollars: The amount that was previously reserved.
                Must be a non-negative integer.
            actual_microdollars: The actual cost that was incurred.
                Must be a non-negative integer.

        Raises:
            BudgetTrackerError: If either argument is not a non-negative integer.
        """
        # H2: Validate inputs before acquiring the lock
        if not isinstance(reserved_microdollars, int) or reserved_microdollars < 0:
            raise BudgetTrackerError(
                f"reserved_microdollars must be a non-negative integer, got {reserved_microdollars!r}",
                details={"reserved_microdollars": str(reserved_microdollars)},
            )
        if not isinstance(actual_microdollars, int) or actual_microdollars < 0:
            raise BudgetTrackerError(
                f"actual_microdollars must be a non-negative integer, got {actual_microdollars!r}",
                details={"actual_microdollars": str(actual_microdollars)},
            )

        events_to_fire: List[BudgetEvent] = []
        snapshot_to_save: Optional[BudgetSnapshot] = None

        with self._lock:
            # Saturating subtract from reserved
            self._reserved = max(0, self._reserved - reserved_microdollars)

            # Add actual to committed (no upper-bound saturation -- track real spend)
            self._committed += actual_microdollars

            self._transaction_log.append(
                {
                    "op": "record",
                    "reserved_released": reserved_microdollars,
                    "actual_committed": actual_microdollars,
                    "committed_after": self._committed,
                    "reserved_after": self._reserved,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            )

            logger.debug(
                "record(reserved=%d, actual=%d): committed=%d, reserved=%d, remaining=%d",
                reserved_microdollars,
                actual_microdollars,
                self._committed,
                self._reserved,
                max(0, self._allocated - self._committed - self._reserved),
            )

            # C1: Collect threshold events inside the lock but do NOT fire callbacks here
            events_to_fire = self._collect_threshold_events()

            # C3: Capture a consistent snapshot while still holding the lock
            if self._store is not None:
                snapshot_to_save = BudgetSnapshot(
                    allocated=self._allocated,
                    committed=self._committed,
                )

        # C1: Fire callbacks OUTSIDE the lock to prevent deadlock when callbacks
        # re-enter remaining_microdollars(), check(), or snapshot().
        for event in events_to_fire:
            for cb in self._threshold_callbacks:
                try:
                    cb(event)
                except Exception:
                    logger.exception(
                        "Threshold callback raised exception for event %s -- ignoring",
                        event.event_type,
                    )

        # C3: Save the snapshot that was captured consistently inside the lock.
        if snapshot_to_save is not None and self._tracker_id is not None:
            try:
                self._store.save_snapshot(self._tracker_id, snapshot_to_save)
            except Exception:
                logger.exception(
                    "Failed to auto-save budget snapshot for %s -- state is in memory only",
                    self._tracker_id,
                )

        # H1: Fire record callbacks OUTSIDE the lock after every record().
        # These enable composable integrations (e.g. posture-budget) without
        # monkey-patching.
        for cb in self._record_callbacks:
            try:
                cb()
            except Exception:
                logger.exception("Record callback raised exception -- ignoring")

    def remaining_microdollars(self) -> int:
        """Return the remaining available budget in microdollars.

        Uses saturating arithmetic: result is always >= 0.

        Returns:
            Non-negative remaining budget.
        """
        with self._lock:
            return max(0, self._allocated - self._committed - self._reserved)

    def check(self, estimated_microdollars: int) -> BudgetCheckResult:
        """Non-mutating check: would ``estimated_microdollars`` fit?

        Does NOT modify any internal state. Safe to call from read paths.

        Args:
            estimated_microdollars: Proposed spend to evaluate.

        Returns:
            BudgetCheckResult indicating whether the spend would be allowed.
        """
        with self._lock:
            remaining = max(0, self._allocated - self._committed - self._reserved)
            allowed = remaining >= estimated_microdollars
            return BudgetCheckResult(
                allowed=allowed,
                remaining_microdollars=remaining,
                allocated_microdollars=self._allocated,
                committed_microdollars=self._committed,
                reserved_microdollars=self._reserved,
            )

    def snapshot(self) -> BudgetSnapshot:
        """Capture a serializable snapshot of persistent state.

        The snapshot contains ``allocated`` and ``committed`` only.
        In-flight reservations are intentionally excluded -- they are
        transient and would be meaningless after a process restart.

        Returns:
            BudgetSnapshot with allocated and committed values.
        """
        with self._lock:
            return BudgetSnapshot(
                allocated=self._allocated,
                committed=self._committed,
            )

    @classmethod
    def from_snapshot(cls, snapshot: BudgetSnapshot) -> BudgetTracker:
        """Restore a BudgetTracker from a serialized snapshot.

        The restored tracker has zero reservations, matching the
        kailash-rs semantics where reservations are ephemeral.

        Args:
            snapshot: Previously captured BudgetSnapshot.

        Returns:
            New BudgetTracker initialized from the snapshot.
        """
        tracker = cls(allocated_microdollars=snapshot.allocated)
        # Set committed directly (bypass reserve/record flow)
        tracker._committed = snapshot.committed
        logger.debug(
            "BudgetTracker restored from snapshot: allocated=%d, committed=%d",
            snapshot.allocated,
            snapshot.committed,
        )
        return tracker

    def on_threshold(self, callback: Callable[[BudgetEvent], None]) -> None:
        """Register a callback to be invoked when budget thresholds are crossed.

        Callbacks are invoked for:
        - ``"threshold_80"``: committed >= 80% of allocated
        - ``"threshold_95"``: committed >= 95% of allocated
        - ``"exhausted"``: committed >= 100% of allocated

        Each threshold fires at most once per BudgetTracker lifetime.
        If a callback raises an exception, it is logged and the remaining
        callbacks still execute (fail-safe).

        Args:
            callback: Function accepting a BudgetEvent.
        """
        self._threshold_callbacks.append(callback)

    def on_record(self, callback: Callable[[], None]) -> None:
        """Register a callback to be invoked after every ``record()`` call.

        Unlike ``on_threshold()`` which fires only at specific utilization
        percentages, ``on_record()`` callbacks fire after *every* successful
        ``record()`` invocation.  This is useful for integrations that need
        to check custom utilization thresholds at arbitrary percentages.

        Callbacks are invoked outside the lock, after threshold callbacks.
        If a callback raises an exception, it is logged and the remaining
        callbacks still execute (fail-safe).

        Args:
            callback: Zero-argument callable invoked after each record().
        """
        self._record_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _collect_threshold_events(self) -> List[BudgetEvent]:
        """Collect threshold events for any newly-crossed budget thresholds.

        Called under lock after record(). Each threshold fires at most once.
        Returns a list of BudgetEvent objects to be fired by the caller
        OUTSIDE the lock, to avoid deadlock when callbacks re-enter the
        tracker (e.g. remaining_microdollars(), check(), snapshot()).

        Returns:
            List of BudgetEvent objects for newly-crossed thresholds (may be empty).
        """
        if self._allocated == 0:
            return []

        # M1: Use integer arithmetic for threshold comparisons to avoid
        # floating-point precision issues.  We multiply committed by 100
        # and compare against allocated * threshold_pct.  Float is used
        # only for the log message display.
        committed_x100 = self._committed * 100

        thresholds_to_fire: List[str] = []

        if (
            committed_x100 >= self._allocated * 100
            and "exhausted" not in self._fired_thresholds
        ):
            thresholds_to_fire.append("exhausted")
            self._fired_thresholds.add("exhausted")

        if (
            committed_x100 >= self._allocated * 95
            and "threshold_95" not in self._fired_thresholds
        ):
            thresholds_to_fire.append("threshold_95")
            self._fired_thresholds.add("threshold_95")

        if (
            committed_x100 >= self._allocated * 80
            and "threshold_80" not in self._fired_thresholds
        ):
            thresholds_to_fire.append("threshold_80")
            self._fired_thresholds.add("threshold_80")

        events: List[BudgetEvent] = []
        remaining = max(0, self._allocated - self._committed - self._reserved)
        # Float only for logging display
        utilization_pct_display = (self._committed / self._allocated) * 100
        for event_type in thresholds_to_fire:
            event = BudgetEvent(
                event_type=event_type,
                remaining_microdollars=remaining,
                allocated_microdollars=self._allocated,
            )
            logger.info(
                "Budget threshold crossed: %s (committed=%d, allocated=%d, %.1f%%)",
                event_type,
                self._committed,
                self._allocated,
                utilization_pct_display,
            )
            events.append(event)
        return events


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def usd_to_microdollars(amount: float) -> int:
    """Convert a USD amount to integer microdollars.

    1 USD = 1,000,000 microdollars.

    Args:
        amount: USD amount (e.g. 1.50 for $1.50).

    Returns:
        Integer microdollars.
    """
    if not math.isfinite(amount):
        raise BudgetTrackerError(
            f"USD amount must be finite, got {amount!r}",
            details={"amount": str(amount)},
        )
    return int(round(amount * 1_000_000))


def microdollars_to_usd(amount: int) -> float:
    """Convert integer microdollars to a USD float.

    Args:
        amount: Microdollars (e.g. 1_500_000 for $1.50).

    Returns:
        USD as a float.
    """
    return amount / 1_000_000
