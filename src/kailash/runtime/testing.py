"""Testing utilities for Kailash workflows and nodes."""

import json
from typing import Any

from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import NodeValidationError, WorkflowExecutionError
from kailash.tracking import TaskManager
from kailash.workflow import Workflow


class MockNode(Node):
    """Mock node for testing purposes."""

    def __init__(self, **kwargs):
        """Initialize mock node with test behavior."""
        super().__init__(**kwargs)
        self._return_value = kwargs.get("return_value", {"output": "test"})
        self._should_fail = kwargs.get("should_fail", False)
        self._fail_message = kwargs.get("fail_message", "Mock failure")
        self._execution_count = 0

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define mock parameters."""
        return {
            "input": NodeParameter(
                name="input", type=Any, required=False, description="Mock input"
            ),
            "return_value": NodeParameter(
                name="return_value",
                type=dict,
                required=False,
                default={"output": "test"},
                description="Value to return",
            ),
            "should_fail": NodeParameter(
                name="should_fail",
                type=bool,
                required=False,
                default=False,
                description="Whether the node should fail",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute mock node logic."""
        self._execution_count += 1

        if self._should_fail:
            raise RuntimeError(self._fail_message)

        # Return configured value or default
        return self._return_value

    @property
    def execution_count(self) -> int:
        """Get the number of times this node was executed."""
        return self._execution_count


class TestDataGenerator:
    """Generate test data for workflow testing."""

    @staticmethod
    def generate_csv_data(
        rows: int = 10, columns: list[str] = None
    ) -> list[dict[str, Any]]:
        """Generate mock CSV data."""
        if columns is None:
            columns = ["id", "name", "value", "category"]

        data = []
        categories = ["A", "B", "C", "D"]

        for i in range(rows):
            row = {
                "id": i + 1,
                "name": f"Item_{i+1}",
                "value": (i + 1) * 10 + (i % 3),
                "category": categories[i % len(categories)],
            }

            # Only include requested columns
            row = {k: v for k, v in row.items() if k in columns}
            data.append(row)

        return data

    @staticmethod
    def generate_json_data(structure: str = "simple") -> dict | list:
        """Generate mock JSON data."""
        if structure == "simple":
            return {
                "name": "Test Data",
                "version": "1.0",
                "data": [{"id": 1, "value": "test1"}, {"id": 2, "value": "test2"}],
            }
        elif structure == "nested":
            return {
                "metadata": {"created": "2024-01-01", "author": "test"},
                "records": [
                    {"id": 1, "nested": {"key": "value1"}},
                    {"id": 2, "nested": {"key": "value2"}},
                ],
            }
        elif structure == "array":
            return [
                {"id": 1, "data": "value1"},
                {"id": 2, "data": "value2"},
                {"id": 3, "data": "value3"},
            ]
        else:
            return {"type": structure}

    @staticmethod
    def generate_text_data(lines: int = 5) -> str:
        """Generate mock text data."""
        text_lines = []
        for i in range(lines):
            text_lines.append(f"This is line {i+1} of the test text.")
            if i % 2 == 0:
                text_lines.append(
                    f"It contains some interesting data about item {i+1}."
                )

        return "\n".join(text_lines)


class CredentialMockData:
    """Generate mock credential data for testing authentication flows."""

    @staticmethod
    def generate_oauth2_config(provider: str = "generic") -> dict[str, Any]:
        """Generate OAuth2 configuration for testing."""
        configs = {
            "generic": {
                "token_url": "https://auth.example.com/oauth/token",
                "client_id": "test_client_id_123",
                "client_secret": "test_client_secret_456",
                "scope": "read write",
                "grant_type": "client_credentials",
            },
            "github": {
                "token_url": "https://github.com/login/oauth/access_token",
                "client_id": "test_github_client",
                "client_secret": "test_github_secret",
                "scope": "repo user",
                "grant_type": "authorization_code",
            },
            "google": {
                "token_url": "https://oauth2.googleapis.com/token",
                "client_id": "test_google_client.apps.googleusercontent.com",
                "client_secret": "test_google_secret",
                "scope": "https://www.googleapis.com/auth/userinfo.email",
                "grant_type": "authorization_code",
            },
        }
        return configs.get(provider, configs["generic"])

    @staticmethod
    def generate_api_key_config(service: str = "generic") -> dict[str, Any]:
        """Generate API key configuration for testing."""
        configs = {
            "generic": {
                "api_key": "sk_test_4eC39HqLyjWDarjtT1zdp7dc",
                "header_name": "X-API-Key",
                "prefix": None,
            },
            "stripe": {
                "api_key": "sk_test_4eC39HqLyjWDarjtT1zdp7dc",
                "header_name": "Authorization",
                "prefix": "Bearer",
            },
            "openai": {
                "api_key": "sk-test-1234567890abcdef",
                "header_name": "Authorization",
                "prefix": "Bearer",
            },
        }
        return configs.get(service, configs["generic"])

    @staticmethod
    def generate_jwt_claims(user_type: str = "user") -> dict[str, Any]:
        """Generate JWT claims for testing."""
        import time

        now = int(time.time())
        claims = {
            "user": {
                "sub": "1234567890",
                "name": "Test User",
                "email": "test@example.com",
                "iat": now,
                "exp": now + 3600,
                "iss": "test_issuer",
                "aud": "test_audience",
                "roles": ["user"],
            },
            "admin": {
                "sub": "admin_123",
                "name": "Admin User",
                "email": "admin@example.com",
                "iat": now,
                "exp": now + 3600,
                "iss": "test_issuer",
                "aud": "test_audience",
                "roles": ["admin", "user"],
                "permissions": ["read", "write", "delete"],
            },
            "service": {
                "sub": "service_account_456",
                "name": "Service Account",
                "iat": now,
                "exp": now + 86400,  # 24 hours
                "iss": "test_issuer",
                "aud": "test_audience",
                "scope": "api:read api:write",
            },
        }
        return claims.get(user_type, claims["user"])


