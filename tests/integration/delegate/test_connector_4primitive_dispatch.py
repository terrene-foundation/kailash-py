# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration test: Connector 4-primitive shape + verifier wiring.

Per F-17 (Connector ABC rebuild) + C1 (signature verification wiring):
this test verifies that a new-shape Connector implementing all 4
primitives (3 accessors + authenticate + write + read) dispatches
end-to-end through :class:`DispatchSurface` AND that the verifier-wiring
gate fires correctly when a :class:`Verifier` is bound.

Per ``rules/testing.md`` § "Protocol-Satisfying Deterministic Adapters",
the connector here is a real subclass of the abstract :class:`Connector`
satisfying all 4 primitives deterministically — NOT a mock.

Wiring contract verified:

1. New-shape connector with all 6 abstract members implemented
   instantiates and dispatches end-to-end.
2. The 3 accessor surfaces are reachable from the bound connector.
3. The 3 primitive methods (authenticate/write/read) are callable
   independently of the dispatch path.
4. Verifier wiring: when a permissive verifier is bound, dispatch
   succeeds; when a rejecting verifier is bound, dispatch raises
   :class:`DispatchSignatureError`; when verifier=None (legacy default),
   verification is skipped (backwards-compat).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import pytest

from kailash.delegate.audit import AuditChainEngine, DelegateEventType
from kailash.delegate.dispatch import (
    AttestedReadReceipt,
    Connector,
    ConnectorInvocationResult,
    DispatchResult,
    DispatchSignatureError,
    DispatchSurface,
    Principal,
    SignedActionEnvelope,
)
from kailash.delegate.envelope import DelegateConstraintEnvelope
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

# Shard Y owns kailash.delegate.verifier — this stub satisfies the
# Protocol contract in-worktree pending Shard Y's merge.
from tests.unit.delegate._verifier_stub import (
    AcceptAllVerifierStub,
    RaisingVerifierStub,
    RejectAllVerifierStub,
)


def _test_signer(canonical_bytes: bytes) -> str:
    """Deterministic 128-char hex signer for integration tests."""
    h = hashlib.sha256(canonical_bytes).hexdigest()
    return h + h


# ---------------------------------------------------------------------------
# Substrate stubs (real Protocol-satisfying adapters per rules/testing.md)
# ---------------------------------------------------------------------------


class _RevocationStub:
    """Real RevocationChannel — returns False for any delegate_id."""

    def is_revoked(self, delegate_id: str) -> bool:
        return False


class _LedgerStub:
    """Real KnowledgeLedger — records every (event_type, payload)."""

    def __init__(self) -> None:
        self.records: list[tuple[str, dict]] = []

    def record(self, event_type: str, payload: dict) -> None:
        self.records.append((event_type, dict(payload)))


class _AuthStub:
    """Real AuthVerifier — accepts any token."""

    def verify_token(self, token: str) -> bool:
        return True


# ---------------------------------------------------------------------------
# New-shape Connector: implements all 6 abstract members + invoke
# ---------------------------------------------------------------------------


