# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tests for the database_type -> source_type rename.

Verifies:
- source_type returns the correct type string on concrete adapters
- database_type still works but emits DeprecationWarning
- New subclasses implementing only source_type work correctly
"""

import warnings

import pytest
from dataflow.adapters.base_adapter import BaseAdapter
from dataflow.adapters.base import DatabaseAdapter
from dataflow.adapters.postgresql import PostgreSQLAdapter
from dataflow.adapters.mysql import MySQLAdapter
from dataflow.adapters.sqlite import SQLiteAdapter


class TestSourceTypeProperty:
    """Verify .source_type returns the correct identifier on every adapter."""

    @pytest.mark.parametrize(
        "adapter_cls, conn_str, expected",
        [
            (PostgreSQLAdapter, "postgresql://localhost/test", "postgresql"),
            (MySQLAdapter, "mysql://localhost/test", "mysql"),
            (SQLiteAdapter, ":memory:", "sqlite"),
        ],
    )
    def test_source_type_returns_correct_value(self, adapter_cls, conn_str, expected):
        adapter = adapter_cls(conn_str)
        assert adapter.source_type == expected


class TestDatabaseTypeDeprecationShim:
    """Verify .database_type still works but emits DeprecationWarning."""

    def test_database_type_emits_deprecation_warning(self):
        adapter = SQLiteAdapter(":memory:")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = adapter.database_type

        assert result == "sqlite"
        assert len(caught) == 1
        assert issubclass(caught[0].category, DeprecationWarning)
        assert "database_type is deprecated" in str(caught[0].message)

    def test_database_type_returns_same_as_source_type(self):
        adapter = PostgreSQLAdapter("postgresql://localhost/test")

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            deprecated_value = adapter.database_type

        assert deprecated_value == adapter.source_type

    @pytest.mark.parametrize(
        "adapter_cls, conn_str",
        [
            (PostgreSQLAdapter, "postgresql://localhost/test"),
            (MySQLAdapter, "mysql://localhost/test"),
            (SQLiteAdapter, ":memory:"),
        ],
    )
    def test_shim_works_on_all_adapters(self, adapter_cls, conn_str):
        adapter = adapter_cls(conn_str)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = adapter.database_type

        assert result == adapter.source_type
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)


class TestNewSubclassImplementsSourceType:
    """Verify that a new subclass only needs to implement source_type."""

    def test_custom_subclass_with_source_type_only(self):
        class CustomAdapter(DatabaseAdapter):
            @property
            def source_type(self) -> str:
                return "custom_db"

            @property
            def default_port(self) -> int:
                return 9999

            async def connect(self) -> None:
                self.is_connected = True

            async def disconnect(self) -> None:
                self.is_connected = False

            async def execute_query(self, query, params=None):
                return []

            async def execute_transaction(self, queries):
                return []

            async def get_table_schema(self, table_name):
                return {}

            async def create_table(self, table_name, schema):
                pass

            async def drop_table(self, table_name):
                pass

            def get_dialect(self):
                return "custom"

            def supports_feature(self, feature):
                return False

        adapter = CustomAdapter("custom://localhost/test")

        # source_type works
        assert adapter.source_type == "custom_db"

        # deprecated database_type also works via shim
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert adapter.database_type == "custom_db"

        assert len(caught) == 1
        assert issubclass(caught[0].category, DeprecationWarning)


class TestHealthCheckAndReprUseSourceType:
    """Verify health_check and __repr__ use source_type (no deprecation warning)."""

    def test_repr_uses_source_type(self):
        adapter = SQLiteAdapter(":memory:")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            repr_str = repr(adapter)

        assert "source_type='sqlite'" in repr_str
        # repr should NOT trigger the deprecation warning
        assert not any(issubclass(w.category, DeprecationWarning) for w in caught)

    def test_get_connection_info_uses_source_type(self):
        adapter = SQLiteAdapter(":memory:")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            info = adapter.get_connection_info()

        assert "source_type" in info
        assert info["source_type"] == "sqlite"
        assert "database_type" not in info
        # Should NOT trigger deprecation warning
        assert not any(issubclass(w.category, DeprecationWarning) for w in caught)
