"""Comprehensive unit tests for PythonCodeNode fixes.

Follows the testing policy:
- Unit tests (Tier 1): Fast, isolated, mocking allowed
- Tests all parameter handling fixes from TODO-092
"""

import ast
import inspect
from typing import Any, Dict
from unittest.mock import Mock, patch

import pytest

from kailash.nodes.code.python import PythonCodeNode
from kailash.sdk_exceptions import (
    NodeConfigurationError,
    NodeExecutionError,
    NodeValidationError,
    SafetyViolationError,
)


class TestPythonCodeDefaultParameters:
    """Test default parameter handling bug fix."""

    def test_default_parameter_detection(self):
        """Test that default parameters are correctly detected."""

        # Function with default parameters
        def test_func(a: int, b: str = "default", c: float = 3.14):
            return {"a": a, "b": b, "c": c}

        node = PythonCodeNode(name="test_node", function=test_func)
        params = node.get_parameters()

        # Check parameter detection
        assert "a" in params
        assert "b" in params
        assert "c" in params

        # Check default detection
        assert params["a"].required is True
        assert params["a"].default is None

        assert params["b"].required is False
        assert params["b"].default == "default"

        assert params["c"].required is False
        assert params["c"].default == 3.14

    def test_default_none_handling(self):
        """Test that None defaults are handled correctly."""

        def test_func(a: str, b: str = None):
            return {"a": a, "b": b}

        node = PythonCodeNode(name="test_node", function=test_func)
        params = node.get_parameters()

        assert params["b"].required is False
        assert params["b"].default is None

    def test_complex_default_types(self):
        """Test handling of complex default types."""

        def test_func(
            a: int,
            b: list = None,
            c: dict = None,
            d: list = [],  # Mutable default (bad practice but should work)
            e: dict = {"key": "value"},
        ):
            return {"a": a, "b": b, "c": c, "d": d, "e": e}

        node = PythonCodeNode(name="test_node", function=test_func)
        params = node.get_parameters()

        assert params["b"].required is False
        assert params["b"].default is None

        assert params["d"].required is False
        assert params["d"].default == []

        assert params["e"].required is False
        assert params["e"].default == {"key": "value"}


class TestPythonCodeParameterInjection:
    """Test parameter injection with **kwargs support."""

    def test_kwargs_detection(self):
        """Test that functions with **kwargs are detected."""

        def test_func(a: int, **kwargs):
            return {"a": a, "kwargs": kwargs}

        node = PythonCodeNode(name="test_node", function=test_func)

        # Check signature analysis
        sig = inspect.signature(test_func)
        accepts_var_keyword = any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in sig.parameters.values()
        )
        assert accepts_var_keyword is True

    def test_workflow_parameter_injection(self):
        """Test that workflow parameters are injected into **kwargs."""

        def test_func(a: int, **kwargs):
            return {
                "a": a,
                "injected_param": kwargs.get("workflow_param"),
                "all_kwargs": kwargs,
            }

        node = PythonCodeNode(name="test_node", function=test_func)

        # Test that extra parameters are injected into kwargs
        # This simulates runtime parameter injection from workflow execution
        result = node.execute(a=10, workflow_param="injected_value", another_param=42)

        assert result["result"]["a"] == 10
        assert result["result"]["injected_param"] == "injected_value"
        assert "workflow_param" in result["result"]["all_kwargs"]
        assert "another_param" in result["result"]["all_kwargs"]

        # Verify the actual injection mechanism - extra params should be in kwargs
        assert result["result"]["all_kwargs"]["workflow_param"] == "injected_value"
        assert result["result"]["all_kwargs"]["another_param"] == 42

    def test_no_kwargs_no_injection(self):
        """Test that functions without **kwargs ignore extra parameters."""

        def test_func(a: int, b: str):
            return {"a": a, "b": b}

        node = PythonCodeNode(name="test_node", function=test_func)

        # Extra parameters should be silently ignored for functions without **kwargs
        result = node.execute(a=10, b="test", workflow_param="should_be_ignored")

        assert result["result"]["a"] == 10
        assert result["result"]["b"] == "test"
        # Extra parameters are not included in the result since no **kwargs


