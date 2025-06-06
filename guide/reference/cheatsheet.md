# Kailash SDK Quick Reference Cheatsheet

**Version**: 0.1.4 | **Last Updated**: 2025-01-06

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
# Core workflow components
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.runtime.access_controlled import AccessControlledRuntime

# Data I/O nodes
from kailash.nodes.data import (
    CSVReaderNode, CSVWriterNode, 
    JSONReaderNode, JSONWriterNode, 
    TextReaderNode, TextWriterNode,
    SharePointGraphReader, SharePointGraphWriter
)

# AI/ML nodes
from kailash.nodes.ai import LLMAgentNode, EmbeddingGeneratorNode
from kailash.nodes.ai.a2a import SharedMemoryPoolNode, A2AAgentNode, A2ACoordinatorNode
from kailash.nodes.ai.self_organizing import (
    AgentPoolManagerNode, ProblemAnalyzerNode, 
    TeamFormationNode, SelfOrganizingAgentNode
)
from kailash.nodes.ai.intelligent_agent_orchestrator import (
    OrchestrationManagerNode, IntelligentCacheNode
)

# API nodes
from kailash.nodes.api import HTTPRequestNode, RESTClientNode

# Transform & logic nodes
from kailash.nodes.transform import DataTransformerNode, FilterNode
from kailash.nodes.logic import SwitchNode, MergeNode, WorkflowNode
from kailash.nodes.code import PythonCodeNode

# Security
from kailash.security import (
    SecurityConfig, set_security_config, 
    validate_file_path, safe_open
)
from kailash.access_control import UserContext, PermissionRule

# API Gateway & MCP
from kailash.api.gateway import WorkflowAPIGateway
from kailash.api.mcp_integration import MCPIntegration
```

## Quick Workflow Creation

### Method 1: Direct Construction (Recommended)
```python
# Create workflow with ID and name
workflow = Workflow("wf-001", name="my_pipeline")

# Add nodes with CONFIGURATION parameters (static settings)
workflow.add_node("reader", CSVReaderNode(), file_path="input.csv")  # WHERE to read
workflow.add_node("processor", DataTransformerNode(),
    operations=[{"type": "filter", "condition": "age > 18"}]  # HOW to process
)
workflow.add_node("writer", CSVWriterNode(), file_path="output.csv")  # WHERE to write

# Connect nodes - RUNTIME data flows through these connections
workflow.connect("reader", "processor")  # Automatic mapping when names match
workflow.connect("processor", "writer", mapping={"transformed": "data"})  # Explicit mapping

# Execute with runtime (ALWAYS RECOMMENDED)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

# With parameter overrides
results, run_id = runtime.execute(workflow, parameters={
    "reader": {"file_path": "custom.csv"}  # Override at runtime
})

# Direct execution (less features, no tracking)
results = workflow.execute()  # Note: No 'inputs' parameter
```

### Method 2: Builder Pattern (Deprecated - Use Method 1)
```python
# NOTE: WorkflowBuilder can cause confusion. Prefer Workflow.connect() instead.
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

## Security Configuration

### Basic Security Setup
```python
from kailash.security import SecurityConfig, set_security_config

# Production security configuration
config = SecurityConfig(
    allowed_directories=["/app/data", "/tmp/kailash"],
    max_file_size=50 * 1024 * 1024,  # 50MB
    execution_timeout=60.0,  # 1 minute
    memory_limit=256 * 1024 * 1024,  # 256MB
    enable_audit_logging=True
)
set_security_config(config)
```

### Safe File Operations
```python
from kailash.security import safe_open, validate_file_path

# Validate file path before use
safe_path = validate_file_path("/app/data/file.txt")

# Safe file opening with automatic validation
with safe_open("data/file.txt", "r") as f:
    content = f.read()
```

### Secure Node Development
```python
from kailash.nodes.mixins import SecurityMixin
from kailash.nodes.base import Node

class MySecureNode(SecurityMixin, Node):
    def run(self, **kwargs):
        # Input is automatically sanitized
        safe_params = self.validate_and_sanitize_inputs(kwargs)
        return self.process_safely(safe_params)
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
workflow = Workflow("etl-001", name="etl_pipeline")

# Extract
workflow.add_node("extract", CSVReaderNode(), file_path="raw_data.csv")

# Transform
workflow.add_node("transform", DataTransformerNode(),
    operations=[
        {"type": "filter", "condition": "valid == True"},
        {"type": "map", "expression": "upper(name)"},
        {"type": "sort", "key": "timestamp"}
    ]
)

# Load
workflow.add_node("load", CSVWriterNode(), file_path="processed_data.csv")

# Connect pipeline
workflow.connect("extract", "transform")
workflow.connect("transform", "load")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)
```

