# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: #1912 Wave 3 re-signing migration (installed-base → Wave-3 posture).

The migration promotes a pre-#1912 chain (legacy caps + no chain-state signature)
to the Wave-3 posture (v1-subject-bound caps + a chain-state signature) so a
deployment can flip fail-closed enforcement on without breaking existing agents.

Tested against REAL stores (InMemory AND a real on-disk Filesystem store), REAL
Ed25519, NO mocking. Scenarios:

  * promote legacy chain → v1 + chain-state sig; verify() then PASSES fail-closed;
  * real on-disk Filesystem store round-trip (serialization survives disk);
  * external-attester cap reported un-migratable (local key cannot re-sign FOR it);
  * chain reported un-migratable when the genesis signing key is absent locally;
  * idempotent (a second run changes nothing);
  * dry_run writes nothing;
  * rollback restores the byte-exact pre-migration state;
  * apply failure rolls back ALL changes (failure-atomicity).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

import pytest

from kailash.trust.authority import AuthorityPermission, OrganizationalAuthority
from kailash.trust.chain import (
    CAPABILITY_SIGNING_VERSION_LEGACY,
    CAPABILITY_SIGNING_VERSION_V1,
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    Constraint,
    ConstraintType,
    GenesisRecord,
    TrustLineageChain,
    VerificationLevel,
)
from kailash.trust.chain_store.filesystem import FilesystemStore
from kailash.trust.chain_store.memory import InMemoryTrustStore
from kailash.trust.exceptions import AuthorityInactiveError, AuthorityNotFoundError
from kailash.trust.migrations.subject_binding_1912 import (
    SubjectBindingMigration,
    SubjectBindingMigrationError,
)
from kailash.trust.operations import (
    CapabilityRequest,
    TrustKeyManager,
    TrustOperations,
)
from kailash.trust.signing.crypto import generate_keypair, serialize_for_signing

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


def _fail_closed_ops(registry, key_manager, store) -> TrustOperations:
    """A TrustOperations with BOTH #1912 Wave-3 opt-outs OFF (fail-closed)."""
    return TrustOperations(
        authority_registry=registry, key_manager=key_manager, trust_store=store
    )


async def _establish_then_downgrade(ops, key_manager, agent_id, caps):
    """Establish a v1 chain, then downgrade it to a pre-#1912 (legacy) chain."""
    await ops.establish(
        agent_id=agent_id,
        authority_id="org-test",
        capabilities=[
            CapabilityRequest(capability=c, capability_type=CapabilityType.ACTION)
            for c in caps
        ],
    )
    chain = await ops.trust_store.get_chain(agent_id)
    # Simulate the installed base: every cap legacy (re-signed over the no-subject
    # legacy pre-image), and NO chain-state signature.
    for cap in chain.capabilities:
        cap.signing_payload_version = CAPABILITY_SIGNING_VERSION_LEGACY
        payload = serialize_for_signing(cap.to_signing_payload())
        cap.signature = await key_manager.sign(payload, "test-key-001")
    chain.chain_state_signature = None
    await ops.trust_store.update_chain(agent_id, chain)
    return chain


# ---------------------------------------------------------------------------
# Core: promote a legacy chain and make it verify under fail-closed enforcement
# ---------------------------------------------------------------------------


async def test_migration_promotes_legacy_chain_to_v1_and_signs(
    registry, key_manager, memory_store
):
    ops = _fail_closed_ops(registry, key_manager, memory_store)
    await ops.initialize()
    await _establish_then_downgrade(ops, key_manager, "agent-a", ["read_data"])

    # Pre-migration: the downgraded legacy chain is REJECTED by fail-closed verify.
    before = await ops.verify(
        agent_id="agent-a", action="read_data", level=VerificationLevel.STANDARD
    )
    assert before.valid is False, "fixture bug: legacy chain should be rejected"

    migration = SubjectBindingMigration(registry, key_manager, memory_store)
    report = await migration.migrate(trust_store_placement=True)

    assert report.total_chains == 1
    assert report.migrated_chains == 1
    assert report.promoted_capabilities == 1
    assert report.added_chain_state_signatures == 1
    assert report.fully_migrated is True
    assert report.unmigratable == []

    # Post-migration: caps are v1, a chain-state sig exists, and fail-closed
    # verify() now PASSES.
    migrated = await memory_store.get_chain("agent-a")
    assert all(
        c.signing_payload_version == CAPABILITY_SIGNING_VERSION_V1
        for c in migrated.capabilities
    )
    assert migrated.chain_state_signature is not None
    after = await ops.verify(
        agent_id="agent-a", action="read_data", level=VerificationLevel.STANDARD
    )
    assert (
        after.valid is True
    ), f"a migrated chain must verify under fail-closed enforcement: {after.reason}"
    # FULL level (full-chain signature verify) must also pass.
    after_full = await ops.verify(
        agent_id="agent-a", action="read_data", level=VerificationLevel.FULL
    )
    assert (
        after_full.valid is True
    ), f"FULL denied a migrated chain: {after_full.reason}"


