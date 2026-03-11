"""
Test to reproduce Bug #1: JSONB Serialization Issue

This test attempts to reproduce the production bug where dict values
are serialized with Python's str() producing {'key': 'value'} instead
of json.dumps() producing {"key": "value"}.

Error seen in production:
    Database query failed: invalid input syntax for type json
    DETAIL: Token "'" is invalid.
"""

import asyncio
import json

import pytest
from dataflow import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class TestJSONBSerialization:
    """Test JSONB field serialization in various scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_simple_dict_jsonb(self, test_suite):
        """Test simple dict in JSONB field."""
        # Create DataFlow with test database
        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class Config:
            name: str
            settings: dict  # JSONB field

        await db.initialize()

        # Create record with simple dict
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ConfigCreateNode",
            "create",
            {"name": "test_config", "settings": {"key": "value"}},
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        assert results["create"]["name"] == "test_config"
        settings = results["create"]["settings"]

        # Verify settings is properly deserialized
        if isinstance(settings, str):
            settings = json.loads(settings)

        assert settings == {"key": "value"}

    @pytest.mark.asyncio
    async def test_nested_dict_jsonb(self, test_suite):
        """Test nested dict in JSONB field."""
        # Create DataFlow with test database
        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class Config:
            name: str
            settings: dict

        await db.initialize()

        # Create record with nested dict
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ConfigCreateNode",
            "create",
            {
                "name": "nested_config",
                "settings": {
                    "database": {"host": "localhost", "port": 5432},
                    "cache": {"enabled": True, "ttl": 3600},
                },
            },
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        assert results["create"]["name"] == "nested_config"
        settings = results["create"]["settings"]

        if isinstance(settings, str):
            settings = json.loads(settings)

        assert settings["database"]["host"] == "localhost"
        assert settings["cache"]["enabled"] is True

    @pytest.mark.asyncio
    async def test_dict_with_special_characters(self, test_suite):
        """Test dict with special characters that might break serialization."""
        # Create DataFlow with test database
        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class Config:
            name: str
            settings: dict

        await db.initialize()

        # Create record with special characters
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ConfigCreateNode",
            "create",
            {
                "name": "special_chars",
                "settings": {
                    "message": "It's a test with 'quotes' and \"double quotes\"",
                    "path": "/path/with\\backslash",
                    "unicode": "Hello 世界 🌍",
                },
            },
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        settings = results["create"]["settings"]
        if isinstance(settings, str):
            settings = json.loads(settings)

        assert "It's a test" in settings["message"]
        assert "世界" in settings["unicode"]

    @pytest.mark.asyncio
    async def test_empty_dict_jsonb(self, test_suite):
        """Test empty dict in JSONB field."""
        # Create DataFlow with test database
        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class Config:
            name: str
            settings: dict

        await db.initialize()

        workflow = WorkflowBuilder()
        workflow.add_node(
            "ConfigCreateNode", "create", {"name": "empty", "settings": {}}
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        settings = results["create"]["settings"]
        if isinstance(settings, str):
            settings = json.loads(settings)

        assert settings == {}

    @pytest.mark.asyncio
    async def test_dict_with_null_values(self, test_suite):
        """Test dict with None/null values."""
        # Create DataFlow with test database
        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class Config:
            name: str
            settings: dict

        await db.initialize()

        workflow = WorkflowBuilder()
        workflow.add_node(
            "ConfigCreateNode",
            "create",
            {
                "name": "with_nulls",
                "settings": {"key1": None, "key2": "value", "key3": None},
            },
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        settings = results["create"]["settings"]
        if isinstance(settings, str):
            settings = json.loads(settings)

        assert settings["key1"] is None
        assert settings["key2"] == "value"

    @pytest.mark.asyncio
    async def test_large_dict_jsonb(self, test_suite):
        """Test large dict that might trigger buffer/encoding issues."""
        # Create DataFlow with test database
        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class Config:
            name: str
            settings: dict

        await db.initialize()

        # Create a large dict
        large_dict = {f"key_{i}": f"value_{i}" * 100 for i in range(100)}

        workflow = WorkflowBuilder()
        workflow.add_node(
            "ConfigCreateNode",
            "create",
            {"name": "large_config", "settings": large_dict},
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        settings = results["create"]["settings"]
        if isinstance(settings, str):
            settings = json.loads(settings)

        assert len(settings) == 100
        assert settings["key_0"].startswith("value_0")

    @pytest.mark.asyncio
    async def test_dict_with_arrays(self, test_suite):
        """Test dict containing arrays."""
        # Create DataFlow with test database
        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class Config:
            name: str
            settings: dict

        await db.initialize()

        workflow = WorkflowBuilder()
        workflow.add_node(
            "ConfigCreateNode",
            "create",
            {
                "name": "with_arrays",
                "settings": {
                    "tags": ["tag1", "tag2", "tag3"],
                    "numbers": [1, 2, 3, 4, 5],
                    "mixed": [1, "two", 3.0, True, None],
                },
            },
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        settings = results["create"]["settings"]
        if isinstance(settings, str):
            settings = json.loads(settings)

        assert settings["tags"] == ["tag1", "tag2", "tag3"]
        assert settings["numbers"] == [1, 2, 3, 4, 5]
        assert settings["mixed"] == [1, "two", 3.0, True, None]

    @pytest.mark.asyncio
    async def test_multiple_jsonb_fields(self, test_suite):
        """Test multiple JSONB fields in same model."""
        # Create DataFlow with test database
        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class MultiConfig:
            name: str
            config1: dict
            config2: dict
            config3: dict

        await db.initialize()

        workflow = WorkflowBuilder()
        workflow.add_node(
            "MultiConfigCreateNode",
            "create",
            {
                "name": "multi",
                "config1": {"a": 1},
                "config2": {"b": 2},
                "config3": {"c": 3},
            },
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        # Check all three configs
        for i in range(1, 4):
            config = results["create"][f"config{i}"]
            if isinstance(config, str):
                config = json.loads(config)
            assert list(config.keys())[0] == chr(96 + i)  # a, b, c

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_direct_asyncpg_bypass(self, test_suite):
        """
        CRITICAL: Test if there's a code path that bypasses JSON serialization.

        This test directly uses AsyncSQLDatabaseNode to reproduce the bug
        where dict parameters in a list are NOT properly serialized to JSON.

        This is the KEY reproduction test!
        """
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        connection_string = test_suite.config.url
        database_type = "postgresql"  # PostgreSQL-specific test

        # Create table manually (use raw connection to avoid prepared statement issue)
        async with test_suite.get_connection() as conn:
            await conn.execute("DROP TABLE IF EXISTS test_bypass CASCADE")
            await conn.execute(
                """
                CREATE TABLE test_bypass (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255),
                    data JSONB
                )
            """
            )

        # Insert with dict parameter using positional parameters
        # This is the CRITICAL test case - passing dict as list element
        insert_query = (
            "INSERT INTO test_bypass (name, data) VALUES ($1, $2) RETURNING *"
        )

        test_dict = {"key": "value", "nested": {"inner": "data"}}

        sql_node = AsyncSQLDatabaseNode(
            node_id="insert",
            connection_string=connection_string,
            database_type=database_type,
            query=insert_query,
            params=["test", test_dict],  # Pass dict as list element - BUG TRIGGER!
            validate_queries=False,
        )

        # This should trigger the bug if it exists
        try:
            result = await sql_node.async_run(
                query=insert_query,
                params=["test", test_dict],
                fetch_mode="one",
                validate_queries=False,
            )

            # If we get here without error, serialization worked
            assert result is not None
            data = result["result"]["data"]

            print("\n✅ INSERT succeeded!")
            print(f"Returned data type: {type(data['data'])}")
            print(f"Returned data value: {data['data']}")

            # Verify data was properly serialized
            if isinstance(data["data"], str):
                parsed = json.loads(data["data"])
                print(f"Parsed data: {parsed}")
                assert parsed == test_dict
            else:
                print(f"Data is dict: {data['data']}")
                assert data["data"] == test_dict

            # Double check: Read back from database using raw connection
            async with test_suite.get_connection() as conn:
                row = await conn.fetchrow(
                    "SELECT data FROM test_bypass WHERE id = $1", data["id"]
                )
                print(f"\nRaw database value type: {type(row['data'])}")
                print(f"Raw database value: {row['data']}")

            print("\n✅ BUG #1 IS FALSE POSITIVE - JSON serialization works correctly!")

        except Exception as e:
            # Check if this is the JSONB serialization bug
            error_msg = str(e)
            if "invalid input syntax for type json" in error_msg.lower():
                pytest.fail(
                    f"🚨 BUG REPRODUCED! JSONB serialization failed with dict in list.\n"
                    f"Error: {error_msg}\n"
                    f"This confirms the bug exists when dict is passed as list element."
                )
            else:
                # Different error - re-raise
                raise
