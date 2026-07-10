# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Strict enforcement for EATP trust verification.

Wraps VERIFY operations with configurable behavior for different
verification outcomes. Designed for production environments where
unauthorized actions must be blocked.
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from kailash.trust.chain import VerificationLevel, VerificationResult

# Reviewer identifiers are bound into audit records and logged; cap the length
# so a multi-megabyte reviewer_id cannot flood the log/audit sink (BH2 leg 3,
# Finding 3a). validate_id() guards the charset (no newline/control/traversal);
# this floor guards the size. 256 chars is generous for any real identifier.
_MAX_REVIEWER_ID_LEN = 256

if TYPE_CHECKING:
    from kailash.trust.enforce.held import (
        ExpiryDisposition,
        HeldActionStore,
        ReviewerDecision,
    )
    from kailash.trust.governance.models import ApprovalPolicyModel
    from kailash.trust.hooks import HookRegistry

logger = logging.getLogger(__name__)


class Verdict(Enum):
    """Enforcement verdict for a verification result."""

    AUTO_APPROVED = "auto_approved"  # Valid, no issues
    FLAGGED = "flagged"  # Valid but has warnings (constraint near limits)
    HELD = "held"  # Requires human review before proceeding
    BLOCKED = "blocked"  # Denied, action must not proceed


class HeldBehavior(Enum):
    """How to handle HELD verdicts."""

    RAISE = "raise"  # Raise EATPHeldError
    QUEUE = "queue"  # Add to review queue (callback required)
    CALLBACK = "callback"  # Call user-provided callback


class EATPBlockedError(PermissionError):
    """Raised when an action is blocked by EATP verification."""

    def __init__(
        self,
        agent_id: str,
        action: str,
        reason: str,
        violations: Optional[List[Dict[str, str]]] = None,
    ):
        self.agent_id = agent_id
        self.action = action
        self.reason = reason
        self.violations = violations or []
        super().__init__(
            f"EATP BLOCKED: Agent '{agent_id}' denied action '{action}': {reason}"
        )


class EATPHeldError(PermissionError):
    """Raised when an action is held for human review."""

    def __init__(
        self,
        agent_id: str,
        action: str,
        reason: str,
        violations: Optional[List[Dict[str, str]]] = None,
    ):
        self.agent_id = agent_id
        self.action = action
        self.reason = reason
        self.violations = violations or []
        super().__init__(
            f"EATP HELD: Agent '{agent_id}' action '{action}' requires review: {reason}"
        )


@dataclass(frozen=True)
class EnforcementRecord:
    """Record of an enforcement decision.

    Frozen to prevent post-creation tampering of audit records.
    """

    agent_id: str
    action: str
    verdict: Verdict
    verification_result: VerificationResult
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


