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


# ---------------------------------------------------------------------------
# Deterministic test signer — produces a 128-char lowercase hex string from
# the canonical-bytes input. SHA-256 doubled to 128 chars satisfies the
# audit-engine's _validate_hex(expected_len=128) contract.
# ---------------------------------------------------------------------------


def _test_signer(canonical_bytes: bytes) -> str:
    h = hashlib.sha256(canonical_bytes).hexdigest()
    return h + h  # 128-char lowercase hex


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


def _build_identity() -> DelegateIdentity:
    return DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-s5",
        role_binding_ref="rb-s5",
        genesis_ref="g-agent-s5",
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
) -> Role:
    return Role(
        role_id=uuid.uuid4(),
        display_name="test-role",
        scope=RoleScope(
            domain="finance",
            capabilities=CapabilitySet(capabilities=capabilities),
        ),
        lifecycle=lifecycle,
    )


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
) -> DispatchSurface:
    return DispatchSurface(
        connector=connector if connector is not None else MockConnector(),
        signature=signature if signature is not None else FakeSignatureHelper(),
        envelope=envelope if envelope is not None else _build_envelope(),
        identity=identity if identity is not None else _build_identity(),
        audit_engine=AuditChainEngine(chain=_build_chain()),
        trust_cascade=cascade if cascade is not None else _build_cascade(),
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
    surface = DispatchSurface(
        connector=connector,
        signature=FakeSignatureHelper(),
        envelope=_build_envelope(),
        identity=_build_identity(),
        audit_engine=audit_engine,
        trust_cascade=_build_cascade(),
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
    surface = DispatchSurface(
        connector=connector,
        signature=FakeSignatureHelper(),
        envelope=envelope,
        identity=identity,
        audit_engine=AuditChainEngine(chain=_build_chain()),
        trust_cascade=_build_cascade(),
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

    The runtime grantee-registry check is deferred to S7+ (the current
    TenantScopedCascade emits GrantMoment but does not retain the grantee
    set); this test asserts the error class exists and is in the
    correct base hierarchy so callers can catch it stably.
    """
    err = DispatchCascadeViolationError("test")
    assert isinstance(err, ValueError)
    assert isinstance(err, DispatchCascadeViolationError)
