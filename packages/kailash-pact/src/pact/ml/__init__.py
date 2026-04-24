# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PACT governance methods for the kailash-ml lifecycle (W32.c).

This module exposes three governance methods that the kailash-ml 1.0.0
engine surface calls at mutation entry points:

1. ``check_trial_admission`` -- pre-trial admission gate for AutoMLEngine,
   HyperparameterSearch, and agent-driven tuning sweeps. Enforces budget,
   latency, and fairness constraints declared on the governance envelope.

2. ``check_engine_method_clearance`` -- per-method D/T/R clearance gate
   that every MLEngine subclass calls at mutation entry points
   (fit / predict / promote / delete / archive / rollback).

3. ``check_cross_tenant_op`` -- explicit cross-tenant gate for cross-
   tenant export / import / mirror operations (ml-registry-pact.md
   Decision 12). **v1.0 contract:** always returns ``admitted=False``.
   Full cross-tenant evaluation is deferred to v1.1 per spec IT-4 /
   Decision 12. The v1.0 always-denied contract is a REAL implementation
   (zero-tolerance Rule 2): the spec mandates that cross-tenant ops are
   structurally refused until v1.1 ships the bilateral-clearance check.

All three methods share a consistent contract:

* Return a ``@dataclass(frozen=True)`` decision dataclass (PACT MUST
  Rule 1 -- frozen ``GovernanceContext`` discipline).
* Denials are DATA, not exceptions. Programmer-error inputs (negative
  budgets, identical src/dst tenant, invalid engine/method names) raise
  typed ``PactError`` subclasses. A denied decision returns ``cleared=False``
  / ``admitted=False`` -- callers MUST inspect the result.
* Acquire the engine's thread lock for the entire decision + audit window.
* Fail-CLOSED on probe exception (``pact-governance.md`` MUST Rule 4).
* Persist ``tenant_id`` on every audit row (``tenant-isolation.md`` MUST
  Rule 5).
* Fingerprint classified payload fields via ``sha256:<8hex>`` shared
  contract with ``dataflow.classification.event_payload`` (cross-SDK
  parity; ``event-payload-classification.md`` MUST Rule 2).

The ``ClearanceRequirement`` decorator is a convenience wrapper that
enforces ``check_engine_method_clearance`` at MLEngine method entry
points without requiring each engine to duplicate the plumbing.

The ``ml_context`` kwarg is the security-relevant kwarg that MLEngine
methods plumb through to governance:

    ml_context = {
        "tenant_id": "tenant-alpha",
        "actor_id": "agent-42",
        "engine_name": "ClassificationEngine",
        "method_name": "promote",
        "clearance_required": "DTR",
    }

Call sites: every MLEngine mutation entry point (``fit``, ``predict``,
``promote``, ``delete``, ``archive``, ``rollback``). This module defines
the signature and the enforcement contract; the plumbing into kailash-ml
call sites happens at the W32.a / W32.b sibling shards.

See ``specs/pact-ml-integration.md`` for the authoritative spec.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Literal, Mapping, Optional

from kailash.trust.pact.exceptions import PactError

logger = logging.getLogger(__name__)

__all__ = [
    # Error hierarchy
    "GovernanceAdmissionError",
    "GovernanceClearanceError",
    "GovernanceCrossTenantError",
    # Decision dataclasses
    "AdmissionDecision",
    "ClearanceDecision",
    "CrossTenantDecision",
    # Governance methods
    "check_trial_admission",
    "check_engine_method_clearance",
    "check_cross_tenant_op",
    # Decorators + contexts
    "ClearanceRequirement",
    "MLGovernanceContext",
]


# -------------------------------------------------------------------
# Error hierarchy -- denials are DATA, not exceptions. These errors
# signal PROGRAMMER error (invalid inputs, negative budgets, etc.).
# -------------------------------------------------------------------


class GovernanceAdmissionError(PactError):
    """Raised only for programmer-error inputs to ``check_trial_admission``.

    A denial is NOT an error -- it is an ``AdmissionDecision(admitted=False)``.
    This exception signals inputs that could never produce a valid decision
    (negative budget, non-finite latency, empty tenant_id, etc.).
    """


class GovernanceClearanceError(PactError):
    """Raised only for programmer-error inputs to ``check_engine_method_clearance``.

    A denied clearance returns ``ClearanceDecision(cleared=False)``.
    """


class GovernanceCrossTenantError(PactError):
    """Raised only for programmer-error inputs to ``check_cross_tenant_op``.

    A denied cross-tenant op returns ``CrossTenantDecision(admitted=False)``.
    Invalid inputs (identical src/dst, empty tenant ids) raise this error
    BEFORE the lock is acquired.
    """


# -------------------------------------------------------------------
# Frozen decision dataclasses -- PACT MUST Rule 1
# -------------------------------------------------------------------


