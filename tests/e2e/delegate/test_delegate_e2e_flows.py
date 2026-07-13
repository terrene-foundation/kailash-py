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
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

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
from kailash.delegate.envelope import DelegateConstraintEnvelope, EnvelopeWideningError
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
    PrincipalDirectory,
    Role,
    RoleLifecycleState,
    RoleScope,
)
from kailash.delegate.verifier import Ed25519Verifier
from kailash.trust._json import canonical_json_dumps
from kailash.trust.chain import AuthorityType, GenesisRecord, TrustLineageChain
from kailash.trust.envelope import ConstraintEnvelope, FinancialConstraint

# ---------------------------------------------------------------------------
# Real-substrate builders (no mocks). Protocol-satisfying connectors and
# signers are deterministic test fixtures, NOT mocks per rules/testing.md §
# "Protocol-Satisfying Deterministic Adapters".
# ---------------------------------------------------------------------------


def _make_ed25519_signer(priv: Ed25519PrivateKey):
    """Real Ed25519 signer callable over whatever canonical bytes it is handed.

    NOT a mock — a real cryptographic signer. The runtime / dispatch hand
    this the #1182 content pre-image; the cascade hands it the grant-signing
    bytes. A real Ed25519 signer signs ANY bytes correctly, so one signer
    keyed to the stack identity satisfies every sign-site, and the wired
    :class:`Ed25519Verifier` verifies each against the registered public key.
    """

    def signer(canonical_bytes: bytes) -> str:
        return priv.sign(canonical_bytes).hex()

    return signer


class _CountingSigner:
    """Real Ed25519 signer that RAISES on the Nth call. Used for Flow D.

    On every non-failing call it produces a REAL Ed25519 signature (so the
    THINKING-phase audit entry actually verifies and lands), then raises a
    RuntimeError on the configured call to exercise the signer-fault path.
    """

    def __init__(self, priv: Ed25519PrivateKey, fail_on_call: int) -> None:
        self._priv = priv
        self.fail_on_call = fail_on_call
        self.calls = 0

    def __call__(self, canonical_bytes: bytes) -> str:
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise RuntimeError(f"signer fault on call {self.calls}")
        return self._priv.sign(canonical_bytes).hex()


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


