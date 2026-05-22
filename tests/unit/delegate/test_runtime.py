# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for ``kailash.delegate.runtime`` (S6, #1035).

Covers TAOD state machine, Posture gating, R2 composition validator,
RuntimeExecutionResult shape + round-trip, and DelegateRuntime spine
construction + per-phase invariants. Per ``probe-driven-verification.md``
MUST Rule 3 all assertions here are STRUCTURAL (typed-error class,
phase value, count of audit entries, isinstance type checks) — no
semantic regex/keyword matching against prose output.

Tier classification: substrate dependencies (DispatchSurface,
AuditChainEngine, TenantScopedCascade, DelegateConstraintEnvelope) are
REAL — no mocks. The only "fake" object is the MockConnector subclass
satisfying the abstract Connector contract deterministically; per
``rules/testing.md`` § "Protocol-Satisfying Deterministic Adapters",
this is NOT a mock — it's a deterministic adapter for the abstract
Connector surface.

Mirrors rs kailash-delegate-runtime substrate.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from typing import Any

import pytest

from kailash.delegate.audit import AuditChainEngine, DelegateEventType
from kailash.delegate.dispatch import (
    Connector,
    ConnectorInvocationResult,
    DispatchResult,
    DispatchSurface,
)
from kailash.delegate.envelope import DelegateConstraintEnvelope
from kailash.delegate.runtime import (
    DelegateRuntime,
    Posture,
    R2Composition,
    R2CompositionError,
    RuntimeCompositionError,
    RuntimeExecutionResult,
    RuntimePhaseError,
    RuntimePostureBlockedError,
    TAODState,
    TAODTransition,
)
from kailash.delegate.trust import TenantScope, TenantScopedCascade
from kailash.delegate.types import (
    CapabilitySet,
    DelegateGenesisRecord,
    DelegateIdentity,
    Role,
    RoleLifecycleState,
    RoleScope,
)
from kailash.trust.chain import AuthorityType, GenesisRecord, TrustLineageChain
from kailash.trust.envelope import ConstraintEnvelope, FinancialConstraint


# ---------------------------------------------------------------------------
# Test signer — deterministic 128-char hex (SHA-256 doubled).
# ---------------------------------------------------------------------------


def _test_signer(canonical_bytes: bytes) -> str:
    """Deterministic SHA-256-doubled signer satisfying _validate_hex(128)."""
    h = hashlib.sha256(canonical_bytes).hexdigest()
    return h + h


# ---------------------------------------------------------------------------
# Substrate builders — real, no mocks
# ---------------------------------------------------------------------------


def _build_chain(agent_id: str = "agent-s6") -> TrustLineageChain:
    return TrustLineageChain(
        genesis=GenesisRecord(
            id=f"g-{agent_id}",
            agent_id=agent_id,
            authority_id=f"auth-{agent_id}",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc),
            signature="a" * 128,
        )
    )


def _build_identity() -> DelegateIdentity:
    return DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-s6",
        role_binding_ref="rb-s6",
        genesis_ref="g-agent-s6",
    )


def _build_envelope() -> DelegateConstraintEnvelope:
    block = GenesisRecord(
        id="g-env-s6",
        agent_id="agent-env-s6",
        authority_id="auth-env-s6",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc),
        signature="d" * 128,
    )
    genesis = DelegateGenesisRecord(
        block=block, spec_version="1", capabilities=("read",)
    )
    return DelegateConstraintEnvelope.from_genesis(
        ConstraintEnvelope(financial=FinancialConstraint(budget_limit=1000.0)),
        genesis,
    )


def _build_role() -> Role:
    return Role(
        role_id=uuid.uuid4(),
        display_name="s6-role",
        scope=RoleScope(
            domain="finance",
            capabilities=CapabilitySet(capabilities=("http.read",)),
        ),
        lifecycle=RoleLifecycleState.ACTIVE,
    )


def _build_cascade(tenant_id: str | None = "tenant-s6") -> TenantScopedCascade:
    if tenant_id is None:
        return TenantScopedCascade(tenant=TenantScope.global_())
    return TenantScopedCascade(tenant=TenantScope.for_tenant(tenant_id))


class _MockConnector(Connector):
    """Deterministic Connector subclass for runtime tests.

    Per ``rules/testing.md`` § "Protocol-Satisfying Deterministic
    Adapters", this is NOT a mock — it's a real Connector subclass.
    Per ``rules/testing.md`` MUST: Helper Classes Use Stub/Helper/Fake
    Suffix — leading underscore + lowercase indicates internal helper;
    pytest's `Test*` collection does not match this name.
    """

    connector_id = "s6-mock-conn"
    connector_kind = "http"
    requires_capabilities = frozenset({"http.read"})

    def __init__(
        self,
        *,
        return_payload: dict | None = None,
        tenant_id_observed: str | None = "tenant-s6",
        raise_exc: BaseException | None = None,
    ) -> None:
        self.return_payload = (
            return_payload if return_payload is not None else {"ok": True}
        )
        self.tenant_id_observed = tenant_id_observed
        self.raise_exc = raise_exc
        self.invocations: list[dict] = []

    async def invoke(self, input_payload, *, identity, envelope):
        self.invocations.append(
            {
                "input_payload": dict(input_payload),
                "identity_id": identity.delegate_id,
            }
        )
        if self.raise_exc is not None:
            raise self.raise_exc
        return ConnectorInvocationResult(
            payload=self.return_payload,
            audit_events=(DelegateEventType.EXTERNAL_SIDE_EFFECT,),
            tenant_id_observed=self.tenant_id_observed,
            external_side_effect=True,
        )


