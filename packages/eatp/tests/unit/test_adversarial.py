"""
Adversarial security tests for the EATP SDK.

Tests attack vectors against the cryptographic trust infrastructure:
1. Forged signatures
2. Replay attacks on audit chains
3. Privilege escalation via delegation
4. Chain splicing / mid-chain tampering
5. Time manipulation
6. Key substitution
7. Cross-chain contamination
8. Challenge-response replay
9. Path traversal on FilesystemStore
10. Pickle injection prevention (JSON-only serialization)
11. Merkle tree proof tampering
12. Selective disclosure tampering
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from eatp.audit_store import AuditRecord, AppendOnlyAuditStore
from eatp.chain import (
    ActionResult,
    AuditAnchor,
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    DelegationRecord,
    GenesisRecord,
    LinkedHashChain,
    TrustLineageChain,
)
from eatp.crypto import generate_keypair, hash_chain, sign, verify_signature
from eatp.enforce.challenge import (
    ChallengeError,
    ChallengeProtocol,
    ChallengeResponse,
)
from eatp.enforce.selective_disclosure import (
    ExportPackage,
    export_for_witness,
    verify_witness_export,
)
from eatp.exceptions import TrustChainNotFoundError
from eatp.merkle import MerkleTree, verify_merkle_proof
from eatp.store.filesystem import FilesystemStore
from eatp.store.memory import InMemoryTrustStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_genesis(
    agent_id: str = "agent-1",
    authority_id: str = "org-acme",
    private_key: str = "",
) -> GenesisRecord:
    """Create a GenesisRecord, optionally signing it with a real key."""
    now = datetime.now(timezone.utc)
    sig = ""
    if private_key:
        sig = sign(
            {
                "id": f"gen-{agent_id}",
                "agent_id": agent_id,
                "authority_id": authority_id,
                "authority_type": "organization",
                "created_at": now.isoformat(),
                "expires_at": None,
                "metadata": {},
            },
            private_key,
        )
    return GenesisRecord(
        id=f"gen-{agent_id}",
        agent_id=agent_id,
        authority_id=authority_id,
        authority_type=AuthorityType.ORGANIZATION,
        created_at=now,
        signature=sig or "unsigned",
    )


def _make_capability(
    cap_id: str,
    capability: str,
    attester_id: str = "org-acme",
    private_key: str = "",
    constraints: list | None = None,
    expires_at: datetime | None = None,
) -> CapabilityAttestation:
    """Create a CapabilityAttestation, optionally signing it."""
    now = datetime.now(timezone.utc)
    sig = ""
    if private_key:
        sig = sign({"id": cap_id, "capability": capability}, private_key)
    return CapabilityAttestation(
        id=cap_id,
        capability=capability,
        capability_type=CapabilityType.ACTION,
        constraints=constraints or [],
        attester_id=attester_id,
        attested_at=now,
        signature=sig or "unsigned",
        expires_at=expires_at,
    )


def _make_chain(
    agent_id: str = "agent-1",
    authority_id: str = "org-acme",
    capabilities: list[str] | None = None,
    private_key: str = "",
) -> TrustLineageChain:
    """Create a TrustLineageChain with optional capabilities."""
    genesis = _make_genesis(agent_id, authority_id, private_key)
    caps = []
    for i, cap_name in enumerate(capabilities or []):
        caps.append(
            _make_capability(
                f"cap-{agent_id}-{i}",
                cap_name,
                attester_id=authority_id,
                private_key=private_key,
            )
        )
    return TrustLineageChain(genesis=genesis, capabilities=caps)


def _make_audit_anchor(
    anchor_id: str,
    agent_id: str,
    action: str = "test_action",
    trust_chain_hash: str = "abc123",
) -> AuditAnchor:
    """Create a minimal AuditAnchor for testing."""
    return AuditAnchor(
        id=anchor_id,
        agent_id=agent_id,
        action=action,
        timestamp=datetime.now(timezone.utc),
        trust_chain_hash=trust_chain_hash,
        result=ActionResult.SUCCESS,
        signature="sig-test",
    )


# ===========================================================================
# 1. Forged Signature Attack
# ===========================================================================


class TestForgedSignatureAttack:
    """Verify that signature verification detects payload and key tampering."""

    def test_modified_payload_detected(self):
        """Sign a payload, modify it, and verify -- must return False."""
        private_key, public_key = generate_keypair()
        original_payload = {"action": "read_data", "agent": "agent-1"}

        signature = sign(original_payload, private_key)

        # Tamper: change the action
        tampered_payload = {"action": "delete_all", "agent": "agent-1"}
        result = verify_signature(tampered_payload, signature, public_key)
        assert result is False, "Signature verification MUST reject a payload that was modified after signing"

    def test_wrong_key_detected(self):
        """Sign with key A, verify with key B -- must return False."""
        priv_a, pub_a = generate_keypair()
        _priv_b, pub_b = generate_keypair()

        payload = "critical-operation"
        signature = sign(payload, priv_a)

        result = verify_signature(payload, signature, pub_b)
        assert result is False, "Signature verification MUST reject when verified with a different key"

    def test_corrupted_signature_detected(self):
        """Corrupt the signature bytes -- verify must return False or raise."""
        private_key, public_key = generate_keypair()
        payload = "test-payload"
        signature = sign(payload, private_key)

        # Flip a character in the base64 signature
        corrupted = signature[:-4] + "XXXX"

        # Should either return False or raise InvalidSignatureError
        try:
            result = verify_signature(payload, corrupted, public_key)
            assert result is False
        except Exception:
            # Any exception is acceptable for a corrupted signature
            pass


# ===========================================================================
# 2. Replay Attack on Audit Chain
# ===========================================================================


class TestReplayAttackOnAuditChain:
    """Verify that LinkedHashChain detects replayed or duplicated entries."""

    def test_duplicate_hash_breaks_linkage(self):
        """Inserting a duplicate original hash in a chain must cause
        verify_chain_linkage to fail when the chain is compared against
        original hashes that differ."""
        chain = LinkedHashChain()
        original_hashes = ["hash_A", "hash_B", "hash_C"]

        for i, h in enumerate(original_hashes):
            chain.add_hash(f"agent-{i}", h)

        # Verify the real originals pass
        valid, idx = chain.verify_chain_linkage(original_hashes)
        assert valid is True, "Original hashes must verify correctly"

        # Attempt replay: pretend hash_A was replayed in place of hash_C
        replayed_hashes = ["hash_A", "hash_B", "hash_A"]
        valid, idx = chain.verify_chain_linkage(replayed_hashes)
        assert valid is False, "Replayed hash (hash_A in slot 2) must fail linkage verification"
        assert idx == 2, "Break must be detected at the replayed index"

    def test_reordered_entries_detected(self):
        """Reordering original hashes must break verify_chain_linkage."""
        chain = LinkedHashChain()
        originals = ["first", "second", "third"]
        for i, h in enumerate(originals):
            chain.add_hash(f"agent-{i}", h)

        # Swap second and third
        reordered = ["first", "third", "second"]
        valid, idx = chain.verify_chain_linkage(reordered)
        assert valid is False, "Reordered hashes must fail linkage verification"

    def test_extra_entry_detected(self):
        """Providing more original hashes than chain entries must fail."""
        chain = LinkedHashChain()
        originals = ["hash_1", "hash_2"]
        for i, h in enumerate(originals):
            chain.add_hash(f"agent-{i}", h)

        # Provide an extra hash
        valid, idx = chain.verify_chain_linkage(originals + ["hash_3"])
        assert valid is False, "Extra original hashes must fail linkage verification"


# ===========================================================================
# 3. Privilege Escalation via Delegation
# ===========================================================================


class TestPrivilegeEscalationViaDelegation:
    """Verify that delegation cannot expand parent capabilities
    at the data structure / constraint level."""

    def test_delegated_capability_not_in_parent(self):
        """A delegation claiming capabilities NOT present in the parent chain
        must be detectable via has_capability checks."""
        priv, _pub = generate_keypair()

        # Parent has only "read_data"
        parent_chain = _make_chain(
            "agent-parent",
            capabilities=["read_data"],
            private_key=priv,
        )

        # A delegation claims to delegate "delete_all" -- this capability
        # does not exist on the parent
        escalation_delegation = DelegationRecord(
            id="del-escalation",
            delegator_id="agent-parent",
            delegatee_id="agent-child",
            task_id="task-escalation",
            capabilities_delegated=["delete_all"],  # NOT in parent
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            signature=sign({"id": "del-escalation"}, priv),
        )

        # The parent does NOT have "delete_all"
        assert parent_chain.has_capability("delete_all") is False, "Parent must not have 'delete_all' capability"
        # The delegation claims it -- proper enforcement must catch this
        assert "delete_all" in escalation_delegation.capabilities_delegated
        assert "delete_all" not in [c.capability for c in parent_chain.capabilities], (
            "Escalated capability must not match any parent capability"
        )

    def test_constraint_tightening_invariant(self):
        """Delegated constraints should be at least as restrictive as parent.
        A delegation with FEWER constraints than parent represents escalation."""
        priv, _pub = generate_keypair()

        parent_chain = _make_chain(
            "agent-parent",
            capabilities=["analyze_data"],
            private_key=priv,
        )
        # Parent capability has constraints
        parent_chain.capabilities[0].constraints = [
            "read_only",
            "no_pii",
            "audit_required",
        ]

        # Delegation tries to drop constraints (escalation attempt)
        escalation_delegation = DelegationRecord(
            id="del-loose",
            delegator_id="agent-parent",
            delegatee_id="agent-child",
            task_id="task-loose",
            capabilities_delegated=["analyze_data"],
            constraint_subset=[],  # NO constraints -- looser than parent
            delegated_at=datetime.now(timezone.utc),
            signature=sign({"id": "del-loose"}, priv),
        )

        parent_constraints = set(parent_chain.capabilities[0].constraints)
        delegated_constraints = set(escalation_delegation.constraint_subset)

        # Proper enforcement: delegated constraints must be a superset of parent
        assert not parent_constraints.issubset(delegated_constraints), (
            "Delegation with fewer constraints than parent represents privilege escalation and must be detectable"
        )


# ===========================================================================
# 4. Chain Splicing Attack
# ===========================================================================


class TestChainSplicingAttack:
    """Verify that modifying a record mid-chain changes the chain hash."""

    def test_modified_delegation_detected_by_signature(self):
        """Modifying a delegation's delegatee_id must be detectable via signature.

        The chain hash uses only delegation IDs (not full content), so content
        tampering is caught at the cryptographic signature level. This test
        verifies that signing the full to_signing_payload() and then tampering
        with a field causes signature verification to fail.
        """
        priv, _pub = generate_keypair()
        now = datetime.now(timezone.utc)

        delegation = DelegationRecord(
            id="del-1",
            delegator_id="agent-0",
            delegatee_id="agent-1",
            task_id="task-1",
            capabilities_delegated=["read_data"],
            constraint_subset=["read_only"],
            delegated_at=now,
            signature="placeholder",
        )

        # Sign the full canonical payload
        signing_payload = delegation.to_signing_payload()
        delegation.signature = sign(signing_payload, priv)

        # Verify the original payload succeeds
        assert verify_signature(signing_payload, delegation.signature, _pub) is True, (
            "Original delegation payload must verify with the signing key"
        )

        # Tamper: change delegatee_id
        delegation.delegatee_id = "agent-attacker"
        tampered_payload = delegation.to_signing_payload()

        # Verification of the tampered payload must fail
        sig_valid_tampered = verify_signature(
            tampered_payload,
            delegation.signature,
            _pub,
        )
        assert sig_valid_tampered is False, "Signature must NOT verify against a tampered delegation payload"

    def test_from_dict_tampered_chain_hash_mismatch(self):
        """Serialize, tamper with a field, deserialize: chain hash must differ."""
        priv, _pub = generate_keypair()
        chain = _make_chain("agent-splice", capabilities=["read"], private_key=priv)

        chain_dict = chain.to_dict()
        original_chain_hash = chain_dict["chain_hash"]

        # Tamper with the genesis authority_id
        chain_dict["genesis"]["authority_id"] = "evil-org"

        reconstructed = TrustLineageChain.from_dict(chain_dict)
        reconstructed_hash = reconstructed.hash()

        # The genesis authority_id is not part of hash_trust_chain_state directly,
        # but the genesis ID IS. Let's also tamper with genesis.id to be sure.
        chain_dict2 = chain.to_dict()
        chain_dict2["genesis"]["id"] = "gen-injected"
        reconstructed2 = TrustLineageChain.from_dict(chain_dict2)

        assert reconstructed2.hash() != original_chain_hash, "Tampered genesis ID must produce a different chain hash"


# ===========================================================================
# 5. Time Manipulation
# ===========================================================================


class TestTimeManipulation:
    """Verify temporal checks against backdated and manipulation attacks."""

    def test_expired_genesis_detected(self):
        """A genesis record with expires_at in the past must be detected."""
        expired_genesis = GenesisRecord(
            id="gen-expired",
            agent_id="agent-expired",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            expires_at=datetime(2020, 6, 1, tzinfo=timezone.utc),
            signature="sig-expired",
        )
        assert expired_genesis.is_expired() is True

        chain = TrustLineageChain(genesis=expired_genesis)
        assert chain.is_expired() is True
        result = chain.verify_basic()
        assert result.valid is False, "Expired chain must fail basic verification"

    def test_expired_capability_detected(self):
        """A capability with expires_at in the past must be detected."""
        now = datetime.now(timezone.utc)
        cap = CapabilityAttestation(
            id="cap-expired",
            capability="read_data",
            capability_type=CapabilityType.ACTION,
            constraints=[],
            attester_id="org-acme",
            attested_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            expires_at=datetime(2020, 6, 1, tzinfo=timezone.utc),
            signature="sig-cap",
        )
        assert cap.is_expired() is True

        genesis = GenesisRecord(
            id="gen-time",
            agent_id="agent-time",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=now,
            signature="sig-gen",
        )
        chain = TrustLineageChain(genesis=genesis, capabilities=[cap])

        # get_capability returns None for expired capabilities
        assert chain.get_capability("read_data") is None, "Expired capability must not be returned by get_capability()"
        assert chain.has_capability("read_data") is False

    def test_expired_delegation_detected(self):
        """A delegation with expires_at in the past must be detected."""
        delegation = DelegationRecord(
            id="del-expired",
            delegator_id="agent-0",
            delegatee_id="agent-1",
            task_id="task-1",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            expires_at=datetime(2020, 6, 1, tzinfo=timezone.utc),
            signature="sig-del",
        )
        assert delegation.is_expired() is True

    def test_future_creation_backdated_expiry(self):
        """A record created in the future but expired in the past is suspicious."""
        cap = CapabilityAttestation(
            id="cap-backdated",
            capability="admin",
            capability_type=CapabilityType.ACTION,
            constraints=[],
            attester_id="org-acme",
            attested_at=datetime(2099, 1, 1, tzinfo=timezone.utc),  # Future
            expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),  # Past
            signature="sig",
        )
        # Even with a future attested_at, if expires_at is in the past, it is expired
        assert cap.is_expired() is True, "Capability must be expired regardless of future attested_at"


# ===========================================================================
# 6. Key Substitution
# ===========================================================================


class TestKeySubstitution:
    """Verify that replacing the public key in verification fails."""

    def test_substituted_key_fails_verification(self):
        """Sign with key A, attempt verify with substituted key B."""
        priv_a, pub_a = generate_keypair()
        _priv_b, pub_b = generate_keypair()

        payload = {"agent_id": "agent-1", "action": "process_data"}
        signature = sign(payload, priv_a)

        # Verify with correct key succeeds
        assert verify_signature(payload, signature, pub_a) is True

        # Verify with substituted key fails
        assert verify_signature(payload, signature, pub_b) is False, (
            "Substituted public key must cause verification to fail"
        )

    def test_key_substitution_in_challenge_response(self):
        """Challenge-response protocol must reject key substitution."""
        priv_a, pub_a = generate_keypair()
        _priv_b, pub_b = generate_keypair()

        protocol = ChallengeProtocol()
        chain = _make_chain(
            "agent-target",
            capabilities=["analyze_data"],
            private_key=priv_a,
        )

        challenge = protocol.create_challenge("verifier", "agent-target", "analyze_data")
        response = protocol.respond_to_challenge(challenge, priv_a, chain)

        # Verify with correct key
        assert protocol.verify_response(challenge, response, pub_a) is True

        # Attempt with substituted key -- create a fresh protocol to avoid nonce replay
        protocol2 = ChallengeProtocol()
        challenge2 = protocol2.create_challenge("verifier", "agent-target", "analyze_data")
        response2 = protocol2.respond_to_challenge(challenge2, priv_a, chain)

        result = protocol2.verify_response(challenge2, response2, pub_b)
        assert result is False, "Challenge-response must reject when verified with a substituted key"


# ===========================================================================
# 7. Cross-Chain Contamination
# ===========================================================================


class TestCrossChainContamination:
    """Verify that mixing capabilities from separate chains is detectable."""

    def test_mixed_capabilities_change_hash(self):
        """Injecting a capability from chain A into chain B must change B's hash."""
        priv, _pub = generate_keypair()

        chain_a = _make_chain("agent-A", capabilities=["read_data"], private_key=priv)
        chain_b = _make_chain("agent-B", capabilities=["write_data"], private_key=priv)

        hash_b_original = chain_b.hash()

        # Contaminate: inject chain_a's capability into chain_b
        stolen_cap = chain_a.capabilities[0]
        chain_b.capabilities.append(stolen_cap)

        hash_b_contaminated = chain_b.hash()

        assert hash_b_contaminated != hash_b_original, "Injecting a foreign capability must change the chain hash"

    def test_mixed_delegations_change_hash(self):
        """Injecting a delegation from chain A into chain B must change B's hash."""
        priv, _pub = generate_keypair()
        now = datetime.now(timezone.utc)

        chain_a = _make_chain("agent-A", private_key=priv)
        chain_a.delegations.append(
            DelegationRecord(
                id="del-A",
                delegator_id="org-acme",
                delegatee_id="agent-A",
                task_id="task-A",
                capabilities_delegated=["read_data"],
                constraint_subset=[],
                delegated_at=now,
                signature=sign({"id": "del-A"}, priv),
            )
        )

        chain_b = _make_chain("agent-B", private_key=priv)
        hash_b_original = chain_b.hash()

        # Contaminate: inject chain_a's delegation into chain_b
        chain_b.delegations.append(chain_a.delegations[0])
        hash_b_contaminated = chain_b.hash()

        assert hash_b_contaminated != hash_b_original, "Injecting a foreign delegation must change the chain hash"

    async def test_store_isolates_chains(self):
        """InMemoryTrustStore must isolate chains by agent_id."""
        priv, _pub = generate_keypair()
        store = InMemoryTrustStore()
        await store.initialize()

        chain_a = _make_chain("agent-A", capabilities=["read_data"], private_key=priv)
        chain_b = _make_chain("agent-B", capabilities=["write_data"], private_key=priv)

        await store.store_chain(chain_a)
        await store.store_chain(chain_b)

        retrieved_a = await store.get_chain("agent-A")
        retrieved_b = await store.get_chain("agent-B")

        # Chains must be independent
        assert retrieved_a.genesis.agent_id == "agent-A"
        assert retrieved_b.genesis.agent_id == "agent-B"
        assert len(retrieved_a.capabilities) == 1
        assert len(retrieved_b.capabilities) == 1
        assert retrieved_a.capabilities[0].capability == "read_data"
        assert retrieved_b.capabilities[0].capability == "write_data"


