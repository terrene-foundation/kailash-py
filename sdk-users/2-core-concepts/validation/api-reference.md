# API Reference - Method Signatures & Patterns

*Complete reference for all Kailash SDK methods*

## 📦 **Required Imports**

All examples in this guide assume these imports:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime, AccessControlledRuntime
from kailash.nodes.data import CSVReaderNode, CSVWriterNode, JSONReaderNode, JSONWriterNode, TextReaderNode, TextWriterNode, DirectoryReaderNode
from kailash.nodes.ai import LLMAgentNode, EmbeddingGeneratorNode
from kailash.nodes.api import HTTPRequestNode, RESTClientNode
from kailash.nodes.logic import SwitchNode, MergeNode, WorkflowNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.transform import DataTransformerNode, FilterNode
from kailash.nodes.base import Node, NodeParameter
from kailash.workflow.builder import WorkflowBuilder
```

## 📋 **Core Workflow Methods**

### **Workflow Class**
```python
from kailash.workflow.builder import WorkflowBuilder

# Constructor
Workflow(id: str, name: str = None) -> Workflow

# Node management
workflow.add_node(node_id: str, node: Node, **config) -> None
workflow.remove_node(node_id: str) -> None
workflow.get_node(node_id: str) -> Node

# Connections
workflow.add_connection("source", "result", "target", "input")  # Fixed mapping pattern -> None

workflow.disconnect(from_node: str, to_node: str) -> None

# Validation and execution
workflow.validate() -> bool
runtime.execute(workflow.build(), ) -> Dict

# Utility methods
workflow.get_nodes() -> Dict[str, Node]
workflow.get_connections() -> List[Dict]
workflow.get_unconnected_nodes() -> List[str]
workflow.to_dict() -> Dict
Workflow.from_dict(data: Dict) -> Workflow

```

### **Runtime Classes**
```python
from kailash.runtime.local import LocalRuntime
from kailash.runtime.access_controlled import AccessControlledRuntime

# LocalRuntime
LocalRuntime(
    max_workers: int = 4,
    timeout: float = 300.0,
    enable_logging: bool = True
)

# Execution (returns tuple)
runtime.execute(
    workflow: Workflow,
    parameters: Dict[str, Dict[str, Any]] = None,
    timeout: float = None
) -> Tuple[Dict, str]

# AccessControlledRuntime
AccessControlledRuntime(
    access_control_strategy: str = "rbac",
    default_permissions: List[str] = None,
    audit_enabled: bool = False
)

```

## 🔧 **Node Configuration Patterns**

### **Data Nodes**
```python
from kailash.nodes.data import (
    CSVReaderNode, CSVWriterNode,
    JSONReaderNode, JSONWriterNode,
    TextReaderNode, TextWriterNode,
    DirectoryReaderNode
)

# CSVReaderNode
CSVReaderNode(
    file_path: str = None,
    has_header: bool = True,
    delimiter: str = ",",
    encoding: str = "utf-8",
    skip_rows: int = 0,
    max_rows: int = None
)

# CSVWriterNode
CSVWriterNode(
    file_path: str = None,
    include_header: bool = True,
    delimiter: str = ",",
    encoding: str = "utf-8",
    mode: str = "w"
)

# DirectoryReaderNode
DirectoryReaderNode(
    directory_path: str = None,
    file_pattern: str = "*",
    recursive: bool = False,
    include_metadata: bool = False,
    max_files: int = None
)

```

### **AI Nodes**
```python

from kailash.nodes.ai import LLMAgentNode, EmbeddingGeneratorNode

# LLMAgentNode
LLMAgentNode(
    provider: str = "openai",
    model: str = "gpt-4",
    temperature: float = 0.7,
    max_tokens: int = 1000,
    system_prompt: str = None,
    top_p: float = 1.0,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0
)

# EmbeddingGeneratorNode
EmbeddingGeneratorNode(
    provider: str = "openai",
    model: str = "text-embedding-ada-002",
    batch_size: int = 100,
    dimensions: int = None
)

