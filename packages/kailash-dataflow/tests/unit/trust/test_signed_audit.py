#!/usr/bin/env python3
"""
Unit Tests for Signed Audit Records (CARE-020).

Tests the cryptographic signing and chain-linking functionality for
DataFlow audit records. These tests use real Ed25519 keys for
cryptographic operations (mocking is allowed for Tier 1 but real crypto
is preferred for accuracy).

Test Coverage:
- SignedAuditRecord creation and serialization
- Ed25519 signing and verification
- SHA-256 hash chain linking
- DataFlowAuditStore operations
- Performance and edge cases

Total: 30 tests organized into 5 groups
"""

import base64
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import List, Optional
from unittest.mock import MagicMock

import pytest

# Import cryptography library for real key operations
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from dataflow.trust.audit import DataFlowAuditStore, SignedAuditRecord

# === Fixtures ===


@pytest.fixture
def ed25519_keypair():
    """Generate a real Ed25519 key pair for testing."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    return {
        "private_key": private_key,
        "public_key": public_key,
        "private_bytes": private_bytes,
        "public_bytes": public_bytes,
    }


@pytest.fixture
def second_keypair():
    """Generate a second Ed25519 key pair for wrong-key tests."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    return {
        "private_key": private_key,
        "public_key": public_key,
        "public_bytes": public_bytes,
    }


@pytest.fixture
def audit_store(ed25519_keypair):
    """Create DataFlowAuditStore with real signing key."""
    return DataFlowAuditStore(
        signing_key=ed25519_keypair["private_bytes"],
        verify_key=ed25519_keypair["public_bytes"],
        enabled=True,
    )


@pytest.fixture
def audit_store_no_keys():
    """Create DataFlowAuditStore without signing keys (graceful degradation).

    Uses strict_verification=False to allow graceful degradation for
    development/testing scenarios where keys are intentionally not configured.
    """
    return DataFlowAuditStore(
        signing_key=None,
        verify_key=None,
        enabled=True,
        strict_verification=False,  # Allow graceful degradation for testing
    )


@pytest.fixture
def sample_record():
    """Create a sample SignedAuditRecord for testing."""
    return SignedAuditRecord(
        record_id="rec-001",
        timestamp=datetime(2025, 2, 8, 12, 0, 0, tzinfo=timezone.utc),
        agent_id="agent-test-001",
        human_origin_id="alice@corp.com",
        model="User",
        operation="SELECT",
        row_count=10,
        query_hash="abc123def456ghij",
        constraints_applied=["data_scope:department:finance"],
        result="success",
        signature="base64signature==",
        previous_record_hash=None,
        sequence_number=0,
    )


# === Group 1: SignedAuditRecord Creation (5 tests) ===


