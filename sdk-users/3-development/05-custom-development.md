# Custom Development - Build Nodes & Extensions

*Create enterprise-grade custom nodes with proper parameter handling and security*

## Prerequisites

- Completed [Fundamentals](01-fundamentals.md) - Core SDK concepts
- Completed [Workflows](02-workflows.md) - Basic workflow patterns
- Understanding of Python classes and inheritance
- Familiarity with type hints

## 🚨 CRITICAL: SDK Nodes vs Custom Nodes

### **Fundamental Pattern Difference**

The Kailash SDK has **different patterns** for SDK nodes vs custom nodes:

#### **SDK Nodes (String-based)**
```python
# ✅ SDK nodes use string references
workflow.add_node("PythonCodeNode", "processor", {"code": "..."})
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
```

#### **Custom Nodes (Class-based)**
```python
# ✅ Custom nodes use class references
from myapp.nodes import CustomProcessorNode
workflow.add_node("CustomProcessorNode", "processor", {"threshold": 0.8})
```

#### **Common Mistake**
```python
# ❌ WRONG: String reference for custom node
workflow.add_node("CustomProcessorNode", "processor", {})
# ERROR: Node 'CustomProcessorNode' not found in registry
```

### **Understanding the Warning**

When using custom nodes, you'll see:
```
✅ CUSTOM NODE USAGE CORRECT

Pattern: add_node(CustomProcessorNode, 'processor', {...})
Status: This is the CORRECT pattern for custom nodes

⚠️  IGNORE "preferred pattern" suggestions for custom nodes
String references only work for @register_node() decorated SDK nodes.
```

**This warning is expected and correct** - it confirms you're using the right pattern.

## Basic Custom Node Structure

### Essential Rules for Custom Nodes

All custom nodes must inherit from `Node` and follow these patterns:

```python
from typing import Dict, Any
from kailash.nodes.base import Node, NodeParameter

class CustomProcessorNode(Node):
    """Custom data processing node."""

    def __init__(self, **kwargs):
        # ⚠️ CRITICAL: Set attributes BEFORE calling super().__init__()
        self.processing_mode = kwargs.get("processing_mode", "standard")
        self.threshold = kwargs.get("threshold", 0.75)

        # NOW call parent init
        super().__init__(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define ALL parameters the node accepts."""
        return {
            "input_data": NodeParameter(
                name="input_data",
                type=list,
                required=True,
                description="Data to process"
            ),
            "threshold": NodeParameter(
                name="threshold",
                type=float,
                required=False,
                default=0.75,
                description="Processing threshold"
            ),
            "processing_mode": NodeParameter(
                name="processing_mode",
                type=str,
                required=False,
                default="standard",
                description="Processing mode"
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute node logic. NEVER override execute()!"""
        # SDK only passes parameters declared in get_parameters()
        input_data = kwargs.get("input_data", [])
        threshold = kwargs.get("threshold", self.threshold)
        mode = kwargs.get("processing_mode", self.processing_mode)

        # Process data
        result = self._process_data(input_data, threshold, mode)

        return {"result": result}

    def _process_data(self, data, threshold, mode):
        """Internal processing logic."""
        # Your custom logic here
        return [item for item in data if item > threshold]
```

## 🚨 Parameter Declaration Best Practices

### **The Silent Parameter Dropping Issue**

The SDK **ONLY** injects parameters declared in `get_parameters()`:

```python
class BrokenNode(Node):
    def get_parameters(self):
        return {}  # ❌ Empty! No parameters declared

    def run(self, **kwargs):
        # kwargs will be EMPTY even if workflow provides parameters!
        data = kwargs.get("data")  # Always None!
        return {"result": data}

# In workflow:
workflow.add_node("BrokenNode", "broken", {"data": [1,2,3]})
# The "data" parameter is SILENTLY DROPPED!
```

### **Correct Parameter Declaration**

```python
class WorkingNode(Node):
    def get_parameters(self):
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Input data to process"
            )
        }

    def run(self, **kwargs):
        data = kwargs["data"]  # ✅ Now available!
        return {"result": data}
```