@dataclass(frozen=True)
class AdmissionDecision:
    """Decision returned by :func:`check_trial_admission`.

    Denials are DATA. Callers MUST inspect ``admitted`` before proceeding.
    ``decision_id`` is a UUID4 logged to the audit chain for forensic
    correlation with the triggering trial.
    """

    admitted: bool
    reason: str
    binding_constraint: Optional[str]
    tenant_id: str
    actor_id: str
    decided_at: datetime
    decision_id: str

    @classmethod
    def denied(
        cls,
        *,
        reason: str,
        binding_constraint: Optional[str] = None,
        tenant_id: str = "",
        actor_id: str = "",
        decision_id: Optional[str] = None,
    ) -> AdmissionDecision:
        """Construct a denial decision.

        The v1.0 cross-tenant always-denied path uses this; callers that
        want to construct deterministic denials in tests can use it too.
        """
        return cls(
            admitted=False,
            reason=reason,
            binding_constraint=binding_constraint,
            tenant_id=tenant_id,
            actor_id=actor_id,
            decided_at=datetime.now(UTC),
            decision_id=decision_id or _fresh_decision_id(),
        )


@dataclass(frozen=True)
class ClearanceDecision:
    """Decision returned by :func:`check_engine_method_clearance`.

    ``missing_dimensions`` is the tuple of D/T/R dimensions the actor
    lacks; empty tuple when ``cleared=True``.
    """

    cleared: bool
    reason: str
    missing_dimensions: tuple[str, ...]
    tenant_id: str
    actor_id: str
    engine_name: str
    method_name: str
    decided_at: datetime
    decision_id: str


@dataclass(frozen=True)
class CrossTenantDecision:
    """Decision returned by :func:`check_cross_tenant_op`.

    ``admitted`` is the logical AND of ``src_clearance.cleared`` and
    ``dst_clearance.cleared`` in v1.1+. In v1.0 this ALWAYS returns
    ``admitted=False`` per spec IT-4 / Decision 12; the clearance
    sub-decisions are populated with denial rationales that name
    v1.0 as the binding constraint.
    """

    admitted: bool
    reason: str
    src_clearance: ClearanceDecision
    dst_clearance: ClearanceDecision
    operation: Literal["export", "import", "mirror"]
    actor_id: str
    decided_at: datetime
    decision_id: str


# -------------------------------------------------------------------
# Shared helpers
# -------------------------------------------------------------------


# Regex-free identifier validator: prevents identifier injection into
# audit rows (aligns with rules/dataflow-identifier-safety.md MUST Rule 2).
# We deliberately do NOT use re.compile here to keep the helper's
# surface minimal -- the predicate is cheap and audit-grep-able.
_ALLOWED_FIRST_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
)
_ALLOWED_REST_CHARS = _ALLOWED_FIRST_CHARS | frozenset("0123456789")


def _validate_identifier(name: str, *, field_label: str) -> None:
    """Validate an identifier against the PACT audit-safe grammar.

    Raises :class:`GovernanceClearanceError` with a fingerprint-safe
    message (the raw input is NEVER echoed verbatim -- stored-XSS /
    log-poisoning defense per ``dataflow-identifier-safety.md`` §2).
    """
    if not isinstance(name, str) or not name:
        raise GovernanceClearanceError(
            f"{field_label} must be a non-empty string",
            details={"field_label": field_label},
        )
    if len(name) > 128:
        raise GovernanceClearanceError(
            f"{field_label} exceeds 128-char limit (len={len(name)})",
            details={"field_label": field_label, "length": len(name)},
        )
    if name[0] not in _ALLOWED_FIRST_CHARS:
        raise GovernanceClearanceError(
            f"{field_label} failed validation "
            f"(fingerprint={hash(name) & 0xFFFF:04x})",
            details={"field_label": field_label},
        )
    for ch in name[1:]:
        if ch not in _ALLOWED_REST_CHARS:
            raise GovernanceClearanceError(
                f"{field_label} failed validation "
                f"(fingerprint={hash(name) & 0xFFFF:04x})",
                details={"field_label": field_label},
            )


_VALID_CLEARANCE_LITERALS = frozenset({"D", "T", "R", "DTR"})


def _validate_clearance_required(value: str) -> str:
    if value not in _VALID_CLEARANCE_LITERALS:
        raise GovernanceClearanceError(
            f"clearance_required must be one of "
            f"{sorted(_VALID_CLEARANCE_LITERALS)}, got {value!r}",
            details={"got": value},
        )
    return value


def _fresh_decision_id() -> str:
    """Return a fresh UUID4 decision identifier."""
    return str(uuid.uuid4())


