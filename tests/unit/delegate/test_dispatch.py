# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for ``kailash.delegate.dispatch`` (S5, #1035).

Covers the Connector ABC + DispatchSurface bind + dispatch surface.
Per ``probe-driven-verification.md`` MUST Rule 3, all assertions here
are STRUCTURAL (typed-error class raised, frozen-dataclass shape,
isinstance type checks, audit-engine state-count) — no semantic
regex / keyword matching against prose output. The bug class this
shard exists to prevent (silent capability bypass, silent tenant
crossing, silent audit-event drop) is structurally observable at the
type / exception / counter level.

Tier classification: substrate dependencies (TenantScopedCascade,
AuditChainEngine, DelegateConstraintEnvelope) are REAL — no mocks.
The only "fake" object is the MockConnector subclass that satisfies
the Connector ABC contract deterministically; per
``rules/testing.md`` § "Protocol-Satisfying Deterministic Adapters",
this is NOT a mock — it's a deterministic adapter for the abstract
Connector surface.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from typing import Any

import pytest

from kailash.delegate.audit import (
    AuditChainEmissionError,
    AuditChainEngine,
    DelegateEventType,
)
from kailash.delegate.dispatch import (
    Connector,
    ConnectorInvocationResult,
    DispatchCascadeViolationError,
    DispatchEnvelopeViolationError,
    DispatchResult,
    DispatchSignerError,
    DispatchSurface,
    DispatchValidationError,
    SignatureContract,
)
from kailash.delegate.envelope import DelegateConstraintEnvelope
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
# Deterministic test signer — produces a 128-char lowercase hex string from
# the canonical-bytes input. SHA-256 doubled to 128 chars satisfies the
# audit-engine's _validate_hex(expected_len=128) contract.
# ---------------------------------------------------------------------------


def _test_signer(canonical_bytes: bytes) -> str:
    h = hashlib.sha256(canonical_bytes).hexdigest()
    return h + h  # 128-char lowercase hex


# ---------------------------------------------------------------------------
# Fixture helpers — keep tests focused on behavior under test
# ---------------------------------------------------------------------------


def _build_chain(agent_id: str = "agent-s5") -> TrustLineageChain:
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


def _build_identity(*, principal_kind: str = "delegate") -> DelegateIdentity:
    return DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-s5",
        role_binding_ref="rb-s5",
        genesis_ref="g-agent-s5",
        principal_kind=principal_kind,  # type: ignore[arg-type]
    )


