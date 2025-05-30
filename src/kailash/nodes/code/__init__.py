"""Code execution nodes for running arbitrary Python code.

This module enables users to write custom Python code as functions or classes
and automatically wrap them as Kailash nodes. This provides maximum flexibility
for users who need custom processing logic that doesn't fit into predefined nodes.

Key Features:
1. Function wrapping - Convert any Python function into a node
2. Class wrapping - Convert Python classes into stateful nodes
3. Dynamic execution - Run arbitrary Python code safely
4. Type inference - Automatically detect inputs/outputs
5. Error handling - Graceful error management during execution

Example:
    # Define a custom function
    def process_data(data: pd.DataFrame, threshold: float) -> pd.DataFrame:
        return data[data['value'] > threshold]

    # Wrap it as a node
    custom_node = PythonCodeNode.from_function(
        func=process_data,
        name="threshold_filter",
        description="Filter data by threshold"
    )

    # Use in workflow
    workflow.add_node(custom_node)
"""

from .python import ClassWrapper, CodeExecutor, FunctionWrapper, PythonCodeNode

__all__ = ["PythonCodeNode", "CodeExecutor", "FunctionWrapper", "ClassWrapper"]
