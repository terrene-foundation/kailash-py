"""
Unit tests for CARE-010: Append-Only Audit Constraints.

Tests the append-only audit store implementation that enforces
immutability of audit records through:
- Blocked UPDATE/DELETE operations
- Linked hash chains for tamper detection
- Monotonically increasing sequence numbers
- Integrity verification
"""

from datetime import datetime, timezone

import pytest
from kaizen.trust.audit_store import (
    AppendOnlyAuditStore,
    AuditRecord,
    AuditStoreImmutabilityError,
    IntegrityVerificationResult,
)
from kaizen.trust.chain import ActionResult, AuditAnchor
from kaizen.trust.exceptions import TrustError

# =============================================================================
# Fixtures
# =============================================================================


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
def sample_anchor_2():
    """Create a second sample AuditAnchor for testing."""
    return AuditAnchor(
        id="aud-002",
        agent_id="agent-002",
        action="process_data",
        timestamp=datetime.now(timezone.utc),
        trust_chain_hash="def456ghi789",
        result=ActionResult.SUCCESS,
        signature="test-signature-2",
    )


@pytest.fixture
def sample_anchor_3():
    """Create a third sample AuditAnchor for testing."""
    return AuditAnchor(
        id="aud-003",
        agent_id="agent-001",
        action="analyze_data",
        timestamp=datetime.now(timezone.utc),
        trust_chain_hash="ghi789jkl012",
        result=ActionResult.FAILURE,
        signature="test-signature-3",
    )


@pytest.fixture
def store():
    """Create a fresh AppendOnlyAuditStore for testing."""
    return AppendOnlyAuditStore()


# =============================================================================
# AuditStoreImmutabilityError Tests
# =============================================================================


class TestAuditStoreImmutabilityError:
    """Tests for AuditStoreImmutabilityError exception class."""

    def test_immutability_error_message(self):
        """AuditStoreImmutabilityError has proper message."""
        error = AuditStoreImmutabilityError(operation="update")
        assert "immutable" in str(error).lower()
        assert "update" in str(error).lower()

    def test_immutability_error_operation(self):
        """AuditStoreImmutabilityError stores operation."""
        error = AuditStoreImmutabilityError(operation="delete")
        assert error.operation == "delete"

    def test_immutability_error_inherits_trust_error(self):
        """AuditStoreImmutabilityError inherits from TrustError."""
        error = AuditStoreImmutabilityError(operation="update")
        assert isinstance(error, TrustError)

    def test_immutability_error_custom_message(self):
        """AuditStoreImmutabilityError accepts custom message."""
        error = AuditStoreImmutabilityError(
            operation="delete",
            message="Custom error message",
        )
        assert "Custom error message" in str(error)

    def test_immutability_error_record_id(self):
        """AuditStoreImmutabilityError stores record_id."""
        error = AuditStoreImmutabilityError(
            operation="update",
            record_id="rec-123",
        )
        assert error.record_id == "rec-123"


# =============================================================================
# AuditRecord Tests
# =============================================================================


class TestAuditRecord:
    """Tests for AuditRecord dataclass."""

    def test_audit_record_creation(self, sample_anchor):
        """AuditRecord can be created with an anchor."""
        record = AuditRecord(anchor=sample_anchor)
        assert record.anchor == sample_anchor

    def test_audit_record_auto_id(self, sample_anchor):
        """AuditRecord generates a UUID for record_id."""
        record = AuditRecord(anchor=sample_anchor)
        assert record.record_id is not None
        assert len(record.record_id) == 36  # UUID format

    def test_audit_record_auto_timestamp(self, sample_anchor):
        """AuditRecord auto-generates stored_at timestamp."""
        before = datetime.now(timezone.utc)
        record = AuditRecord(anchor=sample_anchor)
        after = datetime.now(timezone.utc)

        assert before <= record.stored_at <= after

    def test_audit_record_integrity_hash(self, sample_anchor):
        """AuditRecord computes integrity_hash on creation."""
        record = AuditRecord(anchor=sample_anchor)
        assert record.integrity_hash is not None
        assert len(record.integrity_hash) == 64  # SHA-256 hex

    def test_audit_record_integrity_hash_deterministic(self, sample_anchor):
        """Same anchor produces same integrity_hash."""
        record1 = AuditRecord(anchor=sample_anchor)
        record2 = AuditRecord(anchor=sample_anchor)

        assert record1.integrity_hash == record2.integrity_hash

    def test_audit_record_verify_integrity_valid(self, sample_anchor):
        """AuditRecord.verify_integrity() returns True for valid record."""
        record = AuditRecord(anchor=sample_anchor)
        assert record.verify_integrity() is True

    def test_audit_record_verify_integrity_tampered(self, sample_anchor):
        """AuditRecord.verify_integrity() detects tampering."""
        record = AuditRecord(anchor=sample_anchor)
        # Tamper with the integrity hash
        record.integrity_hash = "tampered_hash_value_abc123"
        assert record.verify_integrity() is False


