# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration test for ``DispatchSurface`` end-to-end wiring.

S5 #1035 — Tier-2 wiring test per ``facade-manager-detection.md`` MUST
Rule 1 ("Every Manager-Shape Class Has a Tier 2 Test"):
``DispatchSurface`` is a Surface-shape coordinator that wires
``(Connector × Signature × Envelope × Identity)`` into the
``AuditChainEngine`` + ``TenantScopedCascade`` substrate.

This test exercises the load-bearing wiring contract end-to-end:

- A real ``TenantScopedCascade`` constrains tenant isolation.
- A real ``AuditChainEngine`` (atop a real ``TrustLineageChain``)
  receives the dispatched audit events.
- A concrete ``MockConnector(Connector)`` subclass records every
  argument it received from ``DispatchSurface`` AND emits real
  ``ConnectorInvocationResult`` records that flow through the audit
  emission path.

**Tier classification:** the substrate ``TrustLineageChain`` is a real
``@dataclass`` (not a ``typing.Protocol`` satisfier), so the
"Protocol-Satisfying Deterministic Adapter" exception in
``rules/testing.md`` does NOT apply to it. The ``MockConnector`` IS a
Protocol-satisfying deterministic adapter for the abstract ``Connector``
surface — it has deterministic output and satisfies the abstract
``invoke`` contract. Per ``rules/testing.md`` § "Protocol Adapters", a
deterministic adapter for an abstract protocol is NOT a mock; it is the
test-side concrete subclass the abstract surface MUST permit.

Pairs with the ``test_audit_chainengine_wiring.py`` pattern — same
shape: import-path + facade-call shape + externally-observable assertion
end-to-end through the real substrate.
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
    DispatchCascadeViolationError,
    DispatchResult,
    DispatchSurface,
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


def _test_signer(canonical_bytes: bytes) -> str:
    """Deterministic 128-char hex signer for integration tests.

    SHA-256 doubled to 128 chars satisfies the audit-engine's
    _validate_hex(expected_len=128) contract while keeping the test
    deterministic for cross-SDK byte-vector comparison.
    """
    h = hashlib.sha256(canonical_bytes).hexdigest()
    return h + h


# ---------------------------------------------------------------------------
# Recording Connector — real Connector subclass for wiring observation
# ---------------------------------------------------------------------------


class RecordingMockConnector(Connector):
    """Deterministic Connector subclass that records all invocation args.

    Per ``rules/testing.md`` § "Protocol-Satisfying Deterministic
    Adapters", this is a real subclass of the abstract :class:`Connector`
    — NOT a mock. Its purpose: record every argument passed by
    DispatchSurface so the integration test can assert the wiring
    contract holds end-to-end.
    """

    connector_id = "wiring-conn-1"
    connector_kind = "http"
    requires_capabilities = frozenset({"http.read", "http.write"})

    def __init__(self, *, tenant_id_observed: str | None = "tenant-wire") -> None:
        self.tenant_id_observed = tenant_id_observed
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
                "input_payload": dict(input_payload),
                "identity_delegate_id": identity.delegate_id,
                "identity_sovereign_ref": identity.sovereign_ref,
                "envelope_genesis_id": envelope.genesis_id,
            }
        )
        return ConnectorInvocationResult(
            payload={"created": True, "received_user_id": input_payload["user_id"]},
            audit_events=(DelegateEventType.EXTERNAL_SIDE_EFFECT,),
            tenant_id_observed=self.tenant_id_observed,
            external_side_effect=True,
        )


class WiringSignature:
    """Minimal SignatureContract satisfier for the wiring test."""

    name = "create_user_wiring"
    input_schema = {"user_id": str}
    output_schema = {"created": bool, "received_user_id": str}


# ---------------------------------------------------------------------------
# Substrate builders (real, no mocks)
# ---------------------------------------------------------------------------


def _build_chain(agent_id: str = "agent-wiring") -> TrustLineageChain:
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
        sovereign_ref="sov-wiring",
        role_binding_ref="rb-wiring",
        genesis_ref="g-agent-wiring",
    )


def _build_envelope() -> DelegateConstraintEnvelope:
    block = GenesisRecord(
        id="g-env-wiring",
        agent_id="agent-env-wiring",
        authority_id="auth-env-wiring",
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
        display_name="wiring-test-role",
        scope=RoleScope(
            domain="finance",
            capabilities=CapabilitySet(
                capabilities=("http.read", "http.write", "extra.cap")
            ),
        ),
        lifecycle=RoleLifecycleState.ACTIVE,
    )


