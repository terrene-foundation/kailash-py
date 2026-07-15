# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for issue #1710 — fail-closed pre-sign mint gate.

EATP-07 capability attestations and trust-lineage aggregates are signed,
portable artifacts: a relying party verifies the signature WITHOUT ever seeing
the underlying chain. If a mint reads the agent's chain via an un-verified,
expiry-blind path, a signed artifact can be produced from a *tampered* chain or
an *expired* grant and then trusted off-chain.

The fix couples every mint surface that reads a stored chain and signs a
portable record (``TrustOperations.delegate`` and ``TrustOperations.audit``) to
a single shared fail-closed gate (``_verify_source_chain_before_mint``) that,
BEFORE producing any signature:

  (a) requires a verifiable genesis issuer,
  (b) rejects an expired grant, and
  (c) verifies the chain's cryptographic integrity.

These tests cover each failure-mode class (a tampered / expired / genesis-less
chain → mint REFUSED, no artifact produced) plus the behaviour-invariance case
(a valid, unexpired, genesis-anchored chain still mints AND the artifact
verifies) — proving the change ONLY adds refusals.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from kailash.trust.authority import AuthorityPermission, OrganizationalAuthority
from kailash.trust.chain import (
    ActionResult,
    AuthorityType,
    CapabilityType,
    GenesisRecord,
)
from kailash.trust.chain_store.memory import InMemoryTrustStore
from kailash.trust.exceptions import (
    InvalidTrustChainError,
    TrustChainNotFoundError,
    TrustError,
)
from kailash.trust.execution_context import ExecutionContext, HumanOrigin
from kailash.trust.operations import (
    CapabilityRequest,
    TrustKeyManager,
    TrustOperations,
)
from kailash.trust.signing.crypto import generate_keypair

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Fixtures — a real authority, key manager, in-memory store, and operations
# instance (NO mocking — Tier 2 style, mirrors tests/trust/integration).
# ---------------------------------------------------------------------------


class _AuthorityRegistry:
    """Minimal real authority registry (not a mock — stores/retrieves)."""

    def __init__(self) -> None:
        self._authorities: dict = {}

    def register(self, authority: OrganizationalAuthority) -> None:
        self._authorities[authority.id] = authority

    async def initialize(self) -> None:  # pragma: no cover - trivial
        return None

    async def get_authority(
        self, authority_id: str, include_inactive: bool = False
    ) -> OrganizationalAuthority:
        from kailash.trust.exceptions import AuthorityNotFoundError

        if authority_id not in self._authorities:
            raise AuthorityNotFoundError(authority_id)
        return self._authorities[authority_id]


@pytest.fixture
def keypair():
    return generate_keypair()


@pytest.fixture
def authority(keypair):
    _, public_key = keypair
    return OrganizationalAuthority(
        id="org-acme",
        name="ACME Corporation",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id="acme-key-001",
        permissions=[
            AuthorityPermission.CREATE_AGENTS,
            AuthorityPermission.DELEGATE_TRUST,
            AuthorityPermission.GRANT_CAPABILITIES,
        ],
    )


@pytest.fixture
def registry(authority):
    reg = _AuthorityRegistry()
    reg.register(authority)
    return reg


@pytest.fixture
def key_manager(keypair):
    private_key, _ = keypair
    km = TrustKeyManager()
    km.register_key("acme-key-001", private_key)
    return km


@pytest.fixture
async def store():
    s = InMemoryTrustStore()
    await s.initialize()
    return s


@pytest.fixture
async def ops(registry, key_manager, store):
    operations = TrustOperations(
        authority_registry=registry,
        key_manager=key_manager,
        trust_store=store,
    )
    await operations.initialize()
    return operations


@pytest.fixture
def execution_ctx():
    return ExecutionContext(
        human_origin=HumanOrigin(
            human_id="alice@acme.com",
            display_name="Alice Chen",
            auth_provider="okta",
            session_id="sess-1710",
            authenticated_at=datetime.now(timezone.utc),
        ),
        delegation_chain=["pseudo:alice@acme.com"],
        delegation_depth=0,
    )


