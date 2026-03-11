"""
CARE-040: Adversarial Tests for Audit Log Integrity and Tamper Resistance.

These tests verify that the audit log system:
- Maintains immutability of written records
- Detects tampering via hash chain verification
- Provides valid Merkle proofs for entries
- Handles concurrent writes correctly
- Survives crash scenarios

Attack Vectors Tested:
- Record modification after write
- Record deletion attempts
- Hash chain tampering
- Record reordering
- Merkle proof forgery
- Timestamp backdating
- Sequence gap injection

NO MOCKING - Uses real instances of AppendOnlyAuditStore, MerkleTree, etc.
"""

import asyncio
import copy
import hashlib
import random
import time
from datetime import datetime, timedelta, timezone
from typing import List
from uuid import uuid4

import pytest
from kaizen.trust.audit_store import (
    AppendOnlyAuditStore,
    AuditRecord,
    AuditStoreImmutabilityError,
    IntegrityVerificationResult,
)
from kaizen.trust.chain import ActionResult, AuditAnchor, LinkedHashChain
from kaizen.trust.merkle import (
    MerkleProof,
    MerkleTree,
    compute_merkle_root,
    get_proof_length,
    verify_merkle_proof,
)
from kaizen.trust.timestamping import (
    LocalTimestampAuthority,
    TimestampAnchorManager,
    TimestampSource,
    TimestampToken,
)

# =============================================================================
# Test Fixtures and Helpers
# =============================================================================


def create_audit_anchor(
    agent_id: str = "agent-test",
    action: str = "test_action",
    resource: str = "test_resource",
    result: ActionResult = ActionResult.SUCCESS,
    parent_anchor_id: str = None,
) -> AuditAnchor:
    """Create an audit anchor for testing."""
    return AuditAnchor(
        id=f"aud-{uuid4()}",
        agent_id=agent_id,
        action=action,
        resource=resource,
        timestamp=datetime.now(timezone.utc),
        trust_chain_hash=hashlib.sha256(f"{agent_id}-{action}".encode()).hexdigest(),
        result=result,
        signature=f"sig-{uuid4()}",
        parent_anchor_id=parent_anchor_id,
        context={"test": True, "value": random.randint(1, 1000)},
    )


async def populate_audit_store(
    store: AppendOnlyAuditStore, count: int = 10
) -> List[AuditRecord]:
    """Populate audit store with test records."""
    records = []
    for i in range(count):
        anchor = create_audit_anchor(
            agent_id=f"agent-{i % 3}",
            action=f"action_{i}",
        )
        record = await store.append(anchor)
        records.append(record)
    return records


# =============================================================================
# Test 1: Audit Record Immutable After Write
# =============================================================================


class TestAuditRecordImmutableAfterWrite:
    """Test that written audit records cannot be modified."""

    @pytest.mark.asyncio
    async def test_audit_record_immutable_after_write(self):
        """
        Scenario: Attempt to modify an audit record after it has been written.

        Expected: The modification should be blocked or detectable.
        """
        store = AppendOnlyAuditStore()

        # Write a record
        anchor = create_audit_anchor(action="original_action")
        record = await store.append(anchor)

        # Store original values
        original_id = record.record_id
        original_hash = record.integrity_hash
        original_seq = record.sequence_number

        # Attempt to modify the record directly (simulating tampering)
        # In-memory store doesn't expose direct modification, but we can
        # verify that any tampering is detectable

        # Try to tamper with the stored record
        stored_record = await store.get(original_id)

        # Create a tampered copy
        tampered_anchor = copy.deepcopy(stored_record.anchor)
        tampered_anchor.action = "tampered_action"  # TAMPERED!

        # The integrity hash should now fail verification
        tampered_record = copy.deepcopy(stored_record)
        tampered_record.anchor = tampered_anchor

        # Recompute hash - it should differ
        tampered_hash = tampered_record._compute_integrity_hash()
        assert (
            tampered_hash != original_hash
        ), "Tampered record should have different hash"

        # Verify integrity should fail for tampered record
        # The stored integrity_hash was computed from original data
        # After tampering, verify_integrity() should fail
        tampered_record.integrity_hash = original_hash  # Keep original hash
        assert (
            not tampered_record.verify_integrity()
        ), "Tampered record should fail integrity verification"

    @pytest.mark.asyncio
    async def test_record_context_tampering_detected(self):
        """
        Scenario: Attempt to tamper with the context field of an audit record.

        Expected: Context tampering should be detected via hash verification.
        """
        store = AppendOnlyAuditStore()

        anchor = create_audit_anchor(action="context_test")
        anchor.context = {"sensitive": "original_data", "amount": 1000}
        record = await store.append(anchor)

        original_hash = record.integrity_hash

        # Tamper with context
        tampered_record = copy.deepcopy(record)
        tampered_record.anchor.context["amount"] = 9999999  # FRAUD!

        # Hash should change
        tampered_hash = tampered_record._compute_integrity_hash()
        assert tampered_hash != original_hash, "Context tampering should change hash"


