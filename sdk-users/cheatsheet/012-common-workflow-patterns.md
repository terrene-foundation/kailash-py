# Common Workflow Patterns - Production Templates

## ETL Pipeline Pattern
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.transform import DataTransformerNode

workflow = Workflow("etl-001", name="ETL Pipeline")

# Extract-Transform-Load
workflow.add_node("extract", CSVReaderNode(),
    file_path="raw_data.csv")

workflow.add_node("transform", DataTransformerNode(),
    operations=[
        {"type": "filter", "condition": "status == 'active'"},
        {"type": "map", "expression": "{'id': id, 'name': name.upper()}"}
    ])

workflow.add_node("load", CSVWriterNode(),
    file_path="processed.csv")

# Connect pipeline
workflow.connect("extract", "transform")
workflow.connect("transform", "load", mapping={"transformed": "data"})

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

```

## AI Analysis Pattern
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# LLM-powered data analysis
workflow = Workflow("ai-analysis", name="AI Data Analyst")

# Read data
workflow = Workflow("example", name="Example")
workflow.add_node("reader", JSONReaderNode(),
    file_path="metrics.json")

# Process with Python
workflow.add_node("prepare", PythonCodeNode.from_function(
    lambda data: {
    "summary": {
        "total_records": len(data),
        "avg_value": sum(d.get('value', 0) for d in data) / len(data),
        "categories": list(set(d.get('category') for d in data))
    },
    "raw_data": data
}
))

# Analyze with LLM
workflow = Workflow("example", name="Example")
workflow.add_node("analyze", LLMAgentNode(),
    provider="openai",
    model="gpt-4",
    prompt="Analyze this data and provide insights: {summary}")

# Connect and execute
workflow.connect("reader", "prepare")
workflow.connect("prepare", "analyze", mapping={"summary": "summary"})

```

## API Gateway Pattern
```python
from kailash.api.gateway import create_gateway

# Single function creates complete middleware stack
gateway = create_gateway(
    workflows={
        "sales": sales_workflow,
        "analytics": analytics_workflow,
        "reports": reporting_workflow
    },
    config={
        "enable_auth": True,
        "enable_monitoring": True,
        "enable_ai_chat": True,
        "enable_realtime": True
    }
)

# Run with full enterprise features
gateway.run(port=8000)

# Endpoints available:
# POST /api/{workflow_name}/execute
# GET /api/workflows
# WS /ws/realtime
# POST /api/chat

```

## Conditional Processing
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Route data based on conditions
workflow = Workflow("router", name="Conditional Router")

# Input and routing
workflow = Workflow("example", name="Example")
workflow.add_node("input", JSONReaderNode(), file_path="requests.json")
workflow = Workflow("example", name="Example")
workflow.add_node("router", SwitchNode(),
    conditions=[
        {"output": "urgent", "expression": "priority == 'high'"},
        {"output": "normal", "expression": "priority == 'medium'"},
        {"output": "batch", "expression": "priority == 'low'"}
    ])

# Different handlers
workflow = Workflow("example", name="Example")
workflow.add_node("urgent_handler", LLMAgentNode(),
    provider="openai", model="gpt-4", prompt="Process urgently: {data}")
workflow.add_node("normal_handler", DataTransformerNode())

# Connect routes
workflow.connect("input", "router")
workflow.connect("router", "urgent_handler", condition="urgent")
workflow.connect("router", "normal_handler", condition="normal")

```

## Next Steps
- [RAG Guide](../developer/07-comprehensive-rag-guide.md) - RAG patterns
- [Production Workflows](../../workflows/) - Industry examples
- [Middleware Guide](../../middleware/) - Real-time features
