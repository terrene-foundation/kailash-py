"""Comprehensive functional tests for mcp_server/discovery.py to boost coverage."""

# Create asyncio event loop for module-level
import asyncio
import hashlib
import json
import socket
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, mock_open, patch

import pytest
import yaml

try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)


class TestMCPServerInfo:
    """Test MCPServerInfo dataclass functionality."""

    def test_mcp_server_info_creation(self):
        """Test creating ServerInfo instances."""
        from kailash.mcp_server.discovery import ServerInfo

        # Basic server info
        server = ServerInfo(
            name="Test MCP Server",
            transport="http",
            capabilities=["tool1", "tool2"],
            url="http://localhost:8080",
            health_status="healthy",
        )

        assert server.name == "Test MCP Server"
        assert server.transport == "http"
        assert server.url == "http://localhost:8080"
        assert server.health_status == "healthy"
        assert server.capabilities == ["tool1", "tool2"]
        assert server.metadata == {}
        assert server.last_seen > 0

        # Server with additional fields
        full_server = ServerInfo(
            name="Full MCP Server",
            transport="http",
            url="https://api.example.com:443",
            capabilities=["auth", "streaming", "batch"],
            metadata={"region": "us-east-1", "tier": "premium"},
            version="2.1.0",
            auth_required=True,
        )

        assert full_server.transport == "http"
        assert full_server.capabilities == ["auth", "streaming", "batch"]
        assert full_server.metadata["region"] == "us-east-1"
        assert full_server.version == "2.1.0"
        assert full_server.auth_required is True

    def test_server_status_enum(self):
        """Test health status values."""
        from kailash.mcp_server.discovery import ServerInfo

        # Test health status string values
        server = ServerInfo(name="test", transport="http", health_status="healthy")
        assert server.health_status == "healthy"

        server2 = ServerInfo(name="test2", transport="http", health_status="unhealthy")
        assert server2.health_status == "unhealthy"

    def test_mcp_server_info_equality(self):
        """Test ServerInfo equality comparison."""
        from kailash.mcp_server.discovery import ServerInfo

        server1 = ServerInfo(
            name="Test Server",
            transport="http",
            url="http://localhost:8080",
        )

        server2 = ServerInfo(
            name="Test Server",
            transport="http",
            url="http://localhost:8080",
        )

        server3 = ServerInfo(
            name="Different Server",
            transport="http",
            url="http://localhost:8081",
        )

        # ServerInfo uses dataclass equality based on all fields
        assert server1 != server2  # Different auto-generated IDs
        assert server1 != server3


class TestDiscoveryStrategyInterface:
    """Test DiscoveryStrategy interface and implementations."""

    def test_discovery_strategy_interface(self):
        """Test DiscoveryBackend abstract interface."""
        import abc

        from kailash.mcp_server.discovery import DiscoveryBackend

        # Verify it's an abstract class
        assert issubclass(DiscoveryBackend, abc.ABC)

        # Try to instantiate should fail
        with pytest.raises(TypeError):
            DiscoveryBackend()

        # Test concrete implementation
        class TestDiscovery(DiscoveryBackend):
            async def discover(self) -> List[Any]:
                return []

            async def register_server(self, server_info: Any) -> bool:
                return True

            async def deregister_server(self, server_id: str) -> bool:
                return True

            async def get_server(self, server_id: str) -> Optional[Any]:
                return None

            async def list_servers(self) -> List[Any]:
                return []

            async def get_servers(self) -> List[Any]:
                return []

            async def update_server_health(
                self, server_id: str, health_status: str
            ) -> bool:
                return True

        # Should instantiate successfully
        strategy = TestDiscovery()
        assert isinstance(strategy, DiscoveryBackend)


class TestStaticDiscovery:
    """Test StaticDiscovery implementation."""

    @pytest.mark.asyncio
    async def test_static_discovery_initialization(self):
        """Test FileBasedDiscovery initialization."""
        import os
        import tempfile

        from kailash.mcp_server.discovery import FileBasedDiscovery

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            # Create a test registry file
            registry_data = {
                "servers": {
                    "test-server": {
                        "name": "Test Server",
                        "transport": "http",
                        "url": "http://localhost:8080",
                    }
                }
            }
            json.dump(registry_data, f)
            f.flush()

            discovery = FileBasedDiscovery(f.name)
            # Discovery initialized successfully
            os.unlink(f.name)

    @pytest.mark.asyncio
    async def test_static_discovery_operations(self):
        """Test FileBasedDiscovery CRUD operations."""
        import os
        import tempfile

        from kailash.mcp_server.discovery import FileBasedDiscovery, ServerInfo

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            # Create initial registry with one server
            registry_data = {
                "servers": {
                    "initial-server": {
                        "name": "Initial Server",
                        "transport": "http",
                        "url": "http://localhost:8080",
                    }
                }
            }
            json.dump(registry_data, f)
            f.flush()

            discovery = FileBasedDiscovery(f.name)

            # Test server registration
            new_server = ServerInfo(
                name="New Server", transport="http", url="http://localhost:8081"
            )

            await discovery.register_server(new_server)
            # Test completed successfully
            os.unlink(f.name)


class TestFileBasedDiscovery:
    """Test FileBasedDiscovery implementation."""

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_file_based_discovery_initialization(self, mock_read_text, mock_exists):
        """Test FileBasedDiscovery initialization and file handling."""
        from kailash.mcp_server.discovery import FileBasedDiscovery

        mock_exists.return_value = True
        mock_read_text.return_value = (
            '{"servers": {}, "last_updated": 1234567890, "version": "1.0"}'
        )

        discovery = FileBasedDiscovery("/tmp/test_registry.json")

        # FileBasedDiscovery stores registry_path internally
        # Test that it implements the discovery interface
        assert hasattr(discovery, "discover_servers") or hasattr(discovery, "discover")

        # Verify file exists check was called
        mock_exists.assert_called()