# =============================================================================
# Append Tests
# =============================================================================


class TestAppendOperations:
    """Tests for AppendOnlyAuditStore.append() method."""

    @pytest.mark.asyncio
    async def test_append_single_record(self, store, sample_anchor):
        """append() stores a single record."""
        record = await store.append(sample_anchor)
        assert record is not None
        assert record.anchor == sample_anchor

    @pytest.mark.asyncio
    async def test_append_multiple_records(
        self, store, sample_anchor, sample_anchor_2, sample_anchor_3
    ):
        """append() stores multiple records."""
        record1 = await store.append(sample_anchor)
        record2 = await store.append(sample_anchor_2)
        record3 = await store.append(sample_anchor_3)

        assert store.count == 3
        assert record1.record_id != record2.record_id != record3.record_id

    @pytest.mark.asyncio
    async def test_append_assigns_sequence_numbers(
        self, store, sample_anchor, sample_anchor_2, sample_anchor_3
    ):
        """append() assigns monotonically increasing sequence numbers."""
        record1 = await store.append(sample_anchor)
        record2 = await store.append(sample_anchor_2)
        record3 = await store.append(sample_anchor_3)

        assert record1.sequence_number == 1
        assert record2.sequence_number == 2
        assert record3.sequence_number == 3

    @pytest.mark.asyncio
    async def test_append_links_hashes(
        self, store, sample_anchor, sample_anchor_2, sample_anchor_3
    ):
        """append() links records via previous_hash."""
        record1 = await store.append(sample_anchor)
        record2 = await store.append(sample_anchor_2)
        record3 = await store.append(sample_anchor_3)

        assert record2.previous_hash == record1.integrity_hash
        assert record3.previous_hash == record2.integrity_hash

    @pytest.mark.asyncio
    async def test_append_first_record_no_previous_hash(self, store, sample_anchor):
        """First appended record has no previous_hash."""
        record = await store.append(sample_anchor)
        assert record.previous_hash is None

    @pytest.mark.asyncio
    async def test_append_returns_audit_record(self, store, sample_anchor):
        """append() returns an AuditRecord instance."""
        record = await store.append(sample_anchor)
        assert isinstance(record, AuditRecord)


# =============================================================================
# Immutability Enforcement Tests
# =============================================================================


