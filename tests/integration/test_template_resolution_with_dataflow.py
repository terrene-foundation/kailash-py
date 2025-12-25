"""
Integration tests for template parameter resolution with DataFlow nodes.

This test suite validates that ${param} template syntax works correctly
with DataFlow's auto-generated nodes, especially for dynamic filtering.

Bug Fixed: v0.9.30 - Templates now resolve in nested objects (filter parameters)

Requirements:
- Real PostgreSQL database
- DataFlow v0.7.1+
- Core SDK v0.9.30+
"""

import pytest
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow


@pytest.fixture
async def test_db():
    """Create test database with sample data."""
    db = DataFlow("postgresql://localhost/test_template_resolution")

    @db.model
    class TestRun:
        id: str
        run_tag: str
        status: str
        name: str

    await db.initialize()

    # Create sample data
    await db.test_run.create(
        {"id": "run1", "run_tag": "local", "status": "active", "name": "Test Run 1"}
    )
    await db.test_run.create(
        {"id": "run2", "run_tag": "local", "status": "completed", "name": "Test Run 2"}
    )
    await db.test_run.create(
        {
            "id": "run3",
            "run_tag": "workflow",
            "status": "active",
            "name": "Test Run 3",
        }
    )
    await db.test_run.create(
        {
            "id": "run4",
            "run_tag": "workflow",
            "status": "completed",
            "name": "Test Run 4",
        }
    )

    yield db

    # Cleanup
    await db.test_run.delete({"id": "run1"})
    await db.test_run.delete({"id": "run2"})
    await db.test_run.delete({"id": "run3"})
    await db.test_run.delete({"id": "run4"})


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dataflow_filter_with_nested_template(test_db):
    """Test DataFlow filter parameter with ${} template in nested object."""
    runtime = AsyncLocalRuntime()
    workflow = WorkflowBuilder()

    # CRITICAL TEST: Template in nested filter object
    workflow.add_node(
        "TestRunListNode",
        "filter_runs",
        {
            "filter": {
                "run_tag": "${tag}",  # ← Template in nested object (THE BUG)
                "status": "${status}",  # ← Another nested template
            },
            "limit": "${limit}",  # ← Top-level template (always worked)
        },
    )

    # Execute with template inputs
    result = await runtime.execute_workflow_async(
        workflow.build(), inputs={"tag": "local", "status": "active", "limit": 10}
    )

    # Verify filter was applied correctly
    records = result["results"]["filter_runs"]["records"]

    # Should return only local + active runs (run1)
    assert len(records) == 1, f"Expected 1 record, got {len(records)}"
    assert records[0]["run_tag"] == "local"
    assert records[0]["status"] == "active"
    assert records[0]["id"] == "run1"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dataflow_filter_with_single_template_field(test_db):
    """Test DataFlow filter with only one template field."""
    runtime = AsyncLocalRuntime()
    workflow = WorkflowBuilder()

    workflow.add_node(
        "TestRunListNode",
        "filter_runs",
        {
            "filter": {"run_tag": "${tag}"},  # Single template field
            "limit": 10,
        },
    )

    result = await runtime.execute_workflow_async(
        workflow.build(), inputs={"tag": "workflow"}
    )

    records = result["results"]["filter_runs"]["records"]

    # Should return both workflow runs (run3, run4)
    assert len(records) == 2
    assert all(r["run_tag"] == "workflow" for r in records)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dataflow_update_with_nested_template(test_db):
    """Test DataFlow update with template in nested fields parameter."""
    runtime = AsyncLocalRuntime()
    workflow = WorkflowBuilder()

    workflow.add_node(
        "TestRunUpdateNode",
        "update_run",
        {
            "filter": {"id": "${run_id}"},  # Template in filter
            "fields": {
                "status": "${new_status}",
                "name": "${new_name}",
            },  # Templates in fields
        },
    )

    result = await runtime.execute_workflow_async(
        workflow.build(),
        inputs={"run_id": "run1", "new_status": "completed", "new_name": "Updated Run"},
    )

    # Verify update worked
    assert result["results"]["update_run"]["updated_count"] == 1

    # Verify data was actually updated
    verify_workflow = WorkflowBuilder()
    verify_workflow.add_node("TestRunReadNode", "read_run", {"filter": {"id": "run1"}})

    verify_result = await runtime.execute_workflow_async(
        verify_workflow.build(), inputs={}
    )

    updated_record = verify_result["results"]["read_run"]["record"]
    assert updated_record["status"] == "completed"
    assert updated_record["name"] == "Updated Run"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_template_resolution_preserves_types(test_db):
    """Test that template resolution preserves data types."""
    runtime = AsyncLocalRuntime()
    workflow = WorkflowBuilder()

    workflow.add_node(
        "PythonCodeNode",
        "test_types",
        {
            "code": """
result = {
    'string_type': type(string_param).__name__,
    'int_type': type(int_param).__name__,
    'dict_type': type(dict_param).__name__,
    'list_type': type(list_param).__name__,
    'bool_type': type(bool_param).__name__,
    'string_value': string_param,
    'int_value': int_param,
    'dict_value': dict_param,
    'list_value': list_param,
    'bool_value': bool_param
}
"""
        },
    )

    result = await runtime.execute_workflow_async(
        workflow.build(),
        inputs={
            "string_param": "hello",
            "int_param": 42,
            "dict_param": {"key": "value"},
            "list_param": [1, 2, 3],
            "bool_param": True,
        },
    )

    node_result = result["results"]["test_types"]["result"]

    # Verify types are preserved
    assert node_result["string_type"] == "str"
    assert node_result["int_type"] == "int"
    assert node_result["dict_type"] == "dict"
    assert node_result["list_type"] == "list"
    assert node_result["bool_type"] == "bool"

    # Verify values are correct
    assert node_result["string_value"] == "hello"
    assert node_result["int_value"] == 42
    assert node_result["dict_value"] == {"key": "value"}
    assert node_result["list_value"] == [1, 2, 3]
    assert node_result["bool_value"] is True


@pytest.mark.asyncio
async def test_template_with_actual_dollar_signs():
    """Test that actual dollar signs (not templates) are preserved."""
    runtime = AsyncLocalRuntime()
    workflow = WorkflowBuilder()

    workflow.add_node(
        "PythonCodeNode",
        "test_dollars",
        {
            "code": """
result = {
    'price': price,
    'regex': regex_pattern,
    'bcrypt': bcrypt_hash
}
"""
        },
    )

    result = await runtime.execute_workflow_async(
        workflow.build(),
        inputs={
            "price": "$19.99",  # Literal dollar sign
            "regex_pattern": r"test$",  # Regex anchor
            "bcrypt_hash": "$2b$12$xyz",  # Bcrypt hash
        },
    )

    node_result = result["results"]["test_dollars"]["result"]

    # Dollar signs should be preserved
    assert node_result["price"] == "$19.99"
    assert node_result["regex"] == "test$"
    assert node_result["bcrypt"] == "$2b$12$xyz"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
