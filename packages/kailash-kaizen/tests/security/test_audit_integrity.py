"""
Security Tests for Audit Log Integrity (Tier 1)

Tests that verify the integrity of audit logs and detection of tampering.
Part of CARE-040: Security testing for trust framework.

Coverage:
- Detection of modified audit entries
- Detection of deleted audit entries
- Detection of injected fake entries
- Detection of timestamp manipulation

These tests use the AuditStore and MerkleTree implementations to verify
that any tampering with audit records is detectable.

Note: These are unit tests (Tier 1) - mocking of storage is allowed.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import List
from uuid import uuid4

import pytest
from kaizen.trust.audit_store import AppendOnlyAuditStore, AuditRecord
from kaizen.trust.chain import ActionResult, AuditAnchor
from kaizen.trust.crypto import generate_keypair, sign, verify_signature
from kaizen.trust.merkle import (
    MerkleProof,
    MerkleTree,
    compute_merkle_root,
    verify_merkle_proof,
)


def create_test_anchor(
    sequence: int,
    agent_id: str = "agent-001",
    action: str = "test_action",
) -> AuditAnchor:
    """Create a test audit anchor."""
    return AuditAnchor(
        id=f"aud-{sequence:03d}",
        agent_id=agent_id,
        action=action,
        resource=f"/api/resource/{sequence}",
        result=ActionResult.SUCCESS,
        timestamp=datetime.now(timezone.utc),
        trust_chain_hash=f"chain-hash-{sequence}",
        signature=f"sig-{sequence}",
        context={"sequence": sequence},
    )


def create_test_record(
    sequence: int,
    agent_id: str = "agent-001",
    action: str = "test_action",
    previous_hash: str = "",
) -> AuditRecord:
    """Create a test audit record with proper chaining."""
    anchor = create_test_anchor(sequence, agent_id, action)
    record = AuditRecord(
        anchor=anchor,
        sequence_number=sequence,
        previous_hash=previous_hash if previous_hash else None,
    )
    return record


class TestModifiedAuditEntryDetected:
    """Test that modifying an audit entry's content is detected."""

    def test_modified_audit_entry_detected(self):
        """
        Modifying an audit entry's content is detected.

        Audit records have an integrity hash that is computed from
        their content. If any field is modified, the integrity hash
        no longer matches, allowing tampering detection.
        """
        # Create an audit anchor and record
        anchor = AuditAnchor(
            id="aud-001",
            agent_id="agent-001",
            action="read_data",
            resource="/api/users",
            result=ActionResult.SUCCESS,
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="chain-hash-abc",
            signature="sig-001",
            context={"user_id": "user-123"},
        )
        record = AuditRecord(anchor=anchor, sequence_number=1)

        # Store the original integrity hash
        original_hash = record.integrity_hash

        # Verify integrity check passes initially
        assert record.verify_integrity(), "Initial integrity should pass"

        # Attempt to modify the action (simulating tampering)
        original_action = record.anchor.action
        record.anchor.action = "delete_data"  # Tampered!

        # Recompute hash - it should be different
        # Note: The stored integrity_hash won't update automatically
        # but verify_integrity() will fail because recomputed hash differs
        assert not record.verify_integrity(), (
            "Tampered record should fail integrity check"
        )

        # Restore original to verify integrity check passes again
        record.anchor.action = original_action
        assert record.verify_integrity(), "Restored record should pass integrity check"

    def test_any_field_modification_detected(self):
        """
        Modification of ANY field is detected through the integrity hash.
        """
        anchor = AuditAnchor(
            id="aud-002",
            agent_id="agent-002",
            action="update_data",
            resource="/api/products/123",
            result=ActionResult.SUCCESS,
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="chain-hash-xyz",
            signature="sig-002",
            context={"product_id": "123"},
        )
        record = AuditRecord(anchor=anchor, sequence_number=2)

        # Verify initial integrity
        assert record.verify_integrity()

        # Test modification of each field
        fields_to_test = [
            ("agent_id", "malicious-agent"),
            ("resource", "/api/admin/delete-all"),
            ("trust_chain_hash", "fake-chain-hash"),
        ]

        for field_name, tampered_value in fields_to_test:
            # Store original
            original_value = getattr(record.anchor, field_name)

            # Tamper
            setattr(record.anchor, field_name, tampered_value)

            # Verify tampering is detected
            assert not record.verify_integrity(), (
                f"Modifying {field_name} should fail integrity check"
            )

            # Restore
            setattr(record.anchor, field_name, original_value)

        # After all restorations, integrity should pass
        assert record.verify_integrity()

    def test_merkle_tree_detects_modification(self):
        """
        Merkle tree verification detects modified entries.

        When an entry is modified after the tree is built,
        the proof for that entry becomes invalid. The stored integrity
        hash in the Merkle tree remains unchanged, but verify_integrity()
        on the individual record will fail.

        Additionally, if an attacker tries to create new records with
        modified content, the new tree will have a different root hash.
        """
        # Create a series of records
        records = []
        prev_hash = ""
        for i in range(8):
            record = create_test_record(i, previous_hash=prev_hash)
            prev_hash = record.integrity_hash
            records.append(record)

        # Build Merkle tree from records
        tree = MerkleTree.from_audit_records(records)
        original_root = tree.root_hash

        # Generate proof for record at index 3
        proof = tree.generate_proof(3)
        assert tree.verify_proof(proof), "Proof should be valid for original tree"

        # Store the original leaf hash for the record
        original_leaf_hash = records[3].integrity_hash

        # Modify the record at index 3
        records[3].anchor.action = "TAMPERED_ACTION"

        # The individual record should fail integrity verification
        assert not records[3].verify_integrity(), (
            "Modified record should fail integrity check"
        )

        # Proof with original leaf hash still verifies against original tree
        # because the proof was generated with the original hash
        assert tree.verify_proof(proof), (
            "Original proof still valid against original tree"
        )

        # But if we try to verify with a recomputed leaf hash (simulating
        # an attacker trying to create a valid proof for tampered data),
        # we would need to create new records with the tampered content.

        # Create a new record with the tampered action (simulating attacker
        # trying to forge records)
        tampered_anchor = AuditAnchor(
            id=records[3].anchor.id,
            agent_id=records[3].anchor.agent_id,
            action="TAMPERED_ACTION",  # Different from original
            resource=records[3].anchor.resource,
            result=records[3].anchor.result,
            timestamp=records[3].anchor.timestamp,
            trust_chain_hash=records[3].anchor.trust_chain_hash,
            signature=records[3].anchor.signature,
            context=records[3].anchor.context,
        )
        tampered_record = AuditRecord(
            anchor=tampered_anchor,
            sequence_number=records[3].sequence_number,
            previous_hash=records[3].previous_hash,
        )

        # The tampered record has a different integrity hash
        tampered_leaf_hash = tampered_record.integrity_hash
        assert tampered_leaf_hash != original_leaf_hash, (
            "Tampered record should have different integrity hash"
        )

        # Trying to use the original proof with the tampered leaf fails
        tampered_proof = MerkleProof(
            leaf_hash=tampered_leaf_hash,
            leaf_index=proof.leaf_index,
            proof_hashes=proof.proof_hashes,
            root_hash=proof.root_hash,
            tree_size=proof.tree_size,
        )
        assert not verify_merkle_proof(tampered_leaf_hash, tampered_proof), (
            "Proof with tampered leaf hash should fail"
        )


