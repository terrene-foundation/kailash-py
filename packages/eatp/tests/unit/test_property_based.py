"""
Property-based tests for the EATP SDK using Hypothesis.

Tests cryptographic invariants, serialization determinism, hash integrity,
Merkle tree properties, and trust chain round-trip serialization using
generative strategies that exercise edge cases automatically.

Covers:
- Signature integrity (sign/verify round-trip, tamper detection)
- Serialization determinism (serialize_for_signing canonical output)
- Hash chain integrity (determinism, collision resistance)
- Merkle tree properties (root determinism, proof generation/verification, tamper detection)
- TrustLineageChain serialization round-trip (to_dict/from_dict equivalence)
- Temporal consistency (is_expired correctness for past/future/None)
- Hash trust chain state determinism and sensitivity to input changes
- DID generation determinism
"""

import hashlib
from datetime import datetime, timedelta, timezone

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from eatp.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    Constraint,
    ConstraintEnvelope,
    ConstraintType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from eatp.crypto import (
    generate_keypair,
    hash_chain,
    hash_trust_chain_state,
    serialize_for_signing,
    sign,
    verify_signature,
)
from eatp.merkle import MerkleTree, verify_merkle_proof

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Identifiers safe for use across all EATP data structures
valid_id = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=1,
    max_size=50,
)

# Payloads suitable for signing operations (non-empty strings)
signing_payload_str = st.text(min_size=1, max_size=200)

# Dict payloads with JSON-safe values (no NaN which breaks JSON equality)
payload_dict = st.dictionaries(
    keys=st.text(min_size=1, max_size=20),
    values=st.one_of(
        st.text(max_size=50),
        st.integers(min_value=-(2**53), max_value=2**53),
        st.floats(allow_nan=False, allow_infinity=False),
        st.booleans(),
    ),
    min_size=1,
    max_size=10,
)

# Hex-encoded SHA-256 hash strings (64 hex characters)
hash_string = st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)

# Lists of hash strings for Merkle tree construction
hash_list = st.lists(hash_string, min_size=1, max_size=32)


# ---------------------------------------------------------------------------
# 1. Signature Integrity
# ---------------------------------------------------------------------------


class TestSignatureIntegrity:
    """Property-based tests for Ed25519 sign/verify round-trip."""

    @given(payload=signing_payload_str)
    @settings(max_examples=200)
    def test_sign_then_verify_returns_true(self, payload: str) -> None:
        """For any payload and valid keypair, signing then verifying succeeds."""
        private_key, public_key = generate_keypair()
        signature = sign(payload, private_key)
        assert verify_signature(payload, signature, public_key) is True

    @given(payload=payload_dict)
    @settings(max_examples=200)
    def test_sign_then_verify_dict_returns_true(self, payload: dict) -> None:
        """For any dict payload and valid keypair, signing then verifying succeeds."""
        private_key, public_key = generate_keypair()
        signature = sign(payload, private_key)
        assert verify_signature(payload, signature, public_key) is True

    @given(
        payload=signing_payload_str,
        tampered=signing_payload_str,
    )
    @settings(max_examples=200)
    def test_tampered_payload_fails_verification(
        self, payload: str, tampered: str
    ) -> None:
        """Modifying the payload after signing must cause verification to fail."""
        assume(payload != tampered)
        private_key, public_key = generate_keypair()
        signature = sign(payload, private_key)
        assert verify_signature(tampered, signature, public_key) is False

    @given(payload=signing_payload_str)
    @settings(max_examples=100)
    def test_wrong_key_fails_verification(self, payload: str) -> None:
        """A signature verified with a different keypair must fail."""
        priv1, _pub1 = generate_keypair()
        _priv2, pub2 = generate_keypair()
        signature = sign(payload, priv1)
        assert verify_signature(payload, signature, pub2) is False


# ---------------------------------------------------------------------------
# 2. Serialization Determinism
# ---------------------------------------------------------------------------