async def _establish(ops, agent_id="agent-001", expires_at=None):
    return await ops.establish(
        agent_id=agent_id,
        authority_id="org-acme",
        capabilities=[
            CapabilityRequest(
                capability="analyze_data",
                capability_type=CapabilityType.ACTION,
            )
        ],
        expires_at=expires_at,
    )


# ---------------------------------------------------------------------------
# (d) Behaviour-invariance: a valid, unexpired, genesis-anchored chain still
# mints AND the produced signature verifies. Proves the change ONLY adds
# refusals for bad chains — good chains are byte-identical.
# ---------------------------------------------------------------------------


class TestBehaviourInvariantOnValidChain:
    async def test_delegate_valid_chain_still_mints_and_verifies(
        self, ops, execution_ctx
    ):
        await _establish(ops)
        delegation = await ops.delegate(
            delegator_id="agent-001",
            delegatee_id="agent-002",
            task_id="task-1",
            capabilities=["analyze_data"],
            context=execution_ctx,
        )
        # Minted successfully with a real signature.
        assert delegation.signature != ""
        # The derived delegatee chain verifies end-to-end (integrity preserved).
        result = await ops.verify(agent_id="agent-002", action="analyze_data")
        assert result.valid is True

    async def test_audit_valid_chain_still_mints_and_signs(self, ops, execution_ctx):
        await _establish(ops)
        anchor = await ops.audit(
            agent_id="agent-001",
            action="analyze_data",
            resource="finance_db",
            result=ActionResult.SUCCESS,
            context=execution_ctx,
        )
        assert anchor.signature != ""
        assert anchor.trust_chain_hash != ""

    async def test_delegate_signature_is_deterministic_pre_and_post_gate(
        self, ops, execution_ctx
    ):
        """The gate is a pure pre-check: a valid chain produces the exact same
        signing payload it did before the gate existed (no new fields, no
        mutation of the source chain)."""
        chain = await _establish(ops)
        genesis_sig_before = chain.genesis.signature
        cap_sig_before = chain.capabilities[0].signature
        await ops.delegate(
            delegator_id="agent-001",
            delegatee_id="agent-002",
            task_id="task-1",
            capabilities=["analyze_data"],
            context=execution_ctx,
        )
        # The gate MUST NOT have mutated the source chain's signatures.
        reloaded = await ops.trust_store.get_chain("agent-001")
        assert reloaded.genesis.signature == genesis_sig_before
        assert reloaded.capabilities[0].signature == cap_sig_before


# ---------------------------------------------------------------------------
# (a) Tampered chain (signature-invalid) → mint REFUSED, no artifact produced.
# ---------------------------------------------------------------------------


class TestTamperedChainRefused:
    async def test_delegate_refused_on_tampered_genesis_signature(
        self, ops, execution_ctx
    ):
        await _establish(ops)
        # Tamper: corrupt the stored genesis signature.
        chain = await ops.trust_store.get_chain("agent-001")
        chain.genesis.signature = "deadbeef" * 8  # invalid signature bytes
        await ops.trust_store.update_chain("agent-001", chain)

        with pytest.raises(InvalidTrustChainError) as exc:
            await ops.delegate(
                delegator_id="agent-001",
                delegatee_id="agent-002",
                task_id="task-1",
                capabilities=["analyze_data"],
                context=execution_ctx,
            )
        assert "integrity" in str(exc.value).lower()
        assert isinstance(exc.value, TrustError)
        # Fail-closed BEFORE signing: no delegatee chain was ever created.
        with pytest.raises(TrustChainNotFoundError):
            await ops.trust_store.get_chain("agent-002")

    async def test_audit_refused_on_tampered_capability_signature(
        self, ops, execution_ctx
    ):
        await _establish(ops)
        chain = await ops.trust_store.get_chain("agent-001")
        chain.capabilities[0].signature = "00" * 64  # invalid signature bytes
        await ops.trust_store.update_chain("agent-001", chain)

        chain_after = await ops.trust_store.get_chain("agent-001")
        anchors_before = len(chain_after.audit_anchors)

        with pytest.raises(InvalidTrustChainError):
            await ops.audit(
                agent_id="agent-001",
                action="analyze_data",
                result=ActionResult.SUCCESS,
                context=execution_ctx,
            )
        # Fail-closed BEFORE signing: no audit anchor was appended.
        reloaded = await ops.trust_store.get_chain("agent-001")
        assert len(reloaded.audit_anchors) == anchors_before


