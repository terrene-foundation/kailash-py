# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 conformance vector integration test (S7, #1035).

Exercises the 5 canonical behavioural vectors from the packaged
``kailash/delegate/conformance/data/canonical.json`` against the REAL
kailash.delegate engines and asserts that each scenario produces the
spec-§-anchored :class:`BehaviouralOutcome` the vector declares.

Per ``rules/cross-sdk-inspection.md`` Rule 4 + 4a: this is the local-side
exercise that lets a kailash-py session produce a :class:`ConformanceReceipt`
sayng "I ran N vectors, M passed against vector-crate version V at
commit-sha S." A kailash-rs session running its equivalent canonical
suite produces a paired receipt; :func:`receipts_agree` proves cross-impl
agreement WITHOUT field-by-field engine diff (preserves the rs F1 fence).

Plus a :func:`receipts_agree_dict` end-to-end round-trip that proves the
dict-shape comparator works against actual ``RuntimeExecutionResult.to_dict()``
output -- the brief's runtime-byte-shape parity intent, scoped to public
OSS surfaces only.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import pytest

from kailash.delegate.audit import AuditChainEngine, DelegateEventType
from kailash.delegate.conformance import (
    BehaviouralOutcome,
    ConformanceReceipt,
    ConformanceVector,
    ConformanceVectorLoader,
    receipts_agree,
    receipts_agree_dict,
)
from kailash.delegate.dispatch import (
    Connector,
    ConnectorInvocationResult,
    DispatchSurface,
)
from kailash.delegate.envelope import DelegateConstraintEnvelope, EnvelopeWideningError
from kailash.delegate.runtime import (
    DelegateRuntime,
    Posture,
    RuntimeExecutionResult,
    RuntimePhaseError,
)
from kailash.delegate.trust import (
    CascadeScopeExpansionError,
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


def _test_signer(canonical_bytes: bytes) -> str:
    """Deterministic 128-char hex signer for integration tests."""
    h = hashlib.sha256(canonical_bytes).hexdigest()
    return h + h


# ---------------------------------------------------------------------------
# Real-substrate builders (no mocks; protocol-satisfying deterministic adapters)
# ---------------------------------------------------------------------------


def _build_identity() -> DelegateIdentity:
    return DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-conformance",
        role_binding_ref="rb-conformance",
        genesis_ref="g-agent-conformance",
    )


def _build_envelope(*, budget: float = 1000.0) -> DelegateConstraintEnvelope:
    block = GenesisRecord(
        id="g-conformance",
        agent_id="agent-conformance",
        authority_id="auth-conformance",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc),
        signature="d" * 128,
    )
    genesis = DelegateGenesisRecord(
        block=block, spec_version="1", capabilities=("read",)
    )
    return DelegateConstraintEnvelope.from_genesis(
        ConstraintEnvelope(financial=FinancialConstraint(budget_limit=budget)),
        genesis,
    )


def _build_role() -> Role:
    return Role(
        role_id=uuid.uuid4(),
        display_name="conformance-role",
        scope=RoleScope(
            domain="finance",
            capabilities=CapabilitySet(capabilities=("http.read",)),
        ),
        lifecycle=RoleLifecycleState.ACTIVE,
    )


def _build_chain(agent_id: str = "agent-conformance") -> TrustLineageChain:
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


class _PassthroughConnector(Connector):
    """Deterministic connector: echoes input."""

    connector_id = "conformance-connector"
    connector_kind = "http"
    requires_capabilities = frozenset({"http.read"})

    def __init__(self, *, tenant_id_observed: str = "tenant-conformance") -> None:
        self.tenant_id_observed = tenant_id_observed
        self.invocations: list[dict] = []

    async def invoke(self, input_payload, *, identity, envelope):
        self.invocations.append({"input": dict(input_payload)})
        return ConnectorInvocationResult(
            payload={"ok": True, "echo": input_payload.get("id", "n/a")},
            audit_events=(DelegateEventType.EXTERNAL_SIDE_EFFECT,),
            tenant_id_observed=self.tenant_id_observed,
            external_side_effect=True,
        )


class _ConformanceSig:
    """Minimal SignatureContract satisfier for conformance tests."""

    name = "conformance-sig"
    input_schema = {"id": str}
    output_schema = {"ok": bool, "echo": str}


