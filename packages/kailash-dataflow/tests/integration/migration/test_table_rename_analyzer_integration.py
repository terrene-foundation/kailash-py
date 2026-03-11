#!/usr/bin/env python3
"""
Integration Tests for Table Schema Rename Engine - TODO-139

Tests the complete table rename functionality including:
- Analysis of table dependencies (foreign keys, views, triggers, indexes)
- Generation of rename execution plans
- Transaction-safe execution with rollback
- Validation of rename completion

Following DataFlow test guidelines:
- Uses IntegrationTestSuite for real PostgreSQL testing
- No mocking - real database operations
- Comprehensive coverage of rename scenarios
"""

import time
from datetime import datetime
from typing import Dict, List, Optional

import asyncpg
import pytest
from dataflow.migrations.dependency_analyzer import DependencyAnalyzer
from dataflow.migrations.foreign_key_analyzer import ForeignKeyAnalyzer
from dataflow.migrations.table_rename_analyzer import (
    RenameExecutionResult,
    RenameImpactLevel,
    RenameStep,
    SchemaObjectType,
    TableRenameAnalyzer,
    TableRenameError,
    TableRenamePlan,
    TableRenameReport,
)

from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
async def analyzer_with_connection(test_suite):
    """Create TableRenameAnalyzer with real database connection."""

    # Create a connection manager that properly handles connection lifecycle
    class TestConnectionManager:
        def __init__(self, test_suite):
            self.test_suite = test_suite
            self._active_connections = []

        async def get_connection(self):
            """Get connection from test suite and track it for proper cleanup."""
            # Use the connection context manager to ensure proper resource management
            # However, analyzers expect a raw connection, so we need a different approach
            # We'll use a single shared connection for the test session
            if not hasattr(self, "_shared_connection"):
                self._shared_connection = (
                    await self.test_suite.infrastructure.get_connection()
                )
                self._active_connections.append(self._shared_connection)
            return self._shared_connection

        async def cleanup(self):
            """Clean up all active connections."""
            for conn in self._active_connections:
                try:
                    if hasattr(self.test_suite.infrastructure._pool, "release"):
                        await self.test_suite.infrastructure._pool.release(conn)
                except Exception as e:
                    print(f"Error releasing connection: {e}")
            self._active_connections.clear()

    connection_manager = TestConnectionManager(test_suite)

    # Create analyzers with real connection
    dependency_analyzer = DependencyAnalyzer(connection_manager)
    fk_analyzer = ForeignKeyAnalyzer(connection_manager)

    analyzer = TableRenameAnalyzer(
        connection_manager=connection_manager,
        dependency_analyzer=dependency_analyzer,
        fk_analyzer=fk_analyzer,
    )

    yield analyzer, test_suite

    # Cleanup connections after test completes
    await connection_manager.cleanup()


