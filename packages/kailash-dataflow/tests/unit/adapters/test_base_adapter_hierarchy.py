"""
Tests for BaseAdapter hierarchy.

Validates that all adapters properly inherit from BaseAdapter and implement
the required interface for their adapter type.
"""

import pytest
from dataflow.adapters import (
    BaseAdapter,
    DatabaseAdapter,
    MySQLAdapter,
    PostgreSQLAdapter,
    SQLiteAdapter,
)


class TestBaseAdapterHierarchy:
    """Test BaseAdapter hierarchy and interface."""

    def test_postgresql_adapter_hierarchy(self):
        """PostgreSQL adapter inherits correctly from BaseAdapter."""
        adapter = PostgreSQLAdapter("postgresql://localhost/test")

        # Should be instance of BaseAdapter
        assert isinstance(adapter, BaseAdapter)

        # Should be instance of DatabaseAdapter
        assert isinstance(adapter, DatabaseAdapter)

        # Should have adapter_type property
        assert adapter.adapter_type == "sql"

        # Should have database_type property
        assert adapter.database_type == "postgresql"

    def test_mysql_adapter_hierarchy(self):
        """MySQL adapter inherits correctly from BaseAdapter."""
        adapter = MySQLAdapter("mysql://localhost/test")

        # Should be instance of BaseAdapter
        assert isinstance(adapter, BaseAdapter)

        # Should be instance of DatabaseAdapter
        assert isinstance(adapter, DatabaseAdapter)

        # Should have adapter_type property
        assert adapter.adapter_type == "sql"

        # Should have database_type property
        assert adapter.database_type == "mysql"

    def test_sqlite_adapter_hierarchy(self):
        """SQLite adapter inherits correctly from BaseAdapter."""
        adapter = SQLiteAdapter(":memory:")

        # Should be instance of BaseAdapter
        assert isinstance(adapter, BaseAdapter)

        # Should be instance of DatabaseAdapter
        assert isinstance(adapter, DatabaseAdapter)

        # Should have adapter_type property
        assert adapter.adapter_type == "sql"

        # Should have database_type property
        assert adapter.database_type == "sqlite"

    def test_all_sql_adapters_have_sql_adapter_type(self):
        """All SQL adapters should have adapter_type='sql'."""
        adapters = [
            PostgreSQLAdapter("postgresql://localhost/test"),
            MySQLAdapter("mysql://localhost/test"),
            SQLiteAdapter(":memory:"),
        ]

        for adapter in adapters:
            assert (
                adapter.adapter_type == "sql"
            ), f"{adapter.__class__.__name__} should have adapter_type='sql'"

    def test_adapter_connection_info(self):
        """Test get_connection_info method from BaseAdapter."""
        adapter = PostgreSQLAdapter("postgresql://localhost/test")

        info = adapter.get_connection_info()

        assert "adapter_type" in info
        assert "database_type" in info
        assert "connected" in info

        assert info["adapter_type"] == "sql"
        assert info["database_type"] == "postgresql"
        assert info["connected"] is False  # Not connected yet

    def test_adapter_repr(self):
        """Test __repr__ method from BaseAdapter."""
        adapter = PostgreSQLAdapter("postgresql://localhost/test")

        repr_str = repr(adapter)

        assert "PostgreSQLAdapter" in repr_str
        assert "database_type='postgresql'" in repr_str
        assert "connected=False" in repr_str

    @pytest.mark.asyncio
    async def test_health_check_interface(self):
        """Test health_check method from BaseAdapter."""
        adapter = PostgreSQLAdapter("postgresql://localhost/test")

        # Health check should return dict with expected keys
        # Note: Will fail to connect but should return proper structure
        health = await adapter.health_check()

        assert isinstance(health, dict)
        assert "healthy" in health
        assert "database_type" in health
        assert "adapter_type" in health
        assert "connected" in health

        # Should have database info even if unhealthy
        assert health["database_type"] == "postgresql"
        assert health["adapter_type"] == "sql"

    def test_database_adapter_is_sql_type(self):
        """DatabaseAdapter should always have adapter_type='sql'."""
        # This tests the base DatabaseAdapter class
        # Cannot instantiate abstract class directly, but can verify via subclasses
        for adapter_class in [PostgreSQLAdapter, MySQLAdapter, SQLiteAdapter]:
            adapter = adapter_class(
                "postgresql://localhost/test"
                if adapter_class == PostgreSQLAdapter
                else (
                    "mysql://localhost/test"
                    if adapter_class == MySQLAdapter
                    else ":memory:"
                )
            )
            assert adapter.adapter_type == "sql"

    def test_supports_feature_interface(self):
        """All adapters must implement supports_feature method."""
        adapters = [
            PostgreSQLAdapter("postgresql://localhost/test"),
            MySQLAdapter("mysql://localhost/test"),
            SQLiteAdapter(":memory:"),
        ]

        for adapter in adapters:
            # Should have supports_feature method
            assert hasattr(adapter, "supports_feature")
            assert callable(adapter.supports_feature)

            # Should return bool
            result = adapter.supports_feature("transactions")
            assert isinstance(result, bool)

    def test_backward_compatibility_imports(self):
        """Ensure backward compatible imports still work."""
        # Old code should still work
        # New code should also work
        from dataflow.adapters import BaseAdapter as Base1
        from dataflow.adapters import DatabaseAdapter as DB1
        from dataflow.adapters import MySQLAdapter as MySQL1
        from dataflow.adapters import PostgreSQLAdapter as Postgres1
        from dataflow.adapters import SQLiteAdapter as SQLite1

        # All imports should succeed
        assert DB1 is not None
        assert MySQL1 is not None
        assert Postgres1 is not None
        assert SQLite1 is not None
        assert Base1 is not None
