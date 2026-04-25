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
from typing import Any, Callable, ClassVar, Dict, List, Optional, Tuple

from kailash.trust.exceptions import TrustError

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

_VALID_EVENT_TYPES = frozenset(
    {"threshold_80", "threshold_95", "exhausted", "custom_threshold"}
)


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
    ``"exhausted"`` (fired by :meth:`BudgetTracker.on_threshold` callbacks
    at the hardcoded 80%/95%/100% utilization marks), or
    ``"custom_threshold"`` (fired by callbacks registered via
    :meth:`BudgetTracker.set_threshold_callback` at a caller-supplied
    fraction of allocated budget).

    For ``"custom_threshold"`` events, ``threshold_pct`` is set to the
    fractional threshold (e.g. ``0.80`` for 80%). For the hardcoded event
    types, ``threshold_pct`` is set to the corresponding fraction
    (``0.80`` / ``0.95`` / ``1.00``) for cross-callback uniformity.

    ``committed_microdollars`` and ``reserved_microdollars`` capture the
    point-in-time values at the moment the threshold was observed, so
    callbacks can correlate the event with budget state without re-locking.
    """

    event_type: str
    remaining_microdollars: int
    allocated_microdollars: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    threshold_pct: Optional[float] = None
    committed_microdollars: Optional[int] = None
    reserved_microdollars: Optional[int] = None

    def __post_init__(self) -> None:
        if self.event_type not in _VALID_EVENT_TYPES:
            raise BudgetTrackerError(
                f"Invalid event_type {self.event_type!r}; expected one of {sorted(_VALID_EVENT_TYPES)}",
                details={"event_type": self.event_type},
            )
        if self.threshold_pct is not None and not math.isfinite(self.threshold_pct):
            raise BudgetTrackerError(
                f"threshold_pct must be finite, got {self.threshold_pct!r}",
                details={"threshold_pct": str(self.threshold_pct)},
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict. Datetime is ISO-8601 string."""
        out: Dict[str, Any] = {
            "event_type": self.event_type,
            "remaining_microdollars": self.remaining_microdollars,
            "allocated_microdollars": self.allocated_microdollars,
            "timestamp": self.timestamp.isoformat(),
        }
        if self.threshold_pct is not None:
            out["threshold_pct"] = self.threshold_pct
        if self.committed_microdollars is not None:
            out["committed_microdollars"] = self.committed_microdollars
        if self.reserved_microdollars is not None:
            out["reserved_microdollars"] = self.reserved_microdollars
        return out

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
        threshold_pct_raw = data.get("threshold_pct")
        committed_raw = data.get("committed_microdollars")
        reserved_raw = data.get("reserved_microdollars")
        return cls(
            event_type=data["event_type"],
            remaining_microdollars=int(data["remaining_microdollars"]),
            allocated_microdollars=int(data["allocated_microdollars"]),
            timestamp=ts,
            threshold_pct=(
                float(threshold_pct_raw) if threshold_pct_raw is not None else None
            ),
            committed_microdollars=(
                int(committed_raw) if committed_raw is not None else None
            ),
            reserved_microdollars=(
                int(reserved_raw) if reserved_raw is not None else None
            ),
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
        # Custom-threshold callbacks keyed by fractional threshold (0.0-1.0).
        # Within a single key, callbacks fire in registration order.
        # An auto-incremented handle is paired with each callback so the
        # caller can pass it back to unregister_threshold_callback().
        self._custom_threshold_callbacks: Dict[
            float, List[Tuple[int, Callable[[BudgetEvent], None]]]
        ] = {}
        # Each (threshold_pct, handle) fires at most once per tracker.
        self._fired_custom_handles: set[int] = set()
        # Monotonic handle counter; never reused so unregister is unambiguous.
        self._next_callback_handle: int = 1
        self._max_callbacks: int = 100
        self._store = store
        self._tracker_id = tracker_id

        # Track which hardcoded thresholds have already fired so we don't re-fire
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

        custom_dispatch: List[
            Tuple[BudgetEvent, List[Callable[[BudgetEvent], None]]]
        ] = []
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
                # Issue #603: collect custom-threshold dispatch list while
                # still holding the lock; reserve() also crosses thresholds
                # because (committed + reserved) just increased.
                custom_dispatch = self._collect_custom_threshold_events()
        except Exception:
            # Fail-closed: any unexpected error -> deny
            logger.exception(
                "Unexpected error in reserve() -- fail-closed, returning False"
            )
            return False

        # Issue #603: dispatch outside the lock. Callback failure isolation
        # is handled inside _dispatch_custom_threshold_callbacks.
        self._dispatch_custom_threshold_callbacks(custom_dispatch)
        return True

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
        custom_dispatch: List[
            Tuple[BudgetEvent, List[Callable[[BudgetEvent], None]]]
        ] = []
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
            # Issue #603: collect custom-threshold dispatch list under the
            # same lock so the rising-edge predicate is evaluated against a
            # consistent (committed, reserved) pair.
            custom_dispatch = self._collect_custom_threshold_events()

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

        # Issue #603: dispatch custom-threshold callbacks OUTSIDE the lock.
        # Failure of one callback MUST NOT prevent siblings from firing,
        # and MUST NOT propagate to the record() caller.
        self._dispatch_custom_threshold_callbacks(custom_dispatch)

        # C3: Save the snapshot that was captured consistently inside the lock.
        if (
            snapshot_to_save is not None
            and self._tracker_id is not None
            and self._store is not None
        ):
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

        Raises:
            BudgetTrackerError: If the maximum number of callbacks (100)
                has been reached.
        """
        if len(self._threshold_callbacks) >= self._max_callbacks:
            raise BudgetTrackerError(
                f"Maximum callback limit ({self._max_callbacks}) reached",
                details={"callback_type": "threshold", "limit": self._max_callbacks},
            )
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

        Raises:
            BudgetTrackerError: If the maximum number of callbacks (100)
                has been reached.
        """
        if len(self._record_callbacks) >= self._max_callbacks:
            raise BudgetTrackerError(
                f"Maximum callback limit ({self._max_callbacks}) reached",
                details={"callback_type": "record", "limit": self._max_callbacks},
            )
        self._record_callbacks.append(callback)

    def set_threshold_callback(
        self,
        threshold_pct: float,
        callback: Callable[[BudgetEvent], None],
    ) -> int:
        """Register a callback to fire when budget utilization crosses ``threshold_pct``.

        Unlike :meth:`on_threshold`, which fires at hardcoded 80%, 95%, and
        100% utilization marks, this method registers a callback at any
        caller-supplied fraction of allocated budget.  The callback fires
        once -- and only once -- per registration when the predicate

            (committed + reserved) / allocated >= threshold_pct

        first becomes true after a successful :meth:`record` or
        :meth:`reserve` call.  State oscillation (committed/reserved
        decreasing below the threshold and crossing it again) does NOT
        re-fire the callback.

        Multiple callbacks MAY be registered for the same threshold.
        Within a single threshold, callbacks fire in registration order.
        Callbacks for distinct thresholds fire in ascending threshold
        order when a single mutation crosses several thresholds at once.

        If a callback raises, the exception is logged at WARNING level via
        ``logger.exception`` and execution continues to the next registered
        callback for the same event.  The triggering :meth:`record` /
        :meth:`reserve` call NEVER propagates a callback exception to its
        caller -- this preserves the budget-accounting hot path.

        Args:
            threshold_pct: Fractional threshold in the half-open range
                ``(0.0, 1.0]``.  ``0.80`` fires at 80% utilization;
                ``1.0`` fires when ``committed + reserved >= allocated``.
                Values outside this range, NaN, or infinite raise
                :class:`BudgetTrackerError`.
            callback: Callable accepting a :class:`BudgetEvent`.  The event
                carries ``event_type="custom_threshold"``, the registered
                ``threshold_pct``, and a snapshot of
                ``committed_microdollars`` / ``reserved_microdollars`` /
                ``remaining_microdollars`` at the moment of crossing.

        Returns:
            An opaque integer handle that can be passed to
            :meth:`unregister_threshold_callback` to symmetrically remove
            this registration.  Handles are unique within a tracker
            instance and are never reused.

        Raises:
            BudgetTrackerError: If ``threshold_pct`` is not finite, is
                ``<= 0.0``, or is ``> 1.0``.  Also raised if the maximum
                callback limit (100) has been reached across the union of
                all custom-threshold callbacks.

        Example::

            tracker = BudgetTracker(allocated_microdollars=10_000_000)
            fired = []
            tracker.set_threshold_callback(
                0.80,
                lambda evt: fired.append(evt.threshold_pct),
            )
            tracker.reserve(8_500_000)  # 85% -- callback fires once
            tracker.record(8_500_000, 1_000_000)  # back to 10% -- no re-fire
            tracker.reserve(9_500_000)  # back to 95% -- still no re-fire
            assert fired == [0.80]
        """
        if not callable(callback):
            raise BudgetTrackerError(
                f"callback must be callable, got {type(callback).__name__}",
                details={"callback_type": type(callback).__name__},
            )
        if not isinstance(threshold_pct, (int, float)) or isinstance(
            threshold_pct, bool
        ):
            raise BudgetTrackerError(
                f"threshold_pct must be a number, got {type(threshold_pct).__name__}",
                details={"threshold_pct_type": type(threshold_pct).__name__},
            )
        threshold = float(threshold_pct)
        if not math.isfinite(threshold):
            raise BudgetTrackerError(
                f"threshold_pct must be finite, got {threshold_pct!r}",
                details={"threshold_pct": str(threshold_pct)},
            )
        if threshold <= 0.0 or threshold > 1.0:
            raise BudgetTrackerError(
                f"threshold_pct must satisfy 0.0 < pct <= 1.0, got {threshold!r}",
                details={"threshold_pct": threshold},
            )

        with self._lock:
            total = sum(len(v) for v in self._custom_threshold_callbacks.values())
            if total >= self._max_callbacks:
                raise BudgetTrackerError(
                    f"Maximum custom-threshold callback limit ({self._max_callbacks}) reached",
                    details={
                        "callback_type": "custom_threshold",
                        "limit": self._max_callbacks,
                    },
                )
            handle = self._next_callback_handle
            self._next_callback_handle += 1
            self._custom_threshold_callbacks.setdefault(threshold, []).append(
                (handle, callback)
            )
            return handle

    def unregister_threshold_callback(self, handle: int) -> bool:
        """Remove a callback previously registered via :meth:`set_threshold_callback`.

        Args:
            handle: The handle returned from :meth:`set_threshold_callback`.

        Returns:
            True if a callback with the given handle was removed; False if
            the handle was not found (already unregistered or never valid).

        Note:
            Unregistering a callback after it has already fired does NOT
            re-arm the registration.  Once a custom-threshold callback has
            fired its one-shot, it stays fired even if its registration
            slot is reused by a subsequent ``set_threshold_callback`` call
            -- the new registration receives a fresh handle and a fresh
            one-shot opportunity.
        """
        if not isinstance(handle, int) or isinstance(handle, bool):
            return False
        with self._lock:
            for threshold, entries in list(self._custom_threshold_callbacks.items()):
                for idx, (h, _cb) in enumerate(entries):
                    if h == handle:
                        del entries[idx]
                        if not entries:
                            del self._custom_threshold_callbacks[threshold]
                        # Leave _fired_custom_handles entry in place so a
                        # re-registration with a new handle gets a fresh
                        # one-shot rather than re-firing on the old crossing.
                        return True
            return False

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
        # Map hardcoded event_type -> threshold fraction for cross-callback
        # uniformity; consumers may filter by threshold_pct regardless of
        # whether the event came from on_threshold or set_threshold_callback.
        _PCT_FOR_TYPE: Dict[str, float] = {
            "threshold_80": 0.80,
            "threshold_95": 0.95,
            "exhausted": 1.00,
        }
        for event_type in thresholds_to_fire:
            event = BudgetEvent(
                event_type=event_type,
                remaining_microdollars=remaining,
                allocated_microdollars=self._allocated,
                threshold_pct=_PCT_FOR_TYPE.get(event_type),
                committed_microdollars=self._committed,
                reserved_microdollars=self._reserved,
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

    def _collect_custom_threshold_events(
        self,
    ) -> List[Tuple[BudgetEvent, List[Callable[[BudgetEvent], None]]]]:
        """Collect custom-threshold events that crossed since last evaluation.

        Called under lock from both :meth:`record` and :meth:`reserve`. For
        each threshold whose predicate
        ``(committed + reserved) / allocated >= threshold_pct`` is now true
        AND whose handle has not yet fired, this method:

        1. Marks every callback at that threshold as fired (one-shot).
        2. Builds one :class:`BudgetEvent` describing the crossing.
        3. Returns ``(event, callbacks_in_registration_order)`` so the
           caller can dispatch OUTSIDE the lock (avoids re-entrancy
           deadlock when callbacks call back into the tracker).

        Thresholds are visited in ascending order so that a single
        mutation crossing both 0.50 and 0.80 fires the 0.50 callbacks
        first.

        Returns:
            List of ``(event, callbacks)`` tuples, possibly empty. Each
            tuple's callbacks list is a stable copy that survives
            concurrent unregistration.
        """
        if self._allocated == 0 or not self._custom_threshold_callbacks:
            return []

        # claimed/allocated >= pct  <=>  claimed >= pct * allocated.
        # Use float comparison; thresholds are bounded in (0,1] so
        # float precision at the boundary matches the documented contract.
        claimed = self._committed + self._reserved
        allocated_f = float(self._allocated)

        out: List[Tuple[BudgetEvent, List[Callable[[BudgetEvent], None]]]] = []
        remaining = max(0, self._allocated - self._committed - self._reserved)
        for threshold in sorted(self._custom_threshold_callbacks.keys()):
            entries = self._custom_threshold_callbacks.get(threshold, [])
            if not entries:
                continue
            # Predicate check
            if (claimed / allocated_f) < threshold:
                continue
            unfired = [
                (h, cb) for (h, cb) in entries if h not in self._fired_custom_handles
            ]
            if not unfired:
                continue
            # Mark fired NOW (still under lock) so concurrent
            # reserve/record cannot double-collect the same handle.
            for h, _cb in unfired:
                self._fired_custom_handles.add(h)
            event = BudgetEvent(
                event_type="custom_threshold",
                remaining_microdollars=remaining,
                allocated_microdollars=self._allocated,
                threshold_pct=threshold,
                committed_microdollars=self._committed,
                reserved_microdollars=self._reserved,
            )
            logger.info(
                "Budget custom threshold crossed: %.4f "
                "(committed=%d, reserved=%d, allocated=%d, claimed=%d)",
                threshold,
                self._committed,
                self._reserved,
                self._allocated,
                claimed,
            )
            out.append((event, [cb for (_h, cb) in unfired]))
        return out

    def _dispatch_custom_threshold_callbacks(
        self,
        dispatch: List[Tuple[BudgetEvent, List[Callable[[BudgetEvent], None]]]],
    ) -> None:
        """Dispatch custom-threshold callbacks OUTSIDE the lock.

        Issue #603: callback failures MUST NOT propagate to the caller of
        :meth:`record` or :meth:`reserve`, AND MUST NOT prevent siblings
        from firing. Each callback runs in its own try/except; raises are
        logged at WARNING via ``logger.exception`` (which captures stack
        trace). The ordering is: events in threshold-ascending order
        (established in :meth:`_collect_custom_threshold_events`),
        callbacks within an event in registration order.
        """
        for event, callbacks in dispatch:
            for cb in callbacks:
                try:
                    cb(event)
                except Exception:
                    logger.exception(
                        "Custom threshold callback raised exception for "
                        "threshold_pct=%s -- ignoring",
                        event.threshold_pct,
                    )


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