def _build_envelope() -> DelegateConstraintEnvelope:
    block = GenesisRecord(
        id="g-env-s5",
        agent_id="agent-env",
        authority_id="auth-env",
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


def _build_role(
    *,
    lifecycle: RoleLifecycleState = RoleLifecycleState.ACTIVE,
    capabilities: tuple[str, ...] = ("http.read", "http.write"),
    permitted_principal_kinds: frozenset[str] | None = None,
) -> Role:
    kwargs: dict[str, object] = {
        "role_id": uuid.uuid4(),
        "display_name": "test-role",
        "scope": RoleScope(
            domain="finance",
            capabilities=CapabilitySet(capabilities=capabilities),
        ),
        "lifecycle": lifecycle,
    }
    if permitted_principal_kinds is not None:
        kwargs["permitted_principal_kinds"] = permitted_principal_kinds
    return Role(**kwargs)  # type: ignore[arg-type]


def _build_cascade(*, tenant_id: str | None = "tenant-a") -> TenantScopedCascade:
    if tenant_id is None:
        return TenantScopedCascade(tenant=TenantScope.global_())
    return TenantScopedCascade(tenant=TenantScope.for_tenant(tenant_id))


# ---------------------------------------------------------------------------
# A minimal SignatureContract-satisfying object
# ---------------------------------------------------------------------------


class FakeSignatureHelper:
    """Deterministic SignatureContract-satisfier for tests.

    Named *Helper not *Test per ``testing.md`` MUST: Helper Classes Use
    Stub/Helper/Fake Suffix — pytest's ``Test*`` collection silently
    drops ``__init__``-bearing helper classes.
    """

    def __init__(
        self,
        *,
        name: str = "create_user",
        input_schema: dict[str, type] | None = None,
        output_schema: dict[str, type] | None = None,
    ) -> None:
        self.name = name
        self.input_schema = (
            input_schema if input_schema is not None else {"user_id": str}
        )
        self.output_schema = (
            output_schema if output_schema is not None else {"created": bool}
        )


# ---------------------------------------------------------------------------
# A minimal Connector-satisfying subclass that records all received args
# ---------------------------------------------------------------------------


class MockConnector(Connector):
    """Deterministic Connector subclass for unit tests.

    Per ``rules/testing.md`` § "Protocol-Satisfying Deterministic
    Adapters", this is NOT a mock — it's a real Connector subclass
    satisfying the abstract ``invoke`` contract deterministically.
    Records all arguments passed to invoke() so tests can assert wiring.
    """

    connector_id = "mock-conn-1"
    connector_kind = "http"
    requires_capabilities = frozenset({"http.read"})

    def __init__(
        self,
        *,
        return_payload: dict | None = None,
        tenant_id_observed: str | None = "tenant-a",
        audit_events: tuple[DelegateEventType, ...] = (
            DelegateEventType.EXTERNAL_SIDE_EFFECT,
        ),
        external_side_effect: bool = True,
    ) -> None:
        self.return_payload = (
            return_payload if return_payload is not None else {"created": True}
        )
        self.tenant_id_observed = tenant_id_observed
        self.audit_events = audit_events
        self.external_side_effect = external_side_effect
        self.invocations: list[dict] = []

    async def invoke(
        self,
        input_payload,
        *,
        identity,
        envelope,
    ):
        self.invocations.append(
            {
                "input_payload": input_payload,
                "identity": identity,
                "envelope": envelope,
            }
        )
        return ConnectorInvocationResult(
            payload=self.return_payload,
            audit_events=self.audit_events,
            tenant_id_observed=self.tenant_id_observed,
            external_side_effect=self.external_side_effect,
        )


# ---------------------------------------------------------------------------
# Connector ABC — instantiation refusal + metadata validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_connector_abc_refuses_direct_instantiation() -> None:
    """Connector is abc.ABC + @abstractmethod invoke — direct construct refused."""
    with pytest.raises(TypeError, match="abstract"):
        Connector()  # type: ignore[abstract]


@pytest.mark.unit
def test_connector_subclass_missing_connector_id_rejected() -> None:
    """Concrete subclass MUST declare non-empty connector_id at class level."""
    with pytest.raises(TypeError, match="connector_id"):

        class BadConnector(Connector):
            # connector_id intentionally not overridden (empty default)
            connector_kind = "http"

            async def invoke(self, input_payload, *, identity, envelope):
                pass  # pragma: no cover


@pytest.mark.unit
def test_connector_subclass_missing_connector_kind_rejected() -> None:
    """Concrete subclass MUST declare non-empty connector_kind at class level."""
    with pytest.raises(TypeError, match="connector_kind"):

        class BadConnector(Connector):
            connector_id = "x"
            # connector_kind intentionally not overridden

            async def invoke(self, input_payload, *, identity, envelope):
                pass  # pragma: no cover


@pytest.mark.unit
def test_connector_subclass_capabilities_must_be_frozenset() -> None:
    """requires_capabilities MUST be a frozenset, not a list / set."""
    with pytest.raises(TypeError, match="frozenset"):

        class BadConnector(Connector):
            connector_id = "x"
            connector_kind = "http"
            requires_capabilities = ["http.read"]  # type: ignore[assignment]

            async def invoke(self, input_payload, *, identity, envelope):
                pass  # pragma: no cover


# ---------------------------------------------------------------------------
# ConnectorInvocationResult — frozen + structural validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_connector_invocation_result_is_frozen() -> None:
    r = ConnectorInvocationResult(
        payload={"x": 1},
        audit_events=(DelegateEventType.EXTERNAL_SIDE_EFFECT,),
        tenant_id_observed="tenant-a",
        external_side_effect=True,
    )
    with pytest.raises(FrozenInstanceError):
        r.payload = {}  # type: ignore[misc]


@pytest.mark.unit
def test_connector_invocation_result_rejects_non_dict_payload() -> None:
    with pytest.raises(TypeError, match="payload MUST be a dict"):
        ConnectorInvocationResult(
            payload="not a dict",  # type: ignore[arg-type]
            audit_events=(),
            tenant_id_observed=None,
            external_side_effect=False,
        )


@pytest.mark.unit
def test_connector_invocation_result_rejects_non_event_tuple() -> None:
    with pytest.raises(TypeError, match="DelegateEventType"):
        ConnectorInvocationResult(
            payload={},
            audit_events=("not-an-event",),  # type: ignore[arg-type]
            tenant_id_observed=None,
            external_side_effect=False,
        )


# ---------------------------------------------------------------------------
# DispatchSurface — bind-time invariants (3 + 5)
# ---------------------------------------------------------------------------


def _make_surface(
    *,
    role: Role | None = None,
    cascade: TenantScopedCascade | None = None,
    connector: Connector | None = None,
    signature: SignatureContract | None = None,
    envelope: DelegateConstraintEnvelope | None = None,
    identity: DelegateIdentity | None = None,
    signer=None,
    skip_grantee_registration: bool = False,
) -> DispatchSurface:
    bound_cascade = cascade if cascade is not None else _build_cascade()
    bound_identity = identity if identity is not None else _build_identity()
    # #1146 H1 — register the identity as a root grantee BEFORE
    # DispatchSurface construction so the bind-time grantee check passes.
    # Tests that want to exercise the H1 refusal path pass
    # skip_grantee_registration=True.
    if not skip_grantee_registration:
        bound_cascade.register_root_grantee(bound_identity)
    return DispatchSurface(
        connector=connector if connector is not None else MockConnector(),
        signature=signature if signature is not None else FakeSignatureHelper(),
        envelope=envelope if envelope is not None else _build_envelope(),
        identity=bound_identity,
        audit_engine=AuditChainEngine(chain=_build_chain()),
        trust_cascade=bound_cascade,
        role=role if role is not None else _build_role(),
        signer=signer if signer is not None else _test_signer,
    )


@pytest.mark.unit
def test_dispatch_surface_binds_when_invariants_hold() -> None:
    surface = _make_surface()
    assert surface.connector.connector_id == "mock-conn-1"
    assert surface.role.lifecycle == RoleLifecycleState.ACTIVE


@pytest.mark.unit
def test_dispatch_surface_refuses_retired_role_lifecycle() -> None:
    """Invariant 5 — RETIRED lifecycle refuses bind."""
    role = _build_role(lifecycle=RoleLifecycleState.RETIRED)
    with pytest.raises(DispatchEnvelopeViolationError, match="lifecycle"):
        _make_surface(role=role)


@pytest.mark.unit
def test_dispatch_surface_refuses_suspended_role_lifecycle() -> None:
    """Invariant 5 — SUSPENDED lifecycle refuses bind."""
    role = _build_role(lifecycle=RoleLifecycleState.SUSPENDED)
    with pytest.raises(DispatchEnvelopeViolationError, match="lifecycle"):
        _make_surface(role=role)


@pytest.mark.unit
def test_dispatch_surface_allows_draft_role_lifecycle() -> None:
    """Invariant 5 — DRAFT lifecycle binds (test/pre-activation use)."""
    role = _build_role(lifecycle=RoleLifecycleState.DRAFT)
    surface = _make_surface(role=role)
    assert surface.role.lifecycle == RoleLifecycleState.DRAFT


@pytest.mark.unit
def test_dispatch_surface_refuses_missing_capability() -> None:
    """Invariant 3 — connector requires capability role does not grant.

    C5-2 error-leakage fix: caller-facing message hashes the capability
    names; full detail is structured-logged at DEBUG. Test matches on
    the stable structural prefix ("refuses bind", "missing_hash=") and
    NOT on the schema-revealing capability strings.
    """
    role = _build_role(capabilities=("other.cap",))
    with pytest.raises(
        DispatchEnvelopeViolationError, match=r"refuses bind.*missing_hash="
    ):
        _make_surface(role=role)


@pytest.mark.unit
def test_dispatch_surface_rejects_non_signature_object() -> None:
    """Invariant 1 — signature MUST satisfy SignatureContract protocol."""

    class NotASignature:
        # Missing input_schema / output_schema
        name = "x"

    with pytest.raises(TypeError, match="SignatureContract"):
        _make_surface(signature=NotASignature())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# DispatchSurface.dispatch — runtime invariants (1, 2, 4)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_input_payload_type_mismatch_raises() -> None:
    """Invariant 1 — declared str field receives int → DispatchValidationError.

    C5-1 error-leakage fix: caller-facing message carries the field
    hash, NOT the schema field name. The hash is stable
    (sha256(field_name)[:8]) so log-aggregator correlation against
    structured DEBUG logs is preserved.
    """
    surface = _make_surface()
    with pytest.raises(
        DispatchValidationError, match=r"field_hash=.*failed schema validation"
    ):
        await surface.dispatch({"user_id": 42})  # type: ignore[dict-item]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_input_payload_extra_key_rejected() -> None:
    """Closed-world schema — extra keys are rejected (Rule 3c parity)."""
    surface = _make_surface()
    with pytest.raises(DispatchValidationError, match="undeclared"):
        await surface.dispatch({"user_id": "u-1", "extra": "x"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_input_payload_missing_required_field_raises() -> None:
    surface = _make_surface()
    with pytest.raises(DispatchValidationError, match="missing required"):
        await surface.dispatch({})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_input_payload_non_dict_raises() -> None:
    surface = _make_surface()
    with pytest.raises(DispatchValidationError, match="type mismatch"):
        await surface.dispatch("not a dict")  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_tenant_mismatch_raises_cascade_violation() -> None:
    """Invariant 2 — connector observed tenant != cascade tenant."""
    connector = MockConnector(tenant_id_observed="tenant-B")
    cascade = _build_cascade(tenant_id="tenant-A")
    surface = _make_surface(connector=connector, cascade=cascade)
    with pytest.raises(CascadeTenantViolationError):
        await surface.dispatch({"user_id": "u-1"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_global_cascade_accepts_any_observed_tenant() -> None:
    """Global cascade accepts any observed tenant including None."""
    connector = MockConnector(tenant_id_observed=None)
    cascade = _build_cascade(tenant_id=None)  # global
    surface = _make_surface(connector=connector, cascade=cascade)
    result = await surface.dispatch({"user_id": "u-1"})
    assert isinstance(result, DispatchResult)
    assert result.tenant_id == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_successful_returns_dispatch_result() -> None:
    surface = _make_surface()
    result = await surface.dispatch({"user_id": "u-42"})
    assert isinstance(result, DispatchResult)
    assert result.payload == {"created": True}
    assert result.tenant_id == "tenant-a"
    assert result.connector_id == "mock-conn-1"
    assert result.executed_at.tzinfo is not None
    # Invariant 4 — exactly one audit event was emitted → one entry hash.
    assert len(result.audit_chain_entries) == 1
    # Each hash is a 64-char lowercase hex SHA-256.
    for h in result.audit_chain_entries:
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_audit_engine_round_trip() -> None:
    """Round-trip: dispatch emits events → audit_engine.entries reflects them."""
    chain = _build_chain("agent-roundtrip")
    audit_engine = AuditChainEngine(chain=chain)
    connector = MockConnector(
        audit_events=(
            DelegateEventType.EXTERNAL_SIDE_EFFECT,
            DelegateEventType.GRANT_CONSUMPTION,
        ),
    )
    cascade = _build_cascade()
    identity = _build_identity()
    cascade.register_root_grantee(identity)  # #1146 H1
    surface = DispatchSurface(
        connector=connector,
        signature=FakeSignatureHelper(),
        envelope=_build_envelope(),
        identity=identity,
        audit_engine=audit_engine,
        trust_cascade=cascade,
        role=_build_role(),
        signer=_test_signer,
    )
    assert len(audit_engine.entries) == 0
    result = await surface.dispatch({"user_id": "u-1"})
    # Both events emitted onto the chain.
    assert len(audit_engine.entries) == 2
    assert len(result.audit_chain_entries) == 2
    # Audit chain entries are monotonic — sequence 0 then 1.
    assert audit_engine.entries[0].sequence == 0
    assert audit_engine.entries[1].sequence == 1
    # Both entries carry the connector_id in their payload (wiring evidence).
    for entry in audit_engine.entries:
        assert entry.event_payload["connector_id"] == "mock-conn-1"
        assert entry.event_payload["signature_name"] == "create_user"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_non_audit_visible_event_propagates_emission_error() -> None:
    """Invariant 4 — REASONING_SCRATCHPAD is not audit-visible; engine refuses."""
    connector = MockConnector(
        audit_events=(DelegateEventType.REASONING_SCRATCHPAD,),
    )
    surface = _make_surface(connector=connector)
    with pytest.raises(AuditChainEmissionError, match="audit-visible"):
        await surface.dispatch({"user_id": "u-1"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_connector_invocation_carries_bound_identity_and_envelope() -> (
    None
):
    """Connector.invoke receives the SAME identity + envelope bound at construction."""
    identity = _build_identity()
    envelope = _build_envelope()
    connector = MockConnector()
    cascade = _build_cascade()
    cascade.register_root_grantee(identity)  # #1146 H1
    surface = DispatchSurface(
        connector=connector,
        signature=FakeSignatureHelper(),
        envelope=envelope,
        identity=identity,
        audit_engine=AuditChainEngine(chain=_build_chain()),
        trust_cascade=cascade,
        role=_build_role(),
        signer=_test_signer,
    )
    await surface.dispatch({"user_id": "u-1"})
    assert len(connector.invocations) == 1
    inv = connector.invocations[0]
    # Identity passed by reference — same delegate_id.
    assert inv["identity"].delegate_id == identity.delegate_id
    # Envelope passed by reference — same genesis_id.
    assert inv["envelope"].genesis_id == envelope.genesis_id
    # Input payload passed unchanged.
    assert inv["input_payload"] == {"user_id": "u-1"}


# ---------------------------------------------------------------------------
# F5 monotonic envelope — Invariant 1 (envelope tightening, not widening)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_envelope_tightening_between_bind_and_invocation_ok() -> None:
    """The bound envelope CAN be tightened to produce a NEW envelope; the
    original bound envelope is NOT mutated (Invariant 1).

    DispatchSurface holds the envelope by reference (frozen dataclass) so
    the bound envelope is immutable. Tightening produces a NEW instance.
    """
    envelope = _build_envelope()
    surface = _make_surface(envelope=envelope)
    # Bound envelope identity preserved.
    assert surface.envelope is envelope
    # Tighten to a strictly stricter budget — produces a NEW envelope,
    # does NOT mutate the surface's bound envelope.
    tighter = ConstraintEnvelope(financial=FinancialConstraint(budget_limit=500.0))
    new_envelope = envelope.tighten_with(tighter)
    assert new_envelope is not envelope
    # Surface still holds the ORIGINAL envelope (Invariant 1 — bind is final).
    assert surface.envelope is envelope


@pytest.mark.unit
def test_envelope_widening_rejected_by_tighten_with() -> None:
    """Widening (loosening) the envelope is rejected by tighten_with.

    Invariant 1 transitively: the F5 widening-raise gate lives in the
    DelegateConstraintEnvelope.tighten_with method; DispatchSurface
    delegates to it. The widening attempt MUST raise EnvelopeWideningError
    BEFORE any silent intersection.
    """
    from kailash.delegate.envelope import EnvelopeWideningError

    envelope = _build_envelope()  # budget_limit=1000.0
    # Attempt to widen to budget=2000 — loosens the financial dim.
    looser = ConstraintEnvelope(financial=FinancialConstraint(budget_limit=2000.0))
    with pytest.raises(EnvelopeWideningError):
        envelope.tighten_with(looser)


# ---------------------------------------------------------------------------
# DispatchResult — frozen + structural validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dispatch_result_is_frozen() -> None:
    r = DispatchResult(
        payload={"x": 1},
        audit_chain_entries=(),
        executed_at=datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc),
        tenant_id="t",
        connector_id="c",
        dispatch_id=uuid.uuid4(),
    )
    with pytest.raises(FrozenInstanceError):
        r.payload = {}  # type: ignore[misc]


@pytest.mark.unit
def test_dispatch_result_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        DispatchResult(
            payload={},
            audit_chain_entries=(),
            executed_at=datetime(2026, 5, 22, 12, 0, 0),  # naive
            tenant_id="t",
            connector_id="c",
            dispatch_id=uuid.uuid4(),
        )


@pytest.mark.unit
def test_dispatch_result_rejects_empty_connector_id() -> None:
    with pytest.raises(ValueError, match="connector_id"):
        DispatchResult(
            payload={},
            audit_chain_entries=(),
            executed_at=datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc),
            tenant_id="t",
            connector_id="",
            dispatch_id=uuid.uuid4(),
        )


# ---------------------------------------------------------------------------
# DispatchCascadeViolationError — typed-error reachability
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dispatch_cascade_violation_error_is_value_error() -> None:
    """DispatchCascadeViolationError is the typed surface for grantee
    refusal; it is a ValueError per the S2.5/S3/S4 convention.

    #1146 H1 closure: the grantee-registry check IS wired (see the
    DispatchSurface H1 tests below). This test pins the typed-error
    hierarchy so downstream callers can catch on
    DispatchCascadeViolationError without depending on its concrete
    message shape.
    """
    err = DispatchCascadeViolationError("test")
    assert isinstance(err, ValueError)
    assert isinstance(err, DispatchCascadeViolationError)


# ---------------------------------------------------------------------------
# Round 1 — C2-1 signer requirement (zero-tolerance fake-encryption fix)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dispatch_surface_rejects_non_callable_signer() -> None:
    """C2-1: signer MUST be a callable; None/placeholder is BLOCKED."""
    # Call DispatchSurface directly to bypass the test helper's signer default.
    with pytest.raises(TypeError, match="signer MUST be a callable"):
        DispatchSurface(
            connector=MockConnector(),
            signature=FakeSignatureHelper(),
            envelope=_build_envelope(),
            identity=_build_identity(),
            audit_engine=AuditChainEngine(chain=_build_chain()),
            trust_cascade=_build_cascade(),
            role=_build_role(),
            signer=None,  # type: ignore[arg-type]
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_invokes_injected_signer_per_event() -> None:
    """C2-1: every audit-event emission MUST call the injected signer
    exactly once with the canonical-bytes encoding of the payload."""
    captured: list[bytes] = []

    def recording_signer(canonical_bytes: bytes) -> str:
        captured.append(canonical_bytes)
        h = hashlib.sha256(canonical_bytes).hexdigest()
        return h + h

    connector = MockConnector(
        audit_events=(
            DelegateEventType.EXTERNAL_SIDE_EFFECT,
            DelegateEventType.GRANT_CONSUMPTION,
        ),
    )
    surface = _make_surface(connector=connector, signer=recording_signer)
    await surface.dispatch({"user_id": "u-1"})
    # Signer called once per emitted event (2 in this case)
    assert len(captured) == 2
    # Each call received non-empty UTF-8 canonical bytes
    for cb in captured:
        assert isinstance(cb, bytes)
        assert len(cb) > 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_signer_fault_raises_dispatch_signer_error() -> None:
    """C2-1: signer that raises MUST surface DispatchSignerError, not
    leak the raw exception to the caller."""

    def faulty_signer(_canonical_bytes: bytes) -> str:
        raise RuntimeError("signing key unavailable")

    surface = _make_surface(signer=faulty_signer)
    with pytest.raises(DispatchSignerError, match="signing key unavailable"):
        await surface.dispatch({"user_id": "u-1"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_signer_returns_non_str_raises() -> None:
    """C2-1: signer return type MUST be str; surface-shape error."""

    def bad_return_signer(_canonical_bytes: bytes) -> str:
        return 12345  # type: ignore[return-value]

    surface = _make_surface(signer=bad_return_signer)
    with pytest.raises(DispatchSignerError, match="MUST return str"):
        await surface.dispatch({"user_id": "u-1"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_signer_returns_short_signature_raises() -> None:
    """C2-1: signer return value that is not exactly 128 lowercase-hex
    chars is structurally invalid (mirrors the audit engine's _validate_hex
    Ed25519 contract at the dispatch boundary for unambiguous attribution).
    """

    def short_signer(_canonical_bytes: bytes) -> str:
        return "0" * 16  # not 128 chars

    surface = _make_surface(signer=short_signer)
    with pytest.raises(DispatchSignerError, match="128-char lowercase-hex"):
        await surface.dispatch({"user_id": "u-1"})


# ---------------------------------------------------------------------------
# Round 1 — C2-3 side-effect-requires-audit gate
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_side_effect_without_audit_blocked() -> None:
    """C2-3: external_side_effect=True with zero audit_events is BLOCKED
    per zero-tolerance.md Rule 2 (fake-dispatch class)."""
    connector = MockConnector(
        audit_events=(),
        external_side_effect=True,
    )
    surface = _make_surface(connector=connector)
    with pytest.raises(DispatchValidationError, match="side-effects without audit"):
        await surface.dispatch({"user_id": "u-1"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_no_side_effect_no_audit_is_ok() -> None:
    """C2-3 negative case: a read-only connector with no audit events
    and no side-effect is permitted (counterfactual to the gate)."""
    connector = MockConnector(
        audit_events=(),
        external_side_effect=False,
    )
    surface = _make_surface(connector=connector)
    result = await surface.dispatch({"user_id": "u-1"})
    assert isinstance(result, DispatchResult)
    assert result.audit_chain_entries == ()


# ---------------------------------------------------------------------------
# Round 1 — C4-1 F5 monotonicity runtime re-check
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_capability_revocation_between_bind_and_dispatch_fails_closed() -> None:
    """C4-1: capability revoked between bind and dispatch → fail-closed.

    The Role object is mutated (its CapabilitySet replaced) after bind.
    DispatchSurface's runtime check compares the bind-time required-caps
    against the CURRENT role caps and raises
    DispatchEnvelopeViolationError when a required cap is missing.
    """
    from kailash.delegate.types import CapabilitySet, RoleScope

    role = _build_role(capabilities=("http.read", "http.write"))
    surface = _make_surface(role=role)
    # Revoke http.read AFTER bind. Role is frozen; bypass with
    # object.__setattr__ (test-only — production code MUST NOT bypass
    # frozen, real revocation replaces the Role instance upstream).
    object.__setattr__(
        role,
        "scope",
        RoleScope(
            domain="finance",
            capabilities=CapabilitySet(capabilities=("http.write",)),
        ),
    )
    with pytest.raises(DispatchEnvelopeViolationError, match="capability set drifted"):
        await surface.dispatch({"user_id": "u-1"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lifecycle_downgrade_to_retired_between_bind_and_dispatch_fails_closed() -> (
    None
):
    """C4-1: role lifecycle transitions to RETIRED after bind → fail-closed."""
    role = _build_role(lifecycle=RoleLifecycleState.ACTIVE)
    surface = _make_surface(role=role)
    # Transition to RETIRED AFTER bind (bypass frozen — test-only)
    object.__setattr__(role, "lifecycle", RoleLifecycleState.RETIRED)
    with pytest.raises(DispatchEnvelopeViolationError, match="lifecycle drifted"):
        await surface.dispatch({"user_id": "u-1"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_capability_widening_between_bind_and_dispatch_ignored() -> None:
    """C4-1: capability widening (gain) does NOT change behavior — bind
    is the upper bound. A subset that still includes required caps
    succeeds normally regardless of whether NEW unrelated caps were added.
    """
    from kailash.delegate.types import CapabilitySet, RoleScope

    role = _build_role(capabilities=("http.read",))
    surface = _make_surface(role=role)
    # Widen the role AFTER bind — gain unrelated capability (bypass frozen)
    object.__setattr__(
        role,
        "scope",
        RoleScope(
            domain="finance",
            capabilities=CapabilitySet(
                capabilities=("http.read", "http.write", "extra.cap")
            ),
        ),
    )
    # Dispatch succeeds: bind-time required cap (http.read) still present.
    result = await surface.dispatch({"user_id": "u-1"})
    assert isinstance(result, DispatchResult)


# ---------------------------------------------------------------------------
# Round 1 — C6-1 DoS depth + size limit
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_rejects_deeply_nested_payload() -> None:
    """C6-1: payload exceeding maximum depth raises DispatchValidationError."""
    # Build a 40-deep nested dict (limit is 32)
    payload: dict[str, Any] = {"user_id": "u-1"}
    inner: dict[str, Any] = payload
    for _ in range(40):
        inner["nested"] = {}
        inner = inner["nested"]
    # Use a signature accepting an extra dict field
    sig = FakeSignatureHelper(input_schema={"user_id": str, "deep": dict})
    payload = {"user_id": "u-1", "deep": payload["nested"]}
    surface = _make_surface(signature=sig)
    with pytest.raises(DispatchValidationError, match="exceeds maximum nesting depth"):
        await surface.dispatch(payload)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_rejects_oversize_payload() -> None:
    """C6-1: payload exceeding serialized-size limit raises validation."""
    huge_str = "x" * (2 * 1024 * 1024)  # 2 MiB
    sig = FakeSignatureHelper(input_schema={"user_id": str, "blob": str})
    surface = _make_surface(signature=sig)
    with pytest.raises(
        DispatchValidationError, match="exceeds maximum serialized size"
    ):
        await surface.dispatch({"user_id": "u-1", "blob": huge_str})


# ---------------------------------------------------------------------------
# Round 1 — C6-2 strict type check (bool BLOCKED for int)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_rejects_bool_for_int_field() -> None:
    """C6-2: isinstance(True, int) is True in Python; explicitly reject
    bool for int-declared fields (security.md sanitizer Rule 2)."""
    sig = FakeSignatureHelper(input_schema={"user_id": str, "count": int})
    surface = _make_surface(signature=sig)
    with pytest.raises(DispatchValidationError, match="bool BLOCKED"):
        await surface.dispatch({"user_id": "u-1", "count": True})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_accepts_int_for_float_field() -> None:
    """C6-2 numeric-tower carve-out: int satisfies float-declared field."""
    sig = FakeSignatureHelper(input_schema={"user_id": str, "ratio": float})
    surface = _make_surface(signature=sig)
    result = await surface.dispatch({"user_id": "u-1", "ratio": 42})
    assert isinstance(result, DispatchResult)


# ---------------------------------------------------------------------------
# Round 1 closure-parity Row 3 — to_dict / from_dict round-trip
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_connector_invocation_result_roundtrip() -> None:
    """ConnectorInvocationResult.to_dict → from_dict is lossless."""
    r = ConnectorInvocationResult(
        payload={"created": True, "id": "u-42"},
        audit_events=(
            DelegateEventType.EXTERNAL_SIDE_EFFECT,
            DelegateEventType.GRANT_CONSUMPTION,
        ),
        tenant_id_observed="tenant-a",
        external_side_effect=True,
    )
    d = r.to_dict()
    # Wire-format shape: audit_events emitted as list of string values
    assert isinstance(d["audit_events"], list)
    assert d["audit_events"] == ["external_side_effect", "grant_consumption"]
    assert d["tenant_id_observed"] == "tenant-a"
    assert d["external_side_effect"] is True
    # Round-trip reconstruction
    r2 = ConnectorInvocationResult.from_dict(d)
    assert r2 == r
    assert r2.audit_events == r.audit_events
    assert r2.payload == r.payload


@pytest.mark.unit
def test_connector_invocation_result_from_dict_rejects_missing_field() -> None:
    with pytest.raises(ValueError, match="missing required field"):
        ConnectorInvocationResult.from_dict({"payload": {}, "audit_events": []})


@pytest.mark.unit
def test_connector_invocation_result_from_dict_handles_none_tenant() -> None:
    """Optional tenant_id_observed round-trips through None."""
    r = ConnectorInvocationResult(
        payload={},
        audit_events=(),
        tenant_id_observed=None,
        external_side_effect=False,
    )
    r2 = ConnectorInvocationResult.from_dict(r.to_dict())
    assert r2.tenant_id_observed is None


@pytest.mark.unit
def test_dispatch_result_roundtrip() -> None:
    """DispatchResult.to_dict → from_dict is lossless on every field."""
    did = uuid.uuid4()
    r = DispatchResult(
        payload={"created": True},
        audit_chain_entries=("a" * 64, "b" * 64),
        executed_at=datetime(2026, 5, 22, 12, 30, 0, tzinfo=timezone.utc),
        tenant_id="tenant-wire",
        connector_id="conn-1",
        dispatch_id=did,
    )
    d = r.to_dict()
    assert d["dispatch_id"] == str(did)
    assert d["executed_at"] == "2026-05-22T12:30:00+00:00"
    assert d["audit_chain_entries"] == ["a" * 64, "b" * 64]
    r2 = DispatchResult.from_dict(d)
    assert r2 == r
    assert r2.dispatch_id == did
    assert r2.executed_at == r.executed_at


@pytest.mark.unit
def test_dispatch_result_from_dict_rejects_missing_dispatch_id() -> None:
    with pytest.raises(ValueError, match="dispatch_id"):
        DispatchResult.from_dict(
            {
                "payload": {},
                "audit_chain_entries": [],
                "executed_at": "2026-05-22T12:00:00+00:00",
                "tenant_id": "t",
                "connector_id": "c",
            }
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_result_dispatch_id_is_unique_per_call() -> None:
    """Each dispatch() generates a fresh dispatch_id UUID."""
    surface = _make_surface()
    r1 = await surface.dispatch({"user_id": "u-1"})
    r2 = await surface.dispatch({"user_id": "u-2"})
    assert r1.dispatch_id != r2.dispatch_id
    assert isinstance(r1.dispatch_id, uuid.UUID)
    assert isinstance(r2.dispatch_id, uuid.UUID)


# ---------------------------------------------------------------------------
# Round 1 — DispatchSignerError typed-error reachability
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dispatch_signer_error_is_value_error() -> None:
    """DispatchSignerError MUST be a ValueError per the typed-error
    convention; callers MAY catch ValueError as a base class."""
    err = DispatchSignerError("test")
    assert isinstance(err, ValueError)
    assert isinstance(err, DispatchSignerError)


# ---------------------------------------------------------------------------
# #1143 §10 G1 — principal-kind discriminator dispatch gate
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dispatch_surface_refuses_service_account_on_sovereign_only_role() -> None:
    """#1143 §10 G1 — DispatchSurface.__init__ MUST refuse a
    service_account-kind identity binding to a role whose
    permitted_principal_kinds = frozenset({"sovereign"}).
    """
    sovereign_only_role = _build_role(
        permitted_principal_kinds=frozenset({"sovereign"}),
    )
    service_account_identity = _build_identity(principal_kind="service_account")
    with pytest.raises(DispatchEnvelopeViolationError, match=r"principal_kind"):
        _make_surface(role=sovereign_only_role, identity=service_account_identity)


@pytest.mark.unit
def test_dispatch_surface_refuses_delegate_on_sovereign_only_role() -> None:
    """Mirror case: the default delegate kind ALSO refuses against a
    sovereign-only role. The discriminator is exact; default kinds get
    no implicit pass."""
    sovereign_only_role = _build_role(
        permitted_principal_kinds=frozenset({"sovereign"}),
    )
    delegate_identity = _build_identity(principal_kind="delegate")
    with pytest.raises(DispatchEnvelopeViolationError, match=r"principal_kind"):
        _make_surface(role=sovereign_only_role, identity=delegate_identity)


@pytest.mark.unit
def test_dispatch_surface_allows_sovereign_on_sovereign_only_role() -> None:
    """Happy path: a sovereign-kind identity binds to a sovereign-only
    role without raising."""
    sovereign_only_role = _build_role(
        permitted_principal_kinds=frozenset({"sovereign"}),
    )
    sovereign_identity = _build_identity(principal_kind="sovereign")
    surface = _make_surface(role=sovereign_only_role, identity=sovereign_identity)
    assert surface.identity.principal_kind == "sovereign"


@pytest.mark.unit
def test_dispatch_surface_default_permitted_set_allows_all_kinds() -> None:
    """Backwards-compat: roles defined without explicit
    permitted_principal_kinds permit every kind, so existing call sites
    continue to bind cleanly."""
    default_role = _build_role()  # default permitted = all kinds
    for kind in ("sovereign", "service_account", "delegate"):
        ident = _build_identity(principal_kind=kind)
        surface = _make_surface(role=default_role, identity=ident)
        assert surface.identity.principal_kind == kind


@pytest.mark.unit
def test_dispatch_surface_refuses_principal_kind_before_capability_check() -> None:
    """Ordering: principal_kind mismatch fires BEFORE capability
    mismatch. When a role has neither the right kind nor the right
    capabilities, the kind error surfaces (the more fundamental refusal).
    """
    role = _build_role(
        capabilities=("unrelated.cap",),  # connector requires http.read
        permitted_principal_kinds=frozenset({"sovereign"}),
    )
    service_account_identity = _build_identity(principal_kind="service_account")
    with pytest.raises(DispatchEnvelopeViolationError, match=r"principal_kind"):
        _make_surface(role=role, identity=service_account_identity)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_principal_kind_re_check_at_dispatch_time() -> None:
    """F5 / R2 defense-in-depth: the principal_kind check re-fires at
    every dispatch() start. If the role's permitted set were swapped
    after bind (object.__setattr__ bypass), the re-check refuses the
    invocation.
    """
    # Bind with an all-kinds role (the default), then swap the role's
    # permitted set to sovereign-only via object.__setattr__ to simulate
    # post-bind tightening.
    surface = _make_surface(
        identity=_build_identity(principal_kind="service_account"),
    )
    object.__setattr__(
        surface.role, "permitted_principal_kinds", frozenset({"sovereign"})
    )
    with pytest.raises(DispatchEnvelopeViolationError, match=r"principal_kind"):
        await surface.dispatch({"user_id": "u-1"})


# ---------------------------------------------------------------------------
# #1146 H1 — grantee-registry bind + dispatch gate (cascade-as-authorization)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dispatch_surface_refuses_ungranted_identity_at_bind() -> None:
    """#1146 H1 — DispatchSurface.__init__ MUST raise
    DispatchCascadeViolationError when the bound identity's delegate_id
    is not in the cascade's grantee registry.

    PR #1144 holistic /redteam HIGH H1: previously any caller with ANY
    DelegateIdentity and a tenant-matching cascade could construct a
    DispatchSurface that audited as that identity. The grantee check
    closes this — the identity MUST have transited cascade_child OR
    been explicitly seeded via register_root_grantee.
    """
    with pytest.raises(
        DispatchCascadeViolationError, match=r"not a registered grantee"
    ):
        _make_surface(skip_grantee_registration=True)


@pytest.mark.unit
def test_dispatch_surface_admits_root_grantee_at_bind() -> None:
    """Identity explicitly registered via register_root_grantee binds
    cleanly — the canonical bootstrap path."""
    cascade = _build_cascade()
    identity = _build_identity()
    cascade.register_root_grantee(identity)
    surface = DispatchSurface(
        connector=MockConnector(),
        signature=FakeSignatureHelper(),
        envelope=_build_envelope(),
        identity=identity,
        audit_engine=AuditChainEngine(chain=_build_chain()),
        trust_cascade=cascade,
        role=_build_role(),
        signer=_test_signer,
    )
    assert surface.identity.delegate_id == identity.delegate_id


@pytest.mark.unit
def test_dispatch_surface_admits_cascade_child_grantee_at_bind() -> None:
    """An identity admitted as a child via cascade_child binds cleanly
    — the canonical 'admit-via-cascade' path."""
    cascade = _build_cascade()
    parent = _build_identity()
    child = _build_identity()
    cascade.register_root_grantee(parent)
    # Bring child into the registry via a successful cascade_child.
    parent_env = _build_envelope()
    cascade.cascade_child(
        parent_env,
        parent_env,  # same envelope = no widening
        parent_identity=parent,
        child_identity=child,
        parent_scope=_build_role().scope,
        child_scope=_build_role().scope,
        child_tenant=cascade.tenant,
        grant_proof="a" * 128,
    )
    # Now construct a DispatchSurface as the CHILD — admitted by cascade.
    surface = DispatchSurface(
        connector=MockConnector(),
        signature=FakeSignatureHelper(),
        envelope=parent_env,
        identity=child,
        audit_engine=AuditChainEngine(chain=_build_chain()),
        trust_cascade=cascade,
        role=_build_role(),
        signer=_test_signer,
    )
    assert surface.identity.delegate_id == child.delegate_id


@pytest.mark.unit
def test_dispatch_surface_refuses_grantee_before_capability_check() -> None:
    """Ordering: grantee gate fires BEFORE capability gate. When an
    identity is both ungranted AND the role lacks required caps, the
    grantee error surfaces (the more fundamental refusal — cascade
    authorization precedes capability authorization)."""
    role = _build_role(capabilities=("unrelated.cap",))  # connector wants http.read
    with pytest.raises(
        DispatchCascadeViolationError, match=r"not a registered grantee"
    ):
        _make_surface(role=role, skip_grantee_registration=True)


@pytest.mark.unit
def test_dispatch_surface_refuses_grantee_after_principal_kind_check() -> None:
    """Ordering: principal_kind gate fires BEFORE grantee gate. A
    wrong-kind identity surfaces principal_kind refusal even when also
    ungranted (principal_kind is structurally more fundamental —
    wrong-kind identity has no business being grantee-checked)."""
    sovereign_only_role = _build_role(
        permitted_principal_kinds=frozenset({"sovereign"}),
    )
    service_account_identity = _build_identity(principal_kind="service_account")
    # Both gates would refuse; ordering says principal_kind wins.
    with pytest.raises(DispatchEnvelopeViolationError, match=r"principal_kind"):
        _make_surface(
            role=sovereign_only_role,
            identity=service_account_identity,
            skip_grantee_registration=True,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_grantee_re_check_at_dispatch_time() -> None:
    """F5 / R2 defense-in-depth: the grantee check re-fires at every
    dispatch() start. If the cascade's grantee registry were mutated
    after bind (via Python's name-mangled internal slot
    ``_TenantScopedCascade__grantees``), the re-check refuses the
    invocation.

    The internal slot is name-mangled (double-underscore at class
    scope) so a single-underscore access like ``cascade._grantees``
    raises ``AttributeError``. Reaching the mutable set requires
    spelling the mangled form. Production code MUST NOT do this; this
    test exercises the mangled form deliberately to simulate a
    determined post-bind registry mutation and confirm the dispatch-time
    re-check structurally guards against it.
    """
    surface = _make_surface()
    # Drain the registry via the name-mangled internal slot — simulating
    # a post-bind registry mutation. The mangled form is the only path
    # external code can reach the mutable set.
    object.__getattribute__(
        surface.trust_cascade, "_TenantScopedCascade__grantees"
    ).clear()
    with pytest.raises(
        DispatchCascadeViolationError, match=r"no longer a registered grantee"
    ):
        await surface.dispatch({"user_id": "u-1"})


@pytest.mark.unit
def test_tenant_scoped_cascade_grantees_slot_is_name_mangled() -> None:
    """Per security-reviewer F1: the grantee registry MUST NOT be reachable
    via a single-underscore alias. The internal slot is name-mangled
    (``_TenantScopedCascade__grantees``); ``cascade._grantees`` raises
    ``AttributeError``. The mangled form is loud and intentional —
    determined adversaries with a cascade reference can still spell it,
    but the cascade reference IS itself the trust authority (see class
    docstring + README #1147 disclosure for the durable-registry
    roadmap).
    """
    from kailash.delegate.trust import TenantScope, TenantScopedCascade

    cascade = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-test"))
    # Underscore-prefix alias raises AttributeError — single-underscore
    # convention is NOT the mutation surface.
    with pytest.raises(AttributeError):
        cascade._grantees  # noqa: B018
    # The mangled form IS reachable (Python's name-mangling rule) —
    # documented and intentional per the trust boundary.
    mangled = object.__getattribute__(cascade, "_TenantScopedCascade__grantees")
    assert mangled == set()
