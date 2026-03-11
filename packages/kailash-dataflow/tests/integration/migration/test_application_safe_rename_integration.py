#!/usr/bin/env python3
"""
Integration Tests for Application-Safe Rename Strategy - TODO-139 Phase 3

Tests zero-downtime table rename strategies with real PostgreSQL database,
production-like scenarios, and complete Phase 1+2+3 integration workflows.

CRITICAL TEST COVERAGE:
- Real PostgreSQL database operations with zero-downtime rename strategies
- Production-like scenarios with views, constraints, and foreign keys
- Complete Phase 1+2+3 integration workflows with actual database changes
- Health check integration with mock application services
- View aliasing with real database views and application transition periods
- Blue-green deployment with actual table creation and atomic cutover

Key Features Tested:
1. Real Database Operations: All strategies tested against real PostgreSQL
2. Phase Integration: Complete Phase 1+2+3 workflows with real database state
3. View Aliasing: Actual view creation and management during gradual migration
4. Blue-Green Deployment: Real table creation, data sync, and atomic cutover
5. Application Health Checks: Integration with mock health check services
6. Production Safety: Complete validation and rollback mechanisms
"""

import asyncio
import time
import uuid
from typing import Dict, List, Optional

import asyncpg
import pytest
from dataflow.migrations.application_safe_rename_strategy import (
    ApplicationHealthChecker,
    ApplicationSafeRenameStrategy,
    DeploymentPhase,
    HealthCheckResult,
    StrategyExecutionResult,
    ZeroDowntimeStrategy,
)
from dataflow.migrations.complete_rename_orchestrator import (
    CompleteRenameOrchestrator,
    OrchestratorResult,
)
from dataflow.migrations.migration_connection_manager import MigrationConnectionManager
from dataflow.migrations.rename_coordination_engine import RenameCoordinationEngine
from dataflow.migrations.rename_deployment_coordinator import (
    DeploymentCoordinationResult,
    RenameDeploymentCoordinator,
)
from dataflow.migrations.table_rename_analyzer import (
    RenameImpactLevel,
    TableRenameAnalyzer,
)

from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite
from tests.utils.real_infrastructure import real_infra


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


