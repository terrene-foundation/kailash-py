# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Strict enforcement for EATP trust verification.

Wraps VERIFY operations with configurable behavior for different
verification outcomes. Designed for production environments where
unauthorized actions must be blocked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from kailash.trust.chain import VerificationLevel, VerificationResult

if TYPE_CHECKING:
    from kailash.trust.enforce.held import ExpiryDisposition, HeldActionStore
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
        """
        from kailash.trust.enforce.held import (
            DEFAULT_EXPIRY_DISPOSITION,
            MemoryHeldActionStore,
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
            logger.info(
                f"[ENFORCE] HELD: agent={agent_id} action={action} — queued for review"
            )
            self._review_queue.append(record)
            # Bounded memory for review queue
            if len(self._review_queue) > self._max_records:
                trim_count = self._max_records // 10
                self._review_queue = self._review_queue[trim_count:]
            # Register a timeout-tracked hold when a response window is set,
            # either explicitly (timeout) or from the approval policy
            # (approval_timeout_seconds). The unset on_expiry disposition is
            # fail-safe DENY (never auto-approves) per self._default_expiry.
            self._register_hold(
                agent_id,
                action,
                record,
                timeout=timeout,
                on_expiry=on_expiry,
                approval_policy=approval_policy,
            )
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

    def _register_hold(
        self,
        agent_id: str,
        action: str,
        record: EnforcementRecord,
        *,
        timeout: Optional[float],
        on_expiry: Optional[ExpiryDisposition],
        approval_policy: Optional[ApprovalPolicyModel],
    ) -> None:
        """Track a QUEUE hold for timeout expiry when a response window is set.

        The timeout comes from ``timeout`` when given, else from
        ``approval_policy.approval_timeout_seconds`` (per-capability window).
        When neither is set, no hold is tracked (the hold has no bounded
        response window and expire_holds() will never fire for it). The
        ``on_expiry`` disposition defaults to the enforcer's fail-safe default.
        """
        from kailash.trust.enforce.held import (
            HeldAction,
            new_hold_id,
            resolve_timeout_seconds,
        )

        resolved_timeout = timeout
        if resolved_timeout is None and approval_policy is not None:
            resolved_timeout = resolve_timeout_seconds(approval_policy)
        if resolved_timeout is None:
            return

        disposition = on_expiry if on_expiry is not None else self._default_expiry
        hold = HeldAction(
            hold_id=new_hold_id(),
            agent_id=agent_id,
            action=action,
            held_at=record.timestamp,
            timeout_seconds=float(resolved_timeout),
            on_expiry=disposition,
            record=record,
            metadata=dict(record.metadata),
        )
        self._held_store.add(hold)

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
        expired = self._held_store.pop_expired(evaluated_at)
        expiry_records: List[EnforcementRecord] = []

        for hold in expired:
            verdict = resolve_expiry_verdict(hold.on_expiry)
            # Monotonic invariant: an expiry outcome is never less restrictive
            # than the hold it replaces. resolve_expiry_verdict guarantees
            # rank >= HELD; this is the defense-in-depth fail-closed backstop.
            if verdict_rank(verdict) < verdict_rank(Verdict.HELD):
                verdict = Verdict.BLOCKED

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
                agent_id=hold.agent_id,
                action=hold.action,
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
                hold.agent_id,
                hold.action,
                hold.hold_id,
                hold.on_expiry.value,
                verdict.value,
            )

        return expiry_records

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
        self._records.clear()

    def clear_review_queue(self) -> None:
        """Clear the review queue."""
        self._review_queue.clear()


__all__ = [
    "StrictEnforcer",
    "Verdict",
    "HeldBehavior",
    "EATPBlockedError",
    "EATPHeldError",
    "EnforcementRecord",
]
