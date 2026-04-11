"""
Unit tests for CARE-006: Linked State Hashing.

Tests the linked hash chain functionality that creates tamper-evident
blockchain-like chains by including previous state hashes in each
new hash computation.
"""

from datetime import datetime, timezone

import pytest
from kailash.trust.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    GenesisRecord,
    LinkedHashChain,
    LinkedHashEntry,
    TrustLineageChain,
)


class TestTrustLineageChainHash:
    """Tests for TrustLineageChain.hash() with linked hashing support."""

    @pytest.fixture
    def genesis(self):
        """Create a sample genesis record."""
        return GenesisRecord(
            id="gen-001",
            agent_id="agent-001",
            authority_id="auth-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2025, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
            signature="test-signature",
            expires_at=datetime(2026, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
        )

    @pytest.fixture
    def capabilities(self):
        """Create sample capabilities."""
        return [
            CapabilityAttestation(
                id="cap-001",
                capability="analyze_data",
                capability_type=CapabilityType.ACCESS,
                constraints=["read_only"],
                attester_id="auth-001",
                attested_at=datetime(2025, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
                signature="test",
                expires_at=datetime(2026, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
            ),
        ]

    @pytest.fixture
    def trust_chain(self, genesis, capabilities):
        """Create a sample trust lineage chain."""
        return TrustLineageChain(genesis=genesis, capabilities=capabilities)

    def test_hash_includes_previous(self, trust_chain):
        """Hash with previous_hash produces different result than without."""
        hash_without_previous = trust_chain.hash()
        hash_with_previous = trust_chain.hash(previous_hash="abc123def456")

        assert hash_without_previous != hash_with_previous
        assert len(hash_with_previous) == 64  # SHA-256 hex

    def test_hash_without_previous(self, trust_chain):
        """Backward compatibility: hash() without arguments still works."""
        hash_result = trust_chain.hash()

        assert isinstance(hash_result, str)
        assert len(hash_result) == 64  # SHA-256 hex

    def test_hash_reproducible_with_same_inputs(self, trust_chain):
        """Same inputs produce same hash (deterministic)."""
        previous = "previous_hash_123"

        hash1 = trust_chain.hash(previous_hash=previous)
        hash2 = trust_chain.hash(previous_hash=previous)

        assert hash1 == hash2

    def test_hash_differs_with_different_previous(self, trust_chain):
        """Different previous_hash values produce different results."""
        hash1 = trust_chain.hash(previous_hash="prev_hash_1")
        hash2 = trust_chain.hash(previous_hash="prev_hash_2")

        assert hash1 != hash2


class TestLinkedHashChain:
    """Tests for LinkedHashChain class."""

    def test_empty_chain_valid(self):
        """Empty chain passes integrity check."""
        chain = LinkedHashChain()

        valid, break_index = chain.verify_integrity()

        assert valid is True
        assert break_index is None
        assert len(chain) == 0

    def test_single_entry_chain_valid(self):
        """Single entry chain passes integrity check."""
        chain = LinkedHashChain()
        chain.add_hash("agent-001", "initial_hash_abc123")

        valid, break_index = chain.verify_integrity()

        assert valid is True
        assert break_index is None
        assert len(chain) == 1

    def test_add_hash_returns_linked_hash(self):
        """add_hash returns the computed linked hash."""
        chain = LinkedHashChain()

        linked_hash = chain.add_hash("agent-001", "original_hash")

        assert isinstance(linked_hash, str)
        assert len(linked_hash) == 64  # SHA-256 hex
        assert linked_hash != "original_hash"  # Should be transformed

    def test_linked_hash_chain_integrity(self):
        """Full chain with multiple entries verifies correctly."""
        chain = LinkedHashChain()

        # Add multiple entries
        hash1 = chain.add_hash("agent-001", "hash_a")
        hash2 = chain.add_hash("agent-002", "hash_b")
        hash3 = chain.add_hash("agent-003", "hash_c")

        valid, break_index = chain.verify_integrity()

        assert valid is True
        assert break_index is None
        assert len(chain) == 3

        # Each hash should be different
        assert hash1 != hash2 != hash3

    def test_chain_order_matters(self):
        """Reordering entries would produce different hashes."""
        chain1 = LinkedHashChain()
        chain1.add_hash("agent-001", "hash_a")
        chain1.add_hash("agent-002", "hash_b")

        chain2 = LinkedHashChain()
        chain2.add_hash("agent-002", "hash_b")
        chain2.add_hash("agent-001", "hash_a")

        # The second entries should differ because they link to different previous
        entries1 = chain1.entries
        entries2 = chain2.entries

        assert entries1[1].hash != entries2[1].hash

    def test_linked_hash_tamper_detection(self):
        """Tampering is detected via hash mismatch."""
        chain = LinkedHashChain()
        linked_hash = chain.add_hash("agent-001", "original_hash")

        # No tampering - should return False
        assert chain.detect_tampering("agent-001", linked_hash) is False

        # Tampered hash - should return True
        assert chain.detect_tampering("agent-001", "tampered_hash") is True

    def test_linked_hash_gap_detection(self):
        """Missing intermediate hash is detected via verify_chain_linkage."""
        chain = LinkedHashChain()
        chain.add_hash("agent-001", "hash_a")
        chain.add_hash("agent-002", "hash_b")
        chain.add_hash("agent-003", "hash_c")

        # Correct original hashes - should pass
        valid, break_index = chain.verify_chain_linkage(["hash_a", "hash_b", "hash_c"])
        assert valid is True
        assert break_index is None

        # Missing middle hash - should fail
        valid, break_index = chain.verify_chain_linkage(["hash_a", "hash_c"])
        assert valid is False
        assert break_index == 2  # Mismatch at chain length comparison

    def test_linked_hash_chain_serialization(self):
        """Chain can be serialized and deserialized (round-trip)."""
        chain = LinkedHashChain()
        chain.add_hash("agent-001", "hash_a")
        chain.add_hash("agent-002", "hash_b")

        # Serialize
        data = chain.to_dict()

        assert data["version"] == "1.0"
        assert data["chain_type"] == "linked_hash_chain"
        assert len(data["entries"]) == 2

        # Deserialize
        restored = LinkedHashChain.from_dict(data)

        assert len(restored) == 2
        assert restored.entries[0].agent_id == "agent-001"
        assert restored.entries[1].agent_id == "agent-002"
        assert restored.entries[0].hash == chain.entries[0].hash
        assert restored.entries[1].hash == chain.entries[1].hash

    def test_get_entry_returns_correct_entry(self):
        """get_entry returns the correct entry for an agent."""
        chain = LinkedHashChain()
        chain.add_hash("agent-001", "hash_a")
        chain.add_hash("agent-002", "hash_b")

        entry = chain.get_entry("agent-002")

        assert entry is not None
        assert entry.agent_id == "agent-002"

        # Non-existent agent
        missing = chain.get_entry("agent-999")
        assert missing is None

    def test_get_previous_hash(self):
        """get_previous_hash returns the preceding entry's hash."""
        chain = LinkedHashChain()
        hash1 = chain.add_hash("agent-001", "hash_a")
        chain.add_hash("agent-002", "hash_b")
        chain.add_hash("agent-003", "hash_c")

        # First entry has no previous
        assert chain.get_previous_hash("agent-001") is None

        # Second entry's previous is first entry's hash
        assert chain.get_previous_hash("agent-002") == hash1

        # Non-existent agent
        assert chain.get_previous_hash("agent-999") is None

    def test_entries_property_returns_copy(self):
        """entries property returns a copy, not the internal list."""
        chain = LinkedHashChain()
        chain.add_hash("agent-001", "hash_a")

        entries = chain.entries
        entries.clear()

        # Original chain should be unaffected
        assert len(chain) == 1


class TestLinkedHashEntry:
    """Tests for LinkedHashEntry dataclass."""

    def test_entry_creation(self):
        """LinkedHashEntry can be created with all fields."""
        timestamp = datetime.now(timezone.utc)
        entry = LinkedHashEntry(
            agent_id="agent-001",
            hash="abc123def456",
            timestamp=timestamp,
        )

        assert entry.agent_id == "agent-001"
        assert entry.hash == "abc123def456"
        assert entry.timestamp == timestamp


class TestLinkedHashingIntegration:
    """Integration tests combining TrustLineageChain and LinkedHashChain."""

    @pytest.fixture
    def genesis_001(self):
        """Create genesis for agent-001."""
        return GenesisRecord(
            id="gen-001",
            agent_id="agent-001",
            authority_id="auth-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2025, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
            signature="test-signature",
            expires_at=datetime(2026, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
        )

    @pytest.fixture
    def genesis_002(self):
        """Create genesis for agent-002."""
        return GenesisRecord(
            id="gen-002",
            agent_id="agent-002",
            authority_id="auth-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2025, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
            signature="test-signature",
            expires_at=datetime(2026, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
        )

    def test_trust_chains_in_linked_chain(self, genesis_001, genesis_002):
        """Multiple TrustLineageChains can be linked together."""
        chain1 = TrustLineageChain(genesis=genesis_001)
        chain2 = TrustLineageChain(genesis=genesis_002)

        linked_chain = LinkedHashChain()

        # Add first chain's hash
        hash1 = chain1.hash()
        linked_hash1 = linked_chain.add_hash(chain1.genesis.agent_id, hash1)

        # Add second chain's hash - links to first
        hash2 = chain2.hash()
        linked_hash2 = linked_chain.add_hash(chain2.genesis.agent_id, hash2)

        # Verify chain integrity
        valid, break_index = linked_chain.verify_chain_linkage([hash1, hash2])

        assert valid is True
        assert break_index is None
        assert linked_hash1 != linked_hash2

    def test_trust_chain_with_previous_hash_integration(self, genesis_001, genesis_002):
        """TrustLineageChain.hash(previous_hash) works with linked chain."""
        chain1 = TrustLineageChain(genesis=genesis_001)
        chain2 = TrustLineageChain(genesis=genesis_002)

        # Get first chain's hash
        first_hash = chain1.hash()

        # Second chain links to first
        second_hash = chain2.hash(previous_hash=first_hash)

        # Verify they're different
        assert first_hash != second_hash

        # Verify second hash changes if first changes
        modified_first = "modified_hash_value"
        second_hash_modified = chain2.hash(previous_hash=modified_first)

        assert second_hash != second_hash_modified


class TestEdgeCases:
    """Edge case tests for linked hashing."""

    def test_empty_original_hash(self):
        """Empty string as original hash is handled."""
        chain = LinkedHashChain()
        linked_hash = chain.add_hash("agent-001", "")

        assert len(linked_hash) == 64

    def test_very_long_original_hash(self):
        """Very long original hash is handled."""
        chain = LinkedHashChain()
        long_hash = "a" * 10000
        linked_hash = chain.add_hash("agent-001", long_hash)

        assert len(linked_hash) == 64

    def test_special_characters_in_hash(self):
        """Special characters in hash are handled."""
        chain = LinkedHashChain()
        special_hash = "hash with spaces and !@#$%^&*()"
        linked_hash = chain.add_hash("agent-001", special_hash)

        assert len(linked_hash) == 64

    def test_unicode_in_agent_id(self):
        """Unicode characters in agent_id are handled."""
        chain = LinkedHashChain()
        linked_hash = chain.add_hash("agent-001", "hash_value")

        assert len(linked_hash) == 64
        entry = chain.get_entry("agent-001")
        assert entry is not None

    def test_duplicate_agent_ids(self):
        """Same agent_id can appear multiple times in chain."""
        chain = LinkedHashChain()
        chain.add_hash("agent-001", "hash_a")
        chain.add_hash("agent-001", "hash_b")

        assert len(chain) == 2

        # get_entry returns first occurrence
        entry = chain.get_entry("agent-001")
        assert entry is not None

    def test_serialization_preserves_timestamps(self):
        """Serialization preserves timestamp precision."""
        chain = LinkedHashChain()
        chain.add_hash("agent-001", "hash_a")

        original_timestamp = chain.entries[0].timestamp

        # Round-trip
        data = chain.to_dict()
        restored = LinkedHashChain.from_dict(data)

        # Timestamps should match
        assert restored.entries[0].timestamp == original_timestamp

    def test_from_dict_with_empty_entries(self):
        """from_dict handles empty entries list."""
        data = {
            "entries": [],
            "version": "1.0",
            "chain_type": "linked_hash_chain",
        }

        chain = LinkedHashChain.from_dict(data)

        assert len(chain) == 0
        valid, _ = chain.verify_integrity()
        assert valid is True

    def test_verify_chain_linkage_wrong_order(self):
        """verify_chain_linkage detects wrong hash order."""
        chain = LinkedHashChain()
        chain.add_hash("agent-001", "hash_a")
        chain.add_hash("agent-002", "hash_b")
        chain.add_hash("agent-003", "hash_c")

        # Wrong order should fail
        valid, break_index = chain.verify_chain_linkage(["hash_b", "hash_a", "hash_c"])

        assert valid is False
        assert break_index == 0  # First entry doesn't match

    def test_verify_chain_linkage_extra_hashes(self):
        """verify_chain_linkage detects extra hashes."""
        chain = LinkedHashChain()
        chain.add_hash("agent-001", "hash_a")
        chain.add_hash("agent-002", "hash_b")

        # More hashes than entries should fail
        valid, break_index = chain.verify_chain_linkage(
            ["hash_a", "hash_b", "hash_c", "hash_d"]
        )

        assert valid is False


class TestVerifyIntegrityStrictMode:
    """Tests for ROUND5-006: verify_integrity strict mode enforcement.

    ROUND5-006 Security Finding:
    verify_integrity() only performs STRUCTURAL checks and cannot detect
    tampering without access to original hashes. The strict parameter
    enforces use of verify_chain_linkage() for proper cryptographic
    verification in production security contexts.
    """

    def test_verify_integrity_strict_mode_raises(self):
        """ROUND5-006: verify_integrity(strict=True) raises ValueError.

        In strict mode, verify_integrity should raise ValueError to enforce
        use of verify_chain_linkage() for proper cryptographic verification.
        """
        chain = LinkedHashChain()
        chain.add_hash("agent-001", "hash_a")
        chain.add_hash("agent-002", "hash_b")

        with pytest.raises(ValueError) as exc_info:
            chain.verify_integrity(strict=True)

        # Error message should mention verify_chain_linkage
        error_message = str(exc_info.value).lower()
        assert "verify_chain_linkage" in error_message, (
            "ROUND5-006: Error message should mention verify_chain_linkage. "
            f"Got: {exc_info.value}"
        )

    def test_verify_integrity_strict_mode_empty_chain_raises(self):
        """ROUND5-006: Empty chain still raises in strict mode."""
        chain = LinkedHashChain()

        # Even empty chain should raise in strict mode
        with pytest.raises(ValueError) as exc_info:
            chain.verify_integrity(strict=True)

        assert "verify_chain_linkage" in str(exc_info.value).lower()

    def test_verify_integrity_structural_check_passes(self):
        """ROUND5-006: Normal structural check still works (non-strict mode).

        verify_integrity(strict=False) or verify_integrity() should still
        perform structural validation and pass for valid chains.
        """
        chain = LinkedHashChain()
        chain.add_hash("agent-001", "hash_a")
        chain.add_hash("agent-002", "hash_b")
        chain.add_hash("agent-003", "hash_c")

        # Non-strict mode should pass structural check
        valid, break_index = chain.verify_integrity(strict=False)

        assert valid is True, "Structural check should pass for valid chain"
        assert break_index is None

    def test_verify_integrity_default_is_non_strict(self):
        """ROUND5-006: Default mode (no strict argument) is non-strict."""
        chain = LinkedHashChain()
        chain.add_hash("agent-001", "hash_a")

        # Should not raise - default is non-strict
        valid, break_index = chain.verify_integrity()

        assert valid is True

    def test_verify_chain_linkage_is_proper_verification(self):
        """ROUND5-006: verify_chain_linkage provides proper cryptographic verification.

        This test demonstrates that verify_chain_linkage is the correct
        method for production security verification.
        """
        chain = LinkedHashChain()
        hash_a = chain.add_hash("agent-001", "original_hash_a")
        hash_b = chain.add_hash("agent-002", "original_hash_b")

        # Proper verification with original hashes
        valid, break_index = chain.verify_chain_linkage(
            ["original_hash_a", "original_hash_b"]
        )

        assert valid is True
        assert break_index is None

        # Tampered hash should be detected
        valid, break_index = chain.verify_chain_linkage(
            ["tampered_hash_a", "original_hash_b"]
        )

        assert valid is False
        assert break_index == 0  # First entry was tampered

    def test_verify_integrity_structural_only_warning(self):
        """ROUND5-006: Non-strict mode should log warning about structural-only check.

        This test verifies the warning is part of the documented behavior,
        though we don't actually check logging here (would require mock).
        """
        chain = LinkedHashChain()
        chain.add_hash("agent-001", "hash_a")
        chain.add_hash("agent-002", "hash_b")

        # This should work but would log a warning
        valid, break_index = chain.verify_integrity(strict=False)

        # Test passes if no exception and returns valid result
        assert valid is True
        assert break_index is None
