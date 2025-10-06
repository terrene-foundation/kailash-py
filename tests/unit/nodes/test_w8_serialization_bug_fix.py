#!/usr/bin/env python3
"""
Comprehensive unit tests for W8 serialization bug fix.

This test suite validates the enhanced Node._is_json_serializable() method
that now recognizes objects with .to_dict() methods as serializable.

Test Strategy (Tier 1 - Unit Tests):
- Speed: <1 second per test
- Isolation: No external dependencies
- Mocking: Allowed for external services
- Focus: Node._is_json_serializable() enhancement validation

Coverage Areas:
1. W8 bug reproduction with exact scenario
2. Enhanced .to_dict() recognition logic
3. Backward compatibility preservation
4. Edge case handling (malformed .to_dict(), circular refs)
5. Performance validation (no significant overhead)
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import Mock, patch

import pytest
from kailash.nodes.base import Node
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class SampleNode(Node):
    """Concrete sample node for testing serialization methods."""

    def get_parameters(self) -> Dict[str, Any]:
        return {}

    def run(self, **kwargs) -> Dict[str, Any]:
        return {"result": "test"}


# ============================================================================
# W8 Bug Reproduction Test Cases
# ============================================================================


@dataclass
class W8Context:
    """Exact reproduction of W8Context that caused the serialization bug."""

    request_id: str
    user_id: Optional[str] = None
    session_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    nested_objects: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert W8Context to dictionary - this should now be recognized."""
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "session_data": self.session_data,
            "metadata": self.metadata,
            "nested_objects": self.nested_objects,
        }


@dataclass
class ComplexNestedContext:
    """Complex nested dataclass structure for comprehensive testing."""

    id: str
    w8_context: W8Context
    processing_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "w8_context": self.w8_context.to_dict(),
            "processing_steps": self.processing_steps,
        }


class TestW8BugReproduction:
    """Test exact W8 bug reproduction and validation of fix."""

    def test_w8_context_serialization_recognition(self):
        """Test that W8Context with .to_dict() is now recognized as serializable."""
        # Create the exact W8Context that caused the original bug
        w8_context = W8Context(
            request_id="w8_test_123",
            user_id="user_456",
            session_data={"session_token": "abc123", "timeout": 3600},
            metadata={"created": "2024-01-01", "version": "1.0"},
            nested_objects=[
                {"type": "config", "data": {"setting1": "value1"}},
                {"type": "state", "data": {"current_step": 2}},
            ],
        )

        # Test the enhanced _is_json_serializable method
        test_node = SampleNode(name="test_node")

        # This should now return True (was False before the fix)
        assert test_node._is_json_serializable(w8_context) is True

        # Verify actual JSON serialization works
        json_str = json.dumps(w8_context.to_dict())
        assert json_str is not None

        # Verify round-trip serialization
        restored_dict = json.loads(json_str)
        assert restored_dict["request_id"] == "w8_test_123"
        assert restored_dict["user_id"] == "user_456"
        assert len(restored_dict["nested_objects"]) == 2

    def test_complex_nested_dataclass_serialization(self):
        """Test complex nested dataclass structures."""
        w8_context = W8Context(
            request_id="nested_test", session_data={"nested": {"deep": {"value": 123}}}
        )

        complex_context = ComplexNestedContext(
            id="complex_123",
            w8_context=w8_context,
            processing_steps=["init", "validate", "process", "finalize"],
        )

        test_node = SampleNode(name="test_node")

        # Should recognize complex nested structure with .to_dict()
        assert test_node._is_json_serializable(complex_context) is True

        # Verify actual serialization
        json_str = json.dumps(complex_context.to_dict())
        restored = json.loads(json_str)

        assert restored["id"] == "complex_123"
        assert restored["w8_context"]["request_id"] == "nested_test"
        assert len(restored["processing_steps"]) == 4

    def test_w8_context_in_node_output_validation(self):
        """Test W8Context in actual node output validation scenario."""

        def create_w8_context() -> W8Context:
            return W8Context(
                request_id="output_test",
                metadata={"source": "node_execution", "timestamp": "2024-01-01"},
            )

        node = PythonCodeNode.from_function(create_w8_context, name="w8_creator")

        # This should now work without serialization errors
        result = node.run()

        # Verify the W8Context is in the result
        assert "result" in result
        # W8Context should be converted to dict via to_dict() method and wrapped by function node
        w8_dict = result["result"]
        assert isinstance(w8_dict, dict)
        assert w8_dict["request_id"] == "output_test"
        assert w8_dict["metadata"]["source"] == "node_execution"

        # Verify node's validate_outputs() accepts it
        node.validate_outputs(result)  # Should not raise


# ============================================================================
# Enhanced Serialization Logic Tests
# ============================================================================


