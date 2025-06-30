"""Debug script to test connection merging."""

import asyncio

from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow import AsyncWorkflowBuilder


async def test_connection_merging():
    """Test basic connection merging functionality."""
    builder = AsyncWorkflowBuilder("debug_test")

    # Simple test code
    test_code1 = """
result = {
    "alerts": ["test alert"],
    "needs_alerting": True
}
"""

    test_code2 = """
print("Input alerts:", alerts)
print("Input needs_alerting:", needs_alerting)

result = {
    "received_alerts": alerts if alerts else [],
    "received_alerting": needs_alerting if needs_alerting is not None else False
}
"""

    builder.add_async_code("node1", test_code1)
    builder.add_async_code("node2", test_code2)

    print("Adding first connection...")
    builder.add_connection("node1", "result.alerts", "node2", "alerts")

    print("Adding second connection...")
    builder.add_connection("node1", "result.needs_alerting", "node2", "needs_alerting")

    workflow = builder.build()

    # Check the graph connections
    graph = workflow.graph
    edge_data = graph.get_edge_data("node1", "node2")
    print("Edge data:", edge_data)

    runtime = AsyncLocalRuntime()
    result = await runtime.execute_workflow_async(workflow, {})

    print("Workflow result:", result)
    return result


if __name__ == "__main__":
    result = asyncio.run(test_connection_merging())