class TestSignedAuditRecordCreation:
    """Tests for SignedAuditRecord dataclass creation."""

    def test_create_record_with_all_fields(self):
        """Test creating a record with all fields populated."""
        record = SignedAuditRecord(
            record_id="rec-full-001",
            timestamp=datetime(2025, 2, 8, 12, 0, 0, tzinfo=timezone.utc),
            agent_id="agent-test-001",
            human_origin_id="alice@corp.com",
            model="User",
            operation="SELECT",
            row_count=10,
            query_hash="abc123def456ghij",
            constraints_applied=["data_scope:department:finance", "row_limit:1000"],
            result="success",
            signature="base64signature==",
            previous_record_hash="prev_hash_abc123",
            sequence_number=5,
        )

        assert record.record_id == "rec-full-001"
        assert record.timestamp == datetime(2025, 2, 8, 12, 0, 0, tzinfo=timezone.utc)
        assert record.agent_id == "agent-test-001"
        assert record.human_origin_id == "alice@corp.com"
        assert record.model == "User"
        assert record.operation == "SELECT"
        assert record.row_count == 10
        assert record.query_hash == "abc123def456ghij"
        assert len(record.constraints_applied) == 2
        assert record.result == "success"
        assert record.signature == "base64signature=="
        assert record.previous_record_hash == "prev_hash_abc123"
        assert record.sequence_number == 5

    def test_create_record_minimal(self):
        """Test creating a record with only required fields (minimal)."""
        record = SignedAuditRecord(
            record_id="rec-min-001",
            timestamp=datetime.now(timezone.utc),
            agent_id="agent-001",
            human_origin_id=None,
            model="Order",
            operation="INSERT",
            row_count=1,
            query_hash="",
            constraints_applied=[],
            result="success",
            signature="unsigned",
            previous_record_hash=None,
            sequence_number=0,
        )

        assert record.record_id == "rec-min-001"
        assert record.human_origin_id is None
        assert record.previous_record_hash is None
        assert record.sequence_number == 0

    def test_record_compute_hash_deterministic(self, sample_record):
        """Test that compute_hash() produces the same hash for same input."""
        hash1 = sample_record.compute_hash()
        hash2 = sample_record.compute_hash()

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 produces 64 hex chars

    def test_record_different_inputs_different_hashes(self):
        """Test that different record data produces different hashes."""
        record1 = SignedAuditRecord(
            record_id="rec-001",
            timestamp=datetime(2025, 2, 8, 12, 0, 0, tzinfo=timezone.utc),
            agent_id="agent-001",
            human_origin_id=None,
            model="User",
            operation="SELECT",
            row_count=10,
            query_hash="hash1",
            constraints_applied=[],
            result="success",
            signature="sig1",
            previous_record_hash=None,
            sequence_number=0,
        )

        record2 = SignedAuditRecord(
            record_id="rec-002",  # Different ID
            timestamp=datetime(2025, 2, 8, 12, 0, 0, tzinfo=timezone.utc),
            agent_id="agent-001",
            human_origin_id=None,
            model="User",
            operation="SELECT",
            row_count=10,
            query_hash="hash1",
            constraints_applied=[],
            result="success",
            signature="sig1",
            previous_record_hash=None,
            sequence_number=0,
        )

        hash1 = record1.compute_hash()
        hash2 = record2.compute_hash()

        assert hash1 != hash2

    def test_record_to_dict_and_from_dict(self, sample_record):
        """Test roundtrip serialization to dict and back."""
        data = sample_record.to_dict()

        assert isinstance(data, dict)
        assert data["record_id"] == "rec-001"
        assert data["agent_id"] == "agent-test-001"
        assert data["model"] == "User"
        assert data["operation"] == "SELECT"

        # Reconstruct from dict
        reconstructed = SignedAuditRecord.from_dict(data)

        assert reconstructed.record_id == sample_record.record_id
        assert reconstructed.agent_id == sample_record.agent_id
        assert reconstructed.model == sample_record.model
        assert reconstructed.operation == sample_record.operation
        assert reconstructed.row_count == sample_record.row_count
        assert reconstructed.signature == sample_record.signature


# === Group 2: Signing and Verification (6 tests) ===


