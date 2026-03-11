#!/usr/bin/env python3
"""
Unit tests for Kailash AsyncSQLDatabaseNode SQLite support.
Tests the Core SDK directly without DataFlow wrapper.

NOTE: These tests may fail due to Core SDK bugs in AsyncSQLDatabaseNode.
They are marked xfail until the Core SDK is updated.
"""

import os
import tempfile

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestAsyncSQLSQLite:
    """Unit tests for AsyncSQLDatabaseNode with SQLite."""

    def test_kailash_sqlite_direct(self):
        """Test Kailash AsyncSQLDatabaseNode with SQLite directly."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
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

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

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