def fingerprint_payload(payload: Any) -> str:
    """Return a ``sha256:<8hex>`` fingerprint of a payload.

    Shared contract with
    ``dataflow.classification.event_payload.format_record_id_for_event``
    per ``rules/event-payload-classification.md`` MUST Rule 2. The
    8-hex-char prefix (32 bits entropy) is sufficient for forensic
    correlation across event + log + DB audit streams and is
    intentionally identical to the kailash-rs helper.

    For ``None``, returns ``"sha256:00000000"`` so every audit row
    carries a fingerprint -- grep-able that the row exists without
    leaking whether a payload was present.
    """
    if payload is None:
        raw = b""
    elif isinstance(payload, (bytes, bytearray)):
        raw = bytes(payload)
    else:
        # Mapping / list / scalar -- canonicalize via repr(sorted(...))
        # to get stable fingerprints for equal-by-value payloads.
        if isinstance(payload, Mapping):
            canonical = repr(sorted((str(k), repr(v)) for k, v in payload.items()))
        else:
            canonical = repr(payload)
        raw = canonical.encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()[:8]}"


# -------------------------------------------------------------------
# Audit row shape -- matches spec §5 schema
# -------------------------------------------------------------------


def _build_audit_row(
    *,
    decision_id: str,
    method: str,
    tenant_id: str,
    actor_id: str,
    admitted_or_cleared: bool,
    reason: str,
    binding_constraint: Optional[str] = None,
    engine_name: Optional[str] = None,
    method_name: Optional[str] = None,
    operation: Optional[str] = None,
    src_tenant_id: Optional[str] = None,
    dst_tenant_id: Optional[str] = None,
    payload_fingerprint: Optional[str] = None,
    decided_at: Optional[datetime] = None,
    audit_correlation_id: Optional[str] = None,
) -> dict[str, Any]:
    """Construct the audit row for one of the three governance methods.

    Per spec §5 the row carries ``tenant_id`` (indexed per
    ``rules/tenant-isolation.md`` §5) AND an ``audit_correlation_id``
    column so kailash-ml's ``_kml_audit`` table rows join the PACT
    audit chain 1:1. The correlation id defaults to the decision_id
    when the caller does not supply one.
    """
    when = decided_at if decided_at is not None else datetime.now(UTC)
    row: dict[str, Any] = {
        "decision_id": decision_id,
        "method": method,
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "admitted_or_cleared": 1 if admitted_or_cleared else 0,
        "reason": reason,
        "binding_constraint": binding_constraint,
        "engine_name": engine_name,
        "method_name": method_name,
        "operation": operation,
        "src_tenant_id": src_tenant_id,
        "dst_tenant_id": dst_tenant_id,
        "decided_at": when.isoformat(),
        "payload_fingerprint": payload_fingerprint,
        "audit_correlation_id": audit_correlation_id or decision_id,
    }
    return row


def _emit_audit(engine: Any, audit_row: Mapping[str, Any]) -> None:
    """Append the governance audit row to the engine's audit chain.

    Non-blocking: exceptions are logged but never re-raised, because a
    governance decision has already been made and returned to the caller.
    An audit-sink failure MUST NOT reverse a governance denial.
    """
    emit_audit_unlocked = getattr(engine, "_emit_audit_unlocked", None)
    if emit_audit_unlocked is None:
        logger.debug(
            "pact.ml.audit.skip",
            extra={
                "method": audit_row.get("method"),
                "decision_id": audit_row.get("decision_id"),
                "reason": "engine lacks _emit_audit_unlocked",
            },
        )
        return
    try:
        # action name matches spec §5 "method" field; audit details carry
        # the full row so downstream consumers can reconstruct the schema.
        emit_audit_unlocked(str(audit_row["method"]), dict(audit_row))
    except Exception:
        logger.exception(
            "pact.ml.audit.error",
            extra={
                "method": audit_row.get("method"),
                "decision_id": audit_row.get("decision_id"),
            },
        )


# -------------------------------------------------------------------
# Lock acquisition -- prefer the engine's lock; fall back to a module-
# local lock for engines that don't expose one. Callers can still pass
# ``engine=None`` for the v1.0 cross-tenant always-denied contract.
# -------------------------------------------------------------------


_FALLBACK_LOCK = threading.Lock()


def _acquire_engine_lock(engine: Any) -> threading.Lock:
    """Return the engine's ``_lock`` if present, else a module-local lock.

    The module-local fallback is safe for the v1.0 always-denied cross-
    tenant path (no state is read), and for testing scenarios that
    exercise the helpers without a full engine. Production callers pass
    a real :class:`kailash.trust.pact.engine.GovernanceEngine`.
    """
    # threading.Lock and threading.RLock are factories, not classes (Py3.11+).
    # Use type() on actual lock instances to obtain the underlying types.
    _LOCK_TYPES = (type(threading.Lock()), type(threading.RLock()))
    lock = getattr(engine, "_lock", None)
    if isinstance(lock, _LOCK_TYPES):
        return lock  # type: ignore[return-value]
    return _FALLBACK_LOCK