```

### **API Nodes**
```python

from kailash.nodes.api import HTTPRequestNode, RESTClientNode

# HTTPRequestNode
HTTPRequestNode(
    url: str = None,
    method: str = "GET",
    headers={},
    timeout: float = 30.0,
    verify_ssl: bool = True,
    follow_redirects: bool = True
)

# RESTClientNode
RESTClientNode(
    base_url: str = None,
    auth_type: str = None,
    auth_config: Dict[str, Any] = None,
    default_headers={},
    timeout: float = 30.0
)

```

### **Logic Nodes**
```python

from kailash.nodes.logic import SwitchNode, MergeNode, WorkflowNode

# SwitchNode
SwitchNode(
    conditions: List[Dict[str, str]] = None,
    default_output: str = "default"
)

# MergeNode
MergeNode(
    strategy: str = "combine",  # "combine", "first", "priority"
    priority_order: List[str] = None
)

# WorkflowNode (nested workflows)
WorkflowNode(
    workflow: Workflow = None,
    # mapping removed)

```

### **Code Nodes**
```python

from kailash.nodes.code import PythonCodeNode

# PythonCodeNode (most flexible)
PythonCodeNode(
    "workflow_name",                           # REQUIRED
    code: str = None,
    input_types: Dict[str, type] = None, # CRITICAL for parameter mapping
    timeout: float = 30.0,
    memory_limit: int = 512,             # MB
    sandbox_mode: bool = True
)

```

## 📊 **Parameter Flow Patterns**

### **Configuration vs Runtime Parameters**
```python

# Configuration parameters (set at node creation)
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {}),
    file_path="default.csv",    # Configuration parameter
    has_header=True,           # Configuration parameter
    delimiter=","              # Configuration parameter
)

# Runtime parameters (override at execution)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "reader": {
        "file_path": "custom.csv",  # Runtime override
        "delimiter": "|"            # Runtime override
    }
})

```

### **Parameter Structure for Runtime**
```python

# Standard parameter structure
results, run_id = runtime.execute(workflow, parameters= {
    "node_id_1": {
        "param1": "value1",
        "param2": 123,
        "param3": True
    },
    "node_id_2": {
        "config_override": "new_value",
        "additional_data": [1, 2, 3]
    }
}

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters=parameters)

```

### **Input Flow to Source Nodes**
```python

# Pattern 1: Source nodes with no external inputs
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {}), file_path="data.csv")
# No external parameters needed

# Pattern 2: External data injection
workflow = WorkflowBuilder()
workflow.add_connection("from_node", "to_node", "output", "input")}",
    input_types={"external_data": list}
))

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "processor": {"external_data": [1, 2, 3, 4, 5]}
})

# Pattern 3: Hybrid (source + runtime override)
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {}), file_path="default.csv")
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
runtime = LocalRuntime()
workflow.csv"}  # Override default
})

```

## 🔄 **Connection Mapping Reference**

### **Basic Mapping Patterns**
```python

# Automatic mapping (when names match)
workflow = WorkflowBuilder()
workflow.add_connection("reader", "result", "processor", "input")
# Maps: reader.data → processor.data (automatic)

# Explicit mapping
workflow = WorkflowBuilder()
workflow.add_connection("from_node", "to_node", "output", "input")

# Nested data access
workflow = WorkflowBuilder()
workflow.add_connection("from_node", "to_node", "output", "input")

```

### **Multiple Input/Output Patterns**
```python

# Multiple inputs to one node (MergeNode)
workflow = WorkflowBuilder()
workflow.add_connection("from_node", "to_node", "output", "input")
workflow = WorkflowBuilder()
workflow.add_connection("from_node", "to_node", "output", "input")
workflow = WorkflowBuilder()
workflow.add_connection("from_node", "to_node", "output", "input")

