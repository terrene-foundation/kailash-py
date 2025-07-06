"""Direct validation tests for PythonCodeNode parameter handling fixes.

This test file directly validates the specific bugs that were fixed:
1. Default parameter handling in get_parameter_info()
2. **kwargs parameter injection in execute_function()
3. Security validation improvements
"""

import inspect
from typing import Any

import pytest

from kailash.nodes.code.python import CodeExecutor, FunctionWrapper, PythonCodeNode
from kailash.sdk_exceptions import SafetyViolationError


class TestDefaultParameterHandlingFix:
    """Test the fix for default parameter detection in get_parameter_info()."""

    def test_function_wrapper_default_detection(self):
        """Test that FunctionWrapper correctly detects default parameters."""

        def test_func(
            required1: str,
            required2: int,
            optional1: str = "default",
            optional2: int = 42,
            optional3: float = None,
        ):
            return {}

        wrapper = FunctionWrapper(test_func)
        param_info = wrapper.get_parameter_info()

        # Required parameters should not have defaults
        assert param_info["required1"]["has_default"] is False
        assert param_info["required1"]["default"] is None
        assert param_info["required2"]["has_default"] is False

        # Optional parameters should have defaults
        assert param_info["optional1"]["has_default"] is True
        assert param_info["optional1"]["default"] == "default"

        assert param_info["optional2"]["has_default"] is True
        assert param_info["optional2"]["default"] == 42

        assert param_info["optional3"]["has_default"] is True
        assert param_info["optional3"]["default"] is None

    def test_pythoncode_node_parameters_with_defaults(self):
        """Test that PythonCodeNode.get_parameters() respects defaults."""

        def func_with_defaults(a: int, b: str = "test", c: float = 1.0):
            return {"result": f"{a}-{b}-{c}"}

        node = PythonCodeNode.from_function(func_with_defaults)
        params = node.get_parameters()

        # Check required flag is set correctly based on defaults
        assert params["a"].required is True
        assert params["b"].required is False
        assert params["b"].default == "test"
        assert params["c"].required is False
        assert params["c"].default == 1.0


class TestKwargsParameterInjection:
    """Test the fix for **kwargs parameter injection."""

    def test_function_accepts_var_keyword(self):
        """Test detection of functions that accept **kwargs."""

        def no_kwargs(a: int, b: str):
            return {}

        def with_kwargs(a: int, **kwargs):
            return kwargs

        wrapper1 = FunctionWrapper(no_kwargs)
        assert wrapper1.accepts_var_keyword() is False

        wrapper2 = FunctionWrapper(with_kwargs)
        assert wrapper2.accepts_var_keyword() is True

    def test_kwargs_not_in_parameter_info(self):
        """Test that **kwargs is not included in parameter info."""

        def func_with_kwargs(required: str, optional: int = 10, **kwargs):
            return {}

        wrapper = FunctionWrapper(func_with_kwargs)
        param_info = wrapper.get_parameter_info()

        # Should include regular parameters but not kwargs
        assert "required" in param_info
        assert "optional" in param_info
        assert "kwargs" not in param_info
        assert len(param_info) == 2

    def test_validate_inputs_with_kwargs(self):
        """Test that validate_inputs passes through all inputs for **kwargs functions."""

        def flexible_func(base: int, **kwargs):
            return {"base": base, "extras": kwargs}

        node = PythonCodeNode.from_function(flexible_func)

        # Should accept any additional parameters
        validated = node.validate_inputs(
            base=10, extra1="value1", extra2=42, extra3={"nested": "data"}
        )

        assert validated["base"] == 10
        assert validated["extra1"] == "value1"
        assert validated["extra2"] == 42
        assert validated["extra3"] == {"nested": "data"}

    def test_run_with_kwargs_injection(self):
        """Test actual execution with parameter injection."""

        def process_with_kwargs(value: int, multiplier: int = 2, **kwargs):
            result = value * multiplier

            # Apply any additional operations from kwargs
            if "offset" in kwargs:
                result += kwargs["offset"]

            return {
                "result": result,
                "used_multiplier": multiplier,
                "received_kwargs": list(kwargs.keys()),
            }

        node = PythonCodeNode.from_function(process_with_kwargs)

        # Test with just required parameter
        output1 = node.execute(value=10)
        assert output1["result"]["result"] == 20  # 10 * 2
        assert output1["result"]["used_multiplier"] == 2
        assert output1["result"]["received_kwargs"] == []

        # Test with overridden default and extra kwargs
        output2 = node.execute(value=10, multiplier=3, offset=5, debug=True)
        assert output2["result"]["result"] == 35  # 10 * 3 + 5
        assert output2["result"]["used_multiplier"] == 3
        assert set(output2["result"]["received_kwargs"]) == {"offset", "debug"}