# ---------------------------------------------------------------------------
# Tier-2 wiring tests — every dependency is REAL
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_end_to_end_wires_audit_and_tenant() -> None:
    """End-to-end: a successful dispatch produces a real audit entry on the
    real TrustLineageChain AND the bound tenant survives cross-validation.

    Wiring contract verified:
    1. DispatchSurface.dispatch awaits Connector.invoke with the bound
       identity + envelope (RecordingMockConnector records these).
    2. ConnectorInvocationResult flows back; tenant observed matches
       cascade's bound tenant (no CascadeTenantViolationError).
    3. AuditChainEngine.emit_event lands a real AuditChainEntry on the
       wrapped TrustLineageChain.audit_anchors (externally observable
       via substrate state).
    4. DispatchResult carries the audit_chain_entries head hash.
    """
    chain = _build_chain("agent-e2e")
    audit_engine = AuditChainEngine(chain=chain)
    cascade = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-wire"))
    connector = RecordingMockConnector(tenant_id_observed="tenant-wire")
    identity = _build_identity()
    envelope = _build_envelope()
    # #1146 H1 — seed the cascade with the root grantee.
    cascade.register_root_grantee(identity)

    surface = DispatchSurface(
        connector=connector,
        signature=WiringSignature(),
        envelope=envelope,
        identity=identity,
        audit_engine=audit_engine,
        trust_cascade=cascade,
        role=_build_role(),
        signer=_test_signer,
    )

    # Pre-dispatch: chain is empty, no audit entries
    assert len(audit_engine.entries) == 0
    assert len(chain.audit_anchors) == 0
    assert len(connector.invocations) == 0

    # Dispatch
    result = await surface.dispatch({"user_id": "user-42"})

    # 1. DispatchResult shape
    assert isinstance(result, DispatchResult)
    assert result.payload == {"created": True, "received_user_id": "user-42"}
    assert result.tenant_id == "tenant-wire"
    assert result.connector_id == "wiring-conn-1"

    # 2. Connector received the bound identity + envelope (wiring evidence)
    assert len(connector.invocations) == 1
    inv = connector.invocations[0]
    assert inv["identity_delegate_id"] == identity.delegate_id
    assert inv["identity_sovereign_ref"] == "sov-wiring"
    assert inv["envelope_genesis_id"] == envelope.genesis_id
    assert inv["input_payload"] == {"user_id": "user-42"}

    # 3. AuditChainEngine wrote ONE entry through to the substrate chain
    assert len(audit_engine.entries) == 1
    assert len(chain.audit_anchors) == 1
    entry = audit_engine.entries[0]
    assert entry.event_type == "external_side_effect"
    assert entry.event_payload["connector_id"] == "wiring-conn-1"
    assert entry.event_payload["signature_name"] == "create_user_wiring"
    assert entry.event_payload["external_side_effect"] is True
    # Substrate anchor mirrors the engine entry
    anchor = chain.audit_anchors[0]
    assert anchor.action == "external_side_effect"
    assert anchor.context["sequence"] == 0

    # 4. DispatchResult.audit_chain_entries contains the head hash
    assert len(result.audit_chain_entries) == 1
    assert result.audit_chain_entries[0] == audit_engine.head_hash()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_tenant_isolation_enforced_end_to_end() -> None:
    """Tenant isolation (Invariant 2) fires end-to-end against real cascade.

    Cascade bound to tenant-A; connector observes tenant-B → raises
    CascadeTenantViolationError BEFORE any audit emission. No audit
    entry lands on the substrate chain (fail-closed contract).
    """
    chain = _build_chain("agent-tenant-iso")
    audit_engine = AuditChainEngine(chain=chain)
    cascade = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-A"))
    connector = RecordingMockConnector(tenant_id_observed="tenant-B")
    identity = _build_identity()
    # #1146 H1 — seed the cascade with the root grantee.
    cascade.register_root_grantee(identity)

    surface = DispatchSurface(
        connector=connector,
        signature=WiringSignature(),
        envelope=_build_envelope(),
        identity=identity,
        audit_engine=audit_engine,
        trust_cascade=cascade,
        role=_build_role(),
        signer=_test_signer,
    )

    with pytest.raises(CascadeTenantViolationError):
        await surface.dispatch({"user_id": "user-1"})

    # Fail-closed: connector WAS invoked (the connector is the source of
    # the observed tenant), but NO audit entry landed because the
    # tenant cross-check fires BEFORE emission.
    assert len(connector.invocations) == 1
    assert len(audit_engine.entries) == 0
    assert len(chain.audit_anchors) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_multiple_events_chain_correctly() -> None:
    """Multiple audit events from one dispatch land sequentially with
    correct previous_hash linkage on the real audit chain."""

    class MultiEventConnector(Connector):
        connector_id = "multi-event-conn"
        connector_kind = "http"
        requires_capabilities = frozenset({"http.read"})

        async def invoke(self, input_payload, *, identity, envelope):
            return ConnectorInvocationResult(
                payload={"ok": True},
                audit_events=(
                    DelegateEventType.GRANT_CONSUMPTION,
                    DelegateEventType.EXTERNAL_SIDE_EFFECT,
                    DelegateEventType.CONSTRAINT_DECISION,
                ),
                tenant_id_observed="tenant-multi",
                external_side_effect=True,
            )

    chain = _build_chain("agent-multi-event")
    audit_engine = AuditChainEngine(chain=chain)
    cascade = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-multi"))
    identity = _build_identity()
    # #1146 H1 — seed the cascade with the root grantee.
    cascade.register_root_grantee(identity)

    surface = DispatchSurface(
        connector=MultiEventConnector(),
        signature=WiringSignature(),
        envelope=_build_envelope(),
        identity=identity,
        audit_engine=audit_engine,
        trust_cascade=cascade,
        role=_build_role(),
        signer=_test_signer,
    )

    result = await surface.dispatch({"user_id": "u-multi"})

    # Three events emitted in declared order
    assert len(audit_engine.entries) == 3
    assert len(result.audit_chain_entries) == 3
    assert audit_engine.entries[0].event_type == "grant_consumption"
    assert audit_engine.entries[1].event_type == "external_side_effect"
    assert audit_engine.entries[2].event_type == "constraint_decision"

    # Sequence is monotonic, previous_hash chains correctly
    assert audit_engine.entries[0].sequence == 0
    assert audit_engine.entries[0].previous_hash == ""
    assert audit_engine.entries[1].sequence == 1
    assert audit_engine.entries[1].previous_hash != ""
    assert audit_engine.entries[2].sequence == 2
    assert (
        audit_engine.entries[2].previous_hash != audit_engine.entries[1].previous_hash
    )


