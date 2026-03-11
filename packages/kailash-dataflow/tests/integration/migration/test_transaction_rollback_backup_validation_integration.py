#!/usr/bin/env python3
"""
Transaction Rollback and Data Backup Validation Tests for TODO-137

Tests the transaction safety and backup mechanisms to ensure ZERO DATA LOSS
under all failure conditions, including system crashes, network failures,
and unexpected errors during column removal operations.

CRITICAL SAFETY REQUIREMENTS TESTED:
1. Complete transaction rollback on any failure
2. Data backup integrity and recoverability
3. Savepoint management during multi-stage operations
4. Database consistency after rollback
5. Backup restoration accuracy (100% data recovery)
6. Concurrent transaction isolation
7. System recovery from partial failures

Following Tier 2 testing guidelines:
- Uses real PostgreSQL Docker infrastructure (NO MOCKING)
- Timeout: <5 seconds per test
- Tests actual database transaction management
- Validates real backup and recovery operations
- CRITICAL PRIORITY: Zero tolerance for data loss

Integration Test Setup:
1. Run: ./tests/utils/test-env up && ./tests/utils/test-env status
2. Verify PostgreSQL running on port 5434
3. Tests use real transaction isolation and recovery mechanisms
"""

import asyncio
import logging
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg
import pytest
from dataflow.migrations.column_removal_manager import (
    BackupStrategy,
    ColumnRemovalManager,
    RemovalPlan,
    RemovalResult,
    RemovalStage,
    RemovalStageResult,
    SafetyValidation,
)

from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


from dataflow.migrations.dependency_analyzer import DependencyAnalyzer, ImpactLevel
from dataflow.migrations.migration_connection_manager import MigrationConnectionManager

# Import test infrastructure
from tests.infrastructure.test_harness import (
    DatabaseConfig,
    DatabaseInfrastructure,
    IntegrationTestSuite,
)

# Configure logging for transaction safety testing
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Integration test fixtures
@pytest.fixture(scope="session")
async def test_database():
    """Set up test database infrastructure."""
    config = DatabaseConfig.from_environment()
    infrastructure = DatabaseInfrastructure(config)
    await infrastructure.initialize()

    yield infrastructure

    # Cleanup
    if infrastructure._pool:
        await infrastructure._pool.close()


@pytest.fixture
async def connection_manager(test_database):
    """Create connection manager for tests."""

    class MockDataFlow:
        def __init__(self, url):
            self.config = type("Config", (), {})()
            self.config.database = type("Database", (), {})()
            self.config.database.url = url

    config = test_database.config
    mock_dataflow = MockDataFlow(config.url)
    manager = MigrationConnectionManager(mock_dataflow)

    yield manager

    # Cleanup
    manager.close_all_connections()


@pytest.fixture
async def transaction_components(connection_manager):
    """Create components for transaction testing."""
    dependency_analyzer = DependencyAnalyzer(connection_manager)
    column_removal_manager = ColumnRemovalManager(connection_manager)

    return dependency_analyzer, column_removal_manager


@pytest.fixture
async def test_connection(test_database):
    """Direct connection for test setup."""
    pool = test_database._pool
    async with pool.acquire() as conn:
        yield conn


@pytest.fixture(autouse=True)
async def clean_transaction_schema(test_connection):
    """Clean transaction test schema before each test."""
    await test_connection.execute(
        """
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            -- Drop backup tables
            FOR r IN (SELECT schemaname, tablename FROM pg_tables
                     WHERE schemaname = 'public' AND tablename LIKE '%backup%')
            LOOP
                EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;

            -- Drop views
            FOR r IN (SELECT schemaname, viewname FROM pg_views
                     WHERE schemaname = 'public' AND viewname LIKE 'txn_%')
            LOOP
                EXECUTE 'DROP VIEW IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.viewname) || ' CASCADE';
            END LOOP;

            -- Drop functions
            FOR r IN (SELECT routine_schema, routine_name FROM information_schema.routines
                     WHERE routine_schema = 'public' AND routine_name LIKE 'txn_%')
            LOOP
                EXECUTE 'DROP FUNCTION IF EXISTS ' || quote_ident(r.routine_schema) || '.' || quote_ident(r.routine_name) || ' CASCADE';
            END LOOP;

            -- Drop tables
            FOR r IN (SELECT schemaname, tablename FROM pg_tables
                     WHERE schemaname = 'public' AND tablename LIKE 'txn_%')
            LOOP
                EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;
    """
    )


