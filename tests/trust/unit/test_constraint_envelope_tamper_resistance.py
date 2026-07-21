# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tamper-resistance regression: constraint ENFORCEMENT re-derives the enforced
set from SIGNED capability/genesis sources, so a store-writer cannot strip an
enforced constraint from the persisted (UNSIGNED) constraint_envelope to
escalate privilege.

Threat model: a legitimate team member with write access to the trust store
(the bounded-trust store-writer #1842 defends against) edits a persisted chain
to weaken its enforced constraints. Before the fix, verify() enforced on the
persisted envelope verbatim; after, verify() re-derives the enforced set from
the signed sources and ignores the tampered cache.

Covers the PRIMARY vector this fix closes (envelope active_constraints strip +
whole-envelope null). NOTE (documented residuals for the envelope-signing
follow-up): a store-writer stripping a constraint from a NON-matched
capability's own `constraints` list, and directly-injected non-capability
access constraints, are sibling vectors not fully closed here — see the fix's
verify() comment + the security write-up.
"""

import pytest

from kailash.trust.authority import AuthorityPermission, OrganizationalAuthority
from kailash.trust.chain import AuthorityType, CapabilityType
from kailash.trust.chain_store.memory import InMemoryTrustStore
from kailash.trust.exceptions import AuthorityInactiveError, AuthorityNotFoundError
from kailash.trust.operations import (
    CapabilityRequest,
    TrustKeyManager,
    TrustOperations,
)
from kailash.trust.signing.crypto import generate_keypair


class _Registry:
    """Minimal real authority registry (no mocks)."""

    def __init__(self):
        self._a = {}

    async def initialize(self):
        return None

    def register(self, a):
        self._a[a.id] = a

    async def get_authority(self, authority_id, include_inactive=False):
        a = self._a.get(authority_id)
        if a is None:
            raise AuthorityNotFoundError(authority_id)
        if not a.is_active and not include_inactive:
            raise AuthorityInactiveError(authority_id)
        return a

    async def update_authority(self, a):
        self._a[a.id] = a


@pytest.fixture
def keypair():
    return generate_keypair()


@pytest.fixture
def registry(keypair):
    _, public_key = keypair
    reg = _Registry()
    reg.register(
        OrganizationalAuthority(
            id="org-test",
            name="Test Corp",
            authority_type=AuthorityType.ORGANIZATION,
            public_key=public_key,
            signing_key_id="test-key-001",
            permissions=[
                AuthorityPermission.CREATE_AGENTS,
                AuthorityPermission.DELEGATE_TRUST,
                AuthorityPermission.GRANT_CAPABILITIES,
            ],
        )
    )
    return reg


@pytest.fixture
def key_manager(keypair):
    private_key, _ = keypair
    km = TrustKeyManager()
    km.register_key("test-key-001", private_key)
    return km


@pytest.fixture
async def store():
    s = InMemoryTrustStore()
    await s.initialize()
    return s


@pytest.fixture
async def ops(registry, key_manager, store):
    o = TrustOperations(
        authority_registry=registry,
        key_manager=key_manager,
        trust_store=store,
    )
    await o.initialize()
    return o


async def _establish_read_only(ops):
    """Agent with SIGNED capabilities carrying a read_only constraint."""
    return await ops.establish(
        agent_id="agent-tamper",
        authority_id="org-test",
        capabilities=[
            CapabilityRequest(
                capability="write_records",
                capability_type=CapabilityType.ACTION,
            ),
            CapabilityRequest(
                capability="read_records",
                capability_type=CapabilityType.ACTION,
            ),
        ],
        constraints=["read_only"],
    )


def _denied_by_read_only(result) -> bool:
    return result.valid is False and any(
        "read_only" in str(v).lower() for v in (result.violations or [])
    )


@pytest.mark.asyncio
async def test_baseline_read_only_denies_write(ops):
    await _establish_read_only(ops)
    result = await ops.verify(agent_id="agent-tamper", action="write_records")
    assert _denied_by_read_only(result)


@pytest.mark.asyncio
async def test_tamper_strip_envelope_constraint_still_denied(ops, store):
    """PRIMARY vector: strip read_only from the persisted (unsigned) envelope.

    verify() re-derives read_only from the SIGNED capability, so the strip is
    ignored and the write stays denied.
    """
    await _establish_read_only(ops)

    chain = await store.get_chain("agent-tamper")
    chain.constraint_envelope.active_constraints = [
        c
        for c in chain.constraint_envelope.active_constraints
        if str(c.value).lower() != "read_only"
    ]
    await store.store_chain(chain)

    result = await ops.verify(agent_id="agent-tamper", action="write_records")
    assert result.valid is False, "stripped envelope constraint must NOT escalate"


@pytest.mark.asyncio
async def test_tamper_null_whole_envelope_still_denied(ops, store):
    """PRIMARY vector: null the whole persisted envelope.

    verify() re-derives from the signed capability, so nulling the cache does
    not drop the enforced constraint.
    """
    await _establish_read_only(ops)

    chain = await store.get_chain("agent-tamper")
    chain.constraint_envelope = None
    await store.store_chain(chain)

    result = await ops.verify(agent_id="agent-tamper", action="write_records")
    assert result.valid is False, "nulled envelope must NOT escalate"


@pytest.mark.asyncio
async def test_tamper_strip_nonmatched_capability_constraint_caught(ops, store):
    """SIBLING vector: strip read_only from a NON-matched capability.

    The tampered capability's signature covered its constraints, so stripping
    read_only invalidates it. Because the enforced-set derivation verifies
    EVERY capability's signature (not only constraint-carrying ones), the
    tamper is caught fail-closed rather than silently dropping the constraint.
    """
    await _establish_read_only(ops)

    chain = await store.get_chain("agent-tamper")
    for cap in chain.capabilities:
        if cap.capability == "read_records":  # not the cap the write action matches
            cap.constraints = [c for c in cap.constraints if c != "read_only"]
    await store.store_chain(chain)

    result = await ops.verify(agent_id="agent-tamper", action="write_records")
    assert result.valid is False, "tampered sibling capability must NOT escalate"


@pytest.mark.asyncio
async def test_untampered_read_action_permitted(ops):
    """Control: a read action under read_only is permitted (no false denial)."""
    await _establish_read_only(ops)
    result = await ops.verify(agent_id="agent-tamper", action="read_records")
    assert result.valid is True


@pytest.mark.asyncio
async def test_tamper_strip_genesis_constraint_still_denied(ops, store):
    """GENESIS vector: strip a read_only carried at the GENESIS level.

    The genesis signature covers the whole ``metadata`` dict, and the enforced-
    set derivation verifies the genesis signature UNCONDITIONALLY (not only when
    ``metadata['constraints']`` is currently non-empty). So a store-writer who
    sets ``genesis.metadata['constraints'] = []`` — which both strips the
    constraint AND invalidates the genesis signature — is caught fail-closed
    rather than silently dropping the constraint.
    """
    await ops.establish(
        agent_id="agent-gtamper",
        authority_id="org-test",
        capabilities=[
            CapabilityRequest(
                capability="write_records", capability_type=CapabilityType.ACTION
            )
        ],
        metadata={"constraints": ["read_only"]},  # genesis-level constraint
    )
    base = await ops.verify(agent_id="agent-gtamper", action="write_records")
    assert base.valid is False, "genesis read_only should deny the write"

    chain = await store.get_chain("agent-gtamper")
    chain.genesis.metadata["constraints"] = []  # strip (also breaks genesis sig)
    if chain.constraint_envelope is not None:
        chain.constraint_envelope.active_constraints = []
    await store.store_chain(chain)

    result = await ops.verify(agent_id="agent-gtamper", action="write_records")
    assert result.valid is False, "genesis-constraint strip must NOT escalate"


@pytest.mark.asyncio
async def test_cross_authority_delegation_not_falsely_denied():
    """Regression: a delegatee established under authority D, delegated into by a
    delegator under a DIFFERENT authority G, must NOT be falsely denied.

    The derived capability is signed by G's key; verifying every capability
    against D (the delegatee chain's genesis authority) would wrongly reject the
    legitimately-G-signed cap and deny every action. The fix resolves each
    capability's signing authority per its own ``attester_id``.
    """
    priv_g, pub_g = generate_keypair()
    priv_d, pub_d = generate_keypair()
    km = TrustKeyManager()
    km.register_key("key-g", priv_g)
    km.register_key("key-d", priv_d)
    reg = _Registry()
    for aid, key, pub in (("auth-g", "key-g", pub_g), ("auth-d", "key-d", pub_d)):
        reg.register(
            OrganizationalAuthority(
                id=aid,
                name=aid,
                authority_type=AuthorityType.ORGANIZATION,
                public_key=pub,
                signing_key_id=key,
                permissions=[
                    AuthorityPermission.CREATE_AGENTS,
                    AuthorityPermission.DELEGATE_TRUST,
                    AuthorityPermission.GRANT_CAPABILITIES,
                ],
            )
        )
    s = InMemoryTrustStore()
    await s.initialize()
    ops = TrustOperations(authority_registry=reg, key_manager=km, trust_store=s)
    await ops.initialize()

    await ops.establish(
        agent_id="agent-d",
        authority_id="auth-d",
        capabilities=[
            CapabilityRequest(
                capability="read_records", capability_type=CapabilityType.ACTION
            )
        ],
    )
    await ops.establish(
        agent_id="delegator-g",
        authority_id="auth-g",
        capabilities=[
            CapabilityRequest(
                capability="write_records", capability_type=CapabilityType.ACTION
            )
        ],
    )
    base = await ops.verify(agent_id="agent-d", action="read_records")
    assert base.valid is True, "agent-d should verify before the cross-auth delegation"

    await ops.delegate(
        delegator_id="delegator-g",
        delegatee_id="agent-d",
        task_id="t1",
        capabilities=["write_records"],
    )

    result = await ops.verify(agent_id="agent-d", action="read_records")
    assert result.valid is True, "cross-authority delegation must NOT falsely deny"
