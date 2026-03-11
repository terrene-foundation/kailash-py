"""
Unit tests for CARE-012: Merkle Tree Audit Verification.

Tests the Merkle tree implementation for efficient audit log verification:
- MerkleNode creation and properties
- MerkleTree construction and operations
- MerkleProof generation and verification
- Integration with AuditRecord
- Edge cases and error handling
"""

import hashlib
from datetime import datetime, timezone

import pytest
from kaizen.trust.audit_store import AuditRecord
from kaizen.trust.chain import ActionResult, AuditAnchor
from kaizen.trust.merkle import (
    MerkleNode,
    MerkleProof,
    MerkleTree,
    compute_merkle_root,
    get_proof_length,
    verify_merkle_proof,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_hashes():
    """Create sample SHA-256 hashes for testing."""
    return [hashlib.sha256(f"data_{i}".encode()).hexdigest() for i in range(4)]


@pytest.fixture
def sample_hashes_8():
    """Create 8 sample SHA-256 hashes for testing."""
    return [hashlib.sha256(f"data_{i}".encode()).hexdigest() for i in range(8)]


@pytest.fixture
def sample_hashes_1000():
    """Create 1000 sample SHA-256 hashes for performance testing."""
    return [hashlib.sha256(f"data_{i}".encode()).hexdigest() for i in range(1000)]


@pytest.fixture
def sample_anchor():
    """Create a sample AuditAnchor for testing."""
    return AuditAnchor(
        id="aud-001",
        agent_id="agent-001",
        action="analyze_data",
        timestamp=datetime.now(timezone.utc),
        trust_chain_hash="abc123def456",
        result=ActionResult.SUCCESS,
        signature="test-signature",
        resource="data/file.csv",
        context={"key": "value"},
    )


@pytest.fixture
def sample_audit_records():
    """Create sample AuditRecords for testing."""
    records = []
    for i in range(5):
        anchor = AuditAnchor(
            id=f"aud-{i:03d}",
            agent_id=f"agent-{i % 2:03d}",
            action="test_action",
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash=f"hash_{i}",
            result=ActionResult.SUCCESS,
            signature=f"sig_{i}",
        )
        record = AuditRecord(anchor=anchor, sequence_number=i + 1)
        records.append(record)
    return records


# =============================================================================
# MerkleNode Tests
# =============================================================================


class TestMerkleNode:
    """Tests for MerkleNode dataclass."""

    def test_merkle_node_creation(self):
        """MerkleNode can be created with hash only."""
        node = MerkleNode(hash="abc123")
        assert node.hash == "abc123"
        assert node.left is None
        assert node.right is None
        assert node.data_index is None

    def test_merkle_node_leaf(self):
        """Leaf node has data_index set."""
        node = MerkleNode(hash="abc123", data_index=5)
        assert node.data_index == 5
        assert node.is_leaf() is True

    def test_merkle_node_internal(self):
        """Internal node has no data_index."""
        left = MerkleNode(hash="left_hash", data_index=0)
        right = MerkleNode(hash="right_hash", data_index=1)
        internal = MerkleNode(hash="parent_hash", left=left, right=right)

        assert internal.data_index is None
        assert internal.is_leaf() is False
        assert internal.left == left
        assert internal.right == right


# =============================================================================
# MerkleTree Construction Tests
# =============================================================================


class TestMerkleTreeConstruction:
    """Tests for MerkleTree construction."""

    def test_empty_tree(self):
        """Empty tree has no root."""
        tree = MerkleTree()
        assert tree.root_hash is None
        assert tree.leaf_count == 0

    def test_empty_tree_with_empty_list(self):
        """Tree with empty list has no root."""
        tree = MerkleTree(leaves=[])
        assert tree.root_hash is None
        assert tree.leaf_count == 0

    def test_single_leaf_tree(self):
        """Single leaf tree has root equal to leaf hash."""
        leaf_hash = hashlib.sha256(b"single").hexdigest()
        tree = MerkleTree(leaves=[leaf_hash])

        assert tree.root_hash == leaf_hash
        assert tree.leaf_count == 1

    def test_two_leaf_tree(self, sample_hashes):
        """Two leaf tree has correct root."""
        leaves = sample_hashes[:2]
        tree = MerkleTree(leaves=leaves)

        # Root should be hash of both leaves
        expected_root = hashlib.sha256((leaves[0] + leaves[1]).encode()).hexdigest()

        assert tree.root_hash == expected_root
        assert tree.leaf_count == 2

    def test_four_leaf_tree(self, sample_hashes):
        """Four leaf tree has correct structure."""
        tree = MerkleTree(leaves=sample_hashes)

        assert tree.leaf_count == 4
        assert tree.root_hash is not None
        assert len(tree.root_hash) == 64  # SHA-256 hex

        # Verify root is computed correctly
        h0, h1, h2, h3 = sample_hashes
        left_parent = hashlib.sha256((h0 + h1).encode()).hexdigest()
        right_parent = hashlib.sha256((h2 + h3).encode()).hexdigest()
        expected_root = hashlib.sha256(
            (left_parent + right_parent).encode()
        ).hexdigest()

        assert tree.root_hash == expected_root

    def test_odd_leaf_count(self):
        """Tree handles odd number of leaves by duplication."""
        hashes = [hashlib.sha256(f"data_{i}".encode()).hexdigest() for i in range(3)]
        tree = MerkleTree(leaves=hashes)

        assert tree.leaf_count == 3
        assert tree.root_hash is not None
        assert len(tree.root_hash) == 64

    def test_large_tree_1000(self, sample_hashes_1000):
        """Large tree (1000 leaves) builds in acceptable time."""
        import time

        start = time.time()
        tree = MerkleTree(leaves=sample_hashes_1000)
        elapsed = time.time() - start

        assert tree.leaf_count == 1000
        assert tree.root_hash is not None
        # Should complete in under 1 second
        assert elapsed < 1.0

    def test_root_hash_property(self, sample_hashes):
        """root_hash property returns correct hash."""
        tree = MerkleTree(leaves=sample_hashes)
        assert tree.root_hash is not None
        assert isinstance(tree.root_hash, str)
        assert len(tree.root_hash) == 64

    def test_leaf_count_property(self, sample_hashes):
        """leaf_count property returns correct count."""
        tree = MerkleTree(leaves=sample_hashes)
        assert tree.leaf_count == 4


# =============================================================================
# Proof Generation Tests
# =============================================================================


class TestProofGeneration:
    """Tests for MerkleTree.generate_proof()."""

    def test_generate_proof_first_leaf(self, sample_hashes):
        """Proof generated for first leaf is valid."""
        tree = MerkleTree(leaves=sample_hashes)
        proof = tree.generate_proof(0)

        assert proof.leaf_hash == sample_hashes[0]
        assert proof.leaf_index == 0
        assert proof.root_hash == tree.root_hash
        assert proof.tree_size == 4

    def test_generate_proof_last_leaf(self, sample_hashes):
        """Proof generated for last leaf is valid."""
        tree = MerkleTree(leaves=sample_hashes)
        proof = tree.generate_proof(3)

        assert proof.leaf_hash == sample_hashes[3]
        assert proof.leaf_index == 3
        assert proof.root_hash == tree.root_hash
        assert proof.tree_size == 4

    def test_generate_proof_middle_leaf(self, sample_hashes):
        """Proof generated for middle leaf is valid."""
        tree = MerkleTree(leaves=sample_hashes)
        proof = tree.generate_proof(1)

        assert proof.leaf_hash == sample_hashes[1]
        assert proof.leaf_index == 1
        assert tree.verify_proof(proof)

    def test_generate_proof_single_leaf_tree(self):
        """Proof for single-leaf tree has no siblings."""
        leaf_hash = hashlib.sha256(b"single").hexdigest()
        tree = MerkleTree(leaves=[leaf_hash])
        proof = tree.generate_proof(0)

        assert proof.leaf_hash == leaf_hash
        assert proof.root_hash == leaf_hash
        assert len(proof.proof_hashes) == 0  # No siblings needed

    def test_generate_proof_out_of_range(self, sample_hashes):
        """generate_proof() raises IndexError for invalid index."""
        tree = MerkleTree(leaves=sample_hashes)

        with pytest.raises(IndexError):
            tree.generate_proof(4)  # Index 4 doesn't exist

        with pytest.raises(IndexError):
            tree.generate_proof(-1)  # Negative index

    def test_generate_proof_empty_tree(self):
        """generate_proof() returns None for empty tree (CARE-057)."""
        tree = MerkleTree()

        # CARE-057: Returns None instead of raising ValueError for consistency
        # with verify_proof() which returns False for empty/None cases
        proof = tree.generate_proof(0)
        assert proof is None

    def test_proof_has_correct_structure(self, sample_hashes):
        """Generated proof has all required fields."""
        tree = MerkleTree(leaves=sample_hashes)
        proof = tree.generate_proof(2)

        assert hasattr(proof, "leaf_hash")
        assert hasattr(proof, "leaf_index")
        assert hasattr(proof, "proof_hashes")
        assert hasattr(proof, "root_hash")
        assert hasattr(proof, "tree_size")

        # Each proof hash has position
        for h, pos in proof.proof_hashes:
            assert isinstance(h, str)
            assert pos in ("left", "right")

    def test_proof_hash_count(self, sample_hashes_8):
        """Proof contains correct number of hashes (log2(n))."""
        tree = MerkleTree(leaves=sample_hashes_8)

        # For 8 leaves, proof should have 3 hashes (log2(8) = 3)
        proof = tree.generate_proof(0)
        assert len(proof.proof_hashes) == 3

    def test_proof_hash_count_odd_tree(self):
        """Proof hash count is correct for odd-sized trees."""
        hashes = [hashlib.sha256(f"data_{i}".encode()).hexdigest() for i in range(5)]
        tree = MerkleTree(leaves=hashes)

        # For 5 leaves, proof should have 3 hashes (ceil(log2(5)) = 3)
        proof = tree.generate_proof(0)
        assert len(proof.proof_hashes) == 3


# =============================================================================
# Proof Verification Tests
# =============================================================================


class TestProofVerification:
    """Tests for proof verification."""

    def test_verify_proof_valid(self, sample_hashes):
        """Valid proof passes verification."""
        tree = MerkleTree(leaves=sample_hashes)

        for i in range(4):
            proof = tree.generate_proof(i)
            assert tree.verify_proof(proof) is True

    def test_verify_proof_tampered_leaf(self, sample_hashes):
        """Proof with tampered leaf hash fails."""
        tree = MerkleTree(leaves=sample_hashes)
        proof = tree.generate_proof(0)

        # Tamper with leaf hash
        proof.leaf_hash = "tampered_leaf_hash"

        assert tree.verify_proof(proof) is False

    def test_verify_proof_tampered_hash(self, sample_hashes):
        """Proof with tampered sibling hash fails."""
        tree = MerkleTree(leaves=sample_hashes)
        proof = tree.generate_proof(0)

        # Tamper with first sibling hash
        if proof.proof_hashes:
            h, pos = proof.proof_hashes[0]
            proof.proof_hashes[0] = ("tampered_hash", pos)

            assert tree.verify_proof(proof) is False

    def test_verify_proof_wrong_root(self, sample_hashes):
        """Proof with wrong root hash fails."""
        tree = MerkleTree(leaves=sample_hashes)
        proof = tree.generate_proof(0)

        # Tamper with root hash
        proof.root_hash = "wrong_root_hash"

        assert tree.verify_proof(proof) is False

    def test_verify_proof_empty_tree(self):
        """Verification on empty tree returns False."""
        tree = MerkleTree()

        # Create a proof manually (can't generate from empty tree)
        proof = MerkleProof(
            leaf_hash="some_hash",
            leaf_index=0,
            root_hash="some_root",
            tree_size=1,
        )

        assert tree.verify_proof(proof) is False

    def test_verify_all_leaves(self, sample_hashes_8):
        """Every leaf in tree verifies correctly."""
        tree = MerkleTree(leaves=sample_hashes_8)

        for i in range(8):
            proof = tree.generate_proof(i)
            assert tree.verify_proof(proof) is True

    def test_standalone_verify_function(self, sample_hashes):
        """verify_merkle_proof() works without tree instance."""
        tree = MerkleTree(leaves=sample_hashes)
        proof = tree.generate_proof(1)

        # Use standalone function
        is_valid = verify_merkle_proof(sample_hashes[1], proof)
        assert is_valid is True

    def test_standalone_verify_wrong_leaf(self, sample_hashes):
        """verify_merkle_proof() fails with wrong leaf hash."""
        tree = MerkleTree(leaves=sample_hashes)
        proof = tree.generate_proof(0)

        # Try to verify with different leaf hash
        is_valid = verify_merkle_proof(sample_hashes[1], proof)
        assert is_valid is False


# =============================================================================
# Add Leaf Tests
# =============================================================================


class TestAddLeaf:
    """Tests for MerkleTree.add_leaf()."""

    def test_add_leaf_updates_root(self, sample_hashes):
        """Adding a leaf updates the root hash."""
        tree = MerkleTree(leaves=sample_hashes[:2])
        original_root = tree.root_hash

        new_hash = hashlib.sha256(b"new_data").hexdigest()
        tree.add_leaf(new_hash)

        assert tree.leaf_count == 3
        assert tree.root_hash != original_root

    def test_add_leaf_existing_proofs_invalid(self, sample_hashes):
        """Old proofs become invalid after adding leaf."""
        tree = MerkleTree(leaves=sample_hashes[:2])
        old_proof = tree.generate_proof(0)

        # Add new leaf
        new_hash = hashlib.sha256(b"new_data").hexdigest()
        tree.add_leaf(new_hash)

        # Old proof should now fail (root hash changed)
        # The tree's root changed, so verification should fail
        assert tree.verify_proof(old_proof) is False

    def test_add_leaf_to_empty_tree(self):
        """Adding leaf to empty tree works."""
        tree = MerkleTree()
        leaf_hash = hashlib.sha256(b"first").hexdigest()

        tree.add_leaf(leaf_hash)

        assert tree.leaf_count == 1
        assert tree.root_hash == leaf_hash


# =============================================================================
# Integration Tests
# =============================================================================


class TestAuditRecordIntegration:
    """Tests for integration with AuditRecord."""

    def test_from_audit_records(self, sample_audit_records):
        """from_audit_records() builds tree from AuditRecord list."""
        tree = MerkleTree.from_audit_records(sample_audit_records)

        assert tree.leaf_count == 5
        assert tree.root_hash is not None

        # Verify each record's hash is in the tree
        for i, record in enumerate(sample_audit_records):
            assert tree.get_leaf(i) == record.integrity_hash

    def test_full_workflow(self, sample_audit_records):
        """Full workflow: build tree, generate proofs, verify."""
        tree = MerkleTree.from_audit_records(sample_audit_records)

        # Generate and verify proof for each record
        for i in range(len(sample_audit_records)):
            proof = tree.generate_proof(i)
            assert tree.verify_proof(proof) is True
            assert verify_merkle_proof(sample_audit_records[i].integrity_hash, proof)

    def test_tampered_audit_record_detected(self, sample_audit_records):
        """Tampering with audit record is detected."""
        tree = MerkleTree.from_audit_records(sample_audit_records)

        # Generate proof for first record
        original_hash = sample_audit_records[0].integrity_hash
        proof = tree.generate_proof(0)

        # "Tamper" by using different hash
        tampered_hash = hashlib.sha256(b"tampered").hexdigest()

        # Proof verification with tampered hash should fail
        assert verify_merkle_proof(tampered_hash, proof) is False

        # Original hash still verifies
        assert verify_merkle_proof(original_hash, proof) is True


# =============================================================================
# Serialization Tests
# =============================================================================


class TestSerialization:
    """Tests for serialization and deserialization."""

    def test_to_dict(self, sample_hashes):
        """to_dict() serializes tree metadata."""
        tree = MerkleTree(leaves=sample_hashes)
        data = tree.to_dict()

        assert "root_hash" in data
        assert "leaf_count" in data
        assert "leaves" in data
        assert "version" in data

        assert data["root_hash"] == tree.root_hash
        assert data["leaf_count"] == 4
        assert len(data["leaves"]) == 4

    def test_from_dict(self, sample_hashes):
        """from_dict() reconstructs tree."""
        original = MerkleTree(leaves=sample_hashes)
        data = original.to_dict()

        reconstructed = MerkleTree.from_dict(data)

        assert reconstructed.root_hash == original.root_hash
        assert reconstructed.leaf_count == original.leaf_count

    def test_proof_to_dict(self, sample_hashes):
        """Proof serializes correctly."""
        tree = MerkleTree(leaves=sample_hashes)
        proof = tree.generate_proof(1)

        data = proof.to_dict()

        assert data["leaf_hash"] == proof.leaf_hash
        assert data["leaf_index"] == 1
        assert data["root_hash"] == proof.root_hash
        assert data["tree_size"] == 4
        assert len(data["proof_hashes"]) == len(proof.proof_hashes)

    def test_proof_from_dict(self, sample_hashes):
        """Proof deserializes correctly."""
        tree = MerkleTree(leaves=sample_hashes)
        original_proof = tree.generate_proof(2)

        data = original_proof.to_dict()
        reconstructed = MerkleProof.from_dict(data)

        assert reconstructed.leaf_hash == original_proof.leaf_hash
        assert reconstructed.leaf_index == original_proof.leaf_index
        assert reconstructed.root_hash == original_proof.root_hash
        assert reconstructed.tree_size == original_proof.tree_size
        assert reconstructed.proof_hashes == original_proof.proof_hashes

    def test_serialized_proof_verifies(self, sample_hashes):
        """Serialized and deserialized proof still verifies."""
        tree = MerkleTree(leaves=sample_hashes)
        original_proof = tree.generate_proof(0)

        # Serialize and deserialize
        data = original_proof.to_dict()
        restored_proof = MerkleProof.from_dict(data)

        # Should still verify
        assert tree.verify_proof(restored_proof) is True


# =============================================================================
# Utility Function Tests
# =============================================================================


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_compute_merkle_root(self, sample_hashes):
        """compute_merkle_root() returns correct root."""
        root = compute_merkle_root(sample_hashes)

        tree = MerkleTree(leaves=sample_hashes)
        assert root == tree.root_hash

    def test_compute_merkle_root_empty(self):
        """compute_merkle_root() returns None for empty list."""
        assert compute_merkle_root([]) is None

    def test_get_proof_length(self):
        """get_proof_length() returns correct length."""
        # Single leaf = no proof needed
        assert get_proof_length(1) == 0

        # 2 leaves = 1 hash
        assert get_proof_length(2) == 1

        # 4 leaves = 2 hashes
        assert get_proof_length(4) == 2

        # 8 leaves = 3 hashes
        assert get_proof_length(8) == 3

        # 1000 leaves = 10 hashes (ceil(log2(1000)) = 10)
        assert get_proof_length(1000) == 10


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Additional edge case tests."""

    def test_deterministic_root(self, sample_hashes):
        """Same leaves produce same root."""
        tree1 = MerkleTree(leaves=sample_hashes)
        tree2 = MerkleTree(leaves=sample_hashes)

        assert tree1.root_hash == tree2.root_hash

    def test_order_matters(self, sample_hashes):
        """Different order produces different root."""
        tree1 = MerkleTree(leaves=sample_hashes)
        tree2 = MerkleTree(leaves=list(reversed(sample_hashes)))

        assert tree1.root_hash != tree2.root_hash

    def test_get_leaf(self, sample_hashes):
        """get_leaf() returns correct leaf hash."""
        tree = MerkleTree(leaves=sample_hashes)

        for i, h in enumerate(sample_hashes):
            assert tree.get_leaf(i) == h

    def test_get_leaf_out_of_range(self, sample_hashes):
        """get_leaf() raises IndexError for invalid index."""
        tree = MerkleTree(leaves=sample_hashes)

        with pytest.raises(IndexError):
            tree.get_leaf(100)

    def test_proof_with_many_leaves(self, sample_hashes_1000):
        """Proofs work correctly with large trees."""
        tree = MerkleTree(leaves=sample_hashes_1000)

        # Verify several random indices
        for i in [0, 100, 500, 999]:
            proof = tree.generate_proof(i)
            assert tree.verify_proof(proof) is True
            assert len(proof.proof_hashes) == 10  # log2(1000) = 10

    def test_verify_proof_empty_root_hash(self):
        """verify_merkle_proof returns False for empty root."""
        proof = MerkleProof(
            leaf_hash="some_hash",
            leaf_index=0,
            root_hash="",  # Empty root
            tree_size=1,
        )

        assert verify_merkle_proof("some_hash", proof) is False

    def test_tree_from_none_leaves(self):
        """Tree handles None input gracefully."""
        tree = MerkleTree(leaves=None)
        assert tree.leaf_count == 0
        assert tree.root_hash is None

    def test_empty_tree_consistent_behavior_care057(self):
        """CARE-057: Empty tree handling is consistent across methods.

        Both generate_proof() and verify_proof() handle empty/None cases
        gracefully without raising exceptions, enabling simple chained usage.
        """
        tree = MerkleTree()  # Empty tree

        # generate_proof returns None for empty tree (not ValueError)
        proof = tree.generate_proof(0)
        assert proof is None

        # verify_proof returns False for None proof (not exception)
        result = tree.verify_proof(proof)
        assert result is False

        # This allows clean chaining without try/except
        # The pattern: if tree.verify_proof(tree.generate_proof(idx)): ...
        # works even for empty trees

    def test_verify_proof_none_input_care057(self):
        """CARE-057: verify_proof handles None proof gracefully."""
        # Non-empty tree
        hashes = ["a" * 64, "b" * 64]
        tree = MerkleTree(leaves=hashes)

        # Explicitly passing None should return False, not raise
        result = tree.verify_proof(None)
        assert result is False