def _build_runtime(
    *,
    posture: Posture = Posture.L5_DELEGATED,
    tenant_id: str = "tenant-conformance",
    envelope: DelegateConstraintEnvelope | None = None,
) -> tuple[
    DelegateRuntime,
    DispatchSurface,
    AuditChainEngine,
    TrustLineageChain,
    _PassthroughConnector,
]:
    chain = _build_chain()
    audit_engine = AuditChainEngine(chain=chain)
    cascade = TenantScopedCascade(tenant=TenantScope.for_tenant(tenant_id))
    env = envelope or _build_envelope()
    identity = _build_identity()
    role = _build_role()
    # #1146 H1 — seed the cascade with the root grantee.
    cascade.register_root_grantee(identity)
    connector = _PassthroughConnector(tenant_id_observed=tenant_id)
    surface = DispatchSurface(
        connector=connector,
        signature=_ConformanceSig(),
        envelope=env,
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
        envelope=env,
        identity=identity,
        signer=_test_signer,
        posture=posture,
    )
    return runtime, surface, audit_engine, chain, connector


# ---------------------------------------------------------------------------
# Per-vector behaviour exercises
#
# Each function takes the local-system substrate and executes the scenario
# the vector describes. Returns True iff the runtime exhibited the vector's
# `expected` BehaviouralOutcome.
# ---------------------------------------------------------------------------


def _exercise_dv_3_001_r2_composition_rejects_cascade_widening() -> bool:
    """DV-3-001 — R2 composition rejects a cascade that widens envelope.

    REJECT iff: an envelope.tighten() with a widened inner constraint raises
    EnvelopeWideningError. The R2 composition gate (envelope, cascade,
    dispatch_surface) fails on the envelope-monotonic-tightening half;
    surfacing the rejection at the tighten() callsite is the structural
    primitive the cascade composition relies on.
    """
    base_env = _build_envelope(budget=500.0)
    # The widening attempt: a downstream cascade grant proposes widening
    # the Financial dimension. R2 composition surfaces this as an
    # envelope-tighten rejection on the widened inner constraint.
    widened_inner = ConstraintEnvelope(
        financial=FinancialConstraint(budget_limit=999_999.0)
    )
    try:
        base_env.tighten_with(widened_inner)
        # If tighten_with() did not raise, the runtime did not exhibit REJECT.
        return False
    except (EnvelopeWideningError, CascadeScopeExpansionError, ValueError):
        return True


def _exercise_dv_5_001_envelope_widening_rejected() -> bool:
    """DV-5-001 — monotonic-tightening rejects a widening Delegation.

    REJECT iff: an envelope.tighten() with a widened inner constraint raises
    EnvelopeWideningError.
    """
    env = _build_envelope(budget=500.0)
    widened = ConstraintEnvelope(
        financial=FinancialConstraint(budget_limit=10_000.0)  # WIDER
    )
    try:
        env.tighten_with(widened)
        return False
    except EnvelopeWideningError:
        return True


@pytest.mark.asyncio
async def _exercise_dv_7_001_taod_post_completion_rejection() -> bool:
    """DV-7-001 — TAOD phase monotonicity rejects re-execute after COMPLETED.

    REJECT iff: a second execute() on a terminal runtime raises
    RuntimePhaseError.
    """
    runtime, _, _, _, _ = _build_runtime()
    # First execute: happy path to COMPLETED.
    result = await runtime.execute({"id": "first"})
    assert result.taod_state.phase == "completed"
    # Second execute: MUST raise.
    try:
        await runtime.execute({"id": "second"})
        return False
    except RuntimePhaseError:
        return True


@pytest.mark.asyncio
async def _exercise_dv_9_001_audit_chain_replay_round_trip() -> bool:
    """DV-9-001 — audit chain canonical serialization is deterministic.

    ACCEPT iff: every audit entry's to_canonical_dict() is JSON-stable
    (byte-equal across two serializations), AND the result's
    audit_head_hash matches the engine's current head_hash() (signature-
    verified head reproduction).
    """
    import json as _json

    runtime, _, audit_engine, _chain, _ = _build_runtime()
    result = await runtime.execute({"id": "audit-replay"})
    if result.taod_state.phase != "completed":
        return False
    # Determinism: each entry's canonical_dict serializes byte-equal twice.
    for entry in audit_engine.entries:
        a = _json.dumps(entry.to_canonical_dict(), sort_keys=True, default=str)
        b = _json.dumps(entry.to_canonical_dict(), sort_keys=True, default=str)
        if a != b:
            return False
    # Head hash matches the engine's tracked head.
    if result.audit_head_hash != audit_engine.head_hash():
        return False
    return True