class TestSigningAndVerification:
    """Tests for Ed25519 signature generation and verification."""

    def test_sign_record_with_key(self, audit_store, ed25519_keypair):
        """Test that recording a query produces a valid signature."""
        record = audit_store.record_query(
            agent_id="agent-001",
            model="User",
            operation="SELECT",
            row_count=10,
            query_params={"id": 1},
            result="success",
        )

        # Signature should be a base64 string, not "unsigned"
        assert record.signature != "unsigned"
        assert len(record.signature) > 0

        # Signature should decode from base64
        try:
            sig_bytes = base64.b64decode(record.signature)
            assert len(sig_bytes) == 64  # Ed25519 signatures are 64 bytes
        except Exception as e:
            pytest.fail(f"Signature is not valid base64: {e}")

    def test_verify_valid_signature(self, audit_store):
        """Test that a valid signature verifies successfully."""
        record = audit_store.record_query(
            agent_id="agent-002",
            model="Order",
            operation="SELECT",
            row_count=5,
            result="success",
        )

        # Verify the signature
        is_valid = audit_store.verify_record(record)

        assert is_valid is True

    def test_verify_tampered_record(self, audit_store):
        """Test that a tampered record fails verification."""
        record = audit_store.record_query(
            agent_id="agent-003",
            model="Transaction",
            operation="SELECT",
            row_count=20,
            result="success",
        )

        # Tamper with the record - change the operation
        # Create a modified record with same signature but different data
        tampered = SignedAuditRecord(
            record_id=record.record_id,
            timestamp=record.timestamp,
            agent_id=record.agent_id,
            human_origin_id=record.human_origin_id,
            model=record.model,
            operation="DELETE",  # Changed from SELECT
            row_count=record.row_count,
            query_hash=record.query_hash,
            constraints_applied=record.constraints_applied,
            result=record.result,
            signature=record.signature,  # Keep original signature
            previous_record_hash=record.previous_record_hash,
            sequence_number=record.sequence_number,
        )

        # Verification should fail
        is_valid = audit_store.verify_record(tampered)

        assert is_valid is False

    def test_verify_wrong_key(self, audit_store, second_keypair):
        """Test that verification with wrong public key fails."""
        record = audit_store.record_query(
            agent_id="agent-004",
            model="User",
            operation="SELECT",
            row_count=15,
            result="success",
        )

        # Create a new store with different public key
        wrong_key_store = DataFlowAuditStore(
            signing_key=None,  # No signing key
            verify_key=second_keypair["public_bytes"],  # Wrong public key
            enabled=True,
        )

        # Verification should fail with wrong key
        is_valid = wrong_key_store.verify_record(record)

        assert is_valid is False

    def test_unsigned_record_when_no_key(self, audit_store_no_keys):
        """Test that records without signing key get 'unsigned' signature."""
        record = audit_store_no_keys.record_query(
            agent_id="agent-005",
            model="User",
            operation="SELECT",
            row_count=10,
            result="success",
        )

        assert record.signature == "unsigned"

    def test_verify_unsigned_record_returns_true(self, audit_store_no_keys):
        """Test that unsigned records pass verification (graceful degradation)."""
        record = audit_store_no_keys.record_query(
            agent_id="agent-006",
            model="Order",
            operation="SELECT",
            row_count=5,
            result="success",
        )

        # Unsigned records should pass verification (graceful mode)
        is_valid = audit_store_no_keys.verify_record(record)

        assert is_valid is True


# === Group 3: Hash Chain Linking (6 tests) ===