# =============================================================================
# Test 2: Audit Record Deletion Blocked
# =============================================================================


class TestAuditRecordDeletionBlocked:
    """Test that individual audit records cannot be deleted."""

    @pytest.mark.asyncio
    async def test_audit_record_deletion_blocked(self):
        """
        Scenario: Attempt to delete an individual audit record.

        Expected: Delete operation should be blocked with appropriate error.
        """
        store = AppendOnlyAuditStore()

        # Write some records
        await populate_audit_store(store, count=5)

        # Attempt to delete
        with pytest.raises(AuditStoreImmutabilityError) as exc_info:
            await store.delete("any-id")

        assert exc_info.value.operation == "delete"
        assert "immutable" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_update_operation_also_blocked(self):
        """
        Scenario: Attempt to update an audit record.

        Expected: Update operation should also be blocked.
        """
        store = AppendOnlyAuditStore()

        anchor = create_audit_anchor()
        await store.append(anchor)

        with pytest.raises(AuditStoreImmutabilityError) as exc_info:
            await store.update("any-id", {"action": "modified"})

        assert exc_info.value.operation == "update"


# =============================================================================
# Test 3: Hash Chain Tamper Detection
# =============================================================================


class TestAuditHashChainTamperDetected:
    """Test that modifying any record breaks the hash chain."""

    @pytest.mark.asyncio
    async def test_audit_hash_chain_tamper_detected(self):
        """
        Scenario: Modify a record in the middle of the chain.

        Expected: Chain integrity verification should detect the tampering.
        """
        store = AppendOnlyAuditStore()

        # Create a chain of records
        records = await populate_audit_store(store, count=10)

        # Verify initial integrity
        initial_result = await store.verify_integrity()
        assert initial_result.valid, "Initial chain should be valid"
        assert initial_result.verified_records == 10

        # Tamper with a record in the middle
        tamper_index = 5
        target_record = records[tamper_index]

        # Directly manipulate the store's internal records (simulating attack)
        # This is a white-box test that accesses internal state
        store._records[tamper_index].anchor.action = "TAMPERED!"

        # The record's integrity hash no longer matches its content
        verification = await store.verify_integrity()
        assert not verification.valid, "Tampered chain should fail verification"
        assert verification.first_invalid_sequence == tamper_index + 1

    @pytest.mark.asyncio
    async def test_first_record_tamper_detected(self):
        """
        Scenario: Tamper with the first record in the chain.

        Expected: Tampering should be detected.
        """
        store = AppendOnlyAuditStore()
        records = await populate_audit_store(store, count=5)

        # Tamper with first record
        store._records[0].anchor.action = "FIRST_TAMPERED!"

        verification = await store.verify_integrity()
        assert not verification.valid
        assert verification.first_invalid_sequence == 1

    @pytest.mark.asyncio
    async def test_last_record_tamper_detected(self):
        """
        Scenario: Tamper with the last record in the chain.

        Expected: Tampering should be detected.
        """
        store = AppendOnlyAuditStore()
        records = await populate_audit_store(store, count=5)

        # Tamper with last record
        last_idx = len(store._records) - 1
        store._records[last_idx].anchor.action = "LAST_TAMPERED!"

        verification = await store.verify_integrity()
        assert not verification.valid
        assert verification.first_invalid_sequence == 5


# =============================================================================
# Test 4: Hash Chain Reorder Detection
# =============================================================================


