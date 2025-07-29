# Fundamentals - Core SDK Concepts

*Essential concepts for building with Kailash SDK*

## 🎯 Prerequisites
- Python 3.8+
- Kailash SDK installed (`pip install kailash`)
- Basic understanding of data processing workflows

## 📋 Core Concepts

### Workflows and Nodes
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Workflow is a container for connected nodes
workflow = WorkflowBuilder()

# Nodes are processing units that perform specific tasks
# All node classes end with "Node"
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.transform import DataTransformerNode

```

### Node Lifecycle
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

# 1. Node Creation (configuration time)
reader = CSVReaderNode(
    file_path="/data/input.csv",    # Configuration parameter
    has_header=True,                # Static setting
    delimiter=","                   # Default behavior
)

# 2. Node Registration (workflow building)
workflow = WorkflowBuilder()
workflow.add_node("csv_reader", reader)

# 3. Node Execution (runtime)
runtime = LocalRuntime()
runtime = LocalRuntime()
runtime.execute(workflow.build(), workflow)

# 4. Result Access
csv_data = results.get("csv_reader", {}).get("data", [])

```

## 🔧 Parameter Types & Constraints

### Supported Parameter Types
```python
from kailash.nodes.base import Node, NodeParameter

class MyNode(Node):
    def get_parameters(self):
        return {
            # ✅ CORRECT - Use these types only
            "text_param": NodeParameter(str, "Text input"),
            "number_param": NodeParameter(int, "Integer value"),
            "float_param": NodeParameter(float, "Decimal value"),
            "flag_param": NodeParameter(bool, "True/False flag"),
            "list_param": NodeParameter(list, "List of items"),
            "dict_param": NodeParameter(dict, "Key-value data"),
            "any_param": NodeParameter(Any, "Any type allowed")
        }

    def run(self, **kwargs):
        # Access parameters safely
        text = kwargs.get("text_param", "default")
        number = kwargs.get("number_param", 0)
        return {"processed": f"{text}_{number}"}

```

### Invalid Parameter Types (Never Use)
```python
from typing import List, Dict, Optional, Union

class BadNode(Node):
    def get_parameters(self):
        return {
            # ❌ WRONG - These will cause errors
            "typed_list": NodeParameter(List[str], "Typed list"),      # No generics
            "typed_dict": NodeParameter(Dict[str, int], "Typed dict"), # No generics
            "optional": NodeParameter(Optional[str], "Maybe string"),  # No Optional
            "union": NodeParameter(Union[str, int], "String or int"),  # No Union
            "custom": NodeParameter(MyClass, "Custom class")           # No custom classes
        }

```

### Parameter Validation
```python
class ValidatedNode(Node):
    def get_parameters(self):
        return {
            "required_text": NodeParameter(str, "Required text input", required=True),
            "bounded_number": NodeParameter(int, "Number 1-100",
                                          validation=lambda x: 1 <= x <= 100),
            "enum_choice": NodeParameter(str, "Choose option",
                                       choices=["option1", "option2", "option3"])
        }

    def run(self, **kwargs):
        # Parameters are already validated at this point
        text = kwargs["required_text"]  # Guaranteed to exist
        number = kwargs.get("bounded_number", 50)  # Guaranteed to be 1-100
        choice = kwargs.get("enum_choice", "option1")  # Guaranteed valid choice

        return {"result": f"{text}_{number}_{choice}"}

```

## 🔗 Node Connections & Data Flow

### Basic Connection Patterns
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

# Simple automatic mapping (when output/input names match)
workflow = WorkflowBuilder()
workflow.add_connection("reader", "result", "processor", "input")  # maps "data" → "data"

# Explicit mapping
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Nested data access with dot notation
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

### Advanced Mapping Patterns
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

# Multiple inputs from different sources
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Conditional routing
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

### Auto-Mapping Features
```python
class SmartNode(Node):
    def get_parameters(self):
        return {
            "primary_input": NodeParameter(list, "Main data",
                auto_map_primary=True),  # Automatically maps from primary output

            "alt_input": NodeParameter(dict, "Alternative data",
                auto_map_from=["metadata", "info", "config"]),  # Maps from alternatives

            "workflow_param": NodeParameter(str, "Workflow-level setting",
                workflow_alias="global_setting")  # Maps from workflow parameters
        }

```

## 🛠️ Common Node Patterns

### Data Input Nodes
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

# File reading patterns
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "csv_reader", {}))

workflow = WorkflowBuilder()
workflow.add_node("JSONReaderNode", "json_reader", {}))

workflow = WorkflowBuilder()
workflow.add_node("DirectoryReaderNode", "directory_scanner", {}))

```

### Data Processing Nodes
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

# Transform data with built-in operations
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature, 'age': age}"},
        {"type": "sort", "key": "age", "reverse": True}
    ]
))

# Custom processing with PythonCodeNode
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature if input_data else 0
processed_items = []

for item in input_data:
    if isinstance(item, dict) and "value" in item:
        processed_items.append({
            "id": item.get("id", "unknown"),
            "processed_value": item["value"] * 2,
            "timestamp": "2024-01-01T10:00:00Z"
        })

# ✅ Always wrap output in result dictionary
result = {
    "processed": processed_items,
    "total_count": total_records,
    "processing_date": "2024-01-01"
}
''',
    input_types={"input_data": list}  # ✅ CRITICAL: Define input types
))

```