class TestSerializationDeterminism:
    """Property-based tests for serialize_for_signing canonical output."""

    @given(data=payload_dict)
    @settings(max_examples=200)
    def test_serialize_is_deterministic(self, data: dict) -> None:
        """Serializing the same dict twice must produce identical output."""
        result1 = serialize_for_signing(data)
        result2 = serialize_for_signing(data)
        assert result1 == result2

    @given(data=payload_dict)
    @settings(max_examples=200)
    def test_key_order_does_not_matter(self, data: dict) -> None:
        """Dicts with the same keys in different insertion order serialize identically."""
        assume(len(data) >= 2)
        reversed_data = dict(reversed(list(data.items())))
        assert serialize_for_signing(data) == serialize_for_signing(reversed_data)

    @given(
        keys=st.lists(
            st.text(min_size=1, max_size=10), min_size=2, max_size=5, unique=True
        ),
        values=st.lists(st.integers(), min_size=2, max_size=5),
    )
    @settings(max_examples=200)
    def test_different_dicts_serialize_differently(
        self, keys: list, values: list
    ) -> None:
        """Two dicts with different content must serialize to different strings."""
        # Build two dicts that differ by at least one value
        n = min(len(keys), len(values))
        assume(n >= 2)
        dict1 = {keys[i]: values[i] for i in range(n)}
        dict2 = {keys[i]: values[i] for i in range(n)}
        dict2[keys[0]] = values[0] + 1  # Ensure they differ
        assert serialize_for_signing(dict1) != serialize_for_signing(dict2)


# ---------------------------------------------------------------------------
# 3. Hash Chain Integrity
# ---------------------------------------------------------------------------


class TestHashChainIntegrity:
    """Property-based tests for hash_chain determinism and collision resistance."""

    @given(data=signing_payload_str)
    @settings(max_examples=200)
    def test_hash_chain_string_deterministic(self, data: str) -> None:
        """Hashing the same string twice must produce the same result."""
        assert hash_chain(data) == hash_chain(data)

    @given(data=payload_dict)
    @settings(max_examples=200)
    def test_hash_chain_dict_deterministic(self, data: dict) -> None:
        """Hashing the same dict twice must produce the same result."""
        assert hash_chain(data) == hash_chain(data)

    @given(data=st.binary(min_size=1, max_size=200))
    @settings(max_examples=200)
    def test_hash_chain_bytes_deterministic(self, data: bytes) -> None:
        """Hashing the same bytes twice must produce the same result."""
        assert hash_chain(data) == hash_chain(data)

    @given(data=signing_payload_str)
    @settings(max_examples=200)
    def test_hash_chain_produces_valid_hex(self, data: str) -> None:
        """hash_chain must return a 64-character lowercase hex string."""
        result = hash_chain(data)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    @given(
        data=st.lists(
            st.text(
                min_size=1,
                max_size=50,
                alphabet=st.characters(
                    min_codepoint=32,
                    blacklist_categories=("Cs",),  # exclude surrogates
                ),
            ),
            min_size=100,
            max_size=150,
            unique=True,
        )
    )
    @settings(max_examples=10)
    def test_hash_chain_collision_resistance(self, data: list) -> None:
        """100+ unique inputs must produce 100+ unique hashes (no collisions)."""
        hashes = [hash_chain(item) for item in data]
        assert len(set(hashes)) == len(hashes), (
            f"Hash collision detected among {len(data)} inputs: "
            f"{len(data) - len(set(hashes))} collision(s)"
        )


# ---------------------------------------------------------------------------
# 4. Merkle Tree Properties
# ---------------------------------------------------------------------------