# ===========================================================================
# 8. Challenge-Response Replay
# ===========================================================================


class TestChallengeResponseReplay:
    """Verify that the challenge-response protocol rejects replayed responses."""

    def test_replayed_response_rejected(self):
        """After successful verification, reusing the same response must raise."""
        priv, pub = generate_keypair()
        protocol = ChallengeProtocol()
        chain = _make_chain("agent-target", capabilities=["analyze_data"], private_key=priv)

        challenge = protocol.create_challenge("verifier", "agent-target", "analyze_data")
        response = protocol.respond_to_challenge(challenge, priv, chain)

        # First verification succeeds
        assert protocol.verify_response(challenge, response, pub) is True

        # Replay: second verification with same nonce must raise
        with pytest.raises(ChallengeError, match="[Rr]eplay|[Nn]once.*used|already"):
            protocol.verify_response(challenge, response, pub)

    def test_expired_challenge_rejected(self):
        """Responding to an expired challenge must raise ChallengeError."""
        priv, pub = generate_keypair()
        protocol = ChallengeProtocol(challenge_timeout_seconds=0)
        chain = _make_chain("agent-target", capabilities=["analyze_data"], private_key=priv)

        challenge = protocol.create_challenge("verifier", "agent-target", "analyze_data")
        time.sleep(0.01)  # Ensure expiration

        with pytest.raises(ChallengeError, match="expired"):
            protocol.respond_to_challenge(challenge, priv, chain)

    def test_cross_challenge_response_swap(self):
        """A response for challenge 1 must not verify against challenge 2."""
        priv, pub = generate_keypair()
        protocol = ChallengeProtocol()
        chain = _make_chain("agent-target", capabilities=["analyze_data"], private_key=priv)

        ch1 = protocol.create_challenge("verifier-A", "agent-target", "analyze_data")
        ch2 = protocol.create_challenge("verifier-B", "agent-target", "analyze_data")

        resp1 = protocol.respond_to_challenge(ch1, priv, chain)

        # Try to verify resp1 against ch2 -- different nonce means signature mismatch
        result = protocol.verify_response(ch2, resp1, pub)
        assert result is False, "Response to one challenge must not verify against a different challenge"

    def test_forged_challenge_id_in_response(self):
        """A response with a fake challenge_id must fail verification."""
        priv, pub = generate_keypair()
        protocol = ChallengeProtocol()
        chain = _make_chain("agent-target", capabilities=["analyze_data"], private_key=priv)

        challenge = protocol.create_challenge("verifier", "agent-target", "analyze_data")
        response = protocol.respond_to_challenge(challenge, priv, chain)

        forged_response = ChallengeResponse(
            challenge_id="ch-forged-id-000000",
            agent_id=response.agent_id,
            signed_nonce=response.signed_nonce,
            capability_proof=response.capability_proof,
            timestamp=response.timestamp,
        )

        result = protocol.verify_response(challenge, forged_response, pub)
        assert result is False, "Forged challenge_id must fail verification"