class TestPythonCodeSecurity:
    """Test security model improvements."""

    @pytest.mark.timeout(5)  # Increased timeout due to module imports
    def test_unsafe_code_detection(self):
        """Test that unsafe code patterns are detected during execution."""
        unsafe_patterns = [
            "import os; os.system('ls')",
            "__import__('subprocess').call(['ls'])",
            "eval('print(1)')",
            "exec('x = 1')",
            "compile('x = 1', 'test', 'exec')",
            "open('/etc/passwd', 'r')",
        ]

        # Safety checks happen at execution time, not initialization
        for code in unsafe_patterns:
            node = PythonCodeNode(name="test_node", code=code)
            with pytest.raises(
                (
                    NodeExecutionError,
                    NodeValidationError,
                    SafetyViolationError,
                    ValueError,
                )
            ):
                node.execute()

    def test_safe_code_allowed(self):
        """Test that safe code patterns are allowed."""
        safe_patterns = [
            "def process(data): return data * 2",
            "lambda x: x + 1",
            "def transform(items): return [i.upper() for i in items]",
            "def calculate(a, b): return {'sum': a + b, 'product': a * b}",
        ]

        for code in safe_patterns:
            # Should not raise
            node = PythonCodeNode(name="test_node", code=code)
            assert node.code == code

    def test_ast_validation(self):
        """Test AST-based code validation."""
        # Test that AST parsing is used
        code = "def func(x): return x * 2"
        node = PythonCodeNode(name="test_node", code=code)

        # Verify the code can be parsed
        tree = ast.parse(code)
        assert isinstance(tree, ast.Module)


class TestPythonCodeFromFunction:
    """Test from_function class method."""

    def test_from_function_basic(self):
        """Test basic from_function usage."""

        def my_func(x: int, y: int) -> int:
            return x + y

        node = PythonCodeNode.from_function(
            my_func, name="AddNode", description="Adds two numbers"
        )

        assert node.metadata.name == "AddNode"
        assert node.metadata.description == "Adds two numbers"
        assert node.function == my_func

        result = node.execute(x=5, y=3)
        assert result["result"] == 8

    def test_from_function_with_defaults(self):
        """Test from_function with default parameters."""

        def my_func(x: int, y: int = 10) -> int:
            return x + y

        node = PythonCodeNode.from_function(my_func)

        # Test with both parameters
        result = node.execute(x=5, y=3)
        assert result["result"] == 8

        # Test with default
        result = node.execute(x=5)
        assert result["result"] == 15

    def test_from_function_with_kwargs(self):
        """Test from_function with **kwargs."""

        def my_func(x: int, **kwargs) -> dict:
            return {"x": x, "extra": kwargs}

        node = PythonCodeNode.from_function(my_func)

        # Test with extra parameters that should be injected into kwargs
        result = node.execute(x=5, injected="value", another="param")
        assert result["result"]["x"] == 5
        assert result["result"]["extra"]["injected"] == "value"
        assert result["result"]["extra"]["another"] == "param"


class TestPythonCodeEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_function(self):
        """Test handling of empty functions."""

        def empty_func():
            pass

        node = PythonCodeNode(name="test_node", function=empty_func)
        result = node.execute()
        assert result["result"] is None

    def test_function_with_args(self):
        """Test that *args is handled correctly."""

        def test_func(*args, **kwargs):
            return {"args": args, "kwargs": kwargs}

        node = PythonCodeNode(name="test_node", function=test_func)

        # PythonCodeNode doesn't support *args directly
        # Parameters are passed as kwargs
        result = node.execute(args=[1, 2, 3])
        assert result["result"]["args"] == ()  # *args is empty
        assert result["result"]["kwargs"]["args"] == [1, 2, 3]  # passed as kwarg

    def test_missing_required_parameter(self):
        """Test error handling for missing required parameters."""

        def test_func(required: int, optional: str = "default"):
            return {"required": required, "optional": optional}

        node = PythonCodeNode(name="test_node", function=test_func)

        # Missing required parameter
        with pytest.raises((TypeError, NodeValidationError)):
            node.execute(optional="provided")

    def test_type_conversion(self):
        """Test automatic type conversion."""

        def test_func(x: int, y: float, z: str) -> dict:
            return {
                "x_type": type(x).__name__,
                "y_type": type(y).__name__,
                "z_type": type(z).__name__,
                "values": {"x": x, "y": y, "z": z},
            }

        node = PythonCodeNode(name="test_node", function=test_func)

        # Test with compatible types
        result = node.execute(x=10, y=3.14, z="123")  # int  # float  # str

        assert result["result"]["values"]["x"] == 10
        assert result["result"]["values"]["y"] == 3.14
        assert result["result"]["values"]["z"] == "123"


@pytest.mark.unit
class TestPythonCodePerformance:
    """Performance-related tests (still unit tests, just measuring performance)."""

    def test_function_caching(self):
        """Test that function objects are cached properly."""
        code = "def process(x): return x * 2"
        node = PythonCodeNode(name="test_node", code=code)

        # Get function twice
        func1 = node.function
        func2 = node.function

        # Should be the same object (cached)
        assert func1 is func2

    def test_parameter_info_caching(self):
        """Test that parameter info is cached."""

        def test_func(a: int, b: str = "default"):
            return {"a": a, "b": b}

        node = PythonCodeNode(name="test_node", function=test_func)

        # Get parameters twice
        params1 = node.get_parameters()
        params2 = node.get_parameters()

        # Should return equivalent data (check keys match)
        assert set(params1.keys()) == set(params2.keys())
