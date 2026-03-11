#!/usr/bin/env python3
"""
DataFlow Query Integration Tests

Test QueryBuilder and QueryCache integration with DataFlow.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from tests.infrastructure.test_harness import IntegrationTestSuite

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from dataflow import DataFlow
from dataflow.core import DataFlowConfig, Environment

from kailash.nodes.data.query_builder import create_query_builder
from kailash.nodes.data.query_cache import CacheInvalidationStrategy, QueryCache


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class TestDataFlowQueryIntegration:
    """Test DataFlow integration with QueryBuilder and QueryCache"""

    def test_query_builder_initialization(self):
        """Test that query builder is properly initialized"""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT

        db = DataFlow(config)

        # Query builder should be initialized
        assert db._query_builder is not None
        assert hasattr(db._query_builder, "table")
        assert hasattr(db._query_builder, "where")
        assert hasattr(db._query_builder, "build_select")

    def test_query_cache_initialization(self):
        """Test that query cache is properly initialized when enabled"""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.enable_query_cache = True

        db = DataFlow(config)

        # Query cache should be initialized
        assert db._query_cache is not None
        assert hasattr(db._query_cache, "get")
        assert hasattr(db._query_cache, "set")
        assert hasattr(db._query_cache, "invalidate_table")

    def test_query_cache_disabled(self):
        """Test that query cache is not initialized when disabled"""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.enable_query_cache = False

        db = DataFlow(config)

        # Query cache should not be initialized
        assert db._query_cache is None

    def test_database_type_detection(self, test_suite):
        """Test that correct query builder is created for different database types"""

        # Test PostgreSQL
        db = DataFlow(test_suite.config.url)
        builder = db.get_query_builder()

        # Should create PostgreSQL query builder
        assert builder is not None

        # Test MySQL
        db = DataFlow("mysql://user:pass@localhost/db")
        builder = db.get_query_builder()

        assert builder is not None

        # Test SQLite
        db = DataFlow("sqlite:///test.db")
        builder = db.get_query_builder()

        assert builder is not None

    def test_cache_invalidation_strategy_mapping(self):
        """Test that cache invalidation strategies are properly mapped"""

        strategies = [
            ("ttl", CacheInvalidationStrategy.TTL),
            ("manual", CacheInvalidationStrategy.MANUAL),
            ("pattern_based", CacheInvalidationStrategy.PATTERN_BASED),
            ("event_based", CacheInvalidationStrategy.EVENT_BASED),
        ]

        for strategy_name, expected_strategy in strategies:
            config = DataFlowConfig()
            config.environment = Environment.DEVELOPMENT
            config.enable_query_cache = True
            config.cache_invalidation_strategy = strategy_name

            db = DataFlow(config)
            cache = db.get_query_cache()

            assert cache is not None
            assert cache.invalidation_strategy == expected_strategy

    def test_build_query_method(self):
        """Test the build_query method"""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT

        db = DataFlow(config)

        # Test basic query building
        builder = db.build_query("users")
        assert builder is not None

        # Test with conditions
        builder = db.build_query(
            "users", [("age", "$gt", 18), ("status", "$eq", "active")]
        )

        sql, params = builder.build_select(["id", "name"])
        assert "SELECT id, name FROM users" in sql
        assert "WHERE" in sql
        assert len(params) == 2
        assert 18 in params
        assert "active" in params

    def test_build_query_with_tenant(self):
        """Test query building with tenant isolation"""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT

        db = DataFlow(config)

        # Test tenant isolation
        builder = db.build_query("users", tenant_id="tenant_123")
        sql, params = builder.build_select(["id", "name"])

        assert "tenant_id" in sql
        assert "tenant_123" in params

    def test_execute_cached_query_no_cache(self):
        """Test execute_cached_query when cache is disabled"""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.enable_query_cache = False

        db = DataFlow(config)

        # Should return None when cache is disabled
        result = db.execute_cached_query("SELECT * FROM users", [])
        assert result is None

    @patch("dataflow.core.engine.QueryCache")
    def test_execute_cached_query_with_cache(self, mock_cache_class):
        """Test execute_cached_query with cache enabled"""
        # Mock cache instance
        mock_cache = Mock()
        mock_cache.get.return_value = {"result": [{"id": 1, "name": "John"}]}
        mock_cache_class.return_value = mock_cache

        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.enable_query_cache = True

        db = DataFlow(config)

        # Should return cached result
        result = db.execute_cached_query("SELECT * FROM users", [])
        assert result == [{"id": 1, "name": "John"}]

        # Test cache miss
        mock_cache.get.return_value = None
        result = db.execute_cached_query("SELECT * FROM users", [])
        assert result is None

    def test_model_enhancement_with_query_features(self):
        """Test that models are enhanced with query builder and cache methods"""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.enable_query_cache = True

        db = DataFlow(config)

        @db.model
        class User:
            id: int
            name: str
            email: str

        # Test query builder method
        assert hasattr(User, "query_builder")
        builder = User.query_builder()
        assert builder is not None

        # Test cached query method
        assert hasattr(User, "cached_query")
        # Note: This would require a real cache implementation to test fully

    def test_resource_registry_integration(self):
        """Test that query cache is registered with resource registry"""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.enable_query_cache = True

        db = DataFlow(config)

        # Query cache should be registered
        resource_registry = db.get_resource_registry()
        assert resource_registry is not None

        # This would require inspecting the registry internals
        # which may not be publicly accessible

    def test_configuration_validation(self):
        """Test configuration validation with query features"""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.enable_query_cache = True
        config.cache_invalidation_strategy = "invalid_strategy"

        # Should handle invalid strategy gracefully
        db = DataFlow(config)
        cache = db.get_query_cache()

        # Should default to pattern_based
        assert cache.invalidation_strategy == CacheInvalidationStrategy.PATTERN_BASED

    def test_multi_tenant_configuration(self):
        """Test multi-tenant configuration with query features"""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.security.multi_tenant = True
        config.enable_query_cache = True

        db = DataFlow(config)

        # Should work with multi-tenant setup
        builder = db.build_query("users", tenant_id="tenant_123")
        sql, params = builder.build_select(["id", "name"])

        assert "tenant_id" in sql
        assert "tenant_123" in params

    def test_performance_configuration(self):
        """Test performance-related configuration"""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.enable_query_cache = True
        config.cache_ttl = 600
        config.redis_host = "custom-redis"
        config.redis_port = 6380

        db = DataFlow(config)
        cache = db.get_query_cache()

        # Should use custom configuration
        assert cache.default_ttl == 600
        assert cache.redis_host == "custom-redis"
        assert cache.redis_port == 6380


class TestDataFlowQueryWorkflowIntegration:
    """Test integration with workflow systems"""

    def test_workflow_builder_integration(self):
        """Test that query features work with WorkflowBuilder"""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT

        db = DataFlow(config)

        # Build query
        builder = db.build_query("users")
        builder.where("status", "$eq", "active")
        sql, params = builder.build_select(["id", "name"])

        # Should be able to use in workflow
        assert sql is not None
        assert params is not None
        assert len(params) == 1
        assert "active" in params

    def test_node_generation_with_query_features(self):
        """Test that auto-generated nodes work with query features"""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.auto_generate_nodes = True

        db = DataFlow(config)

        @db.model
        class User:
            id: int
            name: str
            email: str

        # Nodes should be generated
        nodes = User.nodes()
        assert nodes is not None
        assert len(nodes) > 0

        # Should include CRUD operations
        assert "create" in nodes
        assert "read" in nodes
        assert "update" in nodes
        assert "delete" in nodes


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