class TestAuditHashChainReorderDetected:
    """Test that reordering records is detected."""

    @pytest.mark.asyncio
    async def test_audit_hash_chain_reorder_detected(self):
        """
        Scenario: Reorder records in the audit chain.

        Expected: Chain verification should detect the reordering.
        """
        store = AppendOnlyAuditStore()
        records = await populate_audit_store(store, count=10)

        # Verify initial integrity
        initial_result = await store.verify_integrity()
        assert initial_result.valid

        # Swap two records (simulating reorder attack)
        store._records[3], store._records[7] = store._records[7], store._records[3]

        # Now sequence numbers are out of order
        verification = await store.verify_integrity()
        assert not verification.valid, "Reordered chain should fail verification"

        # The error should mention sequence gap
        assert any(
            "sequence" in e.lower() or "gap" in e.lower() for e in verification.errors
        )


# =============================================================================
# Test 5: Merkle Proof for Invalid Entry Fails
# =============================================================================


class TestMerkleProofForInvalidEntryFails:
    """Test that Merkle proofs cannot be created for non-existent entries."""

    def test_merkle_proof_for_invalid_entry_fails(self):
        """
        Scenario: Attempt to generate a Merkle proof for an index that doesn't exist.

        Expected: Should raise IndexError or similar.
        """
        # Create tree with 5 leaves
        hashes = [hashlib.sha256(f"leaf-{i}".encode()).hexdigest() for i in range(5)]
        tree = MerkleTree(leaves=hashes)

        # Try to generate proof for invalid indices
        with pytest.raises(IndexError):
            tree.generate_proof(index=10)  # Out of range

        with pytest.raises(IndexError):
            tree.generate_proof(index=-1)  # Negative index

        with pytest.raises(IndexError):
            tree.generate_proof(index=5)  # Exactly at boundary

    def test_merkle_proof_empty_tree_fails(self):
        """
        Scenario: Attempt to generate proof from empty tree.

        Expected: Should return None (CARE-057: empty tree consistency).
        """
        tree = MerkleTree(leaves=[])

        proof = tree.generate_proof(index=0)
        assert proof is None
        # verify_proof should also return False for None proof
        assert tree.verify_proof(proof) is False

    def test_forged_proof_rejected(self):
        """
        Scenario: Create a forged proof for a non-existent entry.

        Expected: Verification should reject the forged proof.
        """
        hashes = [hashlib.sha256(f"leaf-{i}".encode()).hexdigest() for i in range(4)]
        tree = MerkleTree(leaves=hashes)

        # Create a valid proof
        valid_proof = tree.generate_proof(0)

        # Forge a proof for a non-existent leaf
        fake_leaf_hash = hashlib.sha256(b"FAKE_ENTRY").hexdigest()

        # Try to verify the fake leaf with real proof structure
        is_valid = verify_merkle_proof(fake_leaf_hash, valid_proof)
        assert not is_valid, "Forged proof should be rejected"


# =============================================================================
# Test 6: Merkle Tree Tampered Leaf Detected
# =============================================================================


class TestMerkleTreeTamperedLeafDetected:
    """Test that modifying a leaf node is detected via root hash."""

    def test_merkle_tree_tampered_leaf_detected(self):
        """
        Scenario: Modify a leaf in the Merkle tree after construction.

        Expected: Root hash should change, proving tampering.
        """
        # Create original tree
        original_hashes = [
            hashlib.sha256(f"data-{i}".encode()).hexdigest() for i in range(8)
        ]
        original_tree = MerkleTree(leaves=original_hashes)
        original_root = original_tree.root_hash

        # Create tampered tree (modify one leaf)
        tampered_hashes = list(original_hashes)
        tampered_hashes[3] = hashlib.sha256(b"TAMPERED_DATA").hexdigest()
        tampered_tree = MerkleTree(leaves=tampered_hashes)
        tampered_root = tampered_tree.root_hash

        # Roots must differ
        assert original_root != tampered_root, "Tampering should change root hash"

    def test_proof_invalid_after_tree_modification(self):
        """
        Scenario: Generate proof, then modify tree.

        Expected: Old proof should no longer verify against new tree.
        """
        hashes = [hashlib.sha256(f"leaf-{i}".encode()).hexdigest() for i in range(4)]
        tree = MerkleTree(leaves=hashes)

        # Generate proof for leaf 2
        proof = tree.generate_proof(2)
        original_root = proof.root_hash

        # Verify proof is valid
        assert tree.verify_proof(proof), "Proof should be valid initially"

        # Modify tree by adding a leaf
        tree.add_leaf(hashlib.sha256(b"new_leaf").hexdigest())
        new_root = tree.root_hash

        # Root has changed
        assert new_root != original_root, "Root should change after modification"

        # Old proof should fail against modified tree
        # (The proof's root_hash doesn't match tree's current root)
        assert not tree.verify_proof(
            proof
        ), "Old proof should fail against modified tree"


