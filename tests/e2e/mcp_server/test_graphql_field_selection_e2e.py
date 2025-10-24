"""E2E tests for GraphQL-style field selection in MCP resource subscriptions."""

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from kailash.mcp_server.server import MCPServer
from kailash.mcp_server.subscriptions import (
    ResourceChange,
    ResourceChangeType,
    ResourceSubscriptionManager,
)
from kailash.middleware.gateway.event_store import EventStore

from tests.integration.docker_test_base import DockerIntegrationTestBase


class TestGraphQLFieldSelectionE2E(DockerIntegrationTestBase):
    """End-to-end tests demonstrating GraphQL field selection in action."""

    @pytest_asyncio.fixture
    async def mcp_server_e2e(self, postgres_conn):
        """Create complete MCP server for E2E testing."""
        event_store = EventStore(postgres_conn)

        server = MCPServer(
            "e2e_field_selection_server",
            event_store=event_store,
            enable_subscriptions=True,
        )

        # Initialize subscription manager
        server.subscription_manager = ResourceSubscriptionManager(
            event_store=event_store
        )
        await server.subscription_manager.initialize()

        # Add some test resources
        @server.resource("file:///{path}")
        async def file_resource(path: str):
            """Mock file resource."""
            return {
                "name": f"file_{path}",
                "content": f"Content of {path}",
                "size": len(path) * 100,
                "type": "text",
            }

        @server.resource("config:///{section}")
        async def config_resource(section: str):
            """Mock configuration resource."""
            configs = {
                "database": {
                    "host": "localhost",
                    "port": 5432,
                    "name": "myapp",
                    "pool_size": 10,
                },
                "cache": {"host": "redis.example.com", "port": 6379, "ttl": 3600},
            }
            return configs.get(section, {})

        yield server

        if server.subscription_manager:
            await server.subscription_manager.shutdown()

    @pytest.mark.asyncio
    async def test_complete_graphql_field_selection_workflow(self, mcp_server_e2e):
        """Test complete workflow: subscribe with field selection, trigger changes, verify filtered notifications."""
        server = mcp_server_e2e
        notifications_received = []

        # Set up notification capture
        async def capture_notifications(connection_id: str, notification: dict):
            notifications_received.append((connection_id, notification))

        server.subscription_manager.set_notification_callback(capture_notifications)

        # Test 1: Subscribe with field selection only
        result = await server._handle_subscribe(
            {
                "uri": "file:///document.txt",
                "fields": ["uri", "content"],  # Only want URI and content
            },
            "req_001",
            "client_fields",
        )

        assert result["jsonrpc"] == "2.0"
        assert "result" in result
        fields_subscription_id = result["result"]["subscriptionId"]

        # Test 2: Subscribe with fragment selection
        result = await server._handle_subscribe(
            {
                "uri": "config:///database",
                "fragments": {
                    "connectionInfo": ["host", "port"],
                    "settings": ["name", "pool_size"],
                },
            },
            "req_002",
            "client_fragments",
        )

        assert "result" in result
        fragments_subscription_id = result["result"]["subscriptionId"]

        # Test 3: Subscribe without field selection (should get all data)
        result = await server._handle_subscribe(
            {"uri": "file:///readme.md"}, "req_003", "client_all"
        )

        assert "result" in result
        all_subscription_id = result["result"]["subscriptionId"]

        # Mock resource data for each subscription
        async def mock_get_resource_data(uri: str):
            if uri == "file:///document.txt":
                return {
                    "uri": uri,
                    "name": "document.txt",
                    "content": "This is the document content",
                    "size": 1024,
                    "type": "text",
                    "metadata": {
                        "created": "2024-01-01T00:00:00Z",
                        "modified": "2024-01-15T10:30:00Z",
                    },
                }
            elif uri == "config:///database":
                return {
                    "uri": uri,
                    "host": "localhost",
                    "port": 5432,
                    "name": "myapp",
                    "pool_size": 10,
                    "ssl": True,
                    "timeout": 30,
                }
            elif uri == "file:///readme.md":
                return {
                    "uri": uri,
                    "name": "readme.md",
                    "content": "# Project README\\n\\nThis is the readme file.",
                    "size": 2048,
                    "type": "markdown",
                    "metadata": {"author": "developer", "version": "1.0"},
                }
            return {}

        server.subscription_manager._get_resource_data = mock_get_resource_data

        # Trigger changes for each subscribed resource

        # Change 1: Update file with field selection
        change1 = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="file:///document.txt",
            timestamp=datetime.utcnow(),
        )
        await server.subscription_manager.process_resource_change(change1)

        # Change 2: Update config with fragment selection
        change2 = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="config:///database",
            timestamp=datetime.utcnow(),
        )
        await server.subscription_manager.process_resource_change(change2)

        # Change 3: Update file without field selection
        change3 = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="file:///readme.md",
            timestamp=datetime.utcnow(),
        )
        await server.subscription_manager.process_resource_change(change3)

        # Verify notifications were received
        assert len(notifications_received) == 3

        # Verify field selection notification (first notification)
        client_id, notification = notifications_received[0]
        assert client_id == "client_fields"
        assert notification["method"] == "notifications/resources/updated"
        assert notification["params"]["uri"] == "file:///document.txt"

        # Check that only selected fields are present
        filtered_data = notification["params"]["data"]
        expected_fields_data = {
            "uri": "file:///document.txt",
            "content": "This is the document content",
        }
        assert filtered_data == expected_fields_data

        # Verify fragment selection notification (second notification)
        client_id, notification = notifications_received[1]
        assert client_id == "client_fragments"
        assert notification["params"]["uri"] == "config:///database"

        # Check that fragments are properly formatted
        filtered_data = notification["params"]["data"]
        expected_fragments_data = {
            "__connectionInfo": {"host": "localhost", "port": 5432},
            "__settings": {"name": "myapp", "pool_size": 10},
        }
        assert filtered_data == expected_fragments_data

        # Verify no field selection notification (third notification)
        client_id, notification = notifications_received[2]
        assert client_id == "client_all"
        assert notification["params"]["uri"] == "file:///readme.md"

        # Check that all data is present
        filtered_data = notification["params"]["data"]
        expected_all_data = {
            "uri": "file:///readme.md",
            "name": "readme.md",
            "content": "# Project README\\n\\nThis is the readme file.",
            "size": 2048,
            "type": "markdown",
            "metadata": {"author": "developer", "version": "1.0"},
        }
        assert filtered_data == expected_all_data

    @pytest.mark.asyncio
    async def test_complex_nested_field_selection(self, mcp_server_e2e):
        """Test complex nested field selection scenarios."""
        server = mcp_server_e2e
        notifications_received = []

        async def capture_notifications(connection_id: str, notification: dict):
            notifications_received.append((connection_id, notification))

        server.subscription_manager.set_notification_callback(capture_notifications)

        # Subscribe with deeply nested field selection
        result = await server._handle_subscribe(
            {
                "uri": "file:///complex.json",
                "fields": [
                    "uri",
                    "metadata.author",
                    "metadata.stats.lines",
                    "content.sections.introduction",
                ],
            },
            "req_complex",
            "client_complex",
        )

        assert "result" in result

        # Mock complex nested resource data
        async def mock_complex_resource_data(uri: str):
            return {
                "uri": uri,
                "name": "complex.json",
                "content": {
                    "title": "Complex Document",
                    "sections": {
                        "introduction": "This is the introduction section",
                        "body": "This is the main body content",
                        "conclusion": "This is the conclusion",
                    },
                    "appendix": {
                        "references": ["ref1", "ref2"],
                        "notes": "Additional notes",
                    },
                },
                "metadata": {
                    "author": "John Doe",
                    "created": "2024-01-01",
                    "stats": {"lines": 150, "words": 2500, "characters": 15000},
                    "tags": ["document", "complex", "nested"],
                },
                "version": "1.2.3",
            }

        server.subscription_manager._get_resource_data = mock_complex_resource_data

        # Trigger change
        change = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="file:///complex.json",
            timestamp=datetime.utcnow(),
        )
        await server.subscription_manager.process_resource_change(change)

        # Verify nested field selection worked correctly
        assert len(notifications_received) == 1
        client_id, notification = notifications_received[0]

        filtered_data = notification["params"]["data"]
        expected_nested_data = {
            "uri": "file:///complex.json",
            "metadata": {"author": "John Doe", "stats": {"lines": 150}},
            "content": {
                "sections": {"introduction": "This is the introduction section"}
            },
        }

        assert filtered_data == expected_nested_data

    @pytest.mark.asyncio
    async def test_mixed_fields_and_fragments(self, mcp_server_e2e):
        """Test using both fields and fragments in the same subscription."""
        server = mcp_server_e2e
        notifications_received = []

        async def capture_notifications(connection_id: str, notification: dict):
            notifications_received.append((connection_id, notification))

        server.subscription_manager.set_notification_callback(capture_notifications)

        # Subscribe with both fields and fragments
        result = await server._handle_subscribe(
            {
                "uri": "config:///app",
                "fields": ["uri", "version"],  # Direct fields
                "fragments": {
                    "serverInfo": ["server.host", "server.port"],
                    "dbInfo": ["database.name", "database.pool_size"],
                },
            },
            "req_mixed",
            "client_mixed",
        )

        assert "result" in result

        # Mock resource with mixed structure
        async def mock_mixed_resource_data(uri: str):
            return {
                "uri": uri,
                "name": "app_config",
                "version": "2.1.0",
                "environment": "production",
                "server": {"host": "api.example.com", "port": 8080, "ssl": True},
                "database": {
                    "name": "prod_db",
                    "host": "db.example.com",
                    "pool_size": 20,
                    "timeout": 60,
                },
                "features": {"caching": True, "logging": True},
            }

        server.subscription_manager._get_resource_data = mock_mixed_resource_data

        # Trigger change
        change = ResourceChange(
            type=ResourceChangeType.UPDATED,
            uri="config:///app",
            timestamp=datetime.utcnow(),
        )
        await server.subscription_manager.process_resource_change(change)

        # Verify mixed selection worked correctly
        assert len(notifications_received) == 1
        client_id, notification = notifications_received[0]

        filtered_data = notification["params"]["data"]
        expected_mixed_data = {
            # Direct fields
            "uri": "config:///app",
            "version": "2.1.0",
            # Fragments
            "__serverInfo": {"server": {"host": "api.example.com", "port": 8080}},
            "__dbInfo": {"database": {"name": "prod_db", "pool_size": 20}},
        }

        assert filtered_data == expected_mixed_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