class TestDeletedAuditEntryDetected:
    """Test that removing an audit entry breaks the chain."""

    def test_deleted_audit_entry_detected(self):
        """
        Removing an audit entry breaks the chain.

        Audit records form a hash chain where each record includes
        the hash of the previous record. Deleting a record breaks
        this chain and is detectable.
        """
        # Create a chain of records
        records: List[AuditRecord] = []
        prev_hash = ""

        for i in range(5):
            record = create_test_record(i, previous_hash=prev_hash)
            prev_hash = record.integrity_hash
            records.append(record)

        # Verify the chain is intact
        def verify_chain(chain: List[AuditRecord]) -> bool:
            """Verify that hash chain is intact."""
            expected_prev = ""
            for record in chain:
                current_prev = record.previous_hash or ""
                if current_prev != expected_prev:
                    return False
                expected_prev = record.integrity_hash
            return True

        assert verify_chain(records), "Original chain should be valid"

        # Delete the record at index 2
        deleted_record = records.pop(2)

        # Chain should now be broken
        assert not verify_chain(records), (
            "Deleting a record should break the hash chain"
        )

    def test_merkle_tree_detects_deletion(self):
        """
        Merkle tree detects deleted entries.

        When an entry is deleted, the Merkle tree structure changes
        and any proofs generated before the deletion become invalid.
        """
        # Create records
        records = [create_test_record(i) for i in range(8)]

        # Build tree and generate proofs for all entries
        original_tree = MerkleTree.from_audit_records(records)
        original_proofs = [original_tree.generate_proof(i) for i in range(8)]

        # Verify all proofs are valid
        for proof in original_proofs:
            assert verify_merkle_proof(proof.leaf_hash, proof)

        # Delete a record (simulating tampering)
        deleted_index = 4
        remaining_records = records[:deleted_index] + records[deleted_index + 1 :]

        # Build new tree without the deleted record
        tampered_tree = MerkleTree.from_audit_records(remaining_records)

        # Root hash should be different
        assert tampered_tree.root_hash != original_tree.root_hash, (
            "Deleting a record should change the Merkle root"
        )

        # Original proofs are now invalid
        # The proof for the deleted entry definitely won't work
        deleted_proof = original_proofs[deleted_index]
        assert not tampered_tree.verify_proof(deleted_proof), (
            "Proof for deleted entry should fail"
        )

    def test_chain_gap_detection(self):
        """
        Test that gaps in sequence numbering are detected.
        """
        records = []
        prev_hash = ""

        # Create records with sequential IDs
        for i in range(5):
            anchor = AuditAnchor(
                id=f"aud-{i:03d}",
                agent_id="agent-001",
                action="test",
                resource=f"/resource/{i}",
                result=ActionResult.SUCCESS,
                timestamp=datetime.now(timezone.utc),
                trust_chain_hash="hash",
                signature=f"sig-{i}",
                context={"seq": i},
            )
            record = AuditRecord(
                anchor=anchor,
                sequence_number=i + 1,
                previous_hash=prev_hash if prev_hash else None,
            )
            prev_hash = record.integrity_hash
            records.append(record)

        # Extract sequence numbers
        def get_sequence_numbers(chain: List[AuditRecord]) -> List[int]:
            return [r.sequence_number for r in chain]

        original_sequences = get_sequence_numbers(records)
        assert original_sequences == [1, 2, 3, 4, 5], "Original should be sequential"

        # Delete record at index 2 (sequence_number 3)
        del records[2]

        modified_sequences = get_sequence_numbers(records)
        assert modified_sequences == [1, 2, 4, 5], "Deletion creates a gap"

        # Detect the gap
        def has_gap(sequences: List[int]) -> bool:
            for i in range(1, len(sequences)):
                if sequences[i] - sequences[i - 1] != 1:
                    return True
            return False

        assert has_gap(modified_sequences), "Gap should be detected"