class StrictEnforcer:
    """Strict enforcement wrapper around EATP VERIFY operations.

    Interprets verification results into enforcement verdicts and takes
    appropriate action (block, hold, flag, or approve).

    Example:
        >>> from kailash.trust.enforce.strict import StrictEnforcer
        >>> enforcer = StrictEnforcer(on_held=HeldBehavior.RAISE)
        >>> enforcer.enforce(agent_id="agent-001", action="read_data", result=verify_result)
    """

    def __init__(
        self,
        on_held: HeldBehavior = HeldBehavior.RAISE,
        held_callback: Optional[Callable[[str, str, VerificationResult], bool]] = None,
        flag_threshold: int = 1,
        maxlen: int = 10_000,
        hook_registry: Optional[HookRegistry] = None,
        held_store: Optional[HeldActionStore] = None,
        default_expiry: Optional[ExpiryDisposition] = None,
        max_pending_holds: int = 1000,
    ):
        """Initialize strict enforcer.

        Args:
            on_held: Behavior when a HELD verdict is issued
            held_callback: Callback for CALLBACK held behavior.
                Receives (agent_id, action, result) and returns True to allow.
            flag_threshold: Number of violations that upgrades FLAGGED to HELD
            maxlen: Maximum number of records to retain (oldest 10% trimmed on overflow)
            hook_registry: Optional hook registry for lifecycle event interception.
                If provided, PRE_VERIFICATION and POST_VERIFICATION hooks are
                executed during enforce(). If None, enforce() behaves identically
                to pre-hook versions (backward compatible).
            held_store: Store tracking QUEUE-behavior holds that carry a timeout,
                so expire_holds() can fire their configured disposition. Defaults
                to an in-memory store bounded by ``maxlen``.
            default_expiry: Disposition applied when a held action carries a
                timeout but no explicit ``on_expiry``. Defaults to the fail-safe
                ``ExpiryDisposition.DENY`` (a hold with no configured expiry
                disposition denies on timeout — it NEVER auto-approves).
            max_pending_holds: Reviewer-capacity admission-control bound (BH2
                leg 2). When the pending review queue is saturated to this
                many holds, a NEW QUEUE-behavior escalation FAILS CLOSED —
                it is DENIED (``BLOCKED``, ``EATPBlockedError``), never
                silently dropped. The default is a safe, finite bound; it is
                distinct from ``maxlen`` (a memory-only FIFO backstop). MUST
                be a positive integer.
        """
        from kailash.trust.enforce.held import (
            DEFAULT_EXPIRY_DISPOSITION,
            MemoryHeldActionStore,
        )

        if not isinstance(max_pending_holds, int) or isinstance(
            max_pending_holds, bool
        ):
            raise ValueError(
                f"max_pending_holds must be an int, got {type(max_pending_holds).__name__}"
            )
        if max_pending_holds < 1:
            raise ValueError(
                f"max_pending_holds must be >= 1, got {max_pending_holds!r}"
            )

        self._on_held = on_held
        self._held_callback = held_callback
        self._flag_threshold = flag_threshold
        self._records: List[EnforcementRecord] = []
        self._review_queue: List[EnforcementRecord] = []
        self._max_records = maxlen
        self._hook_registry = hook_registry
        self._held_store: HeldActionStore = (
            held_store
            if held_store is not None
            else MemoryHeldActionStore(maxlen=maxlen)
        )
        self._default_expiry: ExpiryDisposition = (
            default_expiry if default_expiry is not None else DEFAULT_EXPIRY_DISPOSITION
        )
        self._max_pending_holds = max_pending_holds

        # Admission-control vs store-capacity invariant (BH2 leg 2, Finding 2):
        # a timeout-bearing hold in the review queue MUST stay tracked in the
        # store, else expire_holds never fires for it and it sits reviewer-
        # APPROVABLE past its deadline (defeating deterministic expiry). The max
        # number of holds simultaneously queued is min(max_pending_holds [the
        # capacity gate], max_records [the FIFO trim]); the store MUST hold at
        # least that many without evicting. A store exposing `capacity` is
        # checked; a custom store that does not expose it is documented as
        # responsible for its own sizing and skipped (fail-loud only where we
        # can prove the misconfiguration). The internally-created default store
        # always satisfies this (its capacity == maxlen == self._max_records).
        store_capacity = getattr(self._held_store, "capacity", None)
        if store_capacity is not None:
            required = min(max_pending_holds, self._max_records)
            if store_capacity < required:
                raise ValueError(
                    f"held_store capacity ({store_capacity}) is below the "
                    f"effective pending-hold bound ({required} = "
                    f"min(max_pending_holds={max_pending_holds}, "
                    f"maxlen={self._max_records})); a timeout-bearing queued "
                    f"hold could be evicted from the store and never expire. "
                    f"Increase the store's capacity to >= {required}."
                )

        # Serializes every _review_queue / _records mutation so the review-queue
        # lifecycle is single-winner: the capacity-gate read+append, the
        # apply_review_decision scan→pop→reassign, the expire_holds
        # pop+audit-emit+queue-reconcile, and the clear_* resets are each atomic
        # and mutually exclusive. Reentrant (RLock) DEFENSIVELY — no current path
        # re-acquires it on the same thread (enforce() releases it before calling
        # _handle_held, which re-acquires fresh), but RLock keeps a future
        # guarded-method-calling-a-guarded-method refactor from self-deadlocking.
        # Lock ordering is always enforcer-lock THEN store-lock (never the
        # reverse) so no deadlock with the store's own lock.
        self._lock = threading.RLock()

        if on_held == HeldBehavior.CALLBACK and held_callback is None:
            raise ValueError("held_callback required when on_held is CALLBACK")

    def classify(self, result: VerificationResult) -> Verdict:
        """Classify a verification result into an enforcement verdict.

        Args:
            result: The verification result from a VERIFY operation

        Returns:
            The enforcement verdict
        """
        if not result.valid:
            return Verdict.BLOCKED

        violation_count = len(result.violations)

        if violation_count >= self._flag_threshold:
            return Verdict.HELD

        if violation_count > 0:
            return Verdict.FLAGGED

        return Verdict.AUTO_APPROVED

    @property
    def hook_registry(self) -> Optional[HookRegistry]:
        """Get the attached hook registry, if any."""
        return self._hook_registry

    def enforce(
        self,
        agent_id: str,
        action: str,
        result: VerificationResult,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
        on_expiry: Optional[ExpiryDisposition] = None,
        approval_policy: Optional[ApprovalPolicyModel] = None,
    ) -> Verdict:
        """Enforce a verification result.

        If a hook_registry is attached, PRE_VERIFICATION hooks run before
        classification, and POST_VERIFICATION hooks run after. A hook
        returning ``allow=False`` in PRE_VERIFICATION results in BLOCKED.

        Args:
            agent_id: The agent being verified
            action: The action being verified
            result: The verification result
            metadata: Additional context
            timeout: Optional human-review response window in seconds. When set
                on a QUEUE-behavior hold, the hold is tracked so that a later
                ``expire_holds()`` call fires its ``on_expiry`` disposition once
                the window elapses. If ``None``, ``approval_policy`` is consulted.
            on_expiry: Disposition applied when this hold times out. If ``None``
                the enforcer's ``default_expiry`` (fail-safe ``DENY``) applies —
                a hold with no configured expiry disposition denies on timeout.
            approval_policy: Per-capability / per-action-class approval policy.
                When ``timeout`` is ``None`` and a policy is given, the hold's
                timeout is read from ``policy.approval_timeout_seconds`` — the
                live consumer of that previously-orphan field.

        Returns:
            The enforcement verdict

        Raises:
            EATPBlockedError: If the action is blocked
            EATPHeldError: If the action is held (when on_held=RAISE)
            ValueError: If the resolved timeout is non-finite or negative.
        """
        # Run PRE_VERIFICATION hooks (if registry attached)
        if self._hook_registry is not None:
            from kailash.trust.hooks import HookContext, HookType

            pre_context = HookContext(
                agent_id=agent_id,
                action=action,
                hook_type=HookType.PRE_VERIFICATION,
                metadata=dict(metadata) if metadata else {},
            )
            hook_result = self._hook_registry.execute_sync(
                HookType.PRE_VERIFICATION, pre_context
            )
            if not hook_result.allow:
                logger.warning(
                    f"[ENFORCE] BLOCKED by PRE_VERIFICATION hook: "
                    f"agent={agent_id} action={action} reason={hook_result.reason}"
                )
                raise EATPBlockedError(
                    agent_id=agent_id,
                    action=action,
                    reason=f"Blocked by hook: {hook_result.reason}",
                )

        verdict = self.classify(result)

        # Run POST_VERIFICATION hooks (if registry attached).
        # Invariant: POST hooks can only deny (add a BLOCKED), never upgrade
        # a verdict. The verdict local variable is set by classify() above
        # and is NOT read back from hook metadata.
        if self._hook_registry is not None:
            from kailash.trust.hooks import HookContext, HookType

            post_context = HookContext(
                agent_id=agent_id,
                action=action,
                hook_type=HookType.POST_VERIFICATION,
                metadata={
                    "verdict": verdict.value,
                    "valid": result.valid,
                    "violations": len(result.violations),
                    **(metadata or {}),
                },
            )
            hook_result = self._hook_registry.execute_sync(
                HookType.POST_VERIFICATION, post_context
            )
            if not hook_result.allow:
                logger.warning(
                    f"[ENFORCE] BLOCKED by POST_VERIFICATION hook: "
                    f"agent={agent_id} action={action} reason={hook_result.reason}"
                )
                raise EATPBlockedError(
                    agent_id=agent_id,
                    action=action,
                    reason=f"Blocked by hook: {hook_result.reason}",
                )

        record_metadata = dict(metadata) if metadata else {}

        # Propagate reasoning trace fields into enforcement record metadata
        # when they are explicitly set (not None — preserves backward compat)
        if result.reasoning_present is not None:
            record_metadata["reasoning_present"] = result.reasoning_present
        if result.reasoning_verified is not None:
            record_metadata["reasoning_verified"] = result.reasoning_verified

        record = EnforcementRecord(
            agent_id=agent_id,
            action=action,
            verdict=verdict,
            verification_result=result,
            metadata=record_metadata,
        )
        with self._lock:
            self._records.append(record)
            # Bounded memory: trim oldest 10% when exceeding maxlen
            if len(self._records) > self._max_records:
                trim_count = self._max_records // 10
                self._records = self._records[trim_count:]

        if verdict == Verdict.BLOCKED:
            reason = result.reason or "Verification failed"
            # Include reasoning violation details in log when present
            reasoning_violations = [
                v for v in result.violations if v.get("dimension") == "reasoning"
            ]
            if reasoning_violations:
                logger.warning(
                    f"[ENFORCE] BLOCKED: agent={agent_id} action={action} "
                    f"reason={reason} reasoning_violations={reasoning_violations}"
                )
            else:
                logger.warning(
                    f"[ENFORCE] BLOCKED: agent={agent_id} action={action} reason={reason}"
                )
            raise EATPBlockedError(
                agent_id=agent_id,
                action=action,
                reason=reason,
                violations=result.violations,
            )

        if verdict == Verdict.HELD:
            return self._handle_held(
                agent_id,
                action,
                result,
                record,
                timeout=timeout,
                on_expiry=on_expiry,
                approval_policy=approval_policy,
            )

        if verdict == Verdict.FLAGGED:
            logger.info(
                f"[ENFORCE] FLAGGED: agent={agent_id} action={action} "
                f"violations={len(result.violations)} — allowing execution"
            )

        return verdict

    def _handle_held(
        self,
        agent_id: str,
        action: str,
        result: VerificationResult,
        record: EnforcementRecord,
        *,
        timeout: Optional[float] = None,
        on_expiry: Optional[ExpiryDisposition] = None,
        approval_policy: Optional[ApprovalPolicyModel] = None,
    ) -> Verdict:
        """Handle a HELD verdict based on configured behavior."""
        reason = result.reason or "Action requires human review"

        if self._on_held == HeldBehavior.RAISE:
            logger.warning(
                f"[ENFORCE] HELD: agent={agent_id} action={action} — raising"
            )
            raise EATPHeldError(
                agent_id=agent_id,
                action=action,
                reason=reason,
                violations=result.violations,
            )

        if self._on_held == HeldBehavior.QUEUE:
            from kailash.trust.enforce.held import new_hold_id

            # Resolve + VALIDATE the timeout BEFORE any queue mutation (Finding
            # 3): a negative / non-finite timeout must raise here, not after the
            # queue append — otherwise enforce(timeout=-5) leaves an orphan queue
            # entry before HeldAction.__post_init__ would have raised.
            resolved_timeout = self._resolve_hold_timeout(timeout, approval_policy)

            # The capacity-gate READ and the queue append MUST be one atomic
            # critical section (Finding 2): otherwise two concurrent escalations
            # both read len < capacity and both enqueue, overrunning the bound.
            # The lock also serializes admission vs expire_holds vs
            # apply_review_decision on _review_queue / _records.
            with self._lock:
                # Capacity gate (BH2 leg 2): fail-closed admission control. When
                # the pending review queue is saturated to reviewer capacity, a
                # NEW escalation is DENIED (BLOCKED) — never silently dropped and
                # never unbounded-queued. This is distinct from the ``maxlen``
                # FIFO trim below (a memory-only backstop that silently evicts
                # oldest holds); the capacity gate is real admission control.
                if len(self._review_queue) >= self._max_pending_holds:
                    denial_record = EnforcementRecord(
                        agent_id=agent_id,
                        action=action,
                        verdict=Verdict.BLOCKED,
                        verification_result=result,
                        metadata={
                            **dict(record.metadata),
                            "admission_denied": True,
                            "pending_holds": len(self._review_queue),
                            "max_pending_holds": self._max_pending_holds,
                        },
                    )
                    self._records.append(denial_record)
                    if len(self._records) > self._max_records:
                        trim_count = self._max_records // 10
                        self._records = self._records[trim_count:]
                    logger.warning(
                        "[ENFORCE] HELD escalation DENIED — review queue "
                        "saturated (pending=%d capacity=%d): agent=%s action=%s",
                        len(self._review_queue),
                        self._max_pending_holds,
                        agent_id,
                        action,
                    )
                    raise EATPBlockedError(
                        agent_id=agent_id,
                        action=action,
                        reason=(
                            f"Review queue saturated "
                            f"({len(self._review_queue)}/{self._max_pending_holds}) "
                            f"— escalation denied (fail-closed)"
                        ),
                        violations=result.violations,
                    )

                hold_id = new_hold_id()
                # Correlate the passive review-queue entry with its store hold so
                # a reviewer can address the exact hold by id
                # (apply_review_decision). record.metadata is a mutable dict; the
                # dataclass freeze blocks field reassignment, not dict mutation.
                record.metadata["hold_id"] = hold_id
                logger.info(
                    f"[ENFORCE] HELD: agent={agent_id} action={action} "
                    f"hold_id={hold_id} — queued for review"
                )
                self._review_queue.append(record)
                # Bounded memory for review queue
                if len(self._review_queue) > self._max_records:
                    trim_count = self._max_records // 10
                    self._review_queue = self._review_queue[trim_count:]
                # Register a timeout-tracked hold when a response window is set.
                # The unset on_expiry disposition is fail-safe DENY (never
                # auto-approves) per self._default_expiry. A hold that IS
                # registered (timeout-bearing) is stamped `timeout_bearing` on
                # its queue record so expire_holds can reconcile ONLY store-
                # backed entries — a no-timeout queue hold (never in the store,
                # its PK free) MUST NOT be evictable by a forged corrupt store
                # row bearing its id (Finding 1a).
                timeout_bearing = self._register_hold(
                    agent_id,
                    action,
                    record,
                    hold_id=hold_id,
                    resolved_timeout=resolved_timeout,
                    on_expiry=on_expiry,
                )
                if timeout_bearing:
                    record.metadata["timeout_bearing"] = True
            raise EATPHeldError(
                agent_id=agent_id,
                action=action,
                reason=f"Queued for review: {reason}",
                violations=result.violations,
            )

        # CALLBACK
        assert self._held_callback is not None
        logger.info(
            f"[ENFORCE] HELD: agent={agent_id} action={action} — invoking callback"
        )
        allowed = self._held_callback(agent_id, action, result)
        if allowed:
            object.__setattr__(record, "verdict", Verdict.AUTO_APPROVED)
            return Verdict.AUTO_APPROVED
        raise EATPBlockedError(
            agent_id=agent_id,
            action=action,
            reason=f"Denied by review callback: {reason}",
            violations=result.violations,
        )

    def _resolve_hold_timeout(
        self,
        timeout: Optional[float],
        approval_policy: Optional[ApprovalPolicyModel],
    ) -> Optional[float]:
        """Resolve + validate a hold's response window, fail-closed and early.

        The window comes from ``timeout`` when given, else from
        ``approval_policy.approval_timeout_seconds`` (per-capability). When
        neither is set the hold has no bounded window and ``None`` is returned
        (no store tracking; expire_holds never fires for it). A resolved window
        MUST be finite and non-negative — validated HERE so a bad timeout raises
        BEFORE any queue mutation (Finding 3), not later inside HeldAction.

        Raises:
            ValueError: If the resolved timeout is non-finite or negative.
        """
        from kailash.trust.enforce.held import resolve_timeout_seconds

        resolved = timeout
        if resolved is None and approval_policy is not None:
            resolved = resolve_timeout_seconds(approval_policy)  # validates
        if resolved is None:
            return None
        resolved = float(resolved)
        if not math.isfinite(resolved):
            raise ValueError(f"hold timeout must be finite, got {resolved!r}")
        if resolved < 0:
            raise ValueError(f"hold timeout must be non-negative, got {resolved!r}")
        return resolved

    def _register_hold(
        self,
        agent_id: str,
        action: str,
        record: EnforcementRecord,
        *,
        hold_id: str,
        resolved_timeout: Optional[float],
        on_expiry: Optional[ExpiryDisposition],
    ) -> bool:
        """Track a QUEUE hold for timeout expiry when a response window is set.

        ``resolved_timeout`` is the already-resolved-and-validated window from
        :meth:`_resolve_hold_timeout` (``None`` = no bounded window → not
        tracked). The ``on_expiry`` disposition defaults to the enforcer's
        fail-safe default.

        Returns:
            ``True`` if the hold was registered in the store (timeout-bearing),
            ``False`` if it has no bounded window and was not tracked.
        """
        from kailash.trust.enforce.held import HeldAction

        if resolved_timeout is None:
            return False

        disposition = on_expiry if on_expiry is not None else self._default_expiry
        hold = HeldAction(
            hold_id=hold_id,
            agent_id=agent_id,
            action=action,
            held_at=record.timestamp,
            timeout_seconds=float(resolved_timeout),
            on_expiry=disposition,
            record=record,
            metadata=dict(record.metadata),
        )
        self._held_store.add(hold)
        return True

    def expire_holds(self, now: Optional[datetime] = None) -> List[EnforcementRecord]:
        """Fire the configured disposition for every hold past its deadline.

        Deterministic: pass ``now`` to evaluate expiry at a fixed instant.
        Each expired hold resolves — via the single monotonic
        ``resolve_expiry_verdict`` — to a verdict at least as restrictive as
        ``HELD`` (fail-safe ``DENY`` -> ``BLOCKED`` for an unset disposition;
        never ``AUTO_APPROVED``/``FLAGGED``). Each expiry is recorded to the
        same audit sink (``self._records``) the verdict path writes to.

        Args:
            now: Instant to evaluate expiry against. Defaults to current UTC.

        Returns:
            The enforcement records created for the expired holds (one each).
        """
        from kailash.trust.enforce.held import resolve_expiry_verdict, verdict_rank

        evaluated_at = now if now is not None else datetime.now(timezone.utc)
        expiry_records: List[EnforcementRecord] = []

        # Pop the expired holds from the store AND reconcile the passive review
        # queue in ONE atomic critical section (Finding 1, CRITICAL). An expired
        # hold must vanish from BOTH surfaces together: if only the store row is
        # popped, the lingering _review_queue entry (still valid=True HELD, its
        # hold_id intact) lets a late apply_review_decision(hold_id, APPROVE)
        # find `matched`, skip the both-None fail-closed guard, and resurrect an
        # already-timed-out-and-BLOCKED action to AUTO_APPROVED — a
        # BLOCKED->AUTO_APPROVED monotonic downgrade invariant 5 forbids. The
        # lock also serializes expire vs admission vs apply_review_decision.
        with self._lock:
            expired = self._held_store.pop_expired(evaluated_at)

            # The set of ids to drop from the passive review queue on expiry.
            # For a NORMAL expired hold this is hold.hold_id (== the id
            # _handle_held stamped + _register_hold shared). For a CORRUPT row
            # recovered as the fail-closed sentinel, hold.hold_id is a FRESH id
            # that matches no queue entry — so the ORIGINAL id (preserved by
            # _corrupt_sentinel as metadata["original_hold_id"]) is unioned in.
            # Without this union a corrupt-row expiry leaves the original queue
            # entry (valid=True HELD) live, and a late apply_review_decision(H,
            # APPROVE) resurrects an already-BLOCKED action to AUTO_APPROVED.
            expired_ids = {hold.hold_id for hold in expired}
            expired_ids |= {
                hold.metadata.get("original_hold_id")
                for hold in expired
                if hold.metadata.get("original_hold_id")
            }

            for hold in expired:
                verdict = resolve_expiry_verdict(hold.on_expiry)
                # Monotonic invariant: an expiry outcome is never less
                # restrictive than the hold it replaces. resolve_expiry_verdict
                # guarantees rank >= HELD; this is the fail-closed backstop.
                if verdict_rank(verdict) < verdict_rank(Verdict.HELD):
                    verdict = Verdict.BLOCKED

                # Finding 1b: a corrupt sentinel's agent_id/action are recovered
                # from the attacker-controllable tampered row. Do NOT propagate
                # them verbatim into the emitted audit record — redact to a
                # sentinel so a forged row cannot poison the audit trail with
                # attacker-chosen identifiers. corrupt_row + original_hold_id
                # survive in the metadata (via the spread below) for forensics.
                is_corrupt = bool(hold.metadata.get("corrupt_row"))
                audit_agent_id = "<corrupt>" if is_corrupt else hold.agent_id
                audit_action = "<corrupt>" if is_corrupt else hold.action

                expiry_metadata = {
                    **dict(hold.metadata),
                    "hold_expiry": True,
                    "hold_id": hold.hold_id,
                    "on_expiry": hold.on_expiry.value,
                    "original_verdict": Verdict.HELD.value,
                    "held_at": hold.held_at.isoformat(),
                    "timeout_seconds": hold.timeout_seconds,
                    "expires_at": hold.expires_at.isoformat(),
                }
                expiry_record = EnforcementRecord(
                    agent_id=audit_agent_id,
                    action=audit_action,
                    verdict=verdict,
                    verification_result=hold.record.verification_result,
                    timestamp=evaluated_at,
                    metadata=expiry_metadata,
                )
                self._records.append(expiry_record)
                # Bounded memory: trim oldest 10% when exceeding maxlen
                if len(self._records) > self._max_records:
                    trim_count = self._max_records // 10
                    self._records = self._records[trim_count:]

                expiry_records.append(expiry_record)
                logger.warning(
                    "[ENFORCE] HELD EXPIRED: agent=%s action=%s hold_id=%s "
                    "on_expiry=%s -> %s",
                    audit_agent_id,
                    audit_action,
                    hold.hold_id,
                    hold.on_expiry.value,
                    verdict.value,
                )

            # State advance AFTER the audit emit (eatp.md § Signed-Audit-Emits-
            # BEFORE-State-Advance): every BLOCKED expiry record is appended to
            # the audit sink above BEFORE the review-queue is rebound here, so a
            # sink that raises can never leave a rebound queue with a hole in the
            # audit chain. (The store deletion inside pop_expired is unavoidably
            # first; the queue rebind is the state advance ordered to follow.)
            #
            # RESIDUAL (latent audit-reorder): self._records is an in-memory list
            # today, so append() cannot fail and the store-delete-before-audit-
            # append ordering is harmless. If _records is ever upgraded to a
            # fallible signing / persisting sink, the audit emit MUST move BEFORE
            # the pop_expired store deletion (emit-then-delete), or an emit
            # failure leaves the store row deleted with no audit row.
            #
            # Finding 1a: reconcile ONLY entries that were TIMEOUT-BEARING (had a
            # real store presence). A no-timeout queue hold (never registered in
            # the store, its PK slot free) MUST NOT be evictable by an expire
            # event — an attacker who forges a corrupt store row bearing that
            # hold's id would otherwise get the sentinel's original_hold_id into
            # expired_ids and drop the victim's legit queue entry (fail-closed
            # denial-of-review). Genuinely timeout-bearing holds still reconcile
            # (R2 corrupt-row behavior preserved) — only they carry the flag.
            if expired_ids:
                self._review_queue = [
                    queued
                    for queued in self._review_queue
                    if not (
                        queued.metadata.get("timeout_bearing")
                        and queued.metadata.get("hold_id") in expired_ids
                    )
                ]

        return expiry_records

    def apply_review_decision(
        self,
        hold_id: str,
        decision: "ReviewerDecision",
        reviewer_id: str,
        *,
        modified_verdict: Optional[Verdict] = None,
    ) -> EnforcementRecord:
        """Apply a human reviewer's decision to a pending HITL hold (BH2 leg 3).

        Resolves a held action addressed by ``hold_id`` to a concrete verdict
        under the reviewer's authority, binding ``reviewer_id`` into the
        resulting audit record. Monotonic-guarded and fail-closed:

        - ``DECLINE`` -> ``BLOCKED``.
        - ``APPROVE`` -> ``AUTO_APPROVED`` — sanctions the originally-held
          action to proceed, WITHOUT escalating authority beyond the original
          request.
        - ``MODIFY`` -> the supplied ``modified_verdict``, clamped to
          monotonic-tightening only; a verdict less restrictive than ``HELD``
          (a widening) is clamped fail-closed to ``BLOCKED``. ``MODIFY``
          without a ``modified_verdict`` raises ``ReviewDecisionError``.

        The reviewed hold is removed from BOTH the passive review queue and the
        timeout-tracking store, so it can neither be re-reviewed nor expire. A
        hold recovered from the store as a corrupt fail-closed sentinel forces
        ``BLOCKED`` regardless of the decision (invariant 5).

        Args:
            hold_id: Identifier of the pending hold to resolve.
            decision: The reviewer's disposition (APPROVE / MODIFY / DECLINE).
            reviewer_id: Identifier of the reviewer, bound into the audit
                record's metadata. An identifier, NOT a credential. Validated
                through ``validate_id`` (rejects newline / control-char /
                path-traversal injection) before it is bound or logged.
            modified_verdict: Required for ``MODIFY`` — the reviewer's target
                verdict, subject to the monotonic-tightening clamp.

        Returns:
            The ``EnforcementRecord`` for the reviewer decision (verdict +
            ``reviewer_id`` bound), also appended to the enforcer's audit sink.

        Raises:
            ReviewDecisionError: If ``hold_id`` is unknown/missing/expired, a
                ``MODIFY`` omits ``modified_verdict``, an ``APPROVE``/``DECLINE``
                carries a modified_verdict (ambiguous), or ``reviewer_id``
                exceeds the length cap — all fail-closed. A bad decision raises
                BEFORE the hold is consumed, so the hold survives for a
                corrected retry.
            ValueError: If ``hold_id`` or ``reviewer_id`` is not a safe
                identifier.

        Thread-safe: the scan → pop → reassign is single-winner under a lock;
        concurrent calls on the same hold resolve exactly once.
        """
        from kailash.trust._locking import validate_id
        from kailash.trust.enforce.held import (
            ReviewDecisionError,
            resolve_review_verdict,
        )

        # Validate BOTH identifiers before any state mutation. hold_id gates
        # path-traversal; reviewer_id is bound into the audit record AND logged,
        # so a newline / control-char / null-byte reviewer_id is an audit-log
        # line-injection vector — route it through the same validate_id as
        # hold_id (symmetric charset floor).
        validate_id(hold_id)
        validate_id(reviewer_id)
        # Length floor (Finding 3a): validate_id caps the charset but not the
        # size; a multi-megabyte reviewer_id would flood the audit sink + logs.
        if len(reviewer_id) > _MAX_REVIEWER_ID_LEN:
            raise ReviewDecisionError(
                f"apply_review_decision: reviewer_id length {len(reviewer_id)} "
                f"exceeds cap {_MAX_REVIEWER_ID_LEN} — fail-closed"
            )

        # Resolve the decision FIRST. resolve_review_verdict is pure and
        # side-effect-free but VALIDATES the decision — a MODIFY without a
        # modified_verdict, or a malformed decision, raises HERE. It MUST run
        # BEFORE any hold is consumed so a bad decision leaves the hold intact
        # and re-resolvable on a corrected retry (no state advance before the
        # validating step, per eatp.md § Signed-Audit-Emits-BEFORE-State-Advance).
        verdict = resolve_review_verdict(decision, modified_verdict=modified_verdict)

        # Scan → pop → reassign is a read-modify-write on shared state; it MUST
        # be atomic (Finding 2) so two concurrent apply_review_decision calls on
        # the SAME queue-only hold cannot both find `matched` and both resolve
        # (a DECLINE + APPROVE race could otherwise emit AUTO_APPROVED after a
        # BLOCKED). The lock makes review resolution single-winner: the first
        # caller claims the hold, the second finds it in neither surface and
        # fails closed. Also serializes review vs expire_holds vs admission.
        with self._lock:
            # The passive review queue is the source of truth for pending holds
            # (every QUEUE escalation lands here with its hold_id); the store
            # only tracks the timeout-bearing subset. Compute the surviving
            # queue WITHOUT reassigning it yet, then claim the store hold.
            matched: Optional[EnforcementRecord] = None
            remaining: List[EnforcementRecord] = []
            for queued in self._review_queue:
                if matched is None and queued.metadata.get("hold_id") == hold_id:
                    matched = queued
                else:
                    remaining.append(queued)

            stored = self._held_store.pop(hold_id)

            if matched is None and stored is None:
                # Unknown / already-resolved / already-expired hold_id — fail
                # closed. The pop above was a no-op (the id is in neither
                # surface), so nothing was consumed and the reviewer can retry.
                raise ReviewDecisionError(
                    f"apply_review_decision: unknown or already-resolved hold_id "
                    f"{hold_id!r} — fail-closed"
                )

            # Commit the queue mutation only now that the decision is valid AND
            # the hold exists.
            self._review_queue = remaining

            base = matched if matched is not None else stored.record

            # A hold recovered from the store as a CORRUPT sentinel carries
            # verification_result.valid == False (the fail-closed DENY sentinel
            # from SqliteHeldActionStore.pop). An APPROVE/MODIFY over corrupt
            # state MUST NOT resolve to a permissive verdict — force BLOCKED,
            # symmetric with the expiry path's corrupt-row handling. A
            # well-formed HELD record is always valid=True (classify() only
            # yields HELD for valid results), so this never false-positives on a
            # genuine hold (invariant 5).
            corrupt_hold = base.verification_result.valid is False
            if corrupt_hold:
                verdict = Verdict.BLOCKED

            decision_metadata: Dict[str, Any] = {
                **dict(base.metadata),
                "hold_id": hold_id,
                "reviewer_id": reviewer_id,
                "reviewer_decision": decision.value,
                "review_of_verdict": Verdict.HELD.value,
            }
            if modified_verdict is not None:
                decision_metadata["modified_verdict_requested"] = modified_verdict.value
            if corrupt_hold:
                decision_metadata["corrupt_hold"] = True

            decision_record = EnforcementRecord(
                agent_id=base.agent_id,
                action=base.action,
                verdict=verdict,
                verification_result=base.verification_result,
                metadata=decision_metadata,
            )
            self._records.append(decision_record)
            if len(self._records) > self._max_records:
                trim_count = self._max_records // 10
                self._records = self._records[trim_count:]

        logger.info(
            "[ENFORCE] REVIEW %s by reviewer=%s hold_id=%s -> %s",
            decision.value,
            reviewer_id,
            hold_id,
            verdict.value,
        )
        return decision_record

    @property
    def max_pending_holds(self) -> int:
        """Reviewer-capacity admission-control bound (BH2 leg 2)."""
        return self._max_pending_holds

    @property
    def held_store(self) -> "HeldActionStore":
        """The store tracking pending timeout-bounded holds."""
        return self._held_store

    @property
    def records(self) -> List[EnforcementRecord]:
        """Get all enforcement records."""
        return list(self._records)

    @property
    def review_queue(self) -> List[EnforcementRecord]:
        """Get the pending review queue."""
        return list(self._review_queue)

    def clear_records(self) -> None:
        """Clear enforcement records."""
        with self._lock:
            self._records.clear()

    def clear_review_queue(self) -> None:
        """Clear the review queue."""
        with self._lock:
            self._review_queue.clear()


__all__ = [
    "StrictEnforcer",
    "Verdict",
    "HeldBehavior",
    "EATPBlockedError",
    "EATPHeldError",
    "EnforcementRecord",
]
