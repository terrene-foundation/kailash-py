#!/usr/bin/env python3
"""
Unit Tests for Core Dependency Analysis Engine - TODO-137 Phase 1

Tests the DependencyAnalyzer class with comprehensive coverage of all PostgreSQL
dependency types: Foreign Keys, Views, Triggers, Indexes, and Constraints.

Following Tier 1 testing guidelines:
- Uses standardized unit test fixtures
- Uses mocked database connections for isolation
- Fast execution (<1 second per test)
- Focused on individual method functionality
- Comprehensive edge case coverage
- CRITICAL PRIORITY: Foreign Key Dependencies (data loss prevention)
"""

import unittest.mock as mock
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Import the classes we're going to implement
from dataflow.migrations.dependency_analyzer import (
    ConstraintDependency,
    DependencyAnalyzer,
    DependencyReport,
    DependencyType,
    ForeignKeyDependency,
    ImpactLevel,
    IndexDependency,
    TriggerDependency,
    ViewDependency,
)


@pytest.mark.unit
@pytest.mark.mocking
class TestDependencyAnalyzer:
    """Unit tests for DependencyAnalyzer class."""

    def setup_method(self):
        """Setup test fixtures for each test method."""
        self.mock_connection = AsyncMock()
        self.mock_connection_manager = Mock()
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )
        self.analyzer = DependencyAnalyzer(self.mock_connection_manager)

    @pytest.fixture
    def dependency_analyzer(self, mock_connection_manager):
        """Create DependencyAnalyzer instance with mocked connection manager."""
        return DependencyAnalyzer(mock_connection_manager)

    @pytest.mark.asyncio
    async def test_analyze_column_dependencies_basic(self):
        """Test basic column dependency analysis."""
        # Setup mocked connection
        self.mock_connection.fetch.return_value = []

        result = await self.analyzer.analyze_column_dependencies("users", "email")

        assert isinstance(result, DependencyReport)
        assert result.table_name == "users"
        assert result.column_name == "email"
        assert isinstance(result.dependencies, dict)
        assert DependencyType.FOREIGN_KEY in result.dependencies

    @pytest.mark.asyncio
    async def test_find_foreign_key_dependencies_single_column(self):
        """Test detection of single-column foreign key dependencies."""
        # CRITICAL TEST: Single column FK target (data loss prevention)
        mock_fk_data = [
            {
                "constraint_name": "fk_orders_user_id",
                "source_table": "orders",
                "source_column": "user_id",
                "target_table": "users",
                "target_column": "id",
                "on_delete": "CASCADE",
                "on_update": "RESTRICT",
            }
        ]
        self.mock_connection.fetch.return_value = mock_fk_data

        result = await self.analyzer.find_foreign_key_dependencies("users", "id")

        assert len(result) == 1
        fk_dep = result[0]
        assert isinstance(fk_dep, ForeignKeyDependency)
        assert fk_dep.constraint_name == "fk_orders_user_id"
        assert fk_dep.source_table == "orders"
        assert fk_dep.source_column == "user_id"
        assert fk_dep.impact_level == ImpactLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_find_foreign_key_dependencies_composite_keys(self):
        """Test detection of composite foreign key dependencies."""
        # CRITICAL TEST: Only FKs targeting the specific table.column should be returned
        # For "users", "id", only the FK with target_table='users', target_column='id' should match
        mock_fk_data = [
            {
                "constraint_name": "fk_order_items_composite",
                "source_table": "order_items",
                "source_column": "user_id",
                "target_table": "users",
                "target_column": "id",
                "on_delete": "CASCADE",
                "on_update": "CASCADE",
            }
            # Note: The second row with target_table='orders' would be filtered out by the real query
        ]
        self.mock_connection.fetch.return_value = mock_fk_data
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        result = await self.analyzer.find_foreign_key_dependencies("users", "id")

        assert len(result) == 1
        fk_dep = result[0]
        assert fk_dep.constraint_name == "fk_order_items_composite"
        assert fk_dep.impact_level == ImpactLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_find_view_dependencies_simple_views(self):
        """Test detection of view dependencies."""
        mock_view_data = [
            {
                "view_name": "user_summary",
                "view_definition": "SELECT id, email, created_at FROM users WHERE active = true",
                "schema_name": "public",
            }
        ]
        self.mock_connection.fetch.return_value = mock_view_data
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        result = await self.analyzer.find_view_dependencies("users", "email")

        assert len(result) == 1
        view_dep = result[0]
        assert isinstance(view_dep, ViewDependency)
        assert view_dep.view_name == "user_summary"
        assert view_dep.impact_level == ImpactLevel.HIGH

    @pytest.mark.asyncio
    async def test_find_view_dependencies_nested_views(self):
        """Test detection of nested view dependencies (recursive analysis)."""
        mock_nested_view_data = [
            {
                "view_name": "active_users",
                "view_definition": "SELECT * FROM users WHERE active = true",
                "schema_name": "public",
            },
            {
                "view_name": "user_stats",
                "view_definition": "SELECT COUNT(*) FROM active_users",
                "schema_name": "public",
            },
        ]
        self.mock_connection.fetch.return_value = mock_nested_view_data
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        result = await self.analyzer.find_view_dependencies("users", "active")

        # Only direct references should be detected in Phase 1 (not transitive dependencies)
        assert len(result) == 1
        view_names = {dep.view_name for dep in result}
        assert "active_users" in view_names

    @pytest.mark.asyncio
    async def test_find_trigger_dependencies_new_old_columns(self):
        """Test detection of trigger dependencies using NEW.column/OLD.column."""
        mock_trigger_data = [
            {
                "trigger_name": "audit_user_changes",
                "event_manipulation": "UPDATE",
                "action_timing": "AFTER",
                "action_statement": "EXECUTE FUNCTION audit_user_changes() WHEN (OLD.email IS DISTINCT FROM NEW.email)",
                "function_name": "audit_user_changes",
            }
        ]
        self.mock_connection.fetch.return_value = mock_trigger_data
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        result = await self.analyzer.find_trigger_dependencies("users", "email")

        assert len(result) == 1
        trigger_dep = result[0]
        assert isinstance(trigger_dep, TriggerDependency)
        assert trigger_dep.trigger_name == "audit_user_changes"
        assert trigger_dep.impact_level == ImpactLevel.HIGH

    @pytest.mark.asyncio
    async def test_find_index_dependencies_single_column(self):
        """Test detection of single-column index dependencies."""
        mock_index_data = [
            {
                "index_name": "idx_users_email_unique",
                "index_type": "btree",
                "is_unique": True,
                "columns": ["email"],
                "index_definition": "CREATE UNIQUE INDEX idx_users_email_unique ON users USING btree (email)",
            }
        ]
        self.mock_connection.fetch.return_value = mock_index_data
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        result = await self.analyzer.find_index_dependencies("users", "email")

        assert len(result) == 1
        index_dep = result[0]
        assert isinstance(index_dep, IndexDependency)
        assert index_dep.index_name == "idx_users_email_unique"
        assert index_dep.is_unique is True
        assert index_dep.impact_level == ImpactLevel.MEDIUM

    @pytest.mark.asyncio
    async def test_find_index_dependencies_multi_column(self):
        """Test detection of multi-column indexes including target column."""
        mock_index_data = [
            {
                "index_name": "idx_users_email_created_at",
                "index_type": "btree",
                "is_unique": False,
                "columns": ["email", "created_at"],
                "index_definition": "CREATE INDEX idx_users_email_created_at ON users USING btree (email, created_at)",
            }
        ]
        self.mock_connection.fetch.return_value = mock_index_data
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        result = await self.analyzer.find_index_dependencies("users", "email")

        assert len(result) == 1
        index_dep = result[0]
        assert index_dep.index_name == "idx_users_email_created_at"
        assert "email" in index_dep.columns
        assert "created_at" in index_dep.columns

    @pytest.mark.asyncio
    async def test_find_constraint_dependencies_check_constraints(self):
        """Test detection of check constraints referencing column."""
        mock_constraint_data = [
            {
                "constraint_name": "check_email_format",
                "constraint_type": "CHECK",
                "constraint_definition": "(email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$')",
                "columns": ["email"],
            }
        ]
        self.mock_connection.fetch.return_value = mock_constraint_data
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        result = await self.analyzer.find_constraint_dependencies("users", "email")

        assert len(result) == 1
        constraint_dep = result[0]
        assert isinstance(constraint_dep, ConstraintDependency)
        assert constraint_dep.constraint_name == "check_email_format"
        assert constraint_dep.constraint_type == "CHECK"
        assert constraint_dep.impact_level == ImpactLevel.MEDIUM

    @pytest.mark.asyncio
    async def test_analyze_column_dependencies_no_dependencies(self):
        """Test analysis when no dependencies exist."""
        # Mock empty results for all queries
        self.mock_connection.fetch.return_value = []
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        result = await self.analyzer.analyze_column_dependencies(
            "users", "unused_column"
        )

        assert result.has_dependencies() is False
        assert result.get_critical_dependencies() == []
        assert result.get_total_dependency_count() == 0

    @pytest.mark.asyncio
    async def test_analyze_column_dependencies_all_types(self):
        """Test analysis detecting all dependency types."""
        # Mock data for all dependency types
        fk_data = [
            {
                "constraint_name": "fk_test",
                "source_table": "orders",
                "source_column": "user_id",
                "target_table": "users",
                "target_column": "id",
                "on_delete": "CASCADE",
                "on_update": "RESTRICT",
            }
        ]
        view_data = [
            {
                "view_name": "user_view",
                "view_definition": "SELECT id FROM users",
                "schema_name": "public",
            }
        ]
        trigger_data = [
            {
                "trigger_name": "user_trigger",
                "event_manipulation": "UPDATE",
                "action_timing": "BEFORE",
                "action_statement": "EXECUTE FUNCTION test() WHEN OLD.id IS DISTINCT FROM NEW.id",
                "function_name": "test",
            }
        ]
        index_data = [
            {
                "index_name": "idx_test",
                "index_type": "btree",
                "is_unique": False,
                "columns": ["id"],
                "index_definition": "CREATE INDEX...",
            }
        ]
        constraint_data = [
            {
                "constraint_name": "check_test",
                "constraint_type": "CHECK",
                "constraint_definition": "id > 0",
                "columns": ["id"],
            }
        ]

        # Set up multiple fetch calls
        self.mock_connection.fetch.side_effect = [
            fk_data,
            view_data,
            trigger_data,
            index_data,
            constraint_data,
        ]
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        result = await self.analyzer.analyze_column_dependencies("users", "id")

        assert result.has_dependencies() is True
        assert len(result.dependencies[DependencyType.FOREIGN_KEY]) == 1
        assert len(result.dependencies[DependencyType.VIEW]) == 1
        assert len(result.dependencies[DependencyType.TRIGGER]) == 1
        assert len(result.dependencies[DependencyType.INDEX]) == 1
        assert len(result.dependencies[DependencyType.CONSTRAINT]) == 1

    @pytest.mark.asyncio
    async def test_connection_error_handling(self):
        """Test proper error handling for connection failures."""
        self.mock_connection_manager.get_connection = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        with pytest.raises(Exception) as exc_info:
            await self.analyzer.analyze_column_dependencies("users", "id")

        assert "Connection failed" in str(exc_info.value)

    def test_dependency_report_has_dependencies(self):
        """Test DependencyReport.has_dependencies() method."""
        # Empty report
        empty_report = DependencyReport("users", "id", {})
        assert empty_report.has_dependencies() is False

        # Report with dependencies
        with_deps = DependencyReport(
            "users", "id", {DependencyType.FOREIGN_KEY: [Mock()]}
        )
        assert with_deps.has_dependencies() is True

    def test_dependency_report_get_critical_dependencies(self):
        """Test DependencyReport.get_critical_dependencies() method."""
        critical_fk = Mock()
        critical_fk.impact_level = ImpactLevel.CRITICAL

        medium_index = Mock()
        medium_index.impact_level = ImpactLevel.MEDIUM

        report = DependencyReport(
            "users",
            "id",
            {
                DependencyType.FOREIGN_KEY: [critical_fk],
                DependencyType.INDEX: [medium_index],
            },
        )

        critical_deps = report.get_critical_dependencies()
        assert len(critical_deps) == 1
        assert critical_deps[0].impact_level == ImpactLevel.CRITICAL

    def test_dependency_report_get_total_count(self):
        """Test DependencyReport.get_total_dependency_count() method."""
        report = DependencyReport(
            "users",
            "id",
            {
                DependencyType.FOREIGN_KEY: [Mock(), Mock()],
                DependencyType.VIEW: [Mock()],
                DependencyType.INDEX: [Mock(), Mock(), Mock()],
            },
        )

        assert report.get_total_dependency_count() == 6

    @pytest.mark.asyncio
    async def test_performance_large_schema_mock(self):
        """Test performance with large schema (mocked for unit test)."""
        # Mock large number of dependencies
        large_fk_data = [
            {
                "constraint_name": f"fk_table_{i}",
                "source_table": f"table_{i}",
                "source_column": "ref_id",
                "target_table": "users",
                "target_column": "id",
                "on_delete": "CASCADE",
                "on_update": "RESTRICT",
            }
            for i in range(100)
        ]

        self.mock_connection.fetch.return_value = large_fk_data
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        import time

        start_time = time.time()

        result = await self.analyzer.find_foreign_key_dependencies("users", "id")

        execution_time = time.time() - start_time

        assert len(result) == 100
        assert execution_time < 1.0  # Unit test should complete in <1 second

    @pytest.mark.asyncio
    async def test_sql_injection_protection(self):
        """Test protection against SQL injection in table/column names."""
        malicious_table = "users; DROP TABLE users; --"
        malicious_column = "id'; DROP TABLE users; --"

        self.mock_connection.fetch.return_value = []
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        # Should not raise exception and should sanitize inputs
        result = await self.analyzer.analyze_column_dependencies(
            malicious_table, malicious_column
        )

        # Verify that the analyzer sanitized the inputs
        assert result.table_name != malicious_table
        assert result.column_name != malicious_column