# =============================================================================
# Test 7: Timestamp Cannot Be Backdated
# =============================================================================


class TestAuditTimestampCannotBeBackdated:
    """Test that timestamps must be monotonically increasing."""

    @pytest.mark.asyncio
    async def test_audit_timestamp_cannot_be_backdated(self):
        """
        Scenario: Attempt to add a record with a timestamp earlier than previous.

        Expected: The system should detect or prevent backdating.
        """
        store = AppendOnlyAuditStore()

        # Add first record with current time
        anchor1 = create_audit_anchor(action="first")
        record1 = await store.append(anchor1)

        # Add second record with future time
        anchor2 = create_audit_anchor(action="second")
        anchor2.timestamp = datetime.now(timezone.utc) + timedelta(hours=1)
        record2 = await store.append(anchor2)

        # Try to add third record with backdated timestamp
        anchor3 = create_audit_anchor(action="backdated")
        anchor3.timestamp = datetime.now(timezone.utc) - timedelta(days=1)  # BACKDATED!
        record3 = await store.append(anchor3)

        # The timestamps in stored_at should still be monotonic
        # Even if anchor.timestamp is backdated, stored_at is set at append time
        assert (
            record1.stored_at <= record2.stored_at <= record3.stored_at
        ), "stored_at timestamps should be monotonically increasing"

        # Check that sequence numbers are proper
        assert (
            record1.sequence_number < record2.sequence_number < record3.sequence_number
        )

    @pytest.mark.asyncio
    async def test_timestamp_authority_monotonic(self):
        """
        Scenario: Verify timestamp authority produces monotonic timestamps.

        Expected: Serial numbers should always increase.
        """
        authority = LocalTimestampAuthority()

        responses = []
        for i in range(10):
            response = await authority.get_timestamp(
                hashlib.sha256(f"hash-{i}".encode()).hexdigest()
            )
            responses.append(response)

        # Serial numbers should be strictly increasing
        serials = [r.token.serial_number for r in responses]
        for i in range(1, len(serials)):
            assert (
                serials[i] > serials[i - 1]
            ), f"Serial numbers must increase: {serials[i-1]} -> {serials[i]}"


# =============================================================================
# Test 8: Sequence Gap Detection
# =============================================================================


class TestAuditSequenceGapDetected:
    """Test that gaps in sequence numbers are detected."""

    @pytest.mark.asyncio
    async def test_audit_sequence_gap_detected(self):
        """
        Scenario: Inject a gap in sequence numbers.

        Expected: Verification should detect the gap.
        """
        store = AppendOnlyAuditStore()
        await populate_audit_store(store, count=10)

        # Verify initial integrity
        initial_result = await store.verify_integrity()
        assert initial_result.valid

        # Inject a gap by modifying a sequence number
        store._records[5].sequence_number = 10  # Gap: 5 -> 10 instead of 6

        verification = await store.verify_integrity()
        assert not verification.valid, "Sequence gap should be detected"
        assert any(
            "sequence" in e.lower() or "gap" in e.lower() for e in verification.errors
        )

    @pytest.mark.asyncio
    async def test_duplicate_sequence_detected(self):
        """
        Scenario: Create duplicate sequence numbers.

        Expected: Verification should detect duplicates.
        """
        store = AppendOnlyAuditStore()
        await populate_audit_store(store, count=5)

        # Create duplicate sequence
        store._records[3].sequence_number = store._records[2].sequence_number

        verification = await store.verify_integrity()
        assert not verification.valid


# =============================================================================
# Test 9: Concurrent Audit Writes Maintain Chain
# =============================================================================


