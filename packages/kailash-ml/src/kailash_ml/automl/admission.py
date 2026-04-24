# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PACT admission-gate wire-through for AutoML trials.

W27a provides the caller-side scaffolding that every AutoML trial routes
through before it is scheduled. The actual PACT implementation
(:class:`kailash_pact.GovernanceEngine.check_trial_admission`) lands in
W32 32c. Until then, :func:`check_trial_admission` degrades gracefully:

1. If :mod:`kailash_pact` is not importable AND no engine is injected,
   the call returns :class:`AdmissionDecision` with
   ``decision="skipped"`` and a loud WARN log naming the missing extra.
   Trials proceed — PACT governance is not enforced.
2. If an engine IS injected BUT it raises ``AttributeError`` /
   ``NotImplementedError`` because W32 32c hasn't shipped yet, the
   call returns ``decision="unimplemented"`` and trials proceed with a
   loud WARN. This is the documented "degraded mode" per the W27a brief
   (``rules/zero-tolerance.md`` Rule 2 exception — wire-through to a
   peer-package pending implementation).
3. If the engine raises any OTHER exception, the call returns
   ``decision="error"`` with the error class name — fail-CLOSED for
   programmer errors (per ``specs/pact-ml-integration.md`` §2.1
   invariants) by raising :class:`PromotionRequiresApprovalError`. The
   AutoML engine's approval-gate logic catches this and requires human
   authorization.
4. If the engine returns a real ``AdmissionDecision`` (W32 32c
   onwards), :func:`check_trial_admission` re-wraps it into our local
   dataclass so the AutoML audit schema stays stable regardless of
   upstream PACT refactors.

When the AutoML trial's proposed spend exceeds
``auto_approve_threshold_microdollars``, :func:`check_trial_admission`
raises :class:`PromotionRequiresApprovalError` BEFORE invoking PACT —
this is the human-approval gate mandated by
``specs/ml-automl.md`` §8.3 MUST 4 (approval default is opt-in).

See ``specs/pact-ml-integration.md`` §2.1 for the upstream contract
this module wires against.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

__all__ = [
    "AdmissionDecision",
    "PromotionRequiresApprovalError",
    "GovernanceEngineLike",
    "check_trial_admission",
]


class PromotionRequiresApprovalError(Exception):
    """Raised when a trial's proposed spend exceeds the auto-approve ceiling.

    The AutoML engine's ``auto_approve=False`` default and the
    ``auto_approve_threshold`` kwarg combine to determine whether a
    trial can proceed without human authorization. When the ceiling is
    exceeded, the trial is BLOCKED and this error bubbles up so a
    Nexus/CLI approval loop can resolve it.

    Per ``specs/ml-automl.md`` §8.3 MUST 4 the default MUST be
    human-in-loop; per ``rules/autonomous-execution.md`` approval gates
    are the "Human-on-the-Loop" seam for cost-bearing actions.
    """

    def __init__(
        self,
        *,
        trial_number: int,
        proposed_microdollars: int,
        auto_approve_threshold_microdollars: int,
        tenant_id: str,
        actor_id: str,
        reason: str = "auto-approve threshold exceeded",
    ) -> None:
        self.trial_number = trial_number
        self.proposed_microdollars = proposed_microdollars
        self.auto_approve_threshold_microdollars = auto_approve_threshold_microdollars
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.reason = reason
        super().__init__(
            f"promotion requires approval: tenant={tenant_id} actor={actor_id} "
            f"trial={trial_number} proposed={proposed_microdollars}u "
            f"> threshold={auto_approve_threshold_microdollars}u ({reason})"
        )


@dataclass(frozen=True)
class AdmissionDecision:
    """Outcome of a PACT trial-admission check.

    Mirrors ``kailash_pact.AdmissionDecision`` (see
    ``specs/pact-ml-integration.md`` §2.1) but re-homed in
    ``kailash_ml.automl`` so AutoML callers can persist admission rows
    without a hard dependency on kailash-pact being installed.

    ``decision`` enumerates the three degraded-mode shapes plus
    ``"admitted"`` / ``"denied"``:

    - ``"admitted"``  — PACT approved (W32 32c returns this)
    - ``"denied"``    — PACT rejected (W32 32c returns this)
    - ``"skipped"``   — PACT not installed; degraded mode
    - ``"unimplemented"`` — PACT installed but check_trial_admission
                        not yet implemented (W27a → W32 32c bridge)
    - ``"error"``     — programmer error in the PACT call;
                        :class:`PromotionRequiresApprovalError` raised
    """

    decision: str
    admitted: bool
    reason: str
    tenant_id: str
    actor_id: str
    trial_number: int
    decision_id: str
    decided_at: datetime
    binding_constraint: Optional[str] = None
    upstream_payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "admitted": self.admitted,
            "reason": self.reason,
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "trial_number": self.trial_number,
            "decision_id": self.decision_id,
            "decided_at": self.decided_at.isoformat(),
            "binding_constraint": self.binding_constraint,
            "upstream_payload": dict(self.upstream_payload),
        }