class TestImmutabilityEnforcement:
    """Tests for immutability enforcement (blocked UPDATE/DELETE)."""

    @pytest.mark.asyncio
    async def test_update_raises_immutability_error(self, store, sample_anchor):
        """update() raises AuditStoreImmutabilityError."""
        await store.append(sample_anchor)

        with pytest.raises(AuditStoreImmutabilityError) as exc_info:
            await store.update(sample_anchor)

        assert exc_info.value.operation == "update"

    @pytest.mark.asyncio
    async def test_delete_raises_immutability_error(self, store, sample_anchor):
        """delete() raises AuditStoreImmutabilityError."""
        await store.append(sample_anchor)

        with pytest.raises(AuditStoreImmutabilityError) as exc_info:
            await store.delete(sample_anchor.id)

        assert exc_info.value.operation == "delete"

    @pytest.mark.asyncio
    async def test_update_error_has_operation_field(self, store):
        """update() error has correct operation field."""
        with pytest.raises(AuditStoreImmutabilityError) as exc_info:
            await store.update("some_id", {"field": "value"})

        error = exc_info.value
        assert hasattr(error, "operation")
        assert error.operation == "update"

    @pytest.mark.asyncio
    async def test_delete_error_has_operation_field(self, store):
        """delete() error has correct operation field."""
        with pytest.raises(AuditStoreImmutabilityError) as exc_info:
            await store.delete("some_id")

        error = exc_info.value
        assert hasattr(error, "operation")
        assert error.operation == "delete"


# =============================================================================
# Query Tests
# =============================================================================


class TestQueryOperations:
    """Tests for AppendOnlyAuditStore query methods."""

    @pytest.mark.asyncio
    async def test_get_by_id(self, store, sample_anchor):
        """get() retrieves record by record_id."""
        record = await store.append(sample_anchor)
        retrieved = await store.get(record.record_id)

        assert retrieved is not None
        assert retrieved.record_id == record.record_id
        assert retrieved.anchor.id == sample_anchor.id

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, store):
        """get() returns None for non-existent record_id."""
        result = await store.get("non-existent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_sequence(self, store, sample_anchor, sample_anchor_2):
        """get_by_sequence() retrieves record by sequence number."""
        await store.append(sample_anchor)
        record2 = await store.append(sample_anchor_2)

        retrieved = await store.get_by_sequence(2)
        assert retrieved is not None
        assert retrieved.record_id == record2.record_id

    @pytest.mark.asyncio
    async def test_get_by_sequence_not_found(self, store, sample_anchor):
        """get_by_sequence() returns None for invalid sequence."""
        await store.append(sample_anchor)

        # Sequence 0 is invalid (1-indexed)
        assert await store.get_by_sequence(0) is None
        # Sequence 2 doesn't exist
        assert await store.get_by_sequence(2) is None
        # Negative sequence is invalid
        assert await store.get_by_sequence(-1) is None

    @pytest.mark.asyncio
    async def test_list_records_all(
        self, store, sample_anchor, sample_anchor_2, sample_anchor_3
    ):
        """list_records() returns all records without filters."""
        await store.append(sample_anchor)
        await store.append(sample_anchor_2)
        await store.append(sample_anchor_3)

        records = await store.list_records()
        assert len(records) == 3

    @pytest.mark.asyncio
    async def test_list_records_by_agent(
        self, store, sample_anchor, sample_anchor_2, sample_anchor_3
    ):
        """list_records() filters by agent_id."""
        await store.append(sample_anchor)  # agent-001
        await store.append(sample_anchor_2)  # agent-002
        await store.append(sample_anchor_3)  # agent-001

        records = await store.list_records(agent_id="agent-001")
        assert len(records) == 2
        assert all(r.anchor.agent_id == "agent-001" for r in records)

    @pytest.mark.asyncio
    async def test_list_records_by_action(
        self, store, sample_anchor, sample_anchor_2, sample_anchor_3
    ):
        """list_records() filters by action."""
        await store.append(sample_anchor)  # analyze_data
        await store.append(sample_anchor_2)  # process_data
        await store.append(sample_anchor_3)  # analyze_data

        records = await store.list_records(action="analyze_data")
        assert len(records) == 2
        assert all(r.anchor.action == "analyze_data" for r in records)

    @pytest.mark.asyncio
    async def test_list_records_with_limit(
        self, store, sample_anchor, sample_anchor_2, sample_anchor_3
    ):
        """list_records() respects limit parameter."""
        await store.append(sample_anchor)
        await store.append(sample_anchor_2)
        await store.append(sample_anchor_3)

        records = await store.list_records(limit=2)
        assert len(records) == 2

    @pytest.mark.asyncio
    async def test_list_records_with_offset(
        self, store, sample_anchor, sample_anchor_2, sample_anchor_3
    ):
        """list_records() respects offset parameter."""
        record1 = await store.append(sample_anchor)
        record2 = await store.append(sample_anchor_2)
        await store.append(sample_anchor_3)

        records = await store.list_records(offset=1)
        assert len(records) == 2
        assert records[0].record_id == record2.record_id


# =============================================================================
# Integrity Verification Tests
# =============================================================================


class TestIntegrityVerification:
    """Tests for integrity verification functionality."""

    @pytest.mark.asyncio
    async def test_verify_integrity_empty_store(self, store):
        """verify_integrity() returns valid result for empty store."""
        result = await store.verify_integrity()

        assert isinstance(result, IntegrityVerificationResult)
        assert result.valid is True
        assert result.total_records == 0
        assert result.verified_records == 0

    @pytest.mark.asyncio
    async def test_verify_integrity_valid_chain(
        self, store, sample_anchor, sample_anchor_2, sample_anchor_3
    ):
        """verify_integrity() validates intact chain."""
        await store.append(sample_anchor)
        await store.append(sample_anchor_2)
        await store.append(sample_anchor_3)

        result = await store.verify_integrity()

        assert result.valid is True
        assert result.total_records == 3
        assert result.verified_records == 3
        assert result.first_invalid_sequence is None
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_verify_integrity_detects_tampered_hash(
        self, store, sample_anchor, sample_anchor_2
    ):
        """verify_integrity() detects tampered integrity_hash."""
        await store.append(sample_anchor)
        record2 = await store.append(sample_anchor_2)

        # Tamper with the second record's integrity hash
        record2.integrity_hash = "tampered_hash_value"

        result = await store.verify_integrity()

        assert result.valid is False
        assert result.first_invalid_sequence == 2
        assert len(result.errors) > 0
        assert any("chain" in e.lower() or "hash" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_verify_integrity_detects_sequence_gap(
        self, store, sample_anchor, sample_anchor_2
    ):
        """verify_integrity() detects sequence number gaps."""
        await store.append(sample_anchor)
        record2 = await store.append(sample_anchor_2)

        # Artificially create a gap by modifying sequence number
        record2.sequence_number = 5

        result = await store.verify_integrity()

        assert result.valid is False
        assert len(result.errors) > 0
        assert any("sequence" in e.lower() or "gap" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_verify_single_record(self, store, sample_anchor):
        """verify_record() validates a single record."""
        record = await store.append(sample_anchor)

        is_valid = await store.verify_record(record.record_id)
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_verify_single_record_tampered(self, store, sample_anchor):
        """verify_record() detects tampered single record."""
        record = await store.append(sample_anchor)

        # Tamper with integrity hash
        record.integrity_hash = "tampered_hash"

        is_valid = await store.verify_record(record.record_id)
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_verify_single_record_not_found(self, store):
        """verify_record() returns False for non-existent record."""
        is_valid = await store.verify_record("non-existent-id")
        assert is_valid is False


# =============================================================================
# Properties Tests
# =============================================================================


class TestStoreProperties:
    """Tests for AppendOnlyAuditStore properties."""

    @pytest.mark.asyncio
    async def test_count_property(
        self, store, sample_anchor, sample_anchor_2, sample_anchor_3
    ):
        """count property returns number of records."""
        assert store.count == 0

        await store.append(sample_anchor)
        assert store.count == 1

        await store.append(sample_anchor_2)
        assert store.count == 2

        await store.append(sample_anchor_3)
        assert store.count == 3

    @pytest.mark.asyncio
    async def test_last_sequence_property(self, store, sample_anchor, sample_anchor_2):
        """last_sequence property returns last sequence number."""
        assert store.last_sequence == 0

        await store.append(sample_anchor)
        assert store.last_sequence == 1

        await store.append(sample_anchor_2)
        assert store.last_sequence == 2

    def test_postgres_trigger_sql(self):
        """get_postgres_trigger_sql() returns valid SQL."""
        sql = AppendOnlyAuditStore.get_postgres_trigger_sql()

        assert "CREATE OR REPLACE FUNCTION" in sql
        assert "prevent_audit_modification" in sql
        assert "TRIGGER" in sql
        assert "UPDATE" in sql
        assert "DELETE" in sql
        assert "append-only" in sql.lower()

    def test_postgres_trigger_sql_custom_table(self):
        """get_postgres_trigger_sql() accepts custom table name."""
        sql = AppendOnlyAuditStore.get_postgres_trigger_sql("custom_audit_table")

        assert "custom_audit_table" in sql


# =============================================================================
# IntegrityVerificationResult Tests
# =============================================================================


class TestIntegrityVerificationResult:
    """Tests for IntegrityVerificationResult dataclass."""

    def test_result_creation_valid(self):
        """IntegrityVerificationResult can be created for valid chain."""
        result = IntegrityVerificationResult(
            valid=True,
            total_records=10,
            verified_records=10,
        )

        assert result.valid is True
        assert result.total_records == 10
        assert result.verified_records == 10
        assert result.first_invalid_sequence is None
        assert result.errors == []

    def test_result_creation_invalid(self):
        """IntegrityVerificationResult can be created for invalid chain."""
        result = IntegrityVerificationResult(
            valid=False,
            total_records=10,
            verified_records=5,
            first_invalid_sequence=6,
            errors=["Hash mismatch at sequence 6"],
        )

        assert result.valid is False
        assert result.total_records == 10
        assert result.verified_records == 5
        assert result.first_invalid_sequence == 6
        assert len(result.errors) == 1


# =============================================================================
# Edge Cases and Additional Tests
# =============================================================================


class TestEdgeCases:
    """Additional edge case tests."""

    @pytest.mark.asyncio
    async def test_get_by_anchor_id(self, store, sample_anchor):
        """get_by_anchor_id() retrieves record by anchor ID."""
        record = await store.append(sample_anchor)

        retrieved = await store.get_by_anchor_id(sample_anchor.id)
        assert retrieved is not None
        assert retrieved.record_id == record.record_id

    @pytest.mark.asyncio
    async def test_get_by_anchor_id_not_found(self, store):
        """get_by_anchor_id() returns None for non-existent anchor."""
        result = await store.get_by_anchor_id("non-existent")
        assert result is None

    @pytest.mark.asyncio
    async def test_combined_filters(
        self, store, sample_anchor, sample_anchor_2, sample_anchor_3
    ):
        """list_records() with multiple filters works correctly."""
        await store.append(sample_anchor)  # agent-001, analyze_data
        await store.append(sample_anchor_2)  # agent-002, process_data
        await store.append(sample_anchor_3)  # agent-001, analyze_data

        records = await store.list_records(
            agent_id="agent-001",
            action="analyze_data",
        )
        assert len(records) == 2

    @pytest.mark.asyncio
    async def test_store_isolation(self, sample_anchor):
        """Multiple store instances are isolated."""
        store1 = AppendOnlyAuditStore()
        store2 = AppendOnlyAuditStore()

        await store1.append(sample_anchor)

        assert store1.count == 1
        assert store2.count == 0

    @pytest.mark.asyncio
    async def test_single_record_chain_valid(self, store, sample_anchor):
        """Single record chain passes integrity check."""
        await store.append(sample_anchor)

        result = await store.verify_integrity()
        assert result.valid is True
        assert result.total_records == 1
        assert result.verified_records == 1

    @pytest.mark.asyncio
    async def test_anchor_context_preserved(self, store, sample_anchor):
        """Anchor context is preserved in record."""
        record = await store.append(sample_anchor)

        assert record.anchor.context == {"key": "value"}

    @pytest.mark.asyncio
    async def test_different_anchors_different_hashes(
        self, store, sample_anchor, sample_anchor_2
    ):
        """Different anchors produce different integrity hashes."""
        record1 = await store.append(sample_anchor)
        record2 = await store.append(sample_anchor_2)

        assert record1.integrity_hash != record2.integrity_hash
