"""Unit tests for code execution nodes."""

import pandas as pd
import pytest

from kailash.nodes.code import (
    ClassWrapper,
    CodeExecutor,
    FunctionWrapper,
    PythonCodeNode,
)
from kailash.sdk_exceptions import (
    NodeConfigurationError,
    NodeExecutionError,
    NodeValidationError,
)


class TestCodeExecutor:
    """Test the CodeExecutor class."""

    def test_execute_simple_code(self):
        """Test executing simple Python code."""
        executor = CodeExecutor()
        code = """
result = x + y
"""
        inputs = {"x": 5, "y": 3}
        outputs = executor.execute_code(code, inputs)

        assert outputs["result"] == 8

    def test_execute_with_imports(self):
        """Test code execution with pre-imported modules."""
        executor = CodeExecutor(allowed_modules=["math"])
        # Modules are pre-imported into the namespace, not imported in the code
        code = """
result = math.sqrt(x)
"""
        inputs = {"x": 16}
        outputs = executor.execute_code(code, inputs)

        assert outputs["result"] == 4.0

    def test_execute_function(self):
        """Test executing a function directly."""
        executor = CodeExecutor()

        def add(x, y):
            return x + y

        result = executor.execute_function(add, {"x": 10, "y": 20})
        assert result == 30

    def test_execute_with_error(self):
        """Test error handling in code execution."""
        executor = CodeExecutor()
        code = """
result = 1 / 0  # Division by zero
"""
        with pytest.raises(NodeExecutionError, match="Code execution failed"):
            executor.execute_code(code, {})

    def test_disallowed_module(self):
        """Test that disallowed modules are not available."""
        executor = CodeExecutor(allowed_modules=["math"])  # os not allowed
        code = """
# os module is not available in the namespace
result = os.path.exists('.')  # This will fail with NameError
"""
        # Should raise error because os is not in namespace
        with pytest.raises(NodeExecutionError, match="name 'os' is not defined"):
            executor.execute_code(code, {})


class TestFunctionWrapper:
    """Test the FunctionWrapper class."""

    def test_wrap_simple_function(self):
        """Test wrapping a simple function."""

        def multiply(x: int, y: int) -> int:
            """Multiply two numbers."""
            return x * y

        wrapper = FunctionWrapper(multiply)

        assert wrapper.name == "multiply"
        assert wrapper.doc == "Multiply two numbers."
        assert wrapper.get_input_types() == {"x": int, "y": int}
        assert wrapper.get_output_type() == int  # noqa: E721

    def test_wrap_function_without_annotations(self):
        """Test wrapping a function without type annotations."""

        def process(data):
            return data * 2

        wrapper = FunctionWrapper(process)

        # For functions without annotations, the wrapper should return Any type
        from typing import Any

        assert wrapper.get_input_types() == {"data": Any}
        assert wrapper.get_output_type() == Any

    def test_to_node(self):
        """Test converting wrapper to node."""

        def transform(data: pd.DataFrame) -> pd.DataFrame:
            return data.copy()

        wrapper = FunctionWrapper(transform)
        node = wrapper.to_node(name="data_transformer")

        assert isinstance(node, PythonCodeNode)
        assert node.metadata.name == "data_transformer"


class TestClassWrapper:
    """Test the ClassWrapper class."""

    def test_wrap_class_with_process(self):
        """Test wrapping a class with process method."""

        class Processor:
            def process(self, data):
                return data * 2

        wrapper = ClassWrapper(Processor)

        assert wrapper.name == "Processor"
        assert wrapper.process_method == "process"

    def test_wrap_class_with_execute(self):
        """Test wrapping a class with execute method."""

        class Executor:
            def execute(self, value):
                return value + 1

        wrapper = ClassWrapper(Executor)
        assert wrapper.process_method == "execute"

    def test_wrap_class_without_process_method(self):
        """Test error when class has no process method."""

        class BadClass:
            def do_something(self):
                pass

        with pytest.raises(NodeConfigurationError, match="must have a process method"):
            ClassWrapper(BadClass)

    def test_to_node(self):
        """Test converting class wrapper to node."""

        class Counter:
            def __init__(self):
                self.count = 0

            def process(self, increment: int = 1) -> int:
                self.count += increment
                return self.count

        wrapper = ClassWrapper(Counter)
        node = wrapper.to_node(name="counter_node")

        assert isinstance(node, PythonCodeNode)
        assert node.metadata.name == "counter_node"


