# API Validation Guide for LLMs

## Critical Rules for Using Kailash SDK

### 1. **ALWAYS Use Exact Method Names**
```python
# ✅ CORRECT
workflow.add_node("id", NodeClass(), param1="value1")
workflow.connect("from", "to", mapping={"output": "input"})
workflow.execute(inputs={})  # Direct execution (without runtime)
runtime.execute(workflow)     # Through runtime (RECOMMENDED)

# ❌ INVALID - This pattern does NOT exist
workflow.execute(runtime)     # INVALID - causes error

# ❌ WRONG - Common mistakes
workflow.addNode()      # Wrong: camelCase
workflow.add()          # Wrong: incomplete name  
workflow.node()         # Wrong: incorrect name
workflow.run()          # Wrong: should be execute()
```

### 2. **Node Class Names Vary - Check Each Module**
```python
# ✅ CORRECT - Data nodes (WITH "Node" suffix)
from kailash.nodes.data import CSVReaderNode, JSONWriterNode, TextReaderNode

# ✅ CORRECT - API nodes (WITH "Node" suffix)
from kailash.nodes.api import HTTPRequestNode, RESTClientNode

# ✅ CORRECT - Other nodes with "Node" suffix
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.logic import WorkflowNode

# ❌ WRONG - Using wrong suffix pattern
from kailash.nodes.data import CSVReaderNode   # DOES NOT EXIST (old name)
from kailash.nodes.api import HTTPRequest       # DOES NOT EXIST
```

### 3. **Parameter Order and Names are STRICT**
```python
# ✅ CORRECT - Actual signatures
workflow.add_node(node_id: str, node_or_type: Any, **config)
workflow.connect(source_node: str, target_node: str, mapping: Dict[str, str] = None)

# ❌ WRONG - Common mistakes
workflow.add_node(node, "id", config)                    # Wrong order
workflow.connect("from", "to", from_output="out")      # Wrong: no from_output param
workflow.add_node("id", Node(), {"key": "value"})      # Wrong: config as dict, not kwargs
```

### 4. **Config Keys are Case-Sensitive**
```python
# ✅ CORRECT
config = {
    "file_path": "data.csv",    # Correct: underscore
    "has_header": True,         # Correct: underscore
    "system_prompt": "..."      # Correct: underscore
}

# ❌ WRONG  
config = {
    "filePath": "data.csv",     # Wrong: camelCase
    "file-path": "data.csv",    # Wrong: hyphen
    "filepath": "data.csv"      # Wrong: no separator
}
```

### 5. **Import Paths are Exact**
```python
# ✅ CORRECT - Full import paths
from kailash import Workflow, WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode, JSONWriterNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.logic import SwitchNode

# ❌ WRONG - Incorrect paths
from kailash import LocalRuntime              # Wrong: LocalRuntime is in runtime.local
from kailash.data import CSVReaderNode            # Missing .nodes
from kailash.nodes import CSVReaderNode           # Missing .data
from kailash.ai.nodes import LLMAgentNode         # Wrong structure
```

## Common Method Signatures Reference

### Workflow Methods
```python
# Creating workflow
workflow = Workflow(workflow_id: str, name: str, description: str = "")

# Adding nodes - ACTUAL signature
workflow.add_node(
    node_id: str,           # Unique identifier
    node_or_type: Any,      # Node instance, class, or type name
    **config                # Configuration as keyword arguments
) -> None

# Connecting nodes - ACTUAL signature  
workflow.connect(
    source_node: str,                    # Source node ID
    target_node: str,                    # Target node ID
    mapping: Optional[Dict[str, str]] = None  # Output-to-input mapping
) -> None

# Executing workflow - Two options
# Option 1: Direct execution
workflow.execute(
    inputs: Optional[Dict[str, Any]] = None,    # Optional initial inputs
    task_manager: Optional[TaskManager] = None  # Optional task tracking
) -> Dict[str, Any]

# Option 2: Through runtime
runtime = LocalRuntime()
results, run_id = runtime.execute(
    workflow: Workflow,
    inputs: Optional[Dict[str, Any]] = None
) -> Tuple[Dict[str, Any], str]
```

### Node Configuration Patterns

#### Data Nodes
```python
# CSVReaderNode - Configuration as keyword arguments
workflow.add_node("reader", CSVReaderNode(), 
    file_path="data.csv",      # Required
    delimiter=",",              # Optional, default: ","
    has_header=True,            # Optional, default: True
    encoding="utf-8"            # Optional, default: "utf-8"
)

# CSVWriterNode - Configuration as keyword arguments
workflow.add_node("writer", CSVWriterNode(),
    file_path="output.csv",     # Required
    delimiter=",",              # Optional, default: ","
    write_header=True           # Optional, default: True
)
```