class FourPrimitiveConnector(Connector):
    """Real new-shape Connector — exercises all 4 primitives + 3 accessors.

    Records every primitive invocation so the test can assert all 4
    primitives are reachable AND the dispatch path still calls invoke()
    for the legacy entry point (preserves backwards-compat).
    """

    connector_id = "four-primitive-conn"
    connector_kind = "test"
    requires_capabilities = frozenset({"test.dispatch"})

    def __init__(self) -> None:
        self._revocation = _RevocationStub()
        self._ledger = _LedgerStub()
        self._auth = _AuthStub()
        self.calls: dict[str, list] = {
            "invoke": [],
            "authenticate": [],
            "write": [],
            "read": [],
        }

    @property
    def revocation(self):
        return self._revocation

    @property
    def ledger(self):
        return self._ledger

    @property
    def auth_verifier(self):
        return self._auth

    async def authenticate(self, identity, envelope) -> Principal:
        self.calls["authenticate"].append((identity, envelope))
        return Principal(
            delegate_id=str(identity.delegate_id),
            tenant_id="tenant-4p",
            claims={"primitive": "authenticate"},
        )

    async def write(self, action, *, identity, envelope) -> SignedActionEnvelope:
        self.calls["write"].append((action, identity, envelope))
        payload = await action()
        canonical_bytes = (
            str(payload).encode("utf-8") if not isinstance(payload, bytes) else payload
        )
        return SignedActionEnvelope(
            action_id=uuid.uuid4(),
            canonical_bytes=canonical_bytes,
            signature=b"4p-write-sig",
            signer_delegate_id=str(identity.delegate_id),
            payload=payload if isinstance(payload, dict) else {"value": payload},
        )

    async def read(self, query, *, identity, envelope):
        self.calls["read"].append((query, identity, envelope))
        value = await query()
        receipt = AttestedReadReceipt(
            read_id=uuid.uuid4(),
            canonical_bytes=str(value).encode("utf-8"),
            attestation=b"4p-read-attest",
            attester_delegate_id=str(identity.delegate_id),
            observed_at=datetime.now(timezone.utc),
        )
        return value, receipt

    async def invoke(
        self, input_payload, *, identity, envelope
    ) -> ConnectorInvocationResult:
        # Dispatch hot path enters here per the legacy entry contract.
        self.calls["invoke"].append(
            {"input": dict(input_payload), "identity": identity}
        )
        return ConnectorInvocationResult(
            payload={"4p_invoke": True, "echoed": dict(input_payload)},
            audit_events=(DelegateEventType.EXTERNAL_SIDE_EFFECT,),
            tenant_id_observed="tenant-4p",
            external_side_effect=True,
        )


class _Sig:
    """Minimal SignatureContract satisfier."""

    name = "four_primitive_sig"
    input_schema = {"user_id": str}
    output_schema = {"4p_invoke": bool}


# ---------------------------------------------------------------------------
# Substrate builders
# ---------------------------------------------------------------------------


def _build_chain(agent_id: str = "agent-4p") -> TrustLineageChain:
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
        sovereign_ref="sov-4p",
        role_binding_ref="rb-4p",
        genesis_ref="g-agent-4p",
    )


def _build_envelope() -> DelegateConstraintEnvelope:
    block = GenesisRecord(
        id="g-env-4p",
        agent_id="agent-env-4p",
        authority_id="auth-env-4p",
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
        display_name="four-primitive-role",
        scope=RoleScope(
            domain="test",
            capabilities=CapabilitySet(capabilities=("test.dispatch",)),
        ),
        lifecycle=RoleLifecycleState.ACTIVE,
    )


def _build_surface(
    connector: FourPrimitiveConnector,
    *,
    verifier=None,
) -> DispatchSurface:
    chain = _build_chain()
    cascade = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-4p"))
    identity = _build_identity()
    cascade.register_root_grantee(identity)
    kwargs: dict = {
        "connector": connector,
        "signature": _Sig(),
        "envelope": _build_envelope(),
        "identity": identity,
        "audit_engine": AuditChainEngine(chain=chain),
        "trust_cascade": cascade,
        "role": _build_role(),
        "signer": _test_signer,
    }
    if verifier is not None:
        kwargs["verifier"] = verifier
    return DispatchSurface(**kwargs)


# ---------------------------------------------------------------------------
# 1. New-shape connector dispatches end-to-end (no verifier — legacy default)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_four_primitive_connector_dispatches_end_to_end() -> None:
    """A FourPrimitiveConnector dispatches successfully through DispatchSurface.

    Verifies the 6-abstract-member ABC contract holds end-to-end: the
    connector instantiates, the dispatch path enters via invoke() (legacy
    entry contract), and the result flows back as expected.
    """
    connector = FourPrimitiveConnector()
    surface = _build_surface(connector)
    result = await surface.dispatch({"user_id": "u-1"})
    assert isinstance(result, DispatchResult)
    assert result.payload == {"4p_invoke": True, "echoed": {"user_id": "u-1"}}
    # Dispatch hot path goes through invoke() (legacy entry contract)
    assert len(connector.calls["invoke"]) == 1
    assert connector.calls["invoke"][0]["input"] == {"user_id": "u-1"}