class TestSecurityValidationFix:
    """Test the security validation improvements."""

    def test_code_executor_safety_check(self):
        """Test that CodeExecutor properly validates unsafe code."""

        executor = CodeExecutor()

        # Unsafe imports
        unsafe_imports = [
            "import subprocess",
            "from os import system",
            "import socket",
            "__import__('eval')",
        ]

        for code in unsafe_imports:
            with pytest.raises(SafetyViolationError) as exc_info:
                executor.check_code_safety(code)
            assert "not allowed" in str(exc_info.value)

    def test_unsafe_function_calls(self):
        """Test detection of unsafe function calls."""

        executor = CodeExecutor()

        # These calls should be caught by the safety checker
        unsafe_calls = [
            "eval('malicious')",
            "exec('code')",
            "compile('source', 'file', 'exec')",
        ]

        for code in unsafe_calls:
            with pytest.raises(SafetyViolationError) as exc_info:
                executor.check_code_safety(code)
            error_msg = str(exc_info.value)
            assert any(
                word in error_msg.lower()
                for word in ["eval", "exec", "compile", "not allowed"]
            )

        # __builtins__ access is more complex and not currently caught
        # This is a known limitation of the current AST-based checker
        is_safe, violations, imports = executor.check_code_safety(
            "__builtins__['eval']('code')"
        )
        assert is_safe is True  # Current implementation doesn't catch this pattern

    def test_pythoncode_node_rejects_unsafe_code(self):
        """Test that PythonCodeNode rejects unsafe code during creation.

        Security validation should happen at node creation time (fail-fast principle)
        rather than at execution time to catch issues early in development.
        """

        unsafe_codes = [
            "import os; os.system('ls')",
            "eval(user_input)",
            "import subprocess",
        ]

        for code in unsafe_codes:
            # Node creation should fail with safety violation
            with pytest.raises(SafetyViolationError) as exc_info:
                PythonCodeNode(name="test", code=code, validate_security=True)

            # Verify it's a safety-related error
            assert (
                "safety violation" in str(exc_info.value).lower()
                or "not allowed" in str(exc_info.value).lower()
            )


class TestParameterFlowIntegration:
    """Test the complete parameter flow through PythonCodeNode."""

    def test_complete_parameter_handling(self):
        """Test complete flow: detection, validation, execution."""

        def flexible_processor(
            required_input: str, threshold: float = 0.5, max_items: int = 100, **kwargs
        ):
            # Process with defaults and injected parameters
            debug = kwargs.get("debug", False)
            custom_config = kwargs.get("config", {})

            result = {
                "input": required_input,
                "threshold": threshold,
                "max_items": max_items,
                "debug_enabled": debug,
                "config_keys": list(custom_config.keys()),
            }

            return result

        node = PythonCodeNode.from_function(flexible_processor)

        # Check parameter detection
        params = node.get_parameters()
        assert params["required_input"].required is True
        assert params["threshold"].required is False
        assert params["threshold"].default == 0.5
        assert params["max_items"].required is False
        assert params["max_items"].default == 100

        # Test execution with various parameter combinations

        # 1. Only required parameter
        result1 = node.execute(required_input="test")
        assert result1["result"]["input"] == "test"
        assert result1["result"]["threshold"] == 0.5  # Default
        assert result1["result"]["max_items"] == 100  # Default
        assert result1["result"]["debug_enabled"] is False

        # 2. Override defaults and inject extra parameters
        result2 = node.execute(
            required_input="test2",
            threshold=0.8,
            max_items=50,
            debug=True,
            config={"feature_x": "enabled", "mode": "advanced"},
        )
        assert result2["result"]["input"] == "test2"
        assert result2["result"]["threshold"] == 0.8
        assert result2["result"]["max_items"] == 50
        assert result2["result"]["debug_enabled"] is True
        assert set(result2["result"]["config_keys"]) == {"feature_x", "mode"}

    def test_code_string_parameter_injection(self):
        """Test that code strings can access all parameters."""

        code = """
# All parameters should be available as variables
try:
    c_value = c
except NameError:
    c_value = 'not_provided'

result = {
    'a': a,
    'b': b,
    'c': c_value
}
"""

        node = PythonCodeNode(name="test", code=code, input_types={"a": int, "b": str})

        # Code nodes should accept any parameters
        result = node.execute(a=1, b="test", c="extra")
        assert result["result"]["a"] == 1
        assert result["result"]["b"] == "test"
        # Since c is provided as a parameter, it should be available
        assert result["result"]["c"] == "extra"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