#### AI Nodes
```python
# LLMAgentNode - EXACT config keys
LLMAgentNode_config = {
    "provider": str,       # Required: "openai", "anthropic", "ollama"
    "model": str,          # Required: model name
    "api_key": str,        # Optional: uses env var if not provided
    "temperature": float,  # Optional, default: 0.7
    "max_tokens": int,     # Optional, default: 1000
    "system_prompt": str   # Optional
}
```

#### API Nodes
```python
# HTTPRequestNode - EXACT config keys
HTTPRequestNode_config = {
    "url": str,            # Required
    "method": str,         # Optional, default: "GET"
    "headers": dict,       # Optional
    "params": dict,        # Optional
    "timeout": int         # Optional, default: 30
}
```

## Validation Checklist for LLMs

Before generating code, verify:

1. ✓ Check each module for correct class names (all nodes now have "Node" suffix)
2. ✓ Method names use snake_case (add_node, not addNode)
3. ✓ Parameter order matches exactly as documented
4. ✓ Config passed as **kwargs, not as a dict parameter
5. ✓ Import paths include all submodules (kailash.runtime.local for LocalRuntime)
6. ✓ Required parameters are provided
7. ✓ Use connect() with mapping parameter, not from_output/to_input
8. ✓ Execute through runtime OR directly on workflow (not workflow.execute(runtime))

## Error Prevention Examples

### Example 1: Reading a CSV File
```python
# ✅ CORRECT
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode  # All nodes have "Node" suffix!

workflow = Workflow("example", "csv_reader")
workflow.add_node("reader", CSVReaderNode(), file_path="data.csv")

# Execute through runtime
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

# OR execute directly
results = workflow.execute(inputs={})

# ❌ COMMON MISTAKES TO AVOID
# Wrong: Using old names without "Node" suffix
from kailash.nodes.data import CSVReaderNode  # OLD NAME - use CSVReaderNode

# Wrong: Config as dict instead of kwargs
workflow.add_node("reader", CSVReaderNode(), {"file_path": "data.csv"})

# Wrong: Passing runtime to workflow.execute()
results = workflow.execute(runtime)  # Runtime not accepted here

# Wrong: Config key format
workflow.add_node("reader", CSVReaderNode(), filePath="data.csv")  # Should be file_path
```

### Example 2: Using LLM
```python
# ✅ CORRECT
from kailash.nodes.ai import LLMAgentNode

workflow.add_node("llm", LLMAgentNode(), 
    provider="openai",
    model="gpt-4",
    temperature=0.7,
    system_prompt="You are a helpful assistant."
)

# ❌ COMMON MISTAKES TO AVOID
# Wrong: Class name
from kailash.nodes.ai import LLM  # Should be LLMAgentNode

# Wrong: Config as dict
workflow.add_node("llm", LLMAgentNode(), {
    "provider": "openai",
    "model": "gpt-4"
})  # Should use kwargs

# Wrong: Config format
workflow.add_node("llm", LLMAgentNode(),
    Provider="openai",      # Should be lowercase
    model_name="gpt-4",     # Should be "model"
    systemPrompt="..."      # Should be system_prompt
)
```

## Quick Validation Function

Use this pattern to validate your generated code:

```python
def validate_kailash_code(code_snippet):
    """Validate common patterns in Kailash code"""
    errors = []
    
    # Check for wrong class names (missing Node suffix)
    wrong_classes = ["CSVReaderNode", "JSONWriterNode", "HTTPRequest", "LLMAgentNode", "SwitchNode", "MergeNode"]
    for wrong in wrong_classes:
        if f"import {wrong}" in code_snippet and "Node" not in wrong:
            errors.append(f"Class {wrong} should be {wrong}Node")
    
    # Check for wrong method names
    wrong_methods = ["addNode", "runWorkflow", "executeWorkflow"]
    for wrong in wrong_methods:
        if wrong in code_snippet:
            errors.append(f"Method {wrong} is incorrect")
    
    # Check for invalid workflow.execute(runtime) pattern
    if "workflow.execute(runtime)" in code_snippet:
        errors.append("workflow.execute(runtime) does NOT exist - use runtime.execute(workflow)")
    
    return errors
```

## Remember: When in Doubt, Check the Registry

Always refer to `api-registry.yaml` for:
- Exact class names (all now end with "Node")
- Exact method signatures
- Exact parameter names and order
- Exact config key names (use underscores)