class TestMerkleTreeProperties:
    """Property-based tests for Merkle tree determinism, proofs, and tamper detection."""

    @given(leaves=hash_list)
    @settings(max_examples=200)
    def test_root_hash_is_deterministic(self, leaves: list) -> None:
        """Building a Merkle tree from the same leaves must produce the same root."""
        tree1 = MerkleTree(leaves)
        tree2 = MerkleTree(leaves)
        assert tree1.root_hash == tree2.root_hash

    @given(leaves=hash_list)
    @settings(max_examples=200)
    def test_root_hash_is_not_none(self, leaves: list) -> None:
        """A non-empty leaf list must produce a non-None root hash."""
        tree = MerkleTree(leaves)
        assert tree.root_hash is not None

    @given(data=st.data())
    @settings(max_examples=200)
    def test_generate_and_verify_proof_succeeds(self, data) -> None:
        """For any valid index, generate_proof then verify_proof must return True."""
        leaves = data.draw(hash_list)
        tree = MerkleTree(leaves)
        index = data.draw(st.integers(min_value=0, max_value=len(leaves) - 1))
        proof = tree.generate_proof(index)
        assert proof is not None
        assert tree.verify_proof(proof) is True

    @given(data=st.data())
    @settings(max_examples=200)
    def test_standalone_verify_merkle_proof_succeeds(self, data) -> None:
        """verify_merkle_proof (standalone) must return True for a valid proof."""
        leaves = data.draw(hash_list)
        tree = MerkleTree(leaves)
        index = data.draw(st.integers(min_value=0, max_value=len(leaves) - 1))
        proof = tree.generate_proof(index)
        assert proof is not None
        assert verify_merkle_proof(proof.leaf_hash, proof) is True

    @given(data=st.data())
    @settings(max_examples=200)
    def test_modifying_leaf_changes_root(self, data) -> None:
        """Changing any single leaf must produce a different root hash."""
        leaves = data.draw(st.lists(hash_string, min_size=2, max_size=32))
        index = data.draw(st.integers(min_value=0, max_value=len(leaves) - 1))
        replacement = data.draw(hash_string)
        assume(replacement != leaves[index])

        original_tree = MerkleTree(leaves)
        modified_leaves = list(leaves)
        modified_leaves[index] = replacement
        modified_tree = MerkleTree(modified_leaves)

        assert original_tree.root_hash != modified_tree.root_hash

    @given(data=st.data())
    @settings(max_examples=200)
    def test_proof_from_modified_tree_fails_original(self, data) -> None:
        """A proof generated from the original tree must fail on a modified tree."""
        leaves = data.draw(st.lists(hash_string, min_size=2, max_size=16))
        index = data.draw(st.integers(min_value=0, max_value=len(leaves) - 1))

        original_tree = MerkleTree(leaves)
        proof = original_tree.generate_proof(index)
        assert proof is not None

        # Modify a leaf and rebuild
        modified_leaves = list(leaves)
        # Pick a different leaf to modify (or the same one)
        mod_index = data.draw(st.integers(min_value=0, max_value=len(leaves) - 1))
        new_hash = data.draw(hash_string)
        assume(new_hash != modified_leaves[mod_index])
        modified_leaves[mod_index] = new_hash
        modified_tree = MerkleTree(modified_leaves)

        # The original proof must NOT verify against the modified tree
        assert modified_tree.verify_proof(proof) is False

    @given(leaves=hash_list)
    @settings(max_examples=200)
    def test_proof_leaf_hash_matches_tree_leaf(self, leaves: list) -> None:
        """The proof's leaf_hash must match the leaf stored in the tree."""
        tree = MerkleTree(leaves)
        for i in range(len(leaves)):
            proof = tree.generate_proof(i)
            assert proof is not None
            assert proof.leaf_hash == leaves[i]


# ---------------------------------------------------------------------------
# 5. TrustLineageChain Serialization Round-Trip
# ---------------------------------------------------------------------------


def _make_genesis(gen_id: str, agent_id: str, authority_id: str) -> GenesisRecord:
    """Helper to build a minimal GenesisRecord for property tests."""
    return GenesisRecord(
        id=gen_id,
        agent_id=agent_id,
        authority_id=authority_id,
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        signature="test-sig",
        signature_algorithm="Ed25519",
        metadata={},
    )


def _make_capability(
    cap_id: str, capability: str, attester_id: str
) -> CapabilityAttestation:
    """Helper to build a minimal CapabilityAttestation for property tests."""
    return CapabilityAttestation(
        id=cap_id,
        capability=capability,
        capability_type=CapabilityType.ACTION,
        constraints=["read_only"],
        attester_id=attester_id,
        attested_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        signature="test-sig",
    )