def generate_test_id() -> str:
    """Generate unique ID for test resources."""
    return uuid.uuid4().hex[:8]


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestTransactionRollbackBackupValidation:
    """Transaction safety and backup validation tests."""

    @pytest.mark.asyncio
    async def test_complete_transaction_rollback_on_failure(
        self, transaction_components, test_connection
    ):
        """
        CRITICAL SAFETY TEST: Complete Transaction Rollback on Failure

        Tests that ALL changes are completely rolled back when any stage of
        column removal fails, ensuring ZERO DATA LOSS under all conditions.
        """
        dependency_analyzer, column_removal_manager = transaction_components

        test_id = generate_test_id()
        logger.info(
            f"🔄 TRANSACTION ROLLBACK TEST [{test_id}]: Complete rollback on failure"
        )

        # Create test schema with valuable business data
        await test_connection.execute(
            f"""
            CREATE TABLE txn_business_data_{test_id} (
                id SERIAL PRIMARY KEY,
                account_number VARCHAR(50) UNIQUE NOT NULL,
                customer_name VARCHAR(255) NOT NULL,
                account_balance DECIMAL(15,2) NOT NULL,
                target_column VARCHAR(100),  -- This will be removed, but failure should rollback
                critical_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );

            -- Index on target column (will be removed during process)
            CREATE INDEX txn_target_column_idx_{test_id} ON txn_business_data_{test_id}(target_column);

            -- Critical business data that MUST be preserved
            INSERT INTO txn_business_data_{test_id}
                (account_number, customer_name, account_balance, target_column, critical_data)
            VALUES
                ('ACC001', 'Critical Customer 1', 50000.00, 'temp_data_1', 'CRITICAL: Customer payment history'),
                ('ACC002', 'Critical Customer 2', 75000.00, 'temp_data_2', 'CRITICAL: Investment portfolio data'),
                ('ACC003', 'Critical Customer 3', 100000.00, 'temp_data_3', 'CRITICAL: Loan agreement details'),
                ('ACC004', 'Critical Customer 4', 25000.00, 'temp_data_4', 'CRITICAL: Insurance claim data'),
                ('ACC005', 'Critical Customer 5', 60000.00, 'temp_data_5', 'CRITICAL: Transaction audit trail');
        """
        )

        try:
            # Record initial state for comparison
            initial_state = await self._capture_table_state(
                test_connection, f"txn_business_data_{test_id}"
            )
            initial_index_count = await test_connection.fetchval(
                f"""
                SELECT COUNT(*) FROM pg_indexes
                WHERE tablename = 'txn_business_data_{test_id}'
                AND indexname = 'txn_target_column_idx_{test_id}'
            """
            )

            assert len(initial_state) == 5, "Initial data validation"
            assert initial_index_count == 1, "Initial index validation"
            assert (
                sum(row["account_balance"] for row in initial_state) == 310000.00
            ), "Initial balance validation"

            logger.info(
                f"Initial state captured: {len(initial_state)} rows, total balance: $310,000"
            )

            # Create removal plan
            removal_plan = await column_removal_manager.plan_column_removal(
                f"txn_business_data_{test_id}",
                "target_column",
                BackupStrategy.TABLE_SNAPSHOT,
            )

            # Inject failure during column removal stage
            original_execute_stage = column_removal_manager._execute_removal_stage

            failure_injected = False

            async def failing_stage_executor(
                stage, table_name, column_name, connection, plan, stage_details=None
            ):
                nonlocal failure_injected

                # Allow backup to succeed, then fail during column removal
                if stage == RemovalStage.COLUMN_REMOVAL and not failure_injected:
                    failure_injected = True
                    logger.info("💥 INJECTING FAILURE during column removal stage")
                    raise Exception(
                        "SIMULATED SYSTEM FAILURE: Database connection lost during column removal"
                    )

                return await original_execute_stage(
                    stage, table_name, column_name, connection, plan, stage_details
                )

            column_removal_manager._execute_removal_stage = failing_stage_executor

            try:
                # Execute removal with injected failure
                result = await column_removal_manager.execute_safe_removal(removal_plan)

                # Verify failure was handled properly
                assert result.result in [
                    RemovalResult.TRANSACTION_FAILED,
                    RemovalResult.SYSTEM_ERROR,
                ]
                assert (
                    result.rollback_executed is True
                ), "CRITICAL: Rollback must be executed on failure"
                assert "SIMULATED SYSTEM FAILURE" in result.error_message

                logger.info(
                    f"Failure handled: {result.result.value}, rollback executed: {result.rollback_executed}"
                )

            finally:
                # Restore original method
                column_removal_manager._execute_removal_stage = original_execute_stage

            # **CRITICAL VALIDATION**: Verify COMPLETE rollback occurred
            logger.info("Validating complete transaction rollback...")

            # 1. Verify ALL data is exactly as it was before
            final_state = await self._capture_table_state(
                test_connection, f"txn_business_data_{test_id}"
            )

            assert len(final_state) == len(
                initial_state
            ), "CRITICAL: Row count must be unchanged after rollback"

            for initial_row, final_row in zip(initial_state, final_state):
                assert (
                    initial_row == final_row
                ), f"CRITICAL: Data corruption detected - row {initial_row['id']} changed"

            # 2. Verify column still exists (rollback undid removal)
            column_exists = await test_connection.fetchval(
                f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'txn_business_data_{test_id}'
                    AND column_name = 'target_column'
                )
            """
            )
            assert column_exists is True, "CRITICAL: Column must exist after rollback"

            # 3. Verify index still exists (rollback undid index removal)
            final_index_count = await test_connection.fetchval(
                f"""
                SELECT COUNT(*) FROM pg_indexes
                WHERE tablename = 'txn_business_data_{test_id}'
                AND indexname = 'txn_target_column_idx_{test_id}'
            """
            )
            assert (
                final_index_count == initial_index_count
            ), "CRITICAL: Index must be restored after rollback"

            # 4. Verify business data integrity
            final_total_balance = sum(row["account_balance"] for row in final_state)
            initial_total_balance = sum(row["account_balance"] for row in initial_state)

            assert (
                final_total_balance == initial_total_balance
            ), "CRITICAL: Business data must be unchanged"

            # 5. Verify all customer data is intact
            for row in final_state:
                assert row["critical_data"].startswith(
                    "CRITICAL:"
                ), "CRITICAL: Business critical data must be preserved"
                assert (
                    row["account_balance"] > 0
                ), "CRITICAL: Account balances must be preserved"

            logger.info(
                "✅ CRITICAL SAFETY VALIDATED: Complete transaction rollback successful"
            )
            logger.info(f"  - All {len(final_state)} rows preserved exactly")
            logger.info(
                f"  - Total business value preserved: ${final_total_balance:,.2f}"
            )
            logger.info("  - Schema integrity maintained (column + index restored)")

        finally:
            # Cleanup handled by fixture
            pass

    @pytest.mark.asyncio
    async def test_backup_integrity_and_recovery_accuracy(
        self, transaction_components, test_connection
    ):
        """
        CRITICAL SAFETY TEST: Backup Integrity and Recovery Accuracy

        Tests that backups are created correctly and can be used for 100%
        accurate data recovery under all circumstances.
        """
        dependency_analyzer, column_removal_manager = transaction_components

        test_id = generate_test_id()
        logger.info(
            f"💾 BACKUP INTEGRITY TEST [{test_id}]: 100% recovery accuracy validation"
        )

        # Create test data with complex data types
        await test_connection.execute(
            f"""
            CREATE TABLE txn_complex_data_{test_id} (
                id SERIAL PRIMARY KEY,
                json_data JSONB NOT NULL,
                binary_data BYTEA,
                text_data TEXT,
                numeric_data DECIMAL(20,10),
                date_data DATE,
                timestamp_data TIMESTAMP WITH TIME ZONE,
                array_data INTEGER[],
                backup_target_column VARCHAR(500),  -- Target for backup testing
                uuid_data UUID DEFAULT gen_random_uuid()
            );

            -- Insert complex test data
            INSERT INTO txn_complex_data_{test_id}
                (json_data, binary_data, text_data, numeric_data, date_data, timestamp_data, array_data, backup_target_column)
            VALUES
                ('{"customer_id": 1001, "preferences": {"theme": "dark", "notifications": true}}'::jsonb,
                 '\\x48656c6c6f20576f726c64'::bytea,
                 'Multi-line text with special characters: àáâãäåæç €£¥',
                 1234567890.123456789,
                 '2024-01-15',
                 '2024-01-15 14:30:45.123456+00',
                 ARRAY[1, 2, 3, 4, 5],
                 'Complex backup data with unicode: 🚀🔥⭐'),

                ('{"order_id": 2002, "items": [{"sku": "ABC123", "qty": 2}, {"sku": "XYZ789", "qty": 1}]}'::jsonb,
                 '\\x546573742044617461'::bytea,
                 E'Text with newlines\\nand tabs\\t and quotes "quotes" ''single quotes''',
                 9876543210.987654321,
                 '2023-12-25',
                 '2023-12-25 23:59:59.999999+00',
                 ARRAY[10, 20, 30],
                 'More complex data: ñáéíóú àèìòù âêîôû'),

                ('{"metadata": {"version": "1.0", "checksum": "abc123def456"}}'::jsonb,
                 NULL,  -- Test NULL handling
                 NULL,  -- Test NULL handling
                 0.000000001,  -- Test precision
                 NULL,  -- Test NULL dates
                 NOW(),
                 ARRAY[]::INTEGER[], -- Empty array
                 NULL); -- Test NULL target column
        """
        )

        try:
            # **STEP 1**: Create backup using TABLE_SNAPSHOT strategy
            logger.info("Step 1: Creating table snapshot backup")

            table_handler = column_removal_manager.backup_handlers[
                BackupStrategy.TABLE_SNAPSHOT
            ]
            table_backup = await table_handler.create_backup(
                f"txn_complex_data_{test_id}", "backup_target_column", test_connection
            )

            assert table_backup.strategy == BackupStrategy.TABLE_SNAPSHOT
            assert table_backup.backup_size == 3, "Should backup all 3 rows"
            assert table_backup.backup_location is not None

            backup_table_name = table_backup.backup_location

            logger.info(
                f"Table backup created: {backup_table_name} ({table_backup.backup_size} rows)"
            )

            # **STEP 2**: Create backup using COLUMN_ONLY strategy
            logger.info("Step 2: Creating column-only backup")

            column_handler = column_removal_manager.backup_handlers[
                BackupStrategy.COLUMN_ONLY
            ]
            column_backup = await column_handler.create_backup(
                f"txn_complex_data_{test_id}", "backup_target_column", test_connection
            )

            assert column_backup.strategy == BackupStrategy.COLUMN_ONLY
            assert column_backup.backup_size == 3, "Should backup all 3 rows"

            column_backup_table_name = column_backup.backup_location

            logger.info(
                f"Column backup created: {column_backup_table_name} ({column_backup.backup_size} rows)"
            )

            # **STEP 3**: Validate backup data integrity
            logger.info("Step 3: Validating backup data integrity")

            # Get original data for comparison
            original_data = await test_connection.fetch(
                f"""
                SELECT * FROM txn_complex_data_{test_id} ORDER BY id
            """
            )

            # Get table backup data
            table_backup_data = await test_connection.fetch(
                f"""
                SELECT * FROM {backup_table_name} ORDER BY id
            """
            )

            # Get column backup data
            column_backup_data = await test_connection.fetch(
                f"""
                SELECT * FROM {column_backup_table_name} ORDER BY id
            """
            )

            # **CRITICAL VALIDATION**: Backup data must be identical to original
            assert len(table_backup_data) == len(
                original_data
            ), "Table backup must contain all rows"
            assert len(column_backup_data) == len(
                original_data
            ), "Column backup must contain all rows"

            for i, (orig, backup) in enumerate(zip(original_data, table_backup_data)):
                for column_name in orig.keys():
                    orig_val = orig[column_name]
                    backup_val = backup[column_name]

                    # Handle different data types properly
                    if orig_val is None:
                        assert (
                            backup_val is None
                        ), f"NULL value mismatch in row {i}, column {column_name}"
                    elif isinstance(orig_val, (bytes, bytearray)):
                        assert (
                            orig_val == backup_val
                        ), f"Binary data mismatch in row {i}, column {column_name}"
                    elif isinstance(orig_val, dict):  # JSONB
                        assert (
                            orig_val == backup_val
                        ), f"JSON data mismatch in row {i}, column {column_name}"
                    elif isinstance(orig_val, list):  # Arrays
                        assert (
                            orig_val == backup_val
                        ), f"Array data mismatch in row {i}, column {column_name}"
                    else:
                        assert (
                            orig_val == backup_val
                        ), f"Data mismatch in row {i}, column {column_name}: {orig_val} != {backup_val}"

            # **STEP 4**: Test backup recovery under simulated data loss
            logger.info("Step 4: Testing backup recovery accuracy")

            # Simulate data corruption/loss by modifying original table
            await test_connection.execute(
                f"""
                UPDATE txn_complex_data_{test_id}
                SET json_data = '{{"corrupted": true}}'::jsonb,
                    text_data = 'CORRUPTED DATA',
                    numeric_data = -999.999
                WHERE id <= 2
            """
            )

            # Delete one row to simulate data loss
            await test_connection.execute(
                f"""
                DELETE FROM txn_complex_data_{test_id} WHERE id = 3
            """
            )

            # Verify corruption occurred
            corrupted_data = await test_connection.fetch(
                f"""
                SELECT * FROM txn_complex_data_{test_id} ORDER BY id
            """
            )

            assert (
                len(corrupted_data) == 2
            ), "Should have 2 rows after simulated deletion"
            assert (
                corrupted_data[0]["text_data"] == "CORRUPTED DATA"
            ), "Corruption should be applied"

            # **STEP 5**: Perform 100% accurate recovery from backup
            logger.info("Step 5: Performing complete data recovery from backup")

            # Drop corrupted table
            await test_connection.execute(f"DROP TABLE txn_complex_data_{test_id}")

            # Recreate table from backup (simulate recovery)
            await test_connection.execute(
                f"""
                CREATE TABLE txn_complex_data_{test_id} AS
                SELECT * FROM {backup_table_name}
            """
            )

            # Verify recovery accuracy
            recovered_data = await test_connection.fetch(
                f"""
                SELECT * FROM txn_complex_data_{test_id} ORDER BY id
            """
            )

            # **CRITICAL VALIDATION**: Recovery must be 100% accurate
            assert len(recovered_data) == len(
                original_data
            ), "CRITICAL: All rows must be recovered"

            for i, (orig, recovered) in enumerate(zip(original_data, recovered_data)):
                for column_name in orig.keys():
                    if column_name == "uuid_data":
                        # Skip UUID comparison as it's generated
                        continue

                    orig_val = orig[column_name]
                    recovered_val = recovered[column_name]

                    if orig_val is None:
                        assert (
                            recovered_val is None
                        ), f"RECOVERY ERROR: NULL mismatch in row {i}, column {column_name}"
                    elif isinstance(orig_val, (bytes, bytearray)):
                        assert (
                            orig_val == recovered_val
                        ), f"RECOVERY ERROR: Binary mismatch in row {i}, column {column_name}"
                    elif isinstance(orig_val, dict):  # JSONB
                        assert (
                            orig_val == recovered_val
                        ), f"RECOVERY ERROR: JSON mismatch in row {i}, column {column_name}"
                    elif isinstance(orig_val, list):  # Arrays
                        assert (
                            orig_val == recovered_val
                        ), f"RECOVERY ERROR: Array mismatch in row {i}, column {column_name}"
                    else:
                        assert (
                            orig_val == recovered_val
                        ), f"RECOVERY ERROR: Data mismatch in row {i}, column {column_name}"

            # **STEP 6**: Validate backup verification queries
            logger.info("Step 6: Testing backup verification mechanisms")

            # Test table backup verification
            if table_backup.verification_query:
                verification_result = await test_connection.fetchval(
                    table_backup.verification_query
                )
                assert (
                    verification_result == table_backup.backup_size
                ), "Table backup verification failed"

            # Test column backup verification
            if column_backup.verification_query:
                verification_result = await test_connection.fetchval(
                    column_backup.verification_query
                )
                assert (
                    verification_result == column_backup.backup_size
                ), "Column backup verification failed"

            logger.info(
                "✅ BACKUP INTEGRITY VALIDATED: 100% recovery accuracy confirmed"
            )
            logger.info(
                f"  - Table backup: {table_backup.backup_size} rows, 100% accurate"
            )
            logger.info(
                f"  - Column backup: {column_backup.backup_size} rows, 100% accurate"
            )
            logger.info("  - Complex data types preserved: JSON, Binary, Arrays, NULLs")
            logger.info("  - Recovery from corruption: 100% successful")

        finally:
            # Cleanup handled by fixture
            pass

    @pytest.mark.asyncio
    async def test_savepoint_management_multi_stage_operations(
        self, transaction_components, test_connection
    ):
        """
        CRITICAL SAFETY TEST: Savepoint Management During Multi-Stage Operations

        Tests that savepoints are properly managed during complex multi-stage
        operations, allowing granular rollback to specific operation stages.
        """
        dependency_analyzer, column_removal_manager = transaction_components

        test_id = generate_test_id()
        logger.info(
            f"🔖 SAVEPOINT TEST [{test_id}]: Multi-stage operation rollback granularity"
        )

        # Create complex scenario with multiple dependencies
        await test_connection.execute(
            f"""
            CREATE TABLE txn_multi_stage_{test_id} (
                id SERIAL PRIMARY KEY,
                business_id VARCHAR(100) UNIQUE NOT NULL,
                customer_data JSONB NOT NULL,
                target_column VARCHAR(200),  -- Will be removed in multi-stage process
                financial_data DECIMAL(15,2) NOT NULL,
                audit_timestamp TIMESTAMP DEFAULT NOW()
            );

            -- Multiple indexes (multiple removal stages)
            CREATE INDEX txn_multi_target_idx_{test_id} ON txn_multi_stage_{test_id}(target_column);
            CREATE INDEX txn_multi_business_target_idx_{test_id} ON txn_multi_stage_{test_id}(business_id, target_column);

            -- View dependency (another removal stage)
            CREATE VIEW txn_multi_stage_view_{test_id} AS
            SELECT business_id, target_column, financial_data
            FROM txn_multi_stage_{test_id}
            WHERE target_column IS NOT NULL;

            -- Constraint dependency (another removal stage)
            ALTER TABLE txn_multi_stage_{test_id} ADD CONSTRAINT check_target_format_{test_id}
                CHECK (target_column IS NULL OR LENGTH(target_column) >= 5);

            -- Critical business data
            INSERT INTO txn_multi_stage_{test_id}
                (business_id, customer_data, target_column, financial_data)
            VALUES
                ('BIZ001', '{"type": "enterprise", "contracts": 5}'::jsonb, 'legacy_field_001', 500000.00),
                ('BIZ002', '{"type": "small", "contracts": 2}'::jsonb, 'legacy_field_002', 125000.00),
                ('BIZ003', '{"type": "medium", "contracts": 3}'::jsonb, 'legacy_field_003', 275000.00);
        """
        )

        try:
            # Record initial state
            initial_state = await self._capture_table_state(
                test_connection, f"txn_multi_stage_{test_id}"
            )
            initial_view_count = await test_connection.fetchval(
                f"SELECT COUNT(*) FROM txn_multi_stage_view_{test_id}"
            )
            initial_constraint_count = await test_connection.fetchval(
                f"""
                SELECT COUNT(*) FROM information_schema.table_constraints
                WHERE table_name = 'txn_multi_stage_{test_id}'
                AND constraint_name = 'check_target_format_{test_id}'
            """
            )

            assert len(initial_state) == 3, "Initial data validation"
            assert initial_view_count == 3, "Initial view validation"
            assert initial_constraint_count == 1, "Initial constraint validation"

            logger.info(
                f"Initial state: {len(initial_state)} rows, view accessible, constraint active"
            )

            # Create multi-stage removal plan
            removal_plan = await column_removal_manager.plan_column_removal(
                f"txn_multi_stage_{test_id}",
                "target_column",
                BackupStrategy.TABLE_SNAPSHOT,
            )

            # Verify plan includes multiple stages
            expected_stages = {
                RemovalStage.BACKUP_CREATION,
                RemovalStage.CONSTRAINT_REMOVAL,
                RemovalStage.INDEX_REMOVAL,
                RemovalStage.DEPENDENT_OBJECTS,
                RemovalStage.COLUMN_REMOVAL,
                RemovalStage.VALIDATION,
            }

            actual_stages = set(removal_plan.execution_stages)
            assert (
                len(actual_stages.intersection(expected_stages)) >= 4
            ), "Should have multi-stage plan"

            # Inject failure at specific stage (after some stages complete)
            original_execute_stage = column_removal_manager._execute_removal_stage
            stages_completed = []

            async def stage_tracking_executor(
                stage, table_name, column_name, connection, plan, stage_details=None
            ):
                stages_completed.append(stage)

                # Allow backup and constraint removal to succeed
                if stage in [
                    RemovalStage.BACKUP_CREATION,
                    RemovalStage.CONSTRAINT_REMOVAL,
                ]:
                    result = await original_execute_stage(
                        stage, table_name, column_name, connection, plan, stage_details
                    )
                    logger.info(f"✅ Stage completed successfully: {stage.name}")
                    return result

                # Fail at index removal stage
                elif stage == RemovalStage.INDEX_REMOVAL:
                    logger.info(f"💥 INJECTING FAILURE at stage: {stage.name}")
                    raise Exception(
                        f"SIMULATED FAILURE during {stage.name}: Index removal failed"
                    )

                # Should not reach subsequent stages due to failure
                else:
                    logger.info(
                        f"❌ Unexpected stage execution after failure: {stage.name}"
                    )
                    raise Exception(
                        f"Stage {stage.name} should not execute after failure"
                    )

            column_removal_manager._execute_removal_stage = stage_tracking_executor

            try:
                # Execute with injected failure
                result = await column_removal_manager.execute_safe_removal(removal_plan)

                # Verify failure handling
                assert result.result == RemovalResult.TRANSACTION_FAILED
                assert result.rollback_executed is True
                assert "Index removal failed" in result.error_message

                logger.info(
                    f"Multi-stage failure handled: {len(stages_completed)} stages attempted before failure"
                )

            finally:
                column_removal_manager._execute_removal_stage = original_execute_stage

            # **CRITICAL VALIDATION**: Verify granular rollback worked correctly
            logger.info("Validating granular savepoint rollback...")

            # 1. Verify stages that completed were properly rolled back
            assert (
                RemovalStage.BACKUP_CREATION in stages_completed
            ), "Backup stage should have been attempted"
            assert (
                RemovalStage.CONSTRAINT_REMOVAL in stages_completed
            ), "Constraint removal should have been attempted"
            assert (
                RemovalStage.INDEX_REMOVAL in stages_completed
            ), "Index removal should have been attempted (and failed)"

            # 2. Verify complete rollback - constraint should still exist
            final_constraint_count = await test_connection.fetchval(
                f"""
                SELECT COUNT(*) FROM information_schema.table_constraints
                WHERE table_name = 'txn_multi_stage_{test_id}'
                AND constraint_name = 'check_target_format_{test_id}'
            """
            )
            assert (
                final_constraint_count == 1
            ), "CRITICAL: Constraint must be restored after rollback"

            # 3. Verify all indexes still exist
            final_index_count = await test_connection.fetchval(
                f"""
                SELECT COUNT(*) FROM pg_indexes
                WHERE tablename = 'txn_multi_stage_{test_id}'
                AND indexname LIKE '%target%'
            """
            )
            assert (
                final_index_count == 2
            ), "CRITICAL: All indexes must be restored after rollback"

            # 4. Verify view still works
            final_view_count = await test_connection.fetchval(
                f"SELECT COUNT(*) FROM txn_multi_stage_view_{test_id}"
            )
            assert (
                final_view_count == initial_view_count
            ), "CRITICAL: View must still work after rollback"

            # 5. Verify column still exists
            column_exists = await test_connection.fetchval(
                f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'txn_multi_stage_{test_id}'
                    AND column_name = 'target_column'
                )
            """
            )
            assert (
                column_exists is True
            ), "CRITICAL: Target column must exist after rollback"

            # 6. Verify ALL data is unchanged
            final_state = await self._capture_table_state(
                test_connection, f"txn_multi_stage_{test_id}"
            )

            assert len(final_state) == len(
                initial_state
            ), "CRITICAL: Row count must be unchanged"
            for initial_row, final_row in zip(initial_state, final_state):
                assert (
                    initial_row == final_row
                ), f"CRITICAL: Data corruption in row {initial_row['id']}"

            # 7. Verify business data integrity
            total_financial_value = sum(row["financial_data"] for row in final_state)
            assert (
                total_financial_value == 900000.00
            ), "CRITICAL: Business financial data must be preserved"

            logger.info(
                "✅ SAVEPOINT MANAGEMENT VALIDATED: Granular rollback successful"
            )
            logger.info(f"  - Stages attempted before failure: {len(stages_completed)}")
            logger.info("  - Complete rollback achieved: All data/schema restored")
            logger.info(f"  - Business data preserved: ${total_financial_value:,.2f}")

        finally:
            # Cleanup handled by fixture
            pass

    @pytest.mark.asyncio
    async def test_concurrent_transaction_isolation_safety(
        self, test_database, connection_manager
    ):
        """
        CRITICAL SAFETY TEST: Concurrent Transaction Isolation Safety

        Tests that concurrent column removal operations are properly isolated
        and don't interfere with each other's transaction safety.
        """
        test_id = generate_test_id()
        logger.info(
            f"🔄 CONCURRENT ISOLATION TEST [{test_id}]: Transaction isolation safety"
        )

        # Create two separate removal managers (simulating concurrent users)
        removal_manager_1 = ColumnRemovalManager(connection_manager)
        removal_manager_2 = ColumnRemovalManager(connection_manager)

        # Set up test schema
        async with test_database._pool.acquire() as conn:
            await conn.execute(
                f"""
                CREATE TABLE txn_concurrent_{test_id} (
                    id SERIAL PRIMARY KEY,
                    shared_data VARCHAR(255) NOT NULL,
                    column_a VARCHAR(100),  -- Target for manager 1
                    column_b VARCHAR(100),  -- Target for manager 2
                    business_value DECIMAL(12,2) NOT NULL
                );

                CREATE INDEX txn_concurrent_col_a_idx_{test_id} ON txn_concurrent_{test_id}(column_a);
                CREATE INDEX txn_concurrent_col_b_idx_{test_id} ON txn_concurrent_{test_id}(column_b);

                INSERT INTO txn_concurrent_{test_id} (shared_data, column_a, column_b, business_value) VALUES
                ('Shared Business Data 1', 'data_a_1', 'data_b_1', 10000.00),
                ('Shared Business Data 2', 'data_a_2', 'data_b_2', 20000.00),
                ('Shared Business Data 3', 'data_a_3', 'data_b_3', 30000.00);
            """
            )

        try:
            # Record initial state
            async with test_database._pool.acquire() as conn:
                initial_state = await self._capture_table_state(
                    conn, f"txn_concurrent_{test_id}"
                )

            logger.info(
                f"Concurrent test setup: {len(initial_state)} rows, total value: ${sum(r['business_value'] for r in initial_state):,.2f}"
            )

            # Create removal plans for both managers
            plan_1 = await removal_manager_1.plan_column_removal(
                f"txn_concurrent_{test_id}", "column_a", BackupStrategy.COLUMN_ONLY
            )
            plan_2 = await removal_manager_2.plan_column_removal(
                f"txn_concurrent_{test_id}", "column_b", BackupStrategy.COLUMN_ONLY
            )

            # Inject controlled delays to create overlap
            original_execute_1 = removal_manager_1._execute_removal_stage
            original_execute_2 = removal_manager_2._execute_removal_stage

            async def delayed_execute_1(
                stage, table_name, column_name, connection, plan, stage_details=None
            ):
                if stage == RemovalStage.COLUMN_REMOVAL:
                    await asyncio.sleep(0.5)  # Create overlap window
                return await original_execute_1(
                    stage, table_name, column_name, connection, plan, stage_details
                )

            async def delayed_execute_2(
                stage, table_name, column_name, connection, plan, stage_details=None
            ):
                if stage == RemovalStage.COLUMN_REMOVAL:
                    await asyncio.sleep(0.2)  # Different timing
                return await original_execute_2(
                    stage, table_name, column_name, connection, plan, stage_details
                )

            removal_manager_1._execute_removal_stage = delayed_execute_1
            removal_manager_2._execute_removal_stage = delayed_execute_2

            try:
                # Execute concurrent operations
                async def execute_removal_1():
                    try:
                        return await removal_manager_1.execute_safe_removal(plan_1)
                    except Exception as e:
                        return {"error": str(e), "manager": 1}

                async def execute_removal_2():
                    await asyncio.sleep(0.1)  # Slight offset
                    try:
                        return await removal_manager_2.execute_safe_removal(plan_2)
                    except Exception as e:
                        return {"error": str(e), "manager": 2}

                # Run concurrent executions
                results = await asyncio.gather(
                    execute_removal_1(), execute_removal_2(), return_exceptions=True
                )

            finally:
                # Restore original methods
                removal_manager_1._execute_removal_stage = original_execute_1
                removal_manager_2._execute_removal_stage = original_execute_2

            # **CRITICAL VALIDATION**: Verify transaction isolation worked properly
            logger.info("Validating concurrent transaction isolation...")

            success_count = 0
            error_count = 0

            for i, result in enumerate(results):
                if isinstance(result, dict) and "error" in result:
                    error_count += 1
                    logger.info(
                        f"Manager {result.get('manager', i+1)} failed: {result['error'][:100]}"
                    )
                elif (
                    hasattr(result, "result") and result.result == RemovalResult.SUCCESS
                ):
                    success_count += 1
                    logger.info(f"Manager {i+1} succeeded")
                else:
                    logger.info(f"Manager {i+1} had unexpected result: {result}")

            # Verify database consistency after concurrent operations
            async with test_database._pool.acquire() as conn:
                final_state = await self._capture_table_state(
                    conn, f"txn_concurrent_{test_id}"
                )

                # **CRITICAL**: Data must be consistent regardless of success/failure pattern
                assert len(final_state) == len(
                    initial_state
                ), "CRITICAL: Row count must remain consistent"

                # Verify business data integrity
                final_total_value = sum(row["business_value"] for row in final_state)
                initial_total_value = sum(
                    row["business_value"] for row in initial_state
                )

                assert (
                    final_total_value == initial_total_value
                ), "CRITICAL: Business value must be preserved"

                # Verify shared data is unchanged
                for initial_row, final_row in zip(initial_state, final_state):
                    assert (
                        initial_row["shared_data"] == final_row["shared_data"]
                    ), "CRITICAL: Shared data must be unchanged"
                    assert (
                        initial_row["business_value"] == final_row["business_value"]
                    ), "CRITICAL: Business values must be unchanged"

            logger.info(
                "✅ CONCURRENT ISOLATION VALIDATED: Transaction safety maintained"
            )
            logger.info("  - Concurrent operations: 2 managers")
            logger.info(f"  - Successful operations: {success_count}")
            logger.info(f"  - Failed operations: {error_count}")
            logger.info("  - Data consistency: Maintained across all scenarios")
            logger.info(f"  - Business value preserved: ${final_total_value:,.2f}")

        finally:
            # Cleanup
            pass

    async def _capture_table_state(self, connection, table_name: str) -> List[Dict]:
        """Helper method to capture complete table state for comparison."""
        rows = await connection.fetch(f"SELECT * FROM {table_name} ORDER BY id")
        return [dict(row) for row in rows]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