### Hierarchical RAG Pipeline
```python
from kailash.nodes.data.sources import DocumentSourceNode, QuerySourceNode
from kailash.nodes.data.retrieval import RelevanceScorerNode
from kailash.nodes.transform.chunkers import HierarchicalChunkerNode
from kailash.nodes.transform.formatters import (
    ChunkTextExtractorNode, QueryTextWrapperNode, ContextFormatterNode
)

workflow = Workflow("rag-001", name="hierarchical_rag")

# Data sources
workflow.add_node("doc_source", DocumentSourceNode())
workflow.add_node("query_source", QuerySourceNode())

# Document processing
workflow.add_node("chunker", HierarchicalChunkerNode(), 
    chunk_size=1000, chunk_overlap=200)
workflow.add_node("chunk_text_extractor", ChunkTextExtractorNode())
workflow.add_node("query_wrapper", QueryTextWrapperNode())

# Embeddings
workflow.add_node("chunk_embedder", EmbeddingGeneratorNode(),
    provider="ollama", model="nomic-embed-text", operation="embed_batch")
workflow.add_node("query_embedder", EmbeddingGeneratorNode(),
    provider="ollama", model="nomic-embed-text", operation="embed_batch")

# Retrieval and generation
workflow.add_node("scorer", RelevanceScorerNode(), 
    similarity_method="cosine", top_k=5)
workflow.add_node("formatter", ContextFormatterNode())
workflow.add_node("llm", LLMAgentNode(),
    provider="ollama", model="llama3.2", temperature=0.7)

# Connect RAG pipeline
workflow.connect("doc_source", "chunker")
workflow.connect("chunker", "chunk_text_extractor")
workflow.connect("chunk_text_extractor", "chunk_embedder")
workflow.connect("query_source", "query_wrapper")
workflow.connect("query_wrapper", "query_embedder")
workflow.connect("chunker", "scorer", {"chunks": "chunks"})
workflow.connect("query_embedder", "scorer", {"embeddings": "query_embedding"})
workflow.connect("chunk_embedder", "scorer", {"embeddings": "chunk_embeddings"})
workflow.connect("scorer", "formatter")
workflow.connect("query_source", "formatter", {"query": "query"})
workflow.connect("formatter", "llm")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)
```

### Self-Organizing Agent Workflow
```python
workflow = Workflow("agents-001", name="self_organizing_research")

# Shared infrastructure
workflow.add_node("memory", SharedMemoryPoolNode(),
    memory_size_limit=1000, attention_window=50)
workflow.add_node("cache", IntelligentCacheNode(),
    ttl=3600, similarity_threshold=0.8)

# Problem analysis and team formation
workflow.add_node("analyzer", ProblemAnalyzerNode())
workflow.add_node("team_former", TeamFormationNode(),
    formation_strategy="capability_matching")

# Agent pool
workflow.add_node("pool", AgentPoolManagerNode(),
    max_active_agents=20, agent_timeout=120)

# Orchestration
workflow.add_node("orchestrator", OrchestrationManagerNode(),
    max_iterations=10, quality_threshold=0.85)

# Connect components
workflow.connect("orchestrator", "analyzer")
workflow.connect("analyzer", "team_former")
workflow.connect("team_former", "pool")

# Execute with complex problem
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "orchestrator": {
        "query": "Analyze market trends for fintech growth strategy",
        "agent_pool_size": 12,
        "context": {"domain": "fintech", "depth": "comprehensive"}
    }
})
```

### API Gateway for Multiple Workflows
```python
from kailash.api.gateway import WorkflowAPIGateway
from kailash.api.mcp_integration import MCPIntegration

# Create gateway
gateway = WorkflowAPIGateway(
    title="Enterprise Platform",
    description="Unified API for all workflows"
)

# Register workflows
gateway.register_workflow("sales", sales_workflow)
gateway.register_workflow("analytics", analytics_workflow)

# Add MCP tools
mcp = MCPIntegration("ai_tools")
mcp.add_tool("analyze", analyze_function)
gateway.register_mcp_server("ai", mcp)

# Run gateway
gateway.run(port=8000)

# Access endpoints:
# POST /sales/execute
# POST /analytics/execute
# GET /workflows
# GET /health
```

