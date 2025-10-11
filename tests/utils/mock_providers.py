"""
Mock Providers for Test Infrastructure

Provides mock services for unit testing without external dependencies.
Includes LLM providers, database connections, and service registries.
"""

import time
import uuid
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import MagicMock, Mock


class MockLLMProvider:
    """Mock LLM provider for testing without real LLM services."""

    def __init__(self, custom_responses: Optional[Dict[str, str]] = None):
        """
        Initialize mock LLM provider.

        Args:
            custom_responses: Optional dictionary mapping prompts to responses
        """
        self.custom_responses = custom_responses or {}
        self.call_count = 0
        self.call_history: List[Dict[str, Any]] = []

    def complete(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Mock LLM completion.

        Args:
            prompt: Input prompt
            **kwargs: Additional parameters

        Returns:
            Mock completion response
        """
        self.call_count += 1
        call_time = time.time()

        # Check for custom response
        if prompt in self.custom_responses:
            response = self.custom_responses[prompt]
        else:
            # Generate default mock response
            response = f"Mock response for: {prompt[:50]}..."

        call_record = {
            "call_id": self.call_count,
            "timestamp": call_time,
            "prompt": prompt,
            "response": response,
            "kwargs": kwargs,
        }
        self.call_history.append(call_record)

        return {
            "response": response,
            "metadata": {
                "provider": "mock_llm",
                "call_id": self.call_count,
                "timestamp": call_time,
                "prompt_length": len(prompt),
                "response_length": len(response),
            },
        }

    def stream_complete(self, prompt: str, **kwargs):
        """
        Mock streaming completion.

        Args:
            prompt: Input prompt
            **kwargs: Additional parameters

        Yields:
            Mock streaming response chunks
        """
        response = self.complete(prompt, **kwargs)
        full_response = response["response"]

        # Simulate streaming by yielding chunks
        chunk_size = 10
        for i in range(0, len(full_response), chunk_size):
            chunk = full_response[i : i + chunk_size]
            yield {
                "chunk": chunk,
                "metadata": {
                    "chunk_index": i // chunk_size,
                    "is_final": i + chunk_size >= len(full_response),
                },
            }

    def get_call_history(self) -> List[Dict[str, Any]]:
        """Get history of all LLM calls."""
        return self.call_history.copy()

    def reset_history(self) -> None:
        """Reset call history and count."""
        self.call_count = 0
        self.call_history.clear()


class MockDatabaseProvider:
    """Mock database provider for testing without real database connections."""

    def __init__(self):
        """Initialize mock database provider."""
        self.connections: Dict[str, "MockConnection"] = {}
        self.data_store: Dict[str, Any] = {}

    def get_connection(self, connection_id: Optional[str] = None) -> "MockConnection":
        """
        Get a mock database connection.

        Args:
            connection_id: Optional connection identifier

        Returns:
            Mock database connection
        """
        if connection_id is None:
            connection_id = str(uuid.uuid4())

        if connection_id not in self.connections:
            self.connections[connection_id] = MockConnection(self, connection_id)

        return self.connections[connection_id]

    def close_connection(self, connection_id: str) -> None:
        """Close a mock connection."""
        if connection_id in self.connections:
            del self.connections[connection_id]


class MockConnection:
    """Mock database connection for testing."""

    def __init__(self, provider: MockDatabaseProvider, connection_id: str):
        """
        Initialize mock connection.

        Args:
            provider: Parent database provider
            connection_id: Unique connection identifier
        """
        self.provider = provider
        self.connection_id = connection_id
        self.is_closed = False
        self.transaction_active = False
        self.query_history: List[Dict[str, Any]] = []

    def execute(
        self, query: str, parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Mock query execution.

        Args:
            query: SQL query string
            parameters: Optional query parameters

        Returns:
            Mock query result
        """
        if self.is_closed:
            raise ValueError("Connection is closed")

        query_record = {
            "query": query,
            "parameters": parameters or {},
            "timestamp": time.time(),
            "transaction_active": self.transaction_active,
        }
        self.query_history.append(query_record)

        # Generate mock result based on query type
        query_lower = query.lower().strip()

        if query_lower.startswith("select"):
            return {
                "rows": [
                    {"id": 1, "name": "Mock Record 1", "value": 100},
                    {"id": 2, "name": "Mock Record 2", "value": 200},
                ],
                "row_count": 2,
                "columns": ["id", "name", "value"],
            }
        elif query_lower.startswith("insert"):
            return {"affected_rows": 1, "last_insert_id": 123}
        elif query_lower.startswith("update"):
            return {"affected_rows": 2}
        elif query_lower.startswith("delete"):
            return {"affected_rows": 1}
        else:
            return {"status": "success", "message": "Query executed successfully"}

    def begin_transaction(self) -> None:
        """Begin a mock transaction."""
        if self.is_closed:
            raise ValueError("Connection is closed")
        self.transaction_active = True

    def commit_transaction(self) -> None:
        """Commit a mock transaction."""
        if self.is_closed:
            raise ValueError("Connection is closed")
        if not self.transaction_active:
            raise ValueError("No active transaction")
        self.transaction_active = False

    def rollback_transaction(self) -> None:
        """Rollback a mock transaction."""
        if self.is_closed:
            raise ValueError("Connection is closed")
        if not self.transaction_active:
            raise ValueError("No active transaction")
        self.transaction_active = False

    def close(self) -> None:
        """Close the mock connection."""
        if self.transaction_active:
            self.rollback_transaction()
        self.is_closed = True
        self.provider.close_connection(self.connection_id)

    def get_query_history(self) -> List[Dict[str, Any]]:
        """Get history of executed queries."""
        return self.query_history.copy()


class MockServiceRegistry:
    """Mock service registry for testing service management."""

    def __init__(self):
        """Initialize mock service registry."""
        self.services: Dict[str, Any] = {}
        self.service_configs: Dict[str, Dict[str, Any]] = {}
        self.registration_history: List[Dict[str, Any]] = []

    def register(
        self,
        service_name: str,
        service_instance: Any,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register a mock service.

        Args:
            service_name: Name of the service
            service_instance: Service instance or mock
            config: Optional service configuration
        """
        self.services[service_name] = service_instance
        self.service_configs[service_name] = config or {}

        registration_record = {
            "service_name": service_name,
            "registered_at": time.time(),
            "config": config,
        }
        self.registration_history.append(registration_record)

    def get(self, service_name: str) -> Any:
        """
        Get a registered service.

        Args:
            service_name: Name of the service

        Returns:
            Service instance

        Raises:
            KeyError: If service not found
        """
        if service_name not in self.services:
            raise KeyError(f"Service '{service_name}' not found in registry")

        return self.services[service_name]

    def unregister(self, service_name: str) -> None:
        """
        Unregister a service.

        Args:
            service_name: Name of the service to remove
        """
        if service_name in self.services:
            del self.services[service_name]
            del self.service_configs[service_name]

    def list_services(self) -> List[str]:
        """Get list of registered service names."""
        return list(self.services.keys())

    def get_service_config(self, service_name: str) -> Dict[str, Any]:
        """
        Get service configuration.

        Args:
            service_name: Name of the service

        Returns:
            Service configuration dictionary
        """
        return self.service_configs.get(service_name, {})

    def is_registered(self, service_name: str) -> bool:
        """Check if a service is registered."""
        return service_name in self.services

    def clear_registry(self) -> None:
        """Clear all registered services."""
        self.services.clear()
        self.service_configs.clear()

    def get_registration_history(self) -> List[Dict[str, Any]]:
        """Get service registration history."""
        return self.registration_history.copy()


class MockWorkflowExecutor:
    """Mock workflow executor for testing workflow execution without Core SDK."""

    def __init__(self):
        """Initialize mock workflow executor."""
        self.execution_history: List[Dict[str, Any]] = []
        self.should_fail = False
        self.failure_message = "Mock execution failure"

    def execute(self, workflow_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mock workflow execution.

        Args:
            workflow_config: Workflow configuration

        Returns:
            Mock execution results

        Raises:
            RuntimeError: If configured to fail
        """
        execution_id = str(uuid.uuid4())
        start_time = time.time()

        if self.should_fail:
            execution_record = {
                "execution_id": execution_id,
                "workflow_config": workflow_config,
                "start_time": start_time,
                "end_time": time.time(),
                "status": "failed",
                "error": self.failure_message,
            }
            self.execution_history.append(execution_record)
            raise RuntimeError(self.failure_message)

        # Simulate processing time
        time.sleep(0.001)

        # Generate mock results
        nodes = workflow_config.get("nodes", [])
        results = {}

        for node in nodes:
            node_id = node.get("id", f"node_{len(results) + 1}")
            results[node_id] = {
                "status": "completed",
                "result": {
                    "message": f"Mock execution result for {node_id}",
                    "node_type": node.get("type", "unknown"),
                    "executed_at": time.time(),
                },
                "execution_time": 0.001,
            }

        end_time = time.time()
        execution_record = {
            "execution_id": execution_id,
            "workflow_config": workflow_config,
            "start_time": start_time,
            "end_time": end_time,
            "status": "completed",
            "results": results,
        }
        self.execution_history.append(execution_record)

        return {
            "execution_id": execution_id,
            "results": results,
            "execution_time": end_time - start_time,
            "status": "completed",
        }

    def set_failure_mode(
        self, should_fail: bool, failure_message: str = "Mock execution failure"
    ) -> None:
        """
        Configure the mock to fail executions.

        Args:
            should_fail: Whether executions should fail
            failure_message: Error message for failures
        """
        self.should_fail = should_fail
        self.failure_message = failure_message

    def get_execution_history(self) -> List[Dict[str, Any]]:
        """Get history of all executions."""
        return self.execution_history.copy()

    def reset_history(self) -> None:
        """Reset execution history."""
        self.execution_history.clear()


def create_mock_framework() -> Mock:
    """
    Create a comprehensive mock framework for testing.

    Returns:
        Mock framework instance with common methods
    """
    framework = Mock()

    # Mock framework attributes
    framework.name = "mock_framework"
    framework.version = "1.0.0"
    framework.runtime = Mock()

    # Mock framework methods
    framework.create_agent = Mock(return_value=create_mock_agent())
    framework.create_workflow = Mock(return_value=create_mock_workflow())
    framework.execute = Mock(return_value=({}, str(uuid.uuid4())))

    # Mock agent list
    framework.agents = []

    return framework


def create_mock_agent() -> Mock:
    """
    Create a mock agent for testing.

    Returns:
        Mock agent instance
    """
    agent = Mock()

    # Mock agent attributes
    agent.agent_id = str(uuid.uuid4())
    agent.name = "mock_agent"
    agent.config = {"name": "mock_agent"}

    # Mock agent methods
    agent.create_workflow = Mock(return_value=create_mock_workflow())
    agent.execute = Mock(return_value=({}, str(uuid.uuid4())))

    return agent


def create_mock_workflow() -> Mock:
    """
    Create a mock workflow for testing.

    Returns:
        Mock workflow instance
    """
    workflow = Mock()

    # Mock workflow attributes
    workflow.workflow_id = str(uuid.uuid4())
    workflow.nodes = {}
    workflow.edges = []

    # Mock workflow methods
    workflow.add_node = Mock()
    workflow.add_edge = Mock()
    workflow.build = Mock(return_value=workflow)

    return workflow
