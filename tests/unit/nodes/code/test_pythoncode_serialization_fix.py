"""Comprehensive unit tests for PythonCodeNode serialization fix (TODO-129).

This test suite follows TDD methodology to implement fixes for the PythonCodeNode
serialization issue where function returns fail JSON serialization in platform
context while working in standalone tests.

Test Strategy:
- Tier 1 (Unit): Fast tests with mocks to isolate serialization behavior
- Test current double-wrapping behavior (failing tests first)
- Validate JSON serialization with various data types
- Test smart result wrapping logic
- Verify backward compatibility mode

Coverage Areas:
1. Current double-wrapping behavior (demonstrating the bug)
2. JSON serialization validation with complex data types
3. Smart result wrapping for functions vs. string code
4. Backward compatibility for existing workflows
5. Platform-specific serialization edge cases
6. Error handling and clear messaging
"""

import json
import sys
from typing import Any, Dict, List
from unittest.mock import Mock, patch

import pytest

from kailash.nodes.code.python import ClassWrapper, FunctionWrapper, PythonCodeNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class TestCurrentDobleWrappingBehavior:
    """Test current double-wrapping behavior to demonstrate the bug.

    These tests should FAIL initially, demonstrating the serialization issue.
    After implementing the fix, they should pass.
    """

    def test_function_return_dict_double_wrapping(self):
        """Test that function returning dict gets double-wrapped (BUG).

        Current behavior: {"result": {"result": actual_data}}
        Expected behavior: {"result": actual_data}
        """

        def test_func(value: int) -> Dict[str, Any]:
            return {"processed_value": value * 2, "status": "success"}

        node = PythonCodeNode.from_function(test_func, name="test_node")
        result = node.run(value=5)

        # Current buggy behavior - this test will FAIL initially
        # demonstrating the double-wrapping issue
        expected = {"processed_value": 10, "status": "success"}

        # This assertion should pass after the fix
        assert result == {"result": expected}

        # Verify JSON serialization works
        json_str = json.dumps(result)
        assert json_str is not None

        # Verify deserialization works
        restored = json.loads(json_str)
        assert restored == result

    def test_function_return_simple_value_wrapping(self):
        """Test that function returning simple value gets properly wrapped."""

        def test_func(value: int) -> int:
            return value * 2

        node = PythonCodeNode.from_function(test_func, name="test_node")
        result = node.run(value=5)

        # Simple values should be wrapped in result
        assert result == {"result": 10}

        # Verify JSON serialization
        json_str = json.dumps(result)
        restored = json.loads(json_str)
        assert restored == result

    def test_string_code_result_assignment(self):
        """Test that string code with result assignment works correctly."""
        code = """
result = {"processed": value * 2, "metadata": {"timestamp": "2024-01-01"}}
"""
        node = PythonCodeNode(name="test_node", code=code)
        result = node.run(value=5)

        expected = {"processed": 10, "metadata": {"timestamp": "2024-01-01"}}
        assert result == {"result": expected}

        # Verify JSON serialization
        json_str = json.dumps(result)
        restored = json.loads(json_str)
        assert restored == result

    def test_class_method_return_wrapping(self):
        """Test that class method returns get wrapped correctly."""

        class TestProcessor:
            def process(self, value: int) -> Dict[str, Any]:
                return {"transformed": value * 3, "method": "class_processing"}

        node = PythonCodeNode.from_class(TestProcessor, name="test_node")
        result = node.run(value=5)

        expected = {"transformed": 15, "method": "class_processing"}
        assert result == {"result": expected}

        # Verify JSON serialization
        json_str = json.dumps(result)
        restored = json.loads(json_str)
        assert restored == result


