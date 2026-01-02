"""Test AgentUIMiddleware input passing to verify external claims."""

import asyncio
from typing import Any, Dict

import pytest
from kailash.middleware.core.agent_ui import AgentUIMiddleware
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import WorkflowBuilder


@pytest.mark.asyncio
async def test_agent_ui_middleware_input_passing():
    """Test that AgentUIMiddleware correctly passes inputs to workflows."""
    # Create a simple workflow that demonstrates input passing
    workflow = WorkflowBuilder()

    # Add a node that will verify it receives the inputs
    workflow.add_node(
        "PythonCodeNode",
        "input_receiver",
        {
            "code": """
# Verify we receive the expected inputs
try:
    creds = credentials
except NameError:
    creds = None

try:
    conf = config
except NameError:
    conf = None

result = {
    "received_credentials": creds,
    "received_config": conf,
    "has_credentials": creds is not None,
    "has_config": conf is not None
}
"""
        },
    )

    # Create AgentUIMiddleware instance
    runtime = LocalRuntime()
    agent_ui = AgentUIMiddleware(runtime)

    # Register the workflow
    workflow_obj = workflow.build()
    workflow_id = "test_input_workflow"

    # Create a session and register the workflow
    session_id = await agent_ui.create_session(session_id="test_session_123")
    session = await agent_ui.get_session(session_id)
    session.workflows[workflow_id] = workflow_obj

    # Execute workflow with inputs - this is the core test
    execution_id = await agent_ui.execute(
        session_id=session_id,
        workflow_id=workflow_id,
        inputs={
            "input_receiver": {
                "credentials": {"username": "test_user", "password": "test_pass"},
                "config": {"debug": True, "timeout": 30},
            }
        },
    )

    # Wait for execution to complete
    await asyncio.sleep(0.1)  # Give it time to complete

    # Get the results
    session = await agent_ui.get_session(session_id)
    execution = session.executions.get(execution_id)

    # Verify the execution completed successfully
    assert execution is not None

    # Check execution status and get results
    assert execution["status"] == "completed"
    results = execution["outputs"]

    # Check that inputs were passed correctly
    assert results is not None
    node_result = results["input_receiver"]["result"]

    # Verify the credentials were passed
    assert node_result["received_credentials"] is not None
    assert node_result["received_credentials"]["username"] == "test_user"
    assert node_result["received_credentials"]["password"] == "test_pass"

    # Verify the config was passed
    assert node_result["received_config"] is not None
    assert node_result["received_config"]["debug"] is True
    assert node_result["received_config"]["timeout"] == 30

    print("✅ AgentUIMiddleware correctly passed inputs to workflow node")


@pytest.mark.asyncio
async def test_agent_ui_multiple_workflow_execution():
    """Test multiple workflow executions with different inputs."""
    runtime = LocalRuntime()
    agent_ui = AgentUIMiddleware(runtime)

    # Create a workflow
    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode",
        "processor",
        {
            "code": """
try:
    data_val = data
except NameError:
    data_val = "NO_DATA"

try:
    mult_val = multiplier
except NameError:
    mult_val = 1

result = {
    "processed_data": data_val,
    "multiplier": mult_val,
    "final_result": (data_val * mult_val) if (data_val != "NO_DATA" and mult_val != 1) else 0
}
"""
        },
    )

    workflow_obj = workflow.build()
    workflow_id = "math_workflow"
    session_id = "session_456"

    session_id = await agent_ui.create_session(session_id=session_id)
    session = await agent_ui.get_session(session_id)
    session.workflows[workflow_id] = workflow_obj

    # Execute with first set of inputs
    execution_id_1 = await agent_ui.execute(
        session_id=session_id,
        workflow_id=workflow_id,
        inputs={"processor": {"data": 10, "multiplier": 2}},
    )

    # Execute with second set of inputs
    execution_id_2 = await agent_ui.execute(
        session_id=session_id,
        workflow_id=workflow_id,
        inputs={"processor": {"data": 5, "multiplier": 3}},
    )

    # Wait for completion
    await asyncio.sleep(0.1)

    # Check both executions
    session = await agent_ui.get_session(session_id)

    execution_1 = session.executions.get(execution_id_1)
    execution_2 = session.executions.get(execution_id_2)

    assert execution_1["status"] == "completed"
    assert execution_2["status"] == "completed"

    result_1 = execution_1["outputs"]["processor"]["result"]
    result_2 = execution_2["outputs"]["processor"]["result"]

    # Verify different inputs produced different results
    assert result_1["final_result"] == 20  # 10 * 2
    assert result_2["final_result"] == 15  # 5 * 3

    print("✅ Multiple executions with different inputs worked correctly")