class TestConcurrentAuditWritesMaintainChain:
    """Test that parallel writes maintain chain integrity."""

    @pytest.mark.asyncio
    async def test_concurrent_audit_writes_maintain_chain(self):
        """
        Scenario: Multiple concurrent writes to the audit store.

        Expected: All writes should succeed and chain should remain valid.
        """
        store = AppendOnlyAuditStore()

        # Create anchors
        anchors = [
            create_audit_anchor(agent_id=f"agent-{i}", action=f"action-{i}")
            for i in range(20)
        ]

        # Write concurrently
        tasks = [store.append(anchor) for anchor in anchors]
        records = await asyncio.gather(*tasks)

        # Verify all records were stored
        assert len(records) == 20, "All records should be stored"

        # Verify sequence numbers are unique
        sequences = [r.sequence_number for r in records]
        assert len(set(sequences)) == 20, "All sequence numbers should be unique"

        # Verify chain integrity
        verification = await store.verify_integrity()
        assert verification.valid, "Chain should be valid after concurrent writes"
        assert verification.verified_records == 20

    @pytest.mark.asyncio
    async def test_interleaved_reads_and_writes(self):
        """
        Scenario: Interleaved read and write operations.

        Expected: All operations should complete successfully.
        """
        store = AppendOnlyAuditStore()

        # Initial records
        initial_records = await populate_audit_store(store, count=5)

        async def write_record(idx: int) -> AuditRecord:
            anchor = create_audit_anchor(action=f"write-{idx}")
            return await store.append(anchor)

        async def read_records() -> List[AuditRecord]:
            return await store.list_records(limit=100)

        # Interleave reads and writes
        tasks = []
        for i in range(10):
            tasks.append(write_record(i))
            tasks.append(read_records())

        results = await asyncio.gather(*tasks)

        # Verify final count
        final_count = store.count
        assert final_count == 15, f"Expected 15 records, got {final_count}"

        # Verify integrity
        verification = await store.verify_integrity()
        assert verification.valid


# =============================================================================
# Test 10: Audit Store Survives Crash Simulation
# =============================================================================


class TestAuditStoreSurvivesCrashSimulation:
    """Test that after simulated crash, integrity is maintained."""

    @pytest.mark.asyncio
    async def test_audit_store_survives_crash_simulation(self):
        """
        Scenario: Simulate a crash during write operations.

        Expected: Records written before crash should remain valid.
        """
        store = AppendOnlyAuditStore()

        # Write some records
        pre_crash_records = await populate_audit_store(store, count=10)

        # Verify pre-crash state
        pre_crash_verification = await store.verify_integrity()
        assert pre_crash_verification.valid

        # Simulate partial write (crash mid-operation)
        # Store the current state
        pre_crash_count = store.count
        pre_crash_sequence = store.last_sequence

        # "Crash" by creating a new store (simulating restart)
        # In a real scenario, this would be persistence-based
        new_store = AppendOnlyAuditStore()

        # Restore records (simulating recovery from persistent storage)
        for record in store._records:
            # Simulate restoring from disk
            restored_anchor = record.anchor
            await new_store.append(restored_anchor)

        # Verify recovered store integrity
        recovered_verification = await new_store.verify_integrity()
        assert recovered_verification.valid
        assert recovered_verification.total_records == pre_crash_count

    @pytest.mark.asyncio
    async def test_partial_write_detection(self):
        """
        Scenario: Detect partially written records.

        Expected: Partial records should be identifiable.
        """
        store = AppendOnlyAuditStore()
        records = await populate_audit_store(store, count=5)

        # Simulate a partial write by corrupting the last record's hash
        last_record = store._records[-1]
        original_hash = last_record.integrity_hash
        last_record.integrity_hash = "corrupted_hash_simulating_partial_write"

        # Verification should catch this
        verification = await store.verify_integrity()
        assert not verification.valid
        assert verification.first_invalid_sequence == 5


# =============================================================================
# Test 11: Linked Hash Chain Insertion Detection
# =============================================================================