class TestJsonSerializationValidation:
    """Test JSON serialization with various data types."""

    def test_complex_nested_structures(self):
        """Test serialization of complex nested data structures."""

        def create_complex_data(depth: int) -> Dict[str, Any]:
            return {
                "nested_dict": {
                    "level_1": {
                        "level_2": {
                            "data": [1, 2, 3, 4, 5],
                            "metadata": {"depth": depth, "type": "nested"},
                        }
                    }
                },
                "arrays": [[1, 2], [3, 4], [5, 6]],
                "mixed_types": [1, "string", 3.14, True, None],
                "unicode_data": "测试数据 🚀 émoji",
                "large_number": 9223372036854775807,  # Max int64
                "small_number": -9223372036854775808,  # Min int64
            }

        node = PythonCodeNode.from_function(create_complex_data, name="complex_test")
        result = node.run(depth=3)

        # Verify structure
        assert "result" in result
        complex_data = result["result"]
        assert (
            complex_data["nested_dict"]["level_1"]["level_2"]["metadata"]["depth"] == 3
        )

        # Verify JSON serialization handles complex structures
        json_str = json.dumps(result)
        restored = json.loads(json_str)
        assert restored == result

    def test_special_float_values(self):
        """Test handling of special float values that can break JSON."""

        def create_special_floats() -> Dict[str, Any]:
            return {
                "normal_float": 3.14159,
                "zero": 0.0,
                "negative_zero": -0.0,
                "very_small": 1e-10,
                "very_large": 1e10,
                # Note: NaN and infinity are not JSON serializable
                # These should be handled by sanitization
            }

        node = PythonCodeNode.from_function(create_special_floats, name="float_test")
        result = node.run()

        # Verify JSON serialization works
        json_str = json.dumps(result)
        restored = json.loads(json_str)
        assert restored == result

    def test_empty_and_null_values(self):
        """Test handling of empty and null values."""

        def create_empty_data() -> Dict[str, Any]:
            return {
                "empty_string": "",
                "empty_list": [],
                "empty_dict": {},
                "null_value": None,
                "zero": 0,
                "false_value": False,
            }

        node = PythonCodeNode.from_function(create_empty_data, name="empty_test")
        result = node.run()

        # Verify all empty/null values are preserved
        data = result["result"]
        assert data["empty_string"] == ""
        assert data["empty_list"] == []
        assert data["empty_dict"] == {}
        assert data["null_value"] is None
        assert data["zero"] == 0
        assert data["false_value"] is False

        # Verify JSON serialization
        json_str = json.dumps(result)
        restored = json.loads(json_str)
        assert restored == result

    def test_unicode_and_special_characters(self):
        """Test handling of unicode and special characters."""

        def create_unicode_data() -> Dict[str, Any]:
            return {
                "emoji": "🚀🌟💡",
                "chinese": "你好世界",
                "japanese": "こんにちは",
                "arabic": "مرحبا",
                "russian": "Привет",
                "special_chars": "\"'\\/@#$%^&*()[]{}|`~",
                "control_chars": "\n\t\r",
                "unicode_escape": "\u0041\u0042\u0043",  # ABC in unicode
            }

        node = PythonCodeNode.from_function(create_unicode_data, name="unicode_test")
        result = node.run()

        # Verify JSON serialization handles unicode
        json_str = json.dumps(result, ensure_ascii=False)
        restored = json.loads(json_str)
        assert restored == result

        # Test with ASCII encoding too
        json_str_ascii = json.dumps(result, ensure_ascii=True)
        restored_ascii = json.loads(json_str_ascii)
        assert restored_ascii == result


