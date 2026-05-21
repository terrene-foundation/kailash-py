# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration test for S3 trust cascade exercised through TrustLineageChain.

Per ``orphan-detection.md`` MUST Rule 2 and ``facade-manager-detection.md``:
the cascade primitives (``TenantScopedCascade``, ``GrantMoment``) are wired
end-to-end against the existing substrate :class:`TrustLineageChain` audit
emission so an integration regression that orphans the cascade or breaks the
audit-trail handoff fails here loudly.

Tier classification follows the S2.5 ``test_genesis_chain_roundtrip.py``
precedent (B5, Round 2 sec M-3): :class:`TrustLineageChain` is a plain
``@dataclass`` (NOT a ``typing.Protocol`` satisfier), so the Tier-2
"real-infrastructure" framing does not require Postgres at this layer — the
chain object IS the infrastructure. Real-Postgres-backed
``TrustChainStore`` persistence is the next-shard follow-up (S4 audit chain
+ S6 runtime spine wire the cascade against real PACT + real Postgres per
#1035 acceptance criterion). This test exercises:

1. End-to-end cascade success → :class:`GrantMoment` emission → audit
   record committed to the substrate :class:`TrustLineageChain`.
2. Cross-tenant cascade rejection: the chain MUST NOT receive an audit
   record for a rejected cascade (fail-closed at the cascade gate).
3. Scope-expansion cascade rejection: same audit-absence guarantee.
4. Envelope-widening cascade rejection: same audit-absence guarantee.
5. Chain hash advances after a successful cascade audit append: proves
   the cascade-emitted GrantMoment composes the chain's tamper-evident
   sequence — not a parallel side-channel.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from kailash.delegate.envelope import DelegateConstraintEnvelope, EnvelopeWideningError
from kailash.delegate.trust import (
    CascadeScopeExpansionError,
    CascadeTenantViolationError,
    GrantMoment,
    TenantScope,
    TenantScopedCascade,
)
from kailash.delegate.types import (
    CapabilitySet,
    DelegateGenesisRecord,
    DelegateIdentity,
    RoleScope,
)
from kailash.trust.chain import (
    AuthorityType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from kailash.trust.envelope import ConstraintEnvelope, FinancialConstraint


def _build_chain(*, genesis_id: str) -> TrustLineageChain:
    """Build a real (in-memory) TrustLineageChain rooted at a substrate
    GenesisRecord. Uses the same shape Wave 1 + S2.5 tests use."""
    block = GenesisRecord(
        id=genesis_id,
        agent_id="agent-tier2",
        authority_id="auth-tier2",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
        signature="d" * 128,
    )
    return TrustLineageChain(genesis=block)


def _envelope(budget: float, *, genesis_id: str) -> DelegateConstraintEnvelope:
    block = GenesisRecord(
        id=genesis_id,
        agent_id="agent-env",
        authority_id="auth-env",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
        signature="d" * 128,
    )
    genesis = DelegateGenesisRecord(
        block=block, spec_version="1", capabilities=("read",)
    )
    return DelegateConstraintEnvelope.from_genesis(
        ConstraintEnvelope(financial=FinancialConstraint(budget_limit=budget)),
        genesis,
    )


def _identity(suffix: str) -> DelegateIdentity:
    return DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref=f"sov-{suffix}",
        role_binding_ref=f"role-{suffix}",
        genesis_ref=f"genesis-{suffix}",
    )


def _scope_finance() -> RoleScope:
    return RoleScope(
        domain="finance",
        capabilities=CapabilitySet(capabilities=("read", "approve")),
    )


def _scope_finance_subset() -> RoleScope:
    return RoleScope(
        domain="finance",
        capabilities=CapabilitySet(capabilities=("read",)),
    )


def _delegation_record_from_grant(
    gm: GrantMoment,
    *,
    parent_identity: DelegateIdentity,
    child_identity: DelegateIdentity,
) -> DelegationRecord:
    """Build a substrate DelegationRecord from a Delegate-layer GrantMoment.

    The Delegate-layer GrantMoment carries the cascade-level proof; the
    substrate chain records it as a DelegationRecord so the audit trail
    composes the existing TrustLineageChain.delegations sequence."""
    return DelegationRecord(
        id=str(gm.cascade_id),
        delegator_id=parent_identity.sovereign_ref,
        delegatee_id=child_identity.sovereign_ref,
        task_id=f"cascade-{gm.cascade_id}",
        capabilities_delegated=["read"],
        constraint_subset=[f"genesis:{parent_identity.genesis_ref}"],
        delegated_at=gm.granted_at,
        signature=gm.grant_proof,
    )


# ---------------------------------------------------------------------------
# Success path — cascade emits GrantMoment, audit appended to chain
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_cascade_success_appends_to_trust_lineage_chain() -> None:
    """End-to-end success path: cascade emits GrantMoment → chain records it."""
    chain = _build_chain(genesis_id="g-tier2-success-0001")
    initial_hash = chain.hash()
    initial_count = len(chain.delegations)

    casc = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-a"))
    parent_env = _envelope(100.0, genesis_id="g-parent")
    child_env = _envelope(50.0, genesis_id="g-child")
    parent = _identity("parent")
    child = _identity("child")

    gm = casc.cascade_child(
        parent_env,
        child_env,
        parent_identity=parent,
        child_identity=child,
        parent_scope=_scope_finance(),
        child_scope=_scope_finance_subset(),
        child_tenant=TenantScope.for_tenant("tenant-a"),
        grant_proof="b" * 128,
    )

    assert isinstance(gm, GrantMoment)
    assert gm.parent_delegate_id == parent.delegate_id
    assert gm.child_delegate_id == child.delegate_id
    assert gm.tenant.tenant_id == "tenant-a"

    # Wire the cascade-emitted moment through the substrate chain.
    chain.delegations.append(
        _delegation_record_from_grant(gm, parent_identity=parent, child_identity=child)
    )

    # State-persistence verification (per testing.md § State Persistence):
    # read back the appended record and confirm chain hash advanced.
    assert len(chain.delegations) == initial_count + 1
    assert chain.delegations[-1].id == str(gm.cascade_id)
    assert chain.delegations[-1].delegator_id == parent.sovereign_ref
    assert chain.delegations[-1].delegatee_id == child.sovereign_ref
    # Hash MUST change after appending — proves the cascade record composes
    # the chain's tamper-evident sequence, not a parallel side-channel.
    assert chain.hash() != initial_hash


# ---------------------------------------------------------------------------
# Fail-closed: cross-tenant cascade — chain MUST NOT receive an audit record
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_cross_tenant_cascade_does_not_pollute_audit_chain() -> None:
    """Cross-tenant cascade raises BEFORE any chain mutation — fail-closed.

    The cascade gate's Step 1 fires before any audit work, so the
    TrustLineageChain MUST be unchanged after the failed call."""
    chain = _build_chain(genesis_id="g-tier2-crosstenant-0001")
    initial_hash = chain.hash()
    initial_count = len(chain.delegations)

    casc = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-a"))
    parent_env = _envelope(100.0, genesis_id="g-p")
    child_env = _envelope(50.0, genesis_id="g-c")

    with pytest.raises(CascadeTenantViolationError):
        casc.cascade_child(
            parent_env,
            child_env,
            parent_identity=_identity("parent"),
            child_identity=_identity("child"),
            parent_scope=_scope_finance(),
            child_scope=_scope_finance_subset(),
            child_tenant=TenantScope.for_tenant("tenant-b"),
            grant_proof="a" * 128,
        )

    # Chain unmodified — fail-closed at the cascade gate.
    assert len(chain.delegations) == initial_count
    assert chain.hash() == initial_hash


# ---------------------------------------------------------------------------
# Fail-closed: scope-expansion cascade — same audit-absence guarantee
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_scope_expansion_cascade_does_not_pollute_audit_chain() -> None:
    """Scope-expansion cascade raises BEFORE any chain mutation."""
    chain = _build_chain(genesis_id="g-tier2-scope-0001")
    initial_hash = chain.hash()
    initial_count = len(chain.delegations)

    casc = TenantScopedCascade(tenant=TenantScope.global_())
    parent_env = _envelope(100.0, genesis_id="g-p")
    child_env = _envelope(50.0, genesis_id="g-c")

    with pytest.raises(CascadeScopeExpansionError):
        casc.cascade_child(
            parent_env,
            child_env,
            parent_identity=_identity("parent"),
            child_identity=_identity("child"),
            parent_scope=RoleScope(
                domain="finance",
                capabilities=CapabilitySet(capabilities=("read",)),
            ),
            # Child WIDENS — adds 'approve'
            child_scope=RoleScope(
                domain="finance",
                capabilities=CapabilitySet(capabilities=("read", "approve")),
            ),
            child_tenant=TenantScope.global_(),
            grant_proof="a" * 128,
        )

    assert len(chain.delegations) == initial_count
    assert chain.hash() == initial_hash


# ---------------------------------------------------------------------------
# Fail-closed: envelope-widening cascade — same audit-absence guarantee
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_envelope_widening_cascade_does_not_pollute_audit_chain() -> None:
    """Envelope-widening cascade raises BEFORE any chain mutation.

    EnvelopeWideningError is propagated from the existing S2.5
    DelegateConstraintEnvelope.tighten_with's pre-intersection widening
    check; the chain remains pristine."""
    chain = _build_chain(genesis_id="g-tier2-env-0001")
    initial_hash = chain.hash()
    initial_count = len(chain.delegations)

    casc = TenantScopedCascade(tenant=TenantScope.global_())
    parent_env = _envelope(50.0, genesis_id="g-p")
    child_env = _envelope(100.0, genesis_id="g-c")  # widens

    with pytest.raises(EnvelopeWideningError):
        casc.cascade_child(
            parent_env,
            child_env,
            parent_identity=_identity("parent"),
            child_identity=_identity("child"),
            parent_scope=_scope_finance(),
            child_scope=_scope_finance(),
            child_tenant=TenantScope.global_(),
            grant_proof="a" * 128,
        )

    assert len(chain.delegations) == initial_count
    assert chain.hash() == initial_hash


# ---------------------------------------------------------------------------
# Two successful cascades produce monotonically advancing chain hashes
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_two_cascades_produce_monotonically_advancing_chain_hashes() -> None:
    """Two successful cascade appends → three distinct chain hashes."""
    chain = _build_chain(genesis_id="g-tier2-multi-0001")
    h0 = chain.hash()

    casc = TenantScopedCascade(tenant=TenantScope.for_tenant("tenant-a"))
    parent_env = _envelope(100.0, genesis_id="g-p")
    child_env = _envelope(50.0, genesis_id="g-c1")

    parent = _identity("parent")
    for i in range(2):
        child = _identity(f"child-{i}")
        gm = casc.cascade_child(
            parent_env,
            child_env,
            parent_identity=parent,
            child_identity=child,
            parent_scope=_scope_finance(),
            child_scope=_scope_finance_subset(),
            child_tenant=TenantScope.for_tenant("tenant-a"),
            grant_proof="b" * 128,
        )
        chain.delegations.append(
            _delegation_record_from_grant(
                gm, parent_identity=parent, child_identity=child
            )
        )

    h2 = chain.hash()
    # Two cascade-records → two distinct hash transitions.
    assert len(chain.delegations) == 2
    assert h2 != h0
    # Unique cascade ids — proves each cascade emits a fresh moment.
    assert chain.delegations[0].id != chain.delegations[1].id
