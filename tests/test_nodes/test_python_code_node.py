"""Simple test for PythonCodeNode functionality."""

import pandas as pd
from kailash.nodes.code import PythonCodeNode, CodeExecutor, FunctionWrapper, ClassWrapper


def test_code_executor():
    """Test basic code execution."""
    executor = CodeExecutor()
    code = """
result = x + y
"""
    inputs = {'x': 5, 'y': 3}
    outputs = executor.execute_code(code, inputs)
    print(f"Code execution result: {outputs['result']}")
    assert outputs['result'] == 8


def test_function_wrapper():
    """Test function wrapping."""
    def multiply(x: int, y: int) -> int:
        """Multiply two numbers."""
        return x * y
    
    wrapper = FunctionWrapper(multiply)
    node = wrapper.to_node(name="multiplier")
    
    result = node.execute_code({'x': 5, 'y': 3})
    print(f"Function result: {result}")
    assert result == 15


def test_class_wrapper():
    """Test class wrapping."""
    class Accumulator:
        def __init__(self):
            self.total = 0
        
        def process(self, value: float) -> float:
            self.total += value
            return self.total
    
    wrapper = ClassWrapper(Accumulator)
    node = wrapper.to_node(name="accumulator")
    
    result1 = node.execute_code({'value': 5.0})
    result2 = node.execute_code({'value': 3.0})
    print(f"Class results: {result1}, {result2}")
    assert result1 == 5.0
    assert result2 == 8.0


def test_python_code_node():
    """Test PythonCodeNode directly."""
    # Test with code string
    code_node = PythonCodeNode(
        name="adder",
        code="result = a + b",
        input_types={'a': int, 'b': int},
        output_type=int
    )
    
    result = code_node.execute_code({'a': 10, 'b': 20})
    print(f"Code node result: {result}")
    assert result == 30
    
    # Test with function
    def transform_data(data: pd.DataFrame) -> pd.DataFrame:
        result = data.copy()
        result['doubled'] = data['value'] * 2
        return result
    
    func_node = PythonCodeNode.from_function(
        func=transform_data,
        name="transformer"
    )
    
    df = pd.DataFrame({'value': [1, 2, 3]})
    result_df = func_node.execute_code({'data': df})
    print(f"DataFrame result:\n{result_df}")
    assert 'doubled' in result_df.columns
    assert list(result_df['doubled']) == [2, 4, 6]


if __name__ == "__main__":
    print("Testing CodeExecutor...")
    test_code_executor()
    
    print("\nTesting FunctionWrapper...")
    test_function_wrapper()
    
    print("\nTesting ClassWrapper...")
    test_class_wrapper()
    
    print("\nTesting PythonCodeNode...")
    test_python_code_node()
    
    print("\nAll tests passed!")