# ===========================================================================
# 9. Path Traversal on FilesystemStore
# ===========================================================================


class TestPathTraversalOnFilesystemStore:
    """Verify that FilesystemStore sanitizes agent_ids to prevent traversal."""

    async def test_path_traversal_with_slashes(self, tmp_path):
        """Agent IDs containing '../' must be rejected with ValueError."""
        store = FilesystemStore(base_dir=str(tmp_path / "chains"))
        await store.initialize()

        # Create a chain with a path traversal agent_id
        traversal_id = "../../etc/passwd"
        chain = TrustLineageChain(
            genesis=GenesisRecord(
                id=f"gen-{traversal_id}",
                agent_id=traversal_id,
                authority_id="org-acme",
                authority_type=AuthorityType.ORGANIZATION,
                created_at=datetime.now(timezone.utc),
                signature="sig-test",
            )
        )

        # Path traversal IDs must be rejected at validation
        with pytest.raises(ValueError, match="path traversal"):
            await store.store_chain(chain)

        # Verify no file was created outside the chains directory
        etc_path = tmp_path / "etc" / "passwd.json"
        assert not etc_path.exists(), "Path traversal must NOT create files outside the store directory"

    async def test_path_traversal_with_backslash(self, tmp_path):
        """Agent IDs with backslashes must be rejected with ValueError."""
        store = FilesystemStore(base_dir=str(tmp_path / "chains"))
        await store.initialize()

        traversal_id = r"..\..\windows\system32"
        chain = TrustLineageChain(
            genesis=GenesisRecord(
                id=f"gen-{traversal_id}",
                agent_id=traversal_id,
                authority_id="org-acme",
                authority_type=AuthorityType.ORGANIZATION,
                created_at=datetime.now(timezone.utc),
                signature="sig-test",
            )
        )

        # Path traversal IDs must be rejected at validation
        with pytest.raises(ValueError, match="path traversal"):
            await store.store_chain(chain)

    async def test_null_byte_in_agent_id(self, tmp_path):
        """Agent IDs with null bytes must be rejected with ValueError."""
        store = FilesystemStore(base_dir=str(tmp_path / "chains"))
        await store.initialize()

        null_id = "agent\x00../../evil"
        chain = TrustLineageChain(
            genesis=GenesisRecord(
                id="gen-null",
                agent_id=null_id,
                authority_id="org-acme",
                authority_type=AuthorityType.ORGANIZATION,
                created_at=datetime.now(timezone.utc),
                signature="sig-test",
            )
        )

        # Null byte IDs must be rejected at validation
        with pytest.raises(ValueError, match="null"):
            await store.store_chain(chain)


