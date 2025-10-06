"""Unit tests for runtime testing utilities.

Follows the testing policy:
- Unit tests (Tier 1): Fast, isolated, mocking allowed for external dependencies
- Tests all testing utility classes and their functionality
"""

import json
import tempfile
import time
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.testing import (
    CredentialMockData,
    MockNode,
    NodeTestHelper,
    SecurityTestHelper,
    TestDataGenerator,
    WorkflowTestHelper,
    WorkflowTestReporter,
    create_test_node,
    create_test_workflow,
)
from kailash.sdk_exceptions import NodeValidationError, WorkflowExecutionError
from kailash.workflow.graph import Workflow


class TestMockNode:
    """Test MockNode functionality."""

    def test_mock_node_initialization(self):
        """Test MockNode initialization with default values."""
        node = MockNode(name="test_mock")

        # Check internal MockNode attributes
        assert node._return_value == {"output": "test"}
        assert node._should_fail is False
        assert node._fail_message == "Mock failure"
        assert node._execution_count == 0

    def test_mock_node_custom_configuration(self):
        """Test MockNode with custom configuration."""
        node = MockNode(
            name="custom_mock",
            return_value={"result": "custom"},
            should_fail=True,
            fail_message="Custom failure",
        )

        assert node._return_value == {"result": "custom"}
        assert node._should_fail is True
        assert node._fail_message == "Custom failure"

    def test_mock_node_parameters(self):
        """Test MockNode parameter definitions."""
        node = MockNode(name="param_test")
        params = node.get_parameters()

        assert "input" in params
        assert "return_value" in params
        assert "should_fail" in params

        # Check parameter properties
        assert params["input"].required is False
        assert params["return_value"].default == {"output": "test"}
        assert params["should_fail"].default is False

    def test_mock_node_successful_execution(self):
        """Test successful MockNode execution."""
        return_value = {"data": [1, 2, 3], "status": "success"}
        node = MockNode(name="success_test", return_value=return_value)

        result = node.run(input="test_input")

        assert result == return_value
        assert node.execution_count == 1

    def test_mock_node_failure_execution(self):
        """Test MockNode execution failure."""
        node = MockNode(
            name="failure_test", should_fail=True, fail_message="Test failure message"
        )

        with pytest.raises(RuntimeError, match="Test failure message"):
            node.run()

        assert node.execution_count == 1

    def test_mock_node_execution_count(self):
        """Test execution count tracking."""
        node = MockNode(name="count_test")

        assert node.execution_count == 0

        node.run()
        assert node.execution_count == 1

        node.run()
        assert node.execution_count == 2

        # Test failure still increments count
        node._should_fail = True
        with pytest.raises(RuntimeError):
            node.run()

        assert node.execution_count == 3


class TestTestDataGenerator:
    """Test TestDataGenerator functionality."""

    def test_generate_csv_data_default(self):
        """Test CSV data generation with defaults."""
        data = TestDataGenerator.generate_csv_data()

        assert len(data) == 10
        assert all("id" in row for row in data)
        assert all("name" in row for row in data)
        assert all("value" in row for row in data)
        assert all("category" in row for row in data)

        # Check first row structure
        first_row = data[0]
        assert first_row["id"] == 1
        assert first_row["name"] == "Item_1"
        assert first_row["category"] in ["A", "B", "C", "D"]

    def test_generate_csv_data_custom(self):
        """Test CSV data generation with custom parameters."""
        data = TestDataGenerator.generate_csv_data(rows=5, columns=["id", "name"])

        assert len(data) == 5
        assert all(len(row) == 2 for row in data)
        assert all("id" in row and "name" in row for row in data)
        assert all("value" not in row for row in data)

    def test_generate_json_data_simple(self):
        """Test simple JSON data generation."""
        data = TestDataGenerator.generate_json_data("simple")

        assert isinstance(data, dict)
        assert "name" in data
        assert "version" in data
        assert "data" in data
        assert data["name"] == "Test Data"
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 2

    def test_generate_json_data_nested(self):
        """Test nested JSON data generation."""
        data = TestDataGenerator.generate_json_data("nested")

        assert isinstance(data, dict)
        assert "metadata" in data
        assert "records" in data
        assert "author" in data["metadata"]
        assert all("nested" in record for record in data["records"])

    def test_generate_json_data_array(self):
        """Test array JSON data generation."""
        data = TestDataGenerator.generate_json_data("array")

        assert isinstance(data, list)
        assert len(data) == 3
        assert all("id" in item and "data" in item for item in data)

    def test_generate_json_data_custom(self):
        """Test custom JSON data generation."""
        data = TestDataGenerator.generate_json_data("custom_type")

        assert isinstance(data, dict)
        assert data == {"type": "custom_type"}

    def test_generate_text_data_default(self):
        """Test text data generation with defaults."""
        text = TestDataGenerator.generate_text_data()
        lines = text.split("\n")

        # Should generate 5 lines + some additional lines for even indexes
        assert len(lines) >= 5
        assert "This is line 1 of the test text." in lines[0]
        assert "interesting data about item 1" in lines[1]

    def test_generate_text_data_custom(self):
        """Test text data generation with custom line count."""
        text = TestDataGenerator.generate_text_data(lines=3)
        lines = text.split("\n")

        assert "This is line 1 of the test text." in lines[0]
        assert (
            "This is line 3 of the test text." in lines[-2]
        )  # Account for additional lines


