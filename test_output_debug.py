"""Debug script to check node output structure."""

import asyncio

from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow import AsyncWorkflowBuilder


async def test_output_structure():
    """Test to see the actual output structure."""
    builder = AsyncWorkflowBuilder("debug_output")

    # Simple test code
    test_code = """
result = {
    "alerts": ["test alert"],
    "needs_alerting": True
}
"""

    builder.add_async_code("node1", test_code)

    workflow = builder.build()
    runtime = AsyncLocalRuntime()
    result = await runtime.execute_workflow_async(workflow, {})

    print("Full result:", result)
    print("Node1 output:", result["results"]["node1"])
    return result


if __name__ == "__main__":
    result = asyncio.run(test_output_structure())