## SharePoint Integration
```python
import os
from kailash.nodes.data import SharePointGraphReader, SharePointGraphWriter

# Read from SharePoint
workflow.add_node("sharepoint_read", SharePointGraphReader(),
    tenant_id=os.getenv("SHAREPOINT_TENANT_ID"),
    client_id=os.getenv("SHAREPOINT_CLIENT_ID"),
    client_secret=os.getenv("SHAREPOINT_CLIENT_SECRET"),
    site_url="https://company.sharepoint.com/sites/Data",
    operation="list_files",
    library_name="Documents"
)

# Write to SharePoint
workflow.add_node("sharepoint_write", SharePointGraphWriter(),
    tenant_id=os.getenv("SHAREPOINT_TENANT_ID"),
    client_id=os.getenv("SHAREPOINT_CLIENT_ID"),
    client_secret=os.getenv("SHAREPOINT_CLIENT_SECRET"),
    site_url="https://company.sharepoint.com/sites/Data",
    library_name="Reports",
    file_path="output/report.xlsx"
)
```

## Access Control & Multi-Tenancy
```python
from kailash.access_control import UserContext
from kailash.runtime.access_controlled import AccessControlledRuntime

# Define user context
user = UserContext(
    user_id="user_001",
    tenant_id="company_abc",
    email="analyst@company.com",
    roles=["analyst", "viewer"]
)

# Create secure runtime
secure_runtime = AccessControlledRuntime(user_context=user)

# Execute with automatic permission checks
results, run_id = secure_runtime.execute(workflow)
```

## Workflow as REST API
```python
from kailash.api.workflow_api import WorkflowAPI

# Expose any workflow as REST API in 3 lines
api = WorkflowAPI(workflow)
api.run(port=8000)

# Endpoints created:
# POST /execute - Execute workflow
# GET /workflow/info - Get workflow metadata
# GET /health - Health check
# GET /docs - OpenAPI documentation
```

## Environment Variables
```python
# Common environment variables for API keys
os.environ["OPENAI_API_KEY"] = "your-key"
os.environ["ANTHROPIC_API_KEY"] = "your-key"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"

# SharePoint credentials
os.environ["SHAREPOINT_TENANT_ID"] = "your-tenant-id"
os.environ["SHAREPOINT_CLIENT_ID"] = "your-client-id"
os.environ["SHAREPOINT_CLIENT_SECRET"] = "your-secret"

# Use in node config
workflow.add_node("llm", LLMAgentNode(),
    provider="openai",
    model="gpt-4"
    # api_key will be read from OPENAI_API_KEY env var
)
```

## Quick Tips

1. **All node classes end with "Node"**: `CSVReaderNode` ✓, `CSVReader` ✗
2. **All methods use snake_case**: `add_node()` ✓, `addNode()` ✗
3. **All config keys use underscores**: `file_path` ✓, `filePath` ✗
4. **Always use runtime.execute()**: Returns (results, run_id) tuple
5. **Use parameters={} for overrides**: Not inputs={} or data={}
6. **Workflow needs ID and name**: `Workflow("id", name="name")`
7. **Prefer Workflow.connect()**: Avoid WorkflowBuilder confusion
8. **Validate before execution**: `workflow.validate()`
9. **Use environment variables**: For API keys and secrets
10. **Enable security in production**: Configure SecurityConfig

## Common Mistakes to Avoid

```python
# ❌ WRONG - Missing "Node" suffix
workflow.add_node("reader", CSVReader())

# ✅ CORRECT
workflow.add_node("reader", CSVReaderNode())

# ❌ WRONG - Wrong parameter name
runtime.execute(workflow, inputs={"data": [1,2,3]})

# ✅ CORRECT
runtime.execute(workflow, parameters={"node_id": {"data": [1,2,3]}})

# ❌ WRONG - Using camelCase
workflow.addNode("reader", node)

# ✅ CORRECT
workflow.add_node("reader", node)

# ❌ WRONG - Direct execution returns only results
results, run_id = workflow.execute()

# ✅ CORRECT - Runtime returns tuple
results, run_id = runtime.execute(workflow)
```