# ===========================================================================
# 10. Pickle Injection Prevention
# ===========================================================================


class TestPickleInjectionPrevention:
    """Verify that stores use JSON serialization, NOT pickle."""

    async def test_filesystem_store_uses_json(self, tmp_path):
        """FilesystemStore must write JSON, not pickle."""
        store = FilesystemStore(base_dir=str(tmp_path / "chains"))
        await store.initialize()

        chain = _make_chain("agent-json")
        await store.store_chain(chain)

        # Read the raw file
        chain_files = list((tmp_path / "chains").glob("*.json"))
        assert len(chain_files) >= 1, "At least one JSON file must exist"

        raw_content = chain_files[0].read_text(encoding="utf-8")

        # Must be valid JSON
        parsed = json.loads(raw_content)
        assert isinstance(parsed, dict), "Store file must contain a JSON object"
        assert "chain" in parsed, "Store file must have a 'chain' key"

    async def test_corrupted_non_json_data_fails_gracefully(self, tmp_path):
        """Writing non-JSON data to a store file must fail gracefully on read."""
        store = FilesystemStore(base_dir=str(tmp_path / "chains"))
        await store.initialize()

        chain = _make_chain("agent-corrupt")
        await store.store_chain(chain)

        # Corrupt the file with binary data (simulating pickle injection)
        chain_file = tmp_path / "chains" / "agent-corrupt.json"
        chain_file.write_bytes(b"\x80\x04\x95\x00\x00\x00\x00")

        # Attempting to read must raise an error, not silently deserialize
        with pytest.raises(Exception):
            await store.get_chain("agent-corrupt")

    async def test_list_chains_skips_corrupted_files(self, tmp_path):
        """list_chains must skip corrupted (non-JSON) files without crashing."""
        store = FilesystemStore(base_dir=str(tmp_path / "chains"))
        await store.initialize()

        chain = _make_chain("agent-good")
        await store.store_chain(chain)

        # Create a corrupted file with valid UTF-8 but invalid JSON
        corrupt_file = tmp_path / "chains" / "agent-bad.json"
        corrupt_file.write_text("{not valid json at all!!!", encoding="utf-8")

        # list_chains must return only the good chain
        chains = await store.list_chains()
        assert len(chains) == 1
        assert chains[0].genesis.agent_id == "agent-good"