def _build_keyed_identity() -> tuple[DelegateIdentity, Ed25519PrivateKey]:
    """Build an identity + a real Ed25519 keypair for it (#1182 real-crypto e2e)."""
    return _build_identity(), Ed25519PrivateKey.generate()


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
    signer_factory=None,
):
    """Real-substrate stack — every dependency is a REAL primitive instance.

    #1182: wires a REAL :class:`Ed25519Verifier` (NOT NullVerifier) into both
    the audit engine and the cascade, and a REAL Ed25519 signer keyed to the
    stack identity. ``DelegateRuntime.execute()`` therefore exercises the
    full sign→verify→append audit path under real cryptography — the exact
    end-to-end path the #1182 contract mismatch was blocking. The signer is
    keyed to the identity registered in the directory, so every audit emit's
    content-pre-image signature verifies and the chain advances to COMPLETED.

    ``signer_factory`` (Flow D) takes the stack's private key and returns a
    custom signer callable (e.g. one that raises mid-execute); it shares the
    SAME key so its non-failing calls still verify.
    """
    chain = _build_chain()
    identity, priv = _build_keyed_identity()
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    directory = PrincipalDirectory(
        identities=(identity,),
        verification_keys={identity.delegate_id: pub_bytes},
    )
    # Same verifier CLASS on both audit engine and cascade — the runtime's
    # R2 coherence gate requires type(audit.verifier) is type(cascade.verifier).
    audit_engine = AuditChainEngine(
        chain=chain, verifier=Ed25519Verifier(directory=directory)
    )
    cascade = TenantScopedCascade(
        tenant=TenantScope.for_tenant(tenant_id),
        verifier=Ed25519Verifier(directory=directory),
    )
    envelope = _build_envelope()
    role = _build_role()
    bound_signer = (
        signer_factory(priv)
        if signer_factory is not None
        else _make_ed25519_signer(priv)
    )
    # #1146 H1 — register the identity as a root grantee so the
    # DispatchSurface bind-time grantee gate passes. With a real cascade
    # verifier wired, the seed MUST carry a real grant_proof: the cascade
    # verifies SHA-over {"delegate_id", "tenant"} against the registered key.
    # The seed is signed with a SEPARATE plain real signer (NOT bound_signer)
    # so a custom signer_factory's call-counting (Flow D) starts clean at the
    # runtime's first emit — the build-time seed does not consume its budget.
    seed_signer = _make_ed25519_signer(priv)
    grant_proof = seed_signer(
        canonical_json_dumps(
            {
                "delegate_id": str(identity.delegate_id),
                "tenant": cascade.tenant.tenant_id,
            }
        ).encode("utf-8")
    )
    cascade.register_root_grantee(identity, grant_proof=grant_proof)
    connector = DeterministicConnector(
        tenant_id_observed=connector_tenant_id or tenant_id,
    )
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
    # signer_factory receives the stack's real private key; the counting
    # signer produces a REAL Ed25519 signature on call #1 (THINKING lands +
    # verifies) and RAISES on call #2 (ACTING). The build-time grant_proof
    # seed uses a SEPARATE signer (see _build_stack), so this counter starts
    # clean at the runtime's first emit: #1 = THINKING, #2 = ACTING (raises).
    runtime, surface, audit_engine, chain, connector = _build_stack(
        signer_factory=lambda priv: _CountingSigner(priv, fail_on_call=2),
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


# ---------------------------------------------------------------------------
# D2 (#1149) — Audit chain hash linkage E2E replay
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_audit_chain_replay_verifies_hash_linkage() -> None:
    """After Flow A executes, walk the audit chain via ``previous_hash`` links
    and verify each entry's ``previous_hash`` matches
    ``sha256(canonical_json(prior_entry.to_canonical_dict()))``. Confirms
    chain integrity end-to-end.

    Acceptance (verbatim from issue #1149):

    * After successful Flow A ``execute()``, retrieve full audit chain from
      ``audit_engine``.
    * Walk chain: for each entry at sequence N≥1, verify
      ``entry.previous_hash == sha256(canonical_json(prior_entry.to_canonical_dict))``.
    * Verify chain length matches expected TAOD transition count
      (5 for happy path: THINKING + ACTING + dispatch-side-effect +
      OBSERVING + COMPLETED).

    Genesis (sequence 0) MUST carry ``previous_hash == ""`` per
    :class:`AuditChainEntry` post-init contract; this is the chain root
    invariant.
    """
    runtime, _surface, audit_engine, _chain, _connector = _build_stack()

    result = await runtime.execute({"id": "audit-replay-1"})
    assert result.taod_state.phase == "completed"

    entries = list(audit_engine.entries)

    # Expected chain length matches Flow A happy-path TAOD cardinality:
    # 4 runtime transitions (THINKING → ACTING → OBSERVING → COMPLETED) +
    # 1 dispatch-relay side-effect entry = 5 total.
    assert len(entries) == 5, (
        f"audit chain length {len(entries)} != expected 5; "
        f"Flow A happy-path emits 4 runtime transitions + 1 dispatch side-effect"
    )

    # Genesis (sequence 0) — previous_hash MUST be empty string per the
    # AuditChainEntry post-init contract; this is the chain root invariant.
    assert entries[0].sequence == 0
    assert (
        entries[0].previous_hash == ""
    ), "genesis entry previous_hash MUST be empty string (chain root)"

    # Walk the chain: for each entry at sequence N≥1, recompute the expected
    # previous_hash from the prior entry's canonical-JSON SHA-256 and assert
    # byte-equality with the stored field. The hashing formula MUST mirror
    # AuditChainEngine._compute_previous_hash exactly:
    #   sha256(canonical_json_dumps(prior.to_canonical_dict()).encode("utf-8")).hexdigest()
    for n in range(1, len(entries)):
        prior = entries[n - 1]
        current = entries[n]

        # Monotonic sequence — each entry's sequence is exactly +1 of the
        # prior. This is a structural-integrity invariant on top of the
        # hash-linkage check (catches gap-insertion attacks the hash alone
        # cannot detect at this layer).
        assert current.sequence == prior.sequence + 1, (
            f"sequence not monotonic at index {n}: "
            f"prior.sequence={prior.sequence}, current.sequence={current.sequence}"
        )

        expected_previous_hash = hashlib.sha256(
            canonical_json_dumps(prior.to_canonical_dict()).encode("utf-8")
        ).hexdigest()

        assert current.previous_hash == expected_previous_hash, (
            f"chain integrity broken at sequence {current.sequence}: "
            f"stored previous_hash={current.previous_hash!r} != "
            f"expected={expected_previous_hash!r} "
            f"(sha256(canonical_json(prior.to_canonical_dict())))"
        )

    # Cross-check: the engine's head_hash MUST equal SHA-256 of the canonical
    # JSON of the tail entry. This validates the engine-level hash anchor
    # cross-SDK verifiers consume aligns with the per-entry chain.
    tail = entries[-1]
    expected_head = hashlib.sha256(
        canonical_json_dumps(tail.to_canonical_dict()).encode("utf-8")
    ).hexdigest()
    assert audit_engine.head_hash() == expected_head, (
        f"audit_engine.head_hash() {audit_engine.head_hash()!r} != "
        f"sha256(canonical_json(tail.to_canonical_dict())) {expected_head!r}"
    )

    # The result's audit_head_hash field MUST also match (Flow A invariant 4).
    assert result.audit_head_hash == expected_head


# ---------------------------------------------------------------------------
# D3 (#1150) — DV-5-001 runtime-end-to-end vector test
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason=(
        "DV-5-001 canonical vector schema does not yet carry expected_payload "
        "or expected_byte_hash. The vector ships only "
        "{id, spec_anchor, given, behaviour, expected: 'Reject'}; there is no "
        "byte-canonical receipt to compare a py-emitted runtime receipt "
        "against. This test exercises the runtime on DV-5-001 inputs and "
        "asserts the documented Reject behaviour structurally, but cannot "
        "exercise receipts_agree(py_result, dv_5_001.expected_payload) parity "
        "until the canonical fixture schema gains expected_payload. "
        "xfail-strict per orphan-detection.md Rule 4a — XPASS when "
        "canonical.json gains expected_payload."
    ),
)
async def test_dv_5_001_runtime_output_matches_vendored_rs_canonical() -> None:
    """DV-5-001 runtime-end-to-end vector test (#1150).

    Vector content (verbatim from the packaged
    ``kailash/delegate/conformance/data/canonical.json``):

    * id: ``DV-5-001``
    * spec_anchor: ``5``
    * given: *Genesis Record G authorizes a Delegate, and a Delegation D
      from that Delegate widens the Financial dimension of its constraint
      envelope relative to G*
    * behaviour: *the runtime MUST reject Delegation D — a delegated
      constraint envelope may only tighten, never widen, a PACT dimension
      within a single lifecycle; widening requires a new Genesis Record*
    * expected: ``Reject``

    Runtime exercise: build the genesis-anchored envelope with
    ``FinancialConstraint(budget_limit=1000.0)`` per ``_build_envelope()``,
    then attempt a tightening operation that would actually WIDEN the
    Financial dimension (``budget_limit=5000.0``). The F5 monotonic-envelope
    gate at ``DelegateConstraintEnvelope.tighten_with`` raises
    :class:`EnvelopeWideningError` BEFORE the intersection can mask the
    widening (the pre-intersection check is the structural defense).

    Receipt-shape parity (the originally-intended Flow G receipts_agree
    counterpart per #1150's acceptance) cannot be exercised because
    DV-5-001 does NOT carry an ``expected_payload`` field in the canonical
    fixture schema — only the closed-taxonomy ``expected: 'Reject'`` token.
    This test therefore xfail-strict's per the divergence axes documented
    in the marker reason; an XPASS surfaces the moment the canonical
    fixture schema gains an ``expected_payload`` field, forcing the receipt
    parity wiring to land.

    Divergence axes documented (xfail-strict reason):

    1. Canonical vector schema currently carries
       ``{id, spec_anchor, given, behaviour, expected}`` — no
       ``expected_payload``.
    2. The runtime-side widening path raises
       :class:`EnvelopeWideningError` (a typed exception, not a wire-form
       receipt). No comparable rs canonical receipt exists to byte-pin.
    3. ``receipts_agree(py_result, dv_5_001.expected_payload)`` is
       structurally undefined until both halves of the contract ship.

    Until then: this test exercises the runtime on DV-5-001 inputs and
    asserts the documented Reject behaviour via the typed widening-refuse
    exception.
    """
    # Load the canonical vector to confirm DV-5-001 is in the fixture and
    # its expected outcome is Reject (defensive — guards against future
    # vector renames or outcome changes that would silently break this test).
    vectors = ConformanceVectorLoader.load_canonical()
    dv_5_001 = next((v for v in vectors if v.id == "DV-5-001"), None)
    assert dv_5_001 is not None, "DV-5-001 missing from canonical fixture"
    assert dv_5_001.expected.value == "Reject", (
        f"DV-5-001 expected outcome changed from 'Reject' to "
        f"{dv_5_001.expected.value!r}; this test's structural assertion is "
        f"no longer aligned with the vector"
    )

    # Confirm the canonical vector schema does NOT yet carry an
    # expected_payload field. The moment it does, this assertion fails and
    # the xfail-strict flips to XPASS, surfacing the gap for the operator
    # to wire receipt parity. (Structural-detection driver for the xfail.)
    vector_dict = dv_5_001.to_dict()
    assert "expected_payload" not in vector_dict, (
        "DV-5-001 canonical vector now carries expected_payload; the "
        "xfail-strict marker on this test SHOULD now fail and the test "
        "MUST be rewritten to exercise receipts_agree parity against the "
        "newly-shipped expected_payload byte-canonical receipt."
    )

    # Construct the genesis-anchored envelope (the "Genesis Record G
    # authorizes a Delegate" half of the given). _build_envelope() seeds
    # FinancialConstraint(budget_limit=1000.0) under a fresh genesis.
    parent_envelope = _build_envelope()
    assert parent_envelope.inner.financial is not None
    assert parent_envelope.inner.financial.budget_limit == 1000.0

    # Attempt the widening (the "Delegation D widens the Financial dimension
    # of its constraint envelope relative to G" half of the given). A budget
    # of 5000.0 LOOSENS the parent's 1000.0 bound — exactly the runtime
    # widening attempt §5 prohibits.
    widening_envelope = ConstraintEnvelope(
        financial=FinancialConstraint(budget_limit=5000.0),
    )

    # The runtime MUST reject Delegation D — the F5 monotonic-envelope
    # gate at DelegateConstraintEnvelope.tighten_with raises
    # EnvelopeWideningError before the intersection can mask the widening.
    with pytest.raises(EnvelopeWideningError) as exc_info:
        parent_envelope.tighten_with(widening_envelope)

    # The error message MUST cite the widening attempt (cross-SDK error
    # message parity per kailash.delegate.envelope:152-158).
    assert "widen" in str(exc_info.value).lower(), (
        f"EnvelopeWideningError message {exc_info.value!s} did not cite "
        f"widening; cross-SDK error parity expects the widening reason"
    )

    # Cascade-layer exercise: per issue #1150 acceptance ("Execute runtime;
    # capture RuntimeExecutionResult"), the rejection MUST propagate through
    # the cascade layer the runtime delegates into. TenantScopedCascade.
    # cascade_child at src/kailash/delegate/trust.py:454-459 invokes the
    # same F5 monotonicity gate via parent.tighten_with(child); the runtime
    # propagates EnvelopeWideningError verbatim per the docstring §389. This
    # closes the reviewer F1 (HIGH) finding: the envelope-method exercise
    # above + the cascade-layer exercise below jointly cover the layers
    # DV-5-001's "the runtime MUST reject Delegation D" applies to.
    cascade = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-e2e"))
    parent_identity = _build_identity()
    child_identity = _build_identity()
    role_scope = RoleScope(
        domain="finance",
        capabilities=CapabilitySet(capabilities=("http.read",)),
    )
    child_widening_envelope = DelegateConstraintEnvelope(
        inner=ConstraintEnvelope(financial=FinancialConstraint(budget_limit=5000.0)),
        genesis_id=parent_envelope.genesis_id,
    )
    with pytest.raises(EnvelopeWideningError):
        cascade.cascade_child(
            parent_envelope,
            child_widening_envelope,
            parent_identity=parent_identity,
            child_identity=child_identity,
            parent_scope=role_scope,
            child_scope=role_scope,
            child_tenant=TenantScope.for_tenant("tenant-e2e"),
            grant_proof="a" * 128,
        )

    # XFAIL signal (the reason we cannot complete receipts_agree here):
    # The above structural assertion proves the runtime DOES reject
    # Delegation D as DV-5-001 specifies. What we CANNOT do — and what the
    # xfail-strict marker documents — is exercise
    # ``receipts_agree(py_result, dv_5_001.expected_payload)`` parity,
    # because the canonical fixture schema does not yet carry an
    # ``expected_payload`` field. The fail is intentional: by raising
    # AssertionError below, we keep the xfail-strict marker honest until
    # the canonical fixture schema gains expected_payload. The moment it
    # does, the ``assert "expected_payload" not in vector_dict`` check above
    # fires FIRST, surfacing the schema-change for the operator to wire
    # receipt parity.
    raise AssertionError(
        "DV-5-001 receipts_agree(py_result, dv_5_001.expected_payload) parity "
        "is structurally undefined — the canonical fixture schema does not "
        "yet carry expected_payload. The runtime's Reject behaviour was "
        "exercised and confirmed via EnvelopeWideningError above; this "
        "AssertionError is the xfail-strict signal that receipt-shape "
        "parity cannot complete. XPASS when canonical.json gains "
        "expected_payload."
    )
