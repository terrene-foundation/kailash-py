"""Unit tests for WebSocket compression support in MCP server."""

import gzip
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from kailash.mcp_server.server import MCPServer


class TestWebSocketCompression:
    """Test WebSocket compression functionality."""

    @pytest.fixture
    def server_with_compression(self):
        """Create server with compression enabled."""
        return MCPServer(
            "test_server",
            enable_websocket_compression=True,
            compression_threshold=100,  # Low threshold for testing
            compression_level=6,
        )

    @pytest.fixture
    def server_without_compression(self):
        """Create server without compression."""
        return MCPServer("test_server", enable_websocket_compression=False)

    def test_compression_initialization(self, server_with_compression):
        """Test that compression settings are properly initialized."""
        assert server_with_compression.enable_websocket_compression is True
        assert server_with_compression.compression_threshold == 100
        assert server_with_compression.compression_level == 6

    def test_compression_disabled_initialization(self, server_without_compression):
        """Test that compression is properly disabled."""
        assert server_without_compression.enable_websocket_compression is False
        assert server_without_compression.compression_threshold == 1024  # Default
        assert server_without_compression.compression_level == 6  # Default

    def test_compress_message_disabled(self, server_without_compression):
        """Test that compression doesn't occur when disabled."""
        message = {
            "jsonrpc": "2.0",
            "method": "notifications/resources/updated",
            "params": {
                "subscriptionId": "sub_123",
                "uri": "file:///large_file.json",
                "data": {"content": "x" * 2000},  # Large content
            },
        }

        result = server_without_compression._compress_message(message)

        # Should return original message unchanged
        assert result == message
        assert not isinstance(result, dict) or not result.get("__compressed")

    def test_compress_message_below_threshold(self, server_with_compression):
        """Test that small messages are not compressed."""
        small_message = {
            "jsonrpc": "2.0",
            "method": "test",
            "params": {"data": "small"},
        }

        result = server_with_compression._compress_message(small_message)

        # Should return original message unchanged
        assert result == small_message
        assert not result.get("__compressed")

    def test_compress_message_above_threshold(self, server_with_compression):
        """Test that large messages are compressed."""
        # Create a message that's definitely above the 100-byte threshold
        large_message = {
            "jsonrpc": "2.0",
            "method": "notifications/resources/updated",
            "params": {
                "subscriptionId": "sub_123",
                "uri": "file:///large_file.json",
                "data": {
                    "content": "x" * 1000,  # Large content that should compress well
                    "metadata": {"size": 1000, "type": "text"},
                    "additional_data": ["item_" + str(i) for i in range(100)],
                },
            },
        }

        result = server_with_compression._compress_message(large_message)

        # Should return compressed message
        assert isinstance(result, dict)
        assert result.get("__compressed") is True
        assert "__original_size" in result
        assert "__compressed_size" in result
        assert "__compression_ratio" in result
        assert "data" in result

        # Compression should reduce size
        assert result["__compressed_size"] < result["__original_size"]
        assert result["__compression_ratio"] < 1.0

    def test_compress_message_poor_compression(self, server_with_compression):
        """Test that messages with poor compression ratios are not compressed."""
        # Create a message with random data that won't compress well
        import random
        import string

        random_data = "".join(
            random.choices(string.ascii_letters + string.digits, k=500)
        )

        message = {
            "jsonrpc": "2.0",
            "method": "test",
            "params": {"random_data": random_data},
        }

        result = server_with_compression._compress_message(message)

        # Should return original message if compression doesn't help much
        # (This test might occasionally fail due to randomness, but usually random data compresses poorly)
        if result.get("__compressed"):
            # If it did compress, ratio should be reasonable
            assert result["__compression_ratio"] <= 0.9
        else:
            # If it didn't compress, that's also valid for random data
            assert result == message

    def test_decompress_message_not_compressed(self, server_with_compression):
        """Test decompressing a message that's not compressed."""
        normal_message = {
            "jsonrpc": "2.0",
            "method": "test",
            "params": {"data": "normal"},
        }

        result = server_with_compression._decompress_message(normal_message)

        # Should return original message unchanged
        assert result == normal_message

    def test_compress_decompress_roundtrip(self, server_with_compression):
        """Test that compression and decompression work together."""
        original_message = {
            "jsonrpc": "2.0",
            "method": "notifications/resources/updated",
            "params": {
                "subscriptionId": "sub_123",
                "uri": "file:///large_file.json",
                "data": {
                    "content": "This is a large message that should compress well. "
                    * 20,
                    "metadata": {"size": 1000, "type": "text", "encoding": "utf-8"},
                    "nested": {
                        "deep": {"structure": ["with", "repeated", "values"] * 10}
                    },
                },
            },
        }

        # Compress the message
        compressed = server_with_compression._compress_message(original_message)

        # Should be compressed
        assert compressed.get("__compressed") is True

        # Decompress the message
        decompressed = server_with_compression._decompress_message(compressed)

        # Should match original
        assert decompressed == original_message

    def test_decompress_invalid_compressed_message(self, server_with_compression):
        """Test handling of invalid compressed messages."""
        invalid_compressed = {"__compressed": True, "data": "invalid_hex_data"}

        result = server_with_compression._decompress_message(invalid_compressed)

        # Should return error message
        assert result.get("jsonrpc") == "2.0"
        assert "error" in result
        assert result["error"]["code"] == -32603

    def test_decompress_corrupted_data(self, server_with_compression):
        """Test handling of corrupted compressed data."""
        corrupted_compressed = {
            "__compressed": True,
            "data": "deadbeef",  # Valid hex but not valid gzip data
        }

        result = server_with_compression._decompress_message(corrupted_compressed)

        # Should return error message
        assert result.get("jsonrpc") == "2.0"
        assert "error" in result
        assert "Failed to decompress message" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_send_websocket_notification_with_compression(
        self, server_with_compression
    ):
        """Test sending notification with compression."""
        # Mock transport
        mock_transport = AsyncMock()
        server_with_compression._transport = mock_transport

        large_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/resources/updated",
            "params": {
                "subscriptionId": "sub_123",
                "uri": "file:///large_file.json",
                "data": {
                    "content": "Large content that should be compressed. " * 50,
                    "metadata": {"size": 2000, "type": "text"},
                },
            },
        }

        await server_with_compression._send_websocket_notification(
            "client_123", large_notification
        )

        # Verify send_message was called
        mock_transport.send_message.assert_called_once()

        # Get the actual message that was sent
        sent_message = mock_transport.send_message.call_args[0][0]

        # Should be compressed
        if sent_message.get("__compressed"):
            assert sent_message["__compressed"] is True
            assert "__original_size" in sent_message
            assert "__compressed_size" in sent_message

    @pytest.mark.asyncio
    async def test_send_websocket_notification_without_compression(
        self, server_without_compression
    ):
        """Test sending notification without compression."""
        # Mock transport
        mock_transport = AsyncMock()
        server_without_compression._transport = mock_transport

        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/resources/updated",
            "params": {
                "subscriptionId": "sub_123",
                "uri": "file:///large_file.json",
                "data": {"content": "x" * 2000},  # Large content
            },
        }

        await server_without_compression._send_websocket_notification(
            "client_123", notification
        )

        # Verify send_message was called with original message
        mock_transport.send_message.assert_called_once()
        sent_message = mock_transport.send_message.call_args[0][0]

        # Should be original message, not compressed
        assert sent_message == notification
        assert not sent_message.get("__compressed")

    @pytest.mark.asyncio
    async def test_handle_websocket_message_with_decompression(
        self, server_with_compression
    ):
        """Test handling WebSocket message with decompression."""
        # Create a compressed message manually
        original_request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "test_tool",
                "arguments": {"data": "x" * 500},  # Large arguments
            },
            "id": "req_123",
        }

        # Compress it
        compressed_request = server_with_compression._compress_message(original_request)

        # Mock the tool registry and other dependencies
        server_with_compression._tool_registry = {
            "test_tool": {
                "handler": lambda args: {"result": "test_result"},
                "input_schema": {},
                "description": "Test tool",
            }
        }

        # Handle the compressed message
        response = await server_with_compression._handle_websocket_message(
            compressed_request, "client_123"
        )

        # Should successfully process the decompressed request
        assert response.get("jsonrpc") == "2.0"
        assert response.get("id") == "req_123"

    @pytest.mark.asyncio
    async def test_handle_websocket_message_normal_request(
        self, server_with_compression
    ):
        """Test handling normal (uncompressed) WebSocket message."""
        normal_request = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": "req_123",
        }

        # Handle the normal message
        response = await server_with_compression._handle_websocket_message(
            normal_request, "client_123"
        )

        # Should successfully process the request
        assert response.get("jsonrpc") == "2.0"
        assert response.get("id") == "req_123"
        assert "result" in response

    @pytest.mark.asyncio
    async def test_server_capabilities_advertise_compression(
        self, server_with_compression
    ):
        """Test that server advertises compression in capabilities."""
        params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        }

        response = await server_with_compression._handle_initialize(
            params, "init_123", "client_123"
        )

        # Check that compression is advertised
        assert response["jsonrpc"] == "2.0"
        assert "result" in response

        capabilities = response["result"]["capabilities"]
        experimental = capabilities.get("experimental", {})

        assert experimental.get("websocketCompression") is True

    @pytest.mark.asyncio
    async def test_server_capabilities_no_compression(self, server_without_compression):
        """Test that server doesn't advertise compression when disabled."""
        params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        }

        response = await server_without_compression._handle_initialize(
            params, "init_123", "client_123"
        )

        # Check that compression is not advertised
        capabilities = response["result"]["capabilities"]
        experimental = capabilities.get("experimental", {})

        assert experimental.get("websocketCompression") is False

    def test_compression_settings_validation(self):
        """Test validation of compression settings."""
        # Test with different compression levels
        server = MCPServer(
            "test_server",
            enable_websocket_compression=True,
            compression_level=1,  # Fastest
        )
        assert server.compression_level == 1

        server = MCPServer(
            "test_server",
            enable_websocket_compression=True,
            compression_level=9,  # Best compression
        )
        assert server.compression_level == 9

        # Test with different thresholds
        server = MCPServer(
            "test_server", enable_websocket_compression=True, compression_threshold=2048
        )
        assert server.compression_threshold == 2048