@runtime_checkable
class GovernanceEngineLike(Protocol):
    """Structural type for a PACT GovernanceEngine capable of trial admission.

    Matches the upstream signature specified in
    ``specs/pact-ml-integration.md`` §2.1. The real class lands in
    ``kailash_pact.GovernanceEngine`` at W32 32c.
    """

    def check_trial_admission(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        trial_config: Mapping[str, Any],
        budget_microdollars: int,
        latency_budget_ms: int,
        fairness_constraints: Optional[Mapping[str, Any]] = None,
    ) -> Any:  # AdmissionDecision-shaped per spec §2.1
        ...


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def check_trial_admission(
    *,
    tenant_id: str,
    actor_id: str,
    trial_number: int,
    trial_config: Mapping[str, Any],
    budget_microdollars: int,
    latency_budget_ms: int = 0,
    fairness_constraints: Optional[Mapping[str, Any]] = None,
    governance_engine: Optional[GovernanceEngineLike] = None,
    auto_approve: bool = False,
    auto_approve_threshold_microdollars: int = 0,
) -> AdmissionDecision:
    """Consult PACT before launching a trial. Degrades gracefully pre-W32 32c.

    Invariants:

    - ``tenant_id`` / ``actor_id`` MUST be non-empty strings; empty
      values are a programmer error (``ValueError``).
    - ``budget_microdollars`` MUST be a non-negative integer.
    - When ``auto_approve=False`` AND ``budget_microdollars
      > auto_approve_threshold_microdollars``, raises
      :class:`PromotionRequiresApprovalError` BEFORE consulting PACT.
    - When ``governance_engine is None``, attempts to import
      ``kailash_pact`` and build the default engine. If the import
      fails, returns a ``decision="skipped"`` AdmissionDecision and
      emits a WARN.
    - When PACT is present but the method raises
      ``AttributeError`` / ``NotImplementedError`` (W32 32c pending),
      returns ``decision="unimplemented"`` and emits a WARN.
    - When PACT raises any other exception, logs at WARN and raises
      :class:`PromotionRequiresApprovalError` (fail-CLOSED).
    """
    if not isinstance(tenant_id, str) or not tenant_id:
        raise ValueError("tenant_id must be a non-empty string")
    if not isinstance(actor_id, str) or not actor_id:
        raise ValueError("actor_id must be a non-empty string")
    if not isinstance(trial_number, int) or trial_number < 0:
        raise ValueError("trial_number must be a non-negative int")
    if not isinstance(budget_microdollars, int) or budget_microdollars < 0:
        raise ValueError("budget_microdollars must be a non-negative int")
    if (
        not isinstance(auto_approve_threshold_microdollars, int)
        or auto_approve_threshold_microdollars < 0
    ):
        raise ValueError(
            "auto_approve_threshold_microdollars must be a non-negative int"
        )

    decision_id = str(uuid.uuid4())
    now = _now_utc()

    # Human-approval gate — precedes PACT, matches spec §8.3 MUST 4
    if not auto_approve and budget_microdollars > auto_approve_threshold_microdollars:
        logger.warning(
            "automl.admission.approval_required",
            extra={
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "trial_number": trial_number,
                "proposed_microdollars": budget_microdollars,
                "auto_approve_threshold_microdollars": auto_approve_threshold_microdollars,
                "decision_id": decision_id,
            },
        )
        raise PromotionRequiresApprovalError(
            trial_number=trial_number,
            proposed_microdollars=budget_microdollars,
            auto_approve_threshold_microdollars=auto_approve_threshold_microdollars,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )

    # Resolve the governance engine
    engine = governance_engine
    if engine is None:
        try:
            # Lazy optional-extra import — kailash-pact is the source of truth
            from kailash_pact import (  # type: ignore[import-not-found,unused-ignore]
                GovernanceEngine as _PactGovernanceEngine,
            )

            # Construction signature / defaults are owned by W32 32c; until
            # then, we cannot instantiate the engine ourselves safely.
            # Treat "no engine injected" as skipped even when the module
            # imports cleanly.
            _ = _PactGovernanceEngine  # silence unused-import lint
            logger.warning(
                "automl.admission.no_engine_injected",
                extra={
                    "tenant_id": tenant_id,
                    "actor_id": actor_id,
                    "trial_number": trial_number,
                    "decision_id": decision_id,
                    "note": (
                        "kailash_pact is importable but no GovernanceEngine"
                        " was injected into AutoMLEngine. Pass"
                        " governance_engine=... at AutoMLEngine construction"
                        " to enable PACT enforcement. Proceeding admitted"
                        " under degraded mode."
                    ),
                },
            )
            return AdmissionDecision(
                decision="skipped",
                admitted=True,
                reason="no GovernanceEngine injected; PACT enforcement disabled",
                tenant_id=tenant_id,
                actor_id=actor_id,
                trial_number=trial_number,
                decision_id=decision_id,
                decided_at=now,
            )
        except ImportError:
            logger.warning(
                "automl.admission.pact_missing",
                extra={
                    "tenant_id": tenant_id,
                    "actor_id": actor_id,
                    "trial_number": trial_number,
                    "decision_id": decision_id,
                    "note": (
                        "kailash_pact not installed; PACT admission gate"
                        " disabled. Install kailash-ml[pact] to enable."
                    ),
                },
            )
            return AdmissionDecision(
                decision="skipped",
                admitted=True,
                reason="kailash_pact extra not installed; PACT enforcement disabled",
                tenant_id=tenant_id,
                actor_id=actor_id,
                trial_number=trial_number,
                decision_id=decision_id,
                decided_at=now,
            )

    # Injected engine path — call through per the spec signature
    try:
        upstream = engine.check_trial_admission(
            tenant_id=tenant_id,
            actor_id=actor_id,
            trial_config=trial_config,
            budget_microdollars=budget_microdollars,
            latency_budget_ms=latency_budget_ms,
            fairness_constraints=fairness_constraints,
        )
    except (AttributeError, NotImplementedError) as exc:
        # W32 32c pending — wire-through exists but upstream doesn't yet
        logger.warning(
            "automl.admission.pact_unimplemented",
            extra={
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "trial_number": trial_number,
                "decision_id": decision_id,
                "error_class": type(exc).__name__,
                "note": (
                    "GovernanceEngine.check_trial_admission is not yet"
                    " implemented upstream (W32 32c pending). Proceeding"
                    " admitted under degraded mode."
                ),
            },
        )
        return AdmissionDecision(
            decision="unimplemented",
            admitted=True,
            reason=(
                f"GovernanceEngine.check_trial_admission raised "
                f"{type(exc).__name__}: W32 32c pending; degraded mode"
            ),
            tenant_id=tenant_id,
            actor_id=actor_id,
            trial_number=trial_number,
            decision_id=decision_id,
            decided_at=now,
        )
    except Exception as exc:  # noqa: BLE001 — fail-CLOSED policy
        # Fail-CLOSED — per spec §2.1, a probe exception is admit=False.
        # Surface as PromotionRequiresApprovalError so the AutoML engine
        # can route through the human approval gate instead of silently
        # proceeding.
        logger.warning(
            "automl.admission.pact_error",
            extra={
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "trial_number": trial_number,
                "decision_id": decision_id,
                "error_class": type(exc).__name__,
                "error_message": str(exc),
            },
        )
        raise PromotionRequiresApprovalError(
            trial_number=trial_number,
            proposed_microdollars=budget_microdollars,
            auto_approve_threshold_microdollars=auto_approve_threshold_microdollars,
            tenant_id=tenant_id,
            actor_id=actor_id,
            reason=f"PACT probe raised {type(exc).__name__}: {exc}",
        ) from exc

    # Re-wrap upstream AdmissionDecision into our local shape
    admitted = bool(getattr(upstream, "admitted", False))
    reason = str(getattr(upstream, "reason", ""))
    binding = getattr(upstream, "binding_constraint", None)
    upstream_id = getattr(upstream, "decision_id", decision_id)
    upstream_at = getattr(upstream, "decided_at", now)
    logger.info(
        "automl.admission.decision",
        extra={
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "trial_number": trial_number,
            "decision_id": str(upstream_id),
            "admitted": admitted,
            "reason": reason,
        },
    )
    return AdmissionDecision(
        decision="admitted" if admitted else "denied",
        admitted=admitted,
        reason=reason,
        tenant_id=tenant_id,
        actor_id=actor_id,
        trial_number=trial_number,
        decision_id=str(upstream_id),
        decided_at=upstream_at if isinstance(upstream_at, datetime) else now,
        binding_constraint=binding,
    )
