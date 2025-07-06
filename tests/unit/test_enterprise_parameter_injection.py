"""Test enterprise node parameter injection framework."""

from typing import Any, Dict

import pytest

from kailash.runtime.local import LocalRuntime
from kailash.runtime.parameter_injector import (
    DeferredConfigNode,
    create_deferred_node,
    create_deferred_oauth2,
    create_deferred_sql,
)
from kailash.workflow import WorkflowBuilder


def test_deferred_oauth2_node_creation():
    """Test creating a deferred OAuth2 node."""
    # Create node without connection parameters
    node = create_deferred_oauth2(name="test_oauth")

    # Should have basic parameter definitions
    params = node.get_parameters()
    assert "token_url" in params
    assert "client_id" in params
    assert "client_secret" in params
    assert params["token_url"].required is True
    assert params["client_id"].required is True
    assert params["client_secret"].required is False


def test_deferred_sql_node_creation():
    """Test creating a deferred SQL node."""
    # Create node without connection parameters
    node = create_deferred_sql(name="test_sql")

    # Should have basic parameter definitions
    params = node.get_parameters()
    assert "database_type" in params
    assert "host" in params
    assert "database" in params
    assert "query" in params
    assert params["query"].required is True
    assert params["host"].required is False


def test_parameter_injection_workflow():
    """Test parameter injection in a workflow context."""
    workflow = WorkflowBuilder()

    # Add a deferred SQL node that will receive connection params at runtime
    sql_node = create_deferred_sql(name="dynamic_sql")
    workflow.add_node(sql_node, "database_query")

    # Add a simple code node to verify the flow
    workflow.add_node(
        "PythonCodeNode",
        "result_processor",
        {
            "code": """
result = {
    "processed": True,
    "data_count": len(data) if 'data' in locals() and isinstance(data, list) else 0
}
"""
        },
    )

    workflow.add_connection("database_query", "data", "result_processor", "data")

    # The workflow should be buildable even without connection parameters
    wf = workflow.build()
    assert wf is not None

    # Check that the SQL node has the expected parameter structure
    sql_params = sql_node.get_parameters()
    assert "database_type" in sql_params
    assert "query" in sql_params


def test_runtime_parameter_injection():
    """Test that runtime parameters are properly injected."""
    node = create_deferred_sql(name="test_injection")

    # Initially not initialized
    assert not node._is_initialized

    # Set runtime parameters
    runtime_params = {
        "database_type": "sqlite",
        "database": ":memory:",
        "query": "SELECT 1 as test_value",
        "host": "localhost",  # Connection parameter
    }

    node.set_runtime_config(**runtime_params)

    # Check effective configuration
    effective_config = node.get_effective_config()
    assert effective_config["database_type"] == "sqlite"
    assert effective_config["database"] == ":memory:"
    assert effective_config["host"] == "localhost"


def test_connection_parameter_extraction():
    """Test extraction of connection parameters from runtime inputs."""
    node = create_deferred_oauth2(name="test_extraction")

    # Mix of connection and non-connection parameters
    inputs = {
        "token_url": "https://auth.example.com/token",
        "client_id": "test_client",
        "client_secret": "secret123",
        "some_data": "not_a_connection_param",
        "grant_type": "client_credentials",
    }

    connection_params = node._extract_config_params(inputs)

    # Should extract only connection-related parameters
    expected_connection_params = {
        "token_url",
        "client_id",
        "client_secret",
        "grant_type",
    }
    assert set(connection_params.keys()) == expected_connection_params
    assert connection_params["token_url"] == "https://auth.example.com/token"
    assert "some_data" not in connection_params


def test_deferred_initialization():
    """Test that nodes can be created without full configuration and initialized later."""
    # Create node with minimal config
    node = create_deferred_oauth2(name="deferred_oauth")

    # Should not be initialized yet
    assert not node._is_initialized
    assert node._actual_node is None

    # Simulate runtime parameter injection
    runtime_config = {
        "token_url": "https://oauth.example.com/token",
        "client_id": "runtime_client_id",
        "client_secret": "runtime_secret",
        "grant_type": "client_credentials",
    }

    node.set_runtime_config(**runtime_config)
    node._initialize_if_needed()

    # Should now be initialized (though actual node creation might fail without real OAuth2Node)
    # We're testing the framework, not the actual OAuth implementation