def _make_delegation(
    del_id: str, delegator: str, delegatee: str, task_id: str
) -> DelegationRecord:
    """Helper to build a minimal DelegationRecord for property tests."""
    return DelegationRecord(
        id=del_id,
        delegator_id=delegator,
        delegatee_id=delegatee,
        task_id=task_id,
        capabilities_delegated=["read_data"],
        constraint_subset=["read_only"],
        delegated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        signature="test-sig",
    )


class TestTrustLineageChainRoundTrip:
    """Property-based tests for TrustLineageChain to_dict/from_dict equivalence."""

    @given(
        gen_id=valid_id,
        agent_id=valid_id,
        authority_id=valid_id,
    )
    @settings(max_examples=200)
    def test_genesis_only_round_trip(
        self, gen_id: str, agent_id: str, authority_id: str
    ) -> None:
        """A chain with only a genesis record survives to_dict/from_dict."""
        genesis = _make_genesis(gen_id, agent_id, authority_id)
        chain = TrustLineageChain(genesis=genesis)
        restored = TrustLineageChain.from_dict(chain.to_dict())

        assert restored.genesis.id == chain.genesis.id
        assert restored.genesis.agent_id == chain.genesis.agent_id
        assert restored.genesis.authority_id == chain.genesis.authority_id
        assert restored.genesis.authority_type == chain.genesis.authority_type
        assert restored.genesis.created_at == chain.genesis.created_at
        assert restored.genesis.signature_algorithm == chain.genesis.signature_algorithm

    @given(
        gen_id=valid_id,
        agent_id=valid_id,
        authority_id=valid_id,
        cap_id=valid_id,
        capability=valid_id,
    )
    @settings(max_examples=200)
    def test_chain_with_capability_round_trip(
        self,
        gen_id: str,
        agent_id: str,
        authority_id: str,
        cap_id: str,
        capability: str,
    ) -> None:
        """A chain with genesis + capability survives to_dict/from_dict."""
        genesis = _make_genesis(gen_id, agent_id, authority_id)
        cap = _make_capability(cap_id, capability, authority_id)
        chain = TrustLineageChain(genesis=genesis, capabilities=[cap])
        restored = TrustLineageChain.from_dict(chain.to_dict())

        assert len(restored.capabilities) == 1
        assert restored.capabilities[0].id == cap.id
        assert restored.capabilities[0].capability == cap.capability
        assert restored.capabilities[0].capability_type == cap.capability_type

    @given(
        gen_id=valid_id,
        agent_id=valid_id,
        authority_id=valid_id,
        del_id=valid_id,
        delegatee=valid_id,
        task_id=valid_id,
    )
    @settings(max_examples=200)
    def test_chain_with_delegation_round_trip(
        self,
        gen_id: str,
        agent_id: str,
        authority_id: str,
        del_id: str,
        delegatee: str,
        task_id: str,
    ) -> None:
        """A chain with genesis + delegation survives to_dict/from_dict."""
        genesis = _make_genesis(gen_id, agent_id, authority_id)
        delegation = _make_delegation(del_id, agent_id, delegatee, task_id)
        chain = TrustLineageChain(genesis=genesis, delegations=[delegation])
        restored = TrustLineageChain.from_dict(chain.to_dict())

        assert len(restored.delegations) == 1
        assert restored.delegations[0].id == delegation.id
        assert restored.delegations[0].delegator_id == delegation.delegator_id
        assert restored.delegations[0].delegatee_id == delegation.delegatee_id
        assert restored.delegations[0].task_id == delegation.task_id

    @given(
        gen_id=valid_id,
        agent_id=valid_id,
        authority_id=valid_id,
    )
    @settings(max_examples=200)
    def test_chain_hash_survives_round_trip(
        self, gen_id: str, agent_id: str, authority_id: str
    ) -> None:
        """The chain hash must be the same before and after serialization round-trip."""
        genesis = _make_genesis(gen_id, agent_id, authority_id)
        chain = TrustLineageChain(genesis=genesis)
        original_hash = chain.hash()
        restored = TrustLineageChain.from_dict(chain.to_dict())
        restored_hash = restored.hash()
        assert original_hash == restored_hash


# ---------------------------------------------------------------------------
# 6. Temporal Consistency
# ---------------------------------------------------------------------------


