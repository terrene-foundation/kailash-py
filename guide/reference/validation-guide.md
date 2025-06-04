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

## Workflow Execution with Inputs

### Primary Execution Method: Runtime.execute()

The standard way to execute workflows in Kailash SDK is through a runtime:

```python
# ✅ CORRECT - Use 'parameters' keyword argument
runtime = LocalRuntime()
results, run_id = runtime.execute(
    workflow,
    parameters={
        "node_id": {
            "param1": "value1",
            "param2": 123
        }
    }
)

# ❌ WRONG - Don't pass inputs as positional argument
results, run_id = runtime.execute(workflow, {"key": "value"})  # WRONG!
```

### Note about Workflow.execute()

While the Workflow class has an `execute()` method, it is not commonly used in practice. All examples and production code use `runtime.execute()` for workflow execution because it provides:
- Task tracking and monitoring
- Proper error handling
- Run ID generation
- Performance metrics

**Recommendation**: Always use `runtime.execute()` for executing workflows.

### Key Differences

| Method | Input Parameter | Return Value | Usage |
|--------|----------------|--------------|--------|
| `runtime.execute(workflow, parameters=...)` | `parameters` (node-specific) | `(results, run_id)` | Production workflows |
| `workflow.execute(inputs=...)` | `inputs` (initial data) | `results` only | Simple testing |

### Parameters Structure

When using `runtime.execute()`, the `parameters` dict maps node IDs to their inputs:

```python
parameters = {
    "reader_node": {
        "file_path": "override.csv"  # Override node's config
    },
    "filter_node": {
        "threshold": 500  # Runtime parameter override
    }
}

results, run_id = runtime.execute(workflow, parameters=parameters)
```

### How Inputs Flow to First Nodes

**IMPORTANT**: Workflows in Kailash SDK can receive initial inputs through multiple mechanisms:

#### 1. Source Nodes (Traditional Pattern)
```python
# Source nodes generate their own data
csv_reader = CSVReaderNode(file_path="data.csv")
workflow.add_node("reader", csv_reader)
# No external input needed - node reads from file
```

#### 2. External Data via Parameters (Dynamic Pattern)
```python
# Processing nodes can receive data from runtime.execute()
filter_node = FilterNode()
workflow.add_node("filter", filter_node)

# Pass data directly to the node
results, run_id = runtime.execute(
    workflow,
    parameters={
        "filter": {
            "data": [1, 2, 3, 4, 5],  # External data
            "threshold": 3
        }
    }
)
```

#### 3. Hybrid Pattern (Source + Parameters)
```python
# Source nodes can also accept parameter overrides
workflow.add_node("reader", CSVReaderNode(), file_path="default.csv")

# Override at runtime
results, run_id = runtime.execute(
    workflow,
    parameters={
        "reader": {"file_path": "custom.csv"}  # Override default
    }
)
```

**Key Point**: There's no requirement for workflows to start with source nodes. Any node can be the entry point and receive data through the `parameters` mechanism.

### Common Mistakes

```python
# ❌ WRONG - Mixing up parameter names
runtime.execute(workflow, inputs={"data": [1, 2, 3]})  # Should be 'parameters'
workflow.execute(parameters={"node": {}})  # Should be 'inputs'

# ❌ WRONG - Passing as positional argument
runtime.execute(workflow, {"data": [1, 2, 3]})  # Must use parameters=...

# ❌ WRONG - Wrong return value unpacking
results = runtime.execute(workflow)  # Returns tuple, not just results
results, run_id = workflow.execute(inputs={})  # Returns only results
```

## WorkflowBuilder vs Workflow Connection Methods

**IMPORTANT**: There's an inconsistency between connection methods:

### Workflow.connect() (Recommended)
```python
# Uses mapping dictionary
workflow.connect("source", "target", mapping={"output": "input"})
workflow.connect("node1", "node2")  # Default: {"output": "input"}
```

### WorkflowBuilder.add_connection() (Different API)
```python
# Requires 4 parameters - NO mapping dict
builder.add_connection("source", "output", "target", "input")
```

**Recommendation**: Use `Workflow` directly with `connect()` method for consistency. The `WorkflowBuilder` has a different API that may cause confusion.

## Configuration vs Runtime Parameters

### Critical Distinction
There are two types of parameters when working with nodes:

1. **Configuration Parameters** - Set when adding the node to workflow
2. **Runtime Parameters** - Passed during execution via inputs

### Understanding get_parameters() Method

**IMPORTANT**: The `get_parameters()` method defines ALL parameters a node can accept, both configuration AND runtime parameters. It does NOT distinguish between them - that distinction happens at the workflow level:

```python
class MyNode(Node):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            # This could be configuration OR runtime depending on usage
            "file_path": NodeParameter(name="file_path", type=str, required=True),
            "data": NodeParameter(name="data", type=Any, required=False),
            "threshold": NodeParameter(name="threshold", type=float, required=False)
        }
```

The same parameter can be:
- **Configuration**: Set via `add_node(..., config={...})`
- **Runtime**: Passed via connections from other nodes
- **Both**: Configuration provides default, runtime overrides it

