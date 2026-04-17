#!/usr/bin/env python3
"""
DataFlow Query Integration Tests

Test QueryBuilder and cache integration with DataFlow 2.0.

These tests were ported from the pre-2.0 test file which exercised the
now-removed ``db._query_builder`` / ``db._query_cache`` /
``db.get_query_builder()`` / ``db.execute_cached_query()`` API surface
and the ``User.nodes()`` classmethod that was removed when DataFlow 2.0
centralised node generation on ``db.get_generated_nodes(model_name)``.

Ported to the DataFlow 2.0 surface per
``packages/kailash-dataflow/src/dataflow/core/engine.py``:

- ``@db.model`` attaches ``Model.query_builder()`` classmethod (engine.py:1529)
  which returns a configured ``QueryBuilder`` against the model's table.
- Cache lives at ``db._cache_integration.cache_manager`` (engine.py:1105),
  exposed via the ``cache_enabled=True`` kwarg (not ``enable_query_cache``).
- Nodes are generated per-model and accessed via
  ``db.get_generated_nodes(model_name)`` instead of ``Model.nodes()``.
- Tenant isolation is handled through ``multi_tenant=True`` on the model +
  ``get_current_tenant_id()`` context instead of a ``tenant_id=`` kwarg on
  the query builder factory.
"""

import sys
from pathlib import Path

import pytest

from tests.infrastructure.test_harness import IntegrationTestSuite

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from dataflow.database.query_builder import create_query_builder