class TestSmartResultWrapping:
    """Test smart result wrapping logic for different execution modes."""

    def test_function_dict_return_no_double_wrap(self):
        """Test that function dict returns don't get double-wrapped."""

        def return_dict() -> Dict[str, Any]:
            return {"key1": "value1", "key2": 42}

        wrapper = FunctionWrapper(return_dict)
        result = wrapper.execute({})

        # Should wrap the entire dict in "result" key, not double-wrap
        expected = {"result": {"key1": "value1", "key2": 42}}
        assert result == expected

    def test_function_simple_return_wrapped(self):
        """Test that function simple returns get wrapped in result."""

        def return_simple() -> str:
            return "simple_value"

        wrapper = FunctionWrapper(return_simple)
        result = wrapper.execute({})

        # Simple values should be wrapped
        expected = {"result": "simple_value"}
        assert result == expected

    def test_class_method_wrapping_consistency(self):
        """Test that class methods wrap consistently with functions."""

        class TestClass:
            def process_dict(self) -> Dict[str, Any]:
                return {"processed": True, "method_type": "class"}

            def process_simple(self) -> int:
                return 42

        dict_wrapper = ClassWrapper(TestClass, "process_dict")
        simple_wrapper = ClassWrapper(TestClass, "process_simple")

        dict_result = dict_wrapper.execute({})
        simple_result = simple_wrapper.execute({})

        # Both should be wrapped consistently
        assert dict_result == {"result": {"processed": True, "method_type": "class"}}
        assert simple_result == {"result": 42}

    def test_string_code_variable_detection(self):
        """Test that string code properly detects result variable."""
        from kailash.nodes.code.python import CodeExecutor

        executor = CodeExecutor()

        # Code that sets result variable
        code_with_result = """
result = {"computed": input_value * 2}
other_var = "ignored"
"""

        outputs = executor.execute_code(code_with_result, {"input_value": 5})

        # Should contain result and other variables
        assert "result" in outputs
        assert outputs["result"] == {"computed": 10}
        assert "other_var" in outputs

    @pytest.mark.parametrize(
        "return_type,expected_wrapping",
        [
            ({"key": "value"}, {"result": {"key": "value"}}),
            ([1, 2, 3], {"result": [1, 2, 3]}),
            ("string", {"result": "string"}),
            (42, {"result": 42}),
            (True, {"result": True}),
            (None, {"result": None}),
        ],
    )
    def test_wrapping_consistency_across_types(self, return_type, expected_wrapping):
        """Test that wrapping is consistent across different return types."""

        def test_func():
            return return_type

        wrapper = FunctionWrapper(test_func)
        result = wrapper.execute({})

        assert result == expected_wrapping


class TestBackwardCompatibility:
    """Test backward compatibility with existing workflows."""

    def test_existing_string_code_patterns(self):
        """Test that existing string code patterns continue to work."""
        # Common pattern: direct result assignment
        code1 = "result = input_data * 2"
        node1 = PythonCodeNode(name="test1", code=code1)
        result1 = node1.run(input_data=5)
        assert result1 == {"result": 10}

        # Common pattern: dictionary building
        code2 = """
output = {}
output['processed'] = input_data * 2
output['status'] = 'completed'
result = output
"""
        node2 = PythonCodeNode(name="test2", code=code2)
        result2 = node2.run(input_data=5)
        assert result2 == {"result": {"processed": 10, "status": "completed"}}

    def test_existing_function_patterns(self):
        """Test that existing function patterns continue to work."""

        # Pattern 1: Return dict
        def process_data(data: List[int]) -> Dict[str, Any]:
            return {
                "sum": sum(data),
                "count": len(data),
                "average": sum(data) / len(data) if data else 0,
            }

        node = PythonCodeNode.from_function(process_data, name="test_func")
        result = node.run(data=[1, 2, 3, 4, 5])

        expected = {"result": {"sum": 15, "count": 5, "average": 3.0}}
        assert result == expected

    def test_mixed_execution_modes_compatibility(self):
        """Test that different execution modes can be used together."""
        # String code node
        string_node = PythonCodeNode(
            name="string_processor",
            code="result = {'source': 'string_code', 'value': input_val}",
        )

        # Function node
        def func_processor(input_val: int) -> Dict[str, Any]:
            return {"source": "function", "value": input_val}

        func_node = PythonCodeNode.from_function(func_processor, name="func_processor")

        # Both should produce compatible output formats
        string_result = string_node.run(input_val=10)
        func_result = func_node.run(input_val=10)

        # Both should have the same structure
        assert "result" in string_result
        assert "result" in func_result
        assert string_result["result"]["value"] == 10
        assert func_result["result"]["value"] == 10