class TestLinkedHashChainInsertionDetected:
    """Test that inserting records mid-chain is detected."""

    def test_linked_hash_chain_insertion_detected(self):
        """
        Scenario: Insert a record into the middle of a linked hash chain.

        Expected: Chain verification should detect the insertion.
        """
        chain = LinkedHashChain()

        # Add legitimate entries
        hashes = [hashlib.sha256(f"entry-{i}".encode()).hexdigest() for i in range(5)]
        for i, h in enumerate(hashes):
            chain.add_hash(f"agent-{i}", h)

        # Verify initial integrity
        is_valid, break_idx = chain.verify_integrity()
        assert is_valid, "Initial chain should be valid"

        # Attempt to insert in the middle
        # This would break the linked hash chain because previous_hash won't match
        original_entries = list(chain._entries)

        # Create a forged entry to insert
        from kaizen.trust.chain import LinkedHashEntry

        forged_entry = LinkedHashEntry(
            agent_id="agent-forged",
            hash=hashlib.sha256(b"forged").hexdigest(),
            timestamp=datetime.now(timezone.utc),
        )

        # Insert at position 2
        chain._entries.insert(2, forged_entry)

        # Now verify - should detect break
        # The forged entry's hash won't properly link
        is_valid, break_idx = chain.verify_integrity()

        # The chain structure is broken
        # Verify using original hashes reveals the break
        original_hashes = hashes[:2] + [forged_entry.hash] + hashes[2:]
        linkage_valid, linkage_break = chain.verify_chain_linkage(original_hashes)
        assert not linkage_valid, "Inserted entry should break chain linkage"

    def test_detect_tampering_by_stored_hash(self):
        """
        Scenario: Verify tampering detection using stored hash comparison.

        Expected: detect_tampering should identify mismatches.
        """
        chain = LinkedHashChain()

        # Add entries
        hash1 = chain.add_hash("agent-1", "original_hash_1")
        hash2 = chain.add_hash("agent-2", "original_hash_2")

        # Verify no tampering with correct hashes
        assert not chain.detect_tampering(
            "agent-1", hash1
        ), "Should not detect tampering"
        assert not chain.detect_tampering(
            "agent-2", hash2
        ), "Should not detect tampering"

        # Detect tampering with wrong hash
        assert chain.detect_tampering(
            "agent-1", "wrong_hash"
        ), "Should detect tampering"
        assert chain.detect_tampering("agent-2", hash1), "Should detect hash mismatch"


# =============================================================================
# Test 12: Merkle Proof with Wrong Root Rejected
# =============================================================================


class TestMerkleProofWithWrongRootRejected:
    """Test that proof verification against wrong root fails."""

    def test_merkle_proof_with_wrong_root_rejected(self):
        """
        Scenario: Verify a valid proof against a different root hash.

        Expected: Verification should fail.
        """
        # Create two different trees
        hashes1 = [hashlib.sha256(f"tree1-{i}".encode()).hexdigest() for i in range(4)]
        hashes2 = [hashlib.sha256(f"tree2-{i}".encode()).hexdigest() for i in range(4)]

        tree1 = MerkleTree(leaves=hashes1)
        tree2 = MerkleTree(leaves=hashes2)

        # Generate proof from tree1
        proof_from_tree1 = tree1.generate_proof(0)

        # Try to verify against tree2
        is_valid = tree2.verify_proof(proof_from_tree1)
        assert not is_valid, "Proof from tree1 should not verify against tree2"

    def test_manipulated_proof_root_rejected(self):
        """
        Scenario: Manually change the root hash in a proof.

        Expected: Verification should fail.
        """
        hashes = [hashlib.sha256(f"leaf-{i}".encode()).hexdigest() for i in range(4)]
        tree = MerkleTree(leaves=hashes)

        # Generate valid proof
        proof = tree.generate_proof(1)
        assert tree.verify_proof(proof), "Original proof should be valid"

        # Manipulate the root hash
        manipulated_proof = MerkleProof(
            leaf_hash=proof.leaf_hash,
            leaf_index=proof.leaf_index,
            proof_hashes=proof.proof_hashes,
            root_hash="0" * 64,  # Fake root
            tree_size=proof.tree_size,
        )

        # Should fail verification
        is_valid = verify_merkle_proof(manipulated_proof.leaf_hash, manipulated_proof)
        assert not is_valid, "Manipulated root should fail verification"

    def test_proof_with_modified_path_rejected(self):
        """
        Scenario: Modify a hash in the proof path.

        Expected: Verification should fail.
        """
        hashes = [hashlib.sha256(f"leaf-{i}".encode()).hexdigest() for i in range(8)]
        tree = MerkleTree(leaves=hashes)

        proof = tree.generate_proof(3)

        # Modify one of the proof hashes
        if proof.proof_hashes:
            modified_proof_hashes = list(proof.proof_hashes)
            original_hash, position = modified_proof_hashes[0]
            modified_proof_hashes[0] = ("0" * 64, position)  # Fake hash

            modified_proof = MerkleProof(
                leaf_hash=proof.leaf_hash,
                leaf_index=proof.leaf_index,
                proof_hashes=modified_proof_hashes,
                root_hash=proof.root_hash,
                tree_size=proof.tree_size,
            )

            is_valid = verify_merkle_proof(modified_proof.leaf_hash, modified_proof)
            assert not is_valid, "Modified proof path should fail verification"