class TestHashChainLinking:
    """Tests for hash chain linking functionality."""

    def test_first_record_has_no_previous_hash(self, audit_store):
        """Test that the first record has no previous_record_hash."""
        record = audit_store.record_query(
            agent_id="agent-chain-001",
            model="User",
            operation="SELECT",
            row_count=1,
            result="success",
        )

        assert record.previous_record_hash is None
        assert record.sequence_number == 0

    def test_second_record_links_to_first(self, audit_store):
        """Test that second record contains hash of first record."""
        first = audit_store.record_query(
            agent_id="agent-chain-002",
            model="User",
            operation="SELECT",
            row_count=1,
            result="success",
        )

        second = audit_store.record_query(
            agent_id="agent-chain-002",
            model="Order",
            operation="INSERT",
            row_count=1,
            result="success",
        )

        # Second record should link to first
        assert second.previous_record_hash is not None
        assert second.previous_record_hash == first.compute_hash()
        assert second.sequence_number == 1

    def test_chain_of_five_records(self, audit_store):
        """Test that a chain of 5 records links correctly."""
        records = []

        for i in range(5):
            record = audit_store.record_query(
                agent_id=f"agent-chain-{i}",
                model="User",
                operation="SELECT",
                row_count=i + 1,
                result="success",
            )
            records.append(record)

        # Verify chain linking
        assert records[0].previous_record_hash is None
        assert records[0].sequence_number == 0

        for i in range(1, 5):
            assert records[i].previous_record_hash == records[i - 1].compute_hash()
            assert records[i].sequence_number == i

    def test_verify_chain_integrity_valid(self, audit_store):
        """Test that verify_chain_integrity passes for valid chain."""
        # Create 3 records
        for i in range(3):
            audit_store.record_query(
                agent_id=f"agent-valid-{i}",
                model="User",
                operation="SELECT",
                row_count=i + 1,
                result="success",
            )

        is_valid, error = audit_store.verify_chain_integrity()

        assert is_valid is True
        assert error is None

    def test_verify_chain_integrity_tampered(self, audit_store):
        """Test that verify_chain_integrity detects tampered records."""
        # Create 3 records
        for i in range(3):
            audit_store.record_query(
                agent_id=f"agent-tamper-{i}",
                model="User",
                operation="SELECT",
                row_count=i + 1,
                result="success",
            )

        # Tamper with middle record (index 1)
        records = audit_store.get_records()
        if len(records) >= 2:
            # Modify the row_count which affects the hash
            tampered = SignedAuditRecord(
                record_id=records[1].record_id,
                timestamp=records[1].timestamp,
                agent_id=records[1].agent_id,
                human_origin_id=records[1].human_origin_id,
                model=records[1].model,
                operation=records[1].operation,
                row_count=999,  # Changed!
                query_hash=records[1].query_hash,
                constraints_applied=records[1].constraints_applied,
                result=records[1].result,
                signature=records[1].signature,
                previous_record_hash=records[1].previous_record_hash,
                sequence_number=records[1].sequence_number,
            )
            # Replace the record in the internal list
            audit_store._records[1] = tampered

        is_valid, error = audit_store.verify_chain_integrity()

        assert is_valid is False
        assert error is not None
        # Tampering can be detected via signature verification or hash mismatch
        assert (
            "tamper" in error.lower()
            or "integrity" in error.lower()
            or "mismatch" in error.lower()
            or "signature"
            in error.lower()  # Signature verification catches tampering too
        )

    def test_verify_chain_integrity_missing_record(self, audit_store):
        """Test that verify_chain_integrity detects gap in sequence."""
        # Create 3 records
        for i in range(3):
            audit_store.record_query(
                agent_id=f"agent-gap-{i}",
                model="User",
                operation="SELECT",
                row_count=i + 1,
                result="success",
            )

        # Remove middle record to create a gap
        records = audit_store.get_records()
        if len(records) >= 3:
            del audit_store._records[1]  # Remove record at sequence 1

        is_valid, error = audit_store.verify_chain_integrity()

        assert is_valid is False
        assert error is not None


# === Group 4: DataFlowAuditStore Operations (8 tests) ===


