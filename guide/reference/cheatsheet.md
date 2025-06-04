# Kailash SDK Quick Reference Cheatsheet

## Quick Links to Resources
- **[Node Catalog](node-catalog.md)** - All 66 available nodes with parameters
- **[Pattern Library](pattern-library.md)** - Common workflow patterns and best practices
- **[Templates](templates/)** - Ready-to-use code templates
- **[API Registry](api-registry.yaml)** - Complete API reference
- **[Validation Guide](validation-guide.md)** - Avoid common mistakes

## Installation
```bash
pip install kailash
```

## Basic Imports
```python
from kailash import Workflow, WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode, CSVWriterNode, JSONReaderNode, JSONWriterNode, TextReaderNode, TextWriterNode
from kailash.nodes.ai import LLMAgentNode, EmbeddingGeneratorNode
from kailash.nodes.api import HTTPRequestNode, RESTClientNode
from kailash.nodes.transform import DataTransformerNode
from kailash.nodes.logic import SwitchNode, MergeNode, WorkflowNode
from kailash.nodes.code import PythonCodeNode
```

## Quick Workflow Creation

### Method 1: Direct Construction
```python
# Create workflow
workflow = Workflow("my_pipeline")

# Add nodes with CONFIGURATION parameters (static settings)
workflow.add_node("reader", CSVReaderNode(), file_path="input.csv")  # WHERE to read
workflow.add_node("processor", DataTransformerNode(), 
    operations=[{"type": "filter", "condition": "age > 18"}]  # HOW to process
)
workflow.add_node("writer", CSVWriterNode(), file_path="output.csv")  # WHERE to write

# Connect nodes - RUNTIME data flows through these connections
workflow.connect("reader", "processor", mapping={"data": "data"})  # data flows at runtime
workflow.connect("processor", "writer", mapping={"data": "data"})

# Execute with runtime (RECOMMENDED)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

# OR execute directly (without runtime)
results = workflow.execute(inputs={})

# INVALID: workflow.execute(runtime) does NOT exist
```

### Method 2: Builder Pattern
```python
workflow = (WorkflowBuilder()
    .create("my_pipeline")
    .add_node("reader", CSVReaderNode, {"file_path": "input.csv"})
    .add_node("processor", DataTransformerNode, {
        "operations": [{"type": "filter", "condition": "age > 18"}]
    })
    .add_node("writer", CSVWriterNode, {"file_path": "output.csv"})
    .connect("reader", "processor")
    .connect("processor", "writer")
    .build()
)
```

## Common Node Patterns

### Data I/O
```python
# CSV Reading
workflow.add_node("csv_in", CSVReaderNode(), 
    file_path="data.csv",
    delimiter=",",
    has_header=True
)

# JSON Writing
workflow.add_node("json_out", JSONWriterNode(), 
    file_path="output.json",
    indent=2
)
```

### AI/LLM Integration
```python
# LLM Processing
workflow.add_node("llm", LLMAgentNode(), 
    provider="openai",
    model="gpt-4",
    temperature=0.7,
    system_prompt="You are a data analyst."
)

# Generate Embeddings
workflow.add_node("embedder", EmbeddingGeneratorNode(), 
    provider="openai",
    model="text-embedding-ada-002"
)
```

### API Calls
```python
# Simple HTTP Request
workflow.add_node("api_call", HTTPRequestNode(), 
    url="https://api.example.com/data",
    method="GET",
    headers={"Authorization": "Bearer token"}
)

# REST Client with Auth
workflow.add_node("rest", RESTClientNode(), 
    base_url="https://api.example.com",
    auth_type="bearer",
    auth_config={"token": "your-token"}
)
```

### Data Transformation
```python
workflow.add_node("transform", DataTransformerNode(), 
    operations=[
        {"type": "filter", "condition": "status == 'active'"},
        {"type": "map", "expression": "{'id': id, 'name': name.upper()}"},
        {"type": "sort", "key": "created_at", "reverse": True}
    ]
)
```

### Conditional Logic
```python
# Route based on conditions
workflow.add_node("router", SwitchNode(), 
    conditions=[
        {"output": "high", "expression": "value > 100"},
        {"output": "medium", "expression": "value > 50"},
        {"output": "low", "expression": "value <= 50"}
    ]
)

# Connect conditional outputs
workflow.connect("router", "high_handler", mapping={"high": "input"})
workflow.connect("router", "medium_handler", mapping={"medium": "input"})
workflow.connect("router", "low_handler", mapping={"low": "input"})
```

