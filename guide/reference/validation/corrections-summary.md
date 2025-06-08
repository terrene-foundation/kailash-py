# Critical Corrections for Kailash SDK Reference Documentation

This document summarizes the critical corrections needed across all reference documentation files to align with the actual codebase implementation.

## 1. Node Class Naming

**UPDATED STANDARD**: All node classes now end with "Node" suffix

**CURRENT REALITY**: Consistent naming across all modules:
- **Data nodes**: WITH "Node" suffix (`CSVReaderNode`, `JSONWriterNode`, `TextReaderNode`)
- **API nodes**: WITH "Node" suffix (`HTTPRequestNode`, `RESTClientNode`, `AsyncHTTPRequestNode`)
- **Code nodes**: WITH "Node" suffix (`PythonCodeNode`)
- **Logic nodes**: WITH "Node" suffix (`SwitchNode`, `MergeNode`, `WorkflowNode`)
- **AI nodes**: WITH "Node" suffix (`LLMAgentNode`, `EmbeddingGeneratorNode`)

## 2. Workflow Execution Pattern

**INVALID PATTERN**:
```python
workflow.execute(runtime)  # INVALID - This pattern does NOT exist
```

**VALID PATTERNS**:
```python
# Option 1: Execute through runtime (RECOMMENDED)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

# Option 2: Direct execution (without runtime)
results = workflow.execute(inputs={})
```

**KEY POINT**: The pattern `workflow.execute(runtime)` is completely unsupported and will cause errors.

## 3. Connection Method Signature

**INCORRECT SIGNATURE**:
```python
workflow.connect(from_node, to_node, from_output="out", to_input="in")
```

**CORRECT SIGNATURE**:
```python
workflow.connect(source_node, target_node, mapping={"output": "input"})
```

## 4. Add Node Method Signature

**INCORRECT**:
```python
workflow.add_node(node_id, node, config={"key": "value"})
```

**CORRECT**:
```python
workflow.add_node(node_id, node_or_type, **config)
# Config passed as kwargs, not as a dict
workflow.add_node("reader", CSVReaderNode, file_path="data.csv")  # Using class
workflow.add_node("reader", CSVReaderNode(), file_path="data.csv")  # Using instance
workflow.add_node("reader", "CSVReaderNode", file_path="data.csv")  # Using string name
```

## 5. Import Paths

**INCORRECT**:
```python
from kailash import LocalRuntime  # WRONG
from kailash.workflow import MermaidVisualizer  # WRONG
```

**CORRECT**:
```python
from kailash.runtime.local import LocalRuntime
from kailash.workflow.mermaid_visualizer import MermaidVisualizer
from kailash.workflow.graph import Workflow
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.data import CSVWriterNode
from kailash.nodes.api.http import HTTPRequestNode
from kailash.nodes.code.python import PythonCodeNode
```

## 6. Node Registration and Registry

**INCORRECT ASSUMPTION**: All nodes must be registered with alias

**REALITY**:
- Most nodes use `@register_node()` without alias
- Node class name becomes the registry name
- Example: `CSVReaderNode` class is registered as "CSVReaderNode"

## 7. Required Node Methods

**CORRECT NODE STRUCTURE**:
```python
@register_node()
class MyCustomNode(Node):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        """REQUIRED: Define input parameters"""
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Input data"
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """REQUIRED: Execute node logic"""
        data = kwargs["data"]
        return {"result": processed_data}

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """OPTIONAL: Define output schema"""
        return {}  # Default if not overridden
```

## 8. Workflow Creation Patterns

**CORRECT WORKFLOW PATTERN**:
```python
from kailash.workflow.graph import Workflow
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.data import CSVWriterNode
from kailash.runtime.local import LocalRuntime

# Create workflow with proper ID and metadata
workflow = Workflow(
    workflow_id="unique_id",  # Required
    name="workflow_name",      # Required
    description="...",         # Optional
    version="1.0.0",          # Optional
    author="..."              # Optional
)

# Add nodes with proper configuration
workflow.add_node("reader", CSVReaderNode, file_path="data.csv", headers=True)
workflow.add_node("writer", CSVWriterNode, file_path="output.csv")

# Connect nodes with mapping
workflow.connect("reader", "writer", mapping={"data": "data"})

# Execute via runtime
runtime = LocalRuntime(debug=True)
results, run_id = runtime.execute(workflow)
```

## Files Requiring Updates

1. **cheatsheet.md**: ✅ UPDATED
   - Fixed node class names
   - Corrected execution patterns
   - Updated connection signatures
   - Fixed config as kwargs

2. **validation-guide.md**: ✅ UPDATED
   - Updated to reflect "all nodes now end with Node" rule
   - Updated method signatures
   - Fixed execution examples
   - Corrected config patterns

3. **api-registry.yaml**: ✅ FULLY UPDATED
   - Fixed workflow method signatures
   - Updated all node class names to include Node suffix
   - Added missing TextReaderNode and TextWriterNode
   - Corrected examples to use kwargs
   - Still needs full review of all nodes

4. **README.md**: ✅ UPDATED
   - Updated critical rules section
   - Fixed quick start example

5. **validate_kailash_code.py**: ❌ NEEDS COMPLETE REWRITE
   - Currently enforces incorrect rules
   - Needs to handle varying node naming patterns
   - Should check for actual patterns, not assumed ones
   - Incorrect execute() validation (doesn't require runtime parameter)
   - Wrong import mappings

6. **api-validation-schema.json**: ❌ NEEDS COMPLETE UPDATE
   - Contains many incorrect assumptions
   - Wrong method signatures (connect, execute, add_node)
   - Incorrect node naming rules
   - Wrong import paths

## Recommended Actions

1. **Create automated tests** that validate all examples in documentation actually work
2. **Add CI check** that compares reference docs against actual implementation
3. **Consider standardizing** node naming for consistency (all with or without "Node")
4. **Update validation tools** to reflect actual patterns, not assumed ones
5. **Add version tracking** to know when docs are out of sync

## Key Takeaways for LLMs

When generating Kailash SDK code:
1. Always check the specific module for node naming patterns
2. Use kwargs for node configuration, not dict parameters
3. Execute workflows through runtime OR directly, but not `workflow.execute(runtime)`
4. Use `mapping` parameter for connections, not `from_output`/`to_input`
5. Import from full module paths, not from `kailash` directly
6. Workflow requires `workflow_id` and `name` parameters
7. Node classes can be passed as class, instance, or string name to `add_node`
8. Not all nodes end with "Node" - this is module-specific