class TestDataFlowAuditStoreOperations:
    """Tests for DataFlowAuditStore class operations."""

    def test_record_query_creates_record(self, audit_store):
        """Test that record_query produces a SignedAuditRecord."""
        record = audit_store.record_query(
            agent_id="agent-op-001",
            model="User",
            operation="SELECT",
            row_count=10,
            query_params={"active": True},
            constraints_applied=["data_scope:department:finance"],
            result="success",
            human_origin_id="alice@corp.com",
        )

        assert isinstance(record, SignedAuditRecord)
        assert record.agent_id == "agent-op-001"
        assert record.model == "User"
        assert record.operation == "SELECT"
        assert record.row_count == 10
        assert record.human_origin_id == "alice@corp.com"
        assert "data_scope:department:finance" in record.constraints_applied

    def test_record_write_creates_record(self, audit_store):
        """Test that record_write produces a SignedAuditRecord."""
        record = audit_store.record_write(
            agent_id="agent-op-002",
            model="Order",
            operation="INSERT",
            row_count=1,
            data={"product_id": 123, "quantity": 5},
            result="success",
            human_origin_id="bob@corp.com",
        )

        assert isinstance(record, SignedAuditRecord)
        assert record.agent_id == "agent-op-002"
        assert record.model == "Order"
        assert record.operation == "INSERT"
        assert record.row_count == 1
        assert record.human_origin_id == "bob@corp.com"

    def test_sequence_numbers_increment(self, audit_store):
        """Test that sequence numbers auto-increment."""
        records = []
        for i in range(5):
            record = audit_store.record_query(
                agent_id="agent-seq",
                model="User",
                operation="SELECT",
                row_count=1,
                result="success",
            )
            records.append(record)

        for i, record in enumerate(records):
            assert record.sequence_number == i

    def test_query_hash_computation(self, audit_store):
        """Test that query params are hashed correctly (16 chars)."""
        record = audit_store.record_query(
            agent_id="agent-hash-001",
            model="User",
            operation="SELECT",
            row_count=10,
            query_params={"id": 1, "active": True, "department": "finance"},
            result="success",
        )

        # Query hash should be 16 characters
        assert len(record.query_hash) == 16

    def test_query_hash_deterministic(self, audit_store):
        """Test that same query params produce same hash."""
        params = {"id": 1, "name": "test", "active": True}

        hash1 = DataFlowAuditStore.compute_query_hash(params)
        hash2 = DataFlowAuditStore.compute_query_hash(params)

        assert hash1 == hash2
        assert len(hash1) == 16

    def test_get_records_by_agent(self, audit_store):
        """Test filtering records by agent ID."""
        # Create records for different agents
        audit_store.record_query(
            agent_id="agent-alice",
            model="User",
            operation="SELECT",
            row_count=1,
            result="success",
        )
        audit_store.record_query(
            agent_id="agent-bob",
            model="User",
            operation="SELECT",
            row_count=2,
            result="success",
        )
        audit_store.record_query(
            agent_id="agent-alice",
            model="Order",
            operation="INSERT",
            row_count=1,
            result="success",
        )

        alice_records = audit_store.get_records_by_agent("agent-alice")
        bob_records = audit_store.get_records_by_agent("agent-bob")

        assert len(alice_records) == 2
        assert len(bob_records) == 1
        assert all(r.agent_id == "agent-alice" for r in alice_records)

    def test_get_records_by_model(self, audit_store):
        """Test filtering records by model name."""
        # Create records for different models
        audit_store.record_query(
            agent_id="agent-001",
            model="User",
            operation="SELECT",
            row_count=1,
            result="success",
        )
        audit_store.record_query(
            agent_id="agent-001",
            model="Order",
            operation="SELECT",
            row_count=2,
            result="success",
        )
        audit_store.record_query(
            agent_id="agent-002",
            model="User",
            operation="UPDATE",
            row_count=1,
            result="success",
        )

        user_records = audit_store.get_records_by_model("User")
        order_records = audit_store.get_records_by_model("Order")

        assert len(user_records) == 2
        assert len(order_records) == 1
        assert all(r.model == "User" for r in user_records)

    def test_disabled_store_no_records(self, ed25519_keypair):
        """Test that disabled store produces no records."""
        disabled_store = DataFlowAuditStore(
            signing_key=ed25519_keypair["private_bytes"],
            verify_key=ed25519_keypair["public_bytes"],
            enabled=False,
        )

        record = disabled_store.record_query(
            agent_id="agent-disabled",
            model="User",
            operation="SELECT",
            row_count=10,
            result="success",
        )

        # When disabled, should return None
        assert record is None

        # No records should be stored
        assert len(disabled_store.get_records()) == 0


# === Group 5: Performance and Edge Cases (5 tests) ===


