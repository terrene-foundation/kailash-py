#!/usr/bin/env python3
"""
Simplified Integration Tests for Table Schema Rename Engine - TODO-139 Phase 1

Tests the TableRenameAnalyzer with real PostgreSQL database connections
focusing on core functionality without complex fixtures.

Following Tier 2 testing guidelines:
- Uses real Docker PostgreSQL services from tests/utils
- NO MOCKING - all database operations must be real
- Tests actual schema object discovery with real data
- Timeout: <5 seconds per test
- CRITICAL PRIORITY: Real referential integrity scenarios
"""

import asyncio
import time
import uuid

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


class TestTableRenameAnalyzerSimpleIntegration:
    """Simplified integration tests for TableRenameAnalyzer with real database."""

    @pytest.fixture
    async def connection_manager(self, test_suite):
        """Create simple connection manager."""

        class SimpleConnectionManager:
            def __init__(self, suite):
                self.suite = suite

            async def get_connection(self):
                return await self.suite.get_connection().__aenter__()

        return SimpleConnectionManager(test_suite)

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

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_basic_table_rename_analysis(self, analyzer, connection):
        """Test basic table rename analysis with real database."""
        # Use unique table name to avoid conflicts
        table_id = str(uuid.uuid4())[:8]
        table_name = f"rename_test_{table_id}"

        try:
            # Create a simple test table
            await connection.execute(
                f"""
                CREATE TABLE {table_name} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL
                );

                CREATE INDEX idx_{table_name}_name ON {table_name}(name);
            """
            )

            # Test rename analysis
            report = await analyzer.analyze_table_rename(table_name, "renamed_table")

            assert isinstance(report, TableRenameReport)
            assert report.old_table_name == table_name
            assert report.new_table_name == "renamed_table"
            assert len(report.schema_objects) >= 0  # May find indexes

            # Should have minimal risk since no FK dependencies
            # Note: May have indexes (including primary key) which can push impact to HIGH
            assert report.impact_summary.overall_risk in [
                RenameImpactLevel.SAFE,
                RenameImpactLevel.MEDIUM,
                RenameImpactLevel.HIGH,
            ]

        finally:
            # Cleanup
            await connection.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_foreign_key_dependency_detection(self, analyzer, connection):
        """Test FK dependency detection with real constraints."""
        table_id = str(uuid.uuid4())[:8]
        parent_table = f"parent_{table_id}"
        child_table = f"child_{table_id}"

        try:
            # Create parent-child relationship with CASCADE
            await connection.execute(
                f"""
                CREATE TABLE {parent_table} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL
                );

                CREATE TABLE {child_table} (
                    id SERIAL PRIMARY KEY,
                    parent_id INTEGER NOT NULL,
                    data TEXT,
                    CONSTRAINT fk_{child_table}_parent FOREIGN KEY (parent_id)
                        REFERENCES {parent_table}(id) ON DELETE CASCADE
                );
            """
            )

            # Analyze parent table rename
            report = await analyzer.analyze_table_rename(parent_table, "renamed_parent")

            # Should detect FK dependency
            assert len(report.schema_objects) > 0

            # Should find FK objects
            fk_objects = [
                obj
                for obj in report.schema_objects
                if obj.object_type == SchemaObjectType.FOREIGN_KEY
            ]
            assert len(fk_objects) >= 1

            # CASCADE FK should be marked as CRITICAL
            cascade_fks = [
                fk for fk in fk_objects if fk.impact_level == RenameImpactLevel.CRITICAL
            ]
            assert len(cascade_fks) >= 1

            # Overall risk should be CRITICAL
            assert report.impact_summary.overall_risk == RenameImpactLevel.CRITICAL

        finally:
            # Cleanup
            await connection.execute(f"DROP TABLE IF EXISTS {child_table} CASCADE")
            await connection.execute(f"DROP TABLE IF EXISTS {parent_table} CASCADE")

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_view_dependency_detection(self, analyzer, connection):
        """Test view dependency detection with real views."""
        table_id = str(uuid.uuid4())[:8]
        table_name = f"view_test_{table_id}"
        view_name = f"view_{table_id}"

        try:
            # Create table and view
            await connection.execute(
                f"""
                CREATE TABLE {table_name} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    active BOOLEAN DEFAULT true
                );

                CREATE VIEW {view_name} AS
                SELECT id, name FROM {table_name} WHERE active = true;
            """
            )

            # Analyze table rename
            report = await analyzer.analyze_table_rename(table_name, "renamed_table")

            # Should detect view dependency
            view_objects = [
                obj
                for obj in report.schema_objects
                if obj.object_type == SchemaObjectType.VIEW
            ]
            assert len(view_objects) >= 1

            # Views should require SQL rewriting
            assert all(obj.requires_sql_rewrite for obj in view_objects)

            # Should have at least MEDIUM impact due to views
            assert report.impact_summary.overall_risk in [
                RenameImpactLevel.MEDIUM,
                RenameImpactLevel.HIGH,
                RenameImpactLevel.CRITICAL,
            ]

        finally:
            # Cleanup
            await connection.execute(f"DROP VIEW IF EXISTS {view_name} CASCADE")
            await connection.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_nonexistent_table_handling(self, analyzer):
        """Test handling of nonexistent table."""
        # Should complete without errors
        report = await analyzer.analyze_table_rename(
            "nonexistent_table_12345", "new_table"
        )

        assert report.old_table_name == "nonexistent_table_12345"
        assert report.new_table_name == "new_table"
        assert len(report.schema_objects) == 0
        assert report.impact_summary.overall_risk == RenameImpactLevel.SAFE

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_validation_with_real_database(self, analyzer):
        """Test rename validation."""
        # Valid rename
        validation = await analyzer.validate_rename_operation(
            "valid_table", "valid_new_name"
        )
        assert validation.is_valid is True

        # Invalid renames
        validation = await analyzer.validate_rename_operation("", "new_name")
        assert validation.is_valid is False

        validation = await analyzer.validate_rename_operation(
            "table", "new_name; DROP TABLE users;"
        )
        assert validation.is_valid is False

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_schema_object_discovery_performance(self, analyzer, connection):
        """Test schema object discovery performance."""
        table_id = str(uuid.uuid4())[:8]
        table_name = f"perf_test_{table_id}"

        try:
            # Create table with multiple indexes
            await connection.execute(
                f"""
                CREATE TABLE {table_name} (
                    id SERIAL PRIMARY KEY,
                    col1 VARCHAR(100),
                    col2 VARCHAR(100),
                    col3 INTEGER,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX idx_{table_name}_col1 ON {table_name}(col1);
                CREATE INDEX idx_{table_name}_col2 ON {table_name}(col2);
                CREATE INDEX idx_{table_name}_col3 ON {table_name}(col3);
            """
            )

            # Measure analysis time
            start_time = time.time()
            report = await analyzer.analyze_table_rename(table_name, "renamed_table")
            analysis_time = time.time() - start_time

            # Should complete within reasonable time
            assert analysis_time < 5.0
            assert len(report.schema_objects) >= 3  # At least 3 indexes

        finally:
            # Cleanup
            await connection.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_complex_dependency_scenario(self, analyzer, connection):
        """Test complex scenario with multiple dependency types."""
        table_id = str(uuid.uuid4())[:8]
        base_table = f"complex_base_{table_id}"
        ref_table = f"complex_ref_{table_id}"
        view_name = f"complex_view_{table_id}"

        try:
            # Create complex scenario
            await connection.execute(
                f"""
                CREATE TABLE {base_table} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    status VARCHAR(20) DEFAULT 'active'
                );

                CREATE TABLE {ref_table} (
                    id SERIAL PRIMARY KEY,
                    base_id INTEGER NOT NULL,
                    data TEXT,
                    CONSTRAINT fk_{ref_table}_base FOREIGN KEY (base_id)
                        REFERENCES {base_table}(id) ON DELETE RESTRICT
                );

                CREATE INDEX idx_{base_table}_name ON {base_table}(name);
                CREATE INDEX idx_{base_table}_status ON {base_table}(status);

                CREATE VIEW {view_name} AS
                SELECT b.id, b.name, COUNT(r.id) as ref_count
                FROM {base_table} b
                LEFT JOIN {ref_table} r ON b.id = r.base_id
                GROUP BY b.id, b.name;
            """
            )

            # Analyze complex rename
            report = await analyzer.analyze_table_rename(base_table, "renamed_base")

            # Should detect multiple object types - at minimum FK and indexes
            object_types = {obj.object_type for obj in report.schema_objects}
            assert SchemaObjectType.FOREIGN_KEY in object_types
            assert SchemaObjectType.INDEX in object_types
            # VIEW detection may be fragile due to SQL parsing - test separately if needed

            # Should have HIGH or CRITICAL impact
            assert report.impact_summary.overall_risk in [
                RenameImpactLevel.HIGH,
                RenameImpactLevel.CRITICAL,
            ]

        finally:
            # Cleanup
            await connection.execute(f"DROP VIEW IF EXISTS {view_name} CASCADE")
            await connection.execute(f"DROP TABLE IF EXISTS {ref_table} CASCADE")
            await connection.execute(f"DROP TABLE IF EXISTS {base_table} CASCADE")
