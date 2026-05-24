# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
# pyright: reportUnnecessaryIsInstance=false
"""Runtime spine + TAOD lifecycle for ``kailash.delegate`` (S6 of #1035).

Composes the existing Delegate primitives — ``DispatchSurface`` (S5),
``AuditChainEngine`` (S4), ``TenantScopedCascade`` (S3),
``DelegateConstraintEnvelope`` (S2.5), ``DelegateIdentity`` (S2) — into the
audit-grade TAOD (Think-Act-Observe-Decide) execution lifecycle per the
CARE Mirror Thesis.

Cross-impl parity: Mirrors rs ``kailash-delegate-runtime`` (S6 substrate).
The TAOD state-machine phase order, the per-phase audit event emission,
the R2 composition contract, and the ``Posture`` enum admit byte-shape
parity with the rs reference. ``RuntimeExecutionResult.to_dict`` /
``from_dict`` round-trip is the wire-format contract.

Invariants (within budget per ``autonomous-execution.md`` MUST Rule 1 —
six invariants total):

1. **Phase monotonicity** — TAOD transitions are append-only; once
   ``COMPLETED`` or ``FAILED``, no further transitions are accepted
   (raises :class:`RuntimePhaseError`).
2. **Posture gating at THINKING** — every ``execute()`` reads the CURRENT
   :class:`Posture` at THINKING phase entry (not bind-time). ``HALT``
   refuses; downgrades are silently respected.
3. **Audit binding** — every TAOD transition emits exactly one audit event
   whose payload carries the ``run_id`` (cryptographic binding via the
   bound signer per S5 C2-1 fix). A run is replayable from the audit
   chain by ``run_id``.
4. **R2 composition re-check** — :meth:`R2Composition.validate` runs at
   construction AND at the start of every ``execute()`` (defense-in-depth
   per S5 C4-1 pattern; a component reconstructed externally between
   constructions cannot silently break the composition).
5. **No silent posture downgrade** — :meth:`DelegateRuntime.with_posture`
   accepts downgrades freely; upgrades require an explicit
   ``human_acknowledged_nonce`` per ``rules/trust-posture.md`` MUST
   Rule 3 (refuses with :class:`RuntimePostureBlockedError`).
6. **Signer identity** — the ``audit_engine``'s signer reference MUST be
   the SAME object (``is`` check, not ``==``) as the DispatchSurface's
   signer. A drifted signer is signature forgery against the audit
   trail and is BLOCKED at composition validation.

The TAOD state machine::

    INITIATED → THINKING → ACTING → OBSERVING → DECIDING → COMPLETED
                                            ╲
                                             ╲→ COMPLETED (early exit;
                                                no decision required)
                                       ╲
                                        ╲→ FAILED (terminal — any phase error)

The runtime is the spine; framework specialists (kaizen/nexus/dataflow)
compose ON it, never re-implement it. Per ``orphan-detection.md`` Rule 1
this module is the production hot path that calls
:meth:`DispatchSurface.dispatch` directly — there is no further
indirection.

Note on Posture integration: this shard accepts a :class:`Posture` as a
constructor parameter and gates ``execute()`` at THINKING on it. Runtime
integration with the ``.claude/learning/posture.json`` state file
(SessionStart-managed) is S8 e2e scope, NOT S6 — keeping S6's surface
area bounded to the spine itself.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from kailash.delegate.audit import AuditChainEngine, DelegateEventType
from kailash.delegate.dispatch import DispatchResult, DispatchSurface
from kailash.delegate.envelope import DelegateConstraintEnvelope
from kailash.delegate.trust import TenantScope, TenantScopedCascade
from kailash.delegate.types import DelegateIdentity, LifecycleState
from kailash.trust._json import canonical_json_dumps

logger = logging.getLogger(__name__)

__all__ = [
    "DelegateRuntime",
    "Posture",
    "R2Composition",
    "R2CompositionError",
    "RuntimeCompositionError",
    "RuntimeExecutionResult",
    "RuntimePhaseError",
    "RuntimePostureBlockedError",
    "TAODState",
    "TAODTransition",
]


# ---------------------------------------------------------------------------
# Posture enum — graduated autonomy ladder (R2 composition gate)
# ---------------------------------------------------------------------------


# Minimum length for a structurally-acceptable posture-upgrade nonce.
# The runtime's check is SYNTACTIC ONLY — cryptographic nonce validation
# (single-use, signed by human authority, expiry) lives in SessionStart /
# S8 nonce-registry integration. The length floor closes the trivial
# truthy-string bypass surfaced at S6 Round 1 (C1): with no minimum, any
# non-empty string (e.g. " ") satisfied the gate and produced a fake
# safety property semantically indistinguishable from S5 C2-1 fake
# authentication. 16 chars is the symmetric mirror of the rs reference's
# minimum-length placeholder for the same gate; both sides converge on
# the same floor so cross-SDK posture-rotation receipts remain comparable.
_MIN_NONCE_LENGTH: int = 16


class Posture(str, Enum):
    """Graduated autonomy posture per ``rules/trust-posture.md``.

    Mirrors rs ``Posture`` enum (S6 substrate). Sub-class of :class:`str`
    per ``eatp.md`` SDK convention so the on-wire form is the bare string
    value (cross-SDK canonical JSON consumes the value directly; no
    re-encoding step).

    Operative posture is the MINIMUM of the operator's per-operator
    posture and the repo floor — this enum encodes the ladder; the
    runtime's per-execute() gate at THINKING applies the value.

    HALT is the emergency stop: any execute() against a HALT-postured
    runtime refuses immediately at THINKING phase with
    :class:`RuntimePostureBlockedError`.
    """

    L5_DELEGATED = "L5_DELEGATED"
    L4_CONTINUOUS_INSIGHT = "L4_CONTINUOUS_INSIGHT"
    L3_SHARED_PLANNING = "L3_SHARED_PLANNING"
    L2_SUPERVISED = "L2_SUPERVISED"
    L1_PSEUDO_AGENT = "L1_PSEUDO_AGENT"
    HALT = "HALT"

    @property
    def _rank(self) -> int:
        """Internal ordinal for monotonic comparison.

        Higher rank = more autonomy. HALT is the floor (rank 0); L5 is
        the ceiling. Used by :meth:`DelegateRuntime.with_posture` to
        distinguish downgrades (silent) from upgrades (refuse without
        nonce).
        """
        ladder = {
            Posture.HALT: 0,
            Posture.L1_PSEUDO_AGENT: 1,
            Posture.L2_SUPERVISED: 2,
            Posture.L3_SHARED_PLANNING: 3,
            Posture.L4_CONTINUOUS_INSIGHT: 4,
            Posture.L5_DELEGATED: 5,
        }
        return ladder[self]


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------


class RuntimeCompositionError(ValueError):
    """Raised when the runtime composition contract is violated.

    Construction-time check that the spine's primitives form a
    consistent triplet: identity.principal_id is grantable per the
    cascade; envelope.tenant_scope matches the cascade's scope;
    audit_engine and dispatch_surface share the same signer reference.

    Distinct from :class:`R2CompositionError` (the R2 re-check at
    execute() start, defense-in-depth); this error is the bind-time
    structural fault.
    """


class RuntimePostureBlockedError(ValueError):
    """Raised when posture refuses an operation.

    Two cases surface here:

    - :attr:`Posture.HALT` at THINKING phase — every execute() under a
      HALT-postured runtime fails fast.
    - :meth:`DelegateRuntime.with_posture` upgrade without a
      ``human_acknowledged_nonce`` — per ``rules/trust-posture.md``
      MUST Rule 3, posture upgrades require explicit human acknowledgement.
    """


class RuntimePhaseError(ValueError):
    """Raised when an illegal TAOD phase transition is attempted.

    Phase monotonicity (Invariant 1) — transitions are append-only;
    once :attr:`TAODState.phase` is ``completed`` or ``failed``, no
    further transitions are accepted. Distinct from
    :class:`RuntimePostureBlockedError` (posture refuses; phase machine
    untouched).
    """


class R2CompositionError(ValueError):
    """Raised when R2 composition validation fails.

    The R2 (Reasoning + Reliability composition) gate validates that
    (envelope, cascade, dispatch_surface) form a consistent triplet AND
    that audit_engine + dispatch_surface share the same signer reference.
    Fired at construction AND at every execute() start (defense-in-depth
    against external component reconstruction between the two).

    Distinct from :class:`RuntimeCompositionError` (the bind-time
    structural fault) — this error is specifically the R2 re-check
    failure mode, surfaced separately so callers can distinguish initial
    construction faults from runtime composition drift.
    """


# ---------------------------------------------------------------------------
# TAOD state machine
# ---------------------------------------------------------------------------


# Literal type pinning the legal phase values. The dataclass field is
# annotated against this so a typo in a phase name surfaces at static-check
# time, not at runtime.
TAODPhase = Literal[
    "initiated",
    "thinking",
    "acting",
    "observing",
    "deciding",
    "completed",
    "failed",
]


@dataclass(frozen=True, slots=True)
class TAODTransition:
    """One phase transition recorded on a :class:`TAODState`.

    Mirrors rs ``TaodTransition`` struct (S6 substrate). Frozen + slots
    per the S2/S3/S4/S5 dataclass conventions. Append-only history of
    transitions for audit + cross-SDK receipt comparison.

    Attributes:
        from_phase: The phase the state was IN before this transition.
        to_phase: The phase the state moved TO.
        at: tz-aware UTC datetime of the transition.
        reason: Optional human-readable reason. ``None`` for normal
            phase advancement; populated on FAILED transitions with the
            error class name + message.
    """

    from_phase: str
    to_phase: str
    at: datetime
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.from_phase, str) or not self.from_phase:
            raise TypeError(
                "TAODTransition.from_phase MUST be a non-empty str; got "
                f"{type(self.from_phase).__name__}={self.from_phase!r}"
            )
        if not isinstance(self.to_phase, str) or not self.to_phase:
            raise TypeError(
                "TAODTransition.to_phase MUST be a non-empty str; got "
                f"{type(self.to_phase).__name__}={self.to_phase!r}"
            )
        if not isinstance(self.at, datetime):
            raise TypeError(
                "TAODTransition.at MUST be a datetime; got " f"{type(self.at).__name__}"
            )
        if self.at.tzinfo is None:
            raise ValueError(
                "TAODTransition.at MUST be timezone-aware (naive "
                "datetimes break cross-SDK wire-format parity)"
            )
        if self.reason is not None and not isinstance(self.reason, str):
            raise TypeError(
                "TAODTransition.reason MUST be str or None; got "
                f"{type(self.reason).__name__}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-canonical dict (cross-SDK wire-format).

        Mirrors rs ``TaodTransition`` serde encoding. ``at`` is
        ISO-8601 UTC; ``reason`` omitted when ``None`` to preserve the
        rs serde-skip-if-none semantics.
        """
        payload: dict[str, Any] = {
            "from_phase": self.from_phase,
            "to_phase": self.to_phase,
            "at": self.at.isoformat(),
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TAODTransition":
        """Reconstruct from a :meth:`to_dict` payload.

        Round-trip lossless on all fields. ``at`` is parsed via
        :meth:`datetime.fromisoformat`; ``reason`` defaults to ``None``
        when absent (mirrors the rs serde-skip-if-none semantics).
        """
        if not isinstance(data, dict):
            raise TypeError(
                "TAODTransition.from_dict requires a dict; got "
                f"{type(data).__name__}"
            )
        for required in ("from_phase", "to_phase", "at"):
            if required not in data:
                raise ValueError(
                    f"TAODTransition.from_dict missing required field {required!r}"
                )
        at_raw = data["at"]
        if not isinstance(at_raw, str):
            raise TypeError(
                "TAODTransition.from_dict 'at' MUST be an ISO-8601 str; got "
                f"{type(at_raw).__name__}"
            )
        return cls(
            from_phase=data["from_phase"],
            to_phase=data["to_phase"],
            at=datetime.fromisoformat(at_raw),
            reason=data.get("reason"),
        )


# Phases that admit no further transitions (terminal). Module-level
# constant so it does NOT become an init=False dataclass field (which
# would conflict with frozen + slots and add per-instance storage).
_TERMINAL_PHASES: frozenset[str] = frozenset({"completed", "failed"})

# Legal successor map per phase. Module-level constant; one structural
# contract; tests pin every edge.
_LEGAL_SUCCESSORS: dict[str, frozenset[str]] = {
    "initiated": frozenset({"thinking", "failed"}),
    "thinking": frozenset({"acting", "failed"}),
    "acting": frozenset({"observing", "failed"}),
    "observing": frozenset({"deciding", "completed", "failed"}),
    "deciding": frozenset({"completed", "failed"}),
}


@dataclass(frozen=True, slots=True)
class TAODState:
    """The TAOD lifecycle state for one runtime execution.

    Mirrors rs ``TaodState`` struct (S6 substrate). Frozen + slots — a
    state transition produces a NEW :class:`TAODState` (the runtime
    holds the latest internally; the
    :class:`RuntimeExecutionResult` carries the final state).
    Append-only :attr:`transitions` are the audit-of-audit: every
    state mutation MUST be reflected as a transition entry.

    The phase axis follows the CARE Mirror Thesis TAOD lifecycle:

    - ``initiated`` — entry state; no work attempted yet.
    - ``thinking`` — read posture + plan dispatch.
    - ``acting`` — invoke the dispatch surface.
    - ``observing`` — cross-validate the dispatch result.
    - ``deciding`` — process a decision-required result.
    - ``completed`` — terminal success.
    - ``failed`` — terminal failure (any phase error).

    Attributes:
        phase: The current phase. Once ``completed`` or ``failed``, the
            state is terminal — :meth:`advance_to` raises on further
            transitions (Invariant 1).
        started_at: tz-aware UTC datetime the state machine entered
            ``initiated``.
        transitions: Append-only tuple of every phase transition (with
            timestamps + optional reasons).
    """

    phase: TAODPhase
    started_at: datetime
    transitions: tuple[TAODTransition, ...] = ()

    def __post_init__(self) -> None:
        # Cannot validate against the Literal type at runtime — the
        # union's members are strings — so re-derive the allowlist
        # explicitly. Drift between this set and TAODPhase is a typed
        # contract that the unit tests pin.
        valid_phases = {
            "initiated",
            "thinking",
            "acting",
            "observing",
            "deciding",
            "completed",
            "failed",
        }
        if self.phase not in valid_phases:
            raise ValueError(
                f"TAODState.phase {self.phase!r} is not a known TAODPhase "
                f"(valid: {sorted(valid_phases)})"
            )
        if not isinstance(self.started_at, datetime):
            raise TypeError(
                "TAODState.started_at MUST be a datetime; got "
                f"{type(self.started_at).__name__}"
            )
        if self.started_at.tzinfo is None:
            raise ValueError(
                "TAODState.started_at MUST be timezone-aware (naive "
                "datetimes break cross-SDK wire-format parity)"
            )
        if not isinstance(self.transitions, tuple):
            raise TypeError(
                "TAODState.transitions MUST be a tuple; got "
                f"{type(self.transitions).__name__}"
            )
        for t in self.transitions:
            if not isinstance(t, TAODTransition):
                raise TypeError(
                    "TAODState.transitions entries MUST be TAODTransition; "
                    f"got {type(t).__name__}"
                )

    @property
    def is_terminal(self) -> bool:
        """True iff the state is in a terminal phase (``completed`` /
        ``failed``).

        Used by :meth:`advance_to` to enforce Invariant 1 (phase
        monotonicity — once terminal, no further transitions accepted).
        """
        return self.phase in _TERMINAL_PHASES

    def advance_to(
        self,
        next_phase: TAODPhase,
        *,
        reason: str | None = None,
        at: datetime | None = None,
    ) -> "TAODState":
        """Return a NEW :class:`TAODState` advanced to ``next_phase``.

        Append-only — Invariant 1 (phase monotonicity). Raises
        :class:`RuntimePhaseError` if the current phase is already
        terminal (``completed`` / ``failed``).

        Per the TAOD machine definition, the LEGAL successor set per
        phase is enumerated below. Any other transition raises.

        Args:
            next_phase: The phase to advance to.
            reason: Optional reason recorded on the
                :class:`TAODTransition`; required on FAILED transitions
                so post-incident analysis can attribute the failure.
            at: Optional tz-aware datetime; defaults to
                ``datetime.now(timezone.utc)``.

        Returns:
            A NEW :class:`TAODState` with the advanced phase and the
            appended transition.

        Raises:
            RuntimePhaseError: terminal-state transition attempt OR
                illegal successor for the current phase.
        """
        if self.is_terminal:
            raise RuntimePhaseError(
                f"TAODState is terminal (phase={self.phase!r}); no further "
                f"transitions accepted (Invariant 1 — phase monotonicity). "
                f"Attempted next_phase={next_phase!r}."
            )
        legal_successors = _LEGAL_SUCCESSORS.get(self.phase, frozenset())
        if next_phase not in legal_successors:
            raise RuntimePhaseError(
                f"Illegal TAOD transition from {self.phase!r} to "
                f"{next_phase!r}; legal successors: "
                f"{sorted(legal_successors)}"
            )
        at_resolved = at if at is not None else datetime.now(timezone.utc)
        transition = TAODTransition(
            from_phase=self.phase,
            to_phase=next_phase,
            at=at_resolved,
            reason=reason,
        )
        return TAODState(
            phase=next_phase,
            started_at=self.started_at,
            transitions=self.transitions + (transition,),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-canonical dict (cross-SDK wire-format).

        Mirrors rs ``TaodState`` serde encoding. ``started_at`` is
        ISO-8601 UTC; ``transitions`` is a list (not tuple) for JSON
        compatibility.
        """
        return {
            "phase": self.phase,
            "started_at": self.started_at.isoformat(),
            "transitions": [t.to_dict() for t in self.transitions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TAODState":
        """Reconstruct from a :meth:`to_dict` payload.

        Round-trip lossless on all fields. The phase value is validated
        against the legal phase allowlist via ``__post_init__``.
        """
        if not isinstance(data, dict):
            raise TypeError(
                "TAODState.from_dict requires a dict; got " f"{type(data).__name__}"
            )
        for required in ("phase", "started_at", "transitions"):
            if required not in data:
                raise ValueError(
                    f"TAODState.from_dict missing required field {required!r}"
                )
        started_raw = data["started_at"]
        if not isinstance(started_raw, str):
            raise TypeError(
                "TAODState.from_dict 'started_at' MUST be an ISO-8601 str; "
                f"got {type(started_raw).__name__}"
            )
        transitions_raw = data["transitions"]
        if not isinstance(transitions_raw, (list, tuple)):
            raise TypeError(
                "TAODState.from_dict 'transitions' MUST be a list/tuple; got "
                f"{type(transitions_raw).__name__}"
            )
        return cls(
            phase=data["phase"],
            started_at=datetime.fromisoformat(started_raw),
            transitions=tuple(TAODTransition.from_dict(t) for t in transitions_raw),
        )


# ---------------------------------------------------------------------------
# RuntimeExecutionResult — the spine's return value
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RuntimeExecutionResult:
    """The result of one :meth:`DelegateRuntime.execute` call.

    Mirrors rs ``RuntimeExecutionResult`` struct (S6 substrate). The
    :meth:`to_dict` / :meth:`from_dict` round-trip is the cross-SDK
    receipt contract — both SDKs MUST produce byte-identical payloads
    for identical input under identical envelopes (per
    ``cross-sdk-inspection.md`` Rule 4).

    Frozen + slots per the S3/S4/S5 dataclass conventions. Returned by
    :meth:`DelegateRuntime.execute` on every code path (success,
    posture-blocked, composition-failed). Failure paths populate
    :attr:`dispatch_result` with ``None`` and the :attr:`taod_state`
    with a transition trail ending in ``failed``.

    Attributes:
        run_id: Unique UUID for this execution. Cryptographically bound
            into every audit event the runtime emits (Invariant 3).
            Generated from :func:`secrets.token_bytes` per security best
            practice (NOT :func:`uuid.uuid4` which uses the
            non-cryptographic ``random`` module).
        dispatch_result: The :class:`DispatchResult` from the bound
            DispatchSurface. ``None`` when execution failed before the
            ACTING phase produced a result (posture-blocked,
            composition-failed, validation-failed).
        taod_state: The final :class:`TAODState`, including the full
            transition trail. A reader can replay the run's TAOD
            history from this single attribute.
        audit_head_hash: SHA-256 hex of the audit chain's head entry
            AFTER execution completed. ``None`` ONLY when the runtime
            failed before emitting any audit event (e.g. composition
            failure). Used by downstream receipt construction to anchor
            the run into the broader chain-of-custody.
        terminated_at: tz-aware UTC datetime the runtime returned
            control to the caller (success or failure).
        posture_at_execute: The :class:`Posture` the runtime ran under
            for this execute() call. Captured at THINKING phase entry
            (Invariant 2 — posture is read at execute time, not at
            bind time).
    """

    run_id: uuid.UUID
    dispatch_result: DispatchResult | None
    taod_state: TAODState
    audit_head_hash: str | None
    terminated_at: datetime
    posture_at_execute: Posture

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, uuid.UUID):
            raise TypeError(
                "RuntimeExecutionResult.run_id MUST be a uuid.UUID; got "
                f"{type(self.run_id).__name__}"
            )
        if self.dispatch_result is not None and not isinstance(
            self.dispatch_result, DispatchResult
        ):
            raise TypeError(
                "RuntimeExecutionResult.dispatch_result MUST be a "
                f"DispatchResult or None; got {type(self.dispatch_result).__name__}"
            )
        if not isinstance(self.taod_state, TAODState):
            raise TypeError(
                "RuntimeExecutionResult.taod_state MUST be a TAODState; got "
                f"{type(self.taod_state).__name__}"
            )
        if self.audit_head_hash is not None and not isinstance(
            self.audit_head_hash, str
        ):
            raise TypeError(
                "RuntimeExecutionResult.audit_head_hash MUST be str or None; "
                f"got {type(self.audit_head_hash).__name__}"
            )
        if not isinstance(self.terminated_at, datetime):
            raise TypeError(
                "RuntimeExecutionResult.terminated_at MUST be a datetime; got "
                f"{type(self.terminated_at).__name__}"
            )
        if self.terminated_at.tzinfo is None:
            raise ValueError(
                "RuntimeExecutionResult.terminated_at MUST be timezone-aware "
                "(naive datetimes break cross-SDK wire-format parity)"
            )
        if not isinstance(self.posture_at_execute, Posture):
            raise TypeError(
                "RuntimeExecutionResult.posture_at_execute MUST be a Posture; "
                f"got {type(self.posture_at_execute).__name__}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-canonical dict (cross-SDK wire-format).

        Mirrors rs ``RuntimeExecutionResult`` serde encoding. ``run_id``
        is the canonical UUID string; ``dispatch_result`` is None or
        the nested DispatchResult dict; ``audit_head_hash`` is None or
        the hex string; ``posture_at_execute`` is the enum string value.
        """
        return {
            "run_id": str(self.run_id),
            "dispatch_result": (
                self.dispatch_result.to_dict()
                if self.dispatch_result is not None
                else None
            ),
            "taod_state": self.taod_state.to_dict(),
            "audit_head_hash": self.audit_head_hash,
            "terminated_at": self.terminated_at.isoformat(),
            "posture_at_execute": self.posture_at_execute.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeExecutionResult":
        """Reconstruct from a :meth:`to_dict` payload.

        Round-trip lossless on all fields. ``run_id`` parsed via
        :class:`uuid.UUID`; ``dispatch_result`` reconstructed via
        :meth:`DispatchResult.from_dict` when non-None;
        ``posture_at_execute`` validated against the
        :class:`Posture` enum.
        """
        if not isinstance(data, dict):
            raise TypeError(
                "RuntimeExecutionResult.from_dict requires a dict; got "
                f"{type(data).__name__}"
            )
        for required in (
            "run_id",
            "dispatch_result",
            "taod_state",
            "audit_head_hash",
            "terminated_at",
            "posture_at_execute",
        ):
            if required not in data:
                raise ValueError(
                    f"RuntimeExecutionResult.from_dict missing required field "
                    f"{required!r}"
                )
        dispatch_raw = data["dispatch_result"]
        dispatch_result = (
            DispatchResult.from_dict(dispatch_raw) if dispatch_raw is not None else None
        )
        terminated_raw = data["terminated_at"]
        if not isinstance(terminated_raw, str):
            raise TypeError(
                "RuntimeExecutionResult.from_dict 'terminated_at' MUST be an "
                f"ISO-8601 str; got {type(terminated_raw).__name__}"
            )
        return cls(
            run_id=uuid.UUID(data["run_id"]),
            dispatch_result=dispatch_result,
            taod_state=TAODState.from_dict(data["taod_state"]),
            audit_head_hash=data["audit_head_hash"],
            terminated_at=datetime.fromisoformat(terminated_raw),
            posture_at_execute=Posture(data["posture_at_execute"]),
        )


# ---------------------------------------------------------------------------
# R2Composition — composition validator (defense-in-depth)
# ---------------------------------------------------------------------------


class R2Composition:
    """Validator for the R2 (Reasoning + Reliability) composition contract.

    Mirrors rs ``R2Composition`` (S6 substrate). The R2 gate validates
    that (envelope, cascade, dispatch_surface) form a consistent triplet
    AND that audit_engine + dispatch_surface share the SAME signer
    reference object (``is`` check, not ``==``; signature forgery
    defense per Invariant 6).

    Called once at :meth:`DelegateRuntime.__init__` AND again at every
    :meth:`DelegateRuntime.execute` start (defense-in-depth per the S5
    C4-1 pattern — a component reconstructed externally between the two
    cannot silently break the composition).

    Per ``orphan-detection.md`` Rule 1 this validator is the framework's
    R2 gate; the runtime calls it directly — no further indirection.
    """

    @staticmethod
    def validate(
        *,
        envelope: DelegateConstraintEnvelope,
        cascade: TenantScopedCascade,
        dispatch_surface: DispatchSurface,
        audit_engine: AuditChainEngine,
        signer: Callable[[bytes], str],
    ) -> None:
        """Validate the R2 composition triplet + signer identity.

        Raises:
            R2CompositionError: tenant scope mismatch, envelope-swap
                detected (post-bind identity inequality), signer
                identity mismatch between audit_engine and
                dispatch_surface.
            TypeError: any argument fails its isinstance check.
        """
        if not isinstance(envelope, DelegateConstraintEnvelope):
            raise TypeError(
                "R2Composition.validate(envelope) MUST be a "
                f"DelegateConstraintEnvelope; got {type(envelope).__name__}"
            )
        if not isinstance(cascade, TenantScopedCascade):
            raise TypeError(
                "R2Composition.validate(cascade) MUST be a "
                f"TenantScopedCascade; got {type(cascade).__name__}"
            )
        if not isinstance(dispatch_surface, DispatchSurface):
            raise TypeError(
                "R2Composition.validate(dispatch_surface) MUST be a "
                f"DispatchSurface; got {type(dispatch_surface).__name__}"
            )
        if not isinstance(audit_engine, AuditChainEngine):
            raise TypeError(
                "R2Composition.validate(audit_engine) MUST be an "
                f"AuditChainEngine; got {type(audit_engine).__name__}"
            )
        if not callable(signer):
            raise TypeError(
                "R2Composition.validate(signer) MUST be callable; got "
                f"{type(signer).__name__}"
            )

        # Envelope identity check — defense against post-bind envelope
        # swap. The DispatchSurface's bound envelope MUST be the same
        # object as the runtime's envelope (`is` check). A value-equal
        # but distinct envelope is the substitution attack this guard
        # closes (R2-substrate finding).
        if dispatch_surface.envelope is not envelope:
            raise R2CompositionError(
                "R2 composition mismatch: dispatch_surface.envelope is not "
                "the same object as the runtime's envelope; an envelope "
                "swap between bind and execute is forbidden (Invariant 4 — "
                "R2 composition gate)"
            )

        # Tenant scope alignment — envelope's genesis_id-derived scope
        # must match the cascade's tenant scope. The current envelope
        # primitive carries only genesis_id (no explicit tenant scope
        # field — see envelope.py); the cascade is the authoritative
        # tenant anchor. Cross-check via the DispatchSurface's bound
        # cascade reference: it MUST be the same object as the runtime's
        # cascade.
        if dispatch_surface.trust_cascade is not cascade:
            raise R2CompositionError(
                "R2 composition mismatch: dispatch_surface.trust_cascade is "
                "not the same object as the runtime's cascade; a cascade "
                "swap between bind and execute is forbidden (Invariant 4 — "
                "R2 composition gate)"
            )

        # Cascade tenant scope structural sanity — both Global and
        # Tenant variants are valid; the runtime accepts either as long
        # as the cascade and dispatch_surface agree (checked above).
        # The redundant isinstance check below catches the case where
        # the cascade's tenant attribute was externally replaced with
        # a non-TenantScope object (sub-microsecond cost; structural
        # defense against external mutation of the cascade post-bind).
        if not isinstance(cascade.tenant, TenantScope):
            raise R2CompositionError(
                "R2 composition mismatch: cascade.tenant is not a "
                f"TenantScope; got {type(cascade.tenant).__name__} (cascade "
                "tenant axis corrupted between bind and execute)"
            )

        # Signer identity check (Invariant 6) — the audit_engine and
        # the dispatch_surface MUST share the same signer reference.
        # `is` is the load-bearing check: two distinct callables with
        # value-identical output STILL constitute signature forgery if
        # one of them was substituted post-bind. The DispatchSurface
        # holds its signer at `_signer`; AuditChainEngine does not
        # itself hold a signer (signer is per-emission by the dispatch
        # path), so the check reduces to "dispatch_surface._signer is
        # signer" — the runtime-provided signer MUST be the same object
        # as the dispatch surface's signer.
        if dispatch_surface._signer is not signer:
            raise R2CompositionError(
                "R2 composition mismatch: dispatch_surface signer is not "
                "the same object as the runtime's signer; signer drift "
                "between bind and execute is signature forgery against the "
                "audit trail (Invariant 6 — signer identity)"
            )


# ---------------------------------------------------------------------------
# DelegateRuntime — the spine
# ---------------------------------------------------------------------------


def _generate_run_id() -> uuid.UUID:
    """Generate a UUID4 backed by :mod:`secrets`, not :mod:`random`.

    Per ``rules/security.md`` (no hardcoded weak randomness). The
    stdlib's :func:`uuid.uuid4` historically uses :func:`os.urandom`
    (which IS cryptographically strong) — but we route through
    :func:`secrets.token_bytes` to make the cryptographic-strength
    guarantee explicit and audit-grep-able. The byte layout is the
    standard UUID4 RFC 4122 § 4.1.3 representation: 16 bytes with the
    version + variant bits set.
    """
    raw = bytearray(secrets.token_bytes(16))
    # Set version 4 (bits 12-15 of clock_seq_hi_and_reserved → 0100).
    raw[6] = (raw[6] & 0x0F) | 0x40
    # Set variant RFC 4122 (bits 6-7 of clock_seq_hi_and_reserved → 10).
    raw[8] = (raw[8] & 0x3F) | 0x80
    return uuid.UUID(bytes=bytes(raw))


class DelegateRuntime:
    """The TAOD runtime spine that composes Delegate primitives.

    Cross-impl parity: Mirrors rs ``DelegateRuntime`` struct (S6
    substrate). The TAOD phase order, the per-phase audit event types,
    the R2 composition contract, and the Posture gating semantics admit
    cross-SDK ``receipts_agree(rs, py)`` verification at S7+.

    Per ``facade-manager-detection.md`` MUST Rule 3, every dependency is
    an EXPLICIT constructor parameter — no global lookup, no
    self-construction. Per ``orphan-detection.md`` MUST Rule 1, this
    runtime IS the framework hot path that calls
    :meth:`DispatchSurface.dispatch` directly — there is no further
    indirection.

    Args:
        dispatch_surface: The bound :class:`DispatchSurface` (S5). The
            runtime delegates the ACTING phase to this surface.
        audit_engine: The :class:`AuditChainEngine` (S4) that records
            every TAOD transition with run_id-bound payloads.
        cascade: The :class:`TenantScopedCascade` (S3) that anchors
            tenant isolation. MUST be the SAME object as the dispatch
            surface's bound cascade (R2 composition).
        envelope: The :class:`DelegateConstraintEnvelope` (S2.5). MUST
            be the SAME object as the dispatch surface's bound envelope
            (R2 composition).
        identity: The :class:`DelegateIdentity` (S2) flowing into every
            audit event as the signer identity.
        signer: Callable ``(canonical_bytes) -> hex_str`` producing
            Ed25519 hex signatures. MUST be the SAME object as the
            dispatch surface's bound signer (Invariant 6).
        posture: The starting :class:`Posture` for this runtime. Default
            :attr:`Posture.L5_DELEGATED`. Posture is read at execute()
            THINKING phase, so it can be mutated via
            :meth:`with_posture` between executions.

    Raises:
        RuntimeCompositionError: identity/cascade/envelope composition
            contract violation (e.g. identity.principal_id is not
            grantable per the cascade — see note below).
        R2CompositionError: R2 validation failed (envelope/cascade/signer
            identity mismatch).
        TypeError: any argument fails its isinstance check.

    Note on identity/cascade gateability: :class:`TenantScopedCascade`
    exposes a persistent grantee registry (``cascade.grantees`` —
    ``frozenset[UUID]``, populated by ``register_root_grantee`` and
    ``cascade_child``; #1146 H1). :class:`DispatchSurface` enforces
    ``identity.delegate_id in cascade.grantees`` at bind
    (``dispatch.py`` bind path) and re-checks at dispatch
    (``dispatch.py`` dispatch path). The runtime binds the same cascade
    object through the R2 composition gate, so the DispatchSurface
    grantee check IS the runtime's grantee gate by composition — no
    parallel registry is maintained here.
    """

    # Per-phase audit event mapping. Each TAOD transition emits exactly
    # one audit event (Invariant 3); this mapping is the contract. The
    # event types are drawn from the S4 DelegateEventType allowlist
    # (audit-visible variants only — REASONING_SCRATCHPAD excluded per
    # the engine's gate).
    _PHASE_EVENT_TYPES: dict[str, DelegateEventType] = {
        "thinking": DelegateEventType.CONSTRAINT_DECISION,
        "acting": DelegateEventType.EXTERNAL_SIDE_EFFECT,
        "observing": DelegateEventType.CONSTRAINT_DECISION,
        "deciding": DelegateEventType.GRANT_CONSUMPTION,
        "completed": DelegateEventType.GRANT_CONSUMPTION,
        "failed": DelegateEventType.POSTURE_OR_SOVEREIGN_HANDOVER,
    }

    def __init__(
        self,
        *,
        dispatch_surface: DispatchSurface,
        audit_engine: AuditChainEngine,
        cascade: TenantScopedCascade,
        envelope: DelegateConstraintEnvelope,
        identity: DelegateIdentity,
        signer: Callable[[bytes], str],
        posture: Posture = Posture.L5_DELEGATED,
    ) -> None:
        # Type discipline at the boundary — defense-in-depth on top of
        # each composed type's own post_init.
        if not isinstance(dispatch_surface, DispatchSurface):
            raise TypeError(
                "DelegateRuntime.dispatch_surface MUST be a DispatchSurface; "
                f"got {type(dispatch_surface).__name__}"
            )
        if not isinstance(audit_engine, AuditChainEngine):
            raise TypeError(
                "DelegateRuntime.audit_engine MUST be an AuditChainEngine; "
                f"got {type(audit_engine).__name__}"
            )
        if not isinstance(cascade, TenantScopedCascade):
            raise TypeError(
                "DelegateRuntime.cascade MUST be a TenantScopedCascade; got "
                f"{type(cascade).__name__}"
            )
        if not isinstance(envelope, DelegateConstraintEnvelope):
            raise TypeError(
                "DelegateRuntime.envelope MUST be a DelegateConstraintEnvelope; "
                f"got {type(envelope).__name__}"
            )
        if not isinstance(identity, DelegateIdentity):
            raise TypeError(
                "DelegateRuntime.identity MUST be a DelegateIdentity; got "
                f"{type(identity).__name__}"
            )
        if not callable(signer):
            raise TypeError(
                "DelegateRuntime.signer MUST be callable; got "
                f"{type(signer).__name__}"
            )
        if not isinstance(posture, Posture):
            raise TypeError(
                f"DelegateRuntime.posture MUST be a Posture; got "
                f"{type(posture).__name__}"
            )

        # R2 composition validation at construction (Invariant 4 —
        # part 1 of defense-in-depth; part 2 is the re-check at
        # execute() start).
        R2Composition.validate(
            envelope=envelope,
            cascade=cascade,
            dispatch_surface=dispatch_surface,
            audit_engine=audit_engine,
            signer=signer,
        )

        # Identity-cascade consistency (the runtime composition
        # contract). DispatchSurface already validated capability +
        # lifecycle at bind; the runtime confirms the dispatch surface's
        # identity is the SAME object as the runtime's identity (no
        # silent identity swap between bind and execute).
        if dispatch_surface.identity is not identity:
            raise RuntimeCompositionError(
                "Runtime composition mismatch: dispatch_surface.identity is "
                "not the same object as the runtime's identity; identity "
                "swap between bind and execute is BLOCKED."
            )

        # /redteam Round-1 C1 coherence check: the audit-engine and
        # cascade MUST be gated under the SAME Verifier CLASS so a
        # runtime whose audit chain is cryptographically gated has its
        # cascade gated under the same posture (and vice versa). A
        # split configuration (real Ed25519Verifier on audit +
        # NullVerifier on cascade) is structurally indistinguishable
        # from a partial C1 closure that leaves one half "fake
        # encryption". The check is on CLASS, not instance, because
        # callers may legitimately construct the two surfaces with
        # separate verifier instances over the same directory; what
        # matters is that both surfaces enforce the same gate posture.
        if type(audit_engine.verifier) is not type(cascade.verifier):  # noqa: E721
            raise RuntimeCompositionError(
                "Runtime composition mismatch: audit_engine.verifier "
                f"({type(audit_engine.verifier).__name__}) and "
                f"cascade.verifier ({type(cascade.verifier).__name__}) "
                "MUST be the same Verifier class so the cryptographic "
                "gate posture is consistent across the audit chain AND "
                "the cascade grant chain (#1035 C1 closure — partial "
                "wiring is indistinguishable from fake-encryption per "
                "zero-tolerance.md Rule 2)."
            )

        self._dispatch_surface = dispatch_surface
        self._audit_engine = audit_engine
        self._cascade = cascade
        self._envelope = envelope
        self._identity = identity
        self._signer = signer
        self._posture = posture
        # #1035 H1/F-11 closure: every runtime starts at LifecycleState.
        # PROPOSED. Transitions are driven via :meth:`advance_lifecycle`
        # which routes through :meth:`LifecycleState.advance_to` — the
        # D3 single-linear chain (Proposed → Instantiated →
        # PostureGraded → Active → Retired → Archived). The lifecycle
        # axis is independent of the TAOD per-run axis: TAOD governs
        # one execute() invocation; lifecycle governs the Delegate's
        # lifetime. Both are append-only and monotonic.
        self._lifecycle_state: LifecycleState = LifecycleState.PROPOSED
        # §7 TAOD phase monotonicity — runtime is single-shot per receipt.
        # Once execute() returns (success OR failure), the runtime is
        # consumed and further execute() calls raise RuntimePhaseError.
        # The receipt-bound run model requires fresh substrate per run:
        # an attacker that could retry-until-success on a runtime would
        # silently amplify their audit footprint without leaving a new
        # run_id-bound chain segment. Marked True in finally block of
        # execute() — EVERY exit path consumes (including FAILED), no
        # retry-amplification surface. with_posture() returns a fresh
        # runtime (un-consumed) per Invariant 5.
        self._consumed: bool = False

    @property
    def posture(self) -> Posture:
        """Borrow the current :class:`Posture` (read-only)."""
        return self._posture

    @property
    def dispatch_surface(self) -> DispatchSurface:
        """Borrow the bound :class:`DispatchSurface` (read-only)."""
        return self._dispatch_surface

    @property
    def audit_engine(self) -> AuditChainEngine:
        """Borrow the bound :class:`AuditChainEngine` (read-only)."""
        return self._audit_engine

    @property
    def cascade(self) -> TenantScopedCascade:
        """Borrow the bound :class:`TenantScopedCascade` (read-only)."""
        return self._cascade

    @property
    def envelope(self) -> DelegateConstraintEnvelope:
        """Borrow the bound :class:`DelegateConstraintEnvelope` (read-only)."""
        return self._envelope

    @property
    def identity(self) -> DelegateIdentity:
        """Borrow the bound :class:`DelegateIdentity` (read-only)."""
        return self._identity

    @property
    def lifecycle_state(
        self,
    ) -> LifecycleState:
        """Borrow the current :class:`LifecycleState` (#1035 H1/F-11).

        Returns the D3 lifecycle state — Proposed at construction; the
        runtime traverses the chain via :meth:`advance_lifecycle`.
        Read-only; transitions MUST go through :meth:`advance_lifecycle`
        so each edge is validated by :meth:`LifecycleState.advance_to`.
        """
        return self._lifecycle_state

    def advance_lifecycle(self, target: LifecycleState) -> LifecycleState:
        """Advance to ``target`` lifecycle state iff legal (#1035 H1/F-11).

        Routes through :meth:`LifecycleState.advance_to` — the D3
        single-linear chain (Proposed → Instantiated → PostureGraded →
        Active → Retired → Archived). Arbitrary jumps, backward edges,
        and post-Archived transitions raise :class:`LifecycleError`.

        Args:
            target: The desired next :class:`LifecycleState`.

        Returns:
            The new :class:`LifecycleState` (== ``target`` on success).

        Raises:
            LifecycleError: ``target`` is not the unique legal successor.
            TypeError: ``target`` is not a :class:`LifecycleState`.
        """
        # advance_to itself raises LifecycleError on illegal edges +
        # TypeError on wrong type — both surface here unchanged. The
        # state mutation happens AFTER the validation, so a failed
        # transition leaves self._lifecycle_state unchanged (mirrors
        # the TAOD pattern at TAODState.advance_to).
        self._lifecycle_state = self._lifecycle_state.advance_to(target)
        return self._lifecycle_state

    def with_posture(
        self,
        posture: Posture,
        *,
        human_acknowledged_nonce: str | None = None,
    ) -> "DelegateRuntime":
        """Return a NEW runtime with the posture changed.

        Per Invariant 5: downgrades (lower rank) are accepted silently;
        upgrades (higher rank) require an explicit
        ``human_acknowledged_nonce`` per ``rules/trust-posture.md``
        MUST Rule 3.

        Args:
            posture: The new :class:`Posture` to bind.
            human_acknowledged_nonce: Required for upgrades. The
                runtime's nonce check is purely **SYNTACTIC**: it
                rejects empty AND short (``< _MIN_NONCE_LENGTH`` = 16
                chars) values only. Cryptographic nonce validation
                (single-use, signed by human authority, expiry) is
                **deferred to SessionStart / S8 nonce-registry
                integration**; the runtime's gate is a structural
                placeholder, NOT a cryptographic check. Callers MUST
                treat this gate as the trivial-bypass closure (no
                empty / one-char nonces) and rely on S8 to harden
                against replayed-or-forged nonces.

        Returns:
            A NEW :class:`DelegateRuntime` with the changed posture,
            preserving all other bindings.

        Raises:
            RuntimePostureBlockedError: upgrade attempted without a
                ``human_acknowledged_nonce`` of length
                ``>= _MIN_NONCE_LENGTH`` (16) characters, OR audit
                emission of the posture-rotation event failed (the
                rotation is structurally invalid if it cannot be
                audited).
            TypeError: ``posture`` is not a :class:`Posture` value.
        """
        if not isinstance(posture, Posture):
            raise TypeError(
                f"with_posture(posture) MUST be a Posture; got "
                f"{type(posture).__name__}"
            )
        # Distinguish downgrades from upgrades by rank. Equal rank
        # (same posture) is a no-op upgrade (rank delta zero) and is
        # admitted without a nonce.
        if posture._rank > self._posture._rank:
            nonce_length = (
                len(human_acknowledged_nonce) if human_acknowledged_nonce else 0
            )
            if nonce_length < _MIN_NONCE_LENGTH:
                raise RuntimePostureBlockedError(
                    f"Posture upgrade {self._posture.value!r} → "
                    f"{posture.value!r} requires human_acknowledged_nonce "
                    f"of length >= {_MIN_NONCE_LENGTH} (got {nonce_length}); "
                    "runtime's check is a SYNTACTIC placeholder — "
                    "cryptographic validation lives in SessionStart/S8 "
                    "nonce-registry integration (rules/trust-posture.md "
                    "MUST Rule 3)"
                )

        # Emit a POSTURE_OR_SOVEREIGN_HANDOVER audit event on the
        # SOURCE runtime's audit engine BEFORE returning the new
        # runtime. Posture rotations (both upgrades AND downgrades)
        # are security-relevant transitions: an attacker holding a
        # legitimate L5_DELEGATED runtime that could call
        # ``with_posture(L1)`` without an audit trail would leave the
        # downgrade invisible to forensic correlation. Audit-before-
        # rotate is the S6 R1 MED-1 fix; if the audit emission fails,
        # the rotation is refused (structurally invalid: a rotation
        # that cannot be audited cannot be trusted). This mirrors the
        # S6 R1 A3/D1 emit-before-state-advance invariant applied to
        # the posture transition surface.
        rotation_payload = {
            "rotation_id": str(uuid.UUID(bytes=secrets.token_bytes(16), version=4)),
            "from_posture": self._posture.value,
            "to_posture": posture.value,
            "rank_delta": posture._rank - self._posture._rank,
            "nonce_present": bool(human_acknowledged_nonce),
        }
        try:
            canonical_bytes = canonical_json_dumps(rotation_payload).encode("utf-8")
            signature = self._signer(canonical_bytes)
            self._audit_engine.emit_event(
                event_type=DelegateEventType.POSTURE_OR_SOVEREIGN_HANDOVER.value,
                payload=rotation_payload,
                signer_identity=self._identity,
                signature=signature,
            )
        except Exception as audit_exc:
            # The rotation MUST be observable; failing-closed here
            # converts an unauditable rotation into a typed refusal
            # the caller can catch and surface. Same severity class
            # as the upgrade-without-nonce refusal — the rotation is
            # structurally invalid.
            raise RuntimePostureBlockedError(
                f"Posture rotation {self._posture.value!r} → "
                f"{posture.value!r} refused: audit-engine emit failed "
                f"({type(audit_exc).__name__}); a rotation that cannot "
                "be audited cannot be trusted"
            ) from audit_exc

        return DelegateRuntime(
            dispatch_surface=self._dispatch_surface,
            audit_engine=self._audit_engine,
            cascade=self._cascade,
            envelope=self._envelope,
            identity=self._identity,
            signer=self._signer,
            posture=posture,
        )

    async def execute(self, input_payload: dict[str, Any]) -> RuntimeExecutionResult:
        """Execute one TAOD lifecycle pass.

        Sequence:

        1. INITIATED — allocate run_id, build initial TAODState.
        2. R2 composition re-check (Invariant 4 — defense-in-depth).
        3. THINKING — read posture; ``HALT`` refuses, otherwise advance.
        4. ACTING — invoke ``dispatch_surface.dispatch(input_payload)``;
           catch dispatch errors → FAILED.
        5. OBSERVING — cross-validate dispatch result; emit audit.
        6. DECIDING — if payload signals ``_decision_required: True``,
           process; else skip to COMPLETED.
        7. COMPLETED — emit final audit; build RuntimeExecutionResult.

        Every TAOD transition emits exactly one audit event (Invariant
        3) with the run_id bound into its payload.

        Args:
            input_payload: The dispatch input. Forwarded verbatim to
                :meth:`DispatchSurface.dispatch`.

        Returns:
            A :class:`RuntimeExecutionResult` carrying run_id +
            dispatch_result (or None on failure) + final TAODState +
            audit head hash + termination timestamp + posture.

        Raises:
            RuntimePhaseError: when ``execute()`` is called on an
                already-consumed runtime (§7 TAOD phase monotonicity —
                runtime is single-shot per receipt; create a fresh
                :class:`DelegateRuntime` for additional executions). All
                OTHER failure paths return a :class:`RuntimeExecutionResult`
                with ``taod_state.phase == "failed"`` and
                ``dispatch_result is None``. The error class + message live
                on the FAILED transition's ``reason`` field.
        """
        # §7 TAOD phase monotonicity — single-shot enforcement.
        # If a prior execute() already ran (success OR failure), refuse
        # this call. The check fires BEFORE consuming so the consumed
        # flag remains True from the prior run. Pinned by DV-7-001
        # conformance vector + test_runtime_re_execute_after_completed_*.
        if self._consumed:
            raise RuntimePhaseError(
                "DelegateRuntime is single-shot per §7 TAOD phase "
                "monotonicity; create a new runtime instance for "
                "additional executions (receipt-bound runs MUST not "
                "share substrate)"
            )

        try:
            return await self._execute_impl(input_payload)
        finally:
            # Mark consumed on EVERY exit path — success, FAILED return,
            # AND exceptional bubble-up (R2 re-check could raise TypeError
            # before being caught; defense-in-depth against
            # retry-until-success attack on a runtime).
            self._consumed = True

    async def _execute_impl(
        self, input_payload: dict[str, Any]
    ) -> RuntimeExecutionResult:
        """The actual TAOD lifecycle body — see :meth:`execute`.

        Separated from :meth:`execute` so the §7 single-shot guard
        + finally-block consumption can wrap every exit path including
        early-return failure paths.
        """
        run_id = _generate_run_id()
        started_at = datetime.now(timezone.utc)
        state = TAODState(phase="initiated", started_at=started_at)
        posture_at_execute = self._posture

        # Step 2 — R2 composition re-check at execute() start.
        # Defense-in-depth: a component reconstructed externally between
        # __init__ and execute() must not silently break the
        # composition (Invariant 4 part 2).
        try:
            R2Composition.validate(
                envelope=self._envelope,
                cascade=self._cascade,
                dispatch_surface=self._dispatch_surface,
                audit_engine=self._audit_engine,
                signer=self._signer,
            )
        except (R2CompositionError, TypeError) as exc:
            # Composition failure means we cannot emit ANY audit event
            # (signer/audit binding may be the broken thing). Transition
            # to FAILED without an audit emit and return.
            failed_state = state.advance_to(
                "failed",
                reason=f"R2 composition re-check failed: "
                f"{type(exc).__name__}: {exc}",
            )
            return self._build_result(
                run_id=run_id,
                dispatch_result=None,
                taod_state=failed_state,
                posture_at_execute=posture_at_execute,
                emit_audit=False,
            )

        # Step 3 — INITIATED → THINKING.
        # Per S6 R1 A3/D1 fix: AUDIT FIRST, then advance state. If the
        # audit emit raises (signer failure, JSON-serialization fault,
        # I/O on the wrapped chain), the state MUST NOT advance — that
        # leaves the chain authoritative and the in-memory state
        # consistent with it. Falls back to a FAILED transition with a
        # sanitized reason; the FAILED transition does NOT recurse into
        # another audit emit (the audit subsystem itself just broke —
        # see _advance_to_failed_no_audit).
        try:
            self._emit_phase_audit(
                run_id=run_id,
                phase="thinking",
                extra_payload={"posture": posture_at_execute.value},
            )
        except Exception as audit_exc:
            failed_state = self._advance_to_failed_no_audit(
                state, phase="thinking", audit_exc=audit_exc
            )
            return self._build_result(
                run_id=run_id,
                dispatch_result=None,
                taod_state=failed_state,
                posture_at_execute=posture_at_execute,
                emit_audit=False,
            )
        state = state.advance_to("thinking")

        # Posture gate (Invariant 2 — read at THINKING phase).
        if posture_at_execute is Posture.HALT:
            # FAILED-path: emit first, advance second. Sanitize the
            # reason field per S6 R1 LOW-1 (to_dict observability) —
            # the caller-facing TAOD reason carries the class/phase
            # tag only; the full payload lives in the audit event.
            try:
                self._emit_phase_audit(
                    run_id=run_id,
                    phase="failed",
                    extra_payload={
                        "reason": "posture_halt",
                        "posture": posture_at_execute.value,
                    },
                )
            except Exception as audit_exc:
                failed_state = self._advance_to_failed_no_audit(
                    state, phase="thinking", audit_exc=audit_exc
                )
                return self._build_result(
                    run_id=run_id,
                    dispatch_result=None,
                    taod_state=failed_state,
                    posture_at_execute=posture_at_execute,
                    emit_audit=False,
                )
            failed_state = state.advance_to(
                "failed",
                reason="posture HALT refuses execute()",
            )
            return self._build_result(
                run_id=run_id,
                dispatch_result=None,
                taod_state=failed_state,
                posture_at_execute=posture_at_execute,
                emit_audit=False,  # already emitted above
            )

        # Step 4 — THINKING → ACTING. Audit first, then advance.
        try:
            self._emit_phase_audit(
                run_id=run_id,
                phase="acting",
                extra_payload={
                    "connector_id": self._dispatch_surface.connector.connector_id,
                },
            )
        except Exception as audit_exc:
            failed_state = self._advance_to_failed_no_audit(
                state, phase="acting", audit_exc=audit_exc
            )
            return self._build_result(
                run_id=run_id,
                dispatch_result=None,
                taod_state=failed_state,
                posture_at_execute=posture_at_execute,
                emit_audit=False,
            )
        state = state.advance_to("acting")

        # Invoke the dispatch surface; any exception transitions to
        # FAILED.
        dispatch_result: DispatchResult | None
        try:
            dispatch_result = await self._dispatch_surface.dispatch(input_payload)
        except Exception as exc:
            # Dispatch failure — emit FAILED audit first, then advance.
            # Per S6 R1 LOW-1: the TAOD reason carries ONLY the class
            # name + short phrase (sanitized for to_dict observability);
            # the full exception message lives in the audit payload
            # (signed + sized to forensic surface).
            reason_sanitized = f"dispatch raised: {type(exc).__name__}"
            try:
                self._emit_phase_audit(
                    run_id=run_id,
                    phase="failed",
                    extra_payload={
                        "reason": "dispatch_error",
                        "error_class": type(exc).__name__,
                        "error_message": str(exc),
                    },
                )
            except Exception as audit_exc:
                # Audit subsystem broke AFTER dispatch raised — record
                # FAILED without recursing into another audit attempt.
                # The transition reason carries the audit-failure cause
                # (dispatch failure remains in the original exc's
                # chained traceback the caller may inspect).
                failed_state = self._advance_to_failed_no_audit(
                    state, phase="acting", audit_exc=audit_exc
                )
                return self._build_result(
                    run_id=run_id,
                    dispatch_result=None,
                    taod_state=failed_state,
                    posture_at_execute=posture_at_execute,
                    emit_audit=False,
                )
            failed_state = state.advance_to(
                "failed",
                reason=reason_sanitized,
            )
            return self._build_result(
                run_id=run_id,
                dispatch_result=None,
                taod_state=failed_state,
                posture_at_execute=posture_at_execute,
                emit_audit=False,
            )

        # Step 5 — ACTING → OBSERVING. Cross-validate tenant alignment
        # between the dispatch result and the envelope. The dispatch
        # surface already validated tenant isolation at the connector
        # boundary (S5 Invariant 2); this is a defensive re-check at
        # the runtime spine. Audit first, then advance.
        cascade_tenant = self._cascade.tenant
        expected_tenant = (
            "" if cascade_tenant.is_global else (cascade_tenant.tenant_id or "")
        )
        if dispatch_result.tenant_id != expected_tenant:
            # Tenant mismatch — FAILED-path: emit first, advance second.
            # Reason field already sanitized (no raw exception bleed).
            try:
                self._emit_phase_audit(
                    run_id=run_id,
                    phase="failed",
                    extra_payload={
                        "reason": "tenant_observe_mismatch",
                        "expected_tenant_present": bool(expected_tenant),
                    },
                )
            except Exception as audit_exc:
                failed_state = self._advance_to_failed_no_audit(
                    state, phase="acting", audit_exc=audit_exc
                )
                return self._build_result(
                    run_id=run_id,
                    dispatch_result=dispatch_result,
                    taod_state=failed_state,
                    posture_at_execute=posture_at_execute,
                    emit_audit=False,
                )
            failed_state = state.advance_to(
                "failed",
                reason=(
                    "runtime observe: tenant mismatch on dispatch result "
                    "(envelope cascade scope drifted vs dispatch surface)"
                ),
            )
            return self._build_result(
                run_id=run_id,
                dispatch_result=dispatch_result,
                taod_state=failed_state,
                posture_at_execute=posture_at_execute,
                emit_audit=False,
            )

        # Emit OBSERVING audit (first), then advance. The dispatch
        # surface flagged whether the connector reported an external
        # side effect; surface that in the runtime's observing event
        # so the audit chain carries the full TAOD trail.
        try:
            self._emit_phase_audit(
                run_id=run_id,
                phase="observing",
                extra_payload={
                    "dispatch_id": str(dispatch_result.dispatch_id),
                    "connector_id": dispatch_result.connector_id,
                },
            )
        except Exception as audit_exc:
            failed_state = self._advance_to_failed_no_audit(
                state, phase="acting", audit_exc=audit_exc
            )
            return self._build_result(
                run_id=run_id,
                dispatch_result=dispatch_result,
                taod_state=failed_state,
                posture_at_execute=posture_at_execute,
                emit_audit=False,
            )
        state = state.advance_to("observing")

        # Step 6 — DECIDING (or skip to COMPLETED). Audit first.
        if dispatch_result.payload.get("_decision_required") is True:
            try:
                self._emit_phase_audit(
                    run_id=run_id,
                    phase="deciding",
                    extra_payload={"dispatch_id": str(dispatch_result.dispatch_id)},
                )
            except Exception as audit_exc:
                failed_state = self._advance_to_failed_no_audit(
                    state, phase="observing", audit_exc=audit_exc
                )
                return self._build_result(
                    run_id=run_id,
                    dispatch_result=dispatch_result,
                    taod_state=failed_state,
                    posture_at_execute=posture_at_execute,
                    emit_audit=False,
                )
            state = state.advance_to("deciding")

        # Step 7 — terminal COMPLETED. Audit first, then advance.
        try:
            self._emit_phase_audit(
                run_id=run_id,
                phase="completed",
                extra_payload={"dispatch_id": str(dispatch_result.dispatch_id)},
            )
        except Exception as audit_exc:
            failed_state = self._advance_to_failed_no_audit(
                state, phase=state.phase, audit_exc=audit_exc
            )
            return self._build_result(
                run_id=run_id,
                dispatch_result=dispatch_result,
                taod_state=failed_state,
                posture_at_execute=posture_at_execute,
                emit_audit=False,
            )
        state = state.advance_to("completed")

        return self._build_result(
            run_id=run_id,
            dispatch_result=dispatch_result,
            taod_state=state,
            posture_at_execute=posture_at_execute,
            emit_audit=False,
        )

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _advance_to_failed_no_audit(
        self,
        state: TAODState,
        *,
        phase: str,
        audit_exc: BaseException,
    ) -> TAODState:
        """Advance to FAILED without recursing into another audit emit.

        Per S6 R1 A3/D1: when ``_emit_phase_audit`` raises during a
        TAOD transition, the state MUST land in FAILED — but the FAILED
        transition itself MUST NOT attempt another audit emit (the
        audit subsystem just broke; recursing would re-raise and never
        produce a return value). This helper records the FAILED
        transition with a sanitized reason naming the failure phase and
        the audit-exception class — NOT the raw exception message
        (per LOW-1 to_dict observability discipline).

        The full ``str(audit_exc)`` is intentionally NOT included on
        the TAOD reason field — it would leak audit-subsystem internals
        (signer impl details, audit-chain implementation errors) into
        the observable ``RuntimeExecutionResult.taod_state.to_dict()``
        payload that downstream consumers read.

        Args:
            state: The current TAOD state (non-terminal). Must accept
                a transition to "failed" (every non-terminal phase
                does per ``_LEGAL_SUCCESSORS``).
            phase: The phase whose audit emit just failed; surfaces
                on the reason field so post-incident analysis can
                attribute the audit failure to the correct transition.
            audit_exc: The exception the audit emit raised; only the
                class name lands on the reason field.

        Returns:
            A NEW TAODState advanced to "failed" with a sanitized
            reason. No audit emit is attempted.
        """
        return state.advance_to(
            "failed",
            reason=(
                f"audit emit failed at phase={phase!r}: " f"{type(audit_exc).__name__}"
            ),
        )

    def _emit_phase_audit(
        self,
        *,
        run_id: uuid.UUID,
        phase: str,
        extra_payload: dict[str, Any] | None = None,
    ) -> None:
        """Emit one audit event for a TAOD phase transition.

        Per Invariant 3, every transition produces exactly one audit
        event. The run_id is bound into the payload so a post-incident
        reader can replay every transition of a single run via the
        audit chain.

        The event type per phase is fixed by
        :attr:`_PHASE_EVENT_TYPES`. The signature is computed via the
        bound :attr:`_signer` over the canonical-JSON bytes of the
        payload (mirrors the S5 dispatch path).
        """
        event_type = self._PHASE_EVENT_TYPES[phase]
        payload: dict[str, Any] = {
            "run_id": str(run_id),
            "phase": phase,
        }
        if extra_payload:
            payload.update(extra_payload)
        canonical_bytes = canonical_json_dumps(payload).encode("utf-8")
        signature = self._signer(canonical_bytes)
        self._audit_engine.emit_event(
            event_type=event_type.value,
            payload=payload,
            signer_identity=self._identity,
            signature=signature,
        )

    def _build_result(
        self,
        *,
        run_id: uuid.UUID,
        dispatch_result: DispatchResult | None,
        taod_state: TAODState,
        posture_at_execute: Posture,
        emit_audit: bool,
    ) -> RuntimeExecutionResult:
        """Construct the :class:`RuntimeExecutionResult` return value.

        Captures the audit chain's head hash at the moment of return
        (None when no audit events were emitted, e.g. composition
        failure before THINKING). ``emit_audit`` is reserved for paths
        that wish to emit a final terminal audit event before result
        construction; currently all callers manage their own emissions
        and pass ``emit_audit=False``.
        """
        # emit_audit reserved for future use (e.g. a unified terminal
        # emit path); currently all caller-sites manage their own
        # emissions for tighter control over per-failure payloads.
        _ = emit_audit
        head_hash = self._audit_engine.head_hash()
        return RuntimeExecutionResult(
            run_id=run_id,
            dispatch_result=dispatch_result,
            taod_state=taod_state,
            audit_head_hash=head_hash,
            terminated_at=datetime.now(timezone.utc),
            posture_at_execute=posture_at_execute,
        )