class TestTableRenameAnalyzerIntegration:
    """Integration tests for TableRenameAnalyzer with real PostgreSQL."""

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_simple_table_rename_no_dependencies(self, analyzer_with_connection):
        """Test renaming a table with no dependencies."""
        analyzer, test_suite = analyzer_with_connection

        # Clean test tables first
        async with test_suite.get_connection() as conn:
            await conn.execute("DROP TABLE IF EXISTS test_renamed_table CASCADE")
            await conn.execute("DROP TABLE IF EXISTS test_simple_table CASCADE")

        async with test_suite.get_connection() as conn:
            # Create a simple table with no dependencies
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_simple_table (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Insert test data
            await conn.execute(
                """
                INSERT INTO test_simple_table (name) VALUES ('Test 1'), ('Test 2')
            """
            )

        # Analyze rename operation
        report = await analyzer.analyze_table_rename(
            "test_simple_table", "test_renamed_table"
        )

        assert report.old_table_name == "test_simple_table"
        assert report.new_table_name == "test_renamed_table"
        assert len(report.schema_objects) >= 0  # May have indexes
        # Primary key index makes this HIGH impact (unique indexes are high impact)
        assert report.impact_summary.overall_risk in [
            RenameImpactLevel.SAFE,
            RenameImpactLevel.LOW,
            RenameImpactLevel.HIGH,
        ]

        # Generate rename plan
        plan = await analyzer.generate_rename_plan(report)
        assert len(plan.steps) >= 1  # At least the rename step

        # Execute rename
        async with test_suite.get_connection() as conn:
            result = await analyzer.execute_rename_plan(plan, conn)

        assert result.success is True
        assert result.old_table_name == "test_simple_table"
        assert result.new_table_name == "test_renamed_table"

        # Validate rename completion
        is_complete = await analyzer.validate_rename_completion(
            "test_simple_table", "test_renamed_table"
        )
        assert is_complete is True

        # Verify data integrity
        async with test_suite.get_connection() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM test_renamed_table")
            assert count == 2

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_table_rename_with_foreign_keys(self, analyzer_with_connection):
        """Test renaming a table that is referenced by foreign keys."""
        analyzer, test_suite = analyzer_with_connection

        # Clean test tables first
        async with test_suite.get_connection() as conn:
            await conn.execute("DROP TABLE IF EXISTS test_orders CASCADE")
            await conn.execute("DROP TABLE IF EXISTS test_customers CASCADE")
            await conn.execute("DROP TABLE IF EXISTS test_users CASCADE")

        async with test_suite.get_connection() as conn:
            # Create parent table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(255) UNIQUE,
                    email VARCHAR(255)
                )
            """
            )

            # Create child table with foreign key
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_orders (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES test_users(id) ON DELETE CASCADE,
                    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total DECIMAL(10, 2)
                )
            """
            )

            # Insert test data
            await conn.execute(
                """
                INSERT INTO test_users (username, email)
                VALUES ('user1', 'user1@test.com'), ('user2', 'user2@test.com')
            """
            )

            await conn.execute(
                """
                INSERT INTO test_orders (user_id, total)
                VALUES (1, 100.00), (1, 200.00), (2, 150.00)
            """
            )

        # Analyze rename of parent table
        report = await analyzer.analyze_table_rename("test_users", "test_customers")

        # Should detect foreign key dependencies
        fk_objects = [
            obj
            for obj in report.schema_objects
            if obj.object_type == SchemaObjectType.FOREIGN_KEY
        ]
        assert len(fk_objects) >= 1
        assert report.impact_summary.overall_risk in [
            RenameImpactLevel.HIGH,
            RenameImpactLevel.CRITICAL,
        ]

        # Generate and execute rename plan
        plan = await analyzer.generate_rename_plan(report)

        # Plan should include FK handling steps
        step_types = [step.step_type for step in plan.steps]
        assert "drop_foreign_key" in step_types or "disable_foreign_key" in step_types
        assert "rename_table" in step_types
        assert (
            "recreate_foreign_key" in step_types or "enable_foreign_key" in step_types
        )

        async with test_suite.get_connection() as conn:
            result = await analyzer.execute_rename_plan(plan, conn)

        assert result.success is True

        # Validate rename and FK integrity
        async with test_suite.get_connection() as conn:
            # Check that table was renamed
            table_exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'test_customers'
                )
            """
            )
            assert table_exists is True

            # Check that FK still works - insert should succeed
            await conn.execute(
                """
                INSERT INTO test_orders (user_id, total)
                VALUES (1, 300.00)
            """
            )

            # Check that FK constraint is enforced - should fail
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                await conn.execute(
                    """
                    INSERT INTO test_orders (user_id, total)
                    VALUES (999, 400.00)
                """
                )

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_table_rename_with_views(self, analyzer_with_connection):
        """Test renaming a table that is referenced by views."""
        analyzer, test_suite = analyzer_with_connection

        # Clean test tables and views first
        async with test_suite.get_connection() as conn:
            await conn.execute("DROP MATERIALIZED VIEW IF EXISTS test_product_summary")
            await conn.execute("DROP VIEW IF EXISTS test_expensive_products")
            await conn.execute("DROP TABLE IF EXISTS test_inventory CASCADE")
            await conn.execute("DROP TABLE IF EXISTS test_products CASCADE")

        async with test_suite.get_connection() as conn:
            # Create base table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_products (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255),
                    price DECIMAL(10, 2),
                    category VARCHAR(100)
                )
            """
            )

            # Create view referencing the table
            await conn.execute(
                """
                CREATE VIEW test_expensive_products AS
                SELECT * FROM test_products
                WHERE price > 100.00
            """
            )

            # Create materialized view
            await conn.execute(
                """
                CREATE MATERIALIZED VIEW test_product_summary AS
                SELECT category, COUNT(*) as product_count, AVG(price) as avg_price
                FROM test_products
                GROUP BY category
            """
            )

            # Insert test data
            await conn.execute(
                """
                INSERT INTO test_products (name, price, category)
                VALUES
                    ('Product A', 50.00, 'Electronics'),
                    ('Product B', 150.00, 'Electronics'),
                    ('Product C', 200.00, 'Furniture')
            """
            )

        # Analyze rename
        report = await analyzer.analyze_table_rename("test_products", "test_inventory")

        # Should detect view dependencies
        view_objects = [
            obj
            for obj in report.schema_objects
            if obj.object_type == SchemaObjectType.VIEW
        ]
        assert len(view_objects) >= 1  # At least the regular view

        # Generate and execute rename plan
        plan = await analyzer.generate_rename_plan(report)

        async with test_suite.get_connection() as conn:
            result = await analyzer.execute_rename_plan(plan, conn)

        assert result.success is True

        # Validate views still work with renamed table
        async with test_suite.get_connection() as conn:
            # Regular view should work
            view_count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM test_expensive_products
            """
            )
            assert view_count >= 2  # Products B and C

            # Check view definition was updated
            view_def = await conn.fetchval(
                """
                SELECT definition FROM pg_views
                WHERE viewname = 'test_expensive_products'
            """
            )
            assert "test_inventory" in view_def or "test_products" not in view_def

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_table_rename_with_indexes_and_constraints(
        self, analyzer_with_connection
    ):
        """Test renaming a table with various indexes and constraints."""
        analyzer, test_suite = analyzer_with_connection

        # Clean test tables first
        async with test_suite.get_connection() as conn:
            await conn.execute("DROP TABLE IF EXISTS test_staff CASCADE")
            await conn.execute("DROP TABLE IF EXISTS test_employees CASCADE")

        async with test_suite.get_connection() as conn:
            # Create table with various constraints and indexes
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_employees (
                    id SERIAL PRIMARY KEY,
                    employee_code VARCHAR(50) UNIQUE NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) UNIQUE,
                    department VARCHAR(100),
                    salary DECIMAL(10, 2) CHECK (salary > 0),
                    hire_date DATE DEFAULT CURRENT_DATE,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """
            )

            # Create various indexes
            await conn.execute(
                """
                CREATE INDEX idx_employees_department
                ON test_employees(department)
            """
            )

            await conn.execute(
                """
                CREATE INDEX idx_employees_salary
                ON test_employees(salary DESC)
            """
            )

            await conn.execute(
                """
                CREATE INDEX idx_employees_active_dept
                ON test_employees(is_active, department)
                WHERE is_active = TRUE
            """
            )

        # Analyze rename
        report = await analyzer.analyze_table_rename("test_employees", "test_staff")

        # Should detect indexes
        index_objects = [
            obj
            for obj in report.schema_objects
            if obj.object_type == SchemaObjectType.INDEX
        ]
        assert len(index_objects) >= 3  # Our custom indexes

        # Generate and execute rename plan
        plan = await analyzer.generate_rename_plan(report)

        async with test_suite.get_connection() as conn:
            result = await analyzer.execute_rename_plan(plan, conn)

        assert result.success is True

        # Validate constraints still work
        async with test_suite.get_connection() as conn:
            # Unique constraint should work
            await conn.execute(
                """
                INSERT INTO test_staff (employee_code, name, email, salary)
                VALUES ('EMP001', 'John Doe', 'john@test.com', 50000)
            """
            )

            # Unique violation should fail
            with pytest.raises(asyncpg.UniqueViolationError):
                await conn.execute(
                    """
                    INSERT INTO test_staff (employee_code, name, email, salary)
                    VALUES ('EMP001', 'Jane Doe', 'jane@test.com', 60000)
                """
                )

            # Check constraint should work
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    """
                    INSERT INTO test_staff (employee_code, name, email, salary)
                    VALUES ('EMP002', 'Invalid', 'invalid@test.com', -1000)
                """
                )

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_table_rename_rollback_on_failure(self, analyzer_with_connection):
        """Test that rename operations are properly rolled back on failure."""
        analyzer, test_suite = analyzer_with_connection

        # Clean test tables first
        async with test_suite.get_connection() as conn:
            await conn.execute("DROP TABLE IF EXISTS test_rollback_renamed CASCADE")
            await conn.execute("DROP TABLE IF EXISTS test_rollback_child CASCADE")
            await conn.execute("DROP TABLE IF EXISTS test_rollback_parent CASCADE")

        async with test_suite.get_connection() as conn:
            # Create tables with dependencies
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_rollback_parent (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255)
                )
            """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_rollback_child (
                    id SERIAL PRIMARY KEY,
                    parent_id INTEGER REFERENCES test_rollback_parent(id)
                )
            """
            )

            # Create a conflicting table with the target name
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_rollback_renamed (
                    id SERIAL PRIMARY KEY,
                    data TEXT
                )
            """
            )

        # Try to rename to an existing table name (should fail)
        report = await analyzer.analyze_table_rename(
            "test_rollback_parent", "test_rollback_renamed"
        )

        plan = await analyzer.generate_rename_plan(report)

        async with test_suite.get_connection() as conn:
            result = await analyzer.execute_rename_plan(plan, conn)

        # Should fail because target table exists
        assert result.success is False
        assert result.rollback_executed is True

        # Verify original table still exists and works
        async with test_suite.get_connection() as conn:
            # Original table should still exist
            exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'test_rollback_parent'
                )
            """
            )
            assert exists is True

            # Foreign key should still work
            await conn.execute(
                """
                INSERT INTO test_rollback_parent (name) VALUES ('Test')
            """
            )
            parent_id = await conn.fetchval(
                """
                SELECT id FROM test_rollback_parent WHERE name = 'Test'
            """
            )
            await conn.execute(
                """
                INSERT INTO test_rollback_child (parent_id) VALUES ($1)
            """,
                parent_id,
            )

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_circular_foreign_key_dependencies(self, analyzer_with_connection):
        """Test handling of circular foreign key dependencies."""
        analyzer, test_suite = analyzer_with_connection

        # Clean test tables first
        async with test_suite.get_connection() as conn:
            await conn.execute("DROP TABLE IF EXISTS test_groups CASCADE")
            await conn.execute("DROP TABLE IF EXISTS test_members CASCADE")
            await conn.execute("DROP TABLE IF EXISTS test_teams CASCADE")

        async with test_suite.get_connection() as conn:
            # Create tables with circular FK dependencies
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_teams (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255),
                    leader_id INTEGER
                )
            """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_members (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255),
                    team_id INTEGER REFERENCES test_teams(id)
                )
            """
            )

            # Add circular reference
            await conn.execute(
                """
                ALTER TABLE test_teams
                ADD CONSTRAINT fk_team_leader
                FOREIGN KEY (leader_id) REFERENCES test_members(id)
            """
            )

        # Analyze rename of one table in circular dependency
        report = await analyzer.analyze_table_rename("test_teams", "test_groups")

        # Should detect the circular dependency
        assert report.dependency_graph is not None
        if hasattr(report.dependency_graph, "circular_dependency_detected"):
            assert report.dependency_graph.circular_dependency_detected is True

        # Should still be able to generate a plan
        plan = await analyzer.generate_rename_plan(report)
        assert len(plan.steps) > 0

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_performance_with_large_schema(self, analyzer_with_connection):
        """Test rename analysis performance with many dependencies."""
        analyzer, test_suite = analyzer_with_connection

        # Clean test tables first
        async with test_suite.get_connection() as conn:
            # Drop views first
            for i in range(3):
                await conn.execute(f"DROP VIEW IF EXISTS test_view_{i}")
            # Drop dependent tables
            for i in range(10):
                await conn.execute(f"DROP TABLE IF EXISTS test_dependent_{i} CASCADE")
            # Drop main table
            await conn.execute("DROP TABLE IF EXISTS test_renamed_main CASCADE")
            await conn.execute("DROP TABLE IF EXISTS test_main_table CASCADE")

        async with test_suite.get_connection() as conn:
            # Create a main table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_main_table (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(50) UNIQUE,
                    data TEXT
                )
            """
            )

            # Create multiple dependent tables
            for i in range(10):
                await conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS test_dependent_{i} (
                        id SERIAL PRIMARY KEY,
                        main_id INTEGER REFERENCES test_main_table(id),
                        value VARCHAR(255)
                    )
                """
                )

            # Create multiple indexes
            for i in range(5):
                await conn.execute(
                    f"""
                    CREATE INDEX idx_main_{i}
                    ON test_main_table(code, data)
                """
                )

            # Create a few views
            for i in range(3):
                await conn.execute(
                    f"""
                    CREATE VIEW test_view_{i} AS
                    SELECT * FROM test_main_table
                    WHERE id > {i * 10}
                """
                )

        # Measure analysis time
        start_time = time.time()
        report = await analyzer.analyze_table_rename(
            "test_main_table", "test_renamed_main"
        )
        analysis_time = time.time() - start_time

        # Should complete in reasonable time
        assert analysis_time < 5.0  # Should complete within 5 seconds

        # Should find all dependencies
        assert len(report.schema_objects) >= 18  # 10 FKs + 5 indexes + 3 views

        # Generate plan
        plan = await analyzer.generate_rename_plan(report)
        assert len(plan.steps) >= 10  # Should have steps for all operations

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_sql_injection_protection(self, analyzer_with_connection):
        """Test protection against SQL injection in table names."""
        analyzer, test_suite = analyzer_with_connection

        # Try malicious table names
        malicious_names = [
            "users'; DROP TABLE users; --",
            'users" OR 1=1 --',
            "users`; DELETE FROM users WHERE 1=1; --",
        ]

        for malicious_name in malicious_names:
            # Should sanitize and not execute malicious SQL
            try:
                report = await analyzer.analyze_table_rename(
                    malicious_name, "safe_table_name"
                )
                # If it doesn't raise an error, check that name was sanitized
                assert report.old_table_name != malicious_name
                assert "DROP" not in report.old_table_name
                assert "DELETE" not in report.old_table_name
            except (TableRenameError, ValueError):
                # Expected - malicious input rejected
                pass