class _Sig:
    """Minimal SignatureContract-satisfier for runtime tests."""

    name = "s6-sig"
    input_schema = {"id": str}
    output_schema = {"ok": bool}


def _build_surface(
    *,
    connector: Connector | None = None,
    envelope: DelegateConstraintEnvelope | None = None,
    identity: DelegateIdentity | None = None,
    cascade: TenantScopedCascade | None = None,
    audit_engine: AuditChainEngine | None = None,
    role: Role | None = None,
    signer=None,
) -> tuple[
    DispatchSurface,
    DelegateConstraintEnvelope,
    DelegateIdentity,
    TenantScopedCascade,
    AuditChainEngine,
]:
    envelope = envelope if envelope is not None else _build_envelope()
    identity = identity if identity is not None else _build_identity()
    cascade = cascade if cascade is not None else _build_cascade()
    audit_engine = (
        audit_engine
        if audit_engine is not None
        else AuditChainEngine(chain=_build_chain())
    )
    role = role if role is not None else _build_role()
    signer = signer if signer is not None else _test_signer
    connector = connector if connector is not None else _MockConnector()
    surface = DispatchSurface(
        connector=connector,
        signature=_Sig(),
        envelope=envelope,
        identity=identity,
        audit_engine=audit_engine,
        trust_cascade=cascade,
        role=role,
        signer=signer,
    )
    return surface, envelope, identity, cascade, audit_engine


def _build_runtime(
    *,
    posture: Posture = Posture.L5_DELEGATED,
    connector: Connector | None = None,
) -> tuple[DelegateRuntime, _MockConnector | Connector, AuditChainEngine]:
    """Build a runtime with all real substrate primitives."""
    if connector is None:
        connector = _MockConnector()
    surface, envelope, identity, cascade, audit_engine = _build_surface(
        connector=connector,
    )
    runtime = DelegateRuntime(
        dispatch_surface=surface,
        audit_engine=audit_engine,
        cascade=cascade,
        envelope=envelope,
        identity=identity,
        signer=_test_signer,
        posture=posture,
    )
    return runtime, connector, audit_engine


# ---------------------------------------------------------------------------
# TAODTransition — frozen + validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_taod_transition_is_frozen() -> None:
    """Mirrors rs TaodTransition — frozen dataclass, no mutation."""
    t = TAODTransition(
        from_phase="initiated",
        to_phase="thinking",
        at=datetime.now(timezone.utc),
    )
    with pytest.raises(FrozenInstanceError):
        t.reason = "x"  # type: ignore[misc]


@pytest.mark.unit
def test_taod_transition_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        TAODTransition(
            from_phase="initiated",
            to_phase="thinking",
            at=datetime.now(),  # naive
        )


@pytest.mark.unit
def test_taod_transition_round_trip() -> None:
    """Mirrors rs TaodTransition serde — to_dict/from_dict round-trip."""
    original = TAODTransition(
        from_phase="thinking",
        to_phase="acting",
        at=datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc),
        reason="happy path",
    )
    restored = TAODTransition.from_dict(original.to_dict())
    assert restored == original


@pytest.mark.unit
def test_taod_transition_round_trip_omits_none_reason() -> None:
    """None reason omitted from to_dict per rs serde-skip-if-none."""
    original = TAODTransition(
        from_phase="thinking",
        to_phase="acting",
        at=datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc),
    )
    payload = original.to_dict()
    assert "reason" not in payload
    restored = TAODTransition.from_dict(payload)
    assert restored == original


# ---------------------------------------------------------------------------
# TAODState — phase machine
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_taod_state_initiated_is_not_terminal() -> None:
    s = TAODState(phase="initiated", started_at=datetime.now(timezone.utc))
    assert s.is_terminal is False
    assert len(s.transitions) == 0


@pytest.mark.unit
def test_taod_state_completed_is_terminal() -> None:
    s = TAODState(phase="completed", started_at=datetime.now(timezone.utc))
    assert s.is_terminal is True


@pytest.mark.unit
def test_taod_state_failed_is_terminal() -> None:
    s = TAODState(phase="failed", started_at=datetime.now(timezone.utc))
    assert s.is_terminal is True