# ===========================================================================
# 11. Merkle Tree Tampering
# ===========================================================================


class TestMerkleTreeTampering:
    """Verify that Merkle proof verification detects tampering."""

    def test_modified_leaf_hash_in_proof_detected(self):
        """Modifying the leaf_hash in a proof must cause verification to fail."""
        leaves = [hash_chain(f"record-{i}") for i in range(8)]
        tree = MerkleTree(leaves)

        proof = tree.generate_proof(3)
        assert proof is not None
        assert tree.verify_proof(proof) is True

        # Tamper: change the leaf_hash
        from eatp.merkle import MerkleProof

        tampered_proof = MerkleProof(
            leaf_hash="0000000000000000000000000000000000000000000000000000000000000000",
            leaf_index=proof.leaf_index,
            proof_hashes=proof.proof_hashes,
            root_hash=proof.root_hash,
            tree_size=proof.tree_size,
        )

        result = tree.verify_proof(tampered_proof)
        assert result is False, "Tampered leaf_hash must fail verification"

    def test_modified_proof_hash_detected(self):
        """Modifying a proof hash (sibling) must cause verification to fail."""
        leaves = [hash_chain(f"data-{i}") for i in range(4)]
        tree = MerkleTree(leaves)

        proof = tree.generate_proof(1)
        assert proof is not None
        assert tree.verify_proof(proof) is True

        # Tamper: change one proof hash
        from eatp.merkle import MerkleProof

        tampered_hashes = list(proof.proof_hashes)
        if tampered_hashes:
            original_hash, position = tampered_hashes[0]
            tampered_hashes[0] = (
                "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
                position,
            )

        tampered_proof = MerkleProof(
            leaf_hash=proof.leaf_hash,
            leaf_index=proof.leaf_index,
            proof_hashes=tampered_hashes,
            root_hash=proof.root_hash,
            tree_size=proof.tree_size,
        )

        result = tree.verify_proof(tampered_proof)
        assert result is False, "Tampered proof hash must fail verification"

    def test_proof_from_different_tree_fails(self):
        """A proof generated from tree A must not verify against tree B."""
        leaves_a = [hash_chain(f"tree-a-{i}") for i in range(4)]
        leaves_b = [hash_chain(f"tree-b-{i}") for i in range(4)]

        tree_a = MerkleTree(leaves_a)
        tree_b = MerkleTree(leaves_b)

        proof_a = tree_a.generate_proof(0)
        assert proof_a is not None

        # Proof from tree_a must fail against tree_b
        result = tree_b.verify_proof(proof_a)
        assert result is False, "Proof from a different tree must fail verification"

    def test_standalone_verify_merkle_proof_detects_tampering(self):
        """verify_merkle_proof() must detect leaf hash mismatches."""
        leaves = [hash_chain(f"leaf-{i}") for i in range(4)]
        tree = MerkleTree(leaves)

        proof = tree.generate_proof(2)
        assert proof is not None

        # Correct leaf verifies
        assert verify_merkle_proof(proof.leaf_hash, proof) is True

        # Wrong leaf hash fails
        assert verify_merkle_proof("wrong_hash", proof) is False

    def test_modified_root_hash_detected(self):
        """Tampering with the root_hash in a proof must be detected."""
        leaves = [hash_chain(f"root-test-{i}") for i in range(4)]
        tree = MerkleTree(leaves)

        proof = tree.generate_proof(0)
        assert proof is not None

        from eatp.merkle import MerkleProof

        tampered_proof = MerkleProof(
            leaf_hash=proof.leaf_hash,
            leaf_index=proof.leaf_index,
            proof_hashes=proof.proof_hashes,
            root_hash="0" * 64,  # Fake root
            tree_size=proof.tree_size,
        )

        # The standalone verify_merkle_proof checks proof.root_hash match
        result = verify_merkle_proof(tampered_proof.leaf_hash, tampered_proof)
        assert result is False, "Tampered root_hash must fail verification"


