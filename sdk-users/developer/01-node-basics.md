# Getting Started with Custom Nodes

## Overview

Custom nodes extend the Kailash SDK by adding new functionality. Every custom node inherits from the `Node` base class and must implement two abstract methods.

## Understanding the Node Base Class

The `Node` base class provides:
- Parameter validation (improved in Session 061)
- Configuration management  
- Execution lifecycle (construction → configuration → execution)
- Error handling
- Integration with workflows

**IMPORTANT**: As of Session 061, parameter validation happens at execution time, not construction time. This allows more flexible node creation patterns.

## Required Abstract Methods

Every custom node MUST implement these two methods:

### 1. `get_parameters() -> Dict[str, NodeParameter]`

Defines the node's parameters (inputs).

```python
def get_parameters(self) -> Dict[str, NodeParameter]:
    """Define node parameters."""
    return {
        'input_text': NodeParameter(
            name='input_text',
            type=str,
            required=True,
            description='Text to process'
        )
    }
```

### 2. `run(**kwargs) -> Dict[str, Any]`

Executes the node's logic.

```python
def run(self, **kwargs) -> Dict[str, Any]:
    """Execute node logic."""
    input_text = kwargs['input_text']
    # Process the input
    result = input_text.upper()
    return {'output': result}
```

## Your First Custom Node

Here's a complete example of a simple text processing node:

```python
from typing import Any, Dict
from kailash.nodes.base import Node, NodeParameter

class TextUppercaseNode(Node):
    """Converts text to uppercase."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for uppercase conversion."""
        return {
            'text': NodeParameter(
                name='text',
                type=str,
                required=True,
                description='Text to convert to uppercase'
            ),
            'add_prefix': NodeParameter(
                name='add_prefix',
                type=bool,
                required=False,
                default=False,
                description='Whether to add UPPERCASE: prefix'
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        """Convert text to uppercase."""
        text = kwargs['text']
        add_prefix = kwargs.get('add_prefix', False)
        
        result = text.upper()
        if add_prefix:
            result = f"UPPERCASE: {result}"
            
        return {'result': result}
```

## Using Your Custom Node

### In a Workflow

```python
from kailash import Workflow

# Create workflow
workflow = Workflow("text_processing")

# Add your custom node
workflow.add_node("uppercase", TextUppercaseNode(), text="hello world")

# Execute
results = workflow.execute()
print(results['uppercase']['result'])  # "HELLO WORLD"
```

### With Dynamic Parameters

```python
# Parameters can be provided at runtime
results = workflow.execute(parameters={
    'uppercase': {
        'text': 'dynamic text',
        'add_prefix': True
    }
})
print(results['uppercase']['result'])  # "UPPERCASE: DYNAMIC TEXT"
```

## Node Lifecycle

1. **Initialization**: Node is created with configuration
2. **Validation**: Parameters are validated against schema
3. **Execution**: `run()` method is called with validated parameters
4. **Output**: Results are returned to workflow

## Configuration vs Runtime Parameters

### Configuration Parameters (Static)
Set when adding node to workflow:
```python
workflow.add_node("reader", CSVReaderNode(), file_path="data.csv")
```

### Runtime Parameters (Dynamic)
Provided during execution:
```python
workflow.execute(parameters={
    'processor': {'column': 'price', 'operation': 'sum'}
})
```

## Best Practices

1. **Clear Parameter Names**: Use descriptive names
2. **Comprehensive Descriptions**: Document what each parameter does
3. **Sensible Defaults**: Provide defaults for optional parameters
4. **Type Safety**: Use appropriate parameter types
5. **Error Messages**: Provide helpful error messages
6. **Output Consistency**: Use consistent output key names

## Common Pitfalls

### ❌ Forgetting Abstract Methods
```python
class BadNode(Node):
    def run(self, **kwargs):
        return {}
    # Missing get_parameters()!
```

### ❌ Wrong Return Type
```python
def get_parameters(self):
    return []  # Should return Dict[str, NodeParameter]
```

### ❌ Using Generic Types
```python
NodeParameter(type=List[str])  # Use 'list' or 'Any' instead
```

## Next Steps

- Learn about [Parameter Type Constraints](02-parameter-types.md)
- Explore [Common Patterns](03-common-patterns.md)
- See [Working Examples](examples/)

## Session 061 Architecture Improvements

### New Node Creation Patterns

**NEW (Session 061+)**: Nodes can be created without all required parameters:

```python
# ✅ NEW: Create nodes without all required params
kafka_consumer = KafkaConsumerNode()  # No validation error
workflow.add_node("consumer", kafka_consumer)

# Configuration happens at runtime via parameters
runtime.execute(workflow, parameters={
    "consumer": {"bootstrap_servers": "localhost:9092"}
})
```

**OLD (Pre-Session 061)**: Required parameters at construction:

```python
# ❌ OLD: Required all parameters at construction  
kafka_consumer = KafkaConsumerNode(
    bootstrap_servers="localhost:9092"  # Had to provide during construction
)
```

### New Execution Methods

**NEW**: Proper method separation:

```python
# 1. Configure the node
node.configure({"provider": "openai", "model": "gpt-4"})

# 2. Execute with runtime data
results = node.run(input_text="Hello world")
```

**OLD**: Mixed execution patterns (deprecated):

```python
# ❌ DEPRECATED: Don't use node.execute() directly
results = node.execute({"provider": "openai", "input_text": "Hello"})
```

### Migration Notes

- All existing workflows continue to work (no breaking changes)
- New validation timing prevents construction-time errors
- Better separation of configuration vs runtime data
- Improved error messages when parameters are missing

---

*Continue to [02-parameter-types.md](02-parameter-types.md) →*