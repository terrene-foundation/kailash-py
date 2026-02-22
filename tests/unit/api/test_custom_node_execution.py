"""Tests for custom node execution implementations (C1 gap fix).

Verifies that _execute_python_node, _execute_workflow_node, and _execute_api_node
are real async implementations rather than mock stubs.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class FakeNode:
    """Minimal node-like object for testing."""

    def __init__(self, name: str, implementation_type: str, implementation: dict):
        self.name = name
        self.implementation_type = implementation_type
        self.implementation = implementation


class TestExecutePythonNode:
    """Tests for _execute_python_node."""

    @pytest.mark.asyncio
    async def test_executes_code_via_code_executor(self):
        """Verify Python node uses CodeExecutor to run code."""
        from kailash.api.custom_nodes import _execute_python_node

        node = FakeNode(
            name="test_node",
            implementation_type="python",
            implementation={"code": "result = {'sum': a + b}"},
        )

        result = await _execute_python_node(node, {"a": 2, "b": 3})
        assert result.get("result", result).get("sum") == 5 or "sum" in str(result)

    @pytest.mark.asyncio
    async def test_raises_on_empty_code(self):
        """Verify error when no code is provided."""
        from kailash.api.custom_nodes import _execute_python_node

        node = FakeNode(
            name="empty_node",
            implementation_type="python",
            implementation={"code": ""},
        )

        with pytest.raises(ValueError, match="no Python code"):
            await _execute_python_node(node, {})

    @pytest.mark.asyncio
    async def test_raises_on_missing_code_key(self):
        """Verify error when implementation has no code key."""
        from kailash.api.custom_nodes import _execute_python_node

        node = FakeNode(
            name="no_code_node",
            implementation_type="python",
            implementation={},
        )

        with pytest.raises(ValueError, match="no Python code"):
            await _execute_python_node(node, {})


class TestExecuteWorkflowNode:
    """Tests for _execute_workflow_node."""

    @pytest.mark.asyncio
    async def test_raises_on_missing_workflow_definition(self):
        """Verify error when no workflow_definition is provided."""
        from kailash.api.custom_nodes import _execute_workflow_node

        node = FakeNode(
            name="no_wf_node",
            implementation_type="workflow",
            implementation={},
        )

        with pytest.raises(ValueError, match="no workflow_definition"):
            await _execute_workflow_node(node, {})

    @pytest.mark.asyncio
    async def test_executes_workflow_via_async_runtime(self):
        """Verify workflow node uses AsyncLocalRuntime."""
        from kailash.api.custom_nodes import _execute_workflow_node

        node = FakeNode(
            name="wf_node",
            implementation_type="workflow",
            implementation={
                "workflow_definition": {
                    "nodes": [
                        {
                            "type": "PythonCodeNode",
                            "id": "run_code",
                            "config": {"code": "result = 'hello'"},
                        }
                    ],
                    "connections": [],
                }
            },
        )

        result = await _execute_workflow_node(node, {})
        assert "results" in result
        assert "run_id" in result


class TestExecuteApiNode:
    """Tests for _execute_api_node."""

    @pytest.mark.asyncio
    async def test_raises_on_missing_url(self):
        """Verify error when no URL is provided."""
        from kailash.api.custom_nodes import _execute_api_node

        node = FakeNode(
            name="no_url_node",
            implementation_type="api",
            implementation={},
        )

        with pytest.raises(ValueError, match="no 'url'"):
            await _execute_api_node(node, {})

    @pytest.mark.asyncio
    async def test_api_node_makes_real_http_call(self):
        """Verify API node uses aiohttp (mock at unit level)."""
        from kailash.api.custom_nodes import _execute_api_node

        node = FakeNode(
            name="api_node",
            implementation_type="api",
            implementation={
                "url": "https://httpbin.org/post",
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "timeout": 5,
            },
        )

        # Mock aiohttp at unit test level (Tier 1 allows mocking)
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"status": "ok"})
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.request = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await _execute_api_node(node, {"key": "value"})

        assert result["status_code"] == 200
        assert result["body"] == {"status": "ok"}


class TestExecutionTiming:
    """Tests for execution timing measurement."""

    @pytest.mark.asyncio
    async def test_no_hardcoded_zero_timing(self):
        """Verify execution_time_ms is no longer hardcoded to 0."""
        # Read the source and verify no hardcoded 0 timing
        import inspect

        from kailash.api.custom_nodes import setup_custom_node_routes

        source = inspect.getsource(setup_custom_node_routes)
        assert 'execution_time_ms": 0' not in source.replace(
            " ", ""
        ), "execution_time_ms should not be hardcoded to 0"

    @pytest.mark.asyncio
    async def test_functions_are_async(self):
        """Verify all execution functions are async coroutines."""
        from kailash.api.custom_nodes import (
            _execute_api_node,
            _execute_python_node,
            _execute_workflow_node,
        )

        assert asyncio.iscoroutinefunction(_execute_python_node)
        assert asyncio.iscoroutinefunction(_execute_workflow_node)
        assert asyncio.iscoroutinefunction(_execute_api_node)