def _exercise_dv_10_001_g1_service_account_separation() -> bool:
    """DV-10-001 -- #1143 §10 G1: principal-kind discriminator enforces
    service-account vs sovereign separation at the dispatch bind gate.

    REJECT iff: constructing a :class:`DispatchSurface` with a
    ``service_account``-kind identity bound to a role whose
    ``permitted_principal_kinds`` is ``frozenset({"sovereign"})`` raises
    :class:`DispatchEnvelopeViolationError` at __init__.

    The §10 G1 invariant: a Delegate acts through a scoped service-account
    principal distinct from the sovereign principal the Delegate acts
    for. A Connector binding where these collapse impersonates the
    sovereign and breaks the Genesis-to-Delegation attribution chain.
    The :class:`Role.permitted_principal_kinds` field expresses which
    kinds may bind; the dispatch gate refuses any mismatch.
    """
    from kailash.delegate.dispatch import DispatchEnvelopeViolationError

    # Build a sovereign-only role -- the role permits the SOVEREIGN
    # principal-kind to bind, but NOT the service_account kind.
    sovereign_only_role = Role(
        role_id=uuid.uuid4(),
        display_name="sovereign-only-conformance-role",
        scope=RoleScope(
            domain="finance",
            capabilities=CapabilitySet(capabilities=("http.read",)),
        ),
        lifecycle=RoleLifecycleState.ACTIVE,
        permitted_principal_kinds=frozenset({"sovereign"}),
    )
    # Construct a service-account-kind identity -- the impersonation
    # collapse the §10 G1 invariant blocks.
    service_account_identity = DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-conformance",
        role_binding_ref="rb-conformance",
        genesis_ref="g-agent-conformance",
        principal_kind="service_account",
    )
    # Substrate dependencies for the bind attempt.
    chain = _build_chain()
    audit_engine = AuditChainEngine(chain=chain)
    cascade = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-A"))
    env = _build_envelope()
    connector = _PassthroughConnector(tenant_id_observed="tenant-A")
    try:
        DispatchSurface(
            connector=connector,
            signature=_ConformanceSig(),
            envelope=env,
            identity=service_account_identity,
            audit_engine=audit_engine,
            trust_cascade=cascade,
            role=sovereign_only_role,
            signer=_test_signer,
        )
    except DispatchEnvelopeViolationError:
        return True
    # Bind succeeded -- the §10 G1 gate did not fire.
    return False


# Map vector_id -> async exerciser. Sync exercisers wrap to async for uniform dispatch.
async def _run_vector(vector: ConformanceVector) -> bool:
    if vector.id == "DV-3-001":
        return _exercise_dv_3_001_r2_composition_rejects_cascade_widening()
    if vector.id == "DV-5-001":
        return _exercise_dv_5_001_envelope_widening_rejected()
    if vector.id == "DV-7-001":
        return await _exercise_dv_7_001_taod_post_completion_rejection()
    if vector.id == "DV-9-001":
        return await _exercise_dv_9_001_audit_chain_replay_round_trip()
    if vector.id == "DV-10-001":
        return _exercise_dv_10_001_g1_service_account_separation()
    raise ValueError(f"no exerciser registered for vector {vector.id!r}")


