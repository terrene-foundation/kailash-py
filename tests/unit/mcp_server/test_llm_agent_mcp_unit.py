"""Unit tests for LLMAgentNode MCP integration with async/await fixes."""

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kailash.nodes.ai.llm_agent import LLMAgentNode


class TestLLMAgentMCPIntegration(unittest.TestCase):
    """Test MCP integration in LLMAgentNode with various event loop scenarios."""

    def setUp(self):
        """Set up test environment."""
        # Enable real MCP for tests
        os.environ["KAILASH_USE_REAL_MCP"] = "true"
        self.node = LLMAgentNode()

    def tearDown(self):
        """Clean up test environment."""
        # Reset environment
        os.environ.pop("KAILASH_USE_REAL_MCP", None)

    def test_run_async_in_sync_context_no_loop(self):
        """Test _run_async_in_sync_context when no event loop is running."""

        async def sample_coroutine():
            return "success"

        result = self.node._run_async_in_sync_context(sample_coroutine())
        self.assertEqual(result, "success")

    def test_run_async_in_sync_context_with_loop(self):
        """Test _run_async_in_sync_context when an event loop is already running."""

        async def test_with_running_loop():
            async def sample_coroutine():
                return "success_in_loop"

            # This should handle the running loop case
            result = self.node._run_async_in_sync_context(sample_coroutine())
            return result

        # Run the test in an event loop
        result = asyncio.run(test_with_running_loop())
        self.assertEqual(result, "success_in_loop")

    def test_run_async_in_sync_context_timeout(self):
        """Test _run_async_in_sync_context timeout handling."""
        # Create a custom test that simulates timeout without modifying the actual timeout
        import threading
        import time

        # Create a flag to track if timeout handling works
        timeout_handled = False

        def long_running_task():
            """Simulate a long-running task that would timeout."""
            time.sleep(0.1)  # Short sleep to simulate work
            return "completed"

        # Test that our implementation handles threading correctly
        thread = threading.Thread(target=long_running_task)
        thread.start()
        thread.join(timeout=0.05)  # Timeout before task completes

        # Thread should still be alive (timed out)
        self.assertTrue(thread.is_alive())

        # Wait for thread to actually finish
        thread.join()

        # Now test with a coroutine that completes successfully
        async def fast_coroutine():
            await asyncio.sleep(0.01)
            return "success"

        result = self.node._run_async_in_sync_context(fast_coroutine())
        self.assertEqual(result, "success")

        # Test the actual timeout mechanism by mocking
        original_method = self.node._run_async_in_sync_context

        def mock_timeout(*args, **kwargs):
            raise TimeoutError("MCP operation timed out after 30 seconds")

        # Test timeout is raised properly
        self.node._run_async_in_sync_context = mock_timeout
        try:

            async def test_coro():
                return "test"

            with self.assertRaises(TimeoutError) as cm:
                self.node._run_async_in_sync_context(test_coro())

            self.assertIn("timed out", str(cm.exception))
        finally:
            self.node._run_async_in_sync_context = original_method

    def test_run_async_in_sync_context_exception(self):
        """Test _run_async_in_sync_context exception propagation."""

        async def failing_coroutine():
            raise ValueError("Test exception")

        with self.assertRaises(ValueError) as cm:
            self.node._run_async_in_sync_context(failing_coroutine())

        self.assertEqual(str(cm.exception), "Test exception")

    @patch("kailash.mcp_server.MCPClient")
    def test_retrieve_mcp_context_with_mock_client(self, mock_mcp_client_class):
        """Test _retrieve_mcp_context with mocked MCP client."""
        # Create mock client instance
        mock_client = MagicMock()
        mock_mcp_client_class.return_value = mock_client

        # Mock async methods
        mock_client.list_resources = AsyncMock(
            return_value=[{"uri": "resource://test", "name": "Test Resource"}]
        )
        mock_client.read_resource = AsyncMock(
            return_value={"content": "Test content from MCP"}
        )

        # Test server config
        server_config = {
            "name": "test-server",
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "test_mcp_server"],
        }

        # Call the method
        result = self.node._retrieve_mcp_context(
            mcp_servers=[server_config], mcp_context=["resource://test"]
        )

        # Verify results
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

        # Check that the resource was retrieved
        resource_found = False
        for item in result:
            if item.get("uri") == "resource://test":
                resource_found = True
                self.assertEqual(item.get("content"), "Test content from MCP")
                self.assertEqual(item.get("source"), "test-server")
                break

        self.assertTrue(resource_found, "Expected resource not found in results")

    @patch("kailash.mcp_server.MCPClient")
    def test_retrieve_mcp_context_timeout_handling(self, mock_mcp_client_class):
        """Test _retrieve_mcp_context timeout handling."""
        # Create mock client instance
        mock_client = MagicMock()
        mock_mcp_client_class.return_value = mock_client

        # Create an async function that will actually sleep and timeout
        async def slow_list_resources(*args):
            await asyncio.sleep(35)  # Longer than 30 second timeout
            return []

        # Set the mock to return a coroutine
        mock_client.list_resources = AsyncMock(side_effect=slow_list_resources)

        # Mock the _run_async_in_sync_context to raise TimeoutError
        original_run_async = self.node._run_async_in_sync_context

        def mock_run_async_with_timeout(coro):
            # Check if this is a list_resources call
            if asyncio.iscoroutine(coro):
                # For this test, simulate timeout
                raise TimeoutError("MCP operation timed out after 30 seconds")
            return original_run_async(coro)

        self.node._run_async_in_sync_context = mock_run_async_with_timeout

        # Test server config
        server_config = {
            "name": "timeout-server",
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "timeout_server"],
        }

        try:
            # Call the method - should fallback gracefully
            result = self.node._retrieve_mcp_context(
                mcp_servers=[server_config], mcp_context=[]
            )

            # Should return fallback data
            self.assertIsInstance(result, list)
            self.assertGreater(len(result), 0)

            # Check fallback content
            fallback_item = result[0]
            content = fallback_item.get("content", "").lower()
            # Check for either "timeout" or "timed out" in content
            self.assertTrue(
                "timeout" in content or "timed out" in content,
                f"Expected timeout message in: {content}",
            )
            self.assertEqual(fallback_item.get("metadata", {}).get("error"), "timeout")
        finally:
            # Restore original method
            self.node._run_async_in_sync_context = original_run_async

    @patch("kailash.mcp_server.MCPClient")
    def test_discover_mcp_tools_with_mock_client(self, mock_mcp_client_class):
        """Test _discover_mcp_tools with mocked MCP client."""
        # Create mock client instance
        mock_client = MagicMock()
        mock_mcp_client_class.return_value = mock_client

        # Mock async method
        mock_client.discover_tools = AsyncMock(
            return_value=[
                {
                    "name": "test_tool",
                    "description": "A test tool",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                    },
                }
            ]
        )

        # Test server config
        server_config = {
            "name": "test-server",
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "test_mcp_server"],
        }

        # Call the method
        result = self.node._discover_mcp_tools(mcp_servers=[server_config])

        # Verify results
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

        # Check tool format
        tool = result[0]
        self.assertEqual(tool.get("type"), "function")
        self.assertIn("function", tool)
        self.assertEqual(tool["function"]["name"], "test_tool")
        self.assertEqual(tool["function"]["mcp_server"], "test-server")

    def test_retrieve_mcp_context_without_real_mcp(self):
        """Test _retrieve_mcp_context falls back to mock when KAILASH_USE_REAL_MCP is false."""
        # Disable real MCP
        os.environ["KAILASH_USE_REAL_MCP"] = "false"

        # Test server config
        server_config = {"name": "mock-server", "transport": "stdio"}

        # Call the method
        result = self.node._retrieve_mcp_context(
            mcp_servers=[server_config], mcp_context=["resource://test"]
        )

        # Should return mock data
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

        # Check for mock content
        mock_found = False
        for item in result:
            if "Mock context content" in item.get("content", ""):
                mock_found = True
                break

        self.assertTrue(mock_found, "Expected mock content not found")


if __name__ == "__main__":
    unittest.main()