@pytest.mark.unit
def test_taod_state_rejects_unknown_phase() -> None:
    with pytest.raises(ValueError, match="not a known TAODPhase"):
        TAODState(phase="bogus", started_at=datetime.now(timezone.utc))  # type: ignore[arg-type]


@pytest.mark.unit
def test_taod_state_legal_path_to_completion() -> None:
    """Initiated → thinking → acting → observing → completed."""
    s0 = TAODState(phase="initiated", started_at=datetime.now(timezone.utc))
    s1 = s0.advance_to("thinking")
    s2 = s1.advance_to("acting")
    s3 = s2.advance_to("observing")
    s4 = s3.advance_to("completed")
    assert s4.phase == "completed"
    assert len(s4.transitions) == 4
    # Transitions append-only — ordered
    assert [t.to_phase for t in s4.transitions] == [
        "thinking",
        "acting",
        "observing",
        "completed",
    ]


@pytest.mark.unit
def test_taod_state_legal_path_with_deciding() -> None:
    """Observing → deciding → completed is a legal alternate path."""
    s = TAODState(phase="observing", started_at=datetime.now(timezone.utc))
    s = s.advance_to("deciding").advance_to("completed")
    assert s.phase == "completed"


@pytest.mark.unit
def test_taod_state_terminal_rejects_further_transition() -> None:
    """Invariant 1 — completed state refuses any further transition."""
    s = TAODState(phase="completed", started_at=datetime.now(timezone.utc))
    with pytest.raises(RuntimePhaseError, match="terminal"):
        s.advance_to("failed")


@pytest.mark.unit
def test_taod_state_failed_refuses_further_transition() -> None:
    """Invariant 1 — failed state refuses any further transition."""
    s = TAODState(phase="failed", started_at=datetime.now(timezone.utc))
    with pytest.raises(RuntimePhaseError, match="terminal"):
        s.advance_to("completed")


@pytest.mark.unit
def test_taod_state_illegal_successor_rejected() -> None:
    """Phase machine rejects an illegal successor (initiated → completed)."""
    s = TAODState(phase="initiated", started_at=datetime.now(timezone.utc))
    with pytest.raises(RuntimePhaseError, match="Illegal TAOD transition"):
        s.advance_to("completed")


@pytest.mark.unit
def test_taod_state_failed_from_any_non_terminal_phase() -> None:
    """Every non-terminal phase may transition to failed."""
    for phase in ("initiated", "thinking", "acting", "observing", "deciding"):
        s = TAODState(phase=phase, started_at=datetime.now(timezone.utc))  # type: ignore[arg-type]
        advanced = s.advance_to("failed", reason="test")
        assert advanced.phase == "failed"


@pytest.mark.unit
def test_taod_state_round_trip() -> None:
    """Mirrors rs TaodState serde — to_dict/from_dict round-trip."""
    original = (
        TAODState(
            phase="initiated",
            started_at=datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc),
        )
        .advance_to("thinking", at=datetime(2026, 5, 22, 12, 0, 1, tzinfo=timezone.utc))
        .advance_to("acting", at=datetime(2026, 5, 22, 12, 0, 2, tzinfo=timezone.utc))
    )
    restored = TAODState.from_dict(original.to_dict())
    assert restored.phase == original.phase
    assert restored.started_at == original.started_at
    assert len(restored.transitions) == len(original.transitions)


# ---------------------------------------------------------------------------
# Posture enum
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_posture_string_values_match_rules() -> None:
    """Posture enum values mirror rules/trust-posture.md identifiers."""
    assert Posture.L5_DELEGATED.value == "L5_DELEGATED"
    assert Posture.L4_CONTINUOUS_INSIGHT.value == "L4_CONTINUOUS_INSIGHT"
    assert Posture.L3_SHARED_PLANNING.value == "L3_SHARED_PLANNING"
    assert Posture.L2_SUPERVISED.value == "L2_SUPERVISED"
    assert Posture.L1_PSEUDO_AGENT.value == "L1_PSEUDO_AGENT"
    assert Posture.HALT.value == "HALT"


@pytest.mark.unit
def test_posture_rank_monotonic() -> None:
    """Higher posture = higher rank; HALT is the floor."""
    ranks = [
        Posture.HALT._rank,
        Posture.L1_PSEUDO_AGENT._rank,
        Posture.L2_SUPERVISED._rank,
        Posture.L3_SHARED_PLANNING._rank,
        Posture.L4_CONTINUOUS_INSIGHT._rank,
        Posture.L5_DELEGATED._rank,
    ]
    assert ranks == sorted(ranks)
    assert Posture.HALT._rank == 0


# ---------------------------------------------------------------------------
# RuntimeExecutionResult — frozen + round-trip
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_runtime_execution_result_is_frozen() -> None:
    r = RuntimeExecutionResult(
        run_id=uuid.uuid4(),
        dispatch_result=None,
        taod_state=TAODState(phase="failed", started_at=datetime.now(timezone.utc)),
        audit_head_hash=None,
        terminated_at=datetime.now(timezone.utc),
        posture_at_execute=Posture.L5_DELEGATED,
    )
    with pytest.raises(FrozenInstanceError):
        r.run_id = uuid.uuid4()  # type: ignore[misc]