# ---------------------------------------------------------------------------
# Per-vector tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dv_3_001_r2_composition_behaviour() -> None:
    vectors = ConformanceVectorLoader.load_canonical()
    target = next(v for v in vectors if v.id == "DV-3-001")
    assert target.expected is BehaviouralOutcome.REJECT
    exhibited_reject = await _run_vector(target)
    assert exhibited_reject is True, (
        "DV-3-001 expected REJECT (per §3 R2 composition); runtime did not "
        "exhibit rejection of widening cascade"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dv_5_001_monotonic_tightening_behaviour() -> None:
    vectors = ConformanceVectorLoader.load_canonical()
    target = next(v for v in vectors if v.id == "DV-5-001")
    assert target.expected is BehaviouralOutcome.REJECT
    exhibited_reject = await _run_vector(target)
    assert exhibited_reject is True, (
        "DV-5-001 expected REJECT (per §5 monotonic-tightening); envelope "
        "did not raise EnvelopeWideningError"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dv_7_001_taod_phase_monotonicity_behaviour() -> None:
    """DV-7-001 — §7 TAOD phase monotonicity enforced at runtime level.

    The DelegateRuntime is single-shot per receipt: a second execute()
    on a runtime in any terminal phase (COMPLETED or FAILED) raises
    RuntimePhaseError. Previously xfail-strict pending the runtime fix;
    now PASSES per the §7 single-shot guard. Mirrors unit-level coverage
    in `tests/unit/delegate/test_runtime.py::
    test_runtime_re_execute_after_completed_raises_phase_error`.
    """
    vectors = ConformanceVectorLoader.load_canonical()
    target = next(v for v in vectors if v.id == "DV-7-001")
    assert target.expected is BehaviouralOutcome.REJECT
    exhibited_reject = await _run_vector(target)
    assert exhibited_reject is True, (
        "DV-7-001 expected REJECT (per §7 TAOD phase monotonicity); "
        "runtime did not raise RuntimePhaseError on re-execute"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dv_9_001_audit_chain_replay_behaviour() -> None:
    vectors = ConformanceVectorLoader.load_canonical()
    target = next(v for v in vectors if v.id == "DV-9-001")
    assert target.expected is BehaviouralOutcome.ACCEPT
    accepted = await _run_vector(target)
    assert accepted is True, (
        "DV-9-001 expected ACCEPT (per §9 audit chain replay); audit "
        "entries did not round-trip byte-identically OR head hash mismatched"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dv_10_001_g1_service_account_separation_behaviour() -> None:
    """DV-10-001 -- #1143 §10 G1 principal-kind discriminator.

    The DispatchSurface bind gate cross-validates ``identity.principal_kind``
    against ``role.permitted_principal_kinds`` and raises
    :class:`DispatchEnvelopeViolationError` on mismatch. Previously
    xfail-strict pending the dispatch fix; now PASSES per the §10 G1
    discriminator landing. Mirrors unit-level coverage in
    ``tests/unit/delegate/test_dispatch.py::
    test_dispatch_surface_refuses_principal_kind_mismatch``.
    """
    vectors = ConformanceVectorLoader.load_canonical()
    target = next(v for v in vectors if v.id == "DV-10-001")
    assert target.expected is BehaviouralOutcome.REJECT
    rejected = await _run_vector(target)
    assert rejected is True, (
        "DV-10-001 expected REJECT (per §10 G1 service-account separation); "
        "runtime did not raise on sovereign-principal collapse"
    )


# ---------------------------------------------------------------------------
# Conformance receipt + cross-impl agreement end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_canonical_set_produces_receipt() -> None:
    """Run every canonical vector against the local-py substrate; build the
    ConformanceReceipt reflecting which vectors currently conform.

    The receipt is the cross-impl byte-shape contract: it carries the
    pinned (vector_crate_version, commit_sha) + the count of vectors that
    exhibited their expected BehaviouralOutcome on this implementation.
    A future runtime that closes the §7 + §10 enforcement gaps will flip
    ``vectors_passed`` to ``vectors_total`` and ``.conforms()`` to True
    WITHOUT a schema or fixture change — exactly the F4 contract.
    """
    vectors = ConformanceVectorLoader.load_canonical()
    total = len(vectors)
    passed = 0
    for vector in vectors:
        try:
            exhibited = await _run_vector(vector)
        except Exception:
            # A non-rejection raise (e.g. xfail-class behavioral gap) still
            # records as not-passed; the receipt reflects current truth.
            exhibited = False
        if exhibited:
            passed += 1
    receipt = ConformanceReceipt(
        implementation="kailash-py",
        vector_crate_version="0.1.0",
        commit_sha="local-dev",
        vectors_total=total,
        vectors_passed=passed,
    )
    assert receipt.vectors_total == 5
    # All 5 vectors now pass (DV-3, DV-5, DV-7, DV-9, DV-10). DV-10
    # graduated from xfail when #1143 landed the principal-kind
    # discriminator gate on DispatchSurface.__init__. DV-7 graduated
    # earlier when the runtime §7 single-shot guard landed.
    assert receipt.vectors_passed == 5
    assert receipt.conforms() is True  # 5 of 5 -- conforming
    # Both validation predicates hold:
    assert receipt.vectors_passed <= receipt.vectors_total


@pytest.mark.integration
def test_receipts_agree_proves_cross_impl_agreement_without_engine_diff() -> None:
    """Two receipts naming the SAME (vector_crate_version, commit_sha) from
    DISTINCT impls, both conforming, MUST agree per the F4 protocol -- and
    this happens WITHOUT either side exposing engine internals to the other.
    """
    py_receipt = ConformanceReceipt(
        implementation="kailash-py",
        vector_crate_version="0.1.0",
        commit_sha="abc123def456",
        vectors_total=5,
        vectors_passed=5,
    )
    rs_receipt = ConformanceReceipt(
        implementation="kailash-rs",
        vector_crate_version="0.1.0",
        commit_sha="abc123def456",
        vectors_total=5,
        vectors_passed=5,
    )
    assert receipts_agree(py_receipt, rs_receipt) is True
    # And the symmetric form.
    assert receipts_agree(rs_receipt, py_receipt) is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_receipts_agree_dict_against_actual_runtime_execution_result() -> None:
    """End-to-end: two RuntimeExecutionResult.to_dict() outputs from the
    SAME inputs against the SAME substrate compare as agreeing under
    :func:`receipts_agree_dict` (timestamps excluded by default).

    This is the runtime-byte-shape parity check the brief proposed,
    Fence-B-respected: the comparator operates on dicts produced by the
    public :meth:`RuntimeExecutionResult.to_dict` method; engine classes
    never cross the conformance/ boundary.
    """
    # Build two parallel runtime stacks with identical inputs -- run both,
    # serialize via the public .to_dict() surface, compare via receipts_agree_dict.
    runtime_a, _, _, _, _ = _build_runtime()
    runtime_b, _, _, _, _ = _build_runtime()
    result_a = await runtime_a.execute({"id": "parity-1"})
    result_b = await runtime_b.execute({"id": "parity-1"})

    dict_a = result_a.to_dict()
    dict_b = result_b.to_dict()

    # Two parallel runs have different run_ids by design; the structural
    # check excludes run_id-dependent fields where they're observation-local.
    # The non-observation-local fields (taod transitions phases, dispatch
    # payload, posture, audit_chain shape) MUST agree.
    report = receipts_agree_dict(
        dict_a,
        dict_b,
        # Two parallel runs differ on observation-local identifiers:
        # - run_id, dispatch_id: per-run UUIDs
        # - audit_head_hash, audit_chain_entries: each run anchors a distinct chain
        # - at: per-transition wall-clock timestamp (TAODTransition.at)
        # Exclude these as observation-local for the SAME-impl parity test;
        # the cross-impl receipts_agree() (counts-based) is the canonical gate.
        exclude_fields=frozenset(
            {
                "run_id",
                "dispatch_id",
                "audit_head_hash",
                "audit_chain_entries",
                "at",
            }
        ),
    )
    # The shape (phases, posture, dispatch payload, transitions[].phase)
    # MUST agree even when run_ids + audit chains differ.
    if not report.agree:
        # Surface the divergence for diagnosis if the test ever flips.
        msg = (
            f"receipts_agree_dict failed on parallel SAME-impl runs:\n"
            f"  mismatches: {report.mismatches}\n"
            f"  details: {report.mismatch_details}"
        )
        # The agree=True path is the contract; reach here only if the runtime
        # is non-deterministic in a way the comparator surfaces.
        assert report.agree is True, msg


@pytest.mark.integration
@pytest.mark.asyncio
async def test_receipts_agree_dict_flags_divergent_runtime_results() -> None:
    """Two RuntimeExecutionResult.to_dict() outputs from DIFFERENT input
    payloads MUST surface as divergent under :func:`receipts_agree_dict`."""
    runtime_a, _, _, _, _ = _build_runtime()
    runtime_b, _, _, _, _ = _build_runtime()
    result_a = await runtime_a.execute({"id": "input-A"})
    result_b = await runtime_b.execute({"id": "input-B"})

    report = receipts_agree_dict(
        result_a.to_dict(),
        result_b.to_dict(),
        exclude_fields=frozenset({"run_id", "audit_head_hash", "audit_chain_entries"}),
    )
    # dispatch_result.payload.echo differs between input-A and input-B.
    assert report.agree is False
    assert any("dispatch_result.payload" in m for m in report.mismatches)