class TestPythonCodeNode:
    """Test the PythonCodeNode class."""

    def test_create_from_code_string(self):
        """Test creating node from code string."""
        code = """
result = data * factor
"""
        node = PythonCodeNode(
            name="multiplier",
            code=code,
            input_types={"data": int, "factor": int},
            output_type=int,
        )

        result = node.execute_code({"data": 5, "factor": 3})
        assert result == 15

    def test_create_from_function(self):
        """Test creating node from function."""

        def process_data(values: list, threshold: float = 0.5) -> list:
            return [v for v in values if v > threshold]

        node = PythonCodeNode.from_function(func=process_data, name="filter_node")

        result = node.execute_code({"values": [0.1, 0.6, 0.3, 0.8], "threshold": 0.5})
        assert result == [0.6, 0.8]

    def test_create_from_class(self):
        """Test creating node from class."""

        class Accumulator:
            def __init__(self):
                self.total = 0

            def process(self, value: float) -> float:
                self.total += value
                return self.total

        node = PythonCodeNode.from_class(class_type=Accumulator, name="accumulator")

        # Test stateful behavior
        assert node.execute_code({"value": 5.0}) == 5.0
        assert node.execute_code({"value": 3.0}) == 8.0
        assert node.execute_code({"value": -2.0}) == 6.0

    def test_create_from_file(self, tmp_path):
        """Test creating node from Python file."""
        # Create a temporary Python file
        code_file = tmp_path / "custom_code.py"
        code_file.write_text(
            """
def double(x: int) -> int:
    return x * 2

class Tripler:
    def process(self, x: int) -> int:
        return x * 3
"""
        )

        # Create node from function in file
        func_node = PythonCodeNode.from_file(
            file_path=code_file, function_name="double", name="doubler"
        )

        assert func_node.execute_code({"x": 4}) == 8

        # Create node from class in file
        class_node = PythonCodeNode.from_file(
            file_path=code_file, class_name="Tripler", name="tripler"
        )

        assert class_node.execute_code({"x": 4}) == 12

    def test_input_validation(self):
        """Test input validation."""
        node = PythonCodeNode(
            name="validator",
            code="result = x + y",
            input_types={"x": int, "y": int},
            output_type=int,
        )

        # Test validation through execute() method (which uses base class validation)
        with pytest.raises(
            NodeValidationError, match="Required input 'y' not provided"
        ):
            node.execute(x=5)

        # Wrong type - base class will attempt conversion
        result = node.execute(x=5, y="10")  # Should convert string to int
        assert result == {"result": 15}

        # Test direct execute_code() method bypasses validation
        result = node.execute_code({"x": 5, "y": 10})
        assert result == 15

    def test_configuration_errors(self):
        """Test configuration error handling."""
        # No execution method provided
        with pytest.raises(NodeConfigurationError, match="Must provide either"):
            PythonCodeNode(name="bad_node")

        # Multiple execution methods
        with pytest.raises(NodeConfigurationError, match="Can only provide one"):
            PythonCodeNode(name="bad_node", code="result = 1", function=lambda x: x)

    def test_pandas_integration(self):
        """Test integration with pandas DataFrames."""

        def process_df(df: pd.DataFrame, column: str) -> pd.DataFrame:
            result = df.copy()
            result[f"{column}_squared"] = result[column] ** 2
            return result

        node = PythonCodeNode.from_function(func=process_df, name="df_processor")

        # Create test data
        df = pd.DataFrame({"value": [1, 2, 3], "name": ["a", "b", "c"]})

        result = node.execute_code({"df": df, "column": "value"})

        assert isinstance(result, pd.DataFrame)
        assert "value_squared" in result.columns
        assert list(result["value_squared"]) == [1, 4, 9]

    def test_complex_code_execution(self):
        """Test executing complex code with multiple operations."""
        # Note: numpy must be pre-imported, not imported in the code
        code = """
# Process data
data_array = numpy.array(data)
mean_val = numpy.mean(data_array)
std_val = numpy.std(data_array)

# Normalize
normalized = (data_array - mean_val) / std_val

# Create result dictionary
result = {
    'normalized': normalized.tolist(),
    'mean': mean_val,
    'std': std_val,
    'outliers': [x for x in data if abs(x - mean_val) > 2 * std_val]
}
"""
        node = PythonCodeNode(
            name="analyzer", code=code, input_types={"data": list}, output_type=dict
        )

        test_data = [1, 2, 3, 4, 5, 10, 20]
        result = node.execute_code({"data": test_data})

        assert "normalized" in result
        assert "mean" in result
        assert "std" in result
        assert "outliers" in result
        assert len(result["outliers"]) == 1  # 20 is an outlier

    def test_node_serialization(self):
        """Test node configuration serialization."""
        node = PythonCodeNode(
            name="test_node",
            code="result = x * 2",
            input_types={"x": int},
            output_type=int,
            description="Test node",
        )

        config = node.get_config()

        assert config["name"] == "test_node"
        assert config["code"] == "result = x * 2"
        assert config["input_types"] == {"x": "int"}
        assert config["output_type"] == "int"
        assert config["description"] == "Test node"

    def test_error_propagation(self):
        """Test that errors are properly propagated."""

        def failing_function(x):
            raise ValueError("Intentional error")

        node = PythonCodeNode.from_function(func=failing_function, name="failing_node")

        with pytest.raises(NodeExecutionError, match="Intentional error"):
            node.execute_code({"x": 1})
