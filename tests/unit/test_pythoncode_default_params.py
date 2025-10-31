"""Test default parameters in PythonCodeNode."""

from typing import Any, Dict, List

import pytest
from kailash.nodes.code.python import PythonCodeNode


class TestPythonCodeDefaultParams:
    """Test default parameter handling."""

    def test_function_with_default_parameters(self):
        """Test that functions with default parameters work correctly."""

        def process_data(data: List[float], threshold: float = 0.5) -> Dict[str, Any]:
            """Filter data based on threshold."""
            return {"result": [x for x in data if x > threshold]}

        # Create node from function
        node = PythonCodeNode.from_function(process_data)

        # Test with default threshold
        result = node.execute(data=[0.1, 0.6, 0.3, 0.8])
        assert result["result"] == [0.6, 0.8]

        # Test with custom threshold
        result = node.execute(data=[0.1, 0.6, 0.3, 0.8], threshold=0.7)
        assert result["result"] == [0.8]