class TestInjectedAuditEntryDetected:
    """Test that injecting a fake entry is detected."""

    def test_injected_audit_entry_detected(self):
        """
        Injecting a fake entry is detected.

        Fake entries cannot have valid previous_hash links unless
        the attacker knows the hash of existing records. Even then,
        the chain would be broken after the injection point.
        """
        # Create original chain
        records = []
        prev_hash = ""
        for i in range(4):
            record = create_test_record(i, previous_hash=prev_hash)
            prev_hash = record.integrity_hash
            records.append(record)

        # Attacker creates a fake record
        fake_anchor = AuditAnchor(
            id="aud-fake",
            agent_id="legitimate-agent",  # Attacker pretends to be legitimate
            action="read_sensitive_data",  # Fake action
            resource="/api/admin/secrets",
            result=ActionResult.SUCCESS,
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="fake-chain-hash",
            signature="fake-sig",
            context={"injected": True},
        )
        fake_record = AuditRecord(
            anchor=fake_anchor,
            sequence_number=99,
            previous_hash="invalid-prev-hash",  # Attacker doesn't know real hash
        )

        # Insert fake record at position 2
        tampered_chain = records[:2] + [fake_record] + records[2:]

        # Verify chain is broken
        def verify_chain(chain: List[AuditRecord]) -> tuple[bool, int]:
            """Verify chain and return (is_valid, break_point)."""
            expected_prev = ""
            for i, record in enumerate(chain):
                current_prev = record.previous_hash or ""
                if current_prev != expected_prev:
                    return False, i
                expected_prev = record.integrity_hash
            return True, -1

        is_valid, break_point = verify_chain(tampered_chain)
        assert not is_valid, "Injected record should break the chain"
        assert break_point == 2, "Break should be at injection point"

    def test_merkle_tree_detects_injection(self):
        """
        Merkle tree detects injected entries.

        Adding an entry changes the tree structure and root hash,
        making it detectable through comparison with stored root.
        """
        # Create original records and tree
        original_records = [create_test_record(i) for i in range(8)]
        original_tree = MerkleTree.from_audit_records(original_records)
        original_root = original_tree.root_hash

        # Store a proof for later verification
        proof_for_record_3 = original_tree.generate_proof(3)

        # Inject a fake record
        fake_anchor = AuditAnchor(
            id="aud-injected",
            agent_id="fake-agent",
            action="fake_action",
            resource="/fake",
            result=ActionResult.SUCCESS,
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="fake",
            signature="fake",
            context={},
        )
        fake_record = AuditRecord(anchor=fake_anchor, sequence_number=99)

        # Insert at position 4
        tampered_records = original_records[:4] + [fake_record] + original_records[4:]

        # Build new tree with injected record
        tampered_tree = MerkleTree.from_audit_records(tampered_records)

        # Root hash should be different
        assert tampered_tree.root_hash != original_root, (
            "Injection should change Merkle root"
        )

        # Original proofs may not verify against tampered tree
        # (depends on where injection occurred relative to proof)

    def test_injection_without_proper_signature(self):
        """
        Injected entries without proper signatures are detected.

        Each audit record can be signed by the authority. Fake
        entries won't have valid signatures.
        """
        org_priv, org_pub = generate_keypair()
        attacker_priv, attacker_pub = generate_keypair()

        # Create a legitimate signed record
        legitimate_anchor = AuditAnchor(
            id="aud-legit",
            agent_id="agent-001",
            action="legitimate_action",
            resource="/api/data",
            result=ActionResult.SUCCESS,
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="chain-hash",
            signature="placeholder",
            context={},
        )
        legitimate_record = AuditRecord(anchor=legitimate_anchor, sequence_number=1)

        # Sign with org's key
        signature = sign(legitimate_record.integrity_hash, org_priv)

        # Verify legitimate signature
        assert verify_signature(legitimate_record.integrity_hash, signature, org_pub)

        # Attacker creates fake record
        fake_anchor = AuditAnchor(
            id="aud-fake",
            agent_id="agent-001",  # Pretending to be legitimate
            action="steal_data",
            resource="/api/secrets",
            result=ActionResult.SUCCESS,
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="chain-hash",
            signature="fake-sig",
            context={},
        )
        fake_record = AuditRecord(anchor=fake_anchor, sequence_number=2)

        # Attacker signs with their own key
        fake_signature = sign(fake_record.integrity_hash, attacker_priv)

        # Verification with org's key fails
        assert not verify_signature(
            fake_record.integrity_hash, fake_signature, org_pub
        ), "Fake signature should not verify with org's key"