@pytest.mark.unit
def test_runtime_execution_result_round_trip_no_dispatch() -> None:
    original = RuntimeExecutionResult(
        run_id=uuid.uuid4(),
        dispatch_result=None,
        taod_state=(
            TAODState(
                phase="failed",
                started_at=datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc),
            ).advance_to(
                "failed",  # not a legal transition? failed is terminal-from-init?
                at=datetime(2026, 5, 22, 12, 0, 1, tzinfo=timezone.utc),
            )
            if False  # bypass — failed-from-failed would raise; use init-state alone
            else TAODState(
                phase="failed",
                started_at=datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc),
            )
        ),
        audit_head_hash="ab" * 32,
        terminated_at=datetime(2026, 5, 22, 12, 0, 1, tzinfo=timezone.utc),
        posture_at_execute=Posture.HALT,
    )
    restored = RuntimeExecutionResult.from_dict(original.to_dict())
    assert restored.run_id == original.run_id
    assert restored.dispatch_result is None
    assert restored.audit_head_hash == original.audit_head_hash
    assert restored.posture_at_execute == Posture.HALT
    assert restored.terminated_at == original.terminated_at


@pytest.mark.unit
def test_runtime_execution_result_rejects_naive_terminated_at() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        RuntimeExecutionResult(
            run_id=uuid.uuid4(),
            dispatch_result=None,
            taod_state=TAODState(phase="failed", started_at=datetime.now(timezone.utc)),
            audit_head_hash=None,
            terminated_at=datetime.now(),  # naive
            posture_at_execute=Posture.L5_DELEGATED,
        )


# ---------------------------------------------------------------------------
# R2Composition — composition validator
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_r2_composition_validates_clean_composition() -> None:
    """A correctly-bound composition validates without raising."""
    surface, envelope, identity, cascade, audit_engine = _build_surface()
    R2Composition.validate(
        envelope=envelope,
        cascade=cascade,
        dispatch_surface=surface,
        audit_engine=audit_engine,
        signer=_test_signer,
    )


@pytest.mark.unit
def test_r2_composition_rejects_envelope_swap() -> None:
    """Envelope-swap post-bind detected via `is` check (not value equality).

    Mirrors rs R2 composition gate. A value-equal but DISTINCT envelope
    is the substitution attack this guard closes.
    """
    surface, envelope, identity, cascade, audit_engine = _build_surface()
    # Build a NEW envelope with the same VALUES but distinct identity.
    swapped_envelope = _build_envelope()
    assert swapped_envelope is not envelope
    with pytest.raises(R2CompositionError, match="envelope"):
        R2Composition.validate(
            envelope=swapped_envelope,
            cascade=cascade,
            dispatch_surface=surface,
            audit_engine=audit_engine,
            signer=_test_signer,
        )


@pytest.mark.unit
def test_r2_composition_rejects_cascade_swap() -> None:
    surface, envelope, identity, cascade, audit_engine = _build_surface()
    swapped_cascade = _build_cascade(tenant_id="tenant-s6")
    assert swapped_cascade is not cascade
    with pytest.raises(R2CompositionError, match="cascade"):
        R2Composition.validate(
            envelope=envelope,
            cascade=swapped_cascade,
            dispatch_surface=surface,
            audit_engine=audit_engine,
            signer=_test_signer,
        )


@pytest.mark.unit
def test_r2_composition_rejects_signer_swap() -> None:
    """Signer identity mismatch is signature forgery — BLOCKED.

    Mirrors rs Invariant 6 — signer identity preservation.
    """
    surface, envelope, identity, cascade, audit_engine = _build_surface()

    def _alt_signer(b: bytes) -> str:
        return _test_signer(b)  # value-equal output, distinct object

    assert _alt_signer is not _test_signer
    with pytest.raises(R2CompositionError, match="signer"):
        R2Composition.validate(
            envelope=envelope,
            cascade=cascade,
            dispatch_surface=surface,
            audit_engine=audit_engine,
            signer=_alt_signer,
        )


# ---------------------------------------------------------------------------
# DelegateRuntime — construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_runtime_constructs_with_clean_composition() -> None:
    runtime, _, _ = _build_runtime()
    assert runtime.posture == Posture.L5_DELEGATED


@pytest.mark.unit
def test_runtime_rejects_identity_swap() -> None:
    """Identity-swap between dispatch surface and runtime is BLOCKED."""
    surface, envelope, identity, cascade, audit_engine = _build_surface()
    swapped_identity = _build_identity()
    assert swapped_identity is not identity
    with pytest.raises(RuntimeCompositionError, match="identity"):
        DelegateRuntime(
            dispatch_surface=surface,
            audit_engine=audit_engine,
            cascade=cascade,
            envelope=envelope,
            identity=swapped_identity,
            signer=_test_signer,
            posture=Posture.L5_DELEGATED,
        )


