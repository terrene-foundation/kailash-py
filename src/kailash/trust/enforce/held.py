# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Human-in-the-loop (HITL) hold timeout + fail-safe expiry disposition.

A HELD verdict parks an action pending human review. Without a bounded
response window a hold is oversight-theatre — it blocks forever, or worse,
some caller silently lets it through. This module gives the HELD machinery
a configurable timeout and a *deterministic, fail-safe* expiry disposition.

Design invariants (SAFR BH2 / GitHub #1515):

1. A held action carries a ``timeout`` (seconds) + an ``on_expiry``
   disposition (:class:`ExpiryDisposition`).
2. On expiry the configured disposition fires deterministically and is
   recorded to the enforcer's audit sink.
3. The UNSET ``on_expiry`` default is fail-safe = ``DENY`` — a hold with no
   configured expiry disposition denies on timeout; it NEVER auto-approves.
4. Timeout windows are configurable per capability / action-class via the
   existing :class:`~kailash.trust.governance.models.ApprovalPolicyModel`
   ``approval_timeout_seconds`` field (see :func:`resolve_timeout_seconds`).
5. Expiry is MONOTONIC — the resolved outcome is at least as restrictive as
   the hold itself (never less restrictive than ``HELD``).

Security (trust-plane-security.md):
- ``timeout`` is validated with ``math.isfinite()`` and rejected if negative.
- Hold IDs are ``validate_id()``-checked before use in any file path.
- The SQLite store uses parameterized SQL, 0o600 perms, bounded rows.
- Collections are bounded (``maxlen``).
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, runtime_checkable

from kailash.trust._locking import secure_sqlite_files, validate_id
from kailash.trust.enforce.strict import EnforcementRecord, Verdict

if TYPE_CHECKING:
    from kailash.trust.governance.models import ApprovalPolicyModel

logger = logging.getLogger(__name__)

__all__ = [
    "ExpiryDisposition",
    "DEFAULT_EXPIRY_DISPOSITION",
    "HeldAction",
    "HeldActionStore",
    "MemoryHeldActionStore",
    "ReviewDecisionError",
    "ReviewerDecision",
    "SqliteHeldActionStore",
    "new_hold_id",
    "resolve_expiry_verdict",
    "resolve_review_verdict",
    "resolve_timeout_seconds",
    "verdict_rank",
]


class ExpiryDisposition(Enum):
    """Default disposition applied when a human-review hold times out.

    Every member MUST resolve (via :data:`_DISPOSITION_VERDICT`) to a verdict
    that is at least as restrictive as ``HELD`` — an expired hold can escalate
    to a denial or a re-hold, NEVER relax to auto-approval. This closed set is
    the monotonic guarantee (invariant 5); a member that resolves below
    ``HELD`` is a fail-open regression that :func:`resolve_expiry_verdict`
    clamps closed and ``test_held_timeout_failsafe`` pins.
    """

    DENY = "deny"  # -> BLOCKED (fail-safe default)
    ESCALATE_TO_SENIOR = "escalate_to_senior"  # -> HELD (re-held for senior review)


# The unset-on_expiry fail-safe default (invariant 3). A hold with no
# configured expiry disposition denies on timeout — it never auto-approves.
DEFAULT_EXPIRY_DISPOSITION = ExpiryDisposition.DENY


# Restrictiveness ordering. Monotonic escalation only, matching the trust
# model AUTO_APPROVED -> FLAGGED -> HELD -> BLOCKED (eatp.md § Trust Model).
_VERDICT_RANK: Dict[Verdict, int] = {
    Verdict.AUTO_APPROVED: 0,
    Verdict.FLAGGED: 1,
    Verdict.HELD: 2,
    Verdict.BLOCKED: 3,
}

# The single shared disposition -> verdict mapping. Both members resolve at
# or above HELD; :func:`resolve_expiry_verdict` fail-closes any value not
# present here (and any future member that would resolve below HELD).
_DISPOSITION_VERDICT: Dict[ExpiryDisposition, Verdict] = {
    ExpiryDisposition.DENY: Verdict.BLOCKED,
    ExpiryDisposition.ESCALATE_TO_SENIOR: Verdict.HELD,
}


def verdict_rank(verdict: Verdict) -> int:
    """Return the monotonic restrictiveness rank of a verdict (higher = tighter)."""
    return _VERDICT_RANK[verdict]


def resolve_expiry_verdict(disposition: ExpiryDisposition) -> Verdict:
    """Resolve an expiry disposition to a concrete, monotonic verdict.

    Fail-closed on every axis:

    - An unrecognized / unmapped disposition resolves to ``BLOCKED`` (the
      tightest verdict) rather than leaking through.
    - A mapping that would resolve *below* ``HELD`` (a fail-open regression
      introduced by a future enum member) is clamped up to ``BLOCKED``.

    This is the sole restrictiveness function for the expiry surface — invariant
    5 (monotonic expiry) holds because this function can only ever return a
    verdict with rank >= ``HELD``.
    """
    verdict = _DISPOSITION_VERDICT.get(disposition)
    if verdict is None:
        # Unknown disposition — deny (fail-closed, pact-governance.md Rule 4).
        return Verdict.BLOCKED
    if _VERDICT_RANK[verdict] < _VERDICT_RANK[Verdict.HELD]:
        # Monotonic guard: an expiry outcome may never be less restrictive
        # than the hold it replaces. Clamp to BLOCKED (never auto-approve).
        return Verdict.BLOCKED
    return verdict


class ReviewerDecision(Enum):
    """A human reviewer's disposition of a pending HITL hold (BH2 leg 3).

    A held action parks pending human review; this enum is the authority a
    reviewer exercises over it. The three members resolve — via the single
    monotonic :func:`resolve_review_verdict` — to concrete verdicts:

    - ``APPROVE`` sanctions the *originally-held* action to proceed
      (``AUTO_APPROVED``). This is the reviewer's authorized resolution of the
      hold; it grants exactly the held action and NEVER escalates authority
      beyond the original request.
    - ``DECLINE`` denies the action (``BLOCKED``).
    - ``MODIFY`` substitutes a reviewer-chosen verdict, constrained to
      *monotonic-tightening only* — a MODIFY may never WIDEN authority below
      ``HELD`` (see :func:`resolve_review_verdict`).
    """

    APPROVE = "approve"  # -> AUTO_APPROVED (sanction the originally-held action)
    MODIFY = "modify"  # -> monotonic-tightening only (never widens below HELD)
    DECLINE = "decline"  # -> BLOCKED


class ReviewDecisionError(ValueError):
    """Raised when a reviewer decision cannot be applied (fail-closed).

    Covers a missing/unknown ``hold_id``, a ``MODIFY`` without an explicit
    modified verdict, and an unrecognized decision — every path fails closed
    with a typed error rather than silently permitting an action.
    """


def resolve_review_verdict(
    decision: ReviewerDecision,
    *,
    modified_verdict: Optional[Verdict] = None,
) -> Verdict:
    """Resolve a reviewer decision to a concrete, monotonic-guarded verdict.

    Fail-closed on every axis (pact-governance.md Rule 4/6):

    - ``DECLINE`` -> ``BLOCKED``.
    - ``APPROVE`` -> ``AUTO_APPROVED`` (the authorized resolution of the hold;
      grants the originally-held action, no more — no authority escalation).
    - ``MODIFY`` requires an explicit ``modified_verdict`` (else
      :class:`ReviewDecisionError`) and is *monotonic-tightening only*: a
      modified verdict less restrictive than ``HELD`` (i.e. ``AUTO_APPROVED`` /
      ``FLAGGED`` — a WIDENING of authority) is clamped fail-closed to
      ``BLOCKED``. This reuses the single ``_VERDICT_RANK`` ordering that
      :func:`resolve_expiry_verdict` uses — the restrictiveness function is not
      reinvented.
    - An unrecognized ``decision`` raises :class:`ReviewDecisionError`.

    Only ``APPROVE`` may resolve below ``HELD``; it is the reviewer's explicit,
    authorized sanction of the hold, NOT an automatic widening.
    """
    if decision is ReviewerDecision.DECLINE:
        return Verdict.BLOCKED
    if decision is ReviewerDecision.APPROVE:
        return Verdict.AUTO_APPROVED
    if decision is ReviewerDecision.MODIFY:
        if modified_verdict is None:
            raise ReviewDecisionError(
                "MODIFY requires an explicit modified_verdict (fail-closed)"
            )
        rank = _VERDICT_RANK.get(modified_verdict)
        if rank is None or rank < _VERDICT_RANK[Verdict.HELD]:
            # Monotonic-tightening guard: a MODIFY may not widen authority
            # below HELD. An unknown verdict OR a sub-HELD verdict is clamped
            # fail-closed to BLOCKED (never AUTO_APPROVED/FLAGGED).
            return Verdict.BLOCKED
        return modified_verdict
    raise ReviewDecisionError(f"unknown reviewer decision: {decision!r}")


def resolve_timeout_seconds(policy: "ApprovalPolicyModel") -> float:
    """Resolve the per-capability hold timeout from an approval policy.

    This is the live consumer of
    :attr:`~kailash.trust.governance.models.ApprovalPolicyModel.approval_timeout_seconds`
    — the field that previously had no consumer (invariant 4). Timeout windows
    are therefore configurable per capability / action-class through the
    existing policy model rather than a parallel constant.

    Args:
        policy: An ``ApprovalPolicyModel`` (or any object exposing
            ``approval_timeout_seconds``).

    Returns:
        The timeout in seconds as a float.

    Raises:
        ValueError: If the timeout is non-finite (NaN/Inf) or negative.
    """
    raw = getattr(policy, "approval_timeout_seconds")
    timeout = float(raw)
    if not math.isfinite(timeout):
        raise ValueError(f"approval_timeout_seconds must be finite, got {raw!r}")
    if timeout < 0:
        raise ValueError(f"approval_timeout_seconds must be non-negative, got {raw!r}")
    return timeout


@dataclass(frozen=True)
class HeldAction:
    """A parked human-review hold with a bounded expiry window.

    Frozen to prevent post-creation tampering of the tracked deadline —
    a mutable ``expires_at`` would let a compromised path extend its own
    review window indefinitely.
    """

    hold_id: str
    agent_id: str
    action: str
    held_at: datetime
    timeout_seconds: float
    on_expiry: ExpiryDisposition
    record: EnforcementRecord
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_id(self.hold_id)
        if not math.isfinite(self.timeout_seconds):
            raise ValueError(
                f"timeout_seconds must be finite, got {self.timeout_seconds!r}"
            )
        if self.timeout_seconds < 0:
            raise ValueError(
                f"timeout_seconds must be non-negative, got {self.timeout_seconds!r}"
            )
        # Normalize a tz-naive held_at to UTC (frozen dataclass -> setattr via
        # object). A naive held_at would make expires_at naive too, and the
        # SQLite store compares expires_at.isoformat() lexicographically against
        # an aware now.isoformat() (which carries a +00:00 offset) — the two
        # forms sort differently, and is_expired() would raise TypeError on a
        # naive-vs-aware comparison. Assume UTC for a naive caller.
        if self.held_at.tzinfo is None:
            object.__setattr__(
                self, "held_at", self.held_at.replace(tzinfo=timezone.utc)
            )

    @property
    def expires_at(self) -> datetime:
        """The deterministic deadline: ``held_at + timeout_seconds``."""
        return self.held_at + timedelta(seconds=self.timeout_seconds)

    def is_expired(self, now: datetime) -> bool:
        """True when ``now`` is at or past the deadline."""
        return now >= self.expires_at


def new_hold_id() -> str:
    """Generate a fresh, ``validate_id``-safe hold identifier."""
    return f"hold-{uuid.uuid4().hex}"


# ---------------------------------------------------------------------------
# Store protocol + implementations
# ---------------------------------------------------------------------------


@runtime_checkable
class HeldActionStore(Protocol):
    """Persistence protocol for pending human-review holds with timeouts."""

    def add(self, held: HeldAction) -> None:
        """Register a pending hold for timeout tracking."""
        ...

    def pop_expired(self, now: datetime) -> List[HeldAction]:
        """Atomically remove and return every hold expired as of ``now``."""
        ...

    def pop(self, hold_id: str) -> Optional[HeldAction]:
        """Atomically remove and return the hold with ``hold_id``, else None.

        Used by reviewer-decision resolution (BH2 leg 3) to claim a specific
        pending hold. Returns ``None`` when no such hold is tracked.
        """
        ...

    def pending(self) -> List[HeldAction]:
        """Return all currently-pending holds."""
        ...

    def clear(self) -> None:
        """Remove all pending holds."""
        ...


class MemoryHeldActionStore:
    """In-memory held-action store. Thread-safe, bounded (FIFO eviction)."""

    def __init__(self, maxlen: int = 10_000) -> None:
        self._lock = threading.Lock()
        self._holds: "OrderedDict[str, HeldAction]" = OrderedDict()
        self._maxlen = maxlen

    def add(self, held: HeldAction) -> None:
        with self._lock:
            self._holds[held.hold_id] = held
            # Bounded: evict oldest (FIFO) beyond maxlen.
            while len(self._holds) > self._maxlen:
                self._holds.popitem(last=False)

    def pop_expired(self, now: datetime) -> List[HeldAction]:
        with self._lock:
            expired = [h for h in self._holds.values() if h.is_expired(now)]
            for h in expired:
                del self._holds[h.hold_id]
            return expired

    def pop(self, hold_id: str) -> Optional[HeldAction]:
        validate_id(hold_id)
        with self._lock:
            return self._holds.pop(hold_id, None)

    def pending(self) -> List[HeldAction]:
        with self._lock:
            return list(self._holds.values())

    def clear(self) -> None:
        with self._lock:
            self._holds.clear()


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS held_actions (
    hold_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    action TEXT NOT NULL,
    held_at TEXT NOT NULL,
    timeout_seconds REAL NOT NULL,
    expires_at TEXT NOT NULL,
    on_expiry TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    violations_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}'
)
"""


class SqliteHeldActionStore:
    """SQLite-backed held-action store (persists across restarts).

    Follows the shadow-store conventions: 0o600 file perms, parameterized
    SQL, bounded rows, thread-safe via a lock + WAL.
    """

    def __init__(self, db_path: str, max_records: int = 100_000) -> None:
        self._db_path = db_path
        self._max_records = max_records
        self._lock = threading.Lock()

        if not db_path.startswith(":memory:") and not os.path.exists(db_path):
            open(db_path, "a").close()

        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute(_CREATE_TABLE_SQL)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_held_expires ON held_actions(expires_at)"
        )
        self._conn.commit()
        # Harden the main DB + the WAL/SHM sidecars (created by the commit
        # above under WAL mode) to owner-only — the sidecars hold the same
        # governance data. Runs AFTER the first write so the sidecars exist.
        secure_sqlite_files(db_path)

    def add(self, held: HeldAction) -> None:
        validate_id(held.hold_id)
        vr = held.record.verification_result
        violations_json = json.dumps(vr.violations if vr and vr.violations else [])
        reason = vr.reason if vr and vr.reason else ""
        metadata_json = json.dumps(held.metadata or {})
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO held_actions "
                "(hold_id, agent_id, action, held_at, timeout_seconds, expires_at, "
                "on_expiry, reason, violations_json, metadata_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    held.hold_id,
                    held.agent_id,
                    held.action,
                    held.held_at.isoformat(),
                    held.timeout_seconds,
                    held.expires_at.isoformat(),
                    held.on_expiry.value,
                    reason,
                    violations_json,
                    metadata_json,
                ),
            )
            self._conn.commit()
            # Bounded: trim oldest by expiry when exceeding max.
            row = self._conn.execute("SELECT COUNT(*) FROM held_actions").fetchone()
            if row and row[0] > self._max_records:
                excess = row[0] - self._max_records
                self._conn.execute(
                    "DELETE FROM held_actions WHERE hold_id IN "
                    "(SELECT hold_id FROM held_actions ORDER BY expires_at ASC LIMIT ?)",
                    (excess,),
                )
                self._conn.commit()

    def pop_expired(self, now: datetime) -> List[HeldAction]:
        now_iso = now.isoformat()
        with self._lock:
            cursor = self._conn.execute(
                "SELECT hold_id, agent_id, action, held_at, timeout_seconds, "
                "on_expiry, reason, violations_json, metadata_json "
                "FROM held_actions WHERE expires_at <= ?",
                (now_iso,),
            )
            rows = cursor.fetchall()
            if rows:
                self._conn.execute(
                    "DELETE FROM held_actions WHERE expires_at <= ?", (now_iso,)
                )
                self._conn.commit()
        # Per-row fail-closed conversion. A single corrupt/tampered row (bad
        # on_expiry string, non-finite timeout, unsafe hold_id, malformed
        # timestamp) must NOT abort the whole batch — the rows are already
        # deleted+committed above, so an exception here would silently drop
        # every expired hold (including well-formed siblings) with NO BLOCKED
        # audit record emitted. Instead, a corrupt row yields a fail-closed
        # DENY sentinel (resolves to BLOCKED at expiry) and processing
        # continues (user-flow-validation.md MUST-7 class (c): corrupt state).
        result: List[HeldAction] = []
        for row in rows:
            try:
                result.append(self._row_to_held(row))
            except Exception:
                logger.warning(
                    "[HELD] corrupt held-action row — fail-closed BLOCKED "
                    "(hold_id=%r)",
                    row[0] if row else None,
                    exc_info=True,
                )
                result.append(self._corrupt_sentinel(row, now))
        return result

    def pop(self, hold_id: str) -> Optional[HeldAction]:
        validate_id(hold_id)
        with self._lock:
            cursor = self._conn.execute(
                "SELECT hold_id, agent_id, action, held_at, timeout_seconds, "
                "on_expiry, reason, violations_json, metadata_json "
                "FROM held_actions WHERE hold_id = ?",
                (hold_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            self._conn.execute("DELETE FROM held_actions WHERE hold_id = ?", (hold_id,))
            self._conn.commit()
        # Fail-closed conversion for a corrupt/tampered row: the row is already
        # deleted+committed above, so a raw exception would silently drop the
        # hold with no verdict; instead yield the DENY sentinel (-> BLOCKED).
        try:
            return self._row_to_held(row)
        except Exception:
            logger.warning(
                "[HELD] corrupt held-action row on pop — fail-closed BLOCKED "
                "(hold_id=%r)",
                hold_id,
                exc_info=True,
            )
            return self._corrupt_sentinel(row, datetime.now(timezone.utc))

    def pending(self) -> List[HeldAction]:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT hold_id, agent_id, action, held_at, timeout_seconds, "
                "on_expiry, reason, violations_json, metadata_json FROM held_actions"
            )
            rows = cursor.fetchall()
        return [self._row_to_held(row) for row in rows]

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM held_actions")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def _row_to_held(row: Any) -> HeldAction:
        from kailash.trust.chain import VerificationResult

        (
            hold_id,
            agent_id,
            action,
            held_at_str,
            timeout_seconds,
            on_expiry_str,
            reason,
            violations_json,
            metadata_json,
        ) = row
        violations = json.loads(violations_json) if violations_json else []
        metadata = json.loads(metadata_json) if metadata_json else {}
        vr = VerificationResult(valid=True, reason=reason, violations=violations)
        record = EnforcementRecord(
            agent_id=agent_id,
            action=action,
            verdict=Verdict.HELD,
            verification_result=vr,
            timestamp=datetime.fromisoformat(held_at_str),
            metadata=dict(metadata),
        )
        return HeldAction(
            hold_id=hold_id,
            agent_id=agent_id,
            action=action,
            held_at=datetime.fromisoformat(held_at_str),
            timeout_seconds=float(timeout_seconds),
            on_expiry=ExpiryDisposition(on_expiry_str),
            record=record,
            metadata=dict(metadata),
        )

    @staticmethod
    def _corrupt_sentinel(row: Any, now: datetime) -> HeldAction:
        """Build a fail-closed DENY hold for a corrupt/tampered persisted row.

        Any value in the row may be garbage, so nothing from it is trusted for
        control flow: the sentinel always denies on expiry (``DENY`` -> BLOCKED)
        with a zero timeout (already expired). Best-effort recoverable fields
        (agent_id / action / the original hold_id string) are surfaced in the
        record metadata for forensics but never used to relax the disposition.
        """
        from kailash.trust.chain import VerificationResult

        def _safe_str(index: int) -> str:
            try:
                value = row[index]
            except Exception:
                return "unknown"
            return str(value) if value else "unknown"

        agent_id = _safe_str(1)
        action = _safe_str(2)
        original_hold_id = repr(row[0])[:200] if row else "unknown"

        vr = VerificationResult(
            valid=False,
            reason="corrupt held-action row — fail-closed BLOCKED",
            violations=[],
        )
        record = EnforcementRecord(
            agent_id=agent_id,
            action=action,
            verdict=Verdict.HELD,
            verification_result=vr,
            timestamp=now,
            metadata={"corrupt_row": True, "original_hold_id": original_hold_id},
        )
        return HeldAction(
            hold_id=new_hold_id(),
            agent_id=agent_id,
            action=action,
            held_at=now,
            timeout_seconds=0.0,
            on_expiry=ExpiryDisposition.DENY,
            record=record,
            metadata={"corrupt_row": True, "original_hold_id": original_hold_id},
        )
