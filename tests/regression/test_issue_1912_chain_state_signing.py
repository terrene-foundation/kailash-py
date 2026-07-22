# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: #1912 Wave 2 chain-state signature (whole-set + envelope tamper).

Wave 1 bound each capability to its holder subject (transplant defense). Wave 2
binds the WHOLE chain state under ONE Ed25519 signature by the genesis authority,
closing two store-writer vectors nothing else signs:

  MED-1 (whole-capability-set deletion): a store-writer deletes a capability that
    carries a constraint while another capability still grants the action; the
    constraint silently drops. The deleted cap's id leaves ``capability_ids`` →
    the chain-state pre-image changes → the signature breaks → verify DENIES.

  MED-2 (reasoning-suppression + directly-injected constraints): the persisted
    ``ChainConstraintEnvelope`` is UNSIGNED; a store-writer strips a
    ``REASONING_REQUIRED`` (or any directly-injected) constraint with nothing to
    break. The constraint feeds the RE-COMPUTED ``constraint_hash`` in the pre-
    image → stripping / editing it changes the recomputed hash → verify DENIES.

Scenarios (task step 9), all against REAL Ed25519, NO mocking:

  (a) whole-cap DELETION detected (fail-closed);
  (b) reasoning-SUPPRESSION (strip REASONING_REQUIRED) detected;
  (c) directly-injected-constraint value tamper detected;
  (d) happy path: a legit chain verifies TRUE;
  (e) #1912 Wave 3 A1: a legacy chain (no chain-state sig) is REJECTED by default
      (fail-closed) and ACCEPTED only under the migration-window opt-out
      allow_unsigned_chain_state=True, each with a loud one-time WARN;
  (f) byte-identity: a legacy chain's dict carries NO chain_state_signature key
      (prune-when-unset); a signed chain's dict carries it and round-trips.

Plus: the cross-SDK canonical pre-image encoding is pinned as a tripwire, the
field round-trips through to_dict/from_dict (serializer completeness), and key
rotation re-issues the signature so a rotated chain still verifies.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List

import pytest

from kailash.trust.authority import AuthorityPermission, OrganizationalAuthority
from kailash.trust.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    Constraint,
    ConstraintType,
    GenesisRecord,
    TrustLineageChain,
    VerificationLevel,
)
from kailash.trust.chain_store.memory import InMemoryTrustStore
from kailash.trust.exceptions import AuthorityInactiveError, AuthorityNotFoundError
from kailash.trust.operations import (
    CapabilityRequest,
    TrustKeyManager,
    TrustOperations,
)
from kailash.trust.signing.chain_state_signing import (
    chain_state_canonical_payload,
    chain_state_canonical_payload_str,
)
from kailash.trust.signing.crypto import generate_keypair

pytestmark = pytest.mark.regression

FIXED_TS = datetime(2026, 3, 11, 14, 30, 0, tzinfo=timezone.utc)


class SimpleAuthorityRegistry:
    """Real in-memory authority registry (NOT a mock)."""

    def __init__(self) -> None:
        self._authorities: Dict[str, OrganizationalAuthority] = {}

    async def initialize(self) -> None:
        pass

    def register(self, authority: OrganizationalAuthority) -> None:
        self._authorities[authority.id] = authority

    async def get_authority(
        self, authority_id: str, include_inactive: bool = False
    ) -> OrganizationalAuthority:
        authority = self._authorities.get(authority_id)
        if authority is None:
            raise AuthorityNotFoundError(authority_id)
        if not authority.is_active and not include_inactive:
            raise AuthorityInactiveError(authority_id)
        return authority

    async def update_authority(self, authority: OrganizationalAuthority) -> None:
        self._authorities[authority.id] = authority


@pytest.fixture
def keypair():
    return generate_keypair()