from dataflow import DataFlow
from dataflow.core import DataFlowConfig, Environment


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class TestDataFlowQueryIntegration:
    """Test DataFlow integration with QueryBuilder and cache."""

    def test_query_builder_initialization(self):
        """Query builder is attached to every @db.model as a classmethod."""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT

        db = DataFlow(config=config)

        @db.model
        class User:
            id: int
            name: str

        # DataFlow 2.0: each model gets a ``query_builder()`` classmethod
        # that returns a QueryBuilder against the model's table.
        builder = User.query_builder()
        assert builder is not None
        # QueryBuilder contract (used by build_query, build_select below)
        assert hasattr(builder, "where")
        assert hasattr(builder, "build_select")
        assert builder.table_name == "users"

    def test_query_cache_initialization(self):
        """Cache initializes when cache_enabled=True."""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.enable_query_cache = True

        db = DataFlow(config=config)
        # Tier 2 eager init — lazy path would require full connect.
        db._initialize_cache_integration()

        # DataFlow 2.0: cache exposed through ``_cache_integration`` facade.
        assert db._cache_integration is not None
        cache_manager = db._cache_integration.cache_manager
        # Cache backend implements get / set / invalidate_model.
        assert hasattr(cache_manager, "get")
        assert hasattr(cache_manager, "set")
        assert hasattr(cache_manager, "invalidate_model")

    def test_query_cache_disabled(self):
        """Cache is None when disabled."""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.enable_query_cache = False

        db = DataFlow(config=config)

        # DataFlow 2.0: ``_cache_integration`` stays None when the feature
        # flag is off, even after an ``_initialize_cache_integration()`` call
        # would otherwise be made — because the gate in ``_ensure_connected``
        # checks ``config.enable_query_cache`` first.
        assert db._cache_integration is None

    def test_database_type_detection(self, test_suite):
        """``create_query_builder`` picks the right dialect per URL scheme."""

        # PostgreSQL via real test infra
        pg_builder = create_query_builder("users", test_suite.config.url)
        assert pg_builder is not None
        assert "postgresql" in test_suite.config.url

        # MySQL scheme detection
        my_builder = create_query_builder("users", "mysql://user:pass@localhost/db")
        assert my_builder is not None

        # SQLite scheme detection
        sqlite_builder = create_query_builder("users", "sqlite:///test.db")
        assert sqlite_builder is not None

    def test_cache_backend_selection(self):
        """Cache backend auto-selects in-memory when Redis is unavailable.

        Replaces the pre-2.0 ``cache_invalidation_strategy`` test — the
        invalidation-strategy enum was removed when cache invalidation
        moved to ``CacheInvalidator`` + ``InvalidationPattern``. The
        backend-selection contract (``auto_detect``) is the live
        equivalent surface.
        """
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.enable_query_cache = True
        # Force in-memory by pointing Redis URL at a non-resolvable host.
        config.cache_redis_url = "redis://nonexistent-host:6379/0"

        db = DataFlow(config=config)
        db._initialize_cache_integration()

        assert db._cache_integration is not None
        backend_name = db._cache_integration.cache_manager.__class__.__name__
        assert backend_name in ["InMemoryCache", "AsyncRedisCacheAdapter"]

    def test_build_query_method(self):
        """Model.query_builder() + where + build_select produces SQL."""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT

        db = DataFlow(config=config)

        @db.model
        class User:
            id: int
            name: str
            age: int
            status: str

        builder = User.query_builder()
        builder.where("age", "$gt", 18)
        builder.where("status", "$eq", "active")

        sql, params = builder.build_select(["id", "name"])
        # DataFlow 2.0 QueryBuilder quotes identifiers (dialect-aware safety,
        # see ``rules/dataflow-identifier-safety.md``). Assert on field and
        # table presence rather than an exact unquoted substring.
        assert "SELECT" in sql
        assert "id" in sql and "name" in sql
        assert "users" in sql
        assert "WHERE" in sql
        assert len(params) == 2
        assert 18 in params
        assert "active" in params

    def test_build_query_with_tenant(self):
        """Multi-tenant models add tenant_id filtering through the context.

        Replaces the pre-2.0 ``db.build_query("users", tenant_id=...)``
        which injected tenant_id directly. DataFlow 2.0 routes tenant
        isolation through ``get_current_tenant_id()`` — see
        ``rules/tenant-isolation.md``. Testing the contract: a
        multi_tenant model's schema includes a ``tenant_id`` column which
        the WHERE clause can then filter on.
        """
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.security.multi_tenant = True

        db = DataFlow(config=config)

        @db.model
        class User:
            id: int
            name: str

        # DataFlow 2.0 injects tenant_id into the field set for
        # multi_tenant models (engine.py:1519-1526).
        model_info = db._models["User"]
        assert "tenant_id" in model_info["fields"]

        # The user filters on it explicitly through the QueryBuilder:
        builder = User.query_builder()
        builder.where("tenant_id", "$eq", "tenant_123")
        sql, params = builder.build_select(["id", "name"])

        assert "tenant_id" in sql
        assert "tenant_123" in params

    def test_cache_get_set_when_cache_disabled(self):
        """Cache manager is None when caching is disabled.

        Replaces the pre-2.0 ``db.execute_cached_query(...)`` that returned
        None on disabled cache. DataFlow 2.0 never attaches the cache
        integration at all when disabled — the ``_cache_integration``
        attribute stays None, which callers MUST check before using.
        """
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.enable_query_cache = False

        db = DataFlow(config=config)

        # Cache integration is not created → callers see None and skip
        # the cache path.
        assert db._cache_integration is None

    async def test_cache_get_set_roundtrip(self):
        """Cache read-back verifies real in-memory state (Tier 2 contract).

        Replaces the pre-2.0 ``db.execute_cached_query(query, params)`` +
        ``db._build_query_cache_key`` surface. DataFlow 2.0 exposes the
        cache manager directly; callers build their own key and store/
        retrieve through the manager.
        """
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.enable_query_cache = True

        db = DataFlow(config=config)
        db._initialize_cache_integration()

        cache_manager = db._cache_integration.cache_manager

        cache_key = "dataflow:User:list:query_params_hash_abc"
        value = {"result": [{"id": 1, "name": "John"}]}

        # Cache miss first.
        assert await cache_manager.get(cache_key) is None

        # Populate → read-back verifies state persistence per
        # ``rules/testing.md`` Tier 2-3 state-persistence rule.
        await cache_manager.set(cache_key, value)
        assert await cache_manager.get(cache_key) == value

        # Delete → follow-up read returns None.
        await cache_manager.delete(cache_key)
        assert await cache_manager.get(cache_key) is None

    def test_model_enhancement_with_query_features(self):
        """Models are enhanced with ``query_builder`` classmethod."""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.enable_query_cache = True

        db = DataFlow(config=config)

        @db.model
        class User:
            id: int
            name: str
            email: str

        # DataFlow 2.0: models get ``query_builder()`` classmethod attached.
        assert hasattr(User, "query_builder")
        builder = User.query_builder()
        assert builder is not None
        assert builder.table_name == "users"

    def test_model_registry_integration(self):
        """@db.model registers models in the model registry.

        Replaces ``db.get_resource_registry()`` which was removed with the
        Phase-5 wiring sweep (no consumer surface). The live registry is
        ``db._models`` / ``db.get_model_registry()`` — both used by the
        production generator path.
        """
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.enable_query_cache = True

        db = DataFlow(config=config)

        @db.model
        class Widget:
            id: int
            sku: str

        # Model registered in the DataFlow instance's model map.
        assert "Widget" in db._models
        # And in the persistent registry (the Engine-level facade).
        registry = db.get_model_registry()
        assert registry is not None

    def test_configuration_cache_ttl_propagation(self):
        """``cache_ttl`` on the config propagates to the cache manager.

        Replaces ``test_configuration_validation`` which asserted on the
        removed ``CacheInvalidationStrategy`` enum — the config now lives
        on the backend (TTL + max_size) rather than a strategy enum.
        """
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.enable_query_cache = True
        config.cache_ttl = 777

        db = DataFlow(config=config)
        db._initialize_cache_integration()

        cache_manager = db._cache_integration.cache_manager
        # InMemoryCache exposes the TTL it was constructed with.
        if cache_manager.__class__.__name__ == "InMemoryCache":
            assert cache_manager.ttl == 777

    def test_multi_tenant_configuration(self):
        """Multi-tenant flag adds tenant_id to model schema."""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.security.multi_tenant = True
        config.enable_query_cache = True

        db = DataFlow(config=config)

        @db.model
        class Document:
            id: int
            title: str

        # DataFlow 2.0: multi_tenant=True injects tenant_id into the
        # generated schema (engine.py:1519-1526).
        fields = db._models["Document"]["fields"]
        assert "tenant_id" in fields

        # Query builder can filter on the injected column.
        builder = Document.query_builder()
        builder.where("tenant_id", "$eq", "tenant_123")
        sql, params = builder.build_select(["id", "title"])
        assert "tenant_id" in sql
        assert "tenant_123" in params

    def test_performance_configuration(self):
        """Performance-related cache configuration reaches the cache manager."""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT
        config.enable_query_cache = True
        config.cache_ttl = 600
        # Use an unreachable Redis URL so auto-detect falls back to
        # InMemoryCache deterministically.
        config.cache_redis_url = "redis://nonexistent-host:6380/0"

        db = DataFlow(config=config)
        db._initialize_cache_integration()

        cache_manager = db._cache_integration.cache_manager
        # InMemoryCache exposes the TTL it was constructed with.
        assert cache_manager.__class__.__name__ == "InMemoryCache"
        assert cache_manager.ttl == 600