### **Parameter Validation**

The SDK now provides comprehensive parameter validation:

```python
# During workflow.build(), the SDK will:
# 1. Detect empty parameter declarations with workflow config
# 2. Warn about undeclared parameters that will be ignored
# 3. Check for missing required parameters
# 4. Validate parameter types

# Example validation messages:
# ERROR PAR001: Node declares no parameters but workflow provides ['data', 'config']
# WARNING PAR002: Parameters ['extra'] not declared - will be ignored by SDK
# ERROR PAR004: Required parameter 'input_data' not provided by workflow
```

## Secure Enterprise Nodes

### **Using SecureGovernedNode**

For enterprise applications, use `SecureGovernedNode` for built-in security:

```python
from kailash.nodes.governance import SecureGovernedNode

class EnterpriseProcessorNode(SecureGovernedNode):
    """Enterprise-grade processor with security and governance."""

    def get_parameters(self):
        return {
            "sensitive_data": NodeParameter(
                name="sensitive_data",
                type=dict,
                required=True,
                description="Sensitive data requiring validation"
            ),
            "user_context": NodeParameter(
                name="user_context",
                type=dict,
                required=True,
                description="User authentication context"
            )
        }

    def run_governed(self, **kwargs):
        """Implement governed logic (called after validation)."""
        # All inputs are pre-validated and sanitized
        sensitive_data = kwargs["sensitive_data"]
        user_context = kwargs["user_context"]

        # Your secure processing logic
        result = self._process_with_audit(sensitive_data, user_context)

        return {"secure_result": result}
```

### **Security Features**

`SecureGovernedNode` provides:
- ✅ Automatic input sanitization
- ✅ Parameter declaration validation
- ✅ Audit logging
- ✅ Security context management
- ✅ Performance monitoring

## Import Best Practices

### **Absolute Imports (REQUIRED for Production)**

```python
# ✅ CORRECT: Absolute imports work in production
from src.myapp.nodes.processors import DataProcessor
from src.myapp.utils.validators import validate_input
from src.myapp.contracts.schemas import DataSchema

# ❌ WRONG: Relative imports fail in production
from ..processors import DataProcessor  # Fails when run from repo root
from .validators import validate_input  # Fails in Docker
from utils.helpers import format_data   # Implicit relative - fails
```

### **Validate Your Imports**

Use the import validator to ensure production compatibility:

```bash
# Validate your custom nodes
python -m kailash.cli.validate_imports src/myapp/nodes

# Fix import issues
python -m kailash.cli.validate_imports src/myapp/nodes --fix
```

## Workflow Integration

### **Registering Custom Nodes**

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from src.myapp.nodes.custom import CustomProcessorNode

# Create workflow
workflow = WorkflowBuilder()

# ✅ CORRECT: Use class reference for custom nodes
workflow.add_node("CustomProcessorNode", "processor", {
    "threshold": 0.8,
    "mode": "advanced"
})

# Connect nodes
workflow.add_connection("input", "data", "processor", "input_data")
workflow.add_connection("processor", "result", "output", "data")

# Build and execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Testing Custom Nodes

### **Unit Testing Pattern**

```python
import pytest
from src.myapp.nodes.custom import CustomProcessorNode

class TestCustomProcessorNode:
    def test_parameter_declarations(self):
        """Test that all parameters are properly declared."""
        node = CustomProcessorNode()
        params = node.get_parameters()

        # Verify required parameters
        assert "input_data" in params
        assert params["input_data"].required is True
        assert params["input_data"].type == list

    def test_execution_with_valid_data(self):
        """Test node execution with valid inputs."""
        node = CustomProcessorNode()

        # Use execute() for tests, not run()
        result = node.execute(
            input_data=[1, 2, 3, 4, 5],
            threshold=3
        )

        assert result["result"] == [4, 5]

    def test_missing_required_parameter(self):
        """Test that missing required parameters raise errors."""
        node = CustomProcessorNode()

        with pytest.raises(ValueError) as exc_info:
            node.execute(threshold=3)  # Missing input_data

        assert "Missing required parameter" in str(exc_info.value)
```