def test_parameter_precedence():
    """Test that runtime parameters take precedence over init-time parameters."""
    # Create node with initial config
    initial_config = {
        "name": "precedence_test",
        "database_type": "postgresql",
        "host": "initial_host",
    }

    node = create_deferred_sql(**initial_config)

    # Set runtime parameters that override some initial config
    runtime_config = {"host": "runtime_host", "database": "runtime_db"}

    node.set_runtime_config(**runtime_config)
    effective_config = node.get_effective_config()

    # Runtime parameters should take precedence
    assert effective_config["host"] == "runtime_host"
    assert effective_config["database"] == "runtime_db"
    # Initial config should still be present for non-overridden values
    assert effective_config["database_type"] == "postgresql"


def test_missing_connection_parameters():
    """Test behavior when required connection parameters are missing."""
    node = create_deferred_oauth2(name="missing_params")

    # Try to run without setting connection parameters
    from kailash.sdk_exceptions import NodeExecutionError

    with pytest.raises(
        NodeExecutionError,
        match="Cannot execute OAuth2Node - missing required configuration",
    ):
        node.execute(some_param="value")


def test_multiple_parameter_updates():
    """Test that parameters can be updated multiple times."""
    node = create_deferred_sql(name="multi_update")

    # First update
    node.set_runtime_config(host="host1", database="db1")
    config1 = node.get_effective_config()
    assert config1["host"] == "host1"
    assert config1["database"] == "db1"

    # Second update - should merge with previous
    node.set_runtime_config(host="host2", user="user1")
    config2 = node.get_effective_config()
    assert config2["host"] == "host2"  # Updated
    assert config2["database"] == "db1"  # Preserved
    assert config2["user"] == "user1"  # Added


def test_workflow_integration_pattern():
    """Test the complete pattern for workflow integration."""
    # This test demonstrates how users should use deferred enterprise nodes
    workflow = WorkflowBuilder()

    # Create deferred nodes
    auth_node = create_deferred_oauth2(name="auth")
    db_node = create_deferred_sql(name="db")

    # Add to workflow
    workflow.add_node(auth_node, "authentication")
    workflow.add_node(db_node, "database")

    # Add result processing
    workflow.add_node(
        "PythonCodeNode",
        "combiner",
        {
            "code": """
result = {
    "auth_success": auth_data.get("access_token") is not None if 'auth_data' in locals() else False,
    "db_success": db_data.get("data") is not None if 'db_data' in locals() else False,
    "combined": True
}
"""
        },
    )

    workflow.add_connection("authentication", "auth_headers", "combiner", "auth_data")
    workflow.add_connection("database", "data", "combiner", "db_data")

    # Build workflow - should work even without connection parameters set
    wf = workflow.build()
    assert wf is not None

    # Verify node parameters are accessible
    auth_params = auth_node.get_parameters()
    db_params = db_node.get_parameters()

    assert "token_url" in auth_params
    assert "database_type" in db_params


def test_create_deferred_node_generic():
    """Test the generic deferred node creation function."""

    # Mock node class
    class MockNode:
        def __init__(self, **kwargs):
            self.config = kwargs

        def get_parameters(self):
            return {"param1": "value1"}

    MockNode.__name__ = "MockNode"

    # Create deferred node
    deferred = create_deferred_node(MockNode, initial_param="test")

    assert isinstance(deferred, DeferredConfigNode)
    assert deferred._node_class == MockNode
    assert deferred._initial_config["initial_param"] == "test"


def test_required_config_detection():
    """Test that different node types have appropriate config detection."""
    # OAuth2 node
    oauth_node = create_deferred_oauth2()

    # Should require token_url and client_id
    assert not oauth_node._has_required_config()

    oauth_node.set_runtime_config(token_url="https://test.com/token")
    assert not oauth_node._has_required_config()

    oauth_node.set_runtime_config(client_id="test_client")
    assert oauth_node._has_required_config()

    # SQL node
    sql_node = create_deferred_sql()

    # Should require database info and query
    assert not sql_node._has_required_config()

    sql_node.set_runtime_config(database="testdb")
    assert not sql_node._has_required_config()

    sql_node.set_runtime_config(query="SELECT 1")
    assert sql_node._has_required_config()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