### Data Output Nodes
```python
# File writing patterns
workflow.add_node("CSVWriterNode", "csv_writer", {}))

workflow.add_node("JSONWriterNode", "json_writer", {}))

# Database output
workflow.add_node("SQLDatabaseNode", "db_writer", {}) VALUES (:data, :timestamp)",
    batch_size=1000
))

```

## ✅ Input/Output Validation

### Workflow Validation
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

# Always validate before execution
try:
workflow = WorkflowBuilder()
workflow.validate()
    print("✅ Workflow structure is valid")
except ValidationError as e:
    print(f"❌ Validation error: {e}")
    # Fix errors before proceeding

# Check for common issues
workflow = WorkflowBuilder()
workflow.get_unconnected_nodes()
if unconnected_nodes:
    print(f"⚠️ Unconnected nodes: {unconnected_nodes}")

workflow = WorkflowBuilder()
workflow.get_missing_inputs()
if missing_inputs:
    print(f"⚠️ Missing required inputs: {missing_inputs}")

```

### Runtime Validation
```python
# Validate data at runtime
class SafeProcessorNode(Node):
    def run(self, context, **kwargs):
        input_data = kwargs.get("input_data", [])

        # Validate input type
        if not isinstance(input_data, list):
            raise ValueError(f"Expected list, got {type(input_data)}")

        # Validate data structure
        valid_items = []
        for item in input_data:
            if isinstance(item, dict) and "id" in item:
                valid_items.append(item)
            else:
                print(f"⚠️ Skipping invalid item: {item}")

        return {"validated_data": valid_items, "validation_count": len(valid_items)}

```

## 📊 Best Practices

### Node Naming Convention
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

# ✅ CORRECT naming patterns
CSVReaderNode       # Data input
DataTransformerNode # Data processing
LLMAgentNode        # AI processing
JSONWriterNode      # Data output
ValidationNode      # Utility

# ❌ WRONG naming patterns
CSVReader          # Missing "Node" suffix
DataTransform      # Missing "Node" suffix
LLMAgent           # Missing "Node" suffix

```

### Parameter Organization
```python
class WellOrganizedNode(Node):
    def get_parameters(self):
        return {
            # Group related parameters
            # Required parameters first
            "input_data": NodeParameter(list, "Input data", required=True),
            "operation_type": NodeParameter(str, "Operation to perform", required=True),

            # Optional parameters with sensible defaults
            "batch_size": NodeParameter(int, "Batch processing size", default=100),
            "timeout": NodeParameter(float, "Operation timeout in seconds", default=30.0),
            "debug_mode": NodeParameter(bool, "Enable debug logging", default=False),

            # Advanced/rarely used parameters last
            "memory_limit": NodeParameter(int, "Memory limit in MB", default=512),
            "custom_headers": NodeParameter(dict, "Custom headers", default={})
        }

```

### Error Handling
```python
class RobustNode(Node):
    def run(self, context, **kwargs):
        try:
            # Main processing logic
            data = kwargs.get("input_data", [])
            processed = self.process_data(data)

            return {
                "result": processed,
                "status": "success",
                "processed_count": len(processed)
            }

        except Exception as e:
            # Return error information instead of raising
            return {
                "result": [],
                "status": "error",
                "error_message": str(e),
                "processed_count": 0
            }

    def process_data(self, data):
        # Separate processing logic for easier testing
        return [item for item in data if self.is_valid(item)]

    def is_valid(self, item):
        return isinstance(item, dict) and "id" in item

```

## 🔗 Related Guides

**Quick References:**
- **[Quick Reference](QUICK_REFERENCE.md)** - Essential patterns and anti-patterns
- **[Node Catalog](../nodes/comprehensive-node-catalog.md)** - Complete node reference

**Next Steps:**
- **[Workflows](02-workflows.md)** - Learn workflow creation and execution patterns
- **[Advanced Features](03-advanced-features.md)** - Enterprise and advanced SDK features
- **[Production](04-production.md)** - Production deployment and security

## 📚 Quick Reference

### Essential Imports
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.base import Node, NodeParameter

```

### Basic Node Template
```python
class MyNode(Node):
    def get_parameters(self):
        return {
            "input_param": NodeParameter(str, "Description", required=True)
        }

    def run(self, context, **kwargs):
        value = kwargs.get("input_param")
        return {"result": f"processed_{value}"}

```

### Workflow Template
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

workflow = WorkflowBuilder()
workflow.workflow = WorkflowBuilder()
workflow.add_node("MyNode", "node_id", {}), input_param="value")
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

runtime = LocalRuntime()
runtime = LocalRuntime()
runtime.execute(workflow.build(), workflow)

```