### **Integration Testing**

```python
def test_custom_node_in_workflow():
    """Test custom node integration in workflow."""
    workflow = WorkflowBuilder()

    # Add custom node
    workflow.add_node("CustomProcessorNode", "processor", {
        "threshold": 0.5
    })

    # Build should validate parameters
    built_workflow = workflow.build()

    # Execute with runtime
    runtime = LocalRuntime()
    results, run_id = runtime.execute(built_workflow)

    assert results["processor"]["result"] is not None
```

## Common Mistakes and Solutions

### **1. Empty get_parameters()**
```python
# ❌ WRONG
def get_parameters(self):
    return {}  # All workflow parameters will be ignored!

# ✅ CORRECT
def get_parameters(self):
    return {
        "param": NodeParameter(name="param", type=str, required=True)
    }
```

### **2. Overriding execute()**
```python
# ❌ WRONG
def execute(self, **kwargs):  # Don't override this!
    return self.process(kwargs)

# ✅ CORRECT
def run(self, **kwargs):  # Implement run() instead
    return self.process(kwargs)
```

### **3. Using String References**
```python
# ❌ WRONG
workflow.add_node("MyCustomNode", "node1", {})  # Not registered!

# ✅ CORRECT
workflow.add_node("MyCustomNode", "node1", {})  # Use class
```

### **4. Relative Imports**
```python
# ❌ WRONG
from .utils import helper  # Fails in production

# ✅ CORRECT
from src.myapp.nodes.utils import helper  # Absolute import
```

## Advanced Patterns

### **Async Custom Nodes**

For async operations, inherit from `AsyncNode`:

```python
from kailash.nodes.base_async import AsyncNode
from kailash.nodes.base import NodeParameter

class AsyncDataFetcher(AsyncNode):
    """Async node for external data fetching."""

    def get_parameters(self):
        return {
            "url": NodeParameter(
                name="url",
                type=str,
                required=True,
                description="URL to fetch data from"
            )
        }

    async def async_run(self, **kwargs):
        """Implement async logic here."""
        url = kwargs["url"]

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()

        return {"fetched_data": data}
```

### **Dynamic Parameter Nodes**

For nodes with dynamic parameters based on configuration:

```python
class DynamicProcessorNode(Node):
    """Node with dynamic parameter requirements."""

    def __init__(self, field_config=None, **kwargs):
        self.field_config = field_config or {}
        super().__init__(**kwargs)

    def get_parameters(self):
        params = {
            "base_data": NodeParameter(
                name="base_data",
                type=dict,
                required=True
            )
        }

        # Add dynamic parameters based on config
        for field_name, field_type in self.field_config.items():
            params[field_name] = NodeParameter(
                name=field_name,
                type=field_type,
                required=False,
                description=f"Dynamic field: {field_name}"
            )

        return params
```

## Production Checklist

Before deploying custom nodes:

- [ ] ✅ All parameters declared in `get_parameters()`
- [ ] ✅ Using absolute imports throughout
- [ ] ✅ Implementing `run()` not `execute()`
- [ ] ✅ Using class references in workflows
- [ ] ✅ Unit tests for parameter validation
- [ ] ✅ Integration tests with workflows
- [ ] ✅ Security validation for sensitive data
- [ ] ✅ Import validation passes
- [ ] ✅ No relative imports
- [ ] ✅ Error handling for missing parameters

## Next Steps

- Review [Parameter Passing Patterns](../2-core-concepts/cheatsheet/028-parameter-passing-patterns.md)
- Explore [SecureGovernedNode Guide](../5-enterprise/patterns/13-secure-governed-nodes.md)
- Check [Import Validation Guide](../7-gold-standards/absolute-imports-gold-standard.md)
- Study [Testing Best Practices](12-testing-production-quality.md)

---

**Remember**: Custom nodes use class references, SDK nodes use string references. This is by design and both patterns are correct for their respective use cases.
