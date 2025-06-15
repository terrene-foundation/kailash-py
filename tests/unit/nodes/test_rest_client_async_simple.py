"""Simple async tests for RESTClient node (070-upgrade-components)."""

import asyncio
from unittest.mock import patch

import pytest

from kailash.nodes.api.rest import RESTClientNode


class TestRESTClientAsyncUpgrade:
    """Test async upgrades for RESTClientNode (070-upgrade-components)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = RESTClientNode(name="rest_client_async")

    @pytest.mark.asyncio
    async def test_rest_client_async_run_exists(self):
        """Test that RESTClientNode has async_run method."""
        assert hasattr(
            self.client, "async_run"
        ), "RESTClientNode missing async_run method"

    @pytest.mark.asyncio
    async def test_rest_client_async_fallback(self):
        """Test async execution with proper mocking."""
        # Mock the AsyncHTTPRequestNode that RESTClientNode uses internally
        from unittest.mock import AsyncMock

        with patch("kailash.nodes.api.http.AsyncHTTPRequestNode") as mock_async_http:
            mock_instance = AsyncMock()
            mock_async_http.return_value = mock_instance

            # Mock successful async HTTP response
            mock_instance.async_run.return_value = {
                "success": True,
                "status_code": 200,
                "content": {"test": "async works"},
                "headers": {"content-type": "application/json"},
                "response_time_ms": 100,
                "url": "https://api.example.com/test",
            }

            # Execute async_run
            result = await self.client.async_run(
                base_url="https://api.example.com", resource="test", method="GET"
            )

            # Verify results
            assert result["success"] is True
            assert result["status_code"] == 200
            assert result["data"]["test"] == "async works"

            # Verify async HTTP was called
            mock_instance.async_run.assert_called_once()