async def test_migration_real_filesystem_store(registry, key_manager, tmp_path):
    """The migration round-trips through a REAL on-disk Filesystem store."""
    store = FilesystemStore(base_dir=str(tmp_path / "chains"))
    await store.initialize()
    ops = _fail_closed_ops(registry, key_manager, store)
    await ops.initialize()
    await _establish_then_downgrade(ops, key_manager, "agent-fs", ["read_data"])

    migration = SubjectBindingMigration(registry, key_manager, store)
    report = await migration.migrate(trust_store_placement=True)
    assert report.migrated_chains == 1
    assert report.fully_migrated is True

    # Re-read from disk (fresh store instance) — the v1 promotion + chain-state
    # signature must survive serialization to disk and back.
    store2 = FilesystemStore(base_dir=str(tmp_path / "chains"))
    await store2.initialize()
    ops2 = _fail_closed_ops(registry, key_manager, store2)
    await ops2.initialize()
    reloaded = await store2.get_chain("agent-fs")
    assert all(
        c.signing_payload_version == CAPABILITY_SIGNING_VERSION_V1
        for c in reloaded.capabilities
    )
    assert reloaded.chain_state_signature is not None
    result = await ops2.verify(
        agent_id="agent-fs", action="read_data", level=VerificationLevel.STANDARD
    )
    assert (
        result.valid is True
    ), f"migrated chain failed after disk round-trip: {result.reason}"


# ---------------------------------------------------------------------------
# Un-migratable reporting (never silently dropped)
# ---------------------------------------------------------------------------


def _signed_genesis(key_manager_sign_sig: str, agent_id: str) -> GenesisRecord:
    return GenesisRecord(
        id=f"gen-{agent_id}",
        agent_id=agent_id,
        authority_id="org-test",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=FIXED_TS,
        signature=key_manager_sign_sig,
    )


async def test_migration_reports_external_attester_cap(
    registry, key_manager, memory_store
):
    # A chain with one LOCAL legacy cap (attester=org-test) and one EXTERNAL
    # legacy cap (attester=org-other) the local genesis key cannot re-sign FOR.
    genesis = _signed_genesis("gs", "agent-x")
    local_cap = CapabilityAttestation(
        id="cap-local",
        capability="read_data",
        capability_type=CapabilityType.ACTION,
        constraints=[],
        attester_id="org-test",
        attested_at=FIXED_TS,
        signature="",
        signing_payload_version=CAPABILITY_SIGNING_VERSION_LEGACY,
    )
    # A GENUINELY-signed legacy cap (Fix A refuses to promote an unverified one).
    local_cap.signature = await key_manager.sign(
        serialize_for_signing(local_cap.to_signing_payload()), "test-key-001"
    )
    external_cap = CapabilityAttestation(
        id="cap-external",
        capability="write_data",
        capability_type=CapabilityType.ACTION,
        constraints=[],
        attester_id="org-other",
        attested_at=FIXED_TS,
        signature="s2",
        signing_payload_version=CAPABILITY_SIGNING_VERSION_LEGACY,
    )
    chain = TrustLineageChain(genesis=genesis, capabilities=[local_cap, external_cap])
    await memory_store.store_chain(chain)

    migration = SubjectBindingMigration(registry, key_manager, memory_store)
    report = await migration.migrate(trust_store_placement=True)

    assert report.promoted_capabilities == 1, "the local cap should be promoted"
    assert report.fully_migrated is False
    external = [u for u in report.unmigratable if u.capability_id == "cap-external"]
    assert len(external) == 1
    assert external[0].kind == "capability"
    assert "org-other" in external[0].reason
    # The migrated chain: local cap v1, external cap still legacy.
    migrated = await memory_store.get_chain("agent-x")
    by_id = {c.id: c for c in migrated.capabilities}
    assert by_id["cap-local"].signing_payload_version == CAPABILITY_SIGNING_VERSION_V1
    assert (
        by_id["cap-external"].signing_payload_version
        == CAPABILITY_SIGNING_VERSION_LEGACY
    )


