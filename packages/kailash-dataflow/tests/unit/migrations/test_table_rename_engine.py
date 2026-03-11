#!/usr/bin/env python3
"""
Unit Tests for Table Schema Rename Engine - TODO-139 Phase 1

Tests the TableRenameAnalyzer and related classes for table renaming operations
with comprehensive coverage of schema object discovery and dependency analysis.

Following Tier 1 testing guidelines:
- Uses mocked database connections for isolation
- Fast execution (<1 second per test)
- Focused on individual method functionality
- Comprehensive edge case coverage
- CRITICAL PRIORITY: Referential integrity during renames
"""

import unittest.mock as mock
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Import the classes we're going to implement
from dataflow.migrations.table_rename_analyzer import (
    DependencyGraph,
    RenameImpactLevel,
    RenameOperation,
    RenameValidation,
    SchemaObject,
    SchemaObjectType,
    TableRenameAnalyzer,
    TableRenameError,
    TableRenameReport,
)


class TestTableRenameAnalyzer:
    """Unit tests for TableRenameAnalyzer class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_connection_manager = Mock()
        self.mock_connection = AsyncMock()
        self.mock_dependency_analyzer = Mock()
        self.mock_fk_analyzer = Mock()

        self.analyzer = TableRenameAnalyzer(
            connection_manager=self.mock_connection_manager,
            dependency_analyzer=self.mock_dependency_analyzer,
            fk_analyzer=self.mock_fk_analyzer,
        )

    @pytest.mark.asyncio
    async def test_analyze_table_rename_basic(self):
        """Test basic table rename analysis."""
        # Mock database responses
        self.mock_connection.fetch.return_value = []
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        result = await self.analyzer.analyze_table_rename("users", "customers")

        assert isinstance(result, TableRenameReport)
        assert result.old_table_name == "users"
        assert result.new_table_name == "customers"
        assert isinstance(result.schema_objects, list)

    @pytest.mark.asyncio
    async def test_discover_schema_objects_comprehensive(self):
        """Test comprehensive schema object discovery."""
        # Mock responses for all schema object types
        mock_fk_data = [
            {
                "constraint_name": "fk_orders_user_id",
                "source_table": "orders",
                "source_column": "user_id",
                "target_table": "users",
                "target_column": "id",
            }
        ]

        mock_view_data = [
            {
                "viewname": "user_summary",
                "definition": "SELECT * FROM users WHERE active = true",
                "schemaname": "public",
            }
        ]

        mock_index_data = [
            {
                "indexname": "idx_users_email",
                "tablename": "users",
                "indexdef": "CREATE INDEX idx_users_email ON users(email)",
            }
        ]

        mock_trigger_data = [
            {
                "trigger_name": "users_audit_trigger",
                "event_manipulation": "INSERT",
                "action_timing": "AFTER",
                "action_statement": "EXECUTE FUNCTION log_user_changes()",
            }
        ]

        # Set up fetch responses for different queries (5 calls total)
        # 1. find_foreign_key_references (incoming FK)
        # 2. find_outgoing_foreign_key_references (outgoing FK)
        # 3. find_view_dependencies
        # 4. find_index_dependencies
        # 5. find_trigger_dependencies
        fetch_side_effects = [
            mock_fk_data,  # Incoming foreign keys
            [],  # Outgoing foreign keys (empty)
            mock_view_data,  # Views
            mock_index_data,  # Indexes
            mock_trigger_data,  # Triggers
        ]

        self.mock_connection.fetch.side_effect = fetch_side_effects
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        result = await self.analyzer.discover_schema_objects("users")

        # Verify all object types discovered
        assert len(result) == 4

        # Verify foreign keys
        fk_objects = [
            obj for obj in result if obj.object_type == SchemaObjectType.FOREIGN_KEY
        ]
        assert len(fk_objects) == 1
        assert fk_objects[0].object_name == "fk_orders_user_id"

        # Verify views
        view_objects = [
            obj for obj in result if obj.object_type == SchemaObjectType.VIEW
        ]
        assert len(view_objects) == 1
        assert view_objects[0].object_name == "user_summary"

        # Verify indexes
        index_objects = [
            obj for obj in result if obj.object_type == SchemaObjectType.INDEX
        ]
        assert len(index_objects) == 1
        assert index_objects[0].object_name == "idx_users_email"

        # Verify triggers
        trigger_objects = [
            obj for obj in result if obj.object_type == SchemaObjectType.TRIGGER
        ]
        assert len(trigger_objects) == 1
        assert trigger_objects[0].object_name == "users_audit_trigger"

    @pytest.mark.asyncio
    async def test_build_dependency_graph(self):
        """Test dependency graph construction for rename operations."""
        # Mock schema objects with dependencies - use CASCADE to ensure CRITICAL level
        schema_objects = [
            SchemaObject(
                object_name="fk_orders_user_id",
                object_type=SchemaObjectType.FOREIGN_KEY,
                definition="FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",
                depends_on_table="users",
                impact_level=RenameImpactLevel.HIGH,  # Will be overridden by __post_init__
            ),
            SchemaObject(
                object_name="user_summary",
                object_type=SchemaObjectType.VIEW,
                definition="SELECT * FROM users WHERE active = true",
                depends_on_table="users",
                impact_level=RenameImpactLevel.HIGH,
            ),
        ]

        graph = await self.analyzer.build_dependency_graph("users", schema_objects)

        assert isinstance(graph, DependencyGraph)
        assert graph.root_table == "users"
        assert len(graph.nodes) == 2

        # Verify critical dependencies are identified
        critical_nodes = graph.get_critical_dependencies()
        assert len(critical_nodes) == 1
        assert critical_nodes[0].object_type == SchemaObjectType.FOREIGN_KEY

    @pytest.mark.asyncio
    async def test_calculate_rename_impact(self):
        """Test rename impact calculation."""
        # Create schema objects with explicit impact levels that won't be overridden
        schema_objects = [
            SchemaObject(
                object_name="fk_orders_user_id",
                object_type=SchemaObjectType.FOREIGN_KEY,
                definition="FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",  # This will trigger CRITICAL
                impact_level=RenameImpactLevel.HIGH,  # Will be overridden by __post_init__
            ),
            SchemaObject(
                object_name="user_summary",
                object_type=SchemaObjectType.VIEW,
                impact_level=RenameImpactLevel.HIGH,
            ),
            SchemaObject(
                object_name="idx_users_email",
                object_type=SchemaObjectType.INDEX,
                impact_level=RenameImpactLevel.MEDIUM,
            ),
        ]

        impact = self.analyzer.calculate_rename_impact(schema_objects)

        assert impact.overall_risk == RenameImpactLevel.CRITICAL
        assert impact.critical_count == 1
        assert impact.high_count == 1
        assert impact.medium_count == 1
        assert impact.total_objects == 3

    @pytest.mark.asyncio
    async def test_validate_rename_operation(self):
        """Test rename operation validation."""
        # Test valid rename
        validation = await self.analyzer.validate_rename_operation("users", "customers")
        assert isinstance(validation, RenameValidation)
        assert validation.is_valid is True

        # Test invalid names - these should return invalid validation, not raise exceptions
        validation = await self.analyzer.validate_rename_operation("", "customers")
        assert validation.is_valid is False
        assert len(validation.violations) > 0

        validation = await self.analyzer.validate_rename_operation("users", "")
        assert validation.is_valid is False
        assert len(validation.violations) > 0

        # Test SQL injection attempts - should return invalid validation
        validation = await self.analyzer.validate_rename_operation(
            "users", "customers; DROP TABLE users;"
        )
        assert validation.is_valid is False
        assert len(validation.violations) > 0

    @pytest.mark.asyncio
    async def test_find_foreign_key_references(self):
        """Test finding foreign key references to target table."""
        mock_fk_data = [
            {
                "constraint_name": "fk_orders_user_id",
                "source_table": "orders",
                "source_column": "user_id",
                "target_table": "users",
                "target_column": "id",
                "delete_rule": "CASCADE",
                "update_rule": "RESTRICT",
                "constraint_definition": "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",
            },
            {
                "constraint_name": "fk_profiles_user_id",
                "source_table": "profiles",
                "source_column": "user_id",
                "target_table": "users",
                "target_column": "id",
                "delete_rule": "SET NULL",
                "update_rule": "CASCADE",
                "constraint_definition": "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL",
            },
        ]

        self.mock_connection.fetch.return_value = mock_fk_data
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        fk_objects = await self.analyzer.find_foreign_key_references("users")

        assert len(fk_objects) == 2
        assert all(
            obj.object_type == SchemaObjectType.FOREIGN_KEY for obj in fk_objects
        )
        assert all(obj.depends_on_table == "users" for obj in fk_objects)

        # Verify CASCADE constraints marked as CRITICAL
        cascade_fks = [obj for obj in fk_objects if "CASCADE" in obj.definition]
        assert len(cascade_fks) >= 1
        assert cascade_fks[0].impact_level == RenameImpactLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_find_view_dependencies(self):
        """Test finding views that reference the target table."""
        mock_view_data = [
            {
                "viewname": "active_users",
                "definition": "SELECT id, name FROM users WHERE active = true",
                "schemaname": "public",
                "is_materialized": False,
            },
            {
                "viewname": "user_stats",
                "definition": "SELECT COUNT(*) FROM users GROUP BY status",
                "schemaname": "public",
                "is_materialized": True,  # This indicates it's a materialized view
            },
        ]

        self.mock_connection.fetch.return_value = mock_view_data
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        view_objects = await self.analyzer.find_view_dependencies("users")

        assert len(view_objects) == 2
        assert all(obj.object_type == SchemaObjectType.VIEW for obj in view_objects)

        # Verify materialized views marked as HIGH impact
        materialized_view = next(
            obj for obj in view_objects if "user_stats" in obj.object_name
        )
        assert materialized_view.impact_level == RenameImpactLevel.HIGH

    @pytest.mark.asyncio
    async def test_find_index_dependencies(self):
        """Test finding indexes on the target table."""
        mock_index_data = [
            {
                "indexname": "idx_users_email",
                "tablename": "users",
                "indexdef": "CREATE UNIQUE INDEX idx_users_email ON users(email)",
                "is_unique": True,
            },
            {
                "indexname": "idx_users_created_at",
                "tablename": "users",
                "indexdef": "CREATE INDEX idx_users_created_at ON users(created_at)",
                "is_unique": False,
            },
        ]

        self.mock_connection.fetch.return_value = mock_index_data
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        index_objects = await self.analyzer.find_index_dependencies("users")

        assert len(index_objects) == 2
        assert all(obj.object_type == SchemaObjectType.INDEX for obj in index_objects)

        # Verify unique indexes marked as higher impact
        unique_index = next(obj for obj in index_objects if "email" in obj.object_name)
        assert unique_index.impact_level == RenameImpactLevel.HIGH

    @pytest.mark.asyncio
    async def test_find_trigger_dependencies(self):
        """Test finding triggers on the target table."""
        mock_trigger_data = [
            {
                "trigger_name": "users_audit_trigger",
                "event_manipulation": "INSERT",
                "action_timing": "AFTER",
                "action_statement": "EXECUTE FUNCTION log_user_changes()",
                "table_name": "users",
            }
        ]

        self.mock_connection.fetch.return_value = mock_trigger_data
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        trigger_objects = await self.analyzer.find_trigger_dependencies("users")

        assert len(trigger_objects) == 1
        assert trigger_objects[0].object_type == SchemaObjectType.TRIGGER
        assert trigger_objects[0].impact_level == RenameImpactLevel.HIGH

    @pytest.mark.asyncio
    async def test_error_handling_and_edge_cases(self):
        """Test error handling and edge cases."""
        # Test with no schema objects found
        self.mock_connection.fetch.return_value = []
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        result = await self.analyzer.analyze_table_rename("nonexistent", "new_table")
        assert len(result.schema_objects) == 0
        assert result.impact_summary.overall_risk == RenameImpactLevel.SAFE

        # Test database connection error
        self.mock_connection_manager.get_connection = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        with pytest.raises(TableRenameError):
            await self.analyzer.analyze_table_rename("users", "customers")

    def test_input_sanitization(self):
        """Test input sanitization methods."""
        # Valid identifiers
        assert self.analyzer._sanitize_identifier("users") == "users"
        assert self.analyzer._sanitize_identifier("user_table") == "user_table"
        assert self.analyzer._sanitize_identifier("table123") == "table123"

        # Invalid identifiers should be sanitized
        assert (
            self.analyzer._sanitize_identifier("users; DROP TABLE x;")
            == "usersDROPTABLEx"
        )
        assert self.analyzer._sanitize_identifier("") == ""
        assert self.analyzer._sanitize_identifier(None) == ""

    @pytest.mark.asyncio
    async def test_circular_dependency_detection(self):
        """Test detection of circular dependencies in table renames."""
        # Mock circular dependency scenario
        schema_objects = [
            SchemaObject(
                object_name="fk_a_to_b",
                object_type=SchemaObjectType.FOREIGN_KEY,
                depends_on_table="table_b",
                references_table="table_a",
            ),
            SchemaObject(
                object_name="fk_b_to_a",
                object_type=SchemaObjectType.FOREIGN_KEY,
                depends_on_table="table_a",
                references_table="table_b",
            ),
        ]

        graph = await self.analyzer.build_dependency_graph("table_a", schema_objects)

        # Should detect circular dependency
        assert graph.has_circular_dependencies()
        assert graph.circular_dependency_detected is True

    @pytest.mark.asyncio
    async def test_performance_with_large_schema(self):
        """Test performance characteristics with large number of objects."""
        # Generate mock data for large schema - views
        large_view_objects = []
        for i in range(100):
            large_view_objects.append(
                {
                    "viewname": f"view_{i}",
                    "definition": f"SELECT * FROM users WHERE id = {i}",
                    "schemaname": "public",
                }
            )

        # Mock needs to return different data for different queries:
        # 1. find_foreign_key_references (incoming FK) - need constraint_name
        # 2. find_outgoing_foreign_key_references (outgoing FK) - need constraint_name
        # 3. find_view_dependencies - viewname, definition, schemaname
        # 4. find_index_dependencies - indexname, tablename, indexdef
        # 5. find_trigger_dependencies - trigger_name, etc.
        fetch_side_effects = [
            [],  # Incoming foreign keys (empty)
            [],  # Outgoing foreign keys (empty)
            large_view_objects,  # Views
            [],  # Indexes (empty)
            [],  # Triggers (empty)
        ]

        self.mock_connection.fetch.side_effect = fetch_side_effects
        self.mock_connection_manager.get_connection = AsyncMock(
            return_value=self.mock_connection
        )

        import time

        start_time = time.time()

        result = await self.analyzer.analyze_table_rename("users", "customers")

        analysis_time = time.time() - start_time

        # Should complete within reasonable time (<1 second for unit tests)
        assert analysis_time < 1.0
        assert len(result.schema_objects) > 0