class SecurityTestHelper:
    """Helper class for testing security and authentication flows."""

    def __init__(self):
        """Initialize security test helper."""
        self.credential_mock = CredentialMockData()

    def create_auth_test_workflow(self, auth_type: str = "oauth2") -> Workflow:
        """Create a workflow for testing authentication."""
        from kailash.nodes.api.auth import APIKeyNode, BasicAuthNode, OAuth2Node
        from kailash.nodes.api.http import HTTPRequestNode
        from kailash.nodes.testing import CredentialTestingNode

        workflow = Workflow(
            workflow_id=f"test_{auth_type}_auth", name=f"Test {auth_type} Auth"
        )

        if auth_type == "oauth2":
            # Add OAuth2 testing nodes
            workflow.add_node(
                "credential_test",
                CredentialTestingNode(),
                credential_type="oauth2",
                scenario="success",
            )
            workflow.add_node("oauth", OAuth2Node())
            workflow.add_node("http", HTTPRequestNode())

            # Connect nodes
            workflow.connect("credential_test", "oauth", {"credentials": "mock_data"})
            workflow.connect("oauth", "http", {"headers": "headers"})

        elif auth_type == "api_key":
            # Add API key testing nodes
            workflow.add_node(
                "credential_test",
                CredentialTestingNode(),
                credential_type="api_key",
                scenario="success",
            )
            workflow.add_node("api_key", APIKeyNode())
            workflow.add_node("http", HTTPRequestNode())

            # Connect nodes
            workflow.connect(
                "credential_test", "api_key", {"credentials.api_key": "api_key"}
            )
            workflow.connect("api_key", "http", {"headers": "headers"})

        elif auth_type == "basic":
            # Add Basic auth testing nodes
            workflow.add_node(
                "credential_test",
                CredentialTestingNode(),
                credential_type="basic",
                scenario="success",
                mock_data={"username": "test_user", "password": "test_pass"},
            )
            workflow.add_node("basic", BasicAuthNode())
            workflow.add_node("http", HTTPRequestNode())

            # Connect nodes
            workflow.connect(
                "credential_test",
                "basic",
                {
                    "credentials.username": "username",
                    "credentials.password": "password",
                },
            )
            workflow.connect("basic", "http", {"headers": "headers"})

        return workflow

    def test_credential_scenarios(
        self, credential_type: str, scenarios: list[str] = None
    ) -> dict[str, Any]:
        """Test multiple credential scenarios and return results."""
        from kailash.nodes.testing import CredentialTestingNode

        if scenarios is None:
            scenarios = ["success", "expired", "invalid", "rate_limit"]

        results = {}
        tester = CredentialTestingNode()

        for scenario in scenarios:
            try:
                result = tester.execute(
                    credential_type=credential_type,
                    scenario=scenario,
                    mock_data=(
                        getattr(
                            self.credential_mock, f"generate_{credential_type}_config"
                        )()
                        if hasattr(
                            self.credential_mock, f"generate_{credential_type}_config"
                        )
                        else {}
                    ),
                )
                results[scenario] = {
                    "success": result.get("valid", False),
                    "result": result,
                }
            except Exception as e:
                results[scenario] = {
                    "success": False,
                    "error": str(e),
                }

        return results