async def test_migration_reports_chain_when_signing_key_absent(
    registry, key_manager, memory_store
):
    # Persist a legacy chain using a key manager that HAS the key.
    ops = _fail_closed_ops(registry, key_manager, memory_store)
    await ops.initialize()
    await _establish_then_downgrade(ops, key_manager, "agent-nokey", ["read_data"])

    # Now run the migration with a key manager that LACKS the signing key.
    empty_km = TrustKeyManager()
    migration = SubjectBindingMigration(registry, empty_km, memory_store)
    report = await migration.migrate(trust_store_placement=True)

    assert report.migrated_chains == 0
    assert report.promoted_capabilities == 0
    assert report.fully_migrated is False
    chain_items = [u for u in report.unmigratable if u.kind == "chain"]
    assert len(chain_items) == 1
    assert "signing key" in chain_items[0].reason
    # Nothing was written — the chain is unchanged (still legacy).
    unchanged = await memory_store.get_chain("agent-nokey")
    assert all(
        c.signing_payload_version == CAPABILITY_SIGNING_VERSION_LEGACY
        for c in unchanged.capabilities
    )
    assert unchanged.chain_state_signature is None


# ---------------------------------------------------------------------------
# Idempotency, dry-run, rollback, failure-atomicity
# ---------------------------------------------------------------------------


async def test_migration_is_idempotent(registry, key_manager, memory_store):
    ops = _fail_closed_ops(registry, key_manager, memory_store)
    await ops.initialize()
    await _establish_then_downgrade(ops, key_manager, "agent-a", ["read_data"])

    migration = SubjectBindingMigration(registry, key_manager, memory_store)
    first = await migration.migrate(trust_store_placement=True)
    assert first.migrated_chains == 1

    second = await migration.migrate(trust_store_placement=True)
    assert second.total_chains == 1
    assert second.migrated_chains == 0, "a re-run must change nothing (idempotent)"
    assert second.promoted_capabilities == 0
    assert second.added_chain_state_signatures == 0
    assert second.already_current_chains == 1


async def test_migration_dry_run_writes_nothing(registry, key_manager, memory_store):
    ops = _fail_closed_ops(registry, key_manager, memory_store)
    await ops.initialize()
    await _establish_then_downgrade(ops, key_manager, "agent-a", ["read_data"])

    migration = SubjectBindingMigration(registry, key_manager, memory_store)
    report = await migration.migrate(trust_store_placement=True, dry_run=True)
    assert report.dry_run is True
    assert report.migrated_chains == 1  # would-migrate count
    assert report.snapshots == {}

    # Store is UNCHANGED — still a legacy chain.
    unchanged = await memory_store.get_chain("agent-a")
    assert all(
        c.signing_payload_version == CAPABILITY_SIGNING_VERSION_LEGACY
        for c in unchanged.capabilities
    )
    assert unchanged.chain_state_signature is None


async def test_migration_rollback_restores_pre_migration_state(
    registry, key_manager, memory_store
):
    ops = _fail_closed_ops(registry, key_manager, memory_store)
    await ops.initialize()
    await _establish_then_downgrade(ops, key_manager, "agent-a", ["read_data"])
    pre = await memory_store.get_chain("agent-a")
    pre_versions = [c.signing_payload_version for c in pre.capabilities]
    pre_sigs = [c.signature for c in pre.capabilities]

    migration = SubjectBindingMigration(registry, key_manager, memory_store)
    report = await migration.migrate(trust_store_placement=True)
    assert report.migrated_chains == 1

    restored_count = await migration.rollback(report)
    assert restored_count == 1

    # Byte-exact restore: versions + signatures + chain-state sig back to legacy.
    restored = await memory_store.get_chain("agent-a")
    assert [c.signing_payload_version for c in restored.capabilities] == pre_versions
    assert [c.signature for c in restored.capabilities] == pre_sigs
    assert restored.chain_state_signature is None


class _FailOnNthUpdateStore:
    """Wraps a real store; raises on the Nth update_chain to test atomicity."""

    def __init__(self, inner, fail_on: int):
        self._inner = inner
        self._fail_on = fail_on
        self._updates = 0

    async def initialize(self):
        await self._inner.initialize()

    async def list_chains(self, **kw):
        return await self._inner.list_chains(**kw)

    async def get_chain(self, agent_id, **kw):
        return await self._inner.get_chain(agent_id, **kw)

    async def store_chain(self, chain, **kw):
        return await self._inner.store_chain(chain, **kw)

    async def update_chain(self, agent_id, chain):
        self._updates += 1
        if self._updates == self._fail_on:
            raise RuntimeError("simulated store failure")
        return await self._inner.update_chain(agent_id, chain)