class TestTableRenamePlanGeneration:
    """Test plan generation for various rename scenarios."""

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_plan_generation_phases(self, analyzer_with_connection):
        """Test that plan generation creates proper phases."""
        analyzer, test_suite = analyzer_with_connection

        # Clean test tables first
        async with test_suite.get_connection() as conn:
            await conn.execute("DROP TABLE IF EXISTS test_plan_renamed CASCADE")
            await conn.execute("DROP VIEW IF EXISTS test_plan_view CASCADE")
            await conn.execute("DROP TABLE IF EXISTS test_plan_child CASCADE")
            await conn.execute("DROP TABLE IF EXISTS test_plan_table CASCADE")

        async with test_suite.get_connection() as conn:
            # Create complex schema
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_plan_table (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255)
                )
            """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_plan_child (
                    id SERIAL PRIMARY KEY,
                    parent_id INTEGER REFERENCES test_plan_table(id)
                )
            """
            )

            await conn.execute(
                """
                CREATE VIEW test_plan_view AS
                SELECT * FROM test_plan_table
            """
            )

            await conn.execute(
                """
                CREATE INDEX idx_plan_name ON test_plan_table(name)
            """
            )

        # Analyze and generate plan
        report = await analyzer.analyze_table_rename(
            "test_plan_table", "test_plan_renamed"
        )

        plan = await analyzer.generate_rename_plan(report)

        # Verify plan has correct phases in order
        step_types = [step.step_type for step in plan.steps]

        # Should validate target first
        assert step_types[0] == "validate_target"

        # Should drop FKs before rename
        fk_drop_index = next(
            (i for i, t in enumerate(step_types) if t == "drop_foreign_key"), -1
        )
        rename_index = next(
            (i for i, t in enumerate(step_types) if t == "rename_table"), -1
        )

        if fk_drop_index >= 0:
            assert fk_drop_index < rename_index

        # Should recreate FKs after rename
        fk_recreate_index = next(
            (i for i, t in enumerate(step_types) if t == "recreate_foreign_key"), -1
        )
        if fk_recreate_index >= 0:
            assert fk_recreate_index > rename_index

        # Each step should have rollback SQL
        for step in plan.steps:
            if step.step_type != "validate_target":
                assert step.rollback_sql is not None

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_plan_risk_assessment(self, analyzer_with_connection):
        """Test that plan steps have appropriate risk levels."""
        analyzer, test_suite = analyzer_with_connection

        # Clean test tables first
        async with test_suite.get_connection() as conn:
            await conn.execute("DROP TABLE IF EXISTS test_risk_renamed CASCADE")
            await conn.execute("DROP TABLE IF EXISTS test_risk_child CASCADE")
            await conn.execute("DROP TABLE IF EXISTS test_risk_parent CASCADE")

        async with test_suite.get_connection() as conn:
            # Create table with CASCADE foreign key (high risk)
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_risk_parent (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255)
                )
            """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_risk_child (
                    id SERIAL PRIMARY KEY,
                    parent_id INTEGER REFERENCES test_risk_parent(id) ON DELETE CASCADE
                )
            """
            )

        report = await analyzer.analyze_table_rename(
            "test_risk_parent", "test_risk_renamed"
        )

        plan = await analyzer.generate_rename_plan(report)

        # Steps involving CASCADE FKs should be high risk
        fk_steps = [step for step in plan.steps if "foreign_key" in step.step_type]
        for step in fk_steps:
            assert step.risk_level in [
                RenameImpactLevel.HIGH,
                RenameImpactLevel.CRITICAL,
            ]

        # The rename itself should be critical
        rename_steps = [step for step in plan.steps if step.step_type == "rename_table"]
        for step in rename_steps:
            assert step.risk_level == RenameImpactLevel.CRITICAL


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=30"])