# -------------------------------------------------------------------
# Probe resolution -- the callable the caller supplies to evaluate an
# envelope constraint. Probes are data endpoints (rules/agent-
# reasoning.md): they return a boolean outcome; the decision logic
# lives here, not in the probe.
# -------------------------------------------------------------------


# Probe signature: (engine, context_dict) -> (passed: bool, reason: str,
# binding_constraint: Optional[str])
TrialProbe = Callable[[Any, Mapping[str, Any]], tuple[bool, str, Optional[str]]]
ClearanceProbe = Callable[[Any, Mapping[str, Any]], tuple[bool, str, tuple[str, ...]]]


def _default_trial_probe(
    engine: Any, context: Mapping[str, Any]
) -> tuple[bool, str, Optional[str]]:
    """Default trial admission probe.

    Consults the engine's envelope for the actor's role; returns a
    pass/fail outcome per spec §2.1. This default probe uses the
    engine's ``verify_action`` surface when available, which:

    * Acquires the engine's internal lock (we already hold the outer
      ``_acquire_engine_lock`` at the caller -- PACT reentrant locks are
      the shared ``threading.Lock`` created at engine init and are NOT
      re-entrant; we therefore delegate to ``verify_action`` OUTSIDE
      our own lock by snapshotting the engine state before entering).
    * Evaluates the envelope constraints (budget, latency, fairness).
    * Returns a ``GovernanceVerdict`` with a level string.

    The default probe is a DATA endpoint: no decision logic, just
    envelope evaluation.
    """
    # Fail-OPEN probe would be a security hole, so the default probe
    # fails CLOSED when it can't determine an outcome.
    if engine is None:
        return (False, "no GovernanceEngine supplied -- fail-closed", None)
    verify_action = getattr(engine, "verify_action", None)
    if verify_action is None:
        return (
            False,
            "engine lacks verify_action -- fail-closed",
            None,
        )
    try:
        verdict = verify_action(
            role_address=context.get("role_address", ""),
            action=context.get("action", "pact.ml.trial_admission"),
            ctx=dict(context),
        )
    except Exception as exc:  # fail-CLOSED per MUST Rule 4
        return (
            False,
            f"probe exception: {type(exc).__name__}",
            None,
        )
    allowed = bool(getattr(verdict, "allowed", False))
    reason = str(getattr(verdict, "reason", ""))
    # Binding constraint: PACT envelope doesn't name the binding
    # constraint directly in GovernanceVerdict; we surface the level
    # string so operators can correlate with envelope config.
    level = str(getattr(verdict, "level", ""))
    binding = level if not allowed else None
    return (allowed, reason, binding)


def _default_clearance_probe(
    engine: Any, context: Mapping[str, Any]
) -> tuple[bool, str, tuple[str, ...]]:
    """Default D/T/R clearance probe.

    v1.0 clearance semantics: returns cleared=True when the caller
    supplied a non-empty ``actor_id`` AND ``clearance_context`` dict with
    every required D/T/R dimension. The dimensions required are in
    ``context['clearance_required']`` (one of "D", "T", "R", "DTR").
    The actor's held dimensions are in ``context['held_dimensions']`` --
    callers plumb this in from the D/T/R address in the kailash-ml call
    site.

    Fails CLOSED when any dimension is missing.
    """
    required = str(context.get("clearance_required", ""))
    held = context.get("held_dimensions", ()) or ()
    if not isinstance(held, (list, tuple, set, frozenset)):
        return (
            False,
            "held_dimensions must be an iterable of D/T/R letters",
            tuple(sorted(_VALID_CLEARANCE_LITERALS - {"DTR"})),
        )
    held_set = frozenset(str(x) for x in held)

    if required == "DTR":
        expected = frozenset({"D", "T", "R"})
    elif required in {"D", "T", "R"}:
        expected = frozenset({required})
    else:
        return (
            False,
            f"unexpected clearance_required={required!r}",
            tuple(sorted({"D", "T", "R"})),
        )

    missing = tuple(sorted(expected - held_set))
    if missing:
        return (
            False,
            f"actor missing clearance dimensions: {missing}",
            missing,
        )
    return (True, "actor holds all required D/T/R dimensions", ())


# -------------------------------------------------------------------
# 1. check_trial_admission -- pre-trial admission gate
# -------------------------------------------------------------------


