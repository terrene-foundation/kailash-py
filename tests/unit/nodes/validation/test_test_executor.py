"""Unit tests for TestExecutor class.

Tests validation framework components in isolation with mocks.
Following testing policy: Unit tests must be fast (<1s), use mocks, no external dependencies.
"""

from unittest.mock import MagicMock, patch

import pytest
from kailash.nodes.validation.test_executor import (
    ValidationLevel,
    ValidationResult,
    ValidationTestExecutor,
)


class TestValidationTestExecutor:
    """Test the TestExecutor class."""

    def test_init(self):
        """Test TestExecutor initialization."""
        executor = ValidationTestExecutor()
        assert executor.sandbox_enabled is True
        assert executor.timeout == 30

        executor = ValidationTestExecutor(sandbox_enabled=False, timeout=60)
        assert executor.sandbox_enabled is False
        assert executor.timeout == 60

    def test_validate_python_syntax_valid(self):
        """Test syntax validation with valid code."""
        executor = ValidationTestExecutor()
        code = """
def hello_world():
    print("Hello, World!")
    return True
"""
        result = executor.validate_python_syntax(code)

        assert isinstance(result, ValidationResult)
        assert result.passed is True
        assert result.level == ValidationLevel.SYNTAX
        assert result.test_name == "python_syntax"
        assert result.error is None
        assert result.details["line_count"] == 4
        assert result.details["has_functions"] is True
        assert result.details["has_classes"] is False

    def test_validate_python_syntax_invalid(self):
        """Test syntax validation with invalid code."""
        executor = ValidationTestExecutor()
        code = """
def broken_function()  # Missing colon
    print("This won't work")
"""
        result = executor.validate_python_syntax(code)

        assert result.passed is False
        assert result.error is not None
        # Different Python versions have different error messages
        assert any(
            err in result.error.lower() for err in ["invalid syntax", "expected ':'"]
        )
        assert len(result.suggestions) > 0
        assert any("colon" in s for s in result.suggestions)

    def test_validate_imports_valid(self):
        """Test import validation with standard library imports."""
        executor = ValidationTestExecutor()
        code = """
import os
import sys
from datetime import datetime
"""
        result = executor.validate_imports(code)

        assert result.passed is True
        assert result.level == ValidationLevel.IMPORTS
        assert result.details["total_imports"] == 3
        assert result.details["resolved"] == 3
        assert result.details["unresolved"] == 0

    def test_validate_imports_invalid(self):
        """Test import validation with non-existent module."""
        executor = ValidationTestExecutor()
        code = """
import os
import nonexistent_module_xyz
from fake_package import something
"""
        result = executor.validate_imports(code)

        assert result.passed is False
        assert result.details["unresolved"] == 2
        assert len(result.suggestions) == 2
        assert any("nonexistent_module_xyz" in s for s in result.suggestions)

    @patch("subprocess.run")
    def test_execute_code_safely_subprocess_success(self, mock_run):
        """Test code execution in subprocess mode with success."""
        # Mock successful subprocess execution
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"success": true, "results": {"result": 10}}'
        mock_run.return_value = mock_result

        executor = ValidationTestExecutor(sandbox_enabled=True)
        code = "result = 5 + 5"
        result = executor.execute_code_safely(code)

        assert result.passed is True
        assert result.level == ValidationLevel.SEMANTIC
        assert result.details["execution_mode"] == "subprocess"
        assert "result" in result.details["output_keys"]

    @patch("subprocess.run")
    def test_execute_code_safely_subprocess_error(self, mock_run):
        """Test code execution in subprocess mode with error."""
        # Mock subprocess execution with error
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"success": false, "error": "NameError: name \'undefined\' is not defined", "error_type": "NameError"}'
        mock_run.return_value = mock_result

        executor = ValidationTestExecutor(sandbox_enabled=True)
        code = "result = undefined + 5"
        result = executor.execute_code_safely(code)

        assert result.passed is False
        assert "NameError" in result.error
        # Suggestions are generated from traceback which we're mocking

    def test_execute_code_safely_direct_success(self):
        """Test code execution in direct mode with success."""
        executor = ValidationTestExecutor(sandbox_enabled=False)
        code = "result = {'value': 42}"
        result = executor.execute_code_safely(code)

        assert result.passed is True
        assert result.details["execution_mode"] == "direct"
        assert "result" in result.details["output_keys"]
        assert result.details["output_types"]["result"] == "dict"

    def test_execute_code_safely_direct_error(self):
        """Test code execution in direct mode with error."""
        executor = ValidationTestExecutor(sandbox_enabled=False)
        code = "result = 1 / 0"
        result = executor.execute_code_safely(code)

        assert result.passed is False
        assert "division by zero" in result.error
        assert result.details["error_type"] == "ZeroDivisionError"

    def test_validate_output_schema_valid(self):
        """Test schema validation with matching output."""
        executor = ValidationTestExecutor()
        output = {"name": "test", "value": 42, "items": [1, 2, 3]}
        schema = {"name": str, "value": int, "items": [int]}

        result = executor.validate_output_schema(output, schema)

        assert result.passed is True
        assert result.level == ValidationLevel.FUNCTIONAL
        assert result.details["error_count"] == 0

    def test_validate_output_schema_invalid(self):
        """Test schema validation with mismatched output."""
        executor = ValidationTestExecutor()
        output = {"name": "test", "value": "not_a_number"}
        schema = {"name": str, "value": int, "missing_key": str}

        result = executor.validate_output_schema(output, schema)

        assert result.passed is False
        assert result.details["error_count"] > 0
        assert any("missing_key" in e for e in result.details["errors"])
        assert any("expected int" in e for e in result.details["errors"])

    def test_run_test_suite_all_pass(self):
        """Test running a test suite where all tests pass."""
        executor = ValidationTestExecutor(sandbox_enabled=False)
        code = """
def double(x):
    result = x * 2
"""
        test_suite = [
            {"name": "test_positive", "inputs": {"x": 5}, "expected_output": None},
            {"name": "test_negative", "inputs": {"x": -3}, "expected_output": None},
        ]

        result = executor.run_test_suite(code, test_suite)

        assert result.passed is True
        assert result.details["total_tests"] == 2
        assert result.details["passed"] == 2
        assert result.details["failed"] == 0

    def test_run_test_suite_with_failures(self):
        """Test running a test suite with failures."""
        executor = ValidationTestExecutor(sandbox_enabled=False)
        code = """
result = undefined_variable
"""
        test_suite = [{"name": "test_error", "inputs": {}, "expected_output": None}]

        result = executor.run_test_suite(code, test_suite)

        assert result.passed is False
        assert result.details["failed"] == 1

    def test_extract_error_line(self):
        """Test error line extraction from traceback."""
        executor = ValidationTestExecutor()
        traceback = """Traceback (most recent call last):
  File "test.py", line 42, in <module>
    result = 1 / 0
ZeroDivisionError: division by zero"""

        line = executor._extract_error_line(traceback)
        assert line == 42

    def test_get_error_suggestions(self):
        """Test error suggestion generation."""
        executor = ValidationTestExecutor()

        # Test NameError suggestions
        suggestions = executor._get_error_suggestions(
            NameError("name 'x' is not defined"), ""
        )
        assert any("variable names" in s for s in suggestions)

        # Test TypeError suggestions
        suggestions = executor._get_error_suggestions(
            TypeError("unsupported operand type(s)"), ""
        )
        assert any("arguments" in s for s in suggestions)

        # Test AttributeError suggestions
        suggestions = executor._get_error_suggestions(
            AttributeError("'NoneType' object has no attribute 'foo'"), ""
        )
        assert any("attribute" in s for s in suggestions)
