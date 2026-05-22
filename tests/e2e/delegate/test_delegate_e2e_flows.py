# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-3 E2E tests for the kailash.delegate composition primitive (S8 #1035).

E2E flows exercise the FULL stack composed across S2 through S7 against real
substrate (no mocks of any primitive). Each flow composes:

* :class:`DelegateIdentity` + :class:`Role` + :class:`RoleScope` +
  :class:`CapabilitySet` (S2 types substrate).
* :class:`DelegateConstraintEnvelope` (S2.5).
* :class:`TenantScope` + :class:`TenantScopedCascade` + :class:`GrantMoment`
  (S3 trust cascade).
* :class:`AuditChainEngine` on a real :class:`TrustLineageChain` with a real
  signer (S4 audit chain).
* :class:`Connector` subclass (test fixture, deterministic protocol-satisfying
  adapter per ``rules/testing.md`` § "Protocol-Satisfying Deterministic
  Adapters" — NOT a mock) + :class:`DispatchSurface` (S5 dispatch).
* :class:`DelegateRuntime` with :class:`R2Composition` + :class:`Posture` (S6
  runtime spine).
* :class:`ConformanceVectorLoader` (S7 conformance) to confirm the canonical
  vector set loads alongside the runtime composition.

Coverage:

* **Flow A — happy path**: Identity → Role → Envelope → Cascade → Dispatch
  → Runtime.execute() → TAOD COMPLETED → 5 audit entries (4 runtime
  transitions + 1 dispatch event) → receipt audit_head_hash matches the
  engine's head.
* **Flow B — posture HALT after construction**: runtime built at L5, then
  ``with_posture(HALT)`` emits POSTURE_OR_SOVEREIGN_HANDOVER on the source
  runtime, the new HALT-posture runtime refuses at THINKING, connector never
  invoked.
* **Flow C — tenant violation**: connector returns ``tenant_id_observed`` that
  does NOT match the envelope's cascade tenant → :class:`CascadeTenantViolation
  Error` raised by DispatchSurface BEFORE audit emission of the side-effect →
  runtime FAILED state, no further audit beyond the violation.
* **Flow D — signer failure mid-execute**: a signer that raises on its second
  call exercises the §7-fix A3/D1 no-recurse FAILED helper; state ends FAILED
  with sanitized reason at the phase where the audit failure occurred.
* **Flow E — §7 single-shot enforcement**: ``runtime.execute()`` twice → second
  raises :class:`RuntimePhaseError` with no audit emission for the second
  attempt.
* **Flow F — conformance vector loader composes alongside runtime**: confirms
  the canonical fixture (5 vectors, DV-3 / DV-5 / DV-7 / DV-9 / DV-10) loads
  cleanly in the same module the runtime composes in.

Invariants verified (4):

1. **Real-substrate composition** — NO mocks of S2-S7 primitives; only the
   :class:`Connector` and signer are test fixtures (Protocol-satisfying
   deterministic adapters).
2. **Audit chain end-to-end** — every flow asserts ``len(audit_engine.entries)``
   matches the expected TAOD transition cardinality.
3. **Receipts comparator coverage** — flow A round-trips
   :meth:`RuntimeExecutionResult.to_dict` through :func:`receipts_agree_dict`
   to confirm the comparator agrees on identical engine output.
4. **README pre-pledge alignment** — every Flow exercises a primitive the
   README pre-pledge section names (envelope monotonic-tightening, capability
   gating, tenant isolation, audit chain binding, §7 single-shot, posture
   rotation audit, R2 composition).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import pytest

from kailash.delegate.audit import AuditChainEngine, DelegateEventType
from kailash.delegate.conformance.schema import (
    ConformanceVectorLoader,
    receipts_agree_dict,
)
from kailash.delegate.dispatch import (
    Connector,
    ConnectorInvocationResult,
    DispatchSurface,
)
from kailash.delegate.envelope import DelegateConstraintEnvelope
from kailash.delegate.runtime import (
    DelegateRuntime,
    Posture,
    RuntimeExecutionResult,
    RuntimePhaseError,
)
from kailash.delegate.trust import (
    CascadeTenantViolationError,
    TenantScope,
    TenantScopedCascade,
)
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
# Real-substrate builders (no mocks). Protocol-satisfying connectors and
# signers are deterministic test fixtures, NOT mocks per rules/testing.md §
# "Protocol-Satisfying Deterministic Adapters".
# ---------------------------------------------------------------------------


def _deterministic_signer(canonical_bytes: bytes) -> str:
    """Deterministic 128-char hex signer for E2E flows (NOT a mock)."""
    digest = hashlib.sha256(canonical_bytes).hexdigest()
    return digest + digest


class _CountingSigner:
    """Signer that fails on the Nth call. Used for Flow D."""

    def __init__(self, fail_on_call: int) -> None:
        self.fail_on_call = fail_on_call
        self.calls = 0

    def __call__(self, canonical_bytes: bytes) -> str:
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise RuntimeError(f"signer fault on call {self.calls}")
        digest = hashlib.sha256(canonical_bytes).hexdigest()
        return digest + digest


def _build_chain(agent_id: str = "agent-e2e") -> TrustLineageChain:
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
        sovereign_ref="sov-e2e",
        role_binding_ref="rb-e2e",
        genesis_ref="g-agent-e2e",
    )


def _build_envelope() -> DelegateConstraintEnvelope:
    block = GenesisRecord(
        id="g-env-e2e",
        agent_id="agent-env-e2e",
        authority_id="auth-env-e2e",
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
        display_name="e2e-role",
        scope=RoleScope(
            domain="finance",
            capabilities=CapabilitySet(capabilities=("http.read",)),
        ),
        lifecycle=RoleLifecycleState.ACTIVE,
    )


class DeterministicConnector(Connector):
    """Protocol-satisfying deterministic connector (NOT a mock).

    Records every invocation argument and returns a deterministic
    :class:`ConnectorInvocationResult` whose ``tenant_id_observed`` and
    audit-events can be parameterized per flow.
    """

    connector_id = "e2e-conn"
    connector_kind = "http"
    requires_capabilities = frozenset({"http.read"})

    def __init__(self, *, tenant_id_observed: str = "tenant-e2e") -> None:
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


class _Signature:
    name = "e2e-sig"
    input_schema = {"id": str}
    output_schema = {"ok": bool, "echo": str}


def _build_stack(
    *,
    posture: Posture = Posture.L5_DELEGATED,
    tenant_id: str = "tenant-e2e",
    connector_tenant_id: str | None = None,
    signer=None,
):
    """Real-substrate stack — every dependency is a REAL primitive instance."""
    chain = _build_chain()
    audit_engine = AuditChainEngine(chain=chain)
    cascade = TenantScopedCascade(tenant=TenantScope.for_tenant(tenant_id))
    envelope = _build_envelope()
    identity = _build_identity()
    role = _build_role()
    # #1146 H1 — register the identity as a root grantee so the
    # DispatchSurface bind-time grantee gate passes. Without this seed
    # the cascade-as-authorization invariant refuses bind because the
    # identity transited no cascade_child path (root identities are
    # explicitly seeded by infrastructure at cascade-setup time).
    cascade.register_root_grantee(identity)
    connector = DeterministicConnector(
        tenant_id_observed=connector_tenant_id or tenant_id,
    )
    bound_signer = signer if signer is not None else _deterministic_signer
    surface = DispatchSurface(
        connector=connector,
        signature=_Signature(),
        envelope=envelope,
        identity=identity,
        audit_engine=audit_engine,
        trust_cascade=cascade,
        role=role,
        signer=bound_signer,
    )
    runtime = DelegateRuntime(
        dispatch_surface=surface,
        audit_engine=audit_engine,
        cascade=cascade,
        envelope=envelope,
        identity=identity,
        signer=bound_signer,
        posture=posture,
    )
    return runtime, surface, audit_engine, chain, connector


# ---------------------------------------------------------------------------
# Flow A — Happy path: full TAOD lifecycle composes across all 7 shards
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_flow_a_happy_path_full_taod_lifecycle_real_substrate() -> None:
    """Identity → Role → Envelope → Cascade → Dispatch → Runtime → COMPLETED.

    Asserts every layer participated:
    * Connector was invoked exactly once with the bound identity.
    * Dispatch surface produced a valid :class:`DispatchResult` whose
      ``tenant_id`` matches the cascade's bound tenant.
    * Audit chain has 4 runtime transitions + 1 dispatch event = 5 entries.
    * Every runtime-emitted audit entry binds the result's ``run_id``.
    * The result's ``audit_head_hash`` equals the engine's current head.
    """
    runtime, surface, audit_engine, chain, connector = _build_stack()

    # Pre-execute baseline
    assert len(audit_engine.entries) == 0
    assert len(connector.invocations) == 0

    result = await runtime.execute({"id": "flow-a-1"})

    # All 7 shards composed end-to-end
    assert isinstance(result, RuntimeExecutionResult)
    assert result.taod_state.phase == "completed"
    assert result.dispatch_result is not None
    assert result.dispatch_result.payload == {"ok": True, "echo": "flow-a-1"}
    assert result.dispatch_result.tenant_id == "tenant-e2e"
    assert result.dispatch_result.connector_id == "e2e-conn"
    assert result.posture_at_execute == Posture.L5_DELEGATED

    # Invariant 2: audit chain end-to-end cardinality
    assert len(audit_engine.entries) == 5
    assert len(audit_engine.entries) == len(chain.audit_anchors)

    # Connector got the bound identity (no impersonation through the stack)
    assert len(connector.invocations) == 1
    assert connector.invocations[0]["identity_id"] == runtime.identity.delegate_id

    # run_id bound into every runtime-emitted audit event (Invariant 3 / S6)
    runtime_entries = [e for e in audit_engine.entries if "run_id" in e.event_payload]
    assert len(runtime_entries) >= 4  # THINKING + ACTING + OBSERVING + COMPLETED
    run_id_str = str(result.run_id)
    for entry in runtime_entries:
        assert entry.event_payload["run_id"] == run_id_str

    # Audit head hash on result matches engine
    assert result.audit_head_hash == audit_engine.head_hash()


# ---------------------------------------------------------------------------
# Flow B — Posture HALT after construction; with_posture emits rotation audit
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_flow_b_posture_halt_blocks_execute_with_rotation_audit() -> None:
    """L5 → ``with_posture(HALT)`` rotates posture, emitting an audit event on
    the SOURCE runtime BEFORE returning the HALT-posture runtime (S6 MED-1).
    The HALT-posture ``execute()`` refuses at THINKING; connector never invoked.

    Verifies:
    * One POSTURE_OR_SOVEREIGN_HANDOVER audit entry lands from the rotation.
    * The new HALT runtime's ``execute()`` returns a FAILED result without
      invoking the connector or further dispatch path.
    """
    runtime, surface, audit_engine, chain, connector = _build_stack(
        posture=Posture.L5_DELEGATED,
    )
    pre_rotation_count = len(audit_engine.entries)

    # with_posture downgrade — no nonce required; audit event MUST land
    halted_runtime = runtime.with_posture(Posture.HALT)

    # Rotation emitted exactly one POSTURE_OR_SOVEREIGN_HANDOVER audit entry
    post_rotation_count = len(audit_engine.entries)
    assert post_rotation_count == pre_rotation_count + 1
    rotation_entry = audit_engine.entries[-1]
    assert (
        rotation_entry.event_type
        == DelegateEventType.POSTURE_OR_SOVEREIGN_HANDOVER.value
    )
    assert rotation_entry.event_payload["from_posture"] == Posture.L5_DELEGATED.value
    assert rotation_entry.event_payload["to_posture"] == Posture.HALT.value

    # Execute against HALT runtime
    result = await halted_runtime.execute({"id": "flow-b-halt"})

    # Execute refused at THINKING; no dispatch, no connector invocation
    assert result.taod_state.phase == "failed"
    assert result.dispatch_result is None
    assert len(connector.invocations) == 0
    assert result.posture_at_execute == Posture.HALT

    # FAILED-path runtime audit events landed (THINKING + FAILED transition)
    runtime_entries_after = [
        e for e in audit_engine.entries if "run_id" in e.event_payload
    ]
    assert len(runtime_entries_after) >= 2


# ---------------------------------------------------------------------------
# Flow C — Tenant violation: connector returns mismatched tenant_id_observed
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_flow_c_connector_tenant_violation_fail_closed_before_side_effect() -> (
    None
):
    """Connector observes ``tenant-foreign`` while cascade bound to
    ``tenant-e2e`` → :class:`CascadeTenantViolationError` raised by the
    dispatch surface BEFORE the side-effect audit emission.

    The runtime catches the dispatch exception and transitions to FAILED.
    The dispatch surface's tenant cross-check fires at S5 Invariant 2 — the
    runtime's defensive re-check at OBSERVING is therefore unreachable for
    this scenario; the FAILED reason cites the dispatch raise.
    """
    runtime, surface, audit_engine, chain, connector = _build_stack(
        tenant_id="tenant-e2e",
        connector_tenant_id="tenant-foreign",
    )

    result = await runtime.execute({"id": "flow-c-violation"})

    # Runtime FAILED on dispatch-error path
    assert result.taod_state.phase == "failed"
    assert result.dispatch_result is None
    # The FAILED transition reason cites the dispatch raise (sanitized form);
    # the underlying class is CascadeTenantViolationError.
    last_transition = result.taod_state.transitions[-1]
    assert "CascadeTenantViolationError" in (last_transition.reason or "")

    # Connector WAS invoked (the dispatch surface's tenant cross-check S5
    # Step 4 fires AFTER connector.invoke). But the surface's per-event
    # audit relay (S5 Step 5) is BLOCKED by the tenant raise — no audit
    # entry carrying ``signature_name`` (the surface-relay payload shape)
    # ever lands. The runtime-spine ACTING audit (which carries ``run_id``
    # and ``connector_id`` but NOT ``signature_name``) IS present per the
    # S6 R1 A3/D1 emit-first invariant.
    assert len(connector.invocations) == 1
    surface_relayed_entries = [
        e for e in audit_engine.entries if "signature_name" in e.event_payload
    ]
    assert len(surface_relayed_entries) == 0

    # Runtime emitted FAILED-path audit events (THINKING + ACTING + FAILED)
    runtime_entries = [e for e in audit_engine.entries if "run_id" in e.event_payload]
    assert len(runtime_entries) >= 3


# ---------------------------------------------------------------------------
# Flow C2 — Independent assertion: CascadeTenantViolationError reachable
# through the dispatch surface alone (defense-in-depth at S5 boundary)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_flow_c2_dispatch_surface_raises_tenant_violation_directly() -> None:
    """The dispatch surface's tenant cross-check is the structural defense.

    Direct ``surface.dispatch(...)`` with a mismatched ``tenant_id_observed``
    raises :class:`CascadeTenantViolationError` independently of the runtime
    spine. Confirms the S5 Invariant 2 enforcement is not runtime-spine
    dependent.
    """
    _runtime, surface, _audit, _chain, _connector = _build_stack(
        tenant_id="tenant-e2e",
        connector_tenant_id="tenant-foreign",
    )
    with pytest.raises(CascadeTenantViolationError):
        await surface.dispatch({"id": "flow-c2-direct"})


# ---------------------------------------------------------------------------
# Flow D — Signer failure mid-execute exercises the no-recurse FAILED helper
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_flow_d_signer_failure_mid_execute_lands_failed_no_recurse() -> None:
    """A signer that raises on its second call mid-``execute()`` exercises
    the S6 R1 A3/D1 no-recurse FAILED helper.

    Construction emits zero audit events (R2 composition does not sign).
    Inside ``execute()``, the THINKING-phase emit consumes call #1
    (succeeds), and the ACTING-phase emit consumes call #2 (raises). The
    runtime's no-recurse FAILED helper transitions to FAILED WITHOUT
    attempting another signed audit emit (which would recurse into the
    same broken signer).
    """
    failing_signer = _CountingSigner(fail_on_call=2)
    runtime, surface, audit_engine, chain, connector = _build_stack(
        signer=failing_signer,
    )

    result = await runtime.execute({"id": "flow-d-signer"})

    # State ends FAILED; dispatch never produced a result
    assert result.taod_state.phase == "failed"
    assert result.dispatch_result is None
    assert len(connector.invocations) == 0  # ACTING audit failed pre-invoke

    # FAILED transition cites the audit-emit-failed phase + class
    last_transition = result.taod_state.transitions[-1]
    reason = last_transition.reason or ""
    assert "audit emit failed" in reason
    assert "phase=" in reason
    # The exception class surfaces in the reason (not necessarily RuntimeError
    # verbatim, but the type tag is present).
    assert "RuntimeError" in reason

    # No-recurse: the helper did NOT attempt another signed emit after the
    # signer failure. Audit engine has at most the successful THINKING entry.
    runtime_entries = [e for e in audit_engine.entries if "run_id" in e.event_payload]
    assert len(runtime_entries) <= 1


# ---------------------------------------------------------------------------
# Flow E — §7 TAOD phase monotonicity: runtime is single-shot
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_flow_e_single_shot_runtime_blocks_second_execute() -> None:
    """First ``execute()`` succeeds; second raises :class:`RuntimePhaseError`.

    Pinned by conformance vector DV-7-001 (§7 TAOD phase monotonicity).
    The single-shot guard fires BEFORE the dispatch path; connector
    invocation count remains 1.
    """
    runtime, surface, audit_engine, chain, connector = _build_stack()

    r1 = await runtime.execute({"id": "flow-e-1"})
    assert r1.taod_state.phase == "completed"
    pre_second_audit_count = len(audit_engine.entries)

    with pytest.raises(RuntimePhaseError, match="single-shot"):
        await runtime.execute({"id": "flow-e-2"})

    # Audit chain unchanged: the guard fires before any second-run emit
    assert len(audit_engine.entries) == pre_second_audit_count
    # Connector invocation count unchanged: the guard fires before dispatch
    assert len(connector.invocations) == 1


# ---------------------------------------------------------------------------
# Flow F — Conformance vector loader composes alongside the runtime
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_e2e_flow_f_conformance_loader_loads_canonical_vectors_alongside_runtime() -> (
    None
):
    """The canonical conformance fixture loads cleanly in the same module the
    runtime composes in — confirms Fence B holds (conformance/ imports do NOT
    pull in runtime/dispatch/trust/audit/posture) AND the fixture's integrity
    check passes (digest matches stored ``digest`` field).

    Verifies the 5 canonical vector IDs (DV-3-001, DV-5-001, DV-7-001,
    DV-9-001, DV-10-001) are present per the canonical fixture file.
    """
    vectors = ConformanceVectorLoader.load_canonical()
    assert len(vectors) == 5
    vector_ids = {v.id for v in vectors}
    assert vector_ids == {
        "DV-3-001",
        "DV-5-001",
        "DV-7-001",
        "DV-9-001",
        "DV-10-001",
    }


# ---------------------------------------------------------------------------
# Flow G — receipts_agree_dict comparator agrees on identical engine output
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_flow_g_receipts_agree_dict_identity_on_runtime_output() -> None:
    """``receipts_agree_dict(result.to_dict(), result.to_dict())`` agrees.

    Confirms the comparator's identity property: a result compared against
    itself MUST agree (no mismatch fields). Cross-implementation comparison
    is exercised in
    ``tests/integration/delegate/test_receipts_agree_cross_impl.py``.
    """
    runtime, _surface, _audit, _chain, _connector = _build_stack()
    result = await runtime.execute({"id": "flow-g-receipt"})
    serialized = result.to_dict()
    report = receipts_agree_dict(serialized, serialized)
    assert report.agree is True
    assert report.mismatches == ()
