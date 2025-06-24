"""Unit tests for AsyncPythonCodeNode."""

import asyncio

import pytest

from kailash.nodes.code.async_python import AsyncPythonCodeNode
from kailash.sdk_exceptions import (
    NodeConfigurationError,
    NodeExecutionError,
    SafetyViolationError,
)
from kailash.security import ExecutionTimeoutError


class TestAsyncPythonCodeNode:
    """Test AsyncPythonCodeNode functionality."""

    @pytest.mark.asyncio
    async def test_basic_async_execution(self):
        """Test basic async code execution."""
        node = AsyncPythonCodeNode(
            code="""
import asyncio

await asyncio.sleep(0.01)  # Short sleep
result = {"value": 42, "status": "completed"}
"""
        )

        result = await node.execute_async()
        assert result["value"] == 42
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_async_with_inputs(self):
        """Test async code with input parameters."""
        node = AsyncPythonCodeNode(
            code="""
import asyncio

# Access input parameters
multiplier = input_value * 2

# Simulate async work
await asyncio.sleep(0.01)

result = {
    "original": input_value,
    "multiplied": multiplier,
    "async": True
}
"""
        )

        result = await node.execute_async(input_value=10)
        assert result["original"] == 10
        assert result["multiplied"] == 20
        assert result["async"] is True

    @pytest.mark.asyncio
    async def test_concurrent_tasks(self):
        """Test running multiple async tasks."""
        node = AsyncPythonCodeNode(
            code="""
import asyncio

async def process_item(item):
    await asyncio.sleep(0.01)
    return item * 2

# Process multiple items concurrently
items = [1, 2, 3, 4, 5]
tasks = [asyncio.create_task(process_item(item)) for item in items]
results = await asyncio.gather(*tasks)

result = {
    "processed": results,
    "count": len(results)
}
""",
            max_concurrent_tasks=10,
        )

        result = await node.execute_async()
        assert result["processed"] == [2, 4, 6, 8, 10]
        assert result["count"] == 5

    @pytest.mark.asyncio
    async def test_timeout_enforcement(self):
        """Test that timeout is enforced."""
        node = AsyncPythonCodeNode(
            code="""
import asyncio

# This should timeout
await asyncio.sleep(5)
result = {"should_not_reach": True}
""",
            timeout=0.1,  # 100ms timeout
        )

        with pytest.raises(NodeExecutionError) as exc_info:
            await node.execute_async()

        assert "timeout" in str(exc_info.value).lower()

    def test_blocked_imports(self):
        """Test that dangerous imports are blocked."""
        with pytest.raises(SafetyViolationError) as exc_info:
            AsyncPythonCodeNode(
                code="""
import subprocess
result = {}
"""
            )

        assert "subprocess" in str(exc_info.value)

    def test_blocked_operations(self):
        """Test that dangerous operations are blocked."""
        with pytest.raises(SafetyViolationError) as exc_info:
            AsyncPythonCodeNode(
                code="""
import asyncio

# Try to use eval (blocked)
# Note: eval function is blocked by safety checker
result = __builtins__['eval']("1 + 1")
"""
            )

        assert "eval" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_uuid_support(self):
        """Test that uuid module is supported."""
        node = AsyncPythonCodeNode(
            code="""
import uuid

# Generate a UUID
unique_id = str(uuid.uuid4())

result = {
    "id": unique_id,
    "has_hyphens": "-" in unique_id
}
"""
        )

        result = await node.execute_async()
        assert "id" in result
        assert result["has_hyphens"] is True
        assert len(result["id"]) == 36  # Standard UUID length

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in async code."""
        node = AsyncPythonCodeNode(
            code="""
import asyncio

# This will raise an error
x = 1 / 0
result = {"should_not_reach": True}
"""
        )

        with pytest.raises(NodeExecutionError) as exc_info:
            await node.execute_async()

        assert "division by zero" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_from_async_function(self):
        """Test creating node from async function."""

        async def my_async_processor(data: int) -> dict:
            import asyncio

            await asyncio.sleep(0.01)
            result = {"processed": data * 3}
            return result

        node = AsyncPythonCodeNode.from_function(my_async_processor)

        result = await node.execute_async(data=7)
        assert result["processed"] == 21

    def test_from_sync_function_fails(self):
        """Test that sync functions are rejected."""

        def sync_function(data):
            return {"data": data}

        with pytest.raises(ValueError) as exc_info:
            AsyncPythonCodeNode.from_function(sync_function)

        assert "must be async" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_complex_async_workflow(self):
        """Test a more complex async workflow."""
        node = AsyncPythonCodeNode(
            code="""
import asyncio
import json
from datetime import datetime

async def fetch_data(item_id):
    # Simulate API call
    await asyncio.sleep(0.02)
    return {
        "id": item_id,
        "data": f"Data for item {item_id}",
        "timestamp": datetime.now().isoformat()
    }

# Fetch multiple items
item_ids = [1, 2, 3]
tasks = [fetch_data(item_id) for item_id in item_ids]
fetched_data = await asyncio.gather(*tasks)

# Process results
result = {
    "items": fetched_data,
    "count": len(fetched_data),
    "success": all(item["data"] for item in fetched_data)
}
""",
            timeout=1.0,  # 1 second timeout
        )

        result = await node.execute_async()
        assert result["count"] == 3
        assert result["success"] is True
        assert len(result["items"]) == 3

    @pytest.mark.asyncio
    async def test_resource_limits(self):
        """Test resource limit enforcement."""
        node = AsyncPythonCodeNode(
            code="""
import asyncio

# Try to create too many tasks
tasks = []
for i in range(100):  # Try to create 100 tasks
    tasks.append(asyncio.create_task(asyncio.sleep(0.01)))

await asyncio.gather(*tasks)
result = {"completed": True}
""",
            max_concurrent_tasks=5,  # Limit to 5 concurrent tasks
        )

        # Should still complete but with limited concurrency
        result = await node.execute_async()
        assert result["completed"] is True