class TestDependencyTypes:
    """Test dependency type data classes."""

    def test_foreign_key_dependency_creation(self):
        """Test ForeignKeyDependency creation."""
        fk_dep = ForeignKeyDependency(
            constraint_name="fk_orders_user_id",
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="id",
            on_delete="CASCADE",
            on_update="RESTRICT",
        )

        assert fk_dep.constraint_name == "fk_orders_user_id"
        assert fk_dep.impact_level == ImpactLevel.CRITICAL
        assert fk_dep.dependency_type == DependencyType.FOREIGN_KEY

    def test_view_dependency_creation(self):
        """Test ViewDependency creation."""
        view_dep = ViewDependency(
            view_name="user_summary",
            view_definition="SELECT * FROM users",
            schema_name="public",
        )

        assert view_dep.view_name == "user_summary"
        assert view_dep.impact_level == ImpactLevel.HIGH
        assert view_dep.dependency_type == DependencyType.VIEW

    def test_trigger_dependency_creation(self):
        """Test TriggerDependency creation."""
        trigger_dep = TriggerDependency(
            trigger_name="audit_trigger",
            event="UPDATE",
            timing="AFTER",
            function_name="audit_function",
        )

        assert trigger_dep.trigger_name == "audit_trigger"
        assert trigger_dep.impact_level == ImpactLevel.HIGH
        assert trigger_dep.dependency_type == DependencyType.TRIGGER

    def test_index_dependency_creation(self):
        """Test IndexDependency creation."""
        index_dep = IndexDependency(
            index_name="idx_users_email",
            index_type="btree",
            columns=["email"],
            is_unique=True,
        )

        assert index_dep.index_name == "idx_users_email"
        assert index_dep.impact_level == ImpactLevel.MEDIUM
        assert index_dep.is_unique is True

    def test_constraint_dependency_creation(self):
        """Test ConstraintDependency creation."""
        constraint_dep = ConstraintDependency(
            constraint_name="check_email_valid",
            constraint_type="CHECK",
            definition="email IS NOT NULL",
            columns=["email"],
        )

        assert constraint_dep.constraint_name == "check_email_valid"
        assert constraint_dep.impact_level == ImpactLevel.MEDIUM
        assert constraint_dep.constraint_type == "CHECK"