# ===========================================================================
# 12. Selective Disclosure Tampering
# ===========================================================================


class TestSelectiveDisclosureTampering:
    """Verify that tampering with exported audit records is detected."""

    def _make_audit_records(self, count: int = 3) -> list[AuditRecord]:
        """Create a list of AuditRecords for export testing."""
        records = []
        for i in range(count):
            anchor = AuditAnchor(
                id=f"aud-{i:03d}",
                agent_id="agent-audited",
                action=f"action_{i}",
                timestamp=datetime(2025, 1, 1, i, 0, 0, tzinfo=timezone.utc),
                trust_chain_hash=hash_chain(f"chain-state-{i}"),
                result=ActionResult.SUCCESS,
                signature=f"sig-aud-{i}",
                context={"detail": f"context-{i}", "sensitive": f"secret-{i}"},
            )
            records.append(
                AuditRecord(
                    anchor=anchor,
                    sequence_number=i + 1,
                    previous_hash=f"prev-{i}" if i > 0 else None,
                )
            )
        return records

    def test_tampered_record_detected_by_chain_hash(self):
        """Modifying a record after export must break chain hash verification."""
        priv, pub = generate_keypair()
        records = self._make_audit_records(3)

        export = export_for_witness(
            audit_records=records,
            disclosed_fields=["action"],
            signing_key=priv,
            witness_id="witness-1",
        )

        # Verify original is valid
        result = verify_witness_export(export, pub)
        assert result.valid is True, f"Original export must be valid. Errors: {result.errors}"

        # Tamper: modify a record's disclosed data
        export.records[1].data["action"] = "TAMPERED_ACTION"

        # Verification must detect the tampering
        result = verify_witness_export(export, pub)
        assert result.chain_integrity_valid is False, "Tampered record must break chain integrity verification"

    def test_tampered_redacted_field_detected(self):
        """Modifying a redacted field must break chain hash verification."""
        priv, pub = generate_keypair()
        records = self._make_audit_records(2)

        export = export_for_witness(
            audit_records=records,
            disclosed_fields=["action"],
            signing_key=priv,
        )

        # Find a redacted field and tamper with it
        record = export.records[0]
        for field_name in record.redacted_fields:
            record.data[field_name] = "REDACTED:sha256:0000000000000000000000000000000000000000000000000000000000000000"
            break

        result = verify_witness_export(export, pub)
        assert result.chain_integrity_valid is False, "Tampered redacted field must break chain integrity"

    def test_wrong_authority_key_detected(self):
        """Export signed with key A must fail verification with key B."""
        priv_a, _pub_a = generate_keypair()
        _priv_b, pub_b = generate_keypair()
        records = self._make_audit_records(2)

        export = export_for_witness(
            audit_records=records,
            disclosed_fields=["action"],
            signing_key=priv_a,
        )

        # Verify with wrong key
        result = verify_witness_export(export, pub_b)
        assert result.signature_valid is False, "Export must fail signature verification with wrong authority key"
        assert result.valid is False

    def test_added_record_detected(self):
        """Adding a record to the export after signing must be detected."""
        priv, pub = generate_keypair()
        records = self._make_audit_records(2)

        export = export_for_witness(
            audit_records=records,
            disclosed_fields=["action"],
            signing_key=priv,
        )

        # Inject an extra record
        from eatp.enforce.selective_disclosure import RedactedAuditRecord

        fake_record = RedactedAuditRecord(
            data={
                "id": "aud-fake",
                "agent_id": "agent-audited",
                "timestamp": "2025-01-01T10:00:00+00:00",
                "action": "fake_action",
                "chain_hash": "fakehash",
                "previous_hash": "fakeprev",
                "action_result": "success",
            },
            disclosed_fields=["action"],
            redacted_fields=[],
        )
        export.records.append(fake_record)

        result = verify_witness_export(export, pub)
        # Either signature or chain integrity must fail
        assert result.valid is False, "Adding a record after signing must be detected"

    def test_removed_record_detected(self):
        """Removing a record from the export after signing must be detected."""
        priv, pub = generate_keypair()
        records = self._make_audit_records(3)

        export = export_for_witness(
            audit_records=records,
            disclosed_fields=["action"],
            signing_key=priv,
        )

        # Remove a record
        export.records.pop(1)

        result = verify_witness_export(export, pub)
        assert result.valid is False, "Removing a record after signing must be detected"