class TestPerformanceAndEdgeCases:
    """Tests for performance and edge case handling."""

    def test_bulk_record_creation(self, audit_store):
        """Test creating 100 records quickly."""
        start_time = time.time()

        for i in range(100):
            audit_store.record_query(
                agent_id=f"agent-bulk-{i}",
                model="User",
                operation="SELECT",
                row_count=i + 1,
                result="success",
            )

        elapsed = time.time() - start_time

        # 100 records should complete in under 5 seconds
        # (Ed25519 signing is fast, target < 50ms per record)
        assert elapsed < 5.0

        # All 100 records should be stored
        assert len(audit_store.get_records()) == 100

    def test_chain_integrity_after_bulk(self, audit_store):
        """Test chain integrity is valid after 100 records."""
        for i in range(100):
            audit_store.record_query(
                agent_id=f"agent-bulk-chain-{i}",
                model="User",
                operation="SELECT",
                row_count=i + 1,
                result="success",
            )

        is_valid, error = audit_store.verify_chain_integrity()

        assert is_valid is True
        assert error is None

    def test_empty_chain_integrity(self, audit_store):
        """Test that empty store passes chain verification."""
        # Don't create any records
        is_valid, error = audit_store.verify_chain_integrity()

        assert is_valid is True
        assert error is None

    def test_clear_records_resets_state(self, audit_store):
        """Test that clear_records resets counter and chain."""
        # Create some records
        for i in range(5):
            audit_store.record_query(
                agent_id=f"agent-clear-{i}",
                model="User",
                operation="SELECT",
                row_count=1,
                result="success",
            )

        assert len(audit_store.get_records()) == 5

        # Clear records
        audit_store.clear_records()

        assert len(audit_store.get_records()) == 0

        # Next record should start fresh
        new_record = audit_store.record_query(
            agent_id="agent-fresh",
            model="User",
            operation="SELECT",
            row_count=1,
            result="success",
        )

        assert new_record.sequence_number == 0
        assert new_record.previous_record_hash is None

    def test_concurrent_safe_sequence(self, audit_store):
        """Test that sequence numbers remain unique with rapid creation."""
        records = []

        # Create 50 records as fast as possible
        for i in range(50):
            record = audit_store.record_query(
                agent_id="agent-rapid",
                model="User",
                operation="SELECT",
                row_count=1,
                result="success",
            )
            records.append(record)

        # All sequence numbers should be unique
        sequence_numbers = [r.sequence_number for r in records]
        assert len(sequence_numbers) == len(set(sequence_numbers))

        # Should be 0 through 49
        assert sorted(sequence_numbers) == list(range(50))


# === Group 6: CARE-051 Fail-Closed Verification (3 tests) ===