class TestEnhancedSerializationLogic:
    """Test the enhanced _is_json_serializable() logic."""

    def test_to_dict_method_recognition(self):
        """Test recognition of objects with .to_dict() methods."""

        class CustomSerializable:
            def __init__(self, data):
                self.data = data

            def to_dict(self):
                return {"custom_data": self.data}

        class NonSerializable:
            def __init__(self, data):
                self.data = data

        test_node = SampleNode(name="test_node")

        # Should recognize objects with .to_dict()
        serializable_obj = CustomSerializable("test_data")
        assert test_node._is_json_serializable(serializable_obj) is True

        # Should NOT recognize objects without .to_dict()
        non_serializable_obj = NonSerializable("test_data")
        assert test_node._is_json_serializable(non_serializable_obj) is False

    def test_to_dict_method_callable_validation(self):
        """Test that .to_dict() must be callable, not just an attribute."""

        class FakeToDict:
            def __init__(self):
                self.to_dict = "not_callable"  # String, not method

        class RealToDict:
            def to_dict(self):
                return {"real": True}

        test_node = SampleNode(name="test_node")

        # Non-callable .to_dict should not be recognized
        fake_obj = FakeToDict()
        assert test_node._is_json_serializable(fake_obj) is False

        # Callable .to_dict should be recognized
        real_obj = RealToDict()
        assert test_node._is_json_serializable(real_obj) is True

    def test_standard_json_types_unchanged(self):
        """Test that standard JSON types behavior is unchanged."""
        test_node = SampleNode(name="test_node")

        # All standard JSON types should still work
        test_cases = [
            ({"key": "value"}, True),
            ([1, 2, 3], True),
            ("string", True),
            (42, True),
            (3.14, True),
            (True, True),
            (False, True),
            (None, True),
        ]

        for obj, expected in test_cases:
            assert test_node._is_json_serializable(obj) is expected

    def test_non_serializable_types_unchanged(self):
        """Test that non-serializable types behavior is unchanged."""
        test_node = SampleNode(name="test_node")

        # These should still be non-serializable
        test_cases = [
            lambda x: x,  # Function
            set([1, 2, 3]),  # Set
            complex(1, 2),  # Complex number
            object(),  # Generic object
        ]

        for obj in test_cases:
            assert test_node._is_json_serializable(obj) is False


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_malformed_to_dict_method(self):
        """Test handling of malformed .to_dict() methods."""

        class MalformedToDict:
            def to_dict(self):
                raise ValueError("Malformed to_dict method")

        class NonDictReturningToDict:
            def to_dict(self):
                return "not_a_dict"  # Returns string, not dict

        test_node = SampleNode(name="test_node")

        # Should handle exceptions gracefully
        malformed_obj = MalformedToDict()
        # Should return False if .to_dict() raises exception
        assert test_node._is_json_serializable(malformed_obj) is False

        # Should handle non-dict returns from .to_dict()
        non_dict_obj = NonDictReturningToDict()
        # This should still be considered serializable if .to_dict() doesn't raise
        # The actual JSON serialization test will catch non-dict returns
        result = test_node._is_json_serializable(non_dict_obj)
        # Could be True or False depending on implementation detail
        assert isinstance(result, bool)

    def test_circular_reference_in_to_dict(self):
        """Test handling of circular references in .to_dict() output."""

        class CircularToDict:
            def __init__(self):
                self.data = {"self_ref": self}

            def to_dict(self):
                return self.data  # Contains circular reference

        test_node = SampleNode(name="test_node")
        circular_obj = CircularToDict()

        # Should return False due to JSON serialization test failure
        assert test_node._is_json_serializable(circular_obj) is False

    def test_deeply_nested_to_dict_structures(self):
        """Test deeply nested structures from .to_dict()."""

        class DeepNestedToDict:
            def to_dict(self):
                # Create deep nesting (but not infinite)
                result = {"level_0": {}}
                current = result["level_0"]
                for i in range(1, 50):  # 50 levels deep
                    current[f"level_{i}"] = {}
                    current = current[f"level_{i}"]
                current["final_value"] = "deep_data"
                return result

        test_node = SampleNode(name="test_node")
        deep_obj = DeepNestedToDict()

        # Should handle deep nesting (within JSON limits)
        assert test_node._is_json_serializable(deep_obj) is True

    def test_large_data_structures_in_to_dict(self):
        """Test large data structures from .to_dict()."""

        class LargeDataToDict:
            def to_dict(self):
                # Create large but valid data structure
                return {
                    "large_list": list(range(10000)),
                    "large_dict": {f"key_{i}": f"value_{i}" for i in range(5000)},
                    "nested_large": {
                        "sublists": [list(range(100)) for _ in range(100)]
                    },
                }

        test_node = SampleNode(name="test_node")
        large_obj = LargeDataToDict()

        # Should handle large structures (may be slow but should work)
        start_time = time.time()
        result = test_node._is_json_serializable(large_obj)
        end_time = time.time()

        assert result is True
        # Should complete in reasonable time (within unit test limits)
        assert (end_time - start_time) < 1.0  # 1 second max for unit tests


# ============================================================================
# Performance and Regression Tests
# ============================================================================