# ---------------------------------------------------------------------------
# #1146 H1 — grantee-registry cascade-as-authorization wiring
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_dispatch_h1_grantee_gate_refuses_ungranted_identity_end_to_end() -> None:
    """#1146 H1 — Tier-2 wiring: an ungranted identity is refused at bind
    against a REAL TenantScopedCascade. No audit emission, no connector
    invocation, no DispatchSurface instance leaks past the gate.

    This closes PR #1144 holistic /redteam HIGH H1 end-to-end:
    a caller with an arbitrary DelegateIdentity who acquires a
    tenant-matching cascade reference CANNOT bind a DispatchSurface
    that audits as that identity.
    """
    chain = _build_chain("agent-h1")
    audit_engine = AuditChainEngine(chain=chain)
    cascade = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-h1"))
    # Identity is constructed but NEVER registered as a grantee — the
    # exact failure mode the H1 finding describes.
    ungranted_identity = _build_identity()
    with pytest.raises(
        DispatchCascadeViolationError, match=r"not a registered grantee"
    ):
        DispatchSurface(
            connector=RecordingMockConnector(tenant_id_observed="tenant-h1"),
            signature=WiringSignature(),
            envelope=_build_envelope(),
            identity=ungranted_identity,
            audit_engine=audit_engine,
            trust_cascade=cascade,
            role=_build_role(),
            signer=_test_signer,
        )
    # Fail-closed: no audit emission, no connector invocation, no
    # substrate mutation.
    assert len(audit_engine.entries) == 0
    assert len(chain.audit_anchors) == 0
    assert cascade.grantees == frozenset()


@pytest.mark.integration
def test_dispatch_h1_grantee_gate_admits_root_grantee_end_to_end() -> None:
    """#1146 H1 — happy path: identity explicitly seeded via
    register_root_grantee binds cleanly against a real cascade."""
    chain = _build_chain("agent-h1-root")
    audit_engine = AuditChainEngine(chain=chain)
    cascade = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-h1"))
    identity = _build_identity()
    # Seed the grantee registry.
    cascade.register_root_grantee(identity)
    # Bind succeeds.
    surface = DispatchSurface(
        connector=RecordingMockConnector(tenant_id_observed="tenant-h1"),
        signature=WiringSignature(),
        envelope=_build_envelope(),
        identity=identity,
        audit_engine=audit_engine,
        trust_cascade=cascade,
        role=_build_role(),
        signer=_test_signer,
    )
    assert surface.identity.delegate_id == identity.delegate_id
    assert identity.delegate_id in cascade.grantees