async def test_migration_atomic_rollback_on_apply_failure(
    registry, key_manager, memory_store
):
    ops = _fail_closed_ops(registry, key_manager, memory_store)
    await ops.initialize()
    # Two legacy chains; the store fails on the 2nd update mid-apply.
    await _establish_then_downgrade(ops, key_manager, "agent-a", ["read_data"])
    await _establish_then_downgrade(ops, key_manager, "agent-b", ["read_data"])
    pre_a = await memory_store.get_chain("agent-a")
    pre_a_versions = [c.signing_payload_version for c in pre_a.capabilities]

    failing = _FailOnNthUpdateStore(memory_store, fail_on=2)
    migration = SubjectBindingMigration(registry, key_manager, failing)
    with pytest.raises(SubjectBindingMigrationError):
        await migration.migrate(trust_store_placement=True)

    # Atomicity: the first-applied chain was ROLLED BACK to its legacy state.
    post_a = await memory_store.get_chain("agent-a")
    assert [
        c.signing_payload_version for c in post_a.capabilities
    ] == pre_a_versions, "a mid-apply failure must restore ALL applied chains"
    assert post_a.chain_state_signature is None
    post_b = await memory_store.get_chain("agent-b")
    assert all(
        c.signing_payload_version == CAPABILITY_SIGNING_VERSION_LEGACY
        for c in post_b.capabilities
    )


# ---------------------------------------------------------------------------
# RT-sec-w3 Finding A: the migration MUST NOT launder an unverified legacy cap
# ---------------------------------------------------------------------------


async def test_migration_refuses_to_resign_forged_legacy_cap(
    registry, key_manager, memory_store
):
    """A store-writer's injected/tampered legacy cap must be REPORTED, never
    re-signed into a valid v1 cap.

    Threat: a bounded-trust store-writer (no signing key) injects a legacy cap
    with `attester_id` == the genesis authority but an INVALID signature. On a
    pre-#1912 chain this is undetected. If the migration re-signed it with the
    genesis key it would launder the forgery into a valid v1 cap (privilege
    escalation THROUGH the migration). The migration must verify the existing
    legacy signature first and report the forgery instead.
    """
    genesis = _signed_genesis("gs", "agent-forge")
    # A GENUINE legacy cap (validly signed over the legacy pre-image) — promoted.
    good_cap = CapabilityAttestation(
        id="cap-good",
        capability="read_data",
        capability_type=CapabilityType.ACTION,
        constraints=[],
        attester_id="org-test",
        attested_at=FIXED_TS,
        signature="",
        signing_payload_version=CAPABILITY_SIGNING_VERSION_LEGACY,
    )
    good_cap.signature = await key_manager.sign(
        serialize_for_signing(good_cap.to_signing_payload()), "test-key-001"
    )
    # A FORGED cap: attester spoofed to the genesis authority, garbage signature.
    forged_cap = CapabilityAttestation(
        id="cap-forged",
        capability="admin_all",
        capability_type=CapabilityType.ACTION,
        constraints=[],
        attester_id="org-test",
        attested_at=FIXED_TS,
        signature="deadbeef-not-a-real-signature",
        signing_payload_version=CAPABILITY_SIGNING_VERSION_LEGACY,
    )
    chain = TrustLineageChain(genesis=genesis, capabilities=[good_cap, forged_cap])
    await memory_store.store_chain(chain)

    migration = SubjectBindingMigration(registry, key_manager, memory_store)
    report = await migration.migrate(trust_store_placement=True)

    # The genuine cap is promoted; the forged cap is REPORTED, never laundered.
    assert report.promoted_capabilities == 1
    forged_items = [u for u in report.unmigratable if u.capability_id == "cap-forged"]
    assert len(forged_items) == 1
    assert "does not verify" in forged_items[0].reason
    migrated = await memory_store.get_chain("agent-forge")
    by_id = {c.id: c for c in migrated.capabilities}
    assert by_id["cap-good"].signing_payload_version == CAPABILITY_SIGNING_VERSION_V1
    # The forged cap stays legacy with its ORIGINAL (invalid) signature — the
    # genesis key never signed it, so Wave-3 verify still rejects it.
    assert (
        by_id["cap-forged"].signing_payload_version == CAPABILITY_SIGNING_VERSION_LEGACY
    )
    assert by_id["cap-forged"].signature == "deadbeef-not-a-real-signature"