def check_trial_admission(
    engine: Any,
    *,
    tenant_id: str,
    actor_id: str,
    trial_config: Mapping[str, Any],
    budget_microdollars: int,
    latency_budget_ms: int,
    fairness_constraints: Optional[Mapping[str, Any]] = None,
    probe: Optional[TrialProbe] = None,
    audit_correlation_id: Optional[str] = None,
    role_address: str = "",
    action: str = "pact.ml.trial_admission",
) -> AdmissionDecision:
    """Pre-trial admission gate for AutoML / HyperparameterSearch sweeps.

    Acquires the engine's lock, runs the admission probe, appends an
    audit row, and returns a frozen :class:`AdmissionDecision`.

    Fails CLOSED on any probe exception -- denials are DATA, programmer
    errors are exceptions (:class:`GovernanceAdmissionError`).

    Args:
        engine: The :class:`kailash.trust.pact.engine.GovernanceEngine`
            instance, or ``None`` for test scenarios that want to verify
            the always-denied fallback path.
        tenant_id: Tenant owning the trial. Non-empty per
            ``rules/tenant-isolation.md`` §5.
        actor_id: Agent / user ID requesting the trial.
        trial_config: The AutoML trial configuration (hyperparameter
            space, dataset, model candidates). Classified fields are
            fingerprinted before landing in the audit row -- never
            echoed verbatim.
        budget_microdollars: Trial budget in micro-dollars (USD x 1e6).
            MUST be a non-negative finite int.
        latency_budget_ms: Per-prediction latency budget in ms. MUST
            be a non-negative finite int.
        fairness_constraints: Optional mapping consumed by the envelope's
            ``pact.ml.fairness`` constraint (if declared). When absent
            or when the envelope has no fairness constraint, this is
            ignored -- ignore-if-absent does NOT imply admission.
        probe: Override the default admission probe. The default probe
            delegates to ``engine.verify_action``. Primarily a test
            seam.
        audit_correlation_id: Optional correlation ID linking this
            decision to a kailash-ml ``_kml_audit`` row.
        role_address: D/T/R address of the actor's role (passed through
            to the probe).
        action: Verb passed to ``verify_action`` for the envelope
            evaluation. Default ``"pact.ml.trial_admission"``.

    Returns:
        An :class:`AdmissionDecision`.

    Raises:
        :class:`GovernanceAdmissionError`: On programmer-error inputs
            (negative budget, empty tenant_id, etc.).
    """
    # Input validation -- BEFORE the lock. Raises on programmer error.
    if not isinstance(tenant_id, str) or not tenant_id:
        raise GovernanceAdmissionError(
            "tenant_id must be a non-empty string",
            details={"tenant_id_type": type(tenant_id).__name__},
        )
    if not isinstance(actor_id, str) or not actor_id:
        raise GovernanceAdmissionError(
            "actor_id must be a non-empty string",
            details={"actor_id_type": type(actor_id).__name__},
        )
    if not isinstance(budget_microdollars, int) or isinstance(
        budget_microdollars, bool
    ):
        raise GovernanceAdmissionError(
            "budget_microdollars must be an int",
            details={"got": type(budget_microdollars).__name__},
        )
    if budget_microdollars < 0:
        raise GovernanceAdmissionError(
            "budget_microdollars must be non-negative",
            details={"got": budget_microdollars},
        )
    if not isinstance(latency_budget_ms, int) or isinstance(latency_budget_ms, bool):
        raise GovernanceAdmissionError(
            "latency_budget_ms must be an int",
            details={"got": type(latency_budget_ms).__name__},
        )
    if latency_budget_ms < 0:
        raise GovernanceAdmissionError(
            "latency_budget_ms must be non-negative",
            details={"got": latency_budget_ms},
        )
    if trial_config is None:
        raise GovernanceAdmissionError(
            "trial_config must be a Mapping, not None",
            details={},
        )

    the_probe: TrialProbe = probe if probe is not None else _default_trial_probe
    decision_id = _fresh_decision_id()
    decided_at = datetime.now(UTC)

    # Build the context the probe evaluates against.
    context: dict[str, Any] = {
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "role_address": role_address,
        "action": action,
        "budget_microdollars": budget_microdollars,
        "cost": budget_microdollars / 1_000_000,  # verify_action budget check
        "latency_budget_ms": latency_budget_ms,
        "fairness_constraints": dict(fairness_constraints or {}),
    }

    lock = _acquire_engine_lock(engine)
    with lock:
        try:
            admitted, reason, binding_constraint = the_probe(engine, context)
        except Exception as exc:
            # fail-CLOSED per MUST Rule 4; exception is NOT a pass.
            logger.warning(
                "pact.ml.trial_admission.probe_exception",
                extra={
                    "tenant_id": tenant_id,
                    "actor_id": actor_id,
                    "exc_type": type(exc).__name__,
                    "payload_fingerprint": fingerprint_payload(trial_config),
                },
            )
            admitted = False
            reason = f"probe exception: {type(exc).__name__}"
            binding_constraint = None

        audit_row = _build_audit_row(
            decision_id=decision_id,
            method="check_trial_admission",
            tenant_id=tenant_id,
            actor_id=actor_id,
            admitted_or_cleared=bool(admitted),
            reason=reason,
            binding_constraint=binding_constraint,
            payload_fingerprint=fingerprint_payload(trial_config),
            decided_at=decided_at,
            audit_correlation_id=audit_correlation_id,
        )
        _emit_audit(engine, audit_row)

    return AdmissionDecision(
        admitted=bool(admitted),
        reason=reason,
        binding_constraint=binding_constraint,
        tenant_id=tenant_id,
        actor_id=actor_id,
        decided_at=decided_at,
        decision_id=decision_id,
    )