class TestPlatformSpecificScenarios:
    """Test scenarios that might behave differently across platforms.

    These are still unit tests but they test platform-specific edge cases.
    """

    def test_path_separator_handling(self):
        """Test that path separators are handled correctly across platforms."""

        def create_path_data() -> Dict[str, Any]:
            import os

            return {
                "sep": os.sep,
                "pathsep": os.pathsep,
                "current_platform": sys.platform,
            }

        node = PythonCodeNode.from_function(create_path_data, name="path_test")
        result = node.run()

        # Should serialize regardless of platform
        json_str = json.dumps(result)
        restored = json.loads(json_str)
        assert restored == result

    def test_line_ending_handling(self):
        """Test that different line endings are handled in string serialization."""

        def create_text_data() -> Dict[str, Any]:
            return {
                "unix_line": "line1\nline2",
                "windows_line": "line1\r\nline2",
                "mac_line": "line1\rline2",
                "mixed": "line1\nline2\r\nline3\rline4",
            }

        node = PythonCodeNode.from_function(create_text_data, name="line_test")
        result = node.run()

        # Should serialize correctly
        json_str = json.dumps(result)
        restored = json.loads(json_str)
        assert restored == result

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific test")
    def test_unix_specific_serialization(self):
        """Test Unix-specific data serialization."""

        def create_unix_data() -> Dict[str, Any]:
            return {
                "platform": "unix",
                "path_example": "/home/user/data.txt",
                "permissions": "755",
            }

        node = PythonCodeNode.from_function(create_unix_data, name="unix_test")
        result = node.run()

        json_str = json.dumps(result)
        restored = json.loads(json_str)
        assert restored == result

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
    def test_windows_specific_serialization(self):
        """Test Windows-specific data serialization."""

        def create_windows_data() -> Dict[str, Any]:
            return {
                "platform": "windows",
                "path_example": "C:\\Users\\user\\data.txt",
                "drive": "C:",
            }

        node = PythonCodeNode.from_function(create_windows_data, name="windows_test")
        result = node.run()

        json_str = json.dumps(result)
        restored = json.loads(json_str)
        assert restored == result


class TestErrorHandlingAndMessaging:
    """Test error handling and clear messaging for serialization issues."""

    def test_non_serializable_object_error(self):
        """Test clear error messages for non-serializable objects."""

        def create_non_serializable() -> Any:
            # Functions are not JSON serializable
            return lambda x: x

        node = PythonCodeNode.from_function(create_non_serializable, name="error_test")
        result = node.run()

        # The result should contain the non-serializable object
        # Testing JSON serialization should fail with clear error
        with pytest.raises((TypeError, ValueError)) as exc_info:
            json.dumps(result)

        # Error message should be informative
        error_msg = str(exc_info.value)
        assert "not JSON serializable" in error_msg or "Object of type" in error_msg

    def test_circular_reference_handling(self):
        """Test handling of circular references in data."""

        def create_circular_ref() -> Dict[str, Any]:
            data = {"name": "root"}
            data["self_ref"] = data  # Circular reference
            return data

        node = PythonCodeNode.from_function(create_circular_ref, name="circular_test")

        # This should execute but create circular reference
        result = node.run()

        # JSON serialization should fail with clear error
        with pytest.raises(ValueError) as exc_info:
            json.dumps(result)

        error_msg = str(exc_info.value)
        assert "circular reference" in error_msg.lower()

    def test_execution_error_propagation(self):
        """Test that execution errors are properly propagated."""

        def failing_function() -> Dict[str, Any]:
            raise ValueError("Intentional test error")

        node = PythonCodeNode.from_function(failing_function, name="failing_test")

        with pytest.raises(NodeExecutionError) as exc_info:
            node.run()

        # Error should contain the original exception info
        error_msg = str(exc_info.value)
        assert "Intentional test error" in error_msg

    def test_malformed_result_detection(self):
        """Test detection of malformed result structures."""
        # String code that produces invalid result structure
        code = """
# This creates an invalid result structure that might break serialization
# Using dict instead of class to avoid __build_class__ issues in restricted namespace
circular_dict = {}
circular_dict['self_ref'] = circular_dict  # Circular reference

result = circular_dict
"""

        node = PythonCodeNode(name="malformed_test", code=code)
        result = node.run()

        # Should execute but result contains circular reference
        with pytest.raises(ValueError):
            json.dumps(result)