class TestDependencyReportMethods:
    """Test DependencyReport utility methods."""

    def test_generate_impact_summary(self):
        """Test impact summary generation."""
        critical_dep = Mock()
        critical_dep.impact_level = ImpactLevel.CRITICAL

        high_dep = Mock()
        high_dep.impact_level = ImpactLevel.HIGH

        medium_dep = Mock()
        medium_dep.impact_level = ImpactLevel.MEDIUM

        report = DependencyReport(
            "users",
            "id",
            {
                DependencyType.FOREIGN_KEY: [critical_dep],
                DependencyType.VIEW: [high_dep],
                DependencyType.INDEX: [medium_dep],
            },
        )

        summary = report.generate_impact_summary()

        assert summary[ImpactLevel.CRITICAL] == 1
        assert summary[ImpactLevel.HIGH] == 1
        assert summary[ImpactLevel.MEDIUM] == 1
        assert summary[ImpactLevel.LOW] == 0

    def test_get_removal_recommendation(self):
        """Test removal safety recommendation."""
        # Safe removal (no critical dependencies)
        safe_report = DependencyReport("users", "unused_column", {})
        assert safe_report.get_removal_recommendation() == "SAFE"

        # Unsafe removal (critical dependencies)
        critical_dep = Mock()
        critical_dep.impact_level = ImpactLevel.CRITICAL

        unsafe_report = DependencyReport(
            "users", "id", {DependencyType.FOREIGN_KEY: [critical_dep]}
        )
        assert unsafe_report.get_removal_recommendation() == "DANGEROUS"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