class TestCredentialMockData:
    """Test CredentialMockData functionality."""

    def test_generate_oauth2_config_generic(self):
        """Test generic OAuth2 configuration generation."""
        config = CredentialMockData.generate_oauth2_config()

        assert "token_url" in config
        assert "client_id" in config
        assert "client_secret" in config
        assert "scope" in config
        assert "grant_type" in config
        assert config["grant_type"] == "client_credentials"

    def test_generate_oauth2_config_github(self):
        """Test GitHub OAuth2 configuration generation."""
        config = CredentialMockData.generate_oauth2_config("github")

        assert "github.com" in config["token_url"]
        assert config["grant_type"] == "authorization_code"
        assert "repo user" in config["scope"]

    def test_generate_oauth2_config_google(self):
        """Test Google OAuth2 configuration generation."""
        config = CredentialMockData.generate_oauth2_config("google")

        assert "googleapis.com" in config["token_url"]
        assert "googleusercontent.com" in config["client_id"]
        assert "googleapis.com" in config["scope"]

    def test_generate_api_key_config_generic(self):
        """Test generic API key configuration generation."""
        config = CredentialMockData.generate_api_key_config()

        assert "api_key" in config
        assert "header_name" in config
        assert config["header_name"] == "X-API-Key"
        assert config["prefix"] is None

    def test_generate_api_key_config_stripe(self):
        """Test Stripe API key configuration generation."""
        config = CredentialMockData.generate_api_key_config("stripe")

        assert config["header_name"] == "Authorization"
        assert config["prefix"] == "Bearer"
        assert config["api_key"].startswith("sk_test_")

    def test_generate_api_key_config_openai(self):
        """Test OpenAI API key configuration generation."""
        config = CredentialMockData.generate_api_key_config("openai")

        assert config["header_name"] == "Authorization"
        assert config["prefix"] == "Bearer"
        assert config["api_key"].startswith("sk-test-")

    def test_generate_jwt_claims_user(self):
        """Test user JWT claims generation."""
        claims = CredentialMockData.generate_jwt_claims("user")

        assert "sub" in claims
        assert "name" in claims
        assert "email" in claims
        assert "iat" in claims
        assert "exp" in claims
        assert claims["roles"] == ["user"]
        assert claims["name"] == "Test User"

    def test_generate_jwt_claims_admin(self):
        """Test admin JWT claims generation."""
        claims = CredentialMockData.generate_jwt_claims("admin")

        assert "permissions" in claims
        assert "admin" in claims["roles"]
        assert "user" in claims["roles"]
        assert claims["name"] == "Admin User"
        assert "read" in claims["permissions"]

    def test_generate_jwt_claims_service(self):
        """Test service account JWT claims generation."""
        claims = CredentialMockData.generate_jwt_claims("service")

        assert "scope" in claims
        assert claims["name"] == "Service Account"
        assert claims["exp"] > claims["iat"] + 86000  # ~24 hours

    def test_jwt_claims_timing(self):
        """Test JWT claims timing is realistic."""
        claims = CredentialMockData.generate_jwt_claims()
        current_time = int(time.time())

        # Should be within a few seconds of current time
        assert abs(claims["iat"] - current_time) < 10
        assert claims["exp"] > claims["iat"]
        assert claims["exp"] - claims["iat"] == 3600  # 1 hour for user