class TestTimestampManipulationDetected:
    """Test that changing timestamps is detected."""

    def test_timestamp_manipulation_detected(self):
        """
        Changing timestamps is detected.

        Timestamps are included in the integrity hash calculation,
        so any modification to the timestamp changes the hash.
        """
        anchor = AuditAnchor(
            id="aud-001",
            agent_id="agent-001",
            action="process_data",
            resource="/api/process",
            result=ActionResult.SUCCESS,
            timestamp=datetime.now(timezone.utc),
            trust_chain_hash="chain-hash",
            signature="sig-001",
            context={},
        )
        record = AuditRecord(anchor=anchor, sequence_number=1)

        # Verify initial integrity passes
        assert record.verify_integrity()

        original_timestamp = record.anchor.timestamp

        # Manipulate timestamp (backdating attack)
        record.anchor.timestamp = original_timestamp - timedelta(days=30)

        # Integrity check should fail
        assert not record.verify_integrity(), (
            "Backdating timestamp should fail integrity check"
        )

        # Forward-dating also detected
        record.anchor.timestamp = original_timestamp + timedelta(days=30)
        assert not record.verify_integrity(), (
            "Forward-dating timestamp should fail integrity check"
        )

        # Restore original
        record.anchor.timestamp = original_timestamp
        assert record.verify_integrity()

    def test_timestamp_ordering_verification(self):
        """
        Verify that timestamps maintain proper ordering.

        Audit records should have monotonically increasing timestamps.
        Out-of-order timestamps indicate tampering.
        """
        records = []
        base_time = datetime.now(timezone.utc)

        # Create properly ordered records
        for i in range(5):
            anchor = AuditAnchor(
                id=f"aud-{i:03d}",
                agent_id="agent-001",
                action="test",
                resource=f"/resource/{i}",
                result=ActionResult.SUCCESS,
                timestamp=base_time + timedelta(seconds=i * 10),
                trust_chain_hash="hash",
                signature=f"sig-{i}",
                context={},
            )
            record = AuditRecord(anchor=anchor, sequence_number=i + 1)
            records.append(record)

        def check_timestamp_order(chain: List[AuditRecord]) -> tuple[bool, int]:
            """Verify timestamps are monotonically increasing."""
            for i in range(1, len(chain)):
                if chain[i].anchor.timestamp < chain[i - 1].anchor.timestamp:
                    return False, i
            return True, -1

        # Original order is valid
        is_valid, _ = check_timestamp_order(records)
        assert is_valid, "Original timestamps should be in order"

        # Tamper with a timestamp (make record 3 appear before record 2)
        records[3].anchor.timestamp = records[1].anchor.timestamp - timedelta(seconds=5)

        is_valid, violation_index = check_timestamp_order(records)
        assert not is_valid, "Out-of-order timestamp should be detected"
        assert violation_index == 3, "Violation should be at tampered record"

    def test_merkle_tree_includes_timestamp(self):
        """
        Verify that Merkle tree verification includes timestamp integrity.

        Since timestamps affect the integrity hash, they are inherently
        protected by the Merkle tree. When timestamp is modified in an
        existing record, verify_integrity() detects the change. When
        creating new records with tampered timestamps, the hash differs.
        """
        # Create records with specific timestamps
        records = []
        base_time = datetime.now(timezone.utc)

        for i in range(4):
            anchor = AuditAnchor(
                id=f"aud-{i:03d}",
                agent_id="agent-001",
                action="test",
                resource=f"/resource/{i}",
                result=ActionResult.SUCCESS,
                timestamp=base_time + timedelta(minutes=i),
                trust_chain_hash="hash",
                signature=f"sig-{i}",
                context={},
            )
            record = AuditRecord(anchor=anchor, sequence_number=i + 1)
            records.append(record)

        # Build tree
        original_tree = MerkleTree.from_audit_records(records)
        original_root = original_tree.root_hash

        # Generate proof for record 2
        proof = original_tree.generate_proof(2)
        assert verify_merkle_proof(proof.leaf_hash, proof)

        # Store original integrity hash
        original_leaf_hash = records[2].integrity_hash

        # Tamper with timestamp of record 2
        records[2].anchor.timestamp = base_time - timedelta(days=1)

        # The record fails individual integrity check
        assert not records[2].verify_integrity(), (
            "Tampered timestamp should fail integrity check"
        )

        # Original proof is still valid against original tree because
        # the stored hash hasn't changed (only verify_integrity detects it)
        assert original_tree.verify_proof(proof), (
            "Original proof still valid against original tree"
        )

        # To show timestamp affects hash, create a new record with tampered time
        tampered_anchor = AuditAnchor(
            id=records[2].anchor.id,
            agent_id=records[2].anchor.agent_id,
            action=records[2].anchor.action,
            resource=records[2].anchor.resource,
            result=records[2].anchor.result,
            timestamp=base_time - timedelta(days=1),  # Tampered timestamp
            trust_chain_hash=records[2].anchor.trust_chain_hash,
            signature=records[2].anchor.signature,
            context=records[2].anchor.context,
        )
        tampered_record = AuditRecord(anchor=tampered_anchor, sequence_number=3)

        # The tampered record has a different integrity hash
        tampered_leaf_hash = tampered_record.integrity_hash
        assert tampered_leaf_hash != original_leaf_hash, (
            "Tampered timestamp produces different hash"
        )

        # A proof generated with tampered hash won't match original root
        tampered_proof = MerkleProof(
            leaf_hash=tampered_leaf_hash,
            leaf_index=proof.leaf_index,
            proof_hashes=proof.proof_hashes,
            root_hash=proof.root_hash,
            tree_size=proof.tree_size,
        )
        assert not verify_merkle_proof(tampered_leaf_hash, tampered_proof), (
            "Tampered timestamp hash doesn't match original proof"
        )

    def test_future_timestamp_detection(self):
        """
        Detect attempts to create records with future timestamps.

        Records should not have timestamps in the future, as this
        could be used to manipulate audit trail ordering.
        """
        now = datetime.now(timezone.utc)

        # Create a record with future timestamp
        future_anchor = AuditAnchor(
            id="aud-future",
            agent_id="agent-001",
            action="test",
            resource="/resource",
            result=ActionResult.SUCCESS,
            timestamp=now + timedelta(hours=1),  # 1 hour in the future
            trust_chain_hash="hash",
            signature="sig",
            context={},
        )
        future_record = AuditRecord(anchor=future_anchor, sequence_number=1)

        def is_timestamp_valid(
            record: AuditRecord, tolerance_seconds: int = 60
        ) -> bool:
            """Check if timestamp is not in the future (with tolerance)."""
            max_allowed = datetime.now(timezone.utc) + timedelta(
                seconds=tolerance_seconds
            )
            return record.anchor.timestamp <= max_allowed

        # Future timestamp should be rejected
        assert not is_timestamp_valid(future_record), (
            "Future timestamp should be detected"
        )

        # Record with current timestamp should be valid
        current_anchor = AuditAnchor(
            id="aud-current",
            agent_id="agent-001",
            action="test",
            resource="/resource",
            result=ActionResult.SUCCESS,
            timestamp=now,
            trust_chain_hash="hash",
            signature="sig",
            context={},
        )
        current_record = AuditRecord(anchor=current_anchor, sequence_number=2)

        assert is_timestamp_valid(current_record), "Current timestamp should be valid"