@pytest.mark.unit
def test_runtime_rejects_non_callable_signer() -> None:
    surface, envelope, identity, cascade, audit_engine = _build_surface()
    with pytest.raises(TypeError, match="callable"):
        DelegateRuntime(
            dispatch_surface=surface,
            audit_engine=audit_engine,
            cascade=cascade,
            envelope=envelope,
            identity=identity,
            signer="not-a-callable",  # type: ignore[arg-type]
            posture=Posture.L5_DELEGATED,
        )


# ---------------------------------------------------------------------------
# with_posture — Invariant 5 (downgrade silent, upgrade gated)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_with_posture_downgrade_silent() -> None:
    """Downgrades L5 → L4 / L1 / HALT need NO nonce."""
    runtime, _, _ = _build_runtime(posture=Posture.L5_DELEGATED)
    for target in (
        Posture.L4_CONTINUOUS_INSIGHT,
        Posture.L3_SHARED_PLANNING,
        Posture.L2_SUPERVISED,
        Posture.L1_PSEUDO_AGENT,
        Posture.HALT,
    ):
        new_runtime = runtime.with_posture(target)
        assert new_runtime.posture == target


@pytest.mark.unit
def test_with_posture_same_posture_is_silent() -> None:
    """No-op (same rank) does not require a nonce."""
    runtime, _, _ = _build_runtime(posture=Posture.L3_SHARED_PLANNING)
    new_runtime = runtime.with_posture(Posture.L3_SHARED_PLANNING)
    assert new_runtime.posture == Posture.L3_SHARED_PLANNING


@pytest.mark.unit
def test_with_posture_upgrade_without_nonce_refused() -> None:
    """Upgrade without nonce raises RuntimePostureBlockedError."""
    runtime, _, _ = _build_runtime(posture=Posture.L2_SUPERVISED)
    with pytest.raises(RuntimePostureBlockedError, match="human_acknowledged_nonce"):
        runtime.with_posture(Posture.L5_DELEGATED)


@pytest.mark.unit
def test_with_posture_upgrade_with_nonce_accepted() -> None:
    """Upgrade with sufficiently-long nonce is accepted.

    Per S6 R1 C1 fix: nonce MUST be >= _MIN_NONCE_LENGTH (16) chars
    to satisfy the SYNTACTIC posture-upgrade gate. The runtime does
    NOT validate the nonce cryptographically — S8 nonce-registry
    integration owns that — but the length floor closes the trivial
    truthy-string bypass (any non-empty string used to pass).
    """
    runtime, _, _ = _build_runtime(posture=Posture.L2_SUPERVISED)
    new_runtime = runtime.with_posture(
        Posture.L4_CONTINUOUS_INSIGHT,
        human_acknowledged_nonce="ack-1234567890abcd",  # 18 chars >= 16
    )
    assert new_runtime.posture == Posture.L4_CONTINUOUS_INSIGHT


@pytest.mark.unit
def test_with_posture_upgrade_empty_nonce_refused() -> None:
    """Empty-string nonce does NOT satisfy the upgrade gate."""
    runtime, _, _ = _build_runtime(posture=Posture.L2_SUPERVISED)
    with pytest.raises(RuntimePostureBlockedError, match="human_acknowledged_nonce"):
        runtime.with_posture(Posture.L4_CONTINUOUS_INSIGHT, human_acknowledged_nonce="")