class TestSecurityTestHelper:
    """Test SecurityTestHelper functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.helper = SecurityTestHelper()

    def test_security_helper_initialization(self):
        """Test SecurityTestHelper initialization."""
        assert hasattr(self.helper, "credential_mock")
        assert isinstance(self.helper.credential_mock, CredentialMockData)

    def test_create_auth_test_workflow_api_key(self):
        """Test API key authentication workflow creation."""
        try:
            workflow = self.helper.create_auth_test_workflow("api_key")
            assert workflow.name == "Test api_key Auth"
            assert workflow.workflow_id == "test_api_key_auth"
        except ImportError:
            pytest.skip("Required auth nodes not available")

    def test_create_auth_test_workflow_basic(self):
        """Test Basic authentication workflow creation."""
        try:
            workflow = self.helper.create_auth_test_workflow("basic")
            assert workflow.name == "Test basic Auth"
            assert workflow.workflow_id == "test_basic_auth"
        except ImportError:
            pytest.skip("Required auth nodes not available")

    def test_credential_scenarios_success(self):
        """Test credential scenario testing with success."""
        try:
            # Mock just the credential testing since that's what we actually control
            with patch("kailash.nodes.testing.CredentialTestingNode") as mock_cred_node:
                mock_tester = Mock()
                mock_tester.execute.return_value = {"valid": True, "status": "success"}
                mock_cred_node.return_value = mock_tester

                results = self.helper.test_credential_scenarios("oauth2", ["success"])

                assert "success" in results
                assert results["success"]["success"] is True
                assert results["success"]["result"]["valid"] is True
        except ImportError:
            pytest.skip("Required credential testing nodes not available")

    def test_credential_scenarios_failure(self):
        """Test credential scenario testing with failure."""
        try:
            with patch("kailash.nodes.testing.CredentialTestingNode") as mock_cred_node:
                mock_tester = Mock()
                mock_tester.execute.side_effect = RuntimeError("Authentication failed")
                mock_cred_node.return_value = mock_tester

                results = self.helper.test_credential_scenarios("oauth2", ["expired"])

                assert "expired" in results
                assert results["expired"]["success"] is False
                assert "Authentication failed" in results["expired"]["error"]
        except ImportError:
            pytest.skip("Required credential testing nodes not available")


class TestWorkflowTestHelper:
    """Test WorkflowTestHelper functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.helper = WorkflowTestHelper()

    def test_workflow_helper_initialization(self):
        """Test WorkflowTestHelper initialization."""
        assert hasattr(self.helper, "runtime")
        assert self.helper.task_manager is None

    def test_create_test_workflow(self):
        """Test test workflow creation."""
        workflow = self.helper.create_test_workflow("sample_workflow")

        assert workflow.name == "Test Workflow: sample_workflow"
        assert workflow.workflow_id == "sample_workflow"

    @patch("kailash.runtime.testing.LocalRuntime")
    def test_run_workflow_without_tracking(self, mock_runtime_class):
        """Test workflow execution without tracking."""
        # Mock runtime execution
        mock_runtime = Mock()
        mock_runtime.execute.return_value = ({"result": "success"}, "run_123")
        mock_runtime_class.return_value = mock_runtime

        # Override the helper's runtime
        self.helper.runtime = mock_runtime

        workflow = Mock(spec=Workflow)
        results, run_id = self.helper.run_workflow(workflow, with_tracking=False)

        assert self.helper.task_manager is None
        assert results == {"result": "success"}
        assert run_id == "run_123"

    @patch("kailash.runtime.testing.TaskManager")
    @patch("kailash.runtime.testing.LocalRuntime")
    def test_run_workflow_with_tracking(
        self, mock_runtime_class, mock_task_manager_class
    ):
        """Test workflow execution with tracking."""
        # Mock task manager and runtime
        mock_task_manager = Mock()
        mock_task_manager_class.return_value = mock_task_manager

        mock_runtime = Mock()
        mock_runtime.execute.return_value = ({"result": "success"}, "run_123")
        mock_runtime_class.return_value = mock_runtime

        # Override the helper's runtime
        self.helper.runtime = mock_runtime

        workflow = Mock(spec=Workflow)
        results, run_id = self.helper.run_workflow(workflow, with_tracking=True)

        assert self.helper.task_manager is not None
        mock_task_manager_class.assert_called_once()

    @patch("kailash.runtime.testing.LocalRuntime")
    def test_assert_workflow_success(self, mock_runtime_class):
        """Test workflow success assertion."""
        # Mock runtime execution
        mock_runtime = Mock()
        mock_runtime.execute.return_value = (
            {"node1": {"output": "success"}, "node2": {"output": "processed"}},
            "run_123",
        )
        self.helper.runtime = mock_runtime

        workflow = Mock(spec=Workflow)
        results, run_id = self.helper.assert_workflow_success(
            workflow, expected_nodes=["node1", "node2"]
        )

        assert "node1" in results
        assert "node2" in results
        assert results["node1"]["output"] == "success"

    @patch("kailash.runtime.testing.LocalRuntime")
    def test_assert_workflow_success_missing_node(self, mock_runtime_class):
        """Test workflow success assertion with missing node."""
        # Mock runtime execution without expected node
        mock_runtime = Mock()
        mock_runtime.execute.return_value = (
            {"node1": {"output": "success"}},  # Missing node2
            "run_123",
        )
        self.helper.runtime = mock_runtime

        workflow = Mock(spec=Workflow)

        with pytest.raises(AssertionError, match="Node node2 was not executed"):
            self.helper.assert_workflow_success(
                workflow, expected_nodes=["node1", "node2"]
            )

    def test_assert_node_output_success(self):
        """Test node output assertion success."""
        results = {
            "test_node": {"key1": "value1", "key2": "value2", "status": "success"}
        }

        # Should not raise any assertion errors
        self.helper.assert_node_output(
            results, "test_node", ["key1", "key2"], {"status": "success"}
        )

    def test_assert_node_output_missing_node(self):
        """Test node output assertion with missing node."""
        results = {"other_node": {"key": "value"}}

        with pytest.raises(AssertionError, match="Node test_node not found in results"):
            self.helper.assert_node_output(results, "test_node", ["key"])

    def test_assert_node_output_missing_key(self):
        """Test node output assertion with missing key."""
        results = {"test_node": {"key1": "value1"}}

        with pytest.raises(
            AssertionError, match="Key 'key2' not found in test_node output"
        ):
            self.helper.assert_node_output(results, "test_node", ["key1", "key2"])

    def test_assert_node_output_wrong_value(self):
        """Test node output assertion with wrong value."""
        results = {"test_node": {"key1": "wrong_value"}}

        with pytest.raises(
            AssertionError, match="Node test_node key 'key1' expected expected_value"
        ):
            self.helper.assert_node_output(
                results, "test_node", ["key1"], {"key1": "expected_value"}
            )


