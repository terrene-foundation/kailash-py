"""Regression test for issue #1695 — default (STANDARD) verification MUST reject
a tampered *stored* capability grant.

Threat model: an actor with write access to the persisted trust chain mutates a
granted capability's CONTENT (e.g. ``read_data`` -> ``delete_data``, or loosens
its ``constraints``) while preserving the capability ``id`` — so the id-only
chain-state hash is unaffected. Before the fix, the shipped default
``VerificationLevel.STANDARD`` authorized the tampered grant because the
per-attestation Ed25519 signature that covers the grant content was verified
ONLY at ``VerificationLevel.FULL``. Every enforcement surface defaults to
STANDARD, so the tamper was authorized.

The fix (``TrustOperations._verify_capability_signature`` called from ``verify``
at STANDARD) verifies the matched capability's content signature at the default
level. These behavioral tests establish a signed grant, tamper the stored
content while preserving the id + signature, and assert the default ``verify()``
DENIES — and that a legitimate (untampered) grant still verifies.

Security-critical path (100% coverage tier per rules/testing.md); real
InMemoryTrustStore, no mocking.
"""

from __future__ import annotations

from typing import Dict

import pytest

from kailash.trust.authority import AuthorityPermission, OrganizationalAuthority
from kailash.trust.chain import AuthorityType, CapabilityType, VerificationLevel
from kailash.trust.chain_store.memory import InMemoryTrustStore
from kailash.trust.operations import CapabilityRequest, TrustKeyManager, TrustOperations
from kailash.trust.signing.crypto import generate_keypair


class _SimpleAuthorityRegistry:
    """Real in-memory authority registry (NOT a mock) — mirrors the lifecycle
    integration harness's registry so this regression is self-contained."""

    def __init__(self) -> None:
        self._authorities: Dict[str, OrganizationalAuthority] = {}

    async def initialize(self) -> None:  # no-op for in-memory
        pass

    def register(self, authority: OrganizationalAuthority) -> None:
        self._authorities[authority.id] = authority

    async def get_authority(
        self, authority_id: str, include_inactive: bool = False
    ) -> OrganizationalAuthority:
        authority = self._authorities.get(authority_id)
        if authority is None:
            from kailash.trust.exceptions import AuthorityNotFoundError

            raise AuthorityNotFoundError(authority_id)
        return authority


@pytest.fixture
def _keypair():
    return generate_keypair()


@pytest.fixture
def _registry(_keypair):
    _, public_key = _keypair
    authority = OrganizationalAuthority(
        id="org-acme",
        name="ACME Corporation",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id="acme-key-001",
        permissions=[
            AuthorityPermission.CREATE_AGENTS,
            AuthorityPermission.GRANT_CAPABILITIES,
        ],
    )
    reg = _SimpleAuthorityRegistry()
    reg.register(authority)
    return reg


@pytest.fixture
def _key_manager(_keypair):
    private_key, _ = _keypair
    km = TrustKeyManager()
    km.register_key("acme-key-001", private_key)
    return km


@pytest.fixture
async def _store():
    store = InMemoryTrustStore()
    await store.initialize()
    return store


@pytest.fixture
async def ops(_registry, _key_manager, _store):
    operations = TrustOperations(
        authority_registry=_registry,
        key_manager=_key_manager,
        trust_store=_store,
    )
    await operations.initialize()
    return operations


@pytest.mark.regression
async def test_default_verify_denies_tampered_capability_action(ops, _store):
    """read_data -> delete_data content tamper (id preserved) is DENIED at the
    shipped default level; the legitimate grant still verifies."""
    await ops.establish(
        agent_id="agent-1695",
        authority_id="org-acme",
        capabilities=[
            CapabilityRequest(
                capability="read_data",
                capability_type=CapabilityType.ACTION,
            ),
        ],
    )

    # Control: the legitimate action verifies at the DEFAULT (STANDARD) level.
    control = await ops.verify(agent_id="agent-1695", action="read_data")
    assert control.valid is True, "untampered grant must verify at default level"

    # Tamper the STORED grant content: read_data -> delete_data, id + signature
    # preserved (simulating an actor that rewrote the persisted chain).
    chain = await _store.get_chain("agent-1695")
    cap = chain.capabilities[0]
    original_id, original_sig = cap.id, cap.signature
    cap.capability = "delete_data"
    assert cap.id == original_id and cap.signature == original_sig
    await _store.update_chain("agent-1695", chain)

    # Default (STANDARD) verification of the tampered action MUST deny.
    result = await ops.verify(agent_id="agent-1695", action="delete_data")
    assert result.valid is False, (
        "default verify() must DENY a tampered stored grant (#1695) — "
        "the content signature is invalid"
    )
    assert "signature" in (result.reason or "").lower()

    # FULL level denies too (consistency across levels).
    result_full = await ops.verify(
        agent_id="agent-1695",
        action="delete_data",
        level=VerificationLevel.FULL,
    )
    assert result_full.valid is False