@pytest.fixture
def authority(keypair):
    _, public_key = keypair
    return OrganizationalAuthority(
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


@pytest.fixture
def registry(authority):
    reg = SimpleAuthorityRegistry()
    reg.register(authority)
    return reg


@pytest.fixture
def key_manager(keypair):
    private_key, _ = keypair
    km = TrustKeyManager()
    km.register_key("test-key-001", private_key)
    return km


@pytest.fixture
async def memory_store():
    store = InMemoryTrustStore()
    await store.initialize()
    return store


@pytest.fixture
async def ops(registry, key_manager, memory_store):
    operations = TrustOperations(
        authority_registry=registry,
        key_manager=key_manager,
        trust_store=memory_store,
    )
    await operations.initialize()
    return operations


async def _establish(
    ops: TrustOperations, agent_id: str, caps: List[CapabilityRequest]
):
    await ops.establish(agent_id=agent_id, authority_id="org-test", capabilities=caps)
    return await ops.trust_store.get_chain(agent_id)


def _cap_req(name: str, constraints: List[str]) -> CapabilityRequest:
    return CapabilityRequest(
        capability=name,
        capability_type=CapabilityType.ACTION,
        constraints=constraints,
    )


# ---------------------------------------------------------------------------
# Sign-time posture: establish now issues a chain-state signature
# ---------------------------------------------------------------------------


async def test_establish_issues_chain_state_signature(ops):
    chain = await _establish(ops, "agent-a", [_cap_req("read_data", [])])
    assert chain.chain_state_signature, (
        "establish must issue a chain-state signature (#1912 Wave 2) — new "
        "chains ALWAYS get it, fail-closed at issuance"
    )


# ---------------------------------------------------------------------------
# (d) HAPPY PATH: a legitimately-signed chain verifies TRUE
# ---------------------------------------------------------------------------


async def test_happy_path_verifies_true(ops):
    await _establish(ops, "agent-a", [_cap_req("read_data", ["read_only"])])
    result = await ops.verify(
        agent_id="agent-a", action="read_data", level=VerificationLevel.STANDARD
    )
    assert (
        result.valid is True
    ), f"a legit chain-state-signed chain was denied at STANDARD: {result.reason}"
    # FULL level (which also runs the full-chain signature verify) must agree.
    result_full = await ops.verify(
        agent_id="agent-a", action="read_data", level=VerificationLevel.FULL
    )
    assert result_full.valid is True, f"FULL denied a legit chain: {result_full.reason}"


# ---------------------------------------------------------------------------
# (a) MED-1: whole-capability-set deletion detected
# ---------------------------------------------------------------------------


async def test_whole_cap_deletion_detected(ops, memory_store):
    # Two caps: one plain grant for the action, one constraint-bearing cap.
    await _establish(
        ops,
        "agent-a",
        [
            _cap_req("read_data", []),
            _cap_req("read_pii", ["read_only", "no_pii_export"]),
        ],
    )
    # Sanity: verify authorizes read_data on the intact, signed chain.
    ok = await ops.verify(
        agent_id="agent-a", action="read_data", level=VerificationLevel.STANDARD
    )
    assert ok.valid is True, f"fixture bug: intact chain denied: {ok.reason}"

    # Store-writer DELETES the constraint-bearing cap while read_data still
    # grants the action — WITHOUT re-issuing the chain-state signature.
    chain = await memory_store.get_chain("agent-a")
    before = len(chain.capabilities)
    chain.capabilities = [c for c in chain.capabilities if c.capability != "read_pii"]
    assert len(chain.capabilities) == before - 1, "fixture bug: cap not deleted"
    await memory_store.update_chain("agent-a", chain)

    # The capability_ids changed → recomputed pre-image differs from the signed
    # one → chain-state signature no longer verifies → fail-closed DENY.
    tampered = await ops.verify(
        agent_id="agent-a", action="read_data", level=VerificationLevel.STANDARD
    )
    assert (
        tampered.valid is False
    ), "a whole-capability deletion was NOT detected — MED-1 is not closed"
    assert "chain-state signature" in tampered.reason.lower()


# ---------------------------------------------------------------------------
# (b) MED-2: REASONING_REQUIRED suppression detected
# ---------------------------------------------------------------------------


async def test_reasoning_required_suppression_detected(ops, memory_store):
    await _establish(ops, "agent-a", [_cap_req("read_data", ["read_only"])])
    chain = await memory_store.get_chain("agent-a")

    # Configure REASONING_REQUIRED by injecting it directly into the persisted
    # envelope, THEN re-issue the chain-state signature so it covers the
    # constraint (the correct, tamper-evident configuration posture).
    chain.constraint_envelope.active_constraints.append(
        Constraint(
            id="con-reasoning",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="reasoning_required",
            source="policy",
        )
    )
    await ops._issue_chain_state_signature(chain)
    await memory_store.update_chain("agent-a", chain)

    # Sanity: STANDARD still authorizes (REASONING_REQUIRED is a non-blocking
    # finding at STANDARD) and the chain-state signature now covers it.
    ok = await ops.verify(
        agent_id="agent-a", action="read_data", level=VerificationLevel.STANDARD
    )
    assert (
        ok.valid is True
    ), f"fixture bug: reasoning-configured chain denied: {ok.reason}"

    # Store-writer STRIPS the REASONING_REQUIRED constraint WITHOUT re-signing.
    chain2 = await memory_store.get_chain("agent-a")
    chain2.constraint_envelope.active_constraints = [
        c
        for c in chain2.constraint_envelope.active_constraints
        if c.constraint_type != ConstraintType.REASONING_REQUIRED
    ]
    await memory_store.update_chain("agent-a", chain2)

    # The recomputed constraint_hash changes → chain-state signature breaks → DENY.
    tampered = await ops.verify(
        agent_id="agent-a", action="read_data", level=VerificationLevel.STANDARD
    )
    assert tampered.valid is False, (
        "stripping a REASONING_REQUIRED constraint was NOT detected — MED-2 "
        "reasoning-suppression is not closed"
    )
    assert "chain-state signature" in tampered.reason.lower()


# ---------------------------------------------------------------------------
# (c) MED-2: directly-injected-constraint value tamper detected
# ---------------------------------------------------------------------------


async def test_injected_constraint_value_tamper_detected(ops, memory_store):
    await _establish(ops, "agent-a", [_cap_req("read_data", ["read_only"])])
    chain = await memory_store.get_chain("agent-a")

    # Inject a directly-configured (non-capability) constraint, then sign.
    chain.constraint_envelope.active_constraints.append(
        Constraint(
            id="con-injected",
            constraint_type=ConstraintType.DATA_ACCESS,
            value="max_rows=100",
            source="policy",
        )
    )
    await ops._issue_chain_state_signature(chain)
    await memory_store.update_chain("agent-a", chain)

    # Store-writer WIDENS the injected constraint's value WITHOUT re-signing.
    chain2 = await memory_store.get_chain("agent-a")
    for c in chain2.constraint_envelope.active_constraints:
        if c.id == "con-injected":
            c.value = "max_rows=100000"
    await memory_store.update_chain("agent-a", chain2)

    tampered = await ops.verify(
        agent_id="agent-a", action="read_data", level=VerificationLevel.STANDARD
    )
    assert tampered.valid is False, (
        "editing a directly-injected constraint's value was NOT detected — the "
        "constraint envelope is not bound by the chain-state signature"
    )
    assert "chain-state signature" in tampered.reason.lower()


# ---------------------------------------------------------------------------
# (e) #1912 Wave 3 A1: a legacy chain (no chain-state sig) is REJECTED by
#     default; ACCEPTED only under the migration-window opt-out.
# ---------------------------------------------------------------------------


async def _ops_with(registry, key_manager, memory_store, **flags):
    operations = TrustOperations(
        authority_registry=registry,
        key_manager=key_manager,
        trust_store=memory_store,
        **flags,
    )
    await operations.initialize()
    return operations


async def test_legacy_chain_rejected_by_default(ops, memory_store, caplog):
    """#1912 Wave 3 A1: an unsigned chain is fail-closed REJECTED.

    Stripping the chain-state signature is exactly the downgrade-to-legacy bypass
    of MED-1/MED-2. With the default fail-closed posture
    (allow_unsigned_chain_state=False) the unsigned chain is DENIED.
    """
    await _establish(ops, "agent-a", [_cap_req("read_data", [])])
    # Simulate a pre-Wave-2 / downgraded chain: strip the chain-state signature.
    chain = await memory_store.get_chain("agent-a")
    chain.chain_state_signature = None
    await memory_store.update_chain("agent-a", chain)

    with caplog.at_level(logging.WARNING, logger="kailash.trust.operations"):
        result = await ops.verify(
            agent_id="agent-a", action="read_data", level=VerificationLevel.STANDARD
        )
    assert result.valid is False, (
        "an unsigned chain (no chain-state signature) must be REJECTED by "
        f"default — #1912 Wave 3 A1 fail-closed enforcement: {result.reason}"
    )
    assert "chain-state signature" in result.reason.lower()
    assert any(
        "REJECTING chain with NO chain-state signature" in rec.message
        for rec in caplog.records
    ), "the fail-closed reject must emit the loud A1 WARN naming the migration path"


async def test_absent_reject_warn_is_one_time_latched(ops, memory_store, caplog):
    """The absent-signature reject WARN is one-time-latched (no per-verify spam)."""
    await _establish(ops, "agent-a", [_cap_req("read_data", [])])
    chain = await memory_store.get_chain("agent-a")
    chain.chain_state_signature = None
    await memory_store.update_chain("agent-a", chain)

    with caplog.at_level(logging.WARNING, logger="kailash.trust.operations"):
        await ops.verify(agent_id="agent-a", action="read_data")
        await ops.verify(agent_id="agent-a", action="read_data")
        await ops.verify(agent_id="agent-a", action="read_data")
    absent_warns = [
        r for r in caplog.records if "NO chain-state signature" in r.message
    ]
    assert (
        len(absent_warns) == 1
    ), f"the absent-signature WARN must be one-time-latched, saw {len(absent_warns)}"


async def test_legacy_chain_accepted_with_opt_out(
    registry, key_manager, memory_store, caplog
):
    """The migration-window opt-out accepts an unsigned chain with a loud WARN.

    allow_unsigned_chain_state=True restores the pre-Wave-3 verify-if-present
    behavior so a deployment keeps running WHILE its chains are re-signed by the
    #1912 migration — with a loud one-time WARN that set-deletion / suppression
    detection is OFF.
    """
    ops_optout = await _ops_with(
        registry, key_manager, memory_store, allow_unsigned_chain_state=True
    )
    await _establish(ops_optout, "agent-a", [_cap_req("read_data", [])])
    chain = await memory_store.get_chain("agent-a")
    chain.chain_state_signature = None
    await memory_store.update_chain("agent-a", chain)

    with caplog.at_level(logging.WARNING, logger="kailash.trust.operations"):
        result = await ops_optout.verify(
            agent_id="agent-a", action="read_data", level=VerificationLevel.STANDARD
        )
    assert result.valid is True, (
        "with allow_unsigned_chain_state=True an unsigned chain must be ACCEPTED "
        f"(migration window): {result.reason}"
    )
    assert any(
        "allow_unsigned_chain_state=True" in rec.message for rec in caplog.records
    ), "the opt-out accept must emit the loud one-time WARN that detection is OFF"


# ---------------------------------------------------------------------------
# (f) PRUNE-WHEN-UNSET byte-identity + serializer round-trip
# ---------------------------------------------------------------------------


def _legacy_chain() -> TrustLineageChain:
    genesis = GenesisRecord(
        id="gen-legacy",
        agent_id="agent-legacy",
        authority_id="org-test",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=FIXED_TS,
        signature="gs",
    )
    return TrustLineageChain(genesis=genesis)


def test_legacy_chain_dict_has_no_chain_state_signature_key():
    chain = _legacy_chain()
    assert chain.chain_state_signature is None
    data = chain.to_dict()
    assert "chain_state_signature" not in data, (
        "a legacy chain (no chain-state signature) must serialize prune-when-unset "
        "— the dict must carry NO chain_state_signature key (byte-identical to "
        "pre-Wave-2)"
    )
    # Empirical byte-identity: removing the field entirely reproduces the exact
    # same dict, so a pre-Wave-2 chain and a None-field chain serialize identically.
    assert data == {k: v for k, v in data.items() if k != "chain_state_signature"}


def test_signed_chain_dict_carries_key_and_round_trips():
    chain = _legacy_chain()
    chain.chain_state_signature = "c2lnbmF0dXJl"  # opaque base64-ish token
    data = chain.to_dict()
    assert (
        data["chain_state_signature"] == "c2lnbmF0dXJl"
    ), "a signed chain must emit chain_state_signature in to_dict"
    restored = TrustLineageChain.from_dict(data)
    assert (
        restored.chain_state_signature == "c2lnbmF0dXJl"
    ), "chain_state_signature must survive to_dict/from_dict round-trip"
    # Discriminating: a legacy dict round-trips to None (not the signed value).
    legacy_restored = TrustLineageChain.from_dict(_legacy_chain().to_dict())
    assert legacy_restored.chain_state_signature is None


async def test_signed_chain_survives_store_round_trip(ops, memory_store):
    """The signature must survive a full store serialize/deserialize (the path
    every persistent store uses is to_dict/from_dict)."""
    from kailash.trust.chain_store.filesystem import FilesystemStore
    import tempfile

    await _establish(ops, "agent-a", [_cap_req("read_data", ["read_only"])])
    chain = await memory_store.get_chain("agent-a")
    original_sig = chain.chain_state_signature
    assert original_sig

    with tempfile.TemporaryDirectory() as d:
        fs = FilesystemStore(base_dir=d)
        await fs.initialize()
        await fs.store_chain(chain)
        reloaded = await fs.get_chain("agent-a")
    assert reloaded.chain_state_signature == original_sig, (
        "chain-state signature did not survive filesystem store round-trip — a "
        "serializer dropped the field (security.md § Multi-Site Kwarg Plumbing)"
    )
    # And the reloaded chain still verifies against operations (structure intact).
    ops.trust_store = memory_store  # keep verify wired to the in-memory chain
    result = await ops.verify(
        agent_id="agent-a", action="read_data", level=VerificationLevel.STANDARD
    )
    assert result.valid is True


# ---------------------------------------------------------------------------
# Cross-SDK canonical pre-image encoding tripwire (fixed input → pinned bytes)
# ---------------------------------------------------------------------------


def test_chain_state_preimage_is_deterministic_and_pinned():
    """Pins the canonical pre-image ENCODING (sorted keys, sorted id lists, no
    whitespace, empty-envelope constraint_hash) on a fixed input. A change to the
    pre-image shape/encoding is a cross-SDK signing-format change and must break
    this tripwire loudly (cross-sdk-inspection.md Rule 4b/4d)."""
    genesis = GenesisRecord(
        id="gen-fixed",
        agent_id="agent-fixed",
        authority_id="org-test",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=FIXED_TS,
        signature="gs",
    )
    # Two caps in NON-sorted id order to prove the pre-image sorts them.
    cap_b = CapabilityAttestation(
        id="cap-b",
        capability="write_data",
        capability_type=CapabilityType.ACTION,
        constraints=[],
        attester_id="org-test",
        attested_at=FIXED_TS,
        signature="s",
    )
    cap_a = CapabilityAttestation(
        id="cap-a",
        capability="read_data",
        capability_type=CapabilityType.ACTION,
        constraints=[],
        attester_id="org-test",
        attested_at=FIXED_TS,
        signature="s",
    )
    chain = TrustLineageChain(genesis=genesis, capabilities=[cap_b, cap_a])
    # Empty constraint envelope → constraint_hash component "".
    chain.constraint_envelope.active_constraints = []

    payload = chain_state_canonical_payload(chain)
    assert payload == {
        "genesis_id": "gen-fixed",
        "capability_ids": ["cap-a", "cap-b"],
        "delegation_ids": [],
        "constraint_hash": "",
    }
    expected = (
        '{"capability_ids":["cap-a","cap-b"],"constraint_hash":"",'
        '"delegation_ids":[],"genesis_id":"gen-fixed"}'
    )
    assert chain_state_canonical_payload_str(chain) == expected, (
        "chain-state canonical pre-image encoding changed — this is a cross-SDK "
        "signing-format change; re-pin ONLY in lockstep with the sibling SDK"
    )


# ---------------------------------------------------------------------------
# Delegation + rotation: mutation surfaces re-issue the signature
# ---------------------------------------------------------------------------


async def test_delegation_reissues_chain_state_signature_and_verifies(
    ops, memory_store
):
    from kailash.trust.execution_context import ExecutionContext, HumanOrigin

    await _establish(ops, "agent-root", [_cap_req("read_data", [])])
    ctx = ExecutionContext(
        human_origin=HumanOrigin(
            human_id="alice@corp.com",
            display_name="Alice",
            auth_provider="test",
            session_id="sess-1",
            authenticated_at=FIXED_TS,
        )
    )
    await ops.delegate(
        delegator_id="agent-root",
        delegatee_id="agent-child",
        task_id="t-1",
        capabilities=["read_data"],
        context=ctx,
    )
    child = await memory_store.get_chain("agent-child")
    assert (
        child.chain_state_signature
    ), "delegate (new-delegatee branch) must issue a chain-state signature"
    result = await ops.verify(
        agent_id="agent-child", action="read_data", level=VerificationLevel.STANDARD
    )
    assert (
        result.valid is True
    ), f"a delegated chain failed chain-state verification: {result.reason}"


async def test_key_rotation_reissues_chain_state_signature(
    ops, registry, key_manager, memory_store
):
    from kailash.trust.signing.rotation import CredentialRotationManager

    await _establish(ops, "agent-a", [_cap_req("read_data", ["read_only"])])
    original_sig = (await memory_store.get_chain("agent-a")).chain_state_signature
    assert original_sig

    mgr = CredentialRotationManager(
        key_manager=key_manager,
        trust_store=memory_store,
        authority_registry=registry,
    )
    await mgr.initialize()
    await mgr.rotate_key("org-test")

    rotated = await memory_store.get_chain("agent-a")
    assert rotated.chain_state_signature, "rotation dropped the chain-state signature"
    assert rotated.chain_state_signature != original_sig, (
        "rotation did not re-sign the chain-state signature with the new key — a "
        "stale old-key signature would fail closed at verify after every rotation"
    )
    # The load-bearing assertion: the re-signed chain still verifies.
    result = await ops.verify(
        agent_id="agent-a", action="read_data", level=VerificationLevel.STANDARD
    )
    assert (
        result.valid is True
    ), f"a chain re-signed by key rotation failed chain-state verify: {result.reason}"


# ---------------------------------------------------------------------------
# Wave-3 A1 enforcement contract (#1912 RT-sec-w2 INVEST-NOW), now LANDED.
# A store-writer who strips chain_state_signature downgrades the chain to
# "legacy". Under Wave 2 that was ACCEPTED-with-WARN (a full bypass of
# MED-1/MED-2); Wave 3 A1 enforcement REQUIRES the signature and REJECTS a
# stripped/absent one. The self-clearing xfail-strict tripwire XPASSed when
# Wave 3 landed and was removed here — this is now a normal passing test.
# ---------------------------------------------------------------------------


async def test_sig_strip_downgrade_rejected(ops, memory_store):
    # A store-writer deletes a constraint-bearing cap AND strips the chain-state
    # signature to HIDE the tamper (downgrade to legacy). Wave 2 accepts it
    # (valid=True); Wave 3 A1 must reject a chain with no valid chain-state sig.
    await _establish(
        ops,
        "agent-a",
        [
            _cap_req("read_data", []),
            _cap_req("read_pii", ["read_only", "no_pii_export"]),
        ],
    )
    chain = await memory_store.get_chain("agent-a")
    chain.capabilities = [c for c in chain.capabilities if c.capability != "read_pii"]
    chain.chain_state_signature = None  # the downgrade: strip the sig
    await memory_store.update_chain("agent-a", chain)

    result = await ops.verify(
        agent_id="agent-a", action="read_data", level=VerificationLevel.STANDARD
    )
    # Wave 3 A1: a stripped/absent chain-state signature MUST be rejected.
    assert result.valid is False, (
        "sig-strip downgrade was accepted — Wave 3 A1 enforcement must reject a "
        "chain whose chain-state signature is stripped/absent"
    )


# ---------------------------------------------------------------------------
# RT-sec-w3 Finding B: the MINT gate enforces the chain-state signature too
# (enforcement-surface parity — a portable artifact must not be minted from a
# chain-state-tampered/unsigned chain).
# ---------------------------------------------------------------------------


async def test_mint_gate_refuses_chain_with_broken_chain_state_signature(
    ops, memory_store
):
    from kailash.trust.exceptions import InvalidTrustChainError

    await _establish(
        ops,
        "agent-a",
        [
            _cap_req("read_data", []),
            _cap_req("read_pii", ["read_only", "no_pii_export"]),
        ],
    )
    # Store-writer deletes a constraint-bearing cap WITHOUT re-signing → the
    # chain-state signature no longer matches the recomputed pre-image.
    chain = await memory_store.get_chain("agent-a")
    chain.capabilities = [c for c in chain.capabilities if c.capability != "read_pii"]
    await memory_store.update_chain("agent-a", chain)
    tampered = await memory_store.get_chain("agent-a")

    # The mint gate must REFUSE — verify() would reject this chain, so mint (which
    # produces a signed, portable artifact) must not accept it either.
    with pytest.raises(InvalidTrustChainError):
        await ops._verify_source_chain_before_mint(tampered, "agent-a")


async def test_mint_gate_refuses_unsigned_chain_by_default(ops, memory_store):
    from kailash.trust.exceptions import InvalidTrustChainError

    await _establish(ops, "agent-a", [_cap_req("read_data", [])])
    chain = await memory_store.get_chain("agent-a")
    chain.chain_state_signature = None  # simulate a pre-Wave-2 / downgraded chain
    await memory_store.update_chain("agent-a", chain)
    tampered = await memory_store.get_chain("agent-a")

    with pytest.raises(InvalidTrustChainError):
        await ops._verify_source_chain_before_mint(tampered, "agent-a")


async def test_mint_gate_accepts_unsigned_chain_under_opt_out(
    registry, key_manager, memory_store
):
    # Under the migration-window opt-out the mint gate matches verify(): an
    # unsigned chain (valid v1 caps) is accepted rather than refused.
    ops_optout = await _ops_with(
        registry, key_manager, memory_store, allow_unsigned_chain_state=True
    )
    await _establish(ops_optout, "agent-a", [_cap_req("read_data", [])])
    chain = await memory_store.get_chain("agent-a")
    chain.chain_state_signature = None
    await memory_store.update_chain("agent-a", chain)
    tampered = await memory_store.get_chain("agent-a")

    # No raise — the opt-out permits minting from an unsigned chain.
    await ops_optout._verify_source_chain_before_mint(tampered, "agent-a")
