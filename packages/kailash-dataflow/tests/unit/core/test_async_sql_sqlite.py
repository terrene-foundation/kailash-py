#!/usr/bin/env python3
"""
Unit tests for Kailash AsyncSQLDatabaseNode SQLite support.
Tests the Core SDK directly without DataFlow wrapper.

NOTE: These tests may fail due to Core SDK bugs in AsyncSQLDatabaseNode.
They are marked xfail until the Core SDK is updated.
"""

import pytest

_runtime = pytest.importorskip("kailash.runtime.local")
LocalRuntime = _runtime.LocalRuntime
_wf = pytest.importorskip("kailash.workflow.builder")
WorkflowBuilder = _wf.WorkflowBuilder


class TestAsyncSQLSQLite:
    """Unit tests for AsyncSQLDatabaseNode with SQLite."""

    def test_kailash_sqlite_direct(self, tmp_path):
        """Test Kailash AsyncSQLDatabaseNode with SQLite directly."""
        db_path = tmp_path / "kailash_sqlite_direct.db"

        # Test 1: Create table
        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "create_table",
            {
                "connection_string": f"sqlite:///{db_path}",
                "query": """
                CREATE TABLE IF NOT EXISTS test_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE
                )
            """,
                "validate_queries": False,
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert "create_table" in results
        assert not results["create_table"].get("error")

        # Test 2: Insert data
        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "insert_data",
            {
                "connection_string": f"sqlite:///{db_path}",
                "query": "INSERT INTO test_users (name, email) VALUES (?, ?)",
                "params": ["John Doe", "john@example.com"],
            },
        )

        results, run_id = runtime.execute(workflow.build())

        assert "insert_data" in results
        assert not results["insert_data"].get("error")

        # Test 3: Query data
        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "query_data",
            {
                "connection_string": f"sqlite:///{db_path}",
                "query": "SELECT * FROM test_users",
            },
        )

        results, run_id = runtime.execute(workflow.build())

        assert "query_data" in results
        assert not results["query_data"].get("error")
        data = results["query_data"].get("result", {}).get("data", [])
        assert len(data) == 1
        assert data[0]["name"] == "John Doe"

    def test_memory_sqlite(self):
        """Test with memory SQLite database."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "create_table",
            {
                "connection_string": ":memory:",
                "query": """
                CREATE TABLE test_items (
                    id INTEGER PRIMARY KEY,
                    name TEXT
                )
            """,
                "validate_queries": False,
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert "create_table" in results
        assert not results["create_table"].get("error")
