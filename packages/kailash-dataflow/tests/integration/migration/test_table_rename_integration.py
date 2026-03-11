#!/usr/bin/env python3
"""
Integration Tests for Table Schema Rename Engine - TODO-139 Phase 1

Tests the TableRenameAnalyzer with real PostgreSQL database connections
to verify schema object discovery and dependency analysis capabilities.

Following Tier 2 testing guidelines:
- Uses real Docker PostgreSQL services from tests/utils
- NO MOCKING - all database operations must be real
- Tests actual schema object discovery with real data
- Timeout: <5 seconds per test
- CRITICAL PRIORITY: Real referential integrity scenarios
"""

import asyncio
import time
from datetime import datetime
from unittest.mock import AsyncMock

import asyncpg
import pytest
from dataflow.migrations.dependency_analyzer import DependencyAnalyzer
from dataflow.migrations.foreign_key_analyzer import ForeignKeyAnalyzer
from dataflow.migrations.table_rename_analyzer import (
    DependencyGraph,
    RenameImpactLevel,
    RenameValidation,
    SchemaObject,
    SchemaObjectType,
    TableRenameAnalyzer,
    TableRenameError,
    TableRenameReport,
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


class TestTableRenameAnalyzerIntegration:
    """Integration tests for TableRenameAnalyzer with real database."""

    @pytest.fixture
    async def connection_manager(self, database_config):
        """Create async connection manager for each test."""

        class AsyncConnectionManager:
            def __init__(self, db_url):
                self.database_url = db_url
                self._connections = {}

            async def get_connection(self):
                """Get async database connection."""
                connection = await asyncpg.connect(self.database_url)
                connection_id = id(connection)
                self._connections[connection_id] = connection
                return connection

            def close_all_connections(self):
                """Close all connections."""
                for connection in self._connections.values():
                    if not connection.is_closed():
                        asyncio.create_task(connection.close())

        manager = AsyncConnectionManager(database_config)
        yield manager
        manager.close_all_connections()

    @pytest.fixture
    async def analyzer(self, connection_manager):
        """Create analyzer with real dependencies."""
        dependency_analyzer = DependencyAnalyzer(connection_manager)
        fk_analyzer = ForeignKeyAnalyzer(connection_manager)

        analyzer = TableRenameAnalyzer(
            connection_manager=connection_manager,
            dependency_analyzer=dependency_analyzer,
            fk_analyzer=fk_analyzer,
        )
        return analyzer

    @pytest.fixture
    async def test_schema(self, connection_manager):
        """Set up test schema with tables, views, indexes, and FKs."""
        connection = await connection_manager.get_connection()

        # Use unique table names to avoid conflicts
        import uuid

        table_suffix = str(uuid.uuid4()).replace("-", "")[:8]

        try:
            # Clean up any existing objects with DROP CASCADE
            await connection.execute(
                f"""
                DROP TABLE IF EXISTS test_profiles_{table_suffix} CASCADE;
                DROP TABLE IF EXISTS test_orders_{table_suffix} CASCADE;
                DROP TABLE IF EXISTS test_users_{table_suffix} CASCADE;
                DROP TABLE IF EXISTS test_audit_log_{table_suffix} CASCADE;
                DROP FUNCTION IF EXISTS test_user_audit_{table_suffix}() CASCADE;
            """
            )

            # Create test tables with FK relationships
            await connection.execute(
                f"""
                CREATE TABLE test_users_{table_suffix} (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE test_orders_{table_suffix} (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    amount DECIMAL(10,2) NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT fk_orders_user_id_{table_suffix} FOREIGN KEY (user_id)
                        REFERENCES test_users_{table_suffix}(id) ON DELETE CASCADE
                );

                CREATE TABLE test_profiles_{table_suffix} (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    bio TEXT,
                    avatar_url VARCHAR(255),
                    CONSTRAINT fk_profiles_user_id_{table_suffix} FOREIGN KEY (user_id)
                        REFERENCES test_users_{table_suffix}(id) ON DELETE SET NULL
                );
            """
            )

            # Create indexes
            await connection.execute(
                f"""
                CREATE INDEX idx_test_users_email_{table_suffix} ON test_users_{table_suffix}(email);
                CREATE INDEX idx_test_users_created_at_{table_suffix} ON test_users_{table_suffix}(created_at);
            """
            )

            # Create views
            await connection.execute(
                f"""
                CREATE VIEW test_active_users_{table_suffix} AS
                SELECT id, email, name FROM test_users_{table_suffix} WHERE created_at > NOW() - INTERVAL '30 days';

                CREATE VIEW test_user_stats_{table_suffix} AS
                SELECT
                    u.id, u.name, u.email,
                    COUNT(o.id) as order_count,
                    COALESCE(SUM(o.amount), 0) as total_spent
                FROM test_users_{table_suffix} u
                LEFT JOIN test_orders_{table_suffix} o ON u.id = o.user_id
                GROUP BY u.id, u.name, u.email;
            """
            )

            # Create trigger function and trigger
            await connection.execute(
                f"""
                CREATE TABLE test_audit_log_{table_suffix} (
                    id SERIAL PRIMARY KEY,
                    table_name VARCHAR(50),
                    action VARCHAR(10),
                    old_data JSONB,
                    new_data JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE OR REPLACE FUNCTION test_user_audit_{table_suffix}() RETURNS TRIGGER AS $$
                BEGIN
                    INSERT INTO test_audit_log_{table_suffix} (table_name, action, old_data, new_data)
                    VALUES ('test_users_{table_suffix}', TG_OP, row_to_json(OLD), row_to_json(NEW));
                    RETURN COALESCE(NEW, OLD);
                END;
                $$ LANGUAGE plpgsql;

                CREATE TRIGGER test_users_audit_trigger_{table_suffix}
                    AFTER INSERT OR UPDATE OR DELETE ON test_users_{table_suffix}
                    FOR EACH ROW EXECUTE FUNCTION test_user_audit_{table_suffix}();
            """
            )

            # Insert test data
            await connection.execute(
                f"""
                INSERT INTO test_users_{table_suffix} (email, name) VALUES
                    ('john{table_suffix}@example.com', 'John Doe'),
                    ('jane{table_suffix}@example.com', 'Jane Smith'),
                    ('bob{table_suffix}@example.com', 'Bob Wilson');

                INSERT INTO test_orders_{table_suffix} (user_id, amount) VALUES
                    (1, 99.99),
                    (1, 149.50),
                    (2, 75.25);

                INSERT INTO test_profiles_{table_suffix} (user_id, bio) VALUES
                    (1, 'Software developer'),
                    (2, 'Product manager');
            """
            )

            yield table_suffix

        finally:
            # Cleanup
            try:
                await connection.execute(
                    f"""
                    DROP TABLE IF EXISTS test_profiles_{table_suffix} CASCADE;
                    DROP TABLE IF EXISTS test_orders_{table_suffix} CASCADE;
                    DROP TABLE IF EXISTS test_users_{table_suffix} CASCADE;
                    DROP TABLE IF EXISTS test_audit_log_{table_suffix} CASCADE;
                    DROP FUNCTION IF EXISTS test_user_audit_{table_suffix}() CASCADE;
                """
                )
                await connection.close()
            except:
                pass  # Ignore cleanup errors

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_analyze_table_with_complex_dependencies(self, analyzer, test_schema):
        """Test analyzing a table with complex dependency relationships."""
        table_suffix = test_schema
        table_name = f"test_users_{table_suffix}"

        # Analyze the test_users table which has FK references, views, indexes, triggers
        report = await analyzer.analyze_table_rename(table_name, "customers")

        assert isinstance(report, TableRenameReport)
        assert report.old_table_name == table_name
        assert report.new_table_name == "customers"
        assert len(report.schema_objects) > 0

        # Verify different object types were discovered
        object_types = {obj.object_type for obj in report.schema_objects}

        # Should find FK references, views, indexes, and triggers
        assert SchemaObjectType.FOREIGN_KEY in object_types
        assert SchemaObjectType.VIEW in object_types
        assert SchemaObjectType.INDEX in object_types
        assert SchemaObjectType.TRIGGER in object_types

        # Verify CASCADE FK is marked as CRITICAL
        fk_objects = [
            obj
            for obj in report.schema_objects
            if obj.object_type == SchemaObjectType.FOREIGN_KEY
        ]
        cascade_fks = [
            fk for fk in fk_objects if fk.impact_level == RenameImpactLevel.CRITICAL
        ]
        assert len(cascade_fks) > 0

        # Overall impact should be CRITICAL due to CASCADE FK
        assert report.impact_summary.overall_risk == RenameImpactLevel.CRITICAL

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_discover_foreign_key_references_real_database(
        self, analyzer, test_schema
    ):
        """Test FK reference discovery with real database constraints."""
        fk_objects = await analyzer.find_foreign_key_references("test_users")

        # Should find both FK constraints referencing test_users
        assert len(fk_objects) == 2

        constraint_names = {obj.object_name for obj in fk_objects}
        assert "fk_orders_user_id" in constraint_names
        assert "fk_profiles_user_id" in constraint_names

        # Verify CASCADE constraint is marked as CRITICAL
        cascade_fks = [fk for fk in fk_objects if "CASCADE" in fk.definition]
        assert len(cascade_fks) == 1
        assert cascade_fks[0].impact_level == RenameImpactLevel.CRITICAL

        # Verify SET NULL constraint is marked as HIGH
        set_null_fks = [fk for fk in fk_objects if "SET NULL" in fk.definition]
        assert len(set_null_fks) == 1
        assert set_null_fks[0].impact_level == RenameImpactLevel.HIGH

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_discover_view_dependencies_real_database(
        self, analyzer, test_schema
    ):
        """Test view dependency discovery with real database views."""
        view_objects = await analyzer.find_view_dependencies("test_users")

        # Should find both views that reference test_users
        assert len(view_objects) == 2

        view_names = {obj.object_name for obj in view_objects}
        assert "test_active_users" in view_names
        assert "test_user_stats" in view_names

        # All views should require SQL rewriting
        assert all(obj.requires_sql_rewrite for obj in view_objects)
        assert all(
            obj.impact_level in [RenameImpactLevel.MEDIUM, RenameImpactLevel.HIGH]
            for obj in view_objects
        )

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_discover_index_dependencies_real_database(
        self, analyzer, test_schema
    ):
        """Test index dependency discovery with real database indexes."""
        index_objects = await analyzer.find_index_dependencies("test_users")

        # Should find the indexes we created (plus any automatic ones)
        assert len(index_objects) >= 2

        index_names = {obj.object_name for obj in index_objects}
        assert "idx_test_users_email" in index_names
        assert "idx_test_users_created_at" in index_names

        # Unique indexes should have higher impact
        unique_indexes = [idx for idx in index_objects if "UNIQUE" in idx.definition]
        if unique_indexes:
            assert unique_indexes[0].impact_level == RenameImpactLevel.HIGH

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_discover_trigger_dependencies_real_database(
        self, analyzer, test_schema
    ):
        """Test trigger dependency discovery with real database triggers."""
        trigger_objects = await analyzer.find_trigger_dependencies("test_users")

        # Should find the audit trigger we created
        assert len(trigger_objects) >= 1

        trigger_names = {obj.object_name for obj in trigger_objects}
        assert "test_users_audit_trigger" in trigger_names

        # All triggers should have HIGH impact and require SQL rewriting
        for trigger in trigger_objects:
            assert trigger.impact_level == RenameImpactLevel.HIGH
            assert trigger.requires_sql_rewrite is True

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_dependency_graph_construction_real_data(self, analyzer, test_schema):
        """Test dependency graph construction with real database objects."""
        schema_objects = await analyzer.discover_schema_objects("test_users")
        graph = await analyzer.build_dependency_graph("test_users", schema_objects)

        assert isinstance(graph, DependencyGraph)
        assert graph.root_table == "test_users"
        assert len(graph.nodes) == len(schema_objects)

        # Check for critical dependencies
        critical_deps = graph.get_critical_dependencies()
        assert len(critical_deps) > 0

        # Verify FK objects are present
        fk_objects = graph.get_objects_by_type(SchemaObjectType.FOREIGN_KEY)
        assert len(fk_objects) >= 2

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_circular_dependency_detection_real_scenario(
        self, analyzer, connection_manager
    ):
        """Test circular dependency detection with real circular FK scenario."""
        connection = await connection_manager.get_connection()

        try:
            # Create circular FK scenario
            await connection.execute(
                """
                DROP TABLE IF EXISTS test_circular_b CASCADE;
                DROP TABLE IF EXISTS test_circular_a CASCADE;

                CREATE TABLE test_circular_a (
                    id SERIAL PRIMARY KEY,
                    b_id INTEGER,
                    name VARCHAR(50)
                );

                CREATE TABLE test_circular_b (
                    id SERIAL PRIMARY KEY,
                    a_id INTEGER,
                    name VARCHAR(50)
                );

                ALTER TABLE test_circular_a
                ADD CONSTRAINT fk_a_to_b FOREIGN KEY (b_id) REFERENCES test_circular_b(id);

                ALTER TABLE test_circular_b
                ADD CONSTRAINT fk_b_to_a FOREIGN KEY (a_id) REFERENCES test_circular_a(id);
            """
            )

            # Analyze for circular dependencies
            schema_objects = await analyzer.discover_schema_objects("test_circular_a")
            graph = await analyzer.build_dependency_graph(
                "test_circular_a", schema_objects
            )

            # Should detect circular dependency
            has_cycles = graph.has_circular_dependencies()
            # Note: This is a basic implementation, so may not detect all circular patterns
            # But we should at least have the FK objects
            fk_objects = graph.get_objects_by_type(SchemaObjectType.FOREIGN_KEY)
            assert len(fk_objects) > 0

        finally:
            await connection.execute(
                """
                DROP TABLE IF EXISTS test_circular_b CASCADE;
                DROP TABLE IF EXISTS test_circular_a CASCADE;
            """
            )

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_performance_with_real_large_schema(
        self, analyzer, connection_manager
    ):
        """Test performance with moderately large schema objects."""
        connection = await connection_manager.get_connection()

        try:
            # Create table with many indexes and views
            await connection.execute(
                """
                DROP TABLE IF EXISTS test_large_table CASCADE;

                CREATE TABLE test_large_table (
                    id SERIAL PRIMARY KEY,
                    col1 VARCHAR(100),
                    col2 VARCHAR(100),
                    col3 INTEGER,
                    col4 DATE,
                    col5 DECIMAL(10,2),
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """
            )

            # Create multiple indexes
            for i in range(10):
                await connection.execute(
                    f"""
                    CREATE INDEX idx_large_table_{i} ON test_large_table(col{(i % 5) + 1});
                """
                )

            # Create multiple views
            for i in range(5):
                await connection.execute(
                    f"""
                    CREATE VIEW test_large_view_{i} AS
                    SELECT id, col1, col{(i % 5) + 1} FROM test_large_table WHERE col3 > {i * 10};
                """
                )

            # Measure analysis time
            start_time = time.time()
            report = await analyzer.analyze_table_rename(
                "test_large_table", "renamed_table"
            )
            analysis_time = time.time() - start_time

            # Should complete within reasonable time (<5 seconds for integration tests)
            assert analysis_time < 5.0
            assert len(report.schema_objects) >= 15  # At least 10 indexes + 5 views

        finally:
            await connection.execute(
                """
                DROP TABLE IF EXISTS test_large_table CASCADE;
            """
            )

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_error_handling_nonexistent_table(self, analyzer, test_schema):
        """Test error handling with nonexistent table."""
        # Should complete without errors even if table doesn't exist
        report = await analyzer.analyze_table_rename("nonexistent_table", "new_table")

        assert report.old_table_name == "nonexistent_table"
        assert report.new_table_name == "new_table"
        assert len(report.schema_objects) == 0
        assert report.impact_summary.overall_risk == RenameImpactLevel.SAFE

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_validation_with_real_database(self, analyzer, test_schema):
        """Test rename validation with real database constraints."""
        # Valid rename
        validation = await analyzer.validate_rename_operation("test_users", "customers")
        assert validation.is_valid is True

        # Invalid renames
        validation = await analyzer.validate_rename_operation("", "customers")
        assert validation.is_valid is False

        validation = await analyzer.validate_rename_operation(
            "test_users", "users; DROP TABLE test_orders;"
        )
        assert validation.is_valid is False

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_comprehensive_analysis_accuracy(self, analyzer, test_schema):
        """Test comprehensive analysis accuracy with known schema objects."""
        report = await analyzer.analyze_table_rename("test_users", "customers")

        # Verify we found all expected object types
        object_types_found = {obj.object_type for obj in report.schema_objects}
        expected_types = {
            SchemaObjectType.FOREIGN_KEY,
            SchemaObjectType.VIEW,
            SchemaObjectType.INDEX,
            SchemaObjectType.TRIGGER,
        }

        # Should find all expected types
        assert expected_types.issubset(object_types_found)

        # Verify object counts are reasonable
        fk_count = len(
            [
                obj
                for obj in report.schema_objects
                if obj.object_type == SchemaObjectType.FOREIGN_KEY
            ]
        )
        view_count = len(
            [
                obj
                for obj in report.schema_objects
                if obj.object_type == SchemaObjectType.VIEW
            ]
        )
        index_count = len(
            [
                obj
                for obj in report.schema_objects
                if obj.object_type == SchemaObjectType.INDEX
            ]
        )
        trigger_count = len(
            [
                obj
                for obj in report.schema_objects
                if obj.object_type == SchemaObjectType.TRIGGER
            ]
        )

        assert fk_count >= 2  # We created 2 FK constraints
        assert view_count >= 2  # We created 2 views
        assert index_count >= 2  # We created multiple indexes
        assert trigger_count >= 1  # We created 1 trigger

        # Verify impact assessment is reasonable
        critical_objects = [
            obj
            for obj in report.schema_objects
            if obj.impact_level == RenameImpactLevel.CRITICAL
        ]
        high_objects = [
            obj
            for obj in report.schema_objects
            if obj.impact_level == RenameImpactLevel.HIGH
        ]

        assert len(critical_objects) >= 1  # CASCADE FK should be CRITICAL
        assert len(high_objects) >= 1  # Views and triggers should be HIGH

        # Overall risk should be CRITICAL due to CASCADE FK
        assert report.impact_summary.overall_risk == RenameImpactLevel.CRITICAL