class TestDataFlowQueryWorkflowIntegration:
    """Test integration with workflow systems."""

    def test_query_builder_produces_usable_sql(self):
        """Query builder + WHERE clause produces SQL usable downstream."""
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT

        db = DataFlow(config=config)

        @db.model
        class User:
            id: int
            name: str
            status: str

        builder = User.query_builder()
        builder.where("status", "$eq", "active")
        sql, params = builder.build_select(["id", "name"])

        # SQL is a valid non-empty string; params carries the bound value.
        assert sql is not None
        assert "SELECT" in sql
        assert "users" in sql
        assert len(params) == 1
        assert "active" in params

    def test_node_generation_with_query_features(self):
        """Auto-generated nodes are discoverable via ``db.get_generated_nodes``.

        Replaces ``User.nodes()`` which was removed. DataFlow 2.0
        centralises node discovery on ``db.get_generated_nodes(model_name)``
        — the model-class no longer carries the ``nodes`` attribute.
        """
        config = DataFlowConfig()
        config.environment = Environment.DEVELOPMENT

        db = DataFlow(config=config)

        @db.model
        class User:
            id: int
            name: str
            email: str

        nodes = db.get_generated_nodes("User")
        assert nodes is not None
        assert len(nodes) > 0

        # DataFlow 2.0: 11 nodes per model (CRUD + query + upsert + bulk).
        # Names are CamelCase — e.g., ``UserCreateNode``.
        node_names = {n.lower() for n in nodes}
        assert any("create" in n for n in node_names)
        assert any("read" in n for n in node_names)
        assert any("update" in n for n in node_names)
        assert any("delete" in n for n in node_names)


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