class WorkflowTestHelper:
    """Helper class for testing workflows."""

    def __init__(self):
        """Initialize test helper."""
        self.runtime = LocalRuntime(debug=True)
        self.task_manager = None

    def create_test_workflow(self, name: str = "test_workflow") -> Workflow:
        """Create a simple test workflow."""
        workflow = Workflow(workflow_id=name, name=f"Test Workflow: {name}")

        # Add some mock nodes
        workflow.add_node("input", MockNode(), return_value={"data": [1, 2, 3]})
        workflow.add_node("process", MockNode(), return_value={"processed": [2, 4, 6]})
        workflow.add_node("output", MockNode(), return_value={"result": "success"})

        # Connect nodes
        workflow.connect("input", "process", {"data": "input"})
        workflow.connect("process", "output", {"processed": "data"})

        return workflow

    def run_workflow(
        self,
        workflow: Workflow,
        with_tracking: bool = True,
        parameters: dict | None = None,
    ) -> tuple[dict[str, Any], str | None]:
        """Run a workflow with optional tracking."""
        if with_tracking:
            self.task_manager = TaskManager()
        else:
            self.task_manager = None

        return self.runtime.execute(workflow, self.task_manager, parameters)

    def assert_workflow_success(
        self, workflow: Workflow, expected_nodes: list[str] | None = None
    ):
        """Assert that a workflow runs successfully."""
        results, run_id = self.run_workflow(workflow)

        # Check that all expected nodes were executed
        if expected_nodes:
            for node_id in expected_nodes:
                assert node_id in results, f"Node {node_id} was not executed"
                assert (
                    "error" not in results[node_id]
                ), f"Node {node_id} failed: {results[node_id].get('error')}"

        return results, run_id

    def assert_node_output(
        self,
        results: dict[str, Any],
        node_id: str,
        expected_keys: list[str],
        expected_values: dict | None = None,
    ):
        """Assert that a node produced expected output."""
        assert node_id in results, f"Node {node_id} not found in results"

        node_output = results[node_id]

        # Check expected keys
        for key in expected_keys:
            assert key in node_output, f"Key '{key}' not found in {node_id} output"

        # Check expected values if provided
        if expected_values:
            for key, expected_value in expected_values.items():
                assert (
                    node_output.get(key) == expected_value
                ), f"Node {node_id} key '{key}' expected {expected_value}, got {node_output.get(key)}"


class NodeTestHelper:
    """Helper class for testing individual nodes."""

    @staticmethod
    def test_node_parameters(node: Node, expected_params: dict[str, type]):
        """Test that a node has expected parameters."""
        params = node.get_parameters()

        for param_name, expected_type in expected_params.items():
            assert param_name in params, f"Parameter '{param_name}' not found"
            param = params[param_name]
            assert (
                param.type == expected_type
            ), f"Parameter '{param_name}' expected type {expected_type}, got {param.type}"

    @staticmethod
    def test_node_execution(
        node: Node,
        inputs: dict[str, Any],
        expected_keys: list[str],
        should_fail: bool = False,
    ) -> dict[str, Any]:
        """Test node execution with given inputs."""
        if should_fail:
            try:
                result = node.execute(**inputs)
                assert False, "Node execution should have failed but didn't"
            except (NodeValidationError, WorkflowExecutionError):
                return {}
        else:
            result = node.execute(**inputs)

            # Check expected output keys
            for key in expected_keys:
                assert key in result, f"Expected key '{key}' not found in output"

            return result

    @staticmethod
    def test_node_validation(
        node: Node, valid_inputs: dict[str, Any], invalid_inputs: list[dict[str, Any]]
    ):
        """Test node input validation."""
        # Test valid inputs
        try:
            node.validate_inputs(**valid_inputs)
        except NodeValidationError:
            assert False, "Valid inputs failed validation"

        # Test invalid inputs
        for invalid_input in invalid_inputs:
            try:
                node.validate_inputs(**invalid_input)
                assert False, f"Invalid input {invalid_input} passed validation"
            except NodeValidationError:
                pass  # Expected


class WorkflowTestReporter:
    """Generate test reports for workflows."""

    def __init__(self, task_manager: TaskManager):
        """Initialize reporter with task manager."""
        self.task_manager = task_manager

    def generate_run_report(self, run_id: str) -> dict[str, Any]:
        """Generate a detailed report for a workflow run."""
        run = self.task_manager.get_run_summary(run_id)
        tasks = self.task_manager.list_tasks(run_id)

        report = {
            "run_id": run_id,
            "workflow": run.workflow_name,
            "status": run.status,
            "duration": run.duration,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "summary": {
                "total_tasks": run.task_count,
                "completed": run.completed_tasks,
                "failed": run.failed_tasks,
            },
            "tasks": [],
        }

        # Add task details
        for task in tasks:
            task_info = {
                "node_id": task.node_id,
                "node_type": task.node_type,
                "status": task.status,
                "duration": task.duration,
            }

            if task.error:
                task_info["error"] = task.error

            report["tasks"].append(task_info)

        return report

    def save_report(self, report: dict[str, Any], output_path: str):
        """Save report to file."""
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)


# Convenience functions
def create_test_node(node_type: str = "MockNode", **config) -> Node:
    """Create a test node instance."""
    if node_type == "MockNode":
        return MockNode(**config)
    else:
        # Try to get from registry
        from kailash.nodes import NodeRegistry

        node_class = NodeRegistry.get(node_type)
        return node_class(**config)


def create_test_workflow(
    name: str = "test_workflow", nodes: list[dict] | None = None
) -> Workflow:
    """Create a test workflow with specified nodes."""
    workflow = Workflow(name=name)

    if nodes:
        for node_config in nodes:
            node_id = node_config["id"]
            node_type = node_config.get("type", "MockNode")
            config = node_config.get("config", {})

            node = create_test_node(node_type, **config)
            workflow.add_node(node_id, node, **config)

        # Add connections if specified
        if "connections" in node_config:
            for conn in node_config["connections"]:
                workflow.connect(conn["from"], conn["to"], conn.get("mapping", {}))

    return workflow
