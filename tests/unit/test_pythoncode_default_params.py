"""Test PythonCodeNode default parameter handling fix."""

from typing import Any, Dict, List

import pytest

from kailash.nodes.code import PythonCodeNode


def test_function_with_default_parameters():
    """Test that functions with default parameters work correctly."""

    def process_data(data: List[float], threshold: float = 0.5) -> Dict[str, Any]:
        """Filter data based on threshold."""
        return {"result": [x for x in data if x > threshold]}

    # Create node from function
    node = PythonCodeNode.from_function(process_data)

    # Verify parameter detection
    params = node.get_parameters()
    assert "data" in params
    assert "threshold" in params

    # Check required flags
    assert params["data"].required is True  # No default
    assert params["threshold"].required is False  # Has default
    assert params["threshold"].default == 0.5

    # Test execution with default parameter
    result = node.execute(data=[0.1, 0.6, 0.3, 0.8])
    assert result["result"]["result"] == [0.6, 0.8]

    # Test execution with custom parameter
    result = node.execute(data=[0.1, 0.6, 0.3, 0.8], threshold=0.7)
    assert result["result"]["result"] == [0.8]


def test_function_with_multiple_defaults():
    """Test function with multiple default parameters."""

    def analyze_data(
        data: List[float],
        min_val: float = 0.0,
        max_val: float = 1.0,
        normalize: bool = True,
    ) -> Dict[str, Any]:
        """Analyze data with configurable bounds."""
        filtered = [x for x in data if min_val <= x <= max_val]
        if normalize and filtered:
            max_filtered = max(filtered)
            min_filtered = min(filtered)
            range_val = max_filtered - min_filtered
            if range_val > 0:
                filtered = [(x - min_filtered) / range_val for x in filtered]
        return {"result": filtered}

    node = PythonCodeNode.from_function(analyze_data)
    params = node.get_parameters()

    # Check all parameters
    assert params["data"].required is True
    assert params["min_val"].required is False
    assert params["max_val"].required is False
    assert params["normalize"].required is False

    # Check defaults
    assert params["min_val"].default == 0.0
    assert params["max_val"].default == 1.0
    assert params["normalize"].default is True

    # Test with only required parameter
    result = node.execute(data=[0.5, 1.5, -0.5, 0.75])
    assert result["result"]["result"] == [
        0.0,
        1.0,
    ]  # normalized [0.5, 0.75] -> [0.0, 1.0]

    # Test with some optional parameters
    result = node.execute(data=[0.5, 1.5, -0.5, 0.75], normalize=False)
    assert result["result"]["result"] == [0.5, 0.75]


def test_class_method_with_defaults():
    """Test class methods with default parameters."""

    class DataProcessor:
        def __init__(self):
            self.processed_count = 0

        def process(self, data: List[float], multiplier: float = 2.0) -> Dict[str, Any]:
            """Process data with optional multiplier."""
            self.processed_count += 1
            return {
                "result": [x * multiplier for x in data],
                "count": self.processed_count,
            }

    node = PythonCodeNode.from_class(DataProcessor)
    params = node.get_parameters()

    # Check parameters
    assert params["data"].required is True
    assert params["multiplier"].required is False
    assert params["multiplier"].default == 2.0

    # Test execution
    result = node.execute(data=[1, 2, 3])
    assert result["result"]["result"] == [2, 4, 6]
    assert result["result"]["count"] == 1


def test_no_defaults_still_required():
    """Test that functions without defaults still have required parameters."""

    def simple_add(x: float, y: float) -> Dict[str, float]:
        return {"result": x + y}

    node = PythonCodeNode.from_function(simple_add)
    params = node.get_parameters()

    assert params["x"].required is True
    assert params["y"].required is True
    assert params["x"].default is None
    assert params["y"].default is None

    # Should fail without required parameters
    with pytest.raises(Exception):  # Will raise validation error
        node.execute(x=5)  # Missing y parameter


def test_complex_type_with_default():
    """Test handling of complex types with defaults."""

    def process_dict(
        data: Dict[str, Any], prefix: str = "processed_"
    ) -> Dict[str, Any]:
        """Process dictionary with optional prefix."""
        return {"result": {f"{prefix}{k}": v for k, v in data.items()}}

    node = PythonCodeNode.from_function(process_dict)
    params = node.get_parameters()

    assert params["data"].required is True
    assert params["prefix"].required is False
    assert params["prefix"].default == "processed_"

    # Test with default
    result = node.execute(data={"a": 1, "b": 2})
    assert result["result"]["result"] == {"processed_a": 1, "processed_b": 2}

    # Test with custom prefix
    result = node.execute(data={"a": 1, "b": 2}, prefix="custom_")
    assert result["result"]["result"] == {"custom_a": 1, "custom_b": 2}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
