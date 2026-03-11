#!/usr/bin/env python3
"""
Integration Tests for Column Removal Manager with Real PostgreSQL Infrastructure - TODO-137 Phase 2

Tests ColumnRemovalManager with real PostgreSQL database infrastructure,
validating transaction safety, backup strategies, and rollback mechanisms.

Following Tier 2 testing guidelines:
- Uses real PostgreSQL Docker infrastructure (NO MOCKING)
- Timeout: <5 seconds per test
- Tests actual database transactions and rollbacks
- Validates real backup and recovery operations
- CRITICAL PRIORITY: Transaction safety and data loss prevention

Integration Test Setup:
1. Run: ./tests/utils/test-env up && ./tests/utils/test-env status
2. Verify PostgreSQL running on port 5434
3. All tests use real database transactions and operations
"""

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

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
from dataflow.migrations.dependency_analyzer import (
    ConstraintDependency,
    DependencyAnalyzer,
    DependencyReport,
    DependencyType,
    ForeignKeyDependency,
    ImpactLevel,
    IndexDependency,
    ViewDependency,
)
from dataflow.migrations.migration_connection_manager import MigrationConnectionManager

from kailash.runtime.local import LocalRuntime

# Import test infrastructure
from tests.infrastructure.test_harness import (
    DatabaseConfig,
    DatabaseInfrastructure,
    IntegrationTestSuite,
)

# Configure logging for integration test debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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

    # Mock DataFlow instance with database config
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
async def removal_manager(connection_manager):
    """Create ColumnRemovalManager for tests."""
    manager = ColumnRemovalManager(connection_manager)
    yield manager


@pytest.fixture
async def test_connection(test_database):
    """Direct connection for test setup."""
    pool = test_database._pool
    async with pool.acquire() as conn:
        yield conn


