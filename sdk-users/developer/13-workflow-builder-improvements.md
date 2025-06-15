# WorkflowBuilder.from_dict() Improvements

**Core SDK Enhancement - December 2024**

## Overview

The Kailash SDK now includes comprehensive improvements to `WorkflowBuilder.from_dict()` that resolve constructor inconsistencies and enable seamless dynamic workflow creation with all node types.

## Key Improvements

### ✅ 1. Automatic Parameter Mapping

The workflow builder now automatically handles different node constructor patterns:

```python
# Previously failed for PythonCodeNode
workflow_config = {
    "nodes": [
        {
            "id": "processor",
            "type": "PythonCodeNode",
            "config": {
                "code": "result = {'processed': True}"
                # 'name' parameter auto-mapped from 'id'
            }
        }
    ]
}

# Now works seamlessly
builder = WorkflowBuilder.from_dict(workflow_config)
workflow = builder.build()  # ✅ Success
```

### ✅ 2. Enhanced Error Diagnostics

Clear error messages with constructor signature details:

```python
# Invalid configuration
workflow_config = {
    "nodes": [{
        "id": "invalid_node",
        "type": "PythonCodeNode",
        "config": {"invalid_param": "value"}  # Missing 'code'
    }]
}

try:
    builder = WorkflowBuilder.from_dict(workflow_config)
    workflow = builder.build()
except WorkflowValidationError as e:
    print(e)
    # Clear error: "Node 'PythonCodeNode' requires 'code' parameter.
    # Constructor signature: __init__(name, code=None, function=None, ...)
    # Config provided: ['invalid_param']"
```

### ✅ 3. Constructor Validation

All registered nodes are validated for WorkflowBuilder compatibility:

```python
@register_node()
class CustomNode(Node):
    def __init__(self, unusual_param):  # Missing name/id/**kwargs
        super().__init__()

# Registration warning:
# "Node CustomNode constructor may not work with WorkflowBuilder.from_dict().
#  Constructor should accept 'name', 'id', or **kwargs parameter."
```

## Supported Node Constructor Patterns

The SDK now supports all these patterns automatically:

### Pattern 1: Name-based (like PythonCodeNode)
```python
class MyNode(Node):
    def __init__(self, name: str, param1: str, **kwargs):
        super().__init__(name=name, **kwargs)
```

### Pattern 2: ID-based (traditional)
```python
class MyNode(Node):
    def __init__(self, id: str = None, param1: str = None, **kwargs):
        super().__init__(id=id, **kwargs)
```

### Pattern 3: Flexible (recommended)
```python
class MyNode(Node):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
```

## Dynamic Workflow Examples

### Mixed Node Types
```python
workflow_config = {
    "name": "Mixed Processing Pipeline",
    "nodes": [
        {
            "id": "data_reader",
            "type": "CSVReaderNode",           # Traditional pattern
            "config": {"file_path": "data.csv"}
        },
        {
            "id": "processor",
            "type": "PythonCodeNode",          # Name-based pattern
            "config": {
                "code": "result = {'count': len(input_data)}"
            }
        },
        {
            "id": "filter",
            "type": "FilterNode",              # Flexible pattern
            "config": {"condition": "value > 10"}
        }
    ],
    "connections": [
        {
            "from_node": "data_reader",
            "from_output": "data",
            "to_node": "processor",
            "to_input": "input_data"
        },
        {
            "from_node": "processor",
            "from_output": "result",
            "to_node": "filter",
            "to_input": "data"
        }
    ]
}

# All node types work seamlessly
builder = WorkflowBuilder.from_dict(workflow_config)
workflow = builder.build()
```

### Class-based Workflow Templates
```python
class DataProcessingWorkflow:
    """Reusable workflow template."""

    @staticmethod
    def get_config(input_file: str, processing_code: str):
        return {
            "name": "data_processing_template",
            "nodes": [
                {
                    "id": "reader",
                    "type": "CSVReaderNode",
                    "config": {"file_path": input_file}
                },
                {
                    "id": "processor",
                    "type": "PythonCodeNode",
                    "config": {"code": processing_code}
                }
            ],
            "connections": [
                {
                    "from_node": "reader",
                    "from_output": "data",
                    "to_node": "processor",
                    "to_input": "input_data"
                }
            ]
        }

# Usage with automatic parameter mapping
config = DataProcessingWorkflow.get_config(
    "sales_data.csv",
    "result = {'total': sum(item['amount'] for item in input_data)}"
)
workflow = WorkflowBuilder.from_dict(config).build()
```

## Middleware Integration

These improvements enable robust middleware dynamic workflow creation:

```python
# Middleware can now create workflows with any node type
async def create_dynamic_workflow(self, session_id: str, workflow_config: dict):
    """Create workflow from user configuration."""
    try:
        # Automatic parameter mapping handles all node types
        workflow = WorkflowBuilder.from_dict(workflow_config).build()

        # Execute with SDK runtime
        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute(workflow, parameters={})

        return results
    except WorkflowValidationError as e:
        # Enhanced error diagnostics help debug configuration issues
        logger.error(f"Workflow creation failed: {e}")
        raise
```

## Migration Guide

**For Existing Code**: No changes required - improvements are backward compatible

**For New Code**: Take advantage of enhanced error messages and automatic mapping

**For Node Developers**: Ensure constructors follow one of the supported patterns

## Testing

Comprehensive test coverage validates all improvements:

```bash
# Test node constructor mapping
python -m pytest tests/test_workflow/test_node_constructor_mapping.py

# Test middleware integration
python -m pytest tests/test_middleware/test_middleware_comprehensive.py
```

## Benefits

- ✅ **Seamless Dynamic Workflows**: All node types work with WorkflowBuilder.from_dict()
- ✅ **Better Developer Experience**: Clear error messages with actionable guidance
- ✅ **Future-Proof**: Constructor validation prevents compatibility issues
- ✅ **Middleware Ready**: Robust foundation for dynamic workflow creation
- ✅ **Backward Compatible**: Existing code continues to work unchanged

These improvements make the Kailash SDK more robust and developer-friendly, enabling sophisticated middleware applications with dynamic workflow capabilities.