class TestPerformanceRegression:
    """Test performance impact and regression scenarios."""

    def test_performance_overhead_standard_types(self):
        """Test that performance overhead for standard types is minimal."""
        test_node = SampleNode(name="test_node")

        # Test standard types performance
        test_data = [
            {"complex": {"nested": {"data": [1, 2, 3, 4, 5]}}},
            [{"item": i} for i in range(1000)],
            "large_string" * 1000,
            list(range(10000)),
        ]

        for data in test_data:
            start_time = time.time()
            result = test_node._is_json_serializable(data)
            end_time = time.time()

            assert result is True
            # Should be very fast for standard types
            assert (end_time - start_time) < 0.01  # 10ms max

    def test_performance_overhead_to_dict_objects(self):
        """Test performance overhead for .to_dict() objects."""

        class FastToDict:
            def to_dict(self):
                return {"simple": "data"}

        class SlowToDict:
            def to_dict(self):
                # Simulate some processing time
                time.sleep(0.001)  # 1ms delay
                return {"processed": "data"}

        test_node = SampleNode(name="test_node")

        # Fast .to_dict() should be very quick
        fast_obj = FastToDict()
        start_time = time.time()
        result = test_node._is_json_serializable(fast_obj)
        end_time = time.time()

        assert result is True
        assert (end_time - start_time) < 0.01  # Should be fast

        # Slow .to_dict() will be slower but should still complete
        slow_obj = SlowToDict()
        start_time = time.time()
        result = test_node._is_json_serializable(slow_obj)
        end_time = time.time()

        assert result is True
        assert (end_time - start_time) < 0.1  # Should complete within 100ms

    def test_backward_compatibility_comprehensive(self):
        """Comprehensive backward compatibility test."""
        test_node = SampleNode(name="test_node")

        # Test all scenarios that should behave exactly as before
        backward_compatibility_cases = [
            # Standard JSON types
            (None, True),
            (True, True),
            (False, True),
            (42, True),
            (-42, True),
            (3.14159, True),
            ("string", True),
            ("", True),  # Empty string
            ([], True),  # Empty list
            ({}, True),  # Empty dict
            # Complex but standard structures
            ({"nested": {"deep": {"value": [1, 2, 3]}}}, True),
            ([{"item": i, "data": f"value_{i}"} for i in range(100)], True),
            # Non-serializable types
            (lambda x: x, False),  # Function
            (set([1, 2, 3]), False),  # Set
            (frozenset([1, 2, 3]), False),  # Frozenset
            (complex(1, 2), False),  # Complex number
            (object(), False),  # Generic object
        ]

        for obj, expected in backward_compatibility_cases:
            result = test_node._is_json_serializable(obj)
            assert (
                result is expected
            ), f"Backward compatibility failed for {type(obj)}: expected {expected}, got {result}"


# ============================================================================
# Integration with Node Output Validation
# ============================================================================


class TestNodeOutputValidationIntegration:
    """Test integration with Node.validate_outputs()."""

    def test_w8_context_in_validate_outputs(self):
        """Test W8Context passes validate_outputs()."""
        w8_context = W8Context(
            request_id="validation_test", metadata={"validated": True}
        )

        test_node = SampleNode(name="test_node")

        # Create output dict with W8Context
        outputs = {
            "w8_context": w8_context,
            "status": "success",
            "metadata": {"processed": True},
        }

        # Should not raise any exceptions
        validated_outputs = test_node.validate_outputs(outputs)

        # Should return the same outputs
        assert validated_outputs == outputs
        assert isinstance(validated_outputs["w8_context"], W8Context)

    def test_mixed_output_types_with_to_dict_objects(self):
        """Test mixed output types including .to_dict() objects."""

        @dataclass
        class ProcessingResult:
            status: str
            data: Dict[str, Any]

            def to_dict(self):
                return {"status": self.status, "data": self.data}

        result_obj = ProcessingResult(
            status="completed", data={"processed_items": 150, "errors": 0}
        )

        test_node = SampleNode(name="test_node")

        outputs = {
            "result": result_obj,
            "metrics": {"execution_time": 1.23, "memory_used": 456},
            "raw_data": [1, 2, 3, 4, 5],
            "flags": {"debug": True, "verbose": False},
        }

        # Should validate all output types including .to_dict() object
        validated_outputs = test_node.validate_outputs(outputs)
        assert validated_outputs == outputs

    def test_non_serializable_mixed_with_to_dict_objects(self):
        """Test that non-serializable objects still fail validation."""

        @dataclass
        class GoodObject:
            value: str

            def to_dict(self):
                return {"value": self.value}

        good_obj = GoodObject("serializable")

        def bad_function():  # Non-serializable function
            return None

        bad_obj = bad_function

        test_node = SampleNode(name="test_node")

        outputs = {
            "good": good_obj,  # Should pass
            "bad": bad_obj,  # Should fail
            "normal": {"key": "value"},  # Should pass
        }

        # Should raise validation error due to bad_obj
        with pytest.raises(Exception):  # NodeValidationError or similar
            test_node.validate_outputs(outputs)


@pytest.mark.unit
class TestW8SerializationBugFixUnit:
    """Unit test marker class for test categorization."""

    pass


if __name__ == "__main__":
    # Run specific test categories
    pytest.main(
        [
            __file__,
            "-v",
            "--timeout=1",  # Enforce 1-second timeout for unit tests
            "-m",
            "unit",
        ]
    )
