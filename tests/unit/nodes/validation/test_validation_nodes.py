"""Unit tests for validation nodes.

Tests validation nodes in isolation with mocks.
Following testing policy: Unit tests must be fast (<1s), use mocks, no external dependencies.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Store original pandas module if it exists
_original_pandas = sys.modules.get("pandas")


@pytest.fixture(autouse=True)
def mock_pandas_for_validation():
    """Mock pandas for validation tests and clean up afterward."""
    # Mock pandas for unit tests
    mock_pandas = MagicMock()
    mock_pandas.DataFrame = type("DataFrame", (), {})
    mock_pandas.Series = type("Series", (), {})
    sys.modules["pandas"] = mock_pandas

    yield mock_pandas

    # Clean up: restore original pandas module
    if _original_pandas is not None:
        sys.modules["pandas"] = _original_pandas
    else:
        sys.modules.pop("pandas", None)


# Import after mock setup to avoid import issues
# ruff: noqa: E402
from kailash.nodes.validation.test_executor import ValidationLevel, ValidationResult
from kailash.nodes.validation.validation_nodes import (
    CodeValidationNode,
    ValidationTestSuiteExecutorNode,
    WorkflowValidationNode,
)


class TestCodeValidationNode:
    """Test the CodeValidationNode class."""

    def test_node_registration(self):
        """Test that node is properly registered."""
        node = CodeValidationNode()
        assert node.__class__.__name__ == "CodeValidationNode"

    def test_get_parameters(self):
        """Test parameter definitions."""
        node = CodeValidationNode()
        params = node.get_parameters()

        assert "code" in params
        assert params["code"].required is True
        assert params["code"].type == str

        assert "validation_levels" in params
        assert params["validation_levels"].required is False
        assert params["validation_levels"].default == ["syntax", "imports", "semantic"]

        assert "test_inputs" in params
        assert params["test_inputs"].type == dict

        assert "timeout" in params
        assert params["timeout"].default == 30

    @patch("kailash.nodes.validation.validation_nodes.ValidationTestExecutor")
    def test_run_syntax_validation_only(self, mock_executor_class):
        """Test running only syntax validation."""
        # Setup mock
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor

        mock_result = ValidationResult(
            level=ValidationLevel.SYNTAX,
            passed=True,
            test_name="python_syntax",
            details={"line_count": 3},
        )
        mock_executor.validate_python_syntax.return_value = mock_result

        # Run node
        node = CodeValidationNode()
        result = node.execute(code="print('hello')", validation_levels=["syntax"])

        # Verify
        assert result["validated"] is True
        assert result["validation_status"] == "PASSED"
        assert result["summary"]["total_tests"] == 1
        assert result["summary"]["passed"] == 1
        mock_executor.validate_python_syntax.assert_called_once()

    @patch("kailash.nodes.validation.validation_nodes.ValidationTestExecutor")
    def test_run_syntax_validation_failure(self, mock_executor_class):
        """Test syntax validation failure stops early."""
        # Setup mock
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor

        mock_result = ValidationResult(
            level=ValidationLevel.SYNTAX,
            passed=False,
            test_name="python_syntax",
            error="SyntaxError: invalid syntax",
            suggestions=["Check for missing colons"],
        )
        mock_executor.validate_python_syntax.return_value = mock_result

        # Run node
        node = CodeValidationNode()
        result = node.execute(
            code="def broken(", validation_levels=["syntax", "imports", "semantic"]
        )

        # Verify - should stop after syntax failure
        assert result["validated"] is False
        assert result["validation_status"] == "FAILED"
        assert result["summary"]["total_tests"] == 1
        mock_executor.validate_python_syntax.assert_called_once()
        mock_executor.validate_imports.assert_not_called()
        mock_executor.execute_code_safely.assert_not_called()

    @patch("kailash.nodes.validation.validation_nodes.ValidationTestExecutor")
    def test_run_multiple_validations(self, mock_executor_class):
        """Test running multiple validation levels."""
        # Setup mock
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor

        # Mock successful results
        syntax_result = ValidationResult(
            level=ValidationLevel.SYNTAX, passed=True, test_name="syntax"
        )
        import_result = ValidationResult(
            level=ValidationLevel.IMPORTS, passed=True, test_name="imports"
        )
        semantic_result = ValidationResult(
            level=ValidationLevel.SEMANTIC, passed=True, test_name="semantic"
        )

        mock_executor.validate_python_syntax.return_value = syntax_result
        mock_executor.validate_imports.return_value = import_result
        mock_executor.execute_code_safely.return_value = semantic_result

        # Run node
        node = CodeValidationNode()
        result = node.execute(
            code="import os\nresult = os.path.exists('.')",
            validation_levels=["syntax", "imports", "semantic"],
            test_inputs={},
        )

        # Verify
        assert result["validated"] is True
        assert result["summary"]["total_tests"] == 3
        assert result["summary"]["passed"] == 3
        assert len(result["validation_results"]) == 3


class TestWorkflowValidationNode:
    """Test the WorkflowValidationNode class."""

    def test_node_registration(self):
        """Test that node is properly registered."""
        node = WorkflowValidationNode()
        assert node.__class__.__name__ == "WorkflowValidationNode"

    def test_get_parameters(self):
        """Test parameter definitions."""
        node = WorkflowValidationNode()
        params = node.get_parameters()

        assert "workflow_code" in params
        assert params["workflow_code"].required is True

        assert "validate_execution" in params
        assert params["validate_execution"].default is False

        assert "expected_nodes" in params
        assert "required_connections" in params

    @patch("kailash.nodes.validation.validation_nodes.ValidationTestExecutor")
    def test_validate_workflow_syntax_error(self, mock_executor_class):
        """Test workflow validation with syntax error."""
        # Setup mock
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor

        mock_result = ValidationResult(
            level=ValidationLevel.SYNTAX,
            passed=False,
            test_name="syntax",
            error="SyntaxError",
        )
        mock_executor.validate_python_syntax.return_value = mock_result

        # Run node
        node = WorkflowValidationNode()
        result = node.execute(workflow_code="invalid python code")

        # Verify
        assert result["validated"] is False
        assert result["validation_status"] == "FAILED"
        assert result["error_count"] == 1
        assert "Syntax error" in result["validation_details"]["errors"][0]

    @patch("kailash.nodes.validation.validation_nodes.ValidationTestExecutor")
    def test_validate_workflow_structure(self, mock_executor_class):
        """Test workflow structure validation."""
        # Setup mocks
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor
        mock_executor.validate_python_syntax.return_value = ValidationResult(
            level=ValidationLevel.SYNTAX, passed=True, test_name="syntax"
        )

        # Create a proper mock class that behaves like WorkflowBuilder
        class MockWorkflowBuilder:
            def __init__(self):
                self.add_node = MagicMock()
                self.connect = MagicMock()

            def build(self):
                return {
                    "nodes": {"reader": {}, "processor": {}},
                    "connections": [{"from_node": "reader", "to_node": "processor"}],
                }

        # Run node with workflow code
        node = WorkflowValidationNode()

        # Mock the _get_workflow_builder_class method to return our mock class
        mock_get_builder = MagicMock(return_value=MockWorkflowBuilder)
        node._get_workflow_builder_class = mock_get_builder

        result = node.execute(
            workflow_code="workflow = WorkflowBuilder()",
            expected_nodes=["reader", "processor"],
            required_connections=[{"from": "reader", "to": "processor"}],
        )

        # Verify
        assert result["validated"] is True
        assert result["validation_details"]["structure_valid"] is True
        assert result["validation_details"]["node_count"] == 2


class TestValidationTestSuiteExecutorNode:
    """Test the TestSuiteExecutorNode class."""

    def test_node_registration(self):
        """Test that node is properly registered."""
        node = ValidationTestSuiteExecutorNode()
        assert node.__class__.__name__ == "ValidationTestSuiteExecutorNode"

    def test_get_parameters(self):
        """Test parameter definitions."""
        node = ValidationTestSuiteExecutorNode()
        params = node.get_parameters()

        assert "code" in params
        assert params["code"].required is True

        assert "test_suite" in params
        assert params["test_suite"].required is True
        assert params["test_suite"].type == list

        assert "stop_on_failure" in params
        assert params["stop_on_failure"].default is False

    @patch("kailash.nodes.validation.validation_nodes.ValidationTestExecutor")
    def test_run_test_suite(self, mock_executor_class):
        """Test running a test suite."""
        # Setup mock
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor

        mock_result = ValidationResult(
            level=ValidationLevel.FUNCTIONAL,
            passed=True,
            test_name="test_suite",
            details={
                "total_tests": 2,
                "passed": 2,
                "failed": 0,
                "results": [
                    {"name": "test1", "passed": True},
                    {"name": "test2", "passed": True},
                ],
            },
        )
        mock_executor.run_test_suite.return_value = mock_result

        # Run node
        node = ValidationTestSuiteExecutorNode()
        test_suite = [
            {"name": "test1", "inputs": {"x": 1}},
            {"name": "test2", "inputs": {"x": 2}},
        ]
        result = node.execute(code="def f(x): return x", test_suite=test_suite)

        # Verify
        assert result["all_tests_passed"] is True
        assert result["validation_status"] == "PASSED"
        assert result["summary"]["total"] == 2
        assert result["summary"]["passed"] == 2
        mock_executor.run_test_suite.assert_called_once()

    @patch("kailash.nodes.validation.validation_nodes.ValidationTestExecutor")
    def test_run_test_suite_with_failures(self, mock_executor_class):
        """Test running a test suite with failures."""
        # Setup mock
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor

        mock_result = ValidationResult(
            level=ValidationLevel.FUNCTIONAL,
            passed=False,
            test_name="test_suite",
            details={
                "total_tests": 3,
                "passed": 1,
                "failed": 2,
                "results": [
                    {"name": "test1", "passed": True},
                    {"name": "test2", "passed": False},
                    {"name": "test3", "passed": False},
                ],
            },
            error="2 tests failed",
        )
        mock_executor.run_test_suite.return_value = mock_result

        # Run node
        node = ValidationTestSuiteExecutorNode()
        result = node.execute(code="def f(x): raise Error", test_suite=[])

        # Verify
        assert result["all_tests_passed"] is False
        assert result["validation_status"] == "FAILED"
        assert result["summary"]["failed"] == 2
