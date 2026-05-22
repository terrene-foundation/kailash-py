# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration test for ``DelegateRuntime`` end-to-end wiring.

S6 #1035 — Tier-2 wiring test per ``facade-manager-detection.md`` MUST
Rule 1 ("Every Manager-Shape Class Has a Tier 2 Test"):
:class:`DelegateRuntime` composes ``DispatchSurface`` (S5) +
``AuditChainEngine`` (S4) + ``TenantScopedCascade`` (S3) +
``DelegateConstraintEnvelope`` (S2.5) + ``DelegateIdentity`` (S2) into
the TAOD execution lifecycle.

This test exercises the load-bearing wiring contract end-to-end:

- A real ``TenantScopedCascade`` anchors tenant isolation.
- A real ``AuditChainEngine`` (atop a real ``TrustLineageChain``)
  receives the run_id-bound TAOD transition audit events.
- A real ``DispatchSurface`` binds connector + signature + envelope +
  identity per S5.
- A real :class:`Connector` subclass produces real
  :class:`ConnectorInvocationResult` records that flow through the
  audit emission path.

Tier classification: per ``rules/testing.md`` § "Protocol-Satisfying
Deterministic Adapters" the :class:`Connector` subclasses below are NOT
mocks — they satisfy the abstract surface deterministically. Every
substrate dependency (chain, engine, cascade, envelope, identity) is a
real instance, no mocks.

Mirrors rs kailash-delegate-runtime substrate. The end-to-end audit
chain produced here is the byte-canonical fixture shape S7 conformance
vectors will pin.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import pytest

from kailash.delegate.audit import AuditChainEngine, DelegateEventType
from kailash.delegate.dispatch import (
    Connector,
    ConnectorInvocationResult,
    DispatchSurface,
)
from kailash.delegate.envelope import DelegateConstraintEnvelope
from kailash.delegate.runtime import (
    DelegateRuntime,
    Posture,
    R2CompositionError,
    RuntimeExecutionResult,
    RuntimePhaseError,
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


def _test_signer(canonical_bytes: bytes) -> str:
    """Deterministic 128-char hex signer for integration tests."""
    h = hashlib.sha256(canonical_bytes).hexdigest()
    return h + h


# ---------------------------------------------------------------------------
# Substrate builders (real, no mocks)
# ---------------------------------------------------------------------------


def _build_chain(agent_id: str = "agent-rt-wire") -> TrustLineageChain:
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
        sovereign_ref="sov-rt-wire",
        role_binding_ref="rb-rt-wire",
        genesis_ref="g-agent-rt-wire",
    )


def _build_envelope() -> DelegateConstraintEnvelope:
    block = GenesisRecord(
        id="g-env-rt-wire",
        agent_id="agent-env-rt-wire",
        authority_id="auth-env-rt-wire",
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
        display_name="rt-wire-role",
        scope=RoleScope(
            domain="finance",
            capabilities=CapabilitySet(capabilities=("http.read",)),
        ),
        lifecycle=RoleLifecycleState.ACTIVE,
    )


class RecordingConnector(Connector):
    """Records every connector.invoke arg for wiring assertions."""

    connector_id = "rt-wire-conn"
    connector_kind = "http"
    requires_capabilities = frozenset({"http.read"})

    def __init__(self, *, tenant_id_observed: str = "tenant-rt-wire") -> None:
        self.tenant_id_observed = tenant_id_observed
        self.invocations: list[dict] = []

    async def invoke(self, input_payload, *, identity, envelope):
        self.invocations.append(
            {
                "input_payload": dict(input_payload),
                "identity_id": identity.delegate_id,
            }
        )
        return ConnectorInvocationResult(
            payload={"ok": True, "echo": input_payload.get("id", "n/a")},
            audit_events=(DelegateEventType.EXTERNAL_SIDE_EFFECT,),
            tenant_id_observed=self.tenant_id_observed,
            external_side_effect=True,
        )