@pytest.mark.regression
async def test_default_verify_denies_loosened_capability_constraints(ops, _store):
    """Loosening a matched grant's ``constraints`` (id + capability preserved)
    is also DENIED at the default level — the signature covers constraints too."""
    await ops.establish(
        agent_id="agent-1695b",
        authority_id="org-acme",
        capabilities=[
            CapabilityRequest(
                capability="read_data",
                capability_type=CapabilityType.ACTION,
                constraints=["scope:own_tenant"],
            ),
        ],
    )

    control = await ops.verify(agent_id="agent-1695b", action="read_data")
    assert control.valid is True

    # Tamper: strip the constraints (widen the grant), keep id + capability.
    chain = await _store.get_chain("agent-1695b")
    cap = chain.capabilities[0]
    cap.constraints = []
    await _store.update_chain("agent-1695b", chain)

    result = await ops.verify(agent_id="agent-1695b", action="read_data")
    assert result.valid is False, (
        "default verify() must DENY a grant whose constraints were loosened "
        "in storage (#1695)"
    )
    assert "signature" in (result.reason or "").lower()


@pytest.mark.regression
async def test_default_verify_fails_closed_on_malformed_signature(ops, _store):
    """A tampered grant carrying a malformed/empty signature makes the crypto
    layer RAISE (InvalidSignatureError) rather than return False; the default
    verify() MUST still fail closed with a clean denial, not propagate the raise
    (security-reviewer MEDIUM on the #1695 fix)."""
    await ops.establish(
        agent_id="agent-1695c",
        authority_id="org-acme",
        capabilities=[
            CapabilityRequest(
                capability="read_data",
                capability_type=CapabilityType.ACTION,
            ),
        ],
    )

    # Tamper: replace the signature with an empty string (malformed).
    chain = await _store.get_chain("agent-1695c")
    chain.capabilities[0].signature = ""
    await _store.update_chain("agent-1695c", chain)

    # MUST NOT raise; MUST return a clean fail-closed denial.
    result = await ops.verify(agent_id="agent-1695c", action="read_data")
    assert result.valid is False
    assert "signature" in (result.reason or "").lower()


@pytest.mark.regression
async def test_mcp_ops_less_verify_fails_closed(ops, _store):
    """The MCP store-only path (EATPMCPServer without TrustOperations) cannot
    verify capability signatures, so it MUST fail closed on a name-matched
    capability rather than authorize an unverifiable/tampered grant
    (security-reviewer HIGH on the #1695 fix)."""
    from kailash.trust.mcp.server import EATPMCPServer

    # Establish a real, correctly-signed chain into the shared store.
    await ops.establish(
        agent_id="agent-1695d",
        authority_id="org-acme",
        capabilities=[
            CapabilityRequest(
                capability="read_data",
                capability_type=CapabilityType.ACTION,
            ),
        ],
    )

    # An ops-less MCP server over the SAME store (the documented default
    # EATPMCPServer(trust_store=...) construction).
    server = EATPMCPServer(trust_store=_store, trust_ops=None)

    # Even a genuine, correctly-signed grant is NOT authorized here — the path
    # cannot verify the signature, so it fails closed.
    result = await server._verify_from_store("agent-1695d", "read_data", None)
    assert result.valid is False, (
        "ops-less MCP verify must fail closed — it cannot verify capability "
        "signatures (#1695)"
    )
    assert "TrustOperations" in (result.reason or "")

    # Sanity: the SAME grant verifies True through a fully-configured ops.
    ok = await ops.verify(agent_id="agent-1695d", action="read_data")
    assert ok.valid is True