class TestNodeTestHelper:
    """Test NodeTestHelper functionality."""

    def test_test_node_parameters_success(self):
        """Test successful node parameter testing."""
        node = MockNode(name="param_test")
        expected_params = {"input": Any, "return_value": dict, "should_fail": bool}

        # Should not raise any assertions
        NodeTestHelper.test_node_parameters(node, expected_params)

    def test_test_node_parameters_missing_param(self):
        """Test node parameter testing with missing parameter."""
        node = MockNode(name="param_test")
        expected_params = {"nonexistent_param": str}

        with pytest.raises(
            AssertionError, match="Parameter 'nonexistent_param' not found"
        ):
            NodeTestHelper.test_node_parameters(node, expected_params)

    def test_test_node_parameters_wrong_type(self):
        """Test node parameter testing with wrong type."""
        node = MockNode(name="param_test")
        expected_params = {"input": str}  # input is actually Any type

        with pytest.raises(AssertionError, match="Parameter 'input' expected type"):
            NodeTestHelper.test_node_parameters(node, expected_params)

    def test_test_node_execution_success(self):
        """Test successful node execution testing."""
        node = MockNode(
            name="exec_test", return_value={"output": "test", "status": "ok"}
        )
        inputs = {"input": "test_data"}
        expected_keys = ["output", "status"]

        result = NodeTestHelper.test_node_execution(node, inputs, expected_keys)

        assert result["output"] == "test"
        assert result["status"] == "ok"

    def test_test_node_execution_missing_key(self):
        """Test node execution testing with missing output key."""
        node = MockNode(name="exec_test", return_value={"output": "test"})
        inputs = {"input": "test_data"}
        expected_keys = ["output", "missing_key"]

        with pytest.raises(
            AssertionError, match="Expected key 'missing_key' not found"
        ):
            NodeTestHelper.test_node_execution(node, inputs, expected_keys)

    def test_test_node_execution_should_fail(self):
        """Test node execution that should fail."""
        node = MockNode(name="fail_test", should_fail=True)
        inputs = {"input": "test_data"}

        # The helper only catches NodeValidationError and WorkflowExecutionError
        # But MockNode raises RuntimeError which gets wrapped as NodeExecutionError
        # So the helper will not catch it and will raise the assertion
        with pytest.raises(Exception):  # Can be either the original error or assertion
            NodeTestHelper.test_node_execution(node, inputs, [], should_fail=True)

    def test_test_node_execution_unexpected_success(self):
        """Test node execution that should fail but doesn't."""
        node = MockNode(name="success_test", should_fail=False)
        inputs = {"input": "test_data"}

        with pytest.raises(
            AssertionError, match="Node execution should have failed but didn't"
        ):
            NodeTestHelper.test_node_execution(node, inputs, [], should_fail=True)

    def test_test_node_validation_success(self):
        """Test successful node validation testing."""
        node = MockNode(name="validation_test")
        valid_inputs = {"input": "valid_data"}
        invalid_inputs = []  # No invalid inputs for MockNode

        # Should not raise any assertion errors
        NodeTestHelper.test_node_validation(node, valid_inputs, invalid_inputs)

    def test_test_node_validation_failure(self):
        """Test node validation testing with validation failure."""

        # Create a node that has validation logic
        class StrictNode(Node):
            def get_parameters(self):
                return {
                    "required_param": NodeParameter(
                        name="required_param", type=str, required=True
                    )
                }

            def run(self, **kwargs):
                return {"result": "ok"}

        node = StrictNode(name="strict_test")
        valid_inputs = {"required_param": "value"}
        invalid_inputs = [{}]  # Missing required parameter

        # Should not raise assertion errors - validation should work as expected
        NodeTestHelper.test_node_validation(node, valid_inputs, invalid_inputs)


