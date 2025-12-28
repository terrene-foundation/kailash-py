"""
Test AgentUIMiddleware shared workflow session management fix.

This test verifies that the fix for shared workflow execution works correctly,
addressing the bug where shared workflows couldn't be executed from sessions.
"""

import asyncio

import pytest
from kailash.middleware.core.agent_ui import AgentUIMiddleware
from kailash.nodes.code.python import PythonCodeNode
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.asyncio
async def test_shared_workflow_execution():
    """Test that shared workflows can be executed from sessions without manual workaround."""

    # Create a simple test workflow
    workflow_builder = WorkflowBuilder()

    def test_function(input_data: str = "default") -> dict:
        return {"result": f"Processed: {input_data}"}

    workflow_builder.add_node(PythonCodeNode.from_function(test_function), "processor")

    workflow = workflow_builder.build()

    # Initialize middleware
    middleware = AgentUIMiddleware()

    # Register workflow as shared
    await middleware.register_workflow("test_workflow", workflow, make_shared=True)

    # Verify it's in shared_workflows
    assert "test_workflow" in middleware.shared_workflows
    assert "test_workflow" not in middleware.sessions  # Not in any session yet

    # Create session
    session_id = await middleware.create_session()
    session = await middleware.get_session(session_id)

    # Verify it's NOT in session workflows initially
    assert "test_workflow" not in session.workflows

    # Execute shared workflow (this should work with the fix)
    execution_id = await middleware.execute(
        session_id, "test_workflow", {"input_data": "test"}
    )

    # Verify execution started
    assert execution_id is not None
    assert execution_id in middleware.active_executions

    # Verify workflow was copied to session
    assert "test_workflow" in session.workflows

    # Wait for completion
    await asyncio.sleep(1)

    # Check status
    status = await middleware.get_execution_status(execution_id, session_id)
    assert status["status"] in ["completed", "running"]

    # If completed, check results
    if status["status"] == "completed":
        assert "outputs" in status
        # The output structure depends on the runtime implementation


@pytest.mark.asyncio
async def test_shared_workflow_multiple_sessions():
    """Test that multiple sessions can use the same shared workflow."""

    middleware = AgentUIMiddleware()

    # Create shared workflow
    workflow_builder = WorkflowBuilder()

    def counter_function(count: int = 0) -> dict:
        return {"count": count + 1}

    workflow_builder.add_node(PythonCodeNode.from_function(counter_function), "counter")

    workflow = workflow_builder.build()
    await middleware.register_workflow("counter_workflow", workflow, make_shared=True)

    # Create two sessions
    session1_id = await middleware.create_session()
    session2_id = await middleware.create_session()

    # Execute in both sessions with different inputs
    exec1 = await middleware.execute(session1_id, "counter_workflow", {"count": 10})
    exec2 = await middleware.execute(session2_id, "counter_workflow", {"count": 20})

    # Both executions should succeed
    assert exec1 is not None
    assert exec2 is not None

    # Verify both sessions now have the workflow
    session1 = await middleware.get_session(session1_id)
    session2 = await middleware.get_session(session2_id)

    assert "counter_workflow" in session1.workflows
    assert "counter_workflow" in session2.workflows


@pytest.mark.asyncio
async def test_shared_workflow_not_found():
    """Test that non-existent shared workflows raise appropriate error."""

    middleware = AgentUIMiddleware()
    session_id = await middleware.create_session()

    # Try to execute non-existent workflow
    with pytest.raises(ValueError, match="Workflow non_existent not found"):
        await middleware.execute(session_id, "non_existent", {})


@pytest.mark.asyncio
async def test_session_workflow_priority():
    """Test that session workflows take priority over shared workflows."""

    middleware = AgentUIMiddleware()

    # Create two different workflows with same ID
    workflow_builder1 = WorkflowBuilder()
    workflow_builder1.add_node(
        PythonCodeNode.from_function(lambda: {"source": "shared"}), "node1"
    )
    shared_workflow = workflow_builder1.build()

    workflow_builder2 = WorkflowBuilder()
    workflow_builder2.add_node(
        PythonCodeNode.from_function(lambda: {"source": "session"}), "node2"
    )
    session_workflow = workflow_builder2.build()

    # Register as shared
    await middleware.register_workflow(
        "test_workflow", shared_workflow, make_shared=True
    )

    # Create session and add session-specific workflow with same ID
    session_id = await middleware.create_session()
    session = await middleware.get_session(session_id)
    session.add_workflow("test_workflow", session_workflow)

    # Execute - should use session workflow, not shared
    execution_id = await middleware.execute(session_id, "test_workflow", {})

    # The session workflow should be used (has node2)
    assert execution_id in middleware.active_executions
    execution_data = middleware.active_executions[execution_id]
    assert "node2" in execution_data["workflow"].nodes  # Session workflow has node2
    assert "node1" not in execution_data["workflow"].nodes  # Shared workflow has node1