### Custom Python Code
```python
workflow.add_node("custom", PythonCodeNode(), 
    code='''
def execute(data):
    # Custom processing logic
    result = []
    for item in data:
        if item['score'] > 0.8:
            result.append({
                'id': item['id'],
                'category': 'high_confidence',
                'score': item['score']
            })
    return {'filtered': result}
'''
)
```

## Connection Patterns

### Basic Connection
```python
workflow.connect("node1", "node2", mapping={"data": "data"})
```

### Named Ports
```python
workflow.connect("node1", "node2", mapping={"processed": "data"})
```

### Multiple Outputs
```python
# SwitchNode node with multiple outputs (each output is mapped)
workflow.connect("switch", "handler1", mapping={"case1": "input"})
workflow.connect("switch", "handler2", mapping={"case2": "input"})
workflow.connect("switch", "default_handler", mapping={"default": "input"})
```

### Merging Inputs
```python
# MergeNode node with multiple inputs
workflow.connect("source1", "merge", mapping={"data": "input1"})
workflow.connect("source2", "merge", mapping={"data": "input2"})
workflow.connect("source3", "merge", mapping={"data": "input3"})
```

## Execution Options

### Standard Execution Pattern
```python
# Always use runtime for workflow execution
runtime = LocalRuntime()

# Basic execution (no parameter overrides)
results, run_id = runtime.execute(workflow)

# Execution with parameter overrides
results, run_id = runtime.execute(
    workflow,
    parameters={
        "reader": {"file_path": "custom.csv"},  # Override node config
        "filter": {"threshold": 100}            # Runtime parameter
    }
)
```

### Parameters Structure
```python
# The 'parameters' dict maps node IDs to their parameter overrides
parameters = {
    "node_id_1": {
        "param1": "value1",
        "param2": 123
    },
    "node_id_2": {
        "param": "override_value"
    }
}
```

### Passing Initial Data to Workflows
```python
# Option 1: Source nodes (self-contained)
workflow.add_node("reader", CSVReaderNode(), file_path="data.csv")
# No external input needed

# Option 2: External data injection (flexible)
workflow.add_node("processor", DataProcessor())
runtime.execute(workflow, parameters={
    "processor": {"data": [1, 2, 3], "config": {...}}
})

# Option 3: Hybrid (source + override)
workflow.add_node("reader", CSVReaderNode(), file_path="default.csv")
runtime.execute(workflow, parameters={
    "reader": {"file_path": "custom.csv"}  # Override at runtime
})
```

### Common Execution Mistakes
```python
# ❌ WRONG - Using wrong parameter name
runtime.execute(workflow, inputs={"data": [1, 2, 3]})  # Should be 'parameters'

# ❌ WRONG - Passing as positional argument
runtime.execute(workflow, {"node": {"param": "value"}})  # Must use parameters=...

# ❌ WRONG - Wrong return value handling
results = runtime.execute(workflow)  # Returns tuple (results, run_id)
results, run_id = workflow.execute(inputs={})  # Returns only results
```

### Access Results
```python
# Get output from specific node
node_output = results.get("node_id", {}).get("output_name")

# Get final results (from nodes with no outgoing connections)
final_results = results.get("_final_outputs", {})
```

## Error Handling
```python
try:
    workflow.validate()  # Check workflow structure
    results = workflow.execute(inputs={})
except WorkflowValidationError as e:
    print(f"Workflow structure error: {e}")
except NodeExecutionError as e:
    print(f"Node {e.node_id} failed: {e}")
```

## Export Workflows
```python
# Export to YAML
from kailash.utils.export import export_workflow
export_workflow(workflow, "workflow.yaml", format="yaml")

# Export to dictionary
workflow_dict = workflow.to_dict()

# Load from dictionary
loaded_workflow = Workflow.from_dict(workflow_dict)
```

## Visualization
```python
# Generate visualization
from kailash import WorkflowVisualizer
visualizer = WorkflowVisualizer()
visualizer.visualize(workflow, "workflow.png")

# Generate Mermaid diagram
from kailash.workflow.mermaid_visualizer import MermaidVisualizer
mermaid_code = MermaidVisualizer.generate(workflow)
```