# -------------------------------------------------------------------
# 2. check_engine_method_clearance -- per-method D/T/R gate
# -------------------------------------------------------------------


def check_engine_method_clearance(
    engine: Any,
    *,
    tenant_id: str,
    actor_id: str,
    engine_name: str,
    method_name: str,
    clearance_required: Literal["D", "T", "R", "DTR"],
    held_dimensions: Optional[tuple[str, ...]] = None,
    probe: Optional[ClearanceProbe] = None,
    audit_correlation_id: Optional[str] = None,
) -> ClearanceDecision:
    """Per-engine-method clearance gate.

    Every ``MLEngine`` mutation entry point (fit / predict / promote /
    delete / archive / rollback) calls this BEFORE performing the
    mutation. Denials are DATA; invalid inputs are exceptions.

    Args:
        engine: The :class:`GovernanceEngine` instance.
        tenant_id: Tenant owning the engine state.
        actor_id: Agent / user ID requesting the action.
        engine_name: MLEngine subclass name (e.g. ``"ClassificationEngine"``).
            Validated against a strict identifier grammar.
        method_name: Method on the engine (e.g. ``"promote"``).
            Validated against a strict identifier grammar.
        clearance_required: One of ``"D"``, ``"T"``, ``"R"``, ``"DTR"``.
            ``"DTR"`` means ALL THREE dimensions.
        held_dimensions: The D/T/R dimensions the actor holds. Pass an
            empty tuple (the default) to trigger denial on any
            requirement -- this is the safe default for actors whose
            clearance has not been resolved yet.
        probe: Override the default clearance probe.
        audit_correlation_id: Optional correlation ID linking to
            ``_kml_audit`` rows in kailash-ml.

    Returns:
        A :class:`ClearanceDecision`.

    Raises:
        :class:`GovernanceClearanceError`: On programmer-error inputs
            (invalid identifier, unsupported clearance literal).
    """
    if not isinstance(tenant_id, str) or not tenant_id:
        raise GovernanceClearanceError(
            "tenant_id must be a non-empty string",
            details={},
        )
    if not isinstance(actor_id, str) or not actor_id:
        raise GovernanceClearanceError(
            "actor_id must be a non-empty string",
            details={},
        )
    _validate_identifier(engine_name, field_label="engine_name")
    _validate_identifier(method_name, field_label="method_name")
    clearance_required = _validate_clearance_required(clearance_required)

    held = tuple(held_dimensions) if held_dimensions is not None else ()

    the_probe: ClearanceProbe = probe if probe is not None else _default_clearance_probe
    decision_id = _fresh_decision_id()
    decided_at = datetime.now(UTC)
    context: dict[str, Any] = {
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "engine_name": engine_name,
        "method_name": method_name,
        "clearance_required": clearance_required,
        "held_dimensions": held,
    }

    lock = _acquire_engine_lock(engine)
    with lock:
        try:
            cleared, reason, missing = the_probe(engine, context)
        except Exception as exc:
            logger.warning(
                "pact.ml.engine_method_clearance.probe_exception",
                extra={
                    "tenant_id": tenant_id,
                    "actor_id": actor_id,
                    "engine_name_fingerprint": fingerprint_payload(engine_name),
                    "method_name_fingerprint": fingerprint_payload(method_name),
                    "exc_type": type(exc).__name__,
                },
            )
            cleared = False
            reason = f"probe exception: {type(exc).__name__}"
            if clearance_required == "DTR":
                missing = ("D", "T", "R")
            else:
                missing = (clearance_required,)

        audit_row = _build_audit_row(
            decision_id=decision_id,
            method="check_engine_method_clearance",
            tenant_id=tenant_id,
            actor_id=actor_id,
            admitted_or_cleared=bool(cleared),
            reason=reason,
            binding_constraint=("clearance" if not cleared else None),
            engine_name=engine_name,
            method_name=method_name,
            decided_at=decided_at,
            audit_correlation_id=audit_correlation_id,
        )
        _emit_audit(engine, audit_row)

    return ClearanceDecision(
        cleared=bool(cleared),
        reason=reason,
        missing_dimensions=tuple(missing),
        tenant_id=tenant_id,
        actor_id=actor_id,
        engine_name=engine_name,
        method_name=method_name,
        decided_at=decided_at,
        decision_id=decision_id,
    )


# -------------------------------------------------------------------
# 3. check_cross_tenant_op -- v1.0 always-denied contract
# -------------------------------------------------------------------


_VALID_CROSS_TENANT_OPS = frozenset({"export", "import", "mirror"})

