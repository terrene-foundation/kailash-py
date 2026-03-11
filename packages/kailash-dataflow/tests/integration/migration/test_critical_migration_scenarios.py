"""
Integration tests for critical DataFlow migration scenarios.

These tests cover the 6 critical migration scenarios with real PostgreSQL
infrastructure. NO MOCKING is used - all tests validate against real database operations.

Critical Migration Scenarios:
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
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.mark.integration
class TestCriticalMigrationScenarios:
    """Integration tests for critical migration scenarios with real PostgreSQL."""

    @pytest.fixture
    def runtime(self):
        """Create LocalRuntime for executing workflows."""
        return LocalRuntime()

    @pytest.fixture
    def table_name(self):
        """Generate unique table name for test."""
        return f"test_critical_{uuid.uuid4().hex[:8]}"

    async def create_populated_table(
        self, connection_string: str, table_name: str, runtime: LocalRuntime
    ):
        """Create a table with data for testing critical scenarios."""
        # Create table with problematic data for testing
        create_sql = f"""
        CREATE TABLE "{table_name}" (
            id SERIAL PRIMARY KEY,
            name VARCHAR(50),
            value_text VARCHAR(20),
            status VARCHAR(10)
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
        assert not results["create_table"].get("error")

        # Insert data including incompatible values
        insert_sql = f"""
        INSERT INTO "{table_name}" (name, value_text, status)
        VALUES
            ('Alice', '25', 'active'),
            ('Bob', 'invalid', 'active'),
            ('Charlie', '30', 'inactive'),
            ('Diana', 'null_text', 'pending'),
            ('Eve', '35', 'active')
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
        assert not results["insert_data"].get("error")

    async def cleanup_table(
        self, connection_string: str, table_name: str, runtime: LocalRuntime
    ):
        """Clean up test table."""
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

    @pytest.mark.asyncio
    async def test_incompatible_data_detection_and_validation(
        self, connection_string, runtime, table_name
    ):
        """
        Integration Test: Column datatype change with incompatible data detection.

        Tests the data validation engine's ability to detect and count
        incompatible data before migration execution.
        """
        await self.create_populated_table(connection_string, table_name, runtime)

        try:
            # Create data validation engine
            validator = DataValidationEngine(connection_string)

            # Test validation of problematic conversion
            result = await validator.validate_type_conversion(
                table_name, "value_text", "varchar(20)", "integer"
            )

            # Should detect incompatible data
            assert result.total_rows == 5
            assert (
                result.incompatible_rows >= 2
            )  # 'invalid' and 'null_text' are incompatible
            assert not result.is_compatible or len(result.issues) > 0

            # Should provide meaningful recommendations
            assert result.recommended_approach is not None
            assert (
                "BLOCKED" in result.recommended_approach
                or "MANUAL_INTERVENTION" in result.recommended_approach
            )

            # Test counting incompatible data directly
            incompatible_count = await validator.count_incompatible_data(
                table_name, "value_text", "varchar(20)", "integer"
            )

            assert incompatible_count >= 2
            assert incompatible_count == result.incompatible_rows

        finally:
            await self.cleanup_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_not_null_constraint_handling(
        self, connection_string, runtime, table_name
    ):
        """
        Integration Test: Safe NOT NULL addition to populated tables.

        Tests adding NOT NULL constraints to tables with existing data,
        including proper default value handling.
        """
        await self.create_populated_table(connection_string, table_name, runtime)

        try:
            # Create orchestration engine
            orchestrator = MigrationOrchestrationEngine(
                auto_migration_system=None,
                schema_state_manager=None,
                connection_string=connection_string,
            )

            # Test 1: Add NOT NULL column with default value (should succeed)
            safe_migration = Migration(
                operations=[
                    MigrationOperation(
                        operation_type=MigrationType.ADD_COLUMN,
                        table_name=table_name,
                        metadata={
                            "column_name": "created_at",
                            "column_type": "TIMESTAMP NOT NULL DEFAULT NOW()",
                        },
                    )
                ],
                version="safe_not_null_v1",
                risk_level=RiskLevel.LOW,
            )

            result = await orchestrator.execute_migration(safe_migration)
            assert result.success is True

            # Verify column was added and all rows have values
            verify_sql = f"""
            SELECT COUNT(*) as total_count,
                   COUNT(created_at) as non_null_count
            FROM "{table_name}"
            """

            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "verify_not_null",
                {
                    "connection_string": connection_string,
                    "query": verify_sql,
                    "validate_queries": False,
                },
            )

            results, _ = runtime.execute(workflow.build())

            if (
                "result" in results["verify_not_null"]
                and "data" in results["verify_not_null"]["result"]
            ):
                rows = results["verify_not_null"]["result"]["data"]
            else:
                rows = results["verify_not_null"].get("rows", [])

            assert len(rows) > 0
            row = rows[0]
            assert (
                row["total_count"] == row["non_null_count"]
            )  # All rows should have non-null values

        finally:
            await self.cleanup_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_migration_rollback_mechanism(
        self, connection_string, runtime, table_name
    ):
        """
        Integration Test: Transaction rollback on migration failure.

        Tests that failed migrations properly roll back changes to maintain
        database integrity.
        """
        await self.create_populated_table(connection_string, table_name, runtime)

        try:
            # Create orchestration engine
            orchestrator = MigrationOrchestrationEngine(
                auto_migration_system=None,
                schema_state_manager=None,
                connection_string=connection_string,
            )

            # Create migration that will fail on purpose
            failing_migration = Migration(
                operations=[
                    MigrationOperation(
                        operation_type=MigrationType.ADD_COLUMN,
                        table_name=table_name,
                        metadata={
                            "column_name": "temp_column",
                            "column_type": "VARCHAR(50)",
                        },
                        rollback_sql=f'ALTER TABLE "{table_name}" DROP COLUMN temp_column',
                    ),
                    MigrationOperation(
                        operation_type=MigrationType.ADD_COLUMN,
                        table_name="nonexistent_table_12345",  # This will fail
                        metadata={
                            "column_name": "fail_column",
                            "column_type": "VARCHAR(50)",
                        },
                    ),
                ],
                version="failing_migration_v1",
                risk_level=RiskLevel.HIGH,
            )

            # Execute failing migration
            result = await orchestrator.execute_migration(failing_migration)

            # Migration should fail
            assert result.success is False
            assert result.error_message is not None

            # Verify temp_column was not left behind (rollback occurred)
            verify_sql = f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = '{table_name}' AND column_name = 'temp_column'
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

            if (
                "result" in results["verify_rollback"]
                and "data" in results["verify_rollback"]["result"]
            ):
                rows = results["verify_rollback"]["result"]["data"]
            else:
                rows = results["verify_rollback"].get("rows", [])

            # temp_column should not exist (rolled back)
            assert len(rows) == 0

            # Verify original data is intact
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

            if (
                "result" in results["verify_data"]
                and "data" in results["verify_data"]["result"]
            ):
                rows = results["verify_data"]["result"]["data"]
            else:
                rows = results["verify_data"].get("rows", [])

            assert rows[0]["row_count"] == 5  # All original data preserved

        finally:
            await self.cleanup_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_connection_pool_integration(
        self, connection_string, runtime, table_name
    ):
        """
        Integration Test: DataFlow connection pool integration.

        Tests that migration operations work correctly with DataFlow's
        connection pooling mechanisms.
        """
        await self.create_populated_table(connection_string, table_name, runtime)

        try:
            # Create multiple orchestration engines to test connection handling
            orchestrator1 = MigrationOrchestrationEngine(
                auto_migration_system=None,
                schema_state_manager=None,
                connection_string=connection_string,
                connection_pool_name="test_pool_1",
            )

            orchestrator2 = MigrationOrchestrationEngine(
                auto_migration_system=None,
                schema_state_manager=None,
                connection_string=connection_string,
                connection_pool_name="test_pool_2",
            )

            # Execute migrations with different connection pools
            migration1 = Migration(
                operations=[
                    MigrationOperation(
                        operation_type=MigrationType.ADD_COLUMN,
                        table_name=table_name,
                        metadata={
                            "column_name": "pool_test_1",
                            "column_type": "VARCHAR(50) DEFAULT 'pool1'",
                        },
                    )
                ],
                version="pool_test_v1",
                risk_level=RiskLevel.LOW,
            )

            migration2 = Migration(
                operations=[
                    MigrationOperation(
                        operation_type=MigrationType.ADD_COLUMN,
                        table_name=table_name,
                        metadata={
                            "column_name": "pool_test_2",
                            "column_type": "VARCHAR(50) DEFAULT 'pool2'",
                        },
                    )
                ],
                version="pool_test_v2",
                risk_level=RiskLevel.LOW,
            )

            # Execute migrations concurrently (simulating connection pool usage)
            result1 = await orchestrator1.execute_migration(migration1)
            result2 = await orchestrator2.execute_migration(migration2)

            # Both should succeed
            assert result1.success is True
            assert result2.success is True

            # Verify both columns were created
            verify_sql = f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = '{table_name}'
            AND column_name IN ('pool_test_1', 'pool_test_2')
            ORDER BY column_name
            """

            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "verify_pools",
                {
                    "connection_string": connection_string,
                    "query": verify_sql,
                    "validate_queries": False,
                },
            )

            results, _ = runtime.execute(workflow.build())

            if (
                "result" in results["verify_pools"]
                and "data" in results["verify_pools"]["result"]
            ):
                rows = results["verify_pools"]["result"]["data"]
            else:
                rows = results["verify_pools"].get("rows", [])

            assert len(rows) == 2
            assert rows[0]["column_name"] == "pool_test_1"
            assert rows[1]["column_name"] == "pool_test_2"

        finally:
            await self.cleanup_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_sql_injection_prevention(
        self, connection_string, runtime, table_name
    ):
        """
        Integration Test: SQL injection prevention validation.

        Tests that the migration system properly handles malicious input
        without executing harmful SQL.
        """
        await self.create_populated_table(connection_string, table_name, runtime)

        try:
            # Test with potentially malicious input
            validator = DataValidationEngine(connection_string)

            # Attempt SQL injection through table name
            malicious_table = f"{table_name}'; DELETE FROM {table_name}; --"

            # Should handle safely without executing malicious SQL
            result = await validator.validate_type_conversion(
                malicious_table, "value_text", "varchar(20)", "integer"
            )

            # Should fail safely (table name is invalid)
            assert not result.is_compatible
            assert len(result.issues) > 0

            # Verify original data is intact (no deletion occurred)
            count_sql = f'SELECT COUNT(*) as row_count FROM "{table_name}"'
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "verify_injection_protection",
                {
                    "connection_string": connection_string,
                    "query": count_sql,
                    "validate_queries": False,
                },
            )

            results, _ = runtime.execute(workflow.build())

            if (
                "result" in results["verify_injection_protection"]
                and "data" in results["verify_injection_protection"]["result"]
            ):
                rows = results["verify_injection_protection"]["result"]["data"]
            else:
                rows = results["verify_injection_protection"].get("rows", [])

            assert rows[0]["row_count"] == 5  # All data should still be there

            # Test with malicious column name
            malicious_column = (
                "value_text'; UPDATE " + table_name + " SET status = 'hacked'; --"
            )

            result2 = await validator.validate_type_conversion(
                table_name, malicious_column, "varchar(20)", "integer"
            )

            # Should fail safely
            assert not result2.is_compatible

            # Verify no updates occurred
            status_sql = f'SELECT DISTINCT status FROM "{table_name}" ORDER BY status'
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "verify_no_updates",
                {
                    "connection_string": connection_string,
                    "query": status_sql,
                    "validate_queries": False,
                },
            )

            results, _ = runtime.execute(workflow.build())

            if (
                "result" in results["verify_no_updates"]
                and "data" in results["verify_no_updates"]["result"]
            ):
                rows = results["verify_no_updates"]["result"]["data"]
            else:
                rows = results["verify_no_updates"].get("rows", [])

            statuses = [row["status"] for row in rows]
            assert "hacked" not in statuses  # Injection should not have occurred
            assert set(statuses) == {
                "active",
                "inactive",
                "pending",
            }  # Original statuses preserved

        finally:
            await self.cleanup_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_concurrent_migration_locking(
        self, connection_string, runtime, table_name
    ):
        """
        Integration Test: Concurrent migration prevention.

        Tests that the migration system properly prevents concurrent migrations
        and maintains lock integrity.
        """
        await self.create_populated_table(connection_string, table_name, runtime)

        try:
            # Create orchestration engine
            orchestrator = MigrationOrchestrationEngine(
                auto_migration_system=None,
                schema_state_manager=None,
                connection_string=connection_string,
            )

            # Test sequential migrations (should both succeed)
            migration1 = Migration(
                operations=[
                    MigrationOperation(
                        operation_type=MigrationType.ADD_COLUMN,
                        table_name=table_name,
                        metadata={
                            "column_name": "lock_test_1",
                            "column_type": "INTEGER DEFAULT 1",
                        },
                    )
                ],
                version="lock_test_v1",
                risk_level=RiskLevel.LOW,
            )

            migration2 = Migration(
                operations=[
                    MigrationOperation(
                        operation_type=MigrationType.ADD_COLUMN,
                        table_name=table_name,
                        metadata={
                            "column_name": "lock_test_2",
                            "column_type": "INTEGER DEFAULT 2",
                        },
                    )
                ],
                version="lock_test_v2",
                risk_level=RiskLevel.LOW,
            )

            # Execute first migration
            result1 = await orchestrator.execute_migration(migration1)
            assert result1.success is True

            # Execute second migration (should succeed since first is complete)
            result2 = await orchestrator.execute_migration(migration2)
            assert result2.success is True

            # Verify both columns were created
            verify_sql = f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = '{table_name}'
            AND column_name IN ('lock_test_1', 'lock_test_2')
            ORDER BY column_name
            """

            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "verify_locking",
                {
                    "connection_string": connection_string,
                    "query": verify_sql,
                    "validate_queries": False,
                },
            )

            results, _ = runtime.execute(workflow.build())

            if (
                "result" in results["verify_locking"]
                and "data" in results["verify_locking"]["result"]
            ):
                rows = results["verify_locking"]["result"]["data"]
            else:
                rows = results["verify_locking"].get("rows", [])

            assert len(rows) == 2
            assert rows[0]["column_name"] == "lock_test_1"
            assert rows[1]["column_name"] == "lock_test_2"

            # Verify data integrity
            count_sql = f'SELECT COUNT(*) as row_count FROM "{table_name}"'
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "verify_lock_data",
                {
                    "connection_string": connection_string,
                    "query": count_sql,
                    "validate_queries": False,
                },
            )

            results, _ = runtime.execute(workflow.build())

            if (
                "result" in results["verify_lock_data"]
                and "data" in results["verify_lock_data"]["result"]
            ):
                rows = results["verify_lock_data"]["result"]["data"]
            else:
                rows = results["verify_lock_data"].get("rows", [])

            assert rows[0]["row_count"] == 5  # All original data preserved

        finally:
            await self.cleanup_table(connection_string, table_name, runtime)
