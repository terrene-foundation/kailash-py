# PythonCodeNode - Custom Code Execution in Workflows

The PythonCodeNode allows users to execute arbitrary Python code within Kailash workflows, providing maximum flexibility for custom data processing logic.

## Overview

The PythonCodeNode supports three main ways to create custom nodes:

1. **Function-based nodes**: Wrap existing Python functions as nodes
2. **Class-based nodes**: Create stateful nodes from Python classes
3. **Code string nodes**: Execute Python code strings dynamically

## Features

- Automatic type inference from function signatures
- Safe execution environment with configurable module access
- State management for class-based nodes
- Integration with pandas, numpy, and other data processing libraries
- Full error handling and validation

## Function-Based Nodes

Convert any Python function into a Kailash node:

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

def process_data(data: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Filter data based on threshold."""
    return data[data['value'] > threshold]

# Create node from function and use in workflow
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "threshold_filter", {
    **PythonCodeNode.from_function(process_data).config,
    "description": "Filter data by threshold value"
})

```

## Class-Based Nodes

Create stateful nodes that maintain state between executions:

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

class MovingAverage:
    def __init__(self, window_size: int = 3):
        self.window_size = window_size
        self.values = []

    def process(self, value: float) -> float:
        """Calculate moving average."""
        self.values.append(value)
        if len(self.values) > self.window_size:
            self.values.pop(0)
        return sum(self.values) / len(self.values)

# Create node from class and use in workflow
workflow.add_node("PythonCodeNode", "moving_avg", {
    **PythonCodeNode.from_class(MovingAverage).config,
    "description": "Calculate moving average"
})

```

## Code String Nodes

Execute Python code strings directly:

```python
code = '''
# Custom aggregation logic
grouped = data.groupby('category').agg({
    'value': ['mean', 'std', 'count']
})

# Flatten column names
grouped.columns = ['_'.join(col).strip() for col in grouped.columns.values]
grouped.reset_index(inplace=True)

result = grouped
'''

# Add to workflow using string node type
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "custom_aggregator", {
    "code": code,
    "description": "Custom data aggregation"
})

```

## Loading from Files

Load Python code from external files:

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Load a function from file
workflow.add_node("PythonCodeNode", "file_processor",
    PythonCodeNode.from_file(
        file_path="custom_processor.py",
        function_name="process_data"
    ).config
)

# Load a class from file
workflow.add_node("PythonCodeNode", "file_class_processor",
    PythonCodeNode.from_file(
        file_path="custom_processor.py",
        class_name="DataProcessor"
    ).config
)

```

## Security and Safety

The PythonCodeNode includes several safety features:

1. **Module Whitelist**: Only allowed modules can be imported (configurable)
2. **Error Isolation**: Execution errors are caught and wrapped
3. **Type Validation**: Input and output types are validated
4. **Resource Limits**: Future support for memory and time limits

## Allowed Modules

By default, the following modules are allowed in code execution:

- pandas
- numpy
- json
- datetime
- math
- re
- collections
- itertools
- functools
- statistics

Additional modules can be configured when creating the node.

## Best Practices

1. **Type Annotations**: Always use type hints for better validation
2. **Docstrings**: Document your functions and classes
3. **Error Handling**: Handle exceptions gracefully
4. **Stateless Functions**: Prefer stateless functions when possible
5. **Testing**: Test your code before wrapping in nodes

## Examples

See the `examples/python_code_node_example.py` file for comprehensive examples of:

- Function-based data processing
- Stateful class-based nodes
- Complex code string execution
- Integration with other Kailash nodes
- Error handling patterns

## Integration with Workflows

PythonCodeNodes integrate seamlessly with other Kailash nodes:

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Create workflow
workflow = WorkflowBuilder()

# Add nodes
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "input.csv"
})

# Add custom processor using from_function
workflow.add_node("PythonCodeNode", "processor",
    PythonCodeNode.from_function(my_processing_function).config
)

workflow.add_node("CSVWriterNode", "writer", {
    "file_path": "output.csv"
})

# Connect nodes
workflow.add_connection("reader", "data", "processor", "data")
workflow.add_connection("processor", "result", "writer", "data")

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

## Validation Behavior

PythonCodeNode leverages the base Node class validation system:

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Using workflow execution (recommended approach)
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor",
    PythonCodeNode.from_function(func).config
)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "processor": {"x": 5, "y": 10}
})
result = results["processor"]

```

## Advanced Usage

### Custom Module Access

```python
# Create node with custom allowed modules
workflow.add_node("PythonCodeNode", "custom_node", {
    "code": "result = custom_function(data)",
    "allowed_modules": ['scipy', 'sklearn']
})

```

### Dynamic Parameter Types

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

def create_dynamic_node(input_types: dict):
    """Create a node with dynamic input types."""
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "dynamic_processor", {
        "code": "result = sum(inputs.values())",
        "description": "Dynamic input processor"
    })
    return workflow

```

## Limitations

1. Code execution is synchronous
2. Limited to Python-compatible data types
3. Some modules may not be available in production environments
4. Performance overhead compared to native nodes

## Future Enhancements

- Async execution support
- Better type inference for complex types
- Jupyter notebook cell execution
- Remote code execution
- Performance optimizations