# ---------------------------------------------------------------------------
# 2. All 4 primitives are independently callable on the new-shape connector
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_four_primitive_connector_authenticate_callable() -> None:
    """The authenticate primitive is reachable independently of dispatch."""
    connector = FourPrimitiveConnector()
    identity = _build_identity()
    envelope = _build_envelope()
    principal = await connector.authenticate(identity, envelope)
    assert isinstance(principal, Principal)
    assert principal.tenant_id == "tenant-4p"
    assert principal.claims["primitive"] == "authenticate"
    assert len(connector.calls["authenticate"]) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_four_primitive_connector_write_callable() -> None:
    """The write primitive is reachable independently of dispatch."""
    connector = FourPrimitiveConnector()
    identity = _build_identity()
    envelope = _build_envelope()

    async def _action() -> dict:
        return {"written": "value-42"}

    env = await connector.write(_action, identity=identity, envelope=envelope)
    assert isinstance(env, SignedActionEnvelope)
    assert env.payload == {"written": "value-42"}
    assert env.signature == b"4p-write-sig"
    assert len(connector.calls["write"]) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_four_primitive_connector_read_callable() -> None:
    """The read primitive is reachable independently of dispatch."""
    connector = FourPrimitiveConnector()
    identity = _build_identity()
    envelope = _build_envelope()

    async def _query() -> str:
        return "read-value-99"

    value, receipt = await connector.read(_query, identity=identity, envelope=envelope)
    assert value == "read-value-99"
    assert isinstance(receipt, AttestedReadReceipt)
    assert receipt.attestation == b"4p-read-attest"
    assert len(connector.calls["read"]) == 1


# ---------------------------------------------------------------------------
# 3. Three accessor surfaces are reachable on the new-shape connector
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_four_primitive_connector_accessors_reachable() -> None:
    """The 3 accessor surfaces return their bound substrate stubs."""
    connector = FourPrimitiveConnector()
    assert isinstance(connector.revocation, _RevocationStub)
    assert isinstance(connector.ledger, _LedgerStub)
    assert isinstance(connector.auth_verifier, _AuthStub)


# ---------------------------------------------------------------------------
# 4. Verifier wiring — AcceptAll succeeds; RejectAll raises;
#    None (legacy default) skips verification
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_verifier_wiring_accept_all_dispatches_successfully() -> None:
    """When AcceptAllVerifierStub is bound, dispatch succeeds AND verify() fires."""
    connector = FourPrimitiveConnector()
    verifier = AcceptAllVerifierStub()
    surface = _build_surface(connector, verifier=verifier)
    result = await surface.dispatch({"user_id": "u-1"})
    assert isinstance(result, DispatchResult)
    # verifier.verify was called once (one audit event = one verify)
    assert len(verifier.calls) == 1
    # Verify was called with (canonical_bytes, signature_bytes, signer_id)
    canonical_bytes, signature_bytes, signer_id = verifier.calls[0]
    assert isinstance(canonical_bytes, bytes)
    assert isinstance(signature_bytes, bytes)
    assert isinstance(signer_id, str)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_verifier_wiring_reject_all_raises_signature_error() -> None:
    """When RejectAllVerifierStub is bound, dispatch raises DispatchSignatureError."""
    connector = FourPrimitiveConnector()
    verifier = RejectAllVerifierStub()
    surface = _build_surface(connector, verifier=verifier)
    with pytest.raises(DispatchSignatureError, match="verification FAILED"):
        await surface.dispatch({"user_id": "u-1"})
    # Verifier was reached
    assert len(verifier.calls) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_verifier_wiring_none_skips_verification() -> None:
    """When verifier=None (legacy default), verification is skipped."""
    connector = FourPrimitiveConnector()
    # No verifier passed — backwards-compat path
    surface = _build_surface(connector, verifier=None)
    result = await surface.dispatch({"user_id": "u-1"})
    # Dispatch succeeds without verifier interaction
    assert isinstance(result, DispatchResult)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_verifier_wiring_raising_verifier_surfaces_signature_error() -> None:
    """When the verifier raises, dispatch wraps as DispatchSignatureError."""
    connector = FourPrimitiveConnector()
    verifier = RaisingVerifierStub(RuntimeError("verifier-stub-boom"))
    surface = _build_surface(connector, verifier=verifier)
    with pytest.raises(DispatchSignatureError, match="verifier raised"):
        await surface.dispatch({"user_id": "u-1"})


@pytest.mark.integration
def test_dispatch_surface_rejects_non_protocol_verifier() -> None:
    """A non-Verifier-protocol object passed as verifier raises TypeError at bind."""
    connector = FourPrimitiveConnector()
    with pytest.raises(TypeError, match="Verifier Protocol"):
        _build_surface(connector, verifier="not-a-verifier")  # type: ignore[arg-type]