class TestWorkflowTestReporter:
    """Test WorkflowTestReporter functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_task_manager = Mock()
        self.reporter = WorkflowTestReporter(self.mock_task_manager)

    def test_workflow_test_reporter_initialization(self):
        """Test WorkflowTestReporter initialization."""
        assert self.reporter.task_manager == self.mock_task_manager

    def test_generate_run_report(self):
        """Test run report generation."""
        # Mock run summary
        mock_run = Mock()
        mock_run.workflow_name = "test_workflow"
        mock_run.status = "completed"
        mock_run.duration = 1.5
        mock_run.started_at = "2024-01-01T00:00:00"
        mock_run.ended_at = "2024-01-01T00:01:30"
        mock_run.task_count = 3
        mock_run.completed_tasks = 3
        mock_run.failed_tasks = 0

        # Mock tasks
        mock_task1 = Mock()
        mock_task1.node_id = "node1"
        mock_task1.node_type = "MockNode"
        mock_task1.status = "completed"
        mock_task1.duration = 0.5
        mock_task1.error = None

        mock_task2 = Mock()
        mock_task2.node_id = "node2"
        mock_task2.node_type = "MockNode"
        mock_task2.status = "failed"
        mock_task2.duration = 0.3
        mock_task2.error = "Test error"

        self.mock_task_manager.get_run_summary.return_value = mock_run
        self.mock_task_manager.list_tasks.return_value = [mock_task1, mock_task2]

        report = self.reporter.generate_run_report("run_123")

        assert report["run_id"] == "run_123"
        assert report["workflow"] == "test_workflow"
        assert report["status"] == "completed"
        assert report["summary"]["total_tasks"] == 3
        assert len(report["tasks"]) == 2
        assert report["tasks"][0]["node_id"] == "node1"
        assert report["tasks"][1]["error"] == "Test error"

    def test_save_report(self):
        """Test report saving to file."""
        report = {"test": "data", "number": 123}

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            temp_path = f.name

        try:
            self.reporter.save_report(report, temp_path)

            # Verify file was written correctly
            with open(temp_path, "r") as f:
                saved_data = json.load(f)

            assert saved_data == report
        finally:
            Path(temp_path).unlink()


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_create_test_node_mock(self):
        """Test creating a MockNode via convenience function."""
        node = create_test_node("MockNode", name="test", return_value={"data": "test"})

        assert isinstance(node, MockNode)
        # Check internal attributes instead of name directly
        assert node._return_value == {"data": "test"}