## Custom Node Creation
```python
from typing import Any, Dict
from kailash.nodes.base import Node, NodeParameter, register_node

@register_node()
class MyCustomNode(Node):
    """Process data with a threshold filter.
    
    Custom node that filters input data based on a configurable threshold.
    """
    
    def __init__(self, **kwargs):
        """Initialize the node with configuration."""
        super().__init__(**kwargs)
        # Access config during initialization if needed
        self.threshold = self.config.get("threshold", 0.5)
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters (REQUIRED method)."""
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Input data to process"
            ),
            "options": NodeParameter(
                name="options",
                type=dict,
                required=False,
                default={},
                description="Processing options"
            )
        }
    
    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define output schema for validation (OPTIONAL method)."""
        return {
            "result": NodeParameter(
                name="result",
                type=dict,
                required=True,
                description="Processing result with filtered data and count"
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=True,
                description="Processing metadata"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the node logic (REQUIRED method).
        
        This method receives validated parameters as keyword arguments.
        """
        # Get inputs
        data = kwargs["data"]
        options = kwargs.get("options", {})
        
        # Use configuration from initialization
        threshold = options.get("threshold", self.threshold)
        
        # Process data
        filtered = [item for item in data if item > threshold]
        
        # Return outputs matching the schema
        return {
            "result": {
                "filtered": filtered,
                "count": len(filtered),
                "threshold_used": threshold
            },
            "metadata": {
                "total_items": len(data),
                "filtered_items": len(filtered),
                "filter_rate": len(filtered) / len(data) if data else 0
            }
        }
```

## Common Workflow Patterns

### ETL Pipeline
```python
workflow = (WorkflowBuilder()
    .create("etl_pipeline")
    .add_node("extract", CSVReaderNode, {"file_path": "raw_data.csv"})
    .add_node("transform", DataTransformerNode, {
        "operations": [
            {"type": "filter", "condition": "valid == True"},
            {"type": "map", "expression": "process_record(item)"}
        ]
    })
    .add_node("load", CSVWriterNode, {"file_path": "processed_data.csv"})
    .connect("extract", "transform")
    .connect("transform", "load")
    .build()
)
```

### AI Analysis Pipeline
```python
workflow = (WorkflowBuilder()
    .create("ai_analysis")
    .add_node("reader", JSONReaderNode, {"file_path": "documents.json"})
    .add_node("embedder", EmbeddingGeneratorNode, {
        "provider": "openai",
        "model": "text-embedding-ada-002"
    })
    .add_node("analyzer", LLMAgentNode, {
        "provider": "openai",
        "model": "gpt-4",
        "system_prompt": "Analyze the following documents..."
    })
    .add_node("writer", JSONWriterNode, {"file_path": "analysis.json"})
    .connect("reader", "embedder")
    .connect("embedder", "analyzer", mapping={"embeddings": "context"})
    .connect("reader", "analyzer", mapping={"data": "prompt"})
    .connect("analyzer", "writer")
    .build()
)
```

### API Integration
```python
workflow = (WorkflowBuilder()
    .create("api_integration")
    .add_node("trigger", HTTPRequestNode, {
        "url": "https://api.source.com/events",
        "method": "GET"
    })
    .add_node("processor", PythonCodeNode, {
        "code": "def execute(data): return {'processed': transform(data)}"
    })
    .add_node("webhook", HTTPRequestNode, {
        "url": "https://api.destination.com/webhook",
        "method": "POST"
    })
    .connect("trigger", "processor")
    .connect("processor", "webhook")
    .build()
)
```

## Environment Variables
```python
# Common environment variables for API keys
os.environ["OPENAI_API_KEY"] = "your-key"
os.environ["ANTHROPIC_API_KEY"] = "your-key"

# Use in node config
workflow.add_node("llm", LLMAgentNode(), {
    "provider": "openai",
    "model": "gpt-4"
    # api_key will be read from OPENAI_API_KEY env var
})
```

## Quick Tips

1. **Always validate workflows before execution**: `workflow.validate()`
2. **Use named outputs/inputs for clarity**: `from_output="processed"` 
3. **Chain operations in DataTransformer**: Multiple operations in sequence
4. **Handle errors gracefully**: Wrap execution in try/except
5. **Export workflows for reuse**: Save as YAML/JSON
6. **Use environment variables for secrets**: Never hardcode API keys
7. **Test with small data first**: Validate logic before scaling
8. **Use type hints in custom nodes**: Better IDE support
9. **Document node configurations**: Clear descriptions in docstrings
10. **Monitor execution with tracking**: Built-in performance metrics