# ---------------------------------------------------------------------------
# execute() — TAOD lifecycle (Tier-1; substrate primitives are REAL)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_happy_path_completes() -> None:
    """A clean execute() walks INITIATED → … → COMPLETED.

    Mirrors rs DelegateRuntime::execute — verifies the TAOD phase order
    on a clean dispatch path.
    """
    runtime, connector, audit_engine = _build_runtime()
    result = await runtime.execute({"id": "x-1"})
    assert isinstance(result, RuntimeExecutionResult)
    assert result.taod_state.phase == "completed"
    assert result.dispatch_result is not None
    assert result.posture_at_execute == Posture.L5_DELEGATED
    # Transitions: initiated→thinking, thinking→acting,
    # acting→observing, observing→completed (no deciding).
    assert [t.to_phase for t in result.taod_state.transitions] == [
        "thinking",
        "acting",
        "observing",
        "completed",
    ]
    assert result.audit_head_hash is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_with_decision_required_passes_through_deciding() -> None:
    """Connector payload signals _decision_required → DECIDING phase fires."""
    connector = _MockConnector(return_payload={"ok": True, "_decision_required": True})
    runtime, _, _ = _build_runtime(connector=connector)
    result = await runtime.execute({"id": "x-dec"})
    assert result.taod_state.phase == "completed"
    assert [t.to_phase for t in result.taod_state.transitions] == [
        "thinking",
        "acting",
        "observing",
        "deciding",
        "completed",
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_posture_halt_refuses_at_thinking() -> None:
    """Invariant 2 — HALT posture refuses execute() at THINKING phase."""
    runtime, connector, audit_engine = _build_runtime(posture=Posture.HALT)
    result = await runtime.execute({"id": "x-halt"})
    assert result.taod_state.phase == "failed"
    assert result.dispatch_result is None
    # Connector never invoked
    assert len(connector.invocations) == 0
    # Final transition cites posture_halt
    last_transition = result.taod_state.transitions[-1]
    assert last_transition.to_phase == "failed"
    assert "HALT" in (last_transition.reason or "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_dispatch_failure_transitions_to_failed() -> None:
    """Dispatch raises → TAODState lands in FAILED.

    Per S6 R1 LOW-1: the TAOD reason field is SANITIZED — only the
    exception class name leaks to the observable
    ``RuntimeExecutionResult.to_dict()`` surface. The full
    ``str(exc)`` lives in the audit chain's signed payload (sized to
    forensic verification surface), NOT on the public reason field.
    """
    connector = _MockConnector(raise_exc=RuntimeError("boom"))
    runtime, _, _ = _build_runtime(connector=connector)
    result = await runtime.execute({"id": "x-fail"})
    assert result.taod_state.phase == "failed"
    last_transition = result.taod_state.transitions[-1]
    assert last_transition.to_phase == "failed"
    # Sanitized reason — class name only, raw exception message MUST NOT bleed.
    assert "RuntimeError" in (last_transition.reason or "")
    assert "boom" not in (last_transition.reason or "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_emits_audit_event_per_transition() -> None:
    """Invariant 3 — every TAOD transition emits exactly one audit event.

    On happy path with no deciding: 4 transitions (initiated→thinking,
    thinking→acting, acting→observing, observing→completed) → 4 runtime
    events PLUS 1 dispatch event from the connector's
    EXTERNAL_SIDE_EFFECT = 5 audit entries total.
    """
    runtime, connector, audit_engine = _build_runtime()
    pre_count = len(audit_engine.entries)
    result = await runtime.execute({"id": "x-aud"})
    post_count = len(audit_engine.entries)
    # 4 runtime transitions + 1 dispatch event
    assert post_count - pre_count == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_audit_events_bind_run_id() -> None:
    """Invariant 3 — every runtime-emitted audit event carries run_id."""
    runtime, _, audit_engine = _build_runtime()
    result = await runtime.execute({"id": "x-rid"})
    run_id_str = str(result.run_id)
    # Every runtime-emitted audit entry (NOT the dispatch surface's
    # EXTERNAL_SIDE_EFFECT) carries the run_id binding. Filter on the
    # presence of the run_id key in payload.
    runtime_entries = [e for e in audit_engine.entries if "run_id" in e.event_payload]
    assert len(runtime_entries) >= 4  # at least the 4 phase transitions
    for entry in runtime_entries:
        assert entry.event_payload["run_id"] == run_id_str


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_run_id_is_unique_across_invocations() -> None:
    """Two execute() calls on DIFFERENT runtimes produce distinct run_ids.

    Per §7 (single-shot enforcement), a single runtime instance can
    only execute() ONCE — receipts are bound per-runtime. Run-id
    uniqueness is therefore verified across two FRESH runtime instances
    rather than two calls on one runtime.
    """
    runtime1, _, _ = _build_runtime()
    runtime2, _, _ = _build_runtime()
    r1 = await runtime1.execute({"id": "x-1"})
    r2 = await runtime2.execute({"id": "x-2"})
    assert r1.run_id != r2.run_id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_run_id_is_uuid4() -> None:
    """Run-id MUST be a UUID4 per secrets-backed generator."""
    runtime, _, _ = _build_runtime()
    result = await runtime.execute({"id": "x-uuid"})
    assert isinstance(result.run_id, uuid.UUID)
    assert result.run_id.version == 4


# ---------------------------------------------------------------------------
# S6 R1 fix-immediately tests — A3/D1, C1, MED-1, LOW-1
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_audit_emit_failure_during_thinking_phase_keeps_state_consistent() -> (
    None
):
    """S6 R1 A3/D1: audit emit BEFORE state advance.

    When ``_emit_phase_audit`` raises during the THINKING transition,
    the state MUST NOT advance to "thinking" with no audit record.
    Instead, the runtime transitions to FAILED with a SANITIZED reason
    naming only the failure phase + exception class — no recursion
    into another audit emit (the audit subsystem itself broke), and
    no exception propagates from execute() (the no-throw contract is
    preserved).
    """
    runtime, _, audit_engine = _build_runtime()

    # Force the audit engine's emit_event to raise on the FIRST call
    # (which is the THINKING transition's audit). State at that point
    # is still "initiated" — must transition directly to "failed".
    call_count = {"n": 0}
    original_emit = audit_engine.emit_event

    def _raising_emit(*args: Any, **kwargs: Any) -> Any:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("audit-subsystem-broken")
        return original_emit(*args, **kwargs)

    audit_engine.emit_event = _raising_emit  # type: ignore[method-assign]

    # No exception propagates; FAILED transition is observable.
    result = await runtime.execute({"id": "x-audit-fail"})
    assert result.taod_state.phase == "failed"
    # Only one transition: initiated→failed; thinking was never
    # entered because the audit emit failed first.
    transitions = result.taod_state.transitions
    assert len(transitions) == 1
    assert transitions[0].from_phase == "initiated"
    assert transitions[0].to_phase == "failed"
    # Reason cites the failed phase + audit-exception class — NOT the
    # raw exception message (LOW-1 sanitization discipline).
    reason = transitions[0].reason or ""
    assert "thinking" in reason
    assert "RuntimeError" in reason
    assert "audit-subsystem-broken" not in reason


@pytest.mark.unit
def test_posture_upgrade_rejects_short_nonce() -> None:
    """S6 R1 C1: nonce shorter than _MIN_NONCE_LENGTH (16) is refused.

    A truthy one-char string used to satisfy the upgrade gate; the
    hardened SYNTACTIC check rejects any nonce shorter than 16 chars
    so the trivial bypass surface ("x" satisfied the gate) is closed.
    """
    runtime, _, _ = _build_runtime(posture=Posture.L2_SUPERVISED)
    with pytest.raises(RuntimePostureBlockedError, match="length >= 16"):
        runtime.with_posture(Posture.L5_DELEGATED, human_acknowledged_nonce="x")


@pytest.mark.unit
def test_posture_upgrade_accepts_sixteen_char_nonce() -> None:
    """S6 R1 C1: nonce of exactly _MIN_NONCE_LENGTH (16) chars is accepted.

    Boundary test: at the floor the gate admits the upgrade. The
    audit-event side-effect of with_posture (S6 R1 MED-1) also fires
    cleanly — no posture-blocked-error from audit emission.
    """
    runtime, _, _ = _build_runtime(posture=Posture.L2_SUPERVISED)
    new_runtime = runtime.with_posture(
        Posture.L5_DELEGATED,
        human_acknowledged_nonce="x" * 16,
    )
    assert new_runtime.posture == Posture.L5_DELEGATED


@pytest.mark.unit
def test_with_posture_emits_audit_event_on_source_runtime() -> None:
    """S6 R1 MED-1: every posture rotation emits an audit event.

    Posture rotations (both upgrades AND downgrades) are
    security-relevant transitions; an attacker holding a legitimate
    L5_DELEGATED runtime that could call .with_posture(L1) silently
    would leave the downgrade invisible to forensic correlation. The
    audit event MUST land on the source runtime's audit engine and
    carry from_posture, to_posture, and rank_delta in the payload.
    """
    runtime, _, audit_engine = _build_runtime(posture=Posture.L5_DELEGATED)
    pre_count = len(audit_engine.entries)

    # Downgrade (no nonce required) — MUST still emit.
    new_runtime = runtime.with_posture(Posture.L2_SUPERVISED)
    assert new_runtime.posture == Posture.L2_SUPERVISED

    post_count = len(audit_engine.entries)
    assert post_count - pre_count == 1
    rotation_entry = audit_engine.entries[-1]
    # Event type is POSTURE_OR_SOVEREIGN_HANDOVER per S6 contract.
    assert (
        rotation_entry.event_type
        == DelegateEventType.POSTURE_OR_SOVEREIGN_HANDOVER.value
    )
    payload = rotation_entry.event_payload
    assert payload["from_posture"] == "L5_DELEGATED"
    assert payload["to_posture"] == "L2_SUPERVISED"
    assert payload["rank_delta"] == -3  # 2 - 5
    assert payload["nonce_present"] is False  # downgrade carries no nonce
    assert "rotation_id" in payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failed_reason_field_is_sanitized() -> None:
    """S6 R1 LOW-1: FAILED transition reason is sanitized for to_dict.

    The TAOD state's reason field is the OBSERVABLE surface exposed
    via RuntimeExecutionResult.to_dict() → downstream logs/aggregators
    per observability.md Rule 8. Schema-revealing adapter-internal
    messages MUST NOT bleed into the reason field; the full message
    lives in the signed audit-event payload (already sized to
    forensic verification surface).
    """
    # Induce a dispatch error with a distinctive raw message —
    # the message MUST NOT appear in the TAOD reason field.
    sensitive_msg = "SENSITIVE_ADAPTER_INTERNAL_DETAIL_XYZ"
    connector = _MockConnector(raise_exc=ValueError(sensitive_msg))
    runtime, _, audit_engine = _build_runtime(connector=connector)
    result = await runtime.execute({"id": "x-low1"})

    # Verify dispatch did fail
    assert result.taod_state.phase == "failed"
    last_transition = result.taod_state.transitions[-1]
    assert last_transition.to_phase == "failed"

    # Critical: raw exception message MUST NOT appear in the
    # observable reason field
    reason = last_transition.reason or ""
    assert sensitive_msg not in reason
    # Class name IS allowed in reason (taxonomy signal)
    assert "ValueError" in reason

    # But the audit payload SHOULD carry the full message (signed +
    # bounded forensic surface). Find the FAILED audit entry.
    failed_entries = [
        e
        for e in audit_engine.entries
        if e.event_payload.get("phase") == "failed"
        and e.event_payload.get("reason") == "dispatch_error"
    ]
    assert len(failed_entries) == 1
    assert failed_entries[0].event_payload["error_message"] == sensitive_msg


@pytest.mark.unit
@pytest.mark.asyncio
async def test_to_dict_does_not_leak_raw_exception_message() -> None:
    """S6 R1 LOW-1: round-trip TAODState.to_dict() never carries raw exc.

    Direct verification of the observability contract: the dict
    payload that flows into downstream consumers MUST NOT carry the
    raw adapter-internal exception message anywhere — not in the
    reason field, not as a substring of any other field.
    """
    sensitive_msg = "DOWNSTREAM_SCHEMA_LEAK_CANARY"
    connector = _MockConnector(raise_exc=RuntimeError(sensitive_msg))
    runtime, _, _ = _build_runtime(connector=connector)
    result = await runtime.execute({"id": "x-leak"})

    # Walk the to_dict() payload for any occurrence of the sensitive
    # message. Stringify the entire dict so a nested embedding would
    # be caught.
    state_dict_str = str(result.taod_state.to_dict())
    assert sensitive_msg not in state_dict_str


# ---------------------------------------------------------------------------
# §7 TAOD phase monotonicity at the runtime level — single-shot enforcement
# (pins DV-7-001 conformance vector; mirrors rs DelegateRuntime semantics)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runtime_re_execute_after_completed_raises_phase_error() -> None:
    """§7 TAOD phase monotonicity — re-execute on COMPLETED MUST raise.

    Pins the DV-7-001 conformance vector at the runtime spine. The
    runtime is single-shot per receipt; a second execute() raises
    :class:`RuntimePhaseError` with the "single-shot" marker so the
    caller can distinguish this from other phase-error classes (e.g.
    TAODState terminal-transition errors).
    """
    runtime, _, _ = _build_runtime()
    result1 = await runtime.execute({"id": "first"})
    assert result1.taod_state.phase == "completed"

    with pytest.raises(RuntimePhaseError, match="single-shot"):
        await runtime.execute({"id": "second"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runtime_consumed_even_on_failed_execute() -> None:
    """§7 enforcement holds on FAILED path — no retry-until-success surface.

    A runtime whose first execute() FAILED (dispatch raised) MUST
    still be consumed. Otherwise an attacker could retry a failing
    dispatch until it happened to succeed, silently amplifying their
    audit footprint without a fresh receipt-bound run_id.
    """
    connector = _MockConnector(raise_exc=RuntimeError("boom"))
    runtime, _, _ = _build_runtime(connector=connector)
    result1 = await runtime.execute({"id": "first"})
    assert result1.taod_state.phase == "failed"

    with pytest.raises(RuntimePhaseError, match="single-shot"):
        await runtime.execute({"id": "second"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runtime_consumed_even_on_posture_halt_refusal() -> None:
    """§7 enforcement holds on POSTURE-HALT refusal path.

    A HALT-postured runtime refuses execute() at THINKING and returns
    a FAILED result. That refusal STILL consumes the runtime — a
    subsequent execute() (e.g. after the operator "thought" the posture
    flipped back) MUST also refuse.
    """
    runtime, _, _ = _build_runtime(posture=Posture.HALT)
    result1 = await runtime.execute({"id": "first"})
    assert result1.taod_state.phase == "failed"

    with pytest.raises(RuntimePhaseError, match="single-shot"):
        await runtime.execute({"id": "second"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runtime_with_posture_returns_fresh_unconsumed_runtime() -> None:
    """Invariant 5 + §7 interaction — with_posture() returns a fresh runtime.

    A runtime that has been consumed cannot execute() again, but
    :meth:`with_posture` returns a NEW :class:`DelegateRuntime` instance.
    That new instance MUST be un-consumed (the consumed flag is per-
    instance state, NOT shared across the with_posture() seam).
    """
    runtime, _, _ = _build_runtime(posture=Posture.L5_DELEGATED)
    result1 = await runtime.execute({"id": "first"})
    assert result1.taod_state.phase == "completed"

    # Source runtime is consumed
    with pytest.raises(RuntimePhaseError, match="single-shot"):
        await runtime.execute({"id": "second"})

    # Downgrade — no nonce required (rank-decreasing)
    fresh = runtime.with_posture(Posture.L3_SHARED_PLANNING)
    assert fresh is not runtime  # new instance

    # Fresh runtime is un-consumed and can execute()
    result_fresh = await fresh.execute({"id": "fresh"})
    assert result_fresh.taod_state.phase == "completed"
    assert result_fresh.posture_at_execute == Posture.L3_SHARED_PLANNING
