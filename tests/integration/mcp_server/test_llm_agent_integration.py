"""Integration tests for LLMAgentNode MCP with real async scenarios."""

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from kailash.nodes.ai.llm_agent import LLMAgentNode


@pytest.mark.integration
class TestLLMAgentMCPRealIntegration:
    """Test MCP integration in real-world async scenarios."""

    def setup_method(self):
        """Set up test environment."""
        # Enable real MCP for tests
        os.environ["KAILASH_USE_REAL_MCP"] = "true"
        # Set Ollama URL for tests
        os.environ["OLLAMA_BASE_URL"] = "http://localhost:11435"
        self.node = LLMAgentNode(name="test_mcp_agent")

    def teardown_method(self):
        """Clean up test environment."""
        # Reset environment
        os.environ.pop("KAILASH_USE_REAL_MCP", None)
        os.environ.pop("OLLAMA_BASE_URL", None)

    def test_mcp_in_sync_context(self):
        """Test MCP works in pure synchronous context."""
        # This simulates the reported bug scenario
        result = self.node.execute(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
            mcp_servers=[
                {
                    "name": "test-server",
                    "transport": "stdio",
                    "command": "echo",
                    "args": ["test"],
                }
            ],
            mcp_context=["resource://test"],
        )

        # Should complete without async warnings
        assert result["success"] is True
        assert "response" in result

    @pytest.mark.asyncio
    async def test_mcp_in_async_context(self):
        """Test MCP works when called from async context."""

        # This tests the event loop detection
        async def run_in_async():
            return self.node.execute(
                provider="mock",
                model="gpt-4",
                messages=[{"role": "user", "content": "Hello async"}],
                mcp_servers=[
                    {
                        "name": "async-test-server",
                        "transport": "stdio",
                        "command": "echo",
                        "args": ["async test"],
                    }
                ],
            )

        result = await run_in_async()
        assert result["success"] is True

    def test_mcp_in_jupyter_like_environment(self):
        """Test MCP in Jupyter-like environment with existing event loop."""
        # Simulate Jupyter notebook environment
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def jupyter_simulation():
            # Create a background task to keep loop running
            async def background_task():
                while True:
                    await asyncio.sleep(0.1)

            # Start background task
            task = asyncio.create_task(background_task())

            try:
                # Now try to use MCP - this would fail with the bug
                def run_node():
                    return self.node.execute(
                        provider="mock",
                        model="gpt-4",
                        messages=[{"role": "user", "content": "Jupyter test"}],
                        mcp_servers=[
                            {
                                "name": "jupyter-server",
                                "transport": "stdio",
                                "command": "echo",
                                "args": ["jupyter"],
                            }
                        ],
                        mcp_context=["resource://jupyter"],
                        auto_discover_tools=True,
                    )

                result = await asyncio.get_event_loop().run_in_executor(None, run_node)

                assert result["success"] is True
                return result
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        try:
            result = loop.run_until_complete(jupyter_simulation())
            assert result is not None
        finally:
            loop.close()

    def test_mcp_concurrent_calls(self):
        """Test MCP handles concurrent calls correctly."""

        def make_call(i):
            return self.node.execute(
                provider="mock",
                model="gpt-4",
                messages=[{"role": "user", "content": f"Call {i}"}],
                mcp_servers=[
                    {
                        "name": f"server-{i}",
                        "transport": "stdio",
                        "command": "echo",
                        "args": [f"test-{i}"],
                    }
                ],
            )

        # Run multiple calls concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_call, i) for i in range(5)]
            results = [f.result() for f in futures]

        # All should succeed
        for i, result in enumerate(results):
            assert result["success"] is True, f"Call {i} failed"

    def test_mcp_timeout_behavior(self):
        """Test MCP timeout handling in real scenario."""
        # Test with a server that would timeout
        start = time.time()
        result = self.node.execute(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Timeout test"}],
            mcp_servers=[
                {
                    "name": "slow-server",
                    "transport": "stdio",
                    "command": "sleep",  # This will timeout
                    "args": ["5"],  # Reduced to 5 seconds for faster test
                    "timeout": 2,  # Set explicit timeout of 2 seconds
                }
            ],
            mcp_context=["resource://slow"],
            mcp_config={
                "connection_timeout": 3,
                "fallback_on_failure": True,
            },
        )
        elapsed = time.time() - start

        # Should timeout quickly and fallback gracefully
        assert result["success"] is True
        assert elapsed < 15, f"Took too long: {elapsed}s"  # Allow for MCP cleanup time

        # Check that it fell back to mock without MCP context
        # When MCP fails, the node should still work without MCP data

    def test_mcp_error_recovery(self):
        """Test MCP recovers from various error conditions."""
        # Test with invalid server config
        result = self.node.execute(
            provider="mock",
            model="gpt-4",
            messages=[{"role": "user", "content": "Error test"}],
            mcp_servers=[
                {
                    "name": "invalid-server",
                    "transport": "stdio",
                    "command": "/nonexistent/command",
                    "args": [],
                },
                {
                    "name": "http-server",
                    "transport": "http",
                    "url": "http://localhost:99999",  # Invalid port
                },
            ],
        )

        # Should still succeed with fallback
        assert result["success"] is True
        assert "response" in result

    @pytest.mark.requires_ollama
    def test_mcp_with_real_llm(self):
        """Test MCP with real LLM (Ollama) integration."""
        # First test without MCP to ensure Ollama is working
        test_result = self.node.execute(
            provider="ollama",
            model="llama3.2:1b",
            messages=[{"role": "user", "content": "Say 'hello'"}],
            generation_config={"temperature": 0, "max_tokens": 10},
        )

        if not test_result["success"]:
            pytest.skip(
                f"Ollama not available or configured: {test_result.get('error', 'Unknown error')}"
            )

        # Now test with MCP
        result = self.node.execute(
            provider="ollama",
            model="llama3.2:1b",
            messages=[{"role": "user", "content": "What is 2+2?"}],
            mcp_servers=[
                {
                    "name": "math-server",
                    "transport": "stdio",
                    "command": "echo",
                    "args": ["Math context: basic arithmetic"],
                }
            ],
            mcp_context=["resource://math/basic"],
            generation_config={"temperature": 0, "max_tokens": 50},
        )

        # Should get a real response
        assert result["success"] is True
        assert "response" in result
        assert "content" in result["response"]

        # Response should contain something about 4 or indicate calculation
        response_text = result["response"]["content"].lower()
        # More flexible assertion - Ollama might respond differently
        assert any(
            term in response_text for term in ["4", "four", "2+2", "equals", "answer"]
        )