# Multiple outputs from one node (SwitchNode)
workflow = WorkflowBuilder()
workflow.add_connection("from_node", "to_node", "output", "input")
workflow = WorkflowBuilder()
workflow.add_connection("from_node", "to_node", "output", "input")
workflow = WorkflowBuilder()
workflow.add_connection("from_node", "to_node", "output", "input")

```

### **Cyclic Connection Patterns**
```python

# Basic cycle
workflow = WorkflowBuilder()
workflow.add_connection("from_node", "to_node", "output", "input")

# Complex cycle with state preservation
workflow = WorkflowBuilder()
workflow.add_connection("from_node", "to_node", "output", "input") < 0.01"
)

```

## 🔍 **WorkflowBuilder vs Workflow.connect()**

### **Workflow.connect() (Recommended)**
```python

# Direct workflow connection (simpler)
workflow = WorkflowBuilder()
workflow.workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {}), file_path="data.csv")
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor", {}))
workflow = WorkflowBuilder()
workflow.add_connection("from_node", "to_node", "output", "input")

```

### **WorkflowBuilder (Alternative API)**
```python
# Builder pattern (different parameter structure)
from kailash.workflow.builder import WorkflowBuilder

builder = WorkflowBuilder()
reader_id = builder.add_node("CSVReaderNode", config={"file_path": "data.csv"})
processor_id = builder.add_node("PythonCodeNode", config={"name": "proc", "code": "result = data"})
builder.add_connection(reader_id, "data", processor_id, "data")  # 4 parameters

workflow = builder.build()

```

## 📋 **Complete Example Templates**

### **Template 1: Data Processing Pipeline**
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.transform import DataTransformerNode
from kailash.nodes.code import PythonCodeNode

# Create workflow
workflow = WorkflowBuilder()

# Add nodes with configuration
workflow.add_node("CSVReaderNode", "reader", {}),
    file_path="input.csv",
    has_header=True,
    delimiter=","
)

workflow.add_node("DataTransformerNode", "transformer", {}),
    operations=[
        {"type": "filter", "condition": "age > 18"},
        {"type": "map", "expression": "{'name': name.upper(), 'age': age}"}
    ]
)

workflow.add_node("PythonCodeNode", "processor", {})
result = {
    "processed_data": data,
    "total_processed": processed_count,
    "processing_timestamp": "2024-01-01T10:00:00Z"
}
''',
    input_types={"data": list}
))

workflow.add_node("CSVWriterNode", "writer", {}),
    file_path="output.csv",
    include_header=True
)

# Connect nodes
workflow.add_connection("reader", "transformer", "data", "data")
workflow.add_connection("transformer", "processor", "transformed", "data")
workflow.add_connection("processor", "writer", "processed_data", "data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "reader": {"file_path": "custom_input.csv"},
    "writer": {"file_path": "custom_output.csv"}
})

```

### **Template 2: AI Processing Pipeline**
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai import LLMAgentNode, EmbeddingGeneratorNode
from kailash.nodes.data import JSONReaderNode, JSONWriterNode

workflow = WorkflowBuilder()

workflow.add_node("JSONReaderNode", "reader", {}),
    file_path="prompts.json"
)

workflow.add_node("LLMAgentNode", "llm", {}),
    provider="openai",
    model="gpt-4",
    temperature=0.7,
    max_tokens=1000
)

workflow.add_node("EmbeddingGeneratorNode", "embedder", {}),
    provider="openai",
    model="text-embedding-ada-002"
)

workflow.add_node("JSONWriterNode", "writer", {}),
    file_path="results.json",
    indent=2
)

workflow.add_connection("reader", "llm", "data", "prompt")
workflow.add_connection("llm", "embedder", "response", "text")
workflow.add_connection("embedder", "writer", "embeddings", "data")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

## 🔗 **Next Steps**

- **[Critical Rules](critical-rules.md)** - Essential rules for success
- **[Common Mistakes](common-mistakes.md)** - Error prevention
- **[Advanced Patterns](advanced-patterns.md)** - Complex scenarios

---

**Use this reference to verify method signatures and parameter patterns!**