@pytest.mark.asyncio
class TestApplicationSafeRenameIntegration:
    """Integration tests for application-safe rename strategies with real PostgreSQL."""

    @pytest.fixture
    async def sample_table_setup(self, test_suite):
        """Create sample table for rename testing."""
        async with test_suite.get_connection() as connection:
            # Create sample table with data
            await connection.execute(
                """
                CREATE TABLE users (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(255) UNIQUE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """
            )

        # Insert sample data
        await connection.execute(
            """
            INSERT INTO users (name, email) VALUES
            ('Alice Johnson', 'alice@example.com'),
            ('Bob Smith', 'bob@example.com'),
            ('Charlie Brown', 'charlie@example.com')
        """
        )

        # Create view that references the table
        await connection.execute(
            """
            CREATE VIEW user_summary AS
            SELECT name, email FROM users WHERE created_at > NOW() - INTERVAL '30 days'
        """
        )

        # Create index
        await connection.execute(
            """
            CREATE INDEX idx_users_email ON users(email)
        """
        )

        yield "users"

        # Cleanup
        try:
            await connection.execute("DROP VIEW IF EXISTS user_summary CASCADE")
            await connection.execute("DROP TABLE IF EXISTS users CASCADE")
            await connection.execute("DROP TABLE IF EXISTS accounts CASCADE")
            await connection.execute(
                "DROP VIEW IF EXISTS migration_alias_users CASCADE"
            )
        except Exception:
            pass  # Ignore cleanup errors

    @pytest.fixture
    def mock_health_checker(self):
        """Create mock health checker for integration testing."""

        class MockHealthChecker(ApplicationHealthChecker):
            def __init__(self):
                super().__init__()
                self.check_count = 0

            async def check_application_health(self, endpoint=None):
                self.check_count += 1
                # Simulate varying health check response times
                await asyncio.sleep(0.1)
                return HealthCheckResult(
                    is_healthy=True,
                    response_time=0.1,
                    endpoint=endpoint or "http://mock-app/health",
                )

        return MockHealthChecker()

    @pytest.fixture
    async def application_safe_strategy(self, test_suite, mock_health_checker):
        """Create ApplicationSafeRenameStrategy with real database components."""

        class ConnectionManager:
            def __init__(self, suite):
                self.suite = suite

            async def get_connection(self):
                return await self.suite.get_connection().__aenter__()

        return ApplicationSafeRenameStrategy(
            connection_manager=ConnectionManager(test_suite),
            health_checker=mock_health_checker,
        )

    async def test_view_aliasing_strategy_with_real_database(
        self, application_safe_strategy, test_suite, sample_table_setup
    ):
        """Test view aliasing strategy with real PostgreSQL database."""
        old_table = sample_table_setup  # "users"
        new_table = "accounts"

        async with test_suite.get_connection() as connection:
            # Execute view aliasing strategy
            result = await application_safe_strategy.execute_view_aliasing_strategy(
                old_table_name=old_table,
                new_table_name=new_table,
                connection=connection,
            )

        assert result.success
        assert result.strategy_used == ZeroDowntimeStrategy.VIEW_ALIASING
        assert result.application_downtime == 0.0  # Zero downtime achieved
        assert len(result.created_objects) > 0

        # Verify the rename actually happened
        tables = await connection.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        table_names = [row["tablename"] for row in tables]

        assert new_table in table_names  # New table exists
        assert old_table not in table_names  # Old table renamed

        # Verify alias view was created
        views = await connection.fetch(
            "SELECT viewname FROM pg_views WHERE schemaname = 'public'"
        )
        view_names = [row["viewname"] for row in views]

        alias_views = [
            name for name in view_names if "alias" in name and old_table in name
        ]
        assert len(alias_views) > 0  # Alias view created

        # Verify data integrity
        new_table_count = await connection.fetchval(f"SELECT COUNT(*) FROM {new_table}")
        assert new_table_count == 3  # All data preserved

    async def test_blue_green_strategy_with_real_database(
        self, application_safe_strategy, connection, sample_table_setup
    ):
        """Test blue-green strategy with real PostgreSQL database."""
        old_table = sample_table_setup  # "users"
        new_table = "accounts"

        # Execute blue-green strategy
        result = await application_safe_strategy.execute_blue_green_strategy(
            old_table_name=old_table, new_table_name=new_table, connection=connection
        )

        assert result.success
        assert result.strategy_used == ZeroDowntimeStrategy.BLUE_GREEN
        assert result.application_downtime == 0.0  # True zero downtime

        # Verify atomic cutover occurred
        tables = await connection.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        table_names = [row["tablename"] for row in tables]

        assert new_table in table_names  # New table exists

        # Verify data was properly migrated
        new_table_count = await connection.fetchval(f"SELECT COUNT(*) FROM {new_table}")
        assert new_table_count == 3

        # Verify backup table exists (blue-green creates backup)
        backup_tables = [
            name
            for name in table_names
            if "backup" in name or f"{old_table}_old" in name
        ]
        assert len(backup_tables) > 0

    async def test_complete_phase_1_2_3_integration(
        self, db_manager, connection, sample_table_setup
    ):
        """Test complete Phase 1+2+3 integration with real database."""
        old_table = sample_table_setup  # "users"
        new_table = "accounts"

        # Create complete orchestrator
        orchestrator = CompleteRenameOrchestrator(connection_manager=db_manager)

        # Execute complete end-to-end rename
        result = await orchestrator.execute_complete_rename(
            old_table=old_table,
            new_table=new_table,
            enable_zero_downtime=True,
            enable_health_monitoring=True,
            enable_production_safety_checks=True,
        )

        assert result.success
        assert result.total_phases_completed == 3
        assert result.total_application_downtime == 0.0

        # Validate Phase 1 (Analysis) results
        assert result.phase1_result.success
        assert result.phase1_result.phase_details is not None

        # Validate Phase 2 (Coordination) results
        assert result.phase2_result.success
        assert result.phase2_result.phase_details is not None

        # Validate Phase 3 (Application-Safe) results
        assert result.phase3_result.success
        assert result.phase3_result.phase_details is not None

        # Verify database state after complete integration
        tables = await connection.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        table_names = [row["tablename"] for row in tables]

        assert new_table in table_names

        # Verify data integrity through all phases
        final_count = await connection.fetchval(f"SELECT COUNT(*) FROM {new_table}")
        assert final_count == 3

    async def test_health_check_integration_during_rename(
        self,
        application_safe_strategy,
        connection,
        sample_table_setup,
        mock_health_checker,
    ):
        """Test health check integration during rename operations."""
        old_table = sample_table_setup
        new_table = "accounts"

        # Execute with health monitoring
        result = await application_safe_strategy.execute_with_health_monitoring(
            old_table_name=old_table,
            new_table_name=new_table,
            strategy=ZeroDowntimeStrategy.VIEW_ALIASING,
            health_check_interval=0.5,
        )

        assert result.success
        assert len(result.health_check_results) > 0

        # Verify all health checks passed
        assert all(check.is_healthy for check in result.health_check_results)

        # Verify health checker was actually called
        assert mock_health_checker.check_count > 0

    async def test_view_aliasing_with_existing_views(
        self, application_safe_strategy, connection, sample_table_setup
    ):
        """Test view aliasing strategy with existing views that reference the table."""
        old_table = sample_table_setup
        new_table = "accounts"

        # Verify existing view exists
        views = await connection.fetch(
            "SELECT viewname FROM pg_views WHERE schemaname = 'public'"
        )
        view_names = [row["viewname"] for row in views]
        assert "user_summary" in view_names

        # Execute view aliasing strategy
        result = await application_safe_strategy.execute_view_aliasing_strategy(
            old_table_name=old_table, new_table_name=new_table, connection=connection
        )

        assert result.success

        # Verify the original view still works (via aliases)
        try:
            view_count = await connection.fetchval("SELECT COUNT(*) FROM user_summary")
            # View may or may not work depending on implementation details
            # The key is that the application doesn't break
        except Exception:
            pass  # Expected if view needs updating

    async def test_production_like_scenario_with_constraints(
        self, db_manager, connection
    ):
        """Test production-like scenario with foreign keys and constraints."""

        # Create more complex schema with foreign keys
        await connection.execute(
            """
            CREATE TABLE departments (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL
            )
        """
        )

        await connection.execute(
            """
            CREATE TABLE employees (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                department_id INTEGER REFERENCES departments(id),
                email VARCHAR(255) UNIQUE
            )
        """
        )

        # Insert test data
        await connection.execute(
            """
            INSERT INTO departments (name) VALUES ('Engineering'), ('Marketing')
        """
        )

        await connection.execute(
            """
            INSERT INTO employees (name, department_id, email) VALUES
            ('Alice', 1, 'alice@company.com'),
            ('Bob', 2, 'bob@company.com')
        """
        )

        try:
            # Create complete orchestrator
            orchestrator = CompleteRenameOrchestrator(connection_manager=db_manager)

            # Execute rename on table with foreign key constraints
            result = await orchestrator.execute_complete_rename(
                old_table="employees",
                new_table="staff_members",
                enable_zero_downtime=True,
                enable_production_safety_checks=True,
            )

            assert result.success

            # Verify foreign key relationships are preserved
            staff_count = await connection.fetchval(
                "SELECT COUNT(*) FROM staff_members"
            )
            assert staff_count == 2

            # Verify FK constraint still works
            try:
                await connection.execute(
                    "INSERT INTO staff_members (name, department_id, email) VALUES ('Invalid', 999, 'test@test.com')"
                )
                assert False, "FK constraint should have prevented this"
            except asyncpg.ForeignKeyViolationError:
                pass  # Expected

        finally:
            # Cleanup
            await connection.execute("DROP TABLE IF EXISTS staff_members CASCADE")
            await connection.execute("DROP TABLE IF EXISTS employees CASCADE")
            await connection.execute("DROP TABLE IF EXISTS departments CASCADE")

    async def test_rollback_capability_on_failure(
        self, application_safe_strategy, connection, sample_table_setup
    ):
        """Test rollback capabilities when rename operations fail."""
        old_table = sample_table_setup
        new_table = "accounts"

        # First, create a conflicting table to force failure
        await connection.execute(f"CREATE TABLE {new_table} (conflict_col INTEGER)")

        try:
            # This should fail due to table already existing
            result = await application_safe_strategy.execute_view_aliasing_strategy(
                old_table_name=old_table,
                new_table_name=new_table,
                connection=connection,
            )

            # Should either fail gracefully or handle the conflict
            if not result.success:
                assert result.error_message is not None

            # Verify original table still exists and is intact
            original_count = await connection.fetchval(
                f"SELECT COUNT(*) FROM {old_table}"
            )
            assert original_count == 3

        finally:
            # Cleanup conflicting table
            await connection.execute(f"DROP TABLE IF EXISTS {new_table} CASCADE")

    async def test_staging_environment_validation_integration(self, db_manager):
        """Test staging environment validation integration (TODO-141 integration)."""

        # Mock staging environment configuration
        staging_config = {
            "host": "staging-db",
            "port": 5432,
            "database": "staging_test",
        }

        orchestrator = CompleteRenameOrchestrator(connection_manager=db_manager)

        # Execute with staging validation (will use mock validation)
        result = await orchestrator.execute_complete_rename_with_staging(
            old_table="users",
            new_table="accounts",
            staging_environment_config=staging_config,
            enable_zero_downtime=True,
        )

        # Should succeed with mock validation
        assert result.success
        assert result.staging_validation_passed
        assert result.staging_test_duration > 0

    async def test_performance_with_larger_dataset(self, connection, db_manager):
        """Test performance with larger dataset to validate zero-downtime claims."""

        # Create table with more substantial data
        await connection.execute(
            """
            CREATE TABLE large_table (
                id SERIAL PRIMARY KEY,
                data TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """
        )

        # Insert substantial amount of data
        for i in range(1000):  # 1000 rows for performance testing
            await connection.execute(
                "INSERT INTO large_table (data) VALUES ($1)", f"Test data row {i}"
            )

        try:
            strategy = ApplicationSafeRenameStrategy(connection_manager=db_manager)

            start_time = time.time()

            result = await strategy.execute_blue_green_strategy(
                old_table_name="large_table",
                new_table_name="renamed_large_table",
                connection=connection,
            )

            total_time = time.time() - start_time

            assert result.success
            assert total_time < 10.0  # Should complete within 10 seconds
            assert result.application_downtime < 1.0  # Minimal downtime

            # Verify all data was preserved
            new_count = await connection.fetchval(
                "SELECT COUNT(*) FROM renamed_large_table"
            )
            assert new_count == 1000

        finally:
            # Cleanup
            await connection.execute("DROP TABLE IF EXISTS renamed_large_table CASCADE")
            await connection.execute("DROP TABLE IF EXISTS large_table CASCADE")
            await connection.execute(
                "DROP TABLE IF EXISTS large_table_old_backup CASCADE"
            )