# ---------------------------------------------------------------------------
# (b) Expired grant → mint REFUSED.
# ---------------------------------------------------------------------------


class TestExpiredChainRefused:
    async def test_delegate_refused_on_expired_grant(self, ops, execution_ctx):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        await _establish(ops, expires_at=past)

        with pytest.raises(InvalidTrustChainError) as exc:
            await ops.delegate(
                delegator_id="agent-001",
                delegatee_id="agent-002",
                task_id="task-1",
                capabilities=["analyze_data"],
                context=execution_ctx,
            )
        assert "expired" in str(exc.value).lower()
        with pytest.raises(TrustChainNotFoundError):
            await ops.trust_store.get_chain("agent-002")

    async def test_audit_refused_on_expired_grant(self, ops, execution_ctx):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        chain = await _establish(ops, expires_at=past)
        anchors_before = len(chain.audit_anchors)

        with pytest.raises(InvalidTrustChainError) as exc:
            await ops.audit(
                agent_id="agent-001",
                action="analyze_data",
                result=ActionResult.SUCCESS,
                context=execution_ctx,
            )
        assert "expired" in str(exc.value).lower()
        reloaded = await ops.trust_store.get_chain("agent-001")
        assert len(reloaded.audit_anchors) == anchors_before


# ---------------------------------------------------------------------------
# (c) Genesis-less / no-issuer chain → mint REFUSED.
# ---------------------------------------------------------------------------


class TestGenesisLessChainRefused:
    async def test_delegate_refused_on_missing_genesis_issuer(self, ops, execution_ctx):
        await _establish(ops)
        chain = await ops.trust_store.get_chain("agent-001")
        # Strip the genesis issuer (authority_id) — no verifiable issuer.
        chain.genesis.authority_id = ""
        await ops.trust_store.update_chain("agent-001", chain)

        with pytest.raises(InvalidTrustChainError) as exc:
            await ops.delegate(
                delegator_id="agent-001",
                delegatee_id="agent-002",
                task_id="task-1",
                capabilities=["analyze_data"],
                context=execution_ctx,
            )
        assert "genesis" in str(exc.value).lower()
        with pytest.raises(TrustChainNotFoundError):
            await ops.trust_store.get_chain("agent-002")

    async def test_audit_refused_when_genesis_authority_unresolvable(
        self, ops, execution_ctx
    ):
        """A genesis naming an authority that does not exist in the registry has
        no verifiable issuer — the integrity verifier's authority resolution
        fails closed as a missing-issuer refusal, not an opaque crash."""
        await _establish(ops)
        chain = await ops.trust_store.get_chain("agent-001")
        chain.genesis.authority_id = "org-does-not-exist"
        await ops.trust_store.update_chain("agent-001", chain)

        with pytest.raises(InvalidTrustChainError) as exc:
            await ops.audit(
                agent_id="agent-001",
                action="analyze_data",
                result=ActionResult.SUCCESS,
                context=execution_ctx,
            )
        assert "genesis" in str(exc.value).lower() or "issuer" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# Structural: both mint surfaces route through the ONE shared helper (parity).
# ---------------------------------------------------------------------------


def test_mint_surfaces_share_a_single_fail_closed_helper():
    """Enforcement-Surface Parity: delegate() and audit() MUST both call the
    single shared pre-sign gate so the two surfaces cannot drift."""
    import inspect

    src = inspect.getsource(TrustOperations)
    assert src.count("_verify_source_chain_before_mint(") >= 3  # def + 2 calls

    delegate_src = inspect.getsource(TrustOperations.delegate)
    audit_src = inspect.getsource(TrustOperations.audit)
    assert "_verify_source_chain_before_mint" in delegate_src
    assert "_verify_source_chain_before_mint" in audit_src