class TestTemporalConsistency:
    """Property-based tests for is_expired behavior on records with expiration."""

    @given(
        seconds_ago=st.integers(min_value=1, max_value=365 * 24 * 3600),
    )
    @settings(max_examples=200)
    def test_genesis_expired_in_past(self, seconds_ago: int) -> None:
        """A GenesisRecord with expires_at in the past must report is_expired=True."""
        expires_at = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
        record = GenesisRecord(
            id="gen-test",
            agent_id="agent-test",
            authority_id="auth-test",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            signature="sig",
            expires_at=expires_at,
        )
        assert record.is_expired() is True

    @given(
        seconds_ahead=st.integers(min_value=60, max_value=365 * 24 * 3600),
    )
    @settings(max_examples=200)
    def test_genesis_not_expired_in_future(self, seconds_ahead: int) -> None:
        """A GenesisRecord with expires_at in the future must report is_expired=False."""
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=seconds_ahead)
        record = GenesisRecord(
            id="gen-test",
            agent_id="agent-test",
            authority_id="auth-test",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            signature="sig",
            expires_at=expires_at,
        )
        assert record.is_expired() is False

    @settings(max_examples=50)
    @given(agent_id=valid_id)
    def test_genesis_no_expiry_never_expires(self, agent_id: str) -> None:
        """A GenesisRecord with expires_at=None must never report as expired."""
        record = GenesisRecord(
            id="gen-test",
            agent_id=agent_id,
            authority_id="auth-test",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            signature="sig",
            expires_at=None,
        )
        assert record.is_expired() is False

    @given(
        seconds_ago=st.integers(min_value=1, max_value=365 * 24 * 3600),
    )
    @settings(max_examples=200)
    def test_capability_expired_in_past(self, seconds_ago: int) -> None:
        """A CapabilityAttestation with expires_at in the past is expired."""
        expires_at = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
        cap = CapabilityAttestation(
            id="cap-test",
            capability="read_data",
            capability_type=CapabilityType.ACCESS,
            constraints=[],
            attester_id="auth-test",
            attested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            signature="sig",
            expires_at=expires_at,
        )
        assert cap.is_expired() is True

    @given(
        seconds_ahead=st.integers(min_value=60, max_value=365 * 24 * 3600),
    )
    @settings(max_examples=200)
    def test_delegation_not_expired_in_future(self, seconds_ahead: int) -> None:
        """A DelegationRecord with expires_at in the future is not expired."""
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=seconds_ahead)
        delegation = DelegationRecord(
            id="del-test",
            delegator_id="agent-a",
            delegatee_id="agent-b",
            task_id="task-1",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            signature="sig",
            expires_at=expires_at,
        )
        assert delegation.is_expired() is False


# ---------------------------------------------------------------------------
# 7. Hash Trust Chain State Determinism
# ---------------------------------------------------------------------------