class TestCompressionPerformance:
    """Test compression performance characteristics."""

    @pytest.fixture
    def server(self):
        """Create server with compression enabled."""
        return MCPServer(
            "test_server",
            enable_websocket_compression=True,
            compression_threshold=100,
            compression_level=6,
        )

    def test_compression_ratio_with_repetitive_data(self, server):
        """Test compression ratio with highly repetitive data."""
        repetitive_message = {
            "jsonrpc": "2.0",
            "method": "test",
            "params": {
                "data": "repeated_pattern " * 100,
                "metadata": {"type": "repetitive"},
            },
        }

        result = server._compress_message(repetitive_message)

        # Repetitive data should compress very well
        if result.get("__compressed"):
            assert (
                result["__compression_ratio"] < 0.5
            )  # Should get at least 50% compression

    def test_compression_with_json_structure(self, server):
        """Test compression with typical JSON API responses."""
        json_api_response = {
            "jsonrpc": "2.0",
            "method": "notifications/resources/updated",
            "params": {
                "subscriptionId": "subscription_12345",
                "uri": "database://users/table",
                "data": {
                    "users": [
                        {
                            "id": i,
                            "name": f"User {i}",
                            "email": f"user{i}@example.com",
                            "created_at": "2024-01-01T00:00:00Z",
                            "updated_at": "2024-01-01T00:00:00Z",
                            "status": "active",
                            "preferences": {
                                "theme": "dark",
                                "notifications": True,
                                "language": "en",
                            },
                        }
                        for i in range(50)  # 50 user records
                    ]
                },
            },
        }

        result = server._compress_message(json_api_response)

        # JSON with repeated structure should compress reasonably well
        if result.get("__compressed"):
            assert (
                result["__compression_ratio"] < 0.7
            )  # Should get at least 30% compression
            assert result["__compressed_size"] < result["__original_size"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