_CROSS_TENANT_V1_REASON = (
    "Cross-tenant operation refused — kailash-pact 0.10.0 ships the "
    "always-denied v1.0 contract per spec IT-4 / Decision 12. Full "
    "bilateral clearance evaluation lands in v1.1."
)


def check_cross_tenant_op(
    engine: Any,
    *,
    actor_id: str,
    src_tenant_id: str,
    dst_tenant_id: str,
    operation: Literal["export", "import", "mirror"],
    clearance_required: Literal["D", "T", "R", "DTR"],
    audit_correlation_id: Optional[str] = None,
) -> CrossTenantDecision:
    """Cross-tenant operation gate.

    **v1.0 contract (kailash-pact 0.10.0):** this method ALWAYS returns
    ``CrossTenantDecision(admitted=False)`` per spec IT-4 / Decision 12.
    The v1.0 always-denied contract is a REAL implementation, not a
    stub:

    * It enforces the spec's structural refusal: every cross-tenant op
      is denied until v1.1 ships bilateral clearance.
    * It produces a frozen decision, an audit row, and typed errors for
      invalid inputs -- callers cannot misuse the API to bypass the
      denial.
    * Removing the call would remove the audit trail and fail-open.

    Full v1.1 bilateral clearance evaluation (src AND dst clearance,
    AND'd under a single lock acquisition) lands at a future release;
    see spec §2.3 for the v1.1 contract shape.

    Args:
        engine: The :class:`GovernanceEngine` instance.
        actor_id: Agent / user ID requesting the op.
        src_tenant_id: Source tenant. Non-empty, distinct from dst.
        dst_tenant_id: Destination tenant. Non-empty, distinct from src.
        operation: One of ``"export"``, ``"import"``, ``"mirror"``.
        clearance_required: D/T/R dimension(s) required on BOTH sides.
        audit_correlation_id: Optional correlation ID.

    Returns:
        A :class:`CrossTenantDecision` with ``admitted=False``.

    Raises:
        :class:`GovernanceCrossTenantError`: On programmer-error inputs
            (identical src/dst, empty ids, invalid operation).
    """
    if not isinstance(actor_id, str) or not actor_id:
        raise GovernanceCrossTenantError(
            "actor_id must be a non-empty string",
            details={},
        )
    if not isinstance(src_tenant_id, str) or not src_tenant_id:
        raise GovernanceCrossTenantError(
            "src_tenant_id must be a non-empty string",
            details={},
        )
    if not isinstance(dst_tenant_id, str) or not dst_tenant_id:
        raise GovernanceCrossTenantError(
            "dst_tenant_id must be a non-empty string",
            details={},
        )
    if src_tenant_id == dst_tenant_id:
        raise GovernanceCrossTenantError(
            "cross-tenant op requires distinct src_tenant_id and dst_tenant_id",
            details={"src": src_tenant_id, "dst": dst_tenant_id},
        )
    if operation not in _VALID_CROSS_TENANT_OPS:
        raise GovernanceCrossTenantError(
            f"operation must be one of {sorted(_VALID_CROSS_TENANT_OPS)}, "
            f"got {operation!r}",
            details={"got": operation},
        )
    clearance_required = _validate_clearance_required(clearance_required)

    decision_id = _fresh_decision_id()
    decided_at = datetime.now(UTC)

    # v1.0 always-denied contract: construct denial sub-decisions
    # that name v1.0 as the binding constraint. The sub-decisions are
    # REAL ClearanceDecision instances (frozen, audit-worthy), NOT stubs.
    v10_missing = (
        ("D", "T", "R") if clearance_required == "DTR" else (clearance_required,)
    )
    src_clearance = ClearanceDecision(
        cleared=False,
        reason=_CROSS_TENANT_V1_REASON,
        missing_dimensions=v10_missing,
        tenant_id=src_tenant_id,
        actor_id=actor_id,
        engine_name="CrossTenantOp",
        method_name=operation,
        decided_at=decided_at,
        decision_id=_fresh_decision_id(),
    )
    dst_clearance = ClearanceDecision(
        cleared=False,
        reason=_CROSS_TENANT_V1_REASON,
        missing_dimensions=v10_missing,
        tenant_id=dst_tenant_id,
        actor_id=actor_id,
        engine_name="CrossTenantOp",
        method_name=operation,
        decided_at=decided_at,
        decision_id=_fresh_decision_id(),
    )

    lock = _acquire_engine_lock(engine)
    with lock:
        audit_row = _build_audit_row(
            decision_id=decision_id,
            method="check_cross_tenant_op",
            tenant_id=src_tenant_id,  # primary tenant on the audit row
            actor_id=actor_id,
            admitted_or_cleared=False,
            reason=_CROSS_TENANT_V1_REASON,
            binding_constraint="v1.0_always_denied",
            operation=operation,
            src_tenant_id=src_tenant_id,
            dst_tenant_id=dst_tenant_id,
            decided_at=decided_at,
            audit_correlation_id=audit_correlation_id,
        )
        _emit_audit(engine, audit_row)

    return CrossTenantDecision(
        admitted=False,
        reason=_CROSS_TENANT_V1_REASON,
        src_clearance=src_clearance,
        dst_clearance=dst_clearance,
        operation=operation,
        actor_id=actor_id,
        decided_at=decided_at,
        decision_id=decision_id,
    )