class TestHashTrustChainState:
    """Property-based tests for hash_trust_chain_state determinism and sensitivity."""

    @given(
        genesis_id=valid_id,
        cap_ids=st.lists(valid_id, min_size=0, max_size=5),
        del_ids=st.lists(valid_id, min_size=0, max_size=5),
        constraint_hash=valid_id,
    )
    @settings(max_examples=200)
    def test_hash_trust_chain_state_deterministic(
        self,
        genesis_id: str,
        cap_ids: list,
        del_ids: list,
        constraint_hash: str,
    ) -> None:
        """hash_trust_chain_state called twice with the same args must return the same hash."""
        h1 = hash_trust_chain_state(genesis_id, cap_ids, del_ids, constraint_hash)
        h2 = hash_trust_chain_state(genesis_id, cap_ids, del_ids, constraint_hash)
        assert h1 == h2

    @given(
        genesis_id=valid_id,
        cap_ids=st.lists(valid_id, min_size=0, max_size=5),
        del_ids=st.lists(valid_id, min_size=0, max_size=5),
        constraint_hash=valid_id,
    )
    @settings(max_examples=200)
    def test_hash_trust_chain_state_produces_valid_hex(
        self,
        genesis_id: str,
        cap_ids: list,
        del_ids: list,
        constraint_hash: str,
    ) -> None:
        """hash_trust_chain_state must return a 64-character hex string."""
        result = hash_trust_chain_state(genesis_id, cap_ids, del_ids, constraint_hash)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    @given(
        genesis_id=valid_id,
        cap_ids=st.lists(valid_id, min_size=0, max_size=5),
        del_ids=st.lists(valid_id, min_size=0, max_size=5),
        constraint_hash=valid_id,
        extra_cap=valid_id,
    )
    @settings(max_examples=200)
    def test_adding_capability_changes_hash(
        self,
        genesis_id: str,
        cap_ids: list,
        del_ids: list,
        constraint_hash: str,
        extra_cap: str,
    ) -> None:
        """Adding a new capability ID to the list must change the state hash."""
        assume(extra_cap not in cap_ids)
        h_before = hash_trust_chain_state(genesis_id, cap_ids, del_ids, constraint_hash)
        h_after = hash_trust_chain_state(
            genesis_id, cap_ids + [extra_cap], del_ids, constraint_hash
        )
        assert h_before != h_after

    @given(
        genesis_id1=valid_id,
        genesis_id2=valid_id,
        constraint_hash=valid_id,
    )
    @settings(max_examples=200)
    def test_different_genesis_ids_produce_different_hashes(
        self,
        genesis_id1: str,
        genesis_id2: str,
        constraint_hash: str,
    ) -> None:
        """Different genesis IDs must produce different state hashes."""
        assume(genesis_id1 != genesis_id2)
        h1 = hash_trust_chain_state(genesis_id1, [], [], constraint_hash)
        h2 = hash_trust_chain_state(genesis_id2, [], [], constraint_hash)
        assert h1 != h2

    @given(
        genesis_id=valid_id,
        cap_ids=st.lists(valid_id, min_size=2, max_size=5, unique=True),
        del_ids=st.lists(valid_id, min_size=0, max_size=5),
        constraint_hash=valid_id,
    )
    @settings(max_examples=200)
    def test_capability_order_does_not_matter(
        self,
        genesis_id: str,
        cap_ids: list,
        del_ids: list,
        constraint_hash: str,
    ) -> None:
        """The hash must be order-independent for capability_ids (they are sorted internally)."""
        h1 = hash_trust_chain_state(genesis_id, cap_ids, del_ids, constraint_hash)
        h2 = hash_trust_chain_state(
            genesis_id, list(reversed(cap_ids)), del_ids, constraint_hash
        )
        assert h1 == h2


# ---------------------------------------------------------------------------
# 8. DID Generation Determinism
# ---------------------------------------------------------------------------


class TestDIDGenerationDeterminism:
    """Property-based tests for DID string generation."""

    @given(agent_id=valid_id)
    @settings(max_examples=200)
    def test_generate_did_deterministic(self, agent_id: str) -> None:
        """generate_did must produce the same DID for the same agent_id."""
        from eatp.interop.did import generate_did

        did1 = generate_did(agent_id)
        did2 = generate_did(agent_id)
        assert did1 == did2

    @given(agent_id=valid_id)
    @settings(max_examples=200)
    def test_generate_did_format(self, agent_id: str) -> None:
        """generate_did must produce a DID matching 'did:eatp:<agent_id>'."""
        from eatp.interop.did import generate_did

        did = generate_did(agent_id)
        assert did == f"did:eatp:{agent_id}"

    @given(agent_id1=valid_id, agent_id2=valid_id)
    @settings(max_examples=200)
    def test_different_agent_ids_produce_different_dids(
        self, agent_id1: str, agent_id2: str
    ) -> None:
        """Different agent IDs must produce different DIDs."""
        assume(agent_id1 != agent_id2)
        from eatp.interop.did import generate_did

        assert generate_did(agent_id1) != generate_did(agent_id2)

    @settings(max_examples=100)
    @given(data=st.data())
    def test_generate_did_key_deterministic(self, data) -> None:
        """generate_did_key must be deterministic for the same public key."""
        from eatp.interop.did import generate_did_key

        _priv, pub = generate_keypair()
        did1 = generate_did_key(pub)
        did2 = generate_did_key(pub)
        assert did1 == did2
        assert did1.startswith("did:key:z")