# ---------------------------------------------------------------------------
# RT-sec-w3r2 Finding C: legacy-cap promotion requires explicit trust ack
# (the migration cannot verify a legacy cap's original holder → transplant risk)
# ---------------------------------------------------------------------------


async def test_migration_refuses_legacy_promotion_without_trust_ack(
    registry, key_manager, memory_store
):
    """By default (trust_store_placement=False) legacy caps are REPORTED, not
    promoted — the migration will not make an unverifiable trust-the-placement
    decision silently.
    """
    ops = _fail_closed_ops(registry, key_manager, memory_store)
    await ops.initialize()
    await _establish_then_downgrade(ops, key_manager, "agent-a", ["read_data"])

    migration = SubjectBindingMigration(registry, key_manager, memory_store)
    report = await migration.migrate()  # no trust_store_placement ack

    assert report.promoted_capabilities == 0
    assert report.fully_migrated is False
    ack_items = [u for u in report.unmigratable if "trust_store_placement" in u.reason]
    assert len(ack_items) == 1
    # Nothing written: the chain stays legacy, and NO chain-state signature was
    # added over the un-promoted legacy set.
    unchanged = await memory_store.get_chain("agent-a")
    assert all(
        c.signing_payload_version == CAPABILITY_SIGNING_VERSION_LEGACY
        for c in unchanged.capabilities
    )
    assert unchanged.chain_state_signature is None


async def test_migration_refuses_to_launder_transplanted_legacy_cap(
    registry, key_manager, memory_store
):
    """RT-sec-w3r2 Finding C: a GENUINE legacy cap (validly signed by the
    authority, but NOT originally bound to this chain — legacy caps carry no
    subject) must NOT be silently laundered into a valid v1 cap. Because Fix A's
    signature check passes for a genuine-but-transplanted cap, the trust ack is
    the ONLY gate — the default must refuse.
    """
    # A legacy cap validly signed by org-test (the authority), placed into a
    # chain whose genesis it was NOT issued for (the transplant).
    transplanted = CapabilityAttestation(
        id="cap-transplant",
        capability="admin_all",
        capability_type=CapabilityType.ACTION,
        constraints=[],
        attester_id="org-test",
        attested_at=FIXED_TS,
        signature="",
        signing_payload_version=CAPABILITY_SIGNING_VERSION_LEGACY,
    )
    # Genuine signature over the (subjectless) legacy pre-image — verifies fine.
    transplanted.signature = await key_manager.sign(
        serialize_for_signing(transplanted.to_signing_payload()), "test-key-001"
    )
    genesis = _signed_genesis("gs", "agent-victim")
    chain = TrustLineageChain(genesis=genesis, capabilities=[transplanted])
    await memory_store.store_chain(chain)

    migration = SubjectBindingMigration(registry, key_manager, memory_store)
    report = await migration.migrate()  # default: no trust ack

    # The genuine-signature check (Fix A) would PASS — only the trust ack stops
    # the laundering. Default refuses: reported, not promoted.
    assert report.promoted_capabilities == 0
    laundered = await memory_store.get_chain("agent-victim")
    assert (
        laundered.capabilities[0].signing_payload_version
        == CAPABILITY_SIGNING_VERSION_LEGACY
    ), "a transplanted legacy cap was laundered into v1 WITHOUT the trust ack"
    assert any("trust_store_placement" in u.reason for u in report.unmigratable)


async def _establish_all_v1_no_sig(ops, memory_store, agent_id):
    """Establish an all-v1 chain, then strip ONLY its chain-state signature
    (the legitimate post-Wave-1 / pre-Wave-2 migration-target shape)."""
    await ops.establish(
        agent_id=agent_id,
        authority_id="org-test",
        capabilities=[
            CapabilityRequest(
                capability="read_data", capability_type=CapabilityType.ACTION
            )
        ],
    )
    chain = await memory_store.get_chain(agent_id)
    assert all(
        c.signing_payload_version == CAPABILITY_SIGNING_VERSION_V1
        for c in chain.capabilities
    )
    chain.chain_state_signature = None
    await memory_store.update_chain(agent_id, chain)
    return chain