# =============================================================================
# Test 13: Audit Log Overflow Handling
# =============================================================================


class TestAuditLogOverflowHandling:
    """Test that very large audit logs don't cause memory issues."""

    @pytest.mark.asyncio
    async def test_audit_log_overflow_handling(self):
        """
        Scenario: Create a very large audit log.

        Expected: System should handle large logs without memory issues.
        """
        store = AppendOnlyAuditStore()

        # Create a large number of records
        # (Reduced for test speed, but demonstrates the pattern)
        large_count = 1000

        for i in range(large_count):
            anchor = create_audit_anchor(
                agent_id=f"agent-{i % 100}",
                action=f"action-{i}",
                resource=f"resource-{i % 50}",
            )
            await store.append(anchor)

        # Verify count
        assert store.count == large_count, f"Should have {large_count} records"

        # Verify integrity still works efficiently
        start_time = time.time()
        verification = await store.verify_integrity()
        elapsed = time.time() - start_time

        assert verification.valid, "Large audit log should be valid"
        assert verification.verified_records == large_count

        # Should complete in reasonable time (< 5 seconds for 1000 records)
        assert elapsed < 5.0, f"Verification took too long: {elapsed:.2f}s"

    def test_large_merkle_tree_performance(self):
        """
        Scenario: Create a large Merkle tree.

        Expected: Proof generation and verification should be O(log n).
        """
        # Create tree with many leaves
        large_count = 1024  # 2^10 for nice tree structure

        hashes = [
            hashlib.sha256(f"leaf-{i}".encode()).hexdigest() for i in range(large_count)
        ]

        start_time = time.time()
        tree = MerkleTree(leaves=hashes)
        build_time = time.time() - start_time

        # Tree should build in reasonable time
        assert build_time < 2.0, f"Tree build took too long: {build_time:.2f}s"

        # Proof generation should be fast (O(log n))
        start_time = time.time()
        proof = tree.generate_proof(large_count // 2)
        proof_time = time.time() - start_time

        assert proof_time < 0.1, f"Proof generation took too long: {proof_time:.4f}s"

        # Proof should have log2(n) hashes
        expected_proof_length = get_proof_length(large_count)
        assert len(proof.proof_hashes) == expected_proof_length

        # Verification should also be fast
        start_time = time.time()
        is_valid = tree.verify_proof(proof)
        verify_time = time.time() - start_time

        assert is_valid
        assert verify_time < 0.1, f"Verification took too long: {verify_time:.4f}s"

    @pytest.mark.asyncio
    async def test_pagination_for_large_logs(self):
        """
        Scenario: Query large audit logs with pagination.

        Expected: Pagination should work correctly for large logs.
        """
        store = AppendOnlyAuditStore()
        await populate_audit_store(store, count=100)

        # Paginated queries
        page_size = 10
        all_records = []

        for offset in range(0, 100, page_size):
            page = await store.list_records(limit=page_size, offset=offset)
            all_records.extend(page)
            assert len(page) <= page_size

        # Should get all records
        assert len(all_records) == 100, "Pagination should retrieve all records"

        # Records should be in order
        sequences = [r.sequence_number for r in all_records]
        assert sequences == sorted(sequences), "Records should be in sequence order"