### How It Works in Practice

```python
# Node defines ALL possible parameters
class FilterNode(Node):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(name="data", type=list, required=True),
            "column": NodeParameter(name="column", type=str, required=True),
            "threshold": NodeParameter(name="threshold", type=float, required=True)
        }

# Usage Option 1: All as configuration (static workflow)
workflow.add_node("filter", FilterNode(), 
    config={
        "data": [{"value": 100}, {"value": 200}],  # Static data
        "column": "value",
        "threshold": 150
    }
)

# Usage Option 2: Mixed (typical pattern)
workflow.add_node("filter", FilterNode(),
    config={
        "column": "value",      # Configuration: which column to filter
        "threshold": 150        # Configuration: filter threshold
    }
)
# "data" comes from connection at runtime
workflow.connect("reader", "filter", {"output": "data"})

# During execution:
# 1. Node receives config: {"column": "value", "threshold": 150}
# 2. Node receives runtime: {"data": [...from reader...]}
# 3. Merged inputs: {"column": "value", "threshold": 150, "data": [...]}
```

### Configuration Parameters (Static)
These are set once when adding a node to the workflow and remain constant:

```python
# ✅ CORRECT - Configuration parameters as kwargs
workflow.add_node("reader", CSVReaderNode(), 
    file_path="data.csv",         # Configuration parameter
    delimiter=",",                # Configuration parameter  
    has_header=True              # Configuration parameter
)

workflow.add_node("llm", LLMAgentNode(),
    provider="openai",           # Configuration parameter
    model="gpt-4",              # Configuration parameter
    temperature=0.7             # Configuration parameter
)

# ❌ WRONG - Don't pass runtime data as configuration
workflow.add_node("processor", DataProcessor(),
    data=[1, 2, 3]  # WRONG: data should come from connections
)
```

### Runtime Parameters (Dynamic)
These are passed between nodes during execution:

```python
# ✅ CORRECT - Runtime parameters flow through connections
workflow.add_node("reader", CSVReaderNode(), file_path="input.csv")
workflow.add_node("processor", ProcessorNode())
workflow.connect("reader", "processor", mapping={"data": "data"})  # data flows at runtime

# The processor node receives 'data' as a runtime parameter:
class ProcessorNode(Node):
    def run(self, **kwargs):
        data = kwargs["data"]  # Runtime parameter from connection
        return {"processed": transform(data)}
```

### Key Rules

1. **File paths, API keys, models = Configuration**
   ```python
   # These are configuration parameters
   file_path="data.csv"
   api_key="sk-..."
   model="gpt-4"
   base_url="https://api.example.com"
   ```

2. **Data to process = Runtime**
   ```python
   # These flow through connections
   data, text, documents, records, items
   ```

3. **Node behavior settings = Configuration**
   ```python
   # These control HOW the node operates
   temperature=0.7
   max_tokens=1000
   delimiter=","
   chunk_size=500
   ```

4. **Processing inputs/outputs = Runtime**
   ```python
   # These are WHAT the node processes
   input_text, query, prompt, response
   ```

### Common Mistake Pattern
```python
# ❌ WRONG - Trying to pass runtime data as configuration
workflow.add_node("analyzer", TextAnalyzer(),
    text="Analyze this text"  # WRONG: text should come from connections
)

# ✅ CORRECT - Runtime data flows through connections
workflow.add_node("reader", TextReaderNode(), file_path="document.txt")
workflow.add_node("analyzer", TextAnalyzer())
workflow.connect("reader", "analyzer", mapping={"content": "text"})
```

### How to Identify Parameter Type

Ask yourself:
- **"Does this change between workflow runs?"** → Runtime parameter
- **"Is this data to be processed?"** → Runtime parameter  
- **"Does this configure HOW the node works?"** → Configuration parameter
- **"Is this a resource location or credential?"** → Configuration parameter

### Examples by Node Type

#### Data Nodes
```python
# Configuration: WHERE to read/write
workflow.add_node("csv", CSVReaderNode(), 
    file_path="data.csv",      # Config: file location
    delimiter=","              # Config: how to parse
)
# Runtime: WHAT data flows through
# The actual CSV data is a runtime parameter
```

#### AI Nodes  
```python
# Configuration: HOW to process
workflow.add_node("llm", LLMAgentNode(),
    provider="openai",         # Config: which service
    model="gpt-4",            # Config: which model
    system_prompt="..."       # Config: behavior
)
# Runtime: WHAT to process
# The actual prompt/text is a runtime parameter
```

#### API Nodes
```python
# Configuration: WHERE and HOW to connect
workflow.add_node("api", HTTPRequestNode(),
    url="https://api.example.com/endpoint",  # Config: endpoint
    method="POST",                            # Config: HTTP method
    headers={"Auth": "Bearer ..."}           # Config: auth
)
# Runtime: WHAT data to send/receive
# The request body and response are runtime parameters
```

## Remember: When in Doubt, Check the Registry

Always refer to `api-registry.yaml` for:
- Exact class names (all now end with "Node")
- Exact method signatures
- Exact parameter names and order
- Exact config key names (use underscores)