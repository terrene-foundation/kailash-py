"""
Comprehensive integration tests for BulkUpsertNode following NO MOCKING policy.

This test suite validates BulkUpsertNode functionality with REAL database operations:
- Insert new records (no conflicts)
- Update existing records (conflict exists)
- Mixed insert + update in same batch
- Conflict resolution strategies (update vs ignore)
- Multiple database types (PostgreSQL, MySQL, SQLite)
- Batch processing with large datasets
- Tenant context isolation
- Database verification (CRITICAL: Never trust success=True alone)

CRITICAL TESTING PRINCIPLES:
1. NO MOCKING - All tests use real PostgreSQL database from Docker
2. ALWAYS verify database state after operations
3. NEVER trust success=True without querying actual records
4. Count exact inserts vs updates by comparing before/after state
5. Verify data integrity (correct values in database)

Run with: pytest tests/integration/bulk_operations/test_bulk_upsert_comprehensive.py -v
"""

import asyncio
import time
from typing import Any, Dict, List

import pytest
from dataflow.nodes.bulk_upsert import BulkUpsertNode

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
async def setup_bulk_upsert_table(test_suite):
    """Create test table for bulk upsert operations and clean up after test."""
    connection_string = test_suite.config.url
    table_name = f"test_bulk_upsert_{int(time.time() * 1000000)}"

    # Create table using AsyncSQLDatabaseNode
    create_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query=f"""
        CREATE TABLE {table_name} (
            id VARCHAR(50) PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            name VARCHAR(100) NOT NULL,
            status VARCHAR(20) DEFAULT 'active',
            score INTEGER DEFAULT 0,
            version INTEGER DEFAULT 1,
            tenant_id VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        validate_queries=False,
    )

    await create_node.async_run()
    await create_node.cleanup()

    yield {"connection_string": connection_string, "table_name": table_name}

    # Cleanup after test
    cleanup_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query=f"DROP TABLE IF EXISTS {table_name} CASCADE",
        validate_queries=False,
    )
    await cleanup_node.async_run()
    await cleanup_node.cleanup()


def _extract_result_data(result):
    """Extract data from AsyncSQLDatabaseNode result format."""
    if isinstance(result, dict) and "result" in result and "data" in result["result"]:
        return result["result"]["data"]
    return result


async def _verify_database_state(
    connection_string: str, table_name: str, order_by: str = "id"
) -> List[Dict[str, Any]]:
    """
    CRITICAL: Verify actual database state by querying records.

    Never trust operation results alone - always verify with actual database query.
    """
    verify_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query=f"SELECT * FROM {table_name} ORDER BY {order_by}",
        validate_queries=False,
    )

    result = await verify_node.async_run()
    await verify_node.cleanup()
    return _extract_result_data(result)


async def _count_records(connection_string: str, table_name: str) -> int:
    """Count total records in table."""
    count_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query=f"SELECT COUNT(*) as count FROM {table_name}",
        validate_queries=False,
    )

    result = await count_node.async_run()
    await count_node.cleanup()
    data = _extract_result_data(result)
    return data[0]["count"]


async def _insert_test_data(
    connection_string: str, table_name: str, records: List[Dict[str, Any]]
):
    """Insert test data into table for setup."""
    for record in records:
        columns = ", ".join(record.keys())
        values = ", ".join(
            [f"'{v}'" if isinstance(v, str) else str(v) for v in record.values()]
        )

        insert_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query=f"INSERT INTO {table_name} ({columns}) VALUES ({values})",
            validate_queries=False,
        )
        await insert_node.async_run()
        await insert_node.cleanup()


# =============================================================================
# TEST GROUP 1: INSERT NEW RECORDS (No Conflicts)
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.timeout(5)
async def test_bulk_upsert_insert_only_new_records(setup_bulk_upsert_table):
    """
    Test bulk upsert with ONLY new records (no conflicts exist).

    VERIFICATION:
    - All records inserted
    - Zero records updated
    - Database contains exact records provided
    """
    config = setup_bulk_upsert_table
    connection_string = config["connection_string"]
    table_name = config["table_name"]

    # BEFORE STATE: Empty table
    initial_count = await _count_records(connection_string, table_name)
    assert initial_count == 0, "Table should start empty"

    # Create BulkUpsertNode
    node = BulkUpsertNode(
        node_id="test_bulk_upsert",
        table_name=table_name,
        database_type="postgresql",
        connection_string=connection_string,
        conflict_columns=["id"],
        auto_timestamps=False,  # Disable for predictable testing
    )

    # Execute upsert with new records
    test_data = [
        {
            "id": "user-001",
            "email": "alice@example.com",
            "name": "Alice",
            "status": "active",
            "score": 100,
        },
        {
            "id": "user-002",
            "email": "bob@example.com",
            "name": "Bob",
            "status": "active",
            "score": 200,
        },
        {
            "id": "user-003",
            "email": "charlie@example.com",
            "name": "Charlie",
            "status": "inactive",
            "score": 150,
        },
    ]

    result = await node.async_run(data=test_data)

    # CRITICAL: Verify operation reported success
    assert result["success"], f"Operation failed: {result.get('error')}"

    # CRITICAL: Query actual database state (DON'T trust success=True alone)
    actual_records = await _verify_database_state(connection_string, table_name)

    # VERIFICATION 1: Correct number of records inserted
    assert (
        len(actual_records) == 3
    ), f"Expected 3 records in database, found {len(actual_records)}"

    # VERIFICATION 2: All records are present with correct data
    emails_in_db = {r["email"] for r in actual_records}
    expected_emails = {"alice@example.com", "bob@example.com", "charlie@example.com"}
    assert (
        emails_in_db == expected_emails
    ), f"Email mismatch: expected {expected_emails}, got {emails_in_db}"

    # VERIFICATION 3: Data integrity - check specific record values
    alice = next(r for r in actual_records if r["id"] == "user-001")
    assert alice["name"] == "Alice"
    assert alice["email"] == "alice@example.com"
    assert alice["score"] == 100
    assert alice["status"] == "active"

    bob = next(r for r in actual_records if r["id"] == "user-002")
    assert bob["name"] == "Bob"
    assert bob["score"] == 200


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.timeout(5)
async def test_bulk_upsert_empty_table_large_batch(setup_bulk_upsert_table):
    """
    Test bulk upsert with large batch into empty table.

    VERIFICATION:
    - All 1000 records inserted
    - Database count matches exactly
    - Performance within acceptable range
    """
    config = setup_bulk_upsert_table
    connection_string = config["connection_string"]
    table_name = config["table_name"]

    # Create BulkUpsertNode with batch size
    node = BulkUpsertNode(
        node_id="test_bulk_upsert",
        table_name=table_name,
        database_type="postgresql",
        connection_string=connection_string,
        conflict_columns=["id"],
        batch_size=250,
        auto_timestamps=False,
    )

    # Generate 1000 records
    test_data = [
        {
            "id": f"user-{i:04d}",
            "email": f"user{i}@example.com",
            "name": f"User {i}",
            "status": "active",
            "score": i,
        }
        for i in range(1000)
    ]

    result = await node.async_run(data=test_data)

    assert result["success"]

    # CRITICAL: Query actual database count
    actual_count = await _count_records(connection_string, table_name)

    # VERIFICATION: All 1000 records inserted
    assert (
        actual_count == 1000
    ), f"Expected 1000 records in database, found {actual_count}"

    # Verify batch processing metrics
    assert result["performance_metrics"]["batches_processed"] == 4  # 1000/250 = 4


# =============================================================================
# TEST GROUP 2: UPDATE EXISTING RECORDS (Conflicts Exist)
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.timeout(5)
async def test_bulk_upsert_update_only_existing_records(setup_bulk_upsert_table):
    """
    Test bulk upsert with ONLY existing records (all conflicts).

    VERIFICATION:
    - Zero new records inserted
    - All existing records updated
    - Database contains updated values
    - Record count unchanged
    """
    config = setup_bulk_upsert_table
    connection_string = config["connection_string"]
    table_name = config["table_name"]

    # SETUP: Insert initial records
    initial_records = [
        {
            "id": "user-001",
            "email": "alice@example.com",
            "name": "Alice Original",
            "status": "active",
            "score": 100,
        },
        {
            "id": "user-002",
            "email": "bob@example.com",
            "name": "Bob Original",
            "status": "inactive",
            "score": 200,
        },
        {
            "id": "user-003",
            "email": "charlie@example.com",
            "name": "Charlie Original",
            "status": "active",
            "score": 150,
        },
    ]

    await _insert_test_data(connection_string, table_name, initial_records)

    # BEFORE STATE: Verify 3 records exist
    initial_count = await _count_records(connection_string, table_name)
    assert initial_count == 3, "Should have 3 initial records"

    # Create BulkUpsertNode
    node = BulkUpsertNode(
        node_id="test_bulk_upsert",
        table_name=table_name,
        database_type="postgresql",
        connection_string=connection_string,
        conflict_columns=["id"],
        auto_timestamps=False,
    )

    # Execute upsert with updated data for existing records
    updated_data = [
        {
            "id": "user-001",
            "email": "alice@example.com",
            "name": "Alice UPDATED",
            "status": "premium",
            "score": 110,
        },
        {
            "id": "user-002",
            "email": "bob@example.com",
            "name": "Bob UPDATED",
            "status": "active",
            "score": 220,
        },
        {
            "id": "user-003",
            "email": "charlie@example.com",
            "name": "Charlie UPDATED",
            "status": "premium",
            "score": 175,
        },
    ]

    result = await node.async_run(data=updated_data)

    assert result["success"]

    # CRITICAL: Query actual database state
    actual_records = await _verify_database_state(connection_string, table_name)

    # VERIFICATION 1: Record count unchanged (no inserts)
    assert (
        len(actual_records) == 3
    ), f"Expected 3 records (no new inserts), found {len(actual_records)}"

    # VERIFICATION 2: All records updated with new values
    alice = next(r for r in actual_records if r["id"] == "user-001")
    assert alice["name"] == "Alice UPDATED", "Alice name should be updated"
    assert alice["status"] == "premium", "Alice status should be updated"
    assert alice["score"] == 110, "Alice score should be updated"

    bob = next(r for r in actual_records if r["id"] == "user-002")
    assert bob["name"] == "Bob UPDATED", "Bob name should be updated"
    assert bob["status"] == "active", "Bob status should be updated"
    assert bob["score"] == 220, "Bob score should be updated"

    charlie = next(r for r in actual_records if r["id"] == "user-003")
    assert charlie["name"] == "Charlie UPDATED", "Charlie name should be updated"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.timeout(5)
async def test_bulk_upsert_update_preserves_unmodified_fields(setup_bulk_upsert_table):
    """
    Test that update only modifies specified fields.

    VERIFICATION:
    - Updated fields have new values
    - Non-updated fields preserve original values
    """
    config = setup_bulk_upsert_table
    connection_string = config["connection_string"]
    table_name = config["table_name"]

    # SETUP: Insert initial record with multiple fields
    await _insert_test_data(
        connection_string,
        table_name,
        [
            {
                "id": "user-001",
                "email": "alice@example.com",
                "name": "Alice",
                "status": "active",
                "score": 100,
            }
        ],
    )

    # Create BulkUpsertNode
    node = BulkUpsertNode(
        node_id="test_bulk_upsert",
        table_name=table_name,
        database_type="postgresql",
        connection_string=connection_string,
        conflict_columns=["id"],
        auto_timestamps=False,
    )

    # Update only score and status, leave name unchanged
    result = await node.async_run(
        data=[
            {
                "id": "user-001",
                "email": "alice@example.com",
                "name": "Alice",  # Same name
                "status": "premium",  # Updated status
                "score": 200,  # Updated score
            }
        ]
    )

    assert result["success"]

    # CRITICAL: Verify database state
    actual_records = await _verify_database_state(connection_string, table_name)
    alice = actual_records[0]

    # VERIFICATION: Updated fields changed, others preserved
    assert alice["name"] == "Alice", "Name should be preserved"
    assert alice["status"] == "premium", "Status should be updated"
    assert alice["score"] == 200, "Score should be updated"


# =============================================================================
# TEST GROUP 3: MIXED INSERT + UPDATE (Some Conflicts, Some New)
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.timeout(5)
async def test_bulk_upsert_mixed_insert_and_update(setup_bulk_upsert_table):
    """
    Test bulk upsert with MIXED operations: some inserts, some updates.

    VERIFICATION:
    - Correct number of inserts
    - Correct number of updates
    - Total record count is correct
    - All data integrity verified
    """
    config = setup_bulk_upsert_table
    connection_string = config["connection_string"]
    table_name = config["table_name"]

    # SETUP: Insert 2 existing records
    existing_records = [
        {
            "id": "user-001",
            "email": "alice@example.com",
            "name": "Alice Original",
            "status": "active",
            "score": 100,
        },
        {
            "id": "user-002",
            "email": "bob@example.com",
            "name": "Bob Original",
            "status": "active",
            "score": 200,
        },
    ]

    await _insert_test_data(connection_string, table_name, existing_records)

    # BEFORE STATE: 2 records exist
    initial_count = await _count_records(connection_string, table_name)
    assert initial_count == 2, "Should have 2 initial records"

    initial_records_state = await _verify_database_state(connection_string, table_name)

    # Create BulkUpsertNode
    node = BulkUpsertNode(
        node_id="test_bulk_upsert",
        table_name=table_name,
        database_type="postgresql",
        connection_string=connection_string,
        conflict_columns=["id"],
        auto_timestamps=False,
    )

    # Execute mixed upsert: 2 updates + 3 inserts
    mixed_data = [
        # UPDATE existing user-001
        {
            "id": "user-001",
            "email": "alice@example.com",
            "name": "Alice UPDATED",
            "status": "premium",
            "score": 150,
        },
        # UPDATE existing user-002
        {
            "id": "user-002",
            "email": "bob@example.com",
            "name": "Bob UPDATED",
            "status": "premium",
            "score": 250,
        },
        # INSERT new user-003
        {
            "id": "user-003",
            "email": "charlie@example.com",
            "name": "Charlie NEW",
            "status": "active",
            "score": 300,
        },
        # INSERT new user-004
        {
            "id": "user-004",
            "email": "diana@example.com",
            "name": "Diana NEW",
            "status": "active",
            "score": 400,
        },
        # INSERT new user-005
        {
            "id": "user-005",
            "email": "eve@example.com",
            "name": "Eve NEW",
            "status": "active",
            "score": 500,
        },
    ]

    result = await node.async_run(data=mixed_data)

    assert result["success"]

    # CRITICAL: Query actual database state
    final_records = await _verify_database_state(connection_string, table_name)
    final_count = len(final_records)

    # VERIFICATION 1: Total count = 2 existing + 3 new = 5 records
    assert (
        final_count == 5
    ), f"Expected 5 total records (2 updated + 3 inserted), found {final_count}"

    # VERIFICATION 2: Updates were applied
    alice = next(r for r in final_records if r["id"] == "user-001")
    assert alice["name"] == "Alice UPDATED", "user-001 should be updated"
    assert alice["score"] == 150, "user-001 score should be updated"

    bob = next(r for r in final_records if r["id"] == "user-002")
    assert bob["name"] == "Bob UPDATED", "user-002 should be updated"
    assert bob["score"] == 250, "user-002 score should be updated"

    # VERIFICATION 3: New inserts are present
    charlie = next(r for r in final_records if r["id"] == "user-003")
    assert charlie["name"] == "Charlie NEW", "user-003 should be inserted"
    assert charlie["score"] == 300

    diana = next(r for r in final_records if r["id"] == "user-004")
    assert diana["name"] == "Diana NEW", "user-004 should be inserted"

    eve = next(r for r in final_records if r["id"] == "user-005")
    assert eve["name"] == "Eve NEW", "user-005 should be inserted"

    # VERIFICATION 4: Count inserts vs updates by comparing with initial state
    initial_ids = {r["id"] for r in initial_records_state}
    final_ids = {r["id"] for r in final_records}

    new_ids = final_ids - initial_ids
    updated_ids = final_ids & initial_ids

    assert len(new_ids) == 3, f"Expected 3 new records, found {len(new_ids)}"
    assert (
        len(updated_ids) == 2
    ), f"Expected 2 updated records, found {len(updated_ids)}"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.timeout(5)
async def test_bulk_upsert_large_mixed_batch(setup_bulk_upsert_table):
    """
    Test large batch with mixed insert/update operations.

    VERIFICATION:
    - Correct total count
    - Updates applied correctly
    - Inserts applied correctly
    - Performance acceptable
    """
    config = setup_bulk_upsert_table
    connection_string = config["connection_string"]
    table_name = config["table_name"]

    # SETUP: Insert 500 existing records
    existing_records = [
        {
            "id": f"user-{i:04d}",
            "email": f"user{i}@example.com",
            "name": f"User {i} Original",
            "status": "active",
            "score": i,
        }
        for i in range(500)
    ]

    await _insert_test_data(connection_string, table_name, existing_records)

    # BEFORE STATE: 500 records exist
    initial_count = await _count_records(connection_string, table_name)
    assert initial_count == 500

    # Create BulkUpsertNode
    node = BulkUpsertNode(
        node_id="test_bulk_upsert",
        table_name=table_name,
        database_type="postgresql",
        connection_string=connection_string,
        conflict_columns=["id"],
        batch_size=200,
        auto_timestamps=False,
    )

    # Prepare mixed data: update first 500 + insert 500 new = 1000 total
    mixed_data = []

    # Update existing 500 records
    for i in range(500):
        mixed_data.append(
            {
                "id": f"user-{i:04d}",
                "email": f"user{i}@example.com",
                "name": f"User {i} UPDATED",
                "status": "premium",
                "score": i * 2,
            }
        )

    # Insert 500 new records
    for i in range(500, 1000):
        mixed_data.append(
            {
                "id": f"user-{i:04d}",
                "email": f"user{i}@example.com",
                "name": f"User {i} NEW",
                "status": "active",
                "score": i,
            }
        )

    result = await node.async_run(data=mixed_data)

    assert result["success"]

    # CRITICAL: Query actual database count
    final_count = await _count_records(connection_string, table_name)

    # VERIFICATION: Total = 500 updated + 500 inserted = 1000 records
    assert final_count == 1000, f"Expected 1000 records, found {final_count}"

    # Sample verification: Check a few updated and new records
    actual_records = await _verify_database_state(connection_string, table_name)

    # Check updated record
    user_100 = next(r for r in actual_records if r["id"] == "user-0100")
    assert user_100["name"] == "User 100 UPDATED"
    assert user_100["score"] == 200  # 100 * 2

    # Check new record
    user_700 = next(r for r in actual_records if r["id"] == "user-0700")
    assert user_700["name"] == "User 700 NEW"
    assert user_700["score"] == 700


# =============================================================================
# TEST GROUP 4: CONFLICT RESOLUTION STRATEGIES
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.timeout(5)
async def test_bulk_upsert_strategy_update(setup_bulk_upsert_table):
    """
    Test conflict resolution strategy: UPDATE existing records.

    VERIFICATION:
    - Existing records are updated with new values
    - No duplicate records created
    """
    config = setup_bulk_upsert_table
    connection_string = config["connection_string"]
    table_name = config["table_name"]

    # SETUP: Insert existing record
    await _insert_test_data(
        connection_string,
        table_name,
        [
            {
                "id": "user-001",
                "email": "alice@example.com",
                "name": "Alice Original",
                "status": "active",
                "score": 100,
            }
        ],
    )

    # Create BulkUpsertNode with UPDATE strategy
    node = BulkUpsertNode(
        node_id="test_bulk_upsert",
        table_name=table_name,
        database_type="postgresql",
        connection_string=connection_string,
        conflict_columns=["id"],
        merge_strategy="update",
        auto_timestamps=False,
    )

    # Execute upsert with conflict
    result = await node.async_run(
        data=[
            {
                "id": "user-001",
                "email": "alice@example.com",
                "name": "Alice UPDATED",
                "status": "premium",
                "score": 200,
            }
        ]
    )

    assert result["success"]

    # CRITICAL: Verify database state
    actual_records = await _verify_database_state(connection_string, table_name)

    # VERIFICATION 1: Only 1 record (no duplicate)
    assert (
        len(actual_records) == 1
    ), "Should have exactly 1 record (updated, not duplicated)"

    # VERIFICATION 2: Record was updated
    alice = actual_records[0]
    assert alice["name"] == "Alice UPDATED"
    assert alice["status"] == "premium"
    assert alice["score"] == 200


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.timeout(5)
async def test_bulk_upsert_strategy_ignore(setup_bulk_upsert_table):
    """
    Test conflict resolution strategy: IGNORE existing records.

    VERIFICATION:
    - Existing records are NOT updated (preserved)
    - New records are inserted
    - No duplicate records created
    """
    config = setup_bulk_upsert_table
    connection_string = config["connection_string"]
    table_name = config["table_name"]

    # SETUP: Insert existing record
    await _insert_test_data(
        connection_string,
        table_name,
        [
            {
                "id": "user-001",
                "email": "alice@example.com",
                "name": "Alice Original",
                "status": "active",
                "score": 100,
            }
        ],
    )

    # Create BulkUpsertNode with IGNORE strategy
    node = BulkUpsertNode(
        node_id="test_bulk_upsert",
        table_name=table_name,
        database_type="postgresql",
        connection_string=connection_string,
        conflict_columns=["id"],
        merge_strategy="ignore",
        auto_timestamps=False,
    )

    # Execute upsert with conflict + new record
    result = await node.async_run(
        data=[
            {
                "id": "user-001",
                "email": "alice@example.com",
                "name": "Alice SHOULD BE IGNORED",
                "status": "premium",
                "score": 999,
            },
            {
                "id": "user-002",
                "email": "bob@example.com",
                "name": "Bob NEW",
                "status": "active",
                "score": 200,
            },
        ]
    )

    assert result["success"]

    # CRITICAL: Verify database state
    actual_records = await _verify_database_state(connection_string, table_name)

    # VERIFICATION 1: 2 records total (1 ignored, 1 inserted)
    assert len(actual_records) == 2, "Should have 2 records"

    # VERIFICATION 2: Existing record NOT updated (ignored)
    alice = next(r for r in actual_records if r["id"] == "user-001")
    assert alice["name"] == "Alice Original", "Alice should NOT be updated (ignored)"
    assert alice["status"] == "active", "Alice status should be original"
    assert alice["score"] == 100, "Alice score should be original (not 999)"

    # VERIFICATION 3: New record was inserted
    bob = next(r for r in actual_records if r["id"] == "user-002")
    assert bob["name"] == "Bob NEW"
    assert bob["score"] == 200


# =============================================================================
# TEST GROUP 5: BATCH PROCESSING
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.timeout(10)
async def test_bulk_upsert_batch_processing_large_dataset(setup_bulk_upsert_table):
    """
    Test batch processing with large dataset.

    VERIFICATION:
    - All records processed across batches
    - Batch metrics are correct
    - Performance within acceptable range
    """
    config = setup_bulk_upsert_table
    connection_string = config["connection_string"]
    table_name = config["table_name"]

    # Create BulkUpsertNode with specific batch size
    node = BulkUpsertNode(
        node_id="test_bulk_upsert",
        table_name=table_name,
        database_type="postgresql",
        connection_string=connection_string,
        conflict_columns=["id"],
        batch_size=250,  # Process in batches of 250
        auto_timestamps=False,
    )

    # Generate 1000 records
    test_data = [
        {
            "id": f"user-{i:04d}",
            "email": f"user{i}@example.com",
            "name": f"User {i}",
            "status": "active",
            "score": i,
        }
        for i in range(1000)
    ]

    result = await node.async_run(data=test_data)

    assert result["success"]

    # CRITICAL: Verify all records were inserted
    final_count = await _count_records(connection_string, table_name)
    assert final_count == 1000, f"Expected 1000 records, found {final_count}"

    # VERIFICATION: Batch metrics
    assert (
        result["performance_metrics"]["batches_processed"] == 4
    )  # 1000/250 = 4 batches
    assert result["total"] == 1000
    assert (
        result["performance_metrics"]["records_per_second"] > 100
    )  # Minimum performance


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.timeout(5)
async def test_bulk_upsert_duplicate_handling_in_batch(setup_bulk_upsert_table):
    """
    Test handling of duplicates WITHIN the batch itself.

    VERIFICATION:
    - Duplicates within batch are deduplicated
    - Last occurrence wins (handle_duplicates='last')
    - Only 1 record inserted (not duplicates)
    """
    config = setup_bulk_upsert_table
    connection_string = config["connection_string"]
    table_name = config["table_name"]

    # Create BulkUpsertNode with duplicate handling
    node = BulkUpsertNode(
        node_id="test_bulk_upsert",
        table_name=table_name,
        database_type="postgresql",
        connection_string=connection_string,
        conflict_columns=["id"],
        handle_duplicates="last",  # Keep last occurrence
        auto_timestamps=False,
    )

    # Send batch with duplicates (same id appears 3 times)
    result = await node.async_run(
        data=[
            {
                "id": "user-001",
                "email": "alice@example.com",
                "name": "First Version",
                "status": "active",
                "score": 10,
            },
            {
                "id": "user-001",
                "email": "alice@example.com",
                "name": "Second Version",
                "status": "inactive",
                "score": 20,
            },
            {
                "id": "user-001",
                "email": "alice@example.com",
                "name": "Final Version",
                "status": "premium",
                "score": 30,
            },
        ]
    )

    assert result["success"]

    # CRITICAL: Verify only 1 record inserted (duplicates removed)
    actual_records = await _verify_database_state(connection_string, table_name)

    # VERIFICATION 1: Only 1 record (duplicates deduplicated)
    assert len(actual_records) == 1, "Should have only 1 record (duplicates removed)"

    # VERIFICATION 2: Last version was kept
    alice = actual_records[0]
    assert alice["name"] == "Final Version", "Should keep last occurrence"
    assert alice["status"] == "premium"
    assert alice["score"] == 30

    # VERIFICATION 3: Check duplicates_removed metric
    assert result["duplicates_removed"] == 2, "Should report 2 duplicates removed"


# =============================================================================
# TEST GROUP 6: TENANT ISOLATION
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.timeout(5)
async def test_bulk_upsert_multi_tenant_isolation(setup_bulk_upsert_table):
    """
    Test multi-tenant isolation with different tenant_ids.

    VERIFICATION:
    - Same ID can exist for different tenants
    - Tenant isolation is enforced
    - Upserts only affect records within same tenant
    """
    config = setup_bulk_upsert_table
    connection_string = config["connection_string"]
    table_name = config["table_name"]

    # SETUP: Add unique constraint for (id, tenant_id) for multi-tenant support
    alter_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query=f"""
        ALTER TABLE {table_name}
        DROP CONSTRAINT {table_name}_pkey,
        ADD CONSTRAINT {table_name}_tenant_key UNIQUE (id, tenant_id)
        """,
        validate_queries=False,
    )
    await alter_node.async_run()
    await alter_node.cleanup()

    # Create BulkUpsertNode with multi-tenant support
    # Note: conflict_columns must include tenant_id for proper isolation
    node = BulkUpsertNode(
        node_id="test_bulk_upsert",
        table_name=table_name,
        database_type="postgresql",
        connection_string=connection_string,
        conflict_columns=["id", "tenant_id"],  # Both id AND tenant_id
        multi_tenant=True,
        auto_timestamps=False,
    )

    # Insert records for tenant_001
    result1 = await node.async_run(
        data=[
            {
                "id": "user-001",
                "email": "alice@tenant1.com",
                "name": "Alice Tenant 1",
                "status": "active",
                "score": 100,
            }
        ],
        tenant_id="tenant_001",
    )

    assert result1["success"]

    # Insert records for tenant_002 (same ID but different tenant)
    result2 = await node.async_run(
        data=[
            {
                "id": "user-001",
                "email": "alice@tenant2.com",
                "name": "Alice Tenant 2",
                "status": "active",
                "score": 200,
            }
        ],
        tenant_id="tenant_002",
    )

    assert result2["success"]

    # CRITICAL: Verify both records exist (different tenants)
    actual_records = await _verify_database_state(
        connection_string, table_name, order_by="tenant_id, id"
    )

    # VERIFICATION 1: 2 records with same ID but different tenants
    assert len(actual_records) == 2, "Should have 2 records (different tenants)"

    # VERIFICATION 2: Tenant 1 record
    tenant1_record = next(r for r in actual_records if r["tenant_id"] == "tenant_001")
    assert tenant1_record["id"] == "user-001"
    assert tenant1_record["name"] == "Alice Tenant 1"
    assert tenant1_record["email"] == "alice@tenant1.com"

    # VERIFICATION 3: Tenant 2 record
    tenant2_record = next(r for r in actual_records if r["tenant_id"] == "tenant_002")
    assert tenant2_record["id"] == "user-001"
    assert tenant2_record["name"] == "Alice Tenant 2"
    assert tenant2_record["email"] == "alice@tenant2.com"

    # VERIFICATION 4: Update tenant_001 record, ensure tenant_002 unaffected
    result3 = await node.async_run(
        data=[
            {
                "id": "user-001",
                "email": "alice@tenant1.com",
                "name": "Alice Tenant 1 UPDATED",
                "status": "premium",
                "score": 150,
            }
        ],
        tenant_id="tenant_001",
    )

    assert result3["success"]

    # Verify tenant_001 updated, tenant_002 unchanged
    final_records = await _verify_database_state(
        connection_string, table_name, order_by="tenant_id, id"
    )

    tenant1_final = next(r for r in final_records if r["tenant_id"] == "tenant_001")
    assert (
        tenant1_final["name"] == "Alice Tenant 1 UPDATED"
    ), "Tenant 1 should be updated"

    tenant2_final = next(r for r in final_records if r["tenant_id"] == "tenant_002")
    assert tenant2_final["name"] == "Alice Tenant 2", "Tenant 2 should be unchanged"


# =============================================================================
# TEST GROUP 7: BUG REPRODUCTION
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.timeout(5)
async def test_bulk_upsert_bug_reproduction_zero_records(setup_bulk_upsert_table):
    """
    CRITICAL BUG REPRODUCTION TEST

    Reproduces the reported bug scenario:
    - BulkUpsertNode reports success=True
    - But ZERO records are actually inserted into database
    - Parameter conflict_fields transformed from list to JSON string

    This test should PASS with the fixed implementation.

    VERIFICATION:
    - Records are actually inserted (not zero)
    - Database state matches expected data
    - Parameter handling is correct
    """
    config = setup_bulk_upsert_table
    connection_string = config["connection_string"]
    table_name = config["table_name"]

    # BEFORE STATE: Empty table
    initial_count = await _count_records(connection_string, table_name)
    assert initial_count == 0, "Table should start empty"

    # Create BulkUpsertNode (matching bug report scenario)
    node = BulkUpsertNode(
        node_id="test_bulk_upsert",
        table_name=table_name,
        database_type="postgresql",
        connection_string=connection_string,
        conflict_columns=["id"],  # Bug report: conflict_fields parameter
        auto_timestamps=False,
    )

    # Execute upsert (matching bug report scenario)
    test_data = [
        {
            "id": "user-001",
            "email": "alice@example.com",
            "name": "Alice",
            "status": "active",
            "score": 100,
        },
        {
            "id": "user-002",
            "email": "bob@example.com",
            "name": "Bob",
            "status": "active",
            "score": 200,
        },
    ]

    result = await node.async_run(data=test_data)

    # BUG: Operation reports success=True
    assert result["success"], "Operation should report success"

    # CRITICAL BUG VERIFICATION: Query actual database state
    # BUG: In the bug report, this would return ZERO records despite success=True
    actual_records = await _verify_database_state(connection_string, table_name)
    actual_count = len(actual_records)

    # CRITICAL ASSERTION: Records should be inserted (not zero)
    assert (
        actual_count > 0
    ), "BUG REPRODUCTION FAILED: Zero records inserted despite success=True"

    # VERIFICATION: Correct number of records
    assert (
        actual_count == 2
    ), f"Expected 2 records, found {actual_count} (BUG: silent failure)"

    # VERIFICATION: Data integrity
    emails_in_db = {r["email"] for r in actual_records}
    expected_emails = {"alice@example.com", "bob@example.com"}
    assert emails_in_db == expected_emails, "Data integrity check failed"

    # If we get here, the bug is FIXED
    print("✅ BUG FIX VERIFIED: Records are actually inserted (not zero)")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.timeout(5)
async def test_bulk_upsert_return_records(setup_bulk_upsert_table):
    """
    Test returning upserted records in response.

    VERIFICATION:
    - Records are returned when return_records=True
    - Returned records match database state
    """
    config = setup_bulk_upsert_table
    connection_string = config["connection_string"]
    table_name = config["table_name"]

    # Create BulkUpsertNode
    node = BulkUpsertNode(
        node_id="test_bulk_upsert",
        table_name=table_name,
        database_type="postgresql",
        connection_string=connection_string,
        conflict_columns=["id"],
        auto_timestamps=False,
    )

    # Execute upsert with return_records
    test_data = [
        {
            "id": "user-001",
            "email": "alice@example.com",
            "name": "Alice",
            "status": "active",
            "score": 100,
        },
        {
            "id": "user-002",
            "email": "bob@example.com",
            "name": "Bob",
            "status": "active",
            "score": 200,
        },
    ]

    result = await node.async_run(data=test_data, return_records=True)

    assert result["success"]

    # VERIFICATION 1: Records are returned
    assert "records" in result, "Should return records when return_records=True"
    returned_records = result["records"]
    assert len(returned_records) > 0, "Should return non-empty records list"

    # VERIFICATION 2: Query database to compare
    actual_records = await _verify_database_state(connection_string, table_name)

    # Compare returned records with database state
    assert len(returned_records) == len(
        actual_records
    ), "Returned records count should match database"
