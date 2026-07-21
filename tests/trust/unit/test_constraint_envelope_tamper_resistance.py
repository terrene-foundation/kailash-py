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