@pytest.mark.unit
class TestSerializationBugDemonstration:
    """Specific tests that demonstrate the current serialization bug.

    These tests are designed to FAIL with the current implementation,
    clearly showing the double-wrapping issue in different scenarios.
    """

    def test_function_wrapper_double_wrapping_bug(self):
        """Demonstrate the double-wrapping bug in FunctionWrapper.execute()."""

        def sample_function(value: int) -> Dict[str, Any]:
            return {"processed": value * 2}

        wrapper = FunctionWrapper(sample_function)
        result = wrapper.execute({"value": 5})

        # CURRENT BUGGY BEHAVIOR: {"result": {"result": {"processed": 10}}}
        # EXPECTED BEHAVIOR: {"result": {"processed": 10}}

        # This test should FAIL initially, demonstrating the bug
        expected = {"result": {"processed": 10}}

        # TODO: This assertion will fail with current implementation
        # showing the double-wrapping bug
        assert result == expected, f"Double-wrapping bug detected: {result}"

    def test_class_wrapper_double_wrapping_bug(self):
        """Demonstrate the double-wrapping bug in ClassWrapper.execute()."""

        class SampleClass:
            def process(self, value: int) -> Dict[str, Any]:
                return {"transformed": value * 3}

        wrapper = ClassWrapper(SampleClass, "process")
        result = wrapper.execute({"value": 5})

        # CURRENT BUGGY BEHAVIOR: {"result": {"result": {"transformed": 15}}}
        # EXPECTED BEHAVIOR: {"result": {"transformed": 15}}

        expected = {"result": {"transformed": 15}}

        # TODO: This assertion will fail with current implementation
        assert result == expected, f"Double-wrapping bug detected: {result}"

    def test_node_run_vs_execute_consistency(self):
        """Test that run() and execute() methods return consistent formats."""

        def test_func(x: int) -> Dict[str, Any]:
            return {"value": x}

        node = PythonCodeNode.from_function(test_func, name="consistency_test")

        # Both methods should return the same format
        run_result = node.run(x=10)
        execute_result = node.execute(x=10)

        # These should be the same (no double-wrapping in either)
        assert run_result == execute_result

        # Both should be JSON serializable
        json.dumps(run_result)
        json.dumps(execute_result)

    def test_platform_context_vs_standalone_behavior(self):
        """Test behavior difference between platform context and standalone execution.

        This test simulates the reported issue where serialization fails in
        platform context but works in standalone tests.
        """

        def create_complex_result() -> Dict[str, Any]:
            return {
                "data": [1, 2, 3],
                "metadata": {"created": "2024-01-01", "version": 1},
                "nested": {"level1": {"level2": "deep_value"}},
            }

        node = PythonCodeNode.from_function(create_complex_result, name="platform_test")

        # Simulate standalone execution
        standalone_result = node.run()

        # Simulate platform context (through different execution path)
        platform_result = node.execute()

        # Both should be identical and JSON serializable
        assert standalone_result == platform_result

        # Both should serialize without issues
        standalone_json = json.dumps(standalone_result)
        platform_json = json.dumps(platform_result)

        # Deserialized results should be identical
        assert json.loads(standalone_json) == json.loads(platform_json)