@pytest.fixture(autouse=True)
async def clean_test_schema(test_connection):
    """Clean test schema before each test."""
    # Drop all test objects and backup tables
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
                     WHERE schemaname = 'public' AND viewname LIKE 'removal_%')
            LOOP
                EXECUTE 'DROP VIEW IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.viewname) || ' CASCADE';
            END LOOP;

            -- Drop functions
            FOR r IN (SELECT routine_schema, routine_name FROM information_schema.routines
                     WHERE routine_schema = 'public' AND routine_name LIKE 'removal_%')
            LOOP
                EXECUTE 'DROP FUNCTION IF EXISTS ' || quote_ident(r.routine_schema) || '.' || quote_ident(r.routine_name) || ' CASCADE';
            END LOOP;

            -- Drop tables
            FOR r IN (SELECT schemaname, tablename FROM pg_tables
                     WHERE schemaname = 'public' AND tablename LIKE 'removal_%')
            LOOP
                EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;
    """
    )


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestColumnRemovalManagerRealIntegration:
    """Integration tests for ColumnRemovalManager with real PostgreSQL."""

    @pytest.mark.asyncio
    async def test_plan_column_removal_with_real_dependencies(
        self, removal_manager, test_connection
    ):
        """Test removal planning with real PostgreSQL dependencies."""
        logger.info("Setting up real schema for removal planning test")

        # Create realistic schema with dependencies
        await test_connection.execute(
            """
            CREATE TABLE removal_users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,  -- Target column
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE removal_orders (
                id SERIAL PRIMARY KEY,
                user_email VARCHAR(255) NOT NULL,
                amount DECIMAL(10,2) NOT NULL,
                CONSTRAINT fk_orders_email FOREIGN KEY (user_email) REFERENCES removal_users(email) ON DELETE CASCADE
            );

            CREATE INDEX removal_users_email_idx ON removal_users(email);
            CREATE INDEX removal_users_email_status_idx ON removal_users(email, status);

            CREATE VIEW removal_active_users AS
            SELECT id, username, email FROM removal_users WHERE status = 'active';

            ALTER TABLE removal_users ADD CONSTRAINT check_email_format
                CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$');
        """
        )

        # Plan removal of email column
        start_time = time.time()
        removal_plan = await removal_manager.plan_column_removal(
            "removal_users", "email", BackupStrategy.TABLE_SNAPSHOT
        )
        planning_time = time.time() - start_time

        # Verify planning completed quickly
        assert planning_time < 5.0, f"Planning took too long: {planning_time:.2f}s"

        # Verify plan structure
        assert removal_plan.table_name == "removal_users"
        assert removal_plan.column_name == "email"
        assert removal_plan.backup_strategy == BackupStrategy.TABLE_SNAPSHOT
        assert removal_plan.estimated_duration > 0

        # Verify dependencies were detected
        assert len(removal_plan.dependencies) >= 4  # FK, indexes, view, constraint

        # Verify execution stages are properly ordered
        stages = removal_plan.execution_stages
        assert RemovalStage.BACKUP_CREATION in stages
        assert RemovalStage.CONSTRAINT_REMOVAL in stages
        assert RemovalStage.INDEX_REMOVAL in stages
        assert RemovalStage.COLUMN_REMOVAL in stages
        assert RemovalStage.VALIDATION in stages

        # Verify stage ordering (backup first, validation last)
        backup_idx = stages.index(RemovalStage.BACKUP_CREATION)
        column_idx = stages.index(RemovalStage.COLUMN_REMOVAL)
        validation_idx = stages.index(RemovalStage.VALIDATION)

        assert backup_idx < column_idx < validation_idx

        logger.info(
            f"Planning completed: {len(removal_plan.dependencies)} dependencies, {len(stages)} stages"
        )

    @pytest.mark.asyncio
    async def test_validate_removal_safety_real_critical_scenario(
        self, removal_manager, test_connection
    ):
        """Test safety validation with real critical dependencies."""
        logger.info("Setting up critical FK scenario for safety validation")

        # Create schema with critical FK dependencies
        await test_connection.execute(
            """
            CREATE TABLE removal_customers (
                id SERIAL PRIMARY KEY,
                customer_code VARCHAR(50) UNIQUE NOT NULL  -- FK target column
            );

            -- Multiple tables with RESTRICT foreign keys (prevent deletion)
            CREATE TABLE removal_orders (
                id SERIAL PRIMARY KEY,
                customer_code VARCHAR(50) NOT NULL,
                total DECIMAL(12,2) NOT NULL,
                CONSTRAINT fk_orders_customer FOREIGN KEY (customer_code)
                    REFERENCES removal_customers(customer_code) ON DELETE RESTRICT
            );

            CREATE TABLE removal_invoices (
                id SERIAL PRIMARY KEY,
                customer_code VARCHAR(50) NOT NULL,
                invoice_date DATE NOT NULL,
                CONSTRAINT fk_invoices_customer FOREIGN KEY (customer_code)
                    REFERENCES removal_customers(customer_code) ON DELETE RESTRICT
            );

            -- Add sample data to make FKs meaningful
            INSERT INTO removal_customers (customer_code) VALUES ('CUST001'), ('CUST002');
            INSERT INTO removal_orders (customer_code, total) VALUES ('CUST001', 100.00), ('CUST002', 200.00);
            INSERT INTO removal_invoices (customer_code, invoice_date) VALUES ('CUST001', '2024-01-01');
        """
        )

        # Create removal plan for critical column
        removal_plan = await removal_manager.plan_column_removal(
            "removal_customers", "customer_code", BackupStrategy.TABLE_SNAPSHOT
        )

        # Validate safety
        safety_validation = await removal_manager.validate_removal_safety(removal_plan)

        # **CRITICAL SAFETY VALIDATION**: Must block removal
        assert (
            safety_validation.is_safe is False
        ), "Must block removal of FK target column with data"
        assert safety_validation.risk_level == ImpactLevel.CRITICAL
        assert len(safety_validation.blocking_dependencies) >= 2  # Both FK constraints
        assert safety_validation.requires_confirmation is True
        assert len(safety_validation.warnings) > 0

        # Verify specific warnings about data loss
        warning_text = " ".join(safety_validation.warnings).lower()
        assert "critical" in warning_text or "foreign key" in warning_text

        # Verify recommendations include FK removal
        recommendation_text = " ".join(safety_validation.recommendations).lower()
        assert (
            "foreign key" in recommendation_text or "constraint" in recommendation_text
        )

        logger.info(
            f"Safety validation blocked: {len(safety_validation.blocking_dependencies)} blocking dependencies"
        )

    @pytest.mark.asyncio
    async def test_validate_removal_safety_real_safe_scenario(
        self, removal_manager, test_connection
    ):
        """Test safety validation with truly safe column removal."""
        logger.info("Setting up safe column removal scenario")

        # Create schema with unused column
        await test_connection.execute(
            """
            CREATE TABLE removal_products (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                unused_temp_field VARCHAR(255),  -- Safe to remove
                created_at TIMESTAMP DEFAULT NOW()
            );

            -- Dependencies on OTHER columns (not unused_temp_field)
            CREATE INDEX removal_products_name_idx ON removal_products(name);
            CREATE VIEW removal_active_products AS
                SELECT id, name, price FROM removal_products WHERE price > 0;

            -- Add sample data
            INSERT INTO removal_products (name, price, unused_temp_field)
            VALUES ('Product A', 10.00, 'old_value'), ('Product B', 20.00, NULL);
        """
        )

        # Create removal plan for safe column
        removal_plan = await removal_manager.plan_column_removal(
            "removal_products", "unused_temp_field", BackupStrategy.COLUMN_ONLY
        )

        # Validate safety
        safety_validation = await removal_manager.validate_removal_safety(removal_plan)

        # **SAFE REMOVAL VALIDATION**: Should allow removal
        assert (
            safety_validation.is_safe is True
        ), "Should allow removal of unused column"
        assert safety_validation.risk_level in [
            ImpactLevel.LOW,
            ImpactLevel.INFORMATIONAL,
        ]
        assert len(safety_validation.blocking_dependencies) == 0
        assert safety_validation.requires_confirmation is False  # Safe removal

        # Should still have some recommendations (backup, etc.)
        assert len(safety_validation.recommendations) >= 1

        logger.info("Safety validation passed: Safe removal confirmed")

    @pytest.mark.asyncio
    async def test_backup_strategies_real_database(
        self, removal_manager, test_connection
    ):
        """Test backup strategies with real database operations."""
        logger.info("Testing backup strategies with real data")

        # Create table with sample data
        await test_connection.execute(
            """
            CREATE TABLE removal_backup_test (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255),
                data JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );

            INSERT INTO removal_backup_test (name, email, data) VALUES
            ('Alice', 'alice@test.com', '{"role": "admin"}'),
            ('Bob', 'bob@test.com', '{"role": "user"}'),
            ('Charlie', NULL, '{"role": "guest"}');
        """
        )

        # Test COLUMN_ONLY backup strategy
        column_handler = removal_manager.backup_handlers[BackupStrategy.COLUMN_ONLY]
        column_backup = await column_handler.create_backup(
            "removal_backup_test", "email", test_connection
        )

        assert column_backup.strategy == BackupStrategy.COLUMN_ONLY
        assert column_backup.backup_size == 3  # 3 rows
        assert "backup" in column_backup.backup_location

        # Verify backup table was created and contains data
        backup_table = column_backup.backup_location
        backup_count = await test_connection.fetchval(
            f"SELECT COUNT(*) FROM {backup_table}"
        )
        assert backup_count == 3

        # Verify backup contains correct data
        backup_data = await test_connection.fetch(
            f"SELECT id, email FROM {backup_table} ORDER BY id"
        )
        assert backup_data[0]["email"] == "alice@test.com"
        assert backup_data[1]["email"] == "bob@test.com"
        assert backup_data[2]["email"] is None

        # Test TABLE_SNAPSHOT backup strategy
        table_handler = removal_manager.backup_handlers[BackupStrategy.TABLE_SNAPSHOT]
        table_backup = await table_handler.create_backup(
            "removal_backup_test", "email", test_connection
        )

        assert table_backup.strategy == BackupStrategy.TABLE_SNAPSHOT
        assert table_backup.backup_size == 3  # 3 rows

        # Verify full table backup
        backup_table = table_backup.backup_location
        backup_columns = await test_connection.fetch(
            f"SELECT column_name FROM information_schema.columns WHERE table_name = '{backup_table.split('.')[-1]}' ORDER BY ordinal_position"
        )
        column_names = [col["column_name"] for col in backup_columns]
        assert "id" in column_names
        assert "name" in column_names
        assert "email" in column_names
        assert "data" in column_names

        logger.info(
            f"Backup strategies tested: column={column_backup.backup_size} rows, table={table_backup.backup_size} rows"
        )

    @pytest.mark.asyncio
    async def test_execute_safe_removal_real_success(
        self, removal_manager, test_connection
    ):
        """Test successful removal execution with real database operations."""
        logger.info("Testing successful column removal execution")

        # Create table with removable column and dependencies
        await test_connection.execute(
            """
            CREATE TABLE removal_execution_test (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                temp_column VARCHAR(100),  -- Target for removal
                created_at TIMESTAMP DEFAULT NOW()
            );

            -- Create index on removable column (safe dependency)
            CREATE INDEX removal_temp_column_idx ON removal_execution_test(temp_column);

            -- Add sample data
            INSERT INTO removal_execution_test (name, temp_column) VALUES
            ('Test 1', 'temp_value_1'),
            ('Test 2', 'temp_value_2'),
            ('Test 3', NULL);
        """
        )

        # Create and execute removal plan
        removal_plan = await removal_manager.plan_column_removal(
            "removal_execution_test", "temp_column", BackupStrategy.COLUMN_ONLY
        )

        # Execute removal
        start_time = time.time()
        result = await removal_manager.execute_safe_removal(removal_plan)
        execution_time = time.time() - start_time

        # Verify successful execution
        assert result.result == RemovalResult.SUCCESS
        assert result.rollback_executed is False
        assert result.execution_time > 0
        assert result.backup_preserved is True
        assert (
            len(result.stages_completed) >= 4
        )  # backup, index removal, column removal, validation

        # Verify all stages completed successfully
        for stage in result.stages_completed:
            assert stage.success is True, f"Stage {stage.stage} failed: {stage.errors}"
            assert stage.execution_time > 0

        # Verify column was actually removed
        column_exists = await test_connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'removal_execution_test'
                AND column_name = 'temp_column'
            )
        """
        )
        assert column_exists is False, "Column should have been removed"

        # Verify index was removed
        index_exists = await test_connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'removal_execution_test'
                AND indexname = 'removal_temp_column_idx'
            )
        """
        )
        assert index_exists is False, "Index should have been removed"

        # Verify data integrity (other columns intact)
        row_count = await test_connection.fetchval(
            "SELECT COUNT(*) FROM removal_execution_test"
        )
        assert row_count == 3, "Data should be preserved"

        # Verify backup exists and contains correct data
        backup_location = None
        for stage in result.stages_completed:
            if stage.stage == RemovalStage.BACKUP_CREATION:
                backup_location = stage.details.get("backup_location")
                break

        assert backup_location is not None, "Backup location should be recorded"

        backup_count = await test_connection.fetchval(
            f"SELECT COUNT(*) FROM {backup_location}"
        )
        assert backup_count == 3, "Backup should contain all rows"

        logger.info(
            f"Successful removal: {execution_time:.2f}s, {len(result.stages_completed)} stages"
        )

    @pytest.mark.asyncio
    async def test_execute_removal_with_transaction_rollback(
        self, removal_manager, test_connection
    ):
        """Test transaction rollback on failure during removal execution."""
        logger.info("Testing transaction rollback on removal failure")

        # Create table with data
        await test_connection.execute(
            """
            CREATE TABLE removal_rollback_test (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                target_column VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW()
            );

            INSERT INTO removal_rollback_test (name, target_column) VALUES
            ('Test 1', 'value_1'),
            ('Test 2', 'value_2');
        """
        )

        # Create removal plan
        removal_plan = await removal_manager.plan_column_removal(
            "removal_rollback_test", "target_column", BackupStrategy.COLUMN_ONLY
        )

        # Simulate failure by dropping the table mid-execution
        # We'll use a custom plan that will fail at column removal stage
        original_execute_stage = removal_manager._execute_removal_stage

        async def failing_execute_stage(
            stage, table_name, column_name, connection, plan, stage_details=None
        ):
            if stage == RemovalStage.COLUMN_REMOVAL:
                # Simulate a database error during column removal
                raise Exception("Simulated column removal failure")
            return await original_execute_stage(
                stage, table_name, column_name, connection, plan, stage_details
            )

        removal_manager._execute_removal_stage = failing_execute_stage

        try:
            # Execute removal (should fail and rollback)
            result = await removal_manager.execute_safe_removal(removal_plan)

            # Verify rollback occurred
            assert result.result == RemovalResult.TRANSACTION_FAILED
            assert result.rollback_executed is True
            assert "Simulated column removal failure" in result.error_message
            assert len(result.recovery_instructions) > 0

            # Verify database state was rolled back (column still exists)
            column_exists = await test_connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'removal_rollback_test'
                    AND column_name = 'target_column'
                )
            """
            )
            assert column_exists is True, "Column should still exist after rollback"

            # Verify data integrity (data still exists)
            row_count = await test_connection.fetchval(
                "SELECT COUNT(*) FROM removal_rollback_test"
            )
            assert row_count == 2, "Data should be preserved after rollback"

            # Verify some stages completed before failure
            completed_stages = [s for s in result.stages_completed if s.success]
            failed_stages = [s for s in result.stages_completed if not s.success]

            assert (
                len(completed_stages) >= 1
            ), "Some stages should have completed before failure"
            assert len(failed_stages) >= 1, "Failed stage should be recorded"

            logger.info(
                f"Rollback successful: {len(completed_stages)} completed, {len(failed_stages)} failed"
            )

        finally:
            # Restore original method
            removal_manager._execute_removal_stage = original_execute_stage

    @pytest.mark.asyncio
    async def test_execute_dry_run_real_database(
        self, removal_manager, test_connection
    ):
        """Test dry run execution with real database (no actual changes)."""
        logger.info("Testing dry run execution")

        # Create table with dependencies
        await test_connection.execute(
            """
            CREATE TABLE removal_dry_run_test (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                test_column VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX removal_dry_run_idx ON removal_dry_run_test(test_column);

            INSERT INTO removal_dry_run_test (name, test_column) VALUES
            ('Test 1', 'value_1'),
            ('Test 2', 'value_2');
        """
        )

        # Create dry run plan
        removal_plan = await removal_manager.plan_column_removal(
            "removal_dry_run_test", "test_column", BackupStrategy.COLUMN_ONLY
        )
        removal_plan.dry_run = True  # Enable dry run mode

        # Execute dry run
        result = await removal_manager.execute_safe_removal(removal_plan)

        # Verify dry run results
        assert result.result == RemovalResult.SUCCESS  # Dry run succeeds
        assert len(result.stages_completed) >= 3  # All stages "executed"

        # Verify all stages marked as dry run
        for stage in result.stages_completed:
            assert stage.success is True
            assert "dry run" in " ".join(stage.details.get("notes", [])).lower()

        # **CRITICAL**: Verify no actual changes were made
        # Column should still exist
        column_exists = await test_connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'removal_dry_run_test'
                AND column_name = 'test_column'
            )
        """
        )
        assert column_exists is True, "DRY RUN: Column should still exist"

        # Index should still exist
        index_exists = await test_connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'removal_dry_run_test'
                AND indexname = 'removal_dry_run_idx'
            )
        """
        )
        assert index_exists is True, "DRY RUN: Index should still exist"

        # Data should be unchanged
        row_count = await test_connection.fetchval(
            "SELECT COUNT(*) FROM removal_dry_run_test"
        )
        assert row_count == 2, "DRY RUN: Data should be unchanged"

        # No backup tables should be created (dry run)
        backup_tables = await test_connection.fetch(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public' AND tablename LIKE '%backup%'
        """
        )
        assert len(backup_tables) == 0, "DRY RUN: No backup tables should be created"

        logger.info("Dry run validation complete: No actual changes made")

    @pytest.mark.asyncio
    async def test_concurrent_removal_safety(self, test_database, connection_manager):
        """Test safety with concurrent removal attempts."""
        logger.info("Testing concurrent removal safety")

        # Create two separate removal managers (simulating concurrent users)
        removal_manager_1 = ColumnRemovalManager(connection_manager)
        removal_manager_2 = ColumnRemovalManager(connection_manager)

        # Set up test schema
        async with test_database._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE removal_concurrent_test (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    concurrent_column VARCHAR(100),
                    created_at TIMESTAMP DEFAULT NOW()
                );

                INSERT INTO removal_concurrent_test (name, concurrent_column) VALUES
                ('Test 1', 'value_1'),
                ('Test 2', 'value_2');
            """
            )

        # Create removal plans for both managers
        plan_1 = await removal_manager_1.plan_column_removal(
            "removal_concurrent_test", "concurrent_column", BackupStrategy.COLUMN_ONLY
        )
        plan_2 = await removal_manager_2.plan_column_removal(
            "removal_concurrent_test", "concurrent_column", BackupStrategy.COLUMN_ONLY
        )

        # Execute concurrent removal attempts
        async def execute_removal_1():
            try:
                return await removal_manager_1.execute_safe_removal(plan_1)
            except Exception as e:
                return {"error": str(e)}

        async def execute_removal_2():
            # Slight delay to ensure first removal starts first
            await asyncio.sleep(0.1)
            try:
                return await removal_manager_2.execute_safe_removal(plan_2)
            except Exception as e:
                return {"error": str(e)}

        # Run concurrent executions
        results = await asyncio.gather(
            execute_removal_1(), execute_removal_2(), return_exceptions=True
        )

        # Verify concurrent safety
        success_count = sum(
            1
            for r in results
            if hasattr(r, "result") and r.result == RemovalResult.SUCCESS
        )
        error_count = sum(1 for r in results if isinstance(r, dict) and "error" in r)

        # At most one should succeed (safe concurrency)
        assert (
            success_count <= 1
        ), f"Too many concurrent removals succeeded: {success_count}"

        # Verify final database state is consistent
        async with test_database._pool.acquire() as conn:
            column_exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'removal_concurrent_test'
                    AND column_name = 'concurrent_column'
                )
            """
            )

            # Column should either exist (no removals succeeded) or not exist (one succeeded)
            data_count = await conn.fetchval(
                "SELECT COUNT(*) FROM removal_concurrent_test"
            )
            assert data_count == 2, "Data integrity should be maintained"

        logger.info(
            f"Concurrent safety verified: {success_count} successes, {error_count} errors"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