async def test_migration_signs_all_v1_chain_with_trust_ack(
    registry, key_manager, memory_store
):
    """An all-v1 chain missing its chain-state signature is re-signed WHEN the
    operator acknowledges a trusted store snapshot (trust_store_placement=True).
    """
    ops = _fail_closed_ops(registry, key_manager, memory_store)
    await ops.initialize()
    await _establish_all_v1_no_sig(ops, memory_store, "agent-v1")

    migration = SubjectBindingMigration(registry, key_manager, memory_store)
    report = await migration.migrate(trust_store_placement=True)

    assert report.promoted_capabilities == 0
    assert report.added_chain_state_signatures == 1
    assert report.fully_migrated is True
    resigned = await memory_store.get_chain("agent-v1")
    assert resigned.chain_state_signature is not None
    result = await ops.verify(
        agent_id="agent-v1", action="read_data", level=VerificationLevel.STANDARD
    )
    assert (
        result.valid is True
    ), f"all-v1 chain failed after chain-state re-sign: {result.reason}"


async def test_migration_refuses_fresh_chain_state_signing_without_ack(
    registry, key_manager, memory_store
):
    """RT-sec-w3r3 Finding D: FRESH chain-state signing (adding a signature where
    the chain has none) re-signs over an UNVERIFIED constraint envelope, so it
    requires the trust ack. Without it, the chain is REPORTED, not signed.
    """
    ops = _fail_closed_ops(registry, key_manager, memory_store)
    await ops.initialize()
    await _establish_all_v1_no_sig(ops, memory_store, "agent-v1")

    migration = SubjectBindingMigration(registry, key_manager, memory_store)
    report = await migration.migrate()  # no ack

    assert report.added_chain_state_signatures == 0
    assert report.fully_migrated is False
    chain_ack_items = [
        u
        for u in report.unmigratable
        if u.kind == "chain" and "chain-state signing requires" in u.reason
    ]
    assert len(chain_ack_items) == 1
    # The chain is UNCHANGED — no fresh signature was minted over unverified state.
    unchanged = await memory_store.get_chain("agent-v1")
    assert unchanged.chain_state_signature is None


async def test_migration_does_not_rebless_stripped_constraint_without_ack(
    registry, key_manager, memory_store
):
    """RT-sec-w3r3 Finding D (the MED-2 scenario): a store-writer strips a
    directly-injected constraint AND the chain-state signature, leaving a chain
    shaped like a legit all-v1 migration target. Without the trust ack the
    migration MUST NOT mint a fresh chain-state signature that would bless the
    suppressed envelope.
    """
    ops = _fail_closed_ops(registry, key_manager, memory_store)
    await ops.initialize()
    await ops.establish(
        agent_id="agent-med2",
        authority_id="org-test",
        capabilities=[
            CapabilityRequest(
                capability="read_data", capability_type=CapabilityType.ACTION
            )
        ],
    )
    chain = await memory_store.get_chain("agent-med2")
    # Inject a directly-configured constraint + re-sign (the legit configured state).
    chain.constraint_envelope.active_constraints.append(
        Constraint(
            id="con-reasoning",
            constraint_type=ConstraintType.REASONING_REQUIRED,
            value="reasoning_required",
            source="policy",
        )
    )
    await ops._issue_chain_state_signature(chain)
    await memory_store.update_chain("agent-med2", chain)

    # Store-writer STRIPS the constraint AND the chain-state signature.
    tampered = await memory_store.get_chain("agent-med2")
    tampered.constraint_envelope.active_constraints = [
        c
        for c in tampered.constraint_envelope.active_constraints
        if c.constraint_type != ConstraintType.REASONING_REQUIRED
    ]
    tampered.chain_state_signature = None
    await memory_store.update_chain("agent-med2", tampered)

    migration = SubjectBindingMigration(registry, key_manager, memory_store)
    report = await migration.migrate()  # no ack — must refuse to bless

    assert report.added_chain_state_signatures == 0
    # The suppressed-envelope chain was NOT freshly signed → verify still rejects
    # it (no chain-state signature), so the suppression is not blessed.
    not_reblessed = await memory_store.get_chain("agent-med2")
    assert not_reblessed.chain_state_signature is None
    rejected = await ops.verify(
        agent_id="agent-med2", action="read_data", level=VerificationLevel.STANDARD
    )
    assert rejected.valid is False, (
        "a stripped-constraint chain was re-blessed without the trust ack — "
        "Finding D MED-2 laundering re-opened"
    )