class TestCARE051FailClosedVerification:
    """Tests for CARE-051 fail-closed signature verification.

    CARE-051 Security Finding:
    The _verify_signature() method must return False (fail-closed) when
    no verify_key is configured in strict verification mode. This prevents
    silent bypass of integrity verification in production environments.

    These tests verify that:
    1. strict_verification=True (default) causes verification to fail for unsigned records
    2. strict_verification=True causes verification to fail when no verify_key is configured
    3. strict_verification=False preserves graceful degradation for development/testing
    """

    def test_strict_verification_rejects_unsigned_records(self):
        """CARE-051: strict_verification=True rejects unsigned records."""
        # Create store with strict verification (default) but no signing key
        strict_store = DataFlowAuditStore(
            signing_key=None,
            verify_key=None,
            enabled=True,
            strict_verification=True,  # Default, but explicit for clarity
        )

        # Create an unsigned record
        record = strict_store.record_query(
            agent_id="agent-strict-001",
            model="User",
            operation="SELECT",
            row_count=10,
            result="success",
        )

        # Record should be unsigned
        assert record.signature == "unsigned"

        # Verification should FAIL in strict mode (fail-closed)
        is_valid = strict_store.verify_record(record)
        assert (
            is_valid is False
        ), "CARE-051: Unsigned records must fail verification in strict mode"

    def test_strict_verification_fails_without_verify_key(self, ed25519_keypair):
        """CARE-051: strict_verification=True fails when no verify_key configured."""
        # Create store WITH signing key but WITHOUT verify key
        # This simulates a production misconfiguration
        strict_store = DataFlowAuditStore(
            signing_key=ed25519_keypair["private_bytes"],
            verify_key=None,  # Missing verify key!
            enabled=True,
            strict_verification=True,
        )

        # Create a properly signed record
        record = strict_store.record_query(
            agent_id="agent-strict-002",
            model="User",
            operation="SELECT",
            row_count=5,
            result="success",
        )

        # Record should have a real signature (not "unsigned")
        assert record.signature != "unsigned"

        # Verification should FAIL because no verify_key is configured
        is_valid = strict_store.verify_record(record)
        assert (
            is_valid is False
        ), "CARE-051: Verification must fail when verify_key is missing in strict mode"

    def test_non_strict_allows_graceful_degradation(self):
        """strict_verification=False allows graceful degradation for dev/testing."""
        # Create store with strict_verification=False (development/testing mode)
        dev_store = DataFlowAuditStore(
            signing_key=None,
            verify_key=None,
            enabled=True,
            strict_verification=False,  # Development/testing mode
        )

        # Create an unsigned record
        record = dev_store.record_query(
            agent_id="agent-dev-001",
            model="User",
            operation="SELECT",
            row_count=10,
            result="success",
        )

        # Record should be unsigned
        assert record.signature == "unsigned"

        # Verification should PASS in non-strict mode (graceful degradation)
        is_valid = dev_store.verify_record(record)
        assert is_valid is True, (
            "Unsigned records should pass verification in non-strict mode "
            "for development/testing convenience"
        )


# === Group 7: Empty Hash Handling (ROUND5-002) ===


class TestEmptyHashHandling:
    """Tests for ROUND5-002: compute_query_hash empty params handling.

    ROUND5-002 Security Finding:
    compute_query_hash({}) and compute_query_hash(None) must return
    "0" * 16 (16 zeroes), not an empty string. An empty hash could
    cause issues with hash comparisons and indexing.
    """

    def test_compute_query_hash_empty_params_returns_16_zeroes(self):
        """ROUND5-002: compute_query_hash({}) returns '0' * 16, not ''."""
        result = DataFlowAuditStore.compute_query_hash({})

        assert result == "0" * 16, (
            f"ROUND5-002: compute_query_hash({{}}) should return '{'0' * 16}', "
            f"got '{result}'"
        )
        assert (
            len(result) == 16
        ), f"ROUND5-002: Hash length should be 16, got {len(result)}"

    def test_compute_query_hash_none_params_returns_16_zeroes(self):
        """ROUND5-002: compute_query_hash(None) returns '0' * 16, not ''."""
        # Note: The method signature expects Dict, but should handle None gracefully
        # through the 'if not params' check
        result = DataFlowAuditStore.compute_query_hash(None)

        assert result == "0" * 16, (
            f"ROUND5-002: compute_query_hash(None) should return '{'0' * 16}', "
            f"got '{result}'"
        )
        assert (
            len(result) == 16
        ), f"ROUND5-002: Hash length should be 16, got {len(result)}"

    def test_compute_query_hash_empty_dict_not_empty_string(self):
        """ROUND5-002: Verify empty params does NOT return empty string."""
        result = DataFlowAuditStore.compute_query_hash({})

        assert (
            result != ""
        ), "ROUND5-002: compute_query_hash({}) must NOT return empty string"
        assert result, "ROUND5-002: compute_query_hash({}) must return a truthy value"

    def test_compute_query_hash_with_params_returns_16_chars(self):
        """Verify normal params return 16-character hash (baseline)."""
        result = DataFlowAuditStore.compute_query_hash({"id": 1, "name": "test"})

        assert len(result) == 16, f"Hash length should be 16, got {len(result)}"
        assert result != "0" * 16, "Non-empty params should not return all zeroes"
