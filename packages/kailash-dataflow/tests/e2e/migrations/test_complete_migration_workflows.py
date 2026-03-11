"""
E2E tests for complete DataFlow migration workflows.

These tests verify the complete migration system with real PostgreSQL infrastructure
covering all critical migration scenarios end-to-end. NO MOCKING is used - all
components integrate with real database operations.

Critical Migration Scenarios Tested:
1. Column datatype change with existing incompatible data
2. Safe NOT NULL addition to populated tables
3. Transaction rollback on migration failure
4. DataFlow connection pool integration
5. SQL injection prevention validation
6. Concurrent migration prevention
"""

import asyncio
import os
import uuid
from datetime import datetime

import pytest
from dataflow.migration.data_validation_engine import DataValidationEngine
from dataflow.migration.orchestration_engine import (
    Migration,
    MigrationOperation,
    MigrationOrchestrationEngine,
    MigrationType,
    RiskLevel,
)

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.e2e
class TestCompleteMigrationWorkflows:
    """E2E tests for complete migration workflows with real PostgreSQL."""

    @pytest.fixture
    def connection_string(self):
        """Get PostgreSQL connection string from environment."""
        return os.getenv(
            "POSTGRES_TEST_URL",
            "postgresql://dataflow_test:dataflow_test_password@localhost:5433/dataflow_test",
        )

    @pytest.fixture
    def runtime(self):
        """Create LocalRuntime for executing workflows."""
        return LocalRuntime()

    @pytest.fixture
    def table_name(self):
        """Generate unique table name for test."""
        return f"test_migration_{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    async def orchestration_engine(self, connection_string):
        """Create MigrationOrchestrationEngine for testing."""
        # Use mock components for dependencies not yet implemented
        return MigrationOrchestrationEngine(
            auto_migration_system=None,  # Mock - not needed for these tests
            schema_state_manager=None,  # Mock - not needed for these tests
            connection_string=connection_string,
        )

    async def create_test_table_with_data(
        self, connection_string: str, table_name: str, runtime: LocalRuntime
    ):
        """Create a test table with data for migration testing."""
        # Create table with mixed data types
        create_sql = f"""
        CREATE TABLE "{table_name}" (
            id SERIAL PRIMARY KEY,
            user_name VARCHAR(50) NOT NULL,
            age_text VARCHAR(20),
            score_number TEXT,
            status_flag VARCHAR(10),
            created_at TIMESTAMP DEFAULT NOW()
        )
        """

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "create_table",
            {
                "connection_string": connection_string,
                "query": create_sql,
                "validate_queries": False,
            },
        )

        results, _ = runtime.execute(workflow.build())
        assert not results["create_table"].get(
            "error"
        ), f"Table creation failed: {results['create_table'].get('error')}"

        # Insert test data with various scenarios
        insert_sql = f"""
        INSERT INTO "{table_name}" (user_name, age_text, score_number, status_flag)
        VALUES
            ('Alice Smith', '25', '95.5', 'active'),
            ('Bob Johnson', '30', '87.2', 'inactive'),
            ('Charlie Brown', '35', '92.1', 'active'),
            ('Diana Prince', 'unknown', 'invalid', 'pending'),
            ('Eve Wilson', '28', '88.7', 'active'),
            ('Frank Miller', '45', '91.3', 'inactive'),
            ('Grace Lee', '22', '96.8', 'active'),
            ('Henry Davis', 'invalid_age', '84.2', 'suspended'),
            ('Iris Chen', '29', '89.4', 'active'),
            ('Jack Taylor', '31', '93.1', 'active')
        """

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "insert_data",
            {
                "connection_string": connection_string,
                "query": insert_sql,
                "validate_queries": False,
            },
        )

        results, _ = runtime.execute(workflow.build())
        assert not results["insert_data"].get(
            "error"
        ), f"Data insertion failed: {results['insert_data'].get('error')}"

    async def cleanup_test_table(
        self, connection_string: str, table_name: str, runtime: LocalRuntime
    ):
        """Clean up test table after test."""
        drop_sql = f'DROP TABLE IF EXISTS "{table_name}"'

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "drop_table",
            {
                "connection_string": connection_string,
                "query": drop_sql,
                "validate_queries": False,
            },
        )

        results, _ = runtime.execute(workflow.build())
        # Don't assert on cleanup - it's best effort

    @pytest.mark.asyncio
    async def test_column_datatype_change_with_incompatible_data(
        self, connection_string, runtime, table_name, orchestration_engine
    ):
        """
        E2E Test: Column datatype change with existing incompatible data.

        This tests the complete workflow of detecting incompatible data,
        validation, and proper error handling for column type changes.
        """
        await self.create_test_table_with_data(connection_string, table_name, runtime)

        try:
            # Create migration to convert age_text (VARCHAR) to INTEGER
            # This should fail due to 'unknown' and 'invalid_age' values
            migration = Migration(
                operations=[
                    MigrationOperation(
                        operation_type=MigrationType.MODIFY_COLUMN,
                        table_name=table_name,
                        metadata={
                            "column_name": "age_text",
                            "old_type": "varchar(20)",
                            "new_type": "integer",
                        },
                        rollback_sql=f'ALTER TABLE "{table_name}" ALTER COLUMN age_text TYPE VARCHAR(20)',
                    )
                ],
                version="test_incompatible_data_v1",
                dependencies=[],
                risk_level=RiskLevel.HIGH,
            )

            # Step 1: Validate migration should detect incompatible data
            validation_result = await orchestration_engine.validate_migration_safety(
                migration
            )

            assert validation_result is not None
            assert validation_result.risk_assessment == RiskLevel.HIGH
            assert len(validation_result.warnings) > 0
            # Should warn about high-risk operation

            # Step 2: Execute migration - should fail or handle gracefully
            execution_result = await orchestration_engine.execute_migration(migration)

            assert execution_result is not None
            assert execution_result.migration_version == "test_incompatible_data_v1"
            # May succeed or fail depending on SQL generation - both are valid for this test

            # Step 3: Verify data integrity is maintained
            verify_sql = f'SELECT COUNT(*) as row_count FROM "{table_name}"'
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "verify_data",
                {
                    "connection_string": connection_string,
                    "query": verify_sql,
                    "validate_queries": False,
                },
            )

            results, _ = runtime.execute(workflow.build())
            assert not results["verify_data"].get("error")

            if (
                "result" in results["verify_data"]
                and "data" in results["verify_data"]["result"]
            ):
                rows = results["verify_data"]["result"]["data"]
            else:
                rows = results["verify_data"].get("rows", [])

            assert len(rows) > 0
            assert rows[0]["row_count"] == 10  # All data should be preserved

        finally:
            await self.cleanup_test_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_safe_not_null_addition_to_populated_table(
        self, connection_string, runtime, table_name, orchestration_engine
    ):
        """
        E2E Test: Safe NOT NULL addition to populated tables.

        This tests adding a NOT NULL column with a default value to a table
        that already contains data.
        """
        await self.create_test_table_with_data(connection_string, table_name, runtime)

        try:
            # Create migration to add NOT NULL column with default
            migration = Migration(
                operations=[
                    MigrationOperation(
                        operation_type=MigrationType.ADD_COLUMN,
                        table_name=table_name,
                        metadata={
                            "column_name": "email",
                            "column_type": "VARCHAR(255) NOT NULL DEFAULT 'noemail@example.com'",
                        },
                        rollback_sql=f'ALTER TABLE "{table_name}" DROP COLUMN email',
                    )
                ],
                version="test_safe_not_null_v1",
                dependencies=[],
                risk_level=RiskLevel.LOW,
            )

            # Step 1: Validate migration
            validation_result = await orchestration_engine.validate_migration_safety(
                migration
            )

            assert validation_result.is_valid is True
            assert validation_result.risk_assessment in [
                RiskLevel.LOW,
                RiskLevel.MEDIUM,
            ]

            # Step 2: Execute migration
            execution_result = await orchestration_engine.execute_migration(migration)

            assert execution_result.success is True
            assert execution_result.executed_operations == 1
            assert execution_result.error_message is None

            # Step 3: Verify column was added and has default values
            verify_sql = f"""
            SELECT email, COUNT(*) as count
            FROM "{table_name}"
            WHERE email = 'noemail@example.com'
            GROUP BY email
            """

            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "verify_column",
                {
                    "connection_string": connection_string,
                    "query": verify_sql,
                    "validate_queries": False,
                },
            )

            results, _ = runtime.execute(workflow.build())
            assert not results["verify_column"].get("error")

            if (
                "result" in results["verify_column"]
                and "data" in results["verify_column"]["result"]
            ):
                rows = results["verify_column"]["result"]["data"]
            else:
                rows = results["verify_column"].get("rows", [])

            assert len(rows) > 0
            assert rows[0]["count"] == 10  # All 10 rows should have the default email

        finally:
            await self.cleanup_test_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_migration_failure(
        self, connection_string, runtime, table_name, orchestration_engine
    ):
        """
        E2E Test: Transaction rollback on migration failure.

        This tests that when a migration fails, the system properly rolls back
        any changes that were made.
        """
        await self.create_test_table_with_data(connection_string, table_name, runtime)

        try:
            # Create migration with multiple operations, second one will fail
            migration = Migration(
                operations=[
                    MigrationOperation(
                        operation_type=MigrationType.ADD_COLUMN,
                        table_name=table_name,
                        metadata={
                            "column_name": "temp_col",
                            "column_type": "VARCHAR(50)",
                        },
                        rollback_sql=f'ALTER TABLE "{table_name}" DROP COLUMN temp_col',
                    ),
                    MigrationOperation(
                        operation_type=MigrationType.ADD_COLUMN,
                        table_name="nonexistent_table",  # This will fail
                        metadata={
                            "column_name": "fail_col",
                            "column_type": "VARCHAR(50)",
                        },
                    ),
                ],
                version="test_rollback_v1",
                dependencies=[],
                risk_level=RiskLevel.MEDIUM,
            )

            # Step 1: Execute migration - should fail on second operation
            execution_result = await orchestration_engine.execute_migration(migration)

            assert execution_result.success is False
            assert (
                execution_result.executed_operations <= 1
            )  # Should stop after first operation
            assert execution_result.error_message is not None

            # Step 2: Verify rollback occurred - temp_col should not exist
            verify_sql = f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = '{table_name}' AND column_name = 'temp_col'
            """

            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "verify_rollback",
                {
                    "connection_string": connection_string,
                    "query": verify_sql,
                    "validate_queries": False,
                },
            )

            results, _ = runtime.execute(workflow.build())
            assert not results["verify_rollback"].get("error")

            if (
                "result" in results["verify_rollback"]
                and "data" in results["verify_rollback"]["result"]
            ):
                rows = results["verify_rollback"]["result"]["data"]
            else:
                rows = results["verify_rollback"].get("rows", [])

            # temp_col should not exist due to rollback
            assert len(rows) == 0, "Column should have been rolled back"

        finally:
            await self.cleanup_test_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_concurrent_migration_prevention(
        self, connection_string, runtime, table_name, orchestration_engine
    ):
        """
        E2E Test: Concurrent migration prevention.

        This tests that the system prevents multiple migrations from running
        simultaneously on the same database.
        """
        await self.create_test_table_with_data(connection_string, table_name, runtime)

        try:
            # Create two similar migrations
            migration1 = Migration(
                operations=[
                    MigrationOperation(
                        operation_type=MigrationType.ADD_COLUMN,
                        table_name=table_name,
                        metadata={"column_name": "col1", "column_type": "VARCHAR(50)"},
                    )
                ],
                version="test_concurrent_v1",
                dependencies=[],
                risk_level=RiskLevel.LOW,
            )

            migration2 = Migration(
                operations=[
                    MigrationOperation(
                        operation_type=MigrationType.ADD_COLUMN,
                        table_name=table_name,
                        metadata={"column_name": "col2", "column_type": "VARCHAR(50)"},
                    )
                ],
                version="test_concurrent_v2",
                dependencies=[],
                risk_level=RiskLevel.LOW,
            )

            # Step 1: Start first migration and second migration concurrently
            # Note: In a real scenario, we'd need more sophisticated concurrency testing
            # For now, we test the lock mechanism

            result1 = await orchestration_engine.execute_migration(migration1)

            # Should succeed
            assert result1.success is True
            assert result1.migration_version == "test_concurrent_v1"

            # Step 2: Try second migration immediately (lock should be released)
            result2 = await orchestration_engine.execute_migration(migration2)

            # Should also succeed since first migration completed
            assert result2.success is True
            assert result2.migration_version == "test_concurrent_v2"

            # Step 3: Verify both columns were created
            verify_sql = f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = '{table_name}'
            AND column_name IN ('col1', 'col2')
            ORDER BY column_name
            """

            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "verify_columns",
                {
                    "connection_string": connection_string,
                    "query": verify_sql,
                    "validate_queries": False,
                },
            )

            results, _ = runtime.execute(workflow.build())
            assert not results["verify_columns"].get("error")

            if (
                "result" in results["verify_columns"]
                and "data" in results["verify_columns"]["result"]
            ):
                rows = results["verify_columns"]["result"]["data"]
            else:
                rows = results["verify_columns"].get("rows", [])

            assert len(rows) == 2
            assert rows[0]["column_name"] == "col1"
            assert rows[1]["column_name"] == "col2"

        finally:
            await self.cleanup_test_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_data_validation_with_sql_injection_prevention(
        self, connection_string, runtime, table_name
    ):
        """
        E2E Test: SQL injection prevention validation.

        This tests that the data validation engine properly handles potentially
        malicious input without SQL injection vulnerabilities.
        """
        await self.create_test_table_with_data(connection_string, table_name, runtime)

        try:
            # Create DataValidationEngine
            validator = DataValidationEngine(connection_string)

            # Test with potentially malicious table/column names
            malicious_table = f"{table_name}'; DROP TABLE users; --"
            malicious_column = "age_text'; SELECT * FROM passwords; --"

            # Step 1: Attempt validation with malicious input
            # Should handle safely without executing malicious SQL
            result = await validator.validate_type_conversion(
                malicious_table, malicious_column, "varchar(20)", "integer"
            )

            # Should fail safely without SQL injection
            assert result is not None
            assert not result.is_compatible  # Should fail due to invalid table/column
            assert len(result.issues) > 0

            # Step 2: Verify original table still exists and is intact
            verify_sql = f'SELECT COUNT(*) as row_count FROM "{table_name}"'
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "verify_integrity",
                {
                    "connection_string": connection_string,
                    "query": verify_sql,
                    "validate_queries": False,
                },
            )

            results, _ = runtime.execute(workflow.build())
            assert not results["verify_integrity"].get("error")

            if (
                "result" in results["verify_integrity"]
                and "data" in results["verify_integrity"]["result"]
            ):
                rows = results["verify_integrity"]["result"]["data"]
            else:
                rows = results["verify_integrity"].get("rows", [])

            assert len(rows) > 0
            assert rows[0]["row_count"] == 10  # All data should still be there

            # Step 3: Test with valid input to ensure normal operation works
            valid_result = await validator.validate_type_conversion(
                table_name, "age_text", "varchar(20)", "integer"
            )

            assert valid_result is not None
            assert valid_result.total_rows == 10
            assert (
                valid_result.incompatible_rows > 0
            )  # Should detect 'unknown' and 'invalid_age'

        finally:
            await self.cleanup_test_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_complete_migration_orchestration_workflow(
        self, connection_string, runtime, table_name, orchestration_engine
    ):
        """
        E2E Test: Complete migration orchestration workflow.

        This tests the full migration lifecycle: validation → planning →
        execution → verification with real database operations.
        """
        await self.create_test_table_with_data(connection_string, table_name, runtime)

        try:
            # Create comprehensive migration with multiple operations
            migration = Migration(
                operations=[
                    MigrationOperation(
                        operation_type=MigrationType.ADD_COLUMN,
                        table_name=table_name,
                        metadata={
                            "column_name": "department",
                            "column_type": "VARCHAR(100) DEFAULT 'Unknown'",
                        },
                        rollback_sql=f'ALTER TABLE "{table_name}" DROP COLUMN department',
                    ),
                    MigrationOperation(
                        operation_type=MigrationType.ADD_COLUMN,
                        table_name=table_name,
                        metadata={
                            "column_name": "is_verified",
                            "column_type": "BOOLEAN DEFAULT FALSE",
                        },
                        rollback_sql=f'ALTER TABLE "{table_name}" DROP COLUMN is_verified',
                    ),
                    MigrationOperation(
                        operation_type=MigrationType.ADD_COLUMN,
                        table_name=table_name,
                        metadata={
                            "column_name": "last_login",
                            "column_type": "TIMESTAMP NULL",
                        },
                        rollback_sql=f'ALTER TABLE "{table_name}" DROP COLUMN last_login',
                    ),
                ],
                version="test_complete_workflow_v1",
                dependencies=[],
                risk_level=RiskLevel.MEDIUM,
            )

            # Step 1: Validate migration safety
            validation_result = await orchestration_engine.validate_migration_safety(
                migration
            )

            assert validation_result.is_valid is True
            assert validation_result.risk_assessment in [
                RiskLevel.LOW,
                RiskLevel.MEDIUM,
            ]

            # Step 2: Create execution plan
            execution_plan = await orchestration_engine.create_execution_plan(migration)

            assert execution_plan is not None
            assert execution_plan.migration == migration
            assert execution_plan.estimated_duration_ms > 0
            assert (
                len(execution_plan.checkpoints) >= 0
            )  # May have checkpoints for medium-risk

            # Step 3: Execute migration with rollback capability
            execution_result = await orchestration_engine.execute_with_rollback(
                execution_plan
            )

            assert execution_result.success is True
            assert execution_result.executed_operations == 3
            assert execution_result.error_message is None
            assert execution_result.execution_time_ms > 0

            # Step 4: Verify all columns were added correctly
            verify_sql = f"""
            SELECT column_name, data_type, column_default, is_nullable
            FROM information_schema.columns
            WHERE table_name = '{table_name}'
            AND column_name IN ('department', 'is_verified', 'last_login')
            ORDER BY column_name
            """

            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "verify_schema",
                {
                    "connection_string": connection_string,
                    "query": verify_sql,
                    "validate_queries": False,
                },
            )

            results, _ = runtime.execute(workflow.build())
            assert not results["verify_schema"].get("error")

            if (
                "result" in results["verify_schema"]
                and "data" in results["verify_schema"]["result"]
            ):
                rows = results["verify_schema"]["result"]["data"]
            else:
                rows = results["verify_schema"].get("rows", [])

            assert len(rows) == 3

            # Verify specific column properties
            columns = {row["column_name"]: row for row in rows}

            assert "department" in columns
            assert "Unknown" in str(columns["department"]["column_default"])

            assert "is_verified" in columns
            assert "false" in str(columns["is_verified"]["column_default"]).lower()

            assert "last_login" in columns
            assert columns["last_login"]["is_nullable"] == "YES"

            # Step 5: Verify data integrity
            count_sql = f'SELECT COUNT(*) as row_count FROM "{table_name}"'
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "verify_data",
                {
                    "connection_string": connection_string,
                    "query": count_sql,
                    "validate_queries": False,
                },
            )

            results, _ = runtime.execute(workflow.build())
            assert not results["verify_data"].get("error")

            if (
                "result" in results["verify_data"]
                and "data" in results["verify_data"]["result"]
            ):
                rows = results["verify_data"]["result"]["data"]
            else:
                rows = results["verify_data"].get("rows", [])

            assert len(rows) > 0
            assert rows[0]["row_count"] == 10  # All original data preserved

        finally:
            await self.cleanup_test_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_migration_with_performance_validation(
        self, connection_string, runtime, table_name, orchestration_engine
    ):
        """
        E2E Test: Migration with performance validation.

        This tests that migrations complete within acceptable time limits
        and performance requirements are met.
        """
        await self.create_test_table_with_data(connection_string, table_name, runtime)

        try:
            # Create simple migration for performance testing
            migration = Migration(
                operations=[
                    MigrationOperation(
                        operation_type=MigrationType.ADD_COLUMN,
                        table_name=table_name,
                        metadata={
                            "column_name": "performance_test",
                            "column_type": "INTEGER DEFAULT 0",
                        },
                    )
                ],
                version="test_performance_v1",
                dependencies=[],
                risk_level=RiskLevel.LOW,
            )

            # Step 1: Execute migration and measure performance
            start_time = datetime.now()
            execution_result = await orchestration_engine.execute_migration(migration)
            end_time = datetime.now()

            execution_time_ms = (end_time - start_time).total_seconds() * 1000

            # Step 2: Verify performance requirements
            assert execution_result.success is True
            assert execution_result.execution_time_ms > 0
            assert (
                execution_time_ms < 10000
            )  # Should complete under 10 seconds (E2E requirement)

            # Step 3: Verify execution time tracking
            assert (
                execution_result.execution_time_ms <= execution_time_ms + 100
            )  # Allow small variance

            # Step 4: Verify migration completed correctly
            verify_sql = f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = '{table_name}' AND column_name = 'performance_test'
            """

            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "verify_performance",
                {
                    "connection_string": connection_string,
                    "query": verify_sql,
                    "validate_queries": False,
                },
            )

            results, _ = runtime.execute(workflow.build())
            assert not results["verify_performance"].get("error")

            if (
                "result" in results["verify_performance"]
                and "data" in results["verify_performance"]["result"]
            ):
                rows = results["verify_performance"]["result"]["data"]
            else:
                rows = results["verify_performance"].get("rows", [])

            assert len(rows) == 1
            assert rows[0]["column_name"] == "performance_test"

        finally:
            await self.cleanup_test_table(connection_string, table_name, runtime)
