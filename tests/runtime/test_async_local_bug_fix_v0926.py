"""
Regression test for v0.9.26: AsyncLocalRuntime parameter passing bug fix.

Bug History:
- Before v0.9.26: AsyncLocalRuntime called async_run() directly, bypassing config merge
- Impact: ALL DataFlow nodes failed because required parameters were not passed
- Root Cause: async_local.py:753 called node_instance.async_run() instead of execute_async()
- Fix: Changed to call execute_async() which merges node.config (base_async.py:190)
- Reference: LocalRuntime pattern at local.py:1362

This test ensures the bug stays fixed.
"""

import os
import tempfile
from pathlib import Path

import pytest
from kailash.runtime import AsyncLocalRuntime, LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Import DataFlow if available
try:
    import sys

    dataflow_path = (
        Path(__file__).parent.parent.parent / "apps" / "kailash-dataflow" / "src"
    )
    if str(dataflow_path) not in sys.path:
        sys.path.insert(0, str(dataflow_path))
    from dataflow import DataFlow

    DATAFLOW_AVAILABLE = True
except ImportError:
    DATAFLOW_AVAILABLE = False
    pytest.skip("DataFlow not available", allow_module_level=True)


@pytest.fixture
def test_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    db = DataFlow(f"sqlite:///{db_path}")

    @db.model
    class BugTestItem:
        name: str  # Required field for parameter passing test

    yield db

    # Cleanup
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.mark.asyncio
async def test_async_local_runtime_passes_config_parameters_bugfix_v0926(test_db):
    """
    CRITICAL REGRESSION TEST: AsyncLocalRuntime MUST pass node.config parameters.

    Before v0.9.26: This test would FAIL because AsyncLocalRuntime did not pass
    the 'name' parameter from node.config to the CreateNode.

    After v0.9.26: This test PASSES because AsyncLocalRuntime now correctly calls
    execute_async() which merges node.config before execution.

    This test ensures the bug stays fixed in future versions.
    """
    # Build workflow with configured parameter
    workflow = WorkflowBuilder()
    workflow.add_node(
        "BugTestItemCreateNode",
        "create_test",
        {"name": "AsyncLocalRuntime Regression Test"},  # This MUST be passed to node
    )

    # Execute with AsyncLocalRuntime
    runtime = AsyncLocalRuntime()
    result = await runtime.execute_workflow_async(workflow.build(), inputs={})

    # CRITICAL ASSERTION: Node MUST have received the 'name' parameter
    created_record = result["results"]["create_test"]
    assert "name" in created_record, (
        "AsyncLocalRuntime MUST pass node.config parameters to async_run(). "
        f"Bug regression detected! Received: {created_record}"
    )
    assert created_record["name"] == "AsyncLocalRuntime Regression Test", (
        f"Parameter value mismatch. Expected 'AsyncLocalRuntime Regression Test', "
        f"got '{created_record['name']}'"
    )


@pytest.mark.asyncio
async def test_async_local_runtime_matches_local_runtime_behavior(test_db):
    """
    Verify AsyncLocalRuntime and LocalRuntime have identical parameter passing behavior.

    This ensures consistency across both runtime implementations.
    """
    # Test with LocalRuntime
    local_workflow = WorkflowBuilder()
    local_workflow.add_node(
        "BugTestItemCreateNode", "create_local", {"name": "LocalRuntime Test"}
    )

    local_runtime = LocalRuntime()
    local_results, _ = local_runtime.execute(local_workflow.build())
    local_record = local_results["create_local"]

    # Test with AsyncLocalRuntime
    async_workflow = WorkflowBuilder()
    async_workflow.add_node(
        "BugTestItemCreateNode", "create_async", {"name": "AsyncLocalRuntime Test"}
    )

    async_runtime = AsyncLocalRuntime()
    async_results = await async_runtime.execute_workflow_async(
        async_workflow.build(), inputs={}
    )
    async_record = async_results["results"]["create_async"]

    # Both should successfully create records with configured names
    assert local_record["name"] == "LocalRuntime Test"
    assert async_record["name"] == "AsyncLocalRuntime Test"

    # Both should have same field structure
    assert set(local_record.keys()) == set(
        async_record.keys()
    ), "LocalRuntime and AsyncLocalRuntime should produce identical result structure"