class WiringSig:
    """Minimal SignatureContract satisfier."""

    name = "rt-wire-sig"
    input_schema = {"id": str}
    output_schema = {"ok": bool, "echo": str}


def _build_runtime_stack(
    *,
    posture: Posture = Posture.L5_DELEGATED,
    tenant_id: str = "tenant-rt-wire",
    connector_tenant_id: str | None = None,
):
    """Construct the full runtime stack with real primitives."""
    chain = _build_chain()
    audit_engine = AuditChainEngine(chain=chain)
    cascade = TenantScopedCascade(tenant=TenantScope.for_tenant(tenant_id))
    envelope = _build_envelope()
    identity = _build_identity()
    role = _build_role()
    # #1146 H1 — seed the cascade with the root grantee so DispatchSurface
    # bind passes the grantee gate.
    cascade.register_root_grantee(identity)
    connector = RecordingConnector(
        tenant_id_observed=connector_tenant_id or tenant_id,
    )
    surface = DispatchSurface(
        connector=connector,
        signature=WiringSig(),
        envelope=envelope,
        identity=identity,
        audit_engine=audit_engine,
        trust_cascade=cascade,
        role=role,
        signer=_test_signer,
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
    return runtime, surface, audit_engine, chain, connector


# ---------------------------------------------------------------------------
# Tier-2 wiring tests — every dependency is REAL
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_runtime_end_to_end_full_taod_lifecycle_against_real_substrate() -> None:
    """Mirrors rs DelegateRuntime end-to-end test.

    Wiring contract verified:
    1. Runtime invokes DispatchSurface.dispatch (connector records args).
    2. AuditChainEngine receives runtime-emitted TAOD events PLUS the
       dispatch-emitted EXTERNAL_SIDE_EFFECT event.
    3. All runtime audit events bind the run_id (Invariant 3).
    4. RuntimeExecutionResult carries valid dispatch_result + audit head hash.
    """
    runtime, surface, audit_engine, chain, connector = _build_runtime_stack()

    # Pre-execute: chain empty
    assert len(audit_engine.entries) == 0
    assert len(chain.audit_anchors) == 0
    assert len(connector.invocations) == 0

    result = await runtime.execute({"id": "rt-1"})

    # 1. Connector invoked exactly once with the bound identity
    assert len(connector.invocations) == 1
    inv = connector.invocations[0]
    assert inv["identity_id"] == runtime.identity.delegate_id
    assert inv["input_payload"] == {"id": "rt-1"}

    # 2. RuntimeExecutionResult shape
    assert isinstance(result, RuntimeExecutionResult)
    assert result.taod_state.phase == "completed"
    assert result.dispatch_result is not None
    assert result.dispatch_result.payload == {"ok": True, "echo": "rt-1"}
    assert result.posture_at_execute == Posture.L5_DELEGATED

    # 3. Audit chain has runtime transitions + dispatch event landed on
    # the SHARED substrate chain (`audit_engine.entries` is the engine's
    # tracked list; `chain.audit_anchors` is the substrate's list — both
    # MUST stay in lockstep per S4 contract).
    assert len(audit_engine.entries) == len(chain.audit_anchors)
    # 4 runtime transitions + 1 dispatch event = 5 entries
    assert len(audit_engine.entries) == 5

    # 4. Every runtime-emitted entry carries run_id (Invariant 3).
    runtime_entries = [e for e in audit_engine.entries if "run_id" in e.event_payload]
    run_id_str = str(result.run_id)
    for e in runtime_entries:
        assert e.event_payload["run_id"] == run_id_str

    # 5. Audit head hash on the result matches the engine's current head
    assert result.audit_head_hash == audit_engine.head_hash()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_runtime_posture_halt_after_construction_blocks_at_thinking() -> None:
    """HALT posture set POST-construction blocks at THINKING phase.

    The runtime is built L5; with_posture downgrades to HALT; the next
    execute() halts at THINKING without invoking the dispatch surface.
    """
    runtime, surface, audit_engine, chain, connector = _build_runtime_stack(
        posture=Posture.L5_DELEGATED,
    )

    halted_runtime = runtime.with_posture(Posture.HALT)

    result = await halted_runtime.execute({"id": "rt-halt"})

    # Failed at thinking, connector never invoked
    assert result.taod_state.phase == "failed"
    assert result.dispatch_result is None
    assert len(connector.invocations) == 0
    # Runtime emitted at least one runtime audit event (the THINKING
    # phase entry) AND the FAILED transition audit; no dispatch events.
    runtime_entries = [e for e in audit_engine.entries if "run_id" in e.event_payload]
    assert len(runtime_entries) >= 2  # THINKING + FAILED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_runtime_r2_recheck_catches_envelope_swap_between_construct_and_execute() -> (
    None
):
    """Invariant 4 — R2 composition re-check fires at execute() start.

    Construct runtime cleanly; then externally mutate the runtime's
    private envelope reference to a swapped-in envelope (simulating
    component reconstruction between bind and execute). The execute()
    start MUST detect the drift and transition to FAILED without
    invoking the dispatch surface.
    """
    runtime, surface, audit_engine, chain, connector = _build_runtime_stack()

    # Swap envelope post-construction (simulates external mutation
    # between __init__ and execute() — the failure mode Invariant 4
    # defense-in-depth catches).
    swapped_envelope = _build_envelope()
    assert swapped_envelope is not runtime._envelope
    runtime._envelope = swapped_envelope

    result = await runtime.execute({"id": "rt-r2"})

    # R2 re-check at execute() start should land FAILED
    assert result.taod_state.phase == "failed"
    assert result.dispatch_result is None
    # Connector NEVER invoked — failure precedes ACTING
    assert len(connector.invocations) == 0
    # The transition reason cites the R2 composition failure
    last_transition = result.taod_state.transitions[-1]
    assert "R2 composition" in (last_transition.reason or "")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_runtime_re_execute_after_completed_blocked_at_wiring_layer() -> None:
    """§7 TAOD phase monotonicity enforced end-to-end through real substrate.

    Tier-2 evidence that the §7 single-shot enforcement holds at the
    full wiring layer (not just the unit-level guard). After a clean
    COMPLETED run, a second execute() on the same runtime raises
    RuntimePhaseError; the audit chain reflects ONLY the first run's
    transitions (no second-run audit emission leaked).

    Reconciles the pre-§7 contract (`test_runtime_executes_multiple_
    runs_on_same_substrate`) which asserted the OPPOSITE behaviour. Per
    `orphan-detection.md` Rule 4a (stub-implementation MUST sweep
    deferral tests in same commit), the contradicting wiring test is
    deleted in the same commit that enforces §7 at the runtime spine.
    Sibling unit tests: `tests/unit/delegate/test_runtime.py::
    test_runtime_re_execute_after_completed_raises_phase_error` (+
    failed-path + posture-halt + with_posture variants).
    """
    runtime, surface, audit_engine, chain, connector = _build_runtime_stack()

    # First execute: happy path to COMPLETED
    r1 = await runtime.execute({"id": "rt-single-1"})
    assert r1.taod_state.phase == "completed"
    assert r1.dispatch_result is not None

    # Audit chain reflects exactly the first run: 4 runtime transitions
    # + 1 dispatch event = 5 entries. Same baseline as the end-to-end
    # full-lifecycle test above.
    assert len(audit_engine.entries) == 5
    assert len(audit_engine.entries) == len(chain.audit_anchors)
    pre_second_count = len(audit_engine.entries)

    # Second execute: MUST raise the §7 single-shot guard
    with pytest.raises(RuntimePhaseError, match="single-shot"):
        await runtime.execute({"id": "rt-single-2"})

    # No second-run audit emission leaked: chain cardinality unchanged
    assert len(audit_engine.entries) == pre_second_count
    assert len(audit_engine.entries) == len(chain.audit_anchors)

    # Connector NEVER invoked for the second attempt — the guard
    # fires before any dispatch path
    assert len(connector.invocations) == 1