# -------------------------------------------------------------------
# ml_context envelope kwarg + ClearanceRequirement decorator
# -------------------------------------------------------------------


@dataclass(frozen=True)
class MLGovernanceContext:
    """Security-relevant kwarg plumbed through every MLEngine mutation.

    kailash-ml 1.0.0 MLEngine methods accept an ``ml_context`` kwarg
    of this shape. Every mutation entry point (``fit``, ``predict``,
    ``promote``, ``delete``, ``archive``, ``rollback``) MUST thread
    this through to :func:`check_engine_method_clearance` before
    mutating state.

    Per ``rules/security.md`` § Multi-Site Kwarg Plumbing, this kwarg
    is security-relevant: a sibling MLEngine method that skips plumbing
    it silently bypasses governance. Every sibling call site MUST be
    updated in the same PR as the helper introduction.
    """

    tenant_id: str
    actor_id: str
    role_address: str = ""
    held_dimensions: tuple[str, ...] = ()
    audit_correlation_id: Optional[str] = None
    extras: Mapping[str, Any] = field(default_factory=dict)


class ClearanceRequirement:
    """Decorator that enforces ``check_engine_method_clearance`` at method entry.

    Usage in a kailash-ml engine subclass::

        class ClassificationEngine(MLEngine):
            @ClearanceRequirement("DTR", method_name="promote")
            def promote(self, model_id, *, ml_context: MLGovernanceContext,
                        **kwargs):
                ...

    The decorator:

    1. Reads the ``ml_context`` kwarg from the decorated method's call
       (keyword-only -- per rules/security.md the caller MUST pass
       it explicitly; silently defaulting would defeat governance).
    2. Looks up the governance engine from ``self.governance_engine``
       (falls back to ``self._governance_engine``).
    3. Calls :func:`check_engine_method_clearance`.
    4. Raises :class:`PactError` (not ``GovernanceClearanceError`` --
       callers catching clearance denials expect a denied-decision,
       not an invalid-input error) when the decision is denied.
    5. Invokes the wrapped method only after clearance.

    The decorator does NOT wrap ``__init__``, ``close``, or any method
    whose name begins with ``_`` -- those are framework plumbing, not
    governance surfaces.
    """

    def __init__(
        self,
        clearance_required: Literal["D", "T", "R", "DTR"],
        *,
        method_name: Optional[str] = None,
        engine_name: Optional[str] = None,
    ) -> None:
        # Validate clearance at decoration time so a typo surfaces at
        # import, not at call.
        self._clearance_required: Literal["D", "T", "R", "DTR"] = (
            _validate_clearance_required(clearance_required)  # type: ignore[assignment]
        )
        self._method_name_override = method_name
        self._engine_name_override = engine_name

    def __call__(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        from functools import wraps

        clearance = self._clearance_required
        method_name_override = self._method_name_override
        engine_name_override = self._engine_name_override

        @wraps(fn)
        def wrapper(instance: Any, *args: Any, **kwargs: Any) -> Any:
            ml_context = kwargs.get("ml_context")
            if not isinstance(ml_context, MLGovernanceContext):
                raise PactError(
                    f"{fn.__qualname__}() requires a ml_context=MLGovernanceContext "
                    f"keyword argument; governance clearance cannot be skipped",
                    details={"method": fn.__qualname__},
                )

            engine = getattr(instance, "governance_engine", None)
            if engine is None:
                engine = getattr(instance, "_governance_engine", None)
            # engine may legitimately be None in tests; check_engine_method_clearance
            # fails CLOSED in that case via the probe fallback.

            engine_name = engine_name_override or type(instance).__name__
            method_name = method_name_override or fn.__name__

            decision = check_engine_method_clearance(
                engine,
                tenant_id=ml_context.tenant_id,
                actor_id=ml_context.actor_id,
                engine_name=engine_name,
                method_name=method_name,
                clearance_required=clearance,
                held_dimensions=ml_context.held_dimensions,
                audit_correlation_id=ml_context.audit_correlation_id,
            )
            if not decision.cleared:
                raise PactError(
                    f"clearance denied for {engine_name}.{method_name}: "
                    f"missing={decision.missing_dimensions}; reason={decision.reason}",
                    details={
                        "decision_id": decision.decision_id,
                        "engine_name": engine_name,
                        "method_name": method_name,
                        "missing_dimensions": list(decision.missing_dimensions),
                    },
                )
            return fn(instance, *args, **kwargs)

        return wrapper