@pytest.mark.asyncio
async def test_agent_ui_function_node_inputs():
    """Test AgentUIMiddleware with function-based nodes."""

    def authentication_processor(credentials: Dict[str, str]) -> Dict[str, Any]:
        """Process authentication credentials."""
        username = credentials.get("username", "")
        return {
            "authenticated": len(username) > 0,
            "username": username.upper(),
            "timestamp": "2024-01-01T00:00:00Z",
        }

    # Create workflow with function node
    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode", "auth_processor", {"function": authentication_processor}
    )

    workflow_obj = workflow.build()
    runtime = LocalRuntime()
    agent_ui = AgentUIMiddleware(runtime)

    session_id = "auth_session"
    workflow_id = "auth_workflow"

    session_id = await agent_ui.create_session(session_id=session_id)
    session = await agent_ui.get_session(session_id)
    session.workflows[workflow_id] = workflow_obj

    # Execute with authentication inputs
    execution_id = await agent_ui.execute(
        session_id=session_id,
        workflow_id=workflow_id,
        inputs={
            "auth_processor": {
                "credentials": {"username": "john_doe", "password": "secret123"}
            }
        },
    )

    await asyncio.sleep(0.1)

    # Verify the function received and processed the inputs correctly
    session = await agent_ui.get_session(session_id)
    execution = session.executions.get(execution_id)

    assert execution["status"] == "completed"

    result = execution["outputs"]["auth_processor"]["result"]
    assert result["authenticated"] is True
    assert result["username"] == "JOHN_DOE"

    print("✅ Function node received inputs correctly via AgentUIMiddleware")


@pytest.mark.asyncio
async def test_agent_ui_empty_inputs():
    """Test AgentUIMiddleware behavior with empty/null inputs."""
    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode",
        "default_handler",
        {
            "code": """
try:
    data_val = data
    has_data = True
except NameError:
    data_val = "DEFAULT"
    has_data = False

result = {
    "has_data": has_data,
    "data_value": data_val,
    "received_empty_inputs": not has_data
}
"""
        },
    )

    runtime = LocalRuntime()
    agent_ui = AgentUIMiddleware(runtime)

    workflow_obj = workflow.build()
    session_id = "empty_session"
    workflow_id = "empty_workflow"

    session_id = await agent_ui.create_session(session_id=session_id)
    session = await agent_ui.get_session(session_id)
    session.workflows[workflow_id] = workflow_obj

    # Test with empty inputs
    execution_id_1 = await agent_ui.execute(
        session_id=session_id, workflow_id=workflow_id, inputs={}  # Empty inputs
    )

    # Test with None inputs
    execution_id_2 = await agent_ui.execute(
        session_id=session_id, workflow_id=workflow_id, inputs=None  # None inputs
    )

    await asyncio.sleep(0.1)

    session = await agent_ui.get_session(session_id)

    execution_1 = session.executions.get(execution_id_1)
    execution_2 = session.executions.get(execution_id_2)

    assert execution_1["status"] == "completed"
    assert execution_2["status"] == "completed"

    result_1 = execution_1["outputs"]["default_handler"]["result"]
    result_2 = execution_2["outputs"]["default_handler"]["result"]

    # Both should handle empty inputs gracefully
    assert result_1["data_value"] == "DEFAULT"
    assert result_2["data_value"] == "DEFAULT"

    print("✅ AgentUIMiddleware handles empty/null inputs correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
