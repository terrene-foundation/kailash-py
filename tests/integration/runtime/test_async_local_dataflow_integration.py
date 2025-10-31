"""
Integration tests for AsyncLocalRuntime with DataFlow nodes (v0.9.26 bug fix).

Bug History:
- Before v0.9.26: AsyncLocalRuntime didn't pass node.config to DataFlow nodes
- Impact: ALL DataFlow CRUD operations failed (CreateNode, UpdateNode, etc.)
- Root Cause: async_local.py:753 called async_run() directly, bypassing execute_async()
- Fix: Changed to call execute_async() which merges node.config (base_async.py:190)

These integration tests verify:
1. DataFlow CreateNode works with AsyncLocalRuntime
2. DataFlow UpdateNode works with AsyncLocalRuntime
3. DataFlow DeleteNode works with AsyncLocalRuntime
4. DataFlow ListNode works with AsyncLocalRuntime
5. End-to-end CRUD workflows work correctly
6. AsyncLocalRuntime matches LocalRuntime behavior with DataFlow

Test Tier: 2 (Integration)
Policy: NO MOCKING - Uses real SQLite database
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
        Path(__file__).parent.parent.parent.parent / "apps" / "kailash-dataflow" / "src"
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
    class TestItem:
        id: str
        name: str
        status: str = "active"

    yield db

    # Cleanup
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dataflow_create_node_with_async_runtime(test_db):
    """
    CRITICAL: DataFlow CreateNode MUST work with AsyncLocalRuntime.

    Bug History:
    - Before v0.9.26: CreateNode failed because node.config not passed
    - Error: "Required field 'name' missing"
    - After v0.9.26: Parameters passed correctly

    This test ensures CreateNode receives all configured parameters.
    """
    workflow = WorkflowBuilder()
    workflow.add_node(
        "TestItemCreateNode",
        "create_item",
        {"id": "test-item-001", "name": "Integration Test Item", "status": "active"},
    )

    # Execute with AsyncLocalRuntime
    runtime = AsyncLocalRuntime()
    result = await runtime.execute_workflow_async(workflow.build(), inputs={})

    # Verify item was created with correct parameters
    created_item = result["results"]["create_item"]
    assert (
        created_item["id"] == "test-item-001"
    ), "AsyncLocalRuntime MUST pass 'id' from node.config to CreateNode"
    assert (
        created_item["name"] == "Integration Test Item"
    ), "AsyncLocalRuntime MUST pass 'name' from node.config to CreateNode"
    assert (
        created_item["status"] == "active"
    ), "AsyncLocalRuntime MUST pass 'status' from node.config to CreateNode"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dataflow_update_node_with_async_runtime(test_db):
    """
    CRITICAL: DataFlow UpdateNode MUST work with AsyncLocalRuntime.

    Bug History:
    - Before v0.9.26: UpdateNode failed because filter/fields not passed
    - After v0.9.26: Parameters passed correctly

    UpdateNode requires both 'filter' and 'fields' from node.config.
    """
    # First create an item
    create_workflow = WorkflowBuilder()
    create_workflow.add_node(
        "TestItemCreateNode",
        "create",
        {"id": "test-item-002", "name": "Original Name", "status": "active"},
    )

    runtime = AsyncLocalRuntime()
    await runtime.execute_workflow_async(create_workflow.build(), inputs={})

    # Now update the item
    update_workflow = WorkflowBuilder()
    update_workflow.add_node(
        "TestItemUpdateNode",
        "update",
        {
            "filter": {"id": "test-item-002"},
            "fields": {"name": "Updated Name", "status": "completed"},
        },
    )

    result = await runtime.execute_workflow_async(update_workflow.build(), inputs={})

    # Verify update succeeded
    update_result = result["results"]["update"]
    assert (
        update_result["updated"] >= 1
    ), "AsyncLocalRuntime MUST pass 'filter' and 'fields' to UpdateNode"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dataflow_list_node_with_async_runtime(test_db):
    """
    CRITICAL: DataFlow ListNode MUST work with AsyncLocalRuntime.

    Bug History:
    - Before v0.9.26: ListNode failed when filter passed via node.config
    - After v0.9.26: Filter parameters passed correctly

    ListNode can receive optional 'filter' from node.config.
    """
    # Create test items
    runtime = AsyncLocalRuntime()

    create_workflow = WorkflowBuilder()
    create_workflow.add_node(
        "TestItemCreateNode",
        "create1",
        {"id": "test-item-003", "name": "Active Item", "status": "active"},
    )
    create_workflow.add_node(
        "TestItemCreateNode",
        "create2",
        {"id": "test-item-004", "name": "Completed Item", "status": "completed"},
    )

    await runtime.execute_workflow_async(create_workflow.build(), inputs={})

    # List all items
    list_all_workflow = WorkflowBuilder()
    list_all_workflow.add_node("TestItemListNode", "list_all", {})

    result = await runtime.execute_workflow_async(list_all_workflow.build(), inputs={})
    all_items = result["results"]["list_all"]["items"]
    assert len(all_items) >= 2, "Should have at least 2 items"

    # List with filter
    list_filtered_workflow = WorkflowBuilder()
    list_filtered_workflow.add_node(
        "TestItemListNode", "list_filtered", {"filter": {"status": "active"}}
    )

    result = await runtime.execute_workflow_async(
        list_filtered_workflow.build(), inputs={}
    )
    filtered_items = result["results"]["list_filtered"]["items"]
    assert (
        len(filtered_items) >= 1
    ), "AsyncLocalRuntime MUST pass 'filter' from node.config to ListNode"
    assert all(
        item["status"] == "active" for item in filtered_items
    ), "Filter should only return active items"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dataflow_delete_node_with_async_runtime(test_db):
    """
    CRITICAL: DataFlow DeleteNode MUST work with AsyncLocalRuntime.

    Bug History:
    - Before v0.9.26: DeleteNode failed because 'filter' not passed
    - After v0.9.26: Filter parameter passed correctly

    DeleteNode requires 'filter' from node.config.
    """
    # Create test item
    runtime = AsyncLocalRuntime()

    create_workflow = WorkflowBuilder()
    create_workflow.add_node(
        "TestItemCreateNode",
        "create",
        {"id": "test-item-005", "name": "To Be Deleted", "status": "active"},
    )

    await runtime.execute_workflow_async(create_workflow.build(), inputs={})

    # Delete the item
    delete_workflow = WorkflowBuilder()
    delete_workflow.add_node(
        "TestItemDeleteNode", "delete", {"filter": {"id": "test-item-005"}}
    )

    result = await runtime.execute_workflow_async(delete_workflow.build(), inputs={})

    # Verify deletion
    delete_result = result["results"]["delete"]
    assert (
        delete_result["deleted"] >= 1
    ), "AsyncLocalRuntime MUST pass 'filter' from node.config to DeleteNode"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dataflow_crud_workflow_async_runtime(test_db):
    """
    End-to-end CRUD workflow with AsyncLocalRuntime.

    Verifies complete workflow with Create → Read → Update → Delete works
    correctly when all nodes receive their configured parameters.
    """
    runtime = AsyncLocalRuntime()

    # Create
    create_workflow = WorkflowBuilder()
    create_workflow.add_node(
        "TestItemCreateNode",
        "create",
        {"id": "test-item-006", "name": "Full CRUD Test", "status": "pending"},
    )

    create_result = await runtime.execute_workflow_async(
        create_workflow.build(), inputs={}
    )
    created_item = create_result["results"]["create"]
    assert created_item["id"] == "test-item-006"
    assert created_item["status"] == "pending"

    # Read (List)
    list_workflow = WorkflowBuilder()
    list_workflow.add_node(
        "TestItemListNode", "list", {"filter": {"id": "test-item-006"}}
    )

    list_result = await runtime.execute_workflow_async(list_workflow.build(), inputs={})
    items = list_result["results"]["list"]["items"]
    assert len(items) == 1
    assert items[0]["name"] == "Full CRUD Test"

    # Update
    update_workflow = WorkflowBuilder()
    update_workflow.add_node(
        "TestItemUpdateNode",
        "update",
        {"filter": {"id": "test-item-006"}, "fields": {"status": "completed"}},
    )

    update_result = await runtime.execute_workflow_async(
        update_workflow.build(), inputs={}
    )
    assert update_result["results"]["update"]["updated"] >= 1

    # Verify update
    verify_workflow = WorkflowBuilder()
    verify_workflow.add_node(
        "TestItemListNode", "verify", {"filter": {"id": "test-item-006"}}
    )

    verify_result = await runtime.execute_workflow_async(
        verify_workflow.build(), inputs={}
    )
    updated_item = verify_result["results"]["verify"]["items"][0]
    assert updated_item["status"] == "completed"

    # Delete
    delete_workflow = WorkflowBuilder()
    delete_workflow.add_node(
        "TestItemDeleteNode", "delete", {"filter": {"id": "test-item-006"}}
    )

    delete_result = await runtime.execute_workflow_async(
        delete_workflow.build(), inputs={}
    )
    assert delete_result["results"]["delete"]["deleted"] >= 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_async_runtime_matches_local_runtime_dataflow(test_db):
    """
    AsyncLocalRuntime and LocalRuntime MUST produce identical results with DataFlow.

    This test ensures parameter passing behavior is consistent between both runtimes.
    """
    # Test with LocalRuntime
    local_workflow = WorkflowBuilder()
    local_workflow.add_node(
        "TestItemCreateNode",
        "create_local",
        {"id": "test-item-007", "name": "LocalRuntime Test", "status": "active"},
    )

    local_runtime = LocalRuntime()
    local_results, _ = local_runtime.execute(local_workflow.build())
    local_item = local_results["create_local"]

    # Test with AsyncLocalRuntime
    async_workflow = WorkflowBuilder()
    async_workflow.add_node(
        "TestItemCreateNode",
        "create_async",
        {"id": "test-item-008", "name": "AsyncLocalRuntime Test", "status": "active"},
    )

    async_runtime = AsyncLocalRuntime()
    async_results = await async_runtime.execute_workflow_async(
        async_workflow.build(), inputs={}
    )
    async_item = async_results["results"]["create_async"]

    # Compare results structure
    assert local_item["name"] == "LocalRuntime Test"
    assert async_item["name"] == "AsyncLocalRuntime Test"
    assert local_item["status"] == async_item["status"] == "active"

    # Both should have same field structure
    assert set(local_item.keys()) == set(
        async_item.keys()
    ), "LocalRuntime and AsyncLocalRuntime should produce identical result structure"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_parameter_precedence_with_dataflow_nodes(test_db):
    """
    Context variables should override node.config for DataFlow nodes.

    Verifies parameter precedence: config → context → connection outputs
    """
    workflow = WorkflowBuilder()

    # Node configured with one name
    workflow.add_node(
        "TestItemCreateNode",
        "create",
        {
            "id": "test-item-009",
            "name": "Config Name",  # From config
            "status": "pending",
        },
    )

    # But context provides different name
    runtime = AsyncLocalRuntime()
    result = await runtime.execute_workflow_async(
        workflow.build(), inputs={"name": "Context Name"}  # Should override config
    )

    created_item = result["results"]["create"]
    assert (
        created_item["name"] == "Context Name"
    ), "Context variables should override node.config for DataFlow nodes"
    assert (
        created_item["status"] == "pending"
    ), "Non-overridden config parameters should still be passed"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_multiple_dataflow_nodes_independent_configs(test_db):
    """
    Multiple DataFlow nodes in same workflow should have independent configs.

    Ensures node.config isolation - each node receives only its own parameters.
    """
    workflow = WorkflowBuilder()

    # Add two create nodes with different configs
    workflow.add_node(
        "TestItemCreateNode",
        "create1",
        {"id": "test-item-010", "name": "Item One", "status": "active"},
    )

    workflow.add_node(
        "TestItemCreateNode",
        "create2",
        {"id": "test-item-011", "name": "Item Two", "status": "completed"},
    )

    runtime = AsyncLocalRuntime()
    result = await runtime.execute_workflow_async(workflow.build(), inputs={})

    # Each node should receive its own config
    item1 = result["results"]["create1"]
    item2 = result["results"]["create2"]

    assert item1["id"] == "test-item-010"
    assert item1["name"] == "Item One"
    assert item1["status"] == "active"

    assert item2["id"] == "test-item-011"
    assert item2["name"] == "Item Two"
    assert item2["status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dataflow_config_not_mutated_across_executions(test_db):
    """
    Node config should not be mutated across multiple workflow executions.

    Regression test: Ensures config isolation between executions.
    """
    workflow = WorkflowBuilder()
    workflow.add_node(
        "TestItemCreateNode",
        "create",
        {"id": "test-item-012", "name": "Original Name", "status": "active"},
    )

    built_workflow = workflow.build()
    runtime = AsyncLocalRuntime()

    # Execute twice
    result1 = await runtime.execute_workflow_async(built_workflow, inputs={})
    result2 = await runtime.execute_workflow_async(built_workflow, inputs={})

    # Both should create items with same config (not mutated)
    item1 = result1["results"]["create"]
    item2 = result2["results"]["create"]

    # Note: Second execution will fail if ID is not unique
    # The important part is that config was not mutated
    assert (
        item1["name"] == "Original Name"
    ), "First execution should use original config"

    # Verify original workflow config is unchanged
    node_instance = built_workflow._node_instances["create"]
    assert (
        node_instance.config["name"] == "Original Name"
    ), "Node config should not be mutated after execution"
