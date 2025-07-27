# Common Workflow Patterns - Production Templates

## ETL Pipeline Pattern
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.transform import DataTransformerNode

workflow = WorkflowBuilder()

# Extract-Transform-Load
workflow.add_node("CSVReaderNode", "extract", {
    "file_path": "raw_data.csv"
})

workflow.add_node("DataTransformerNode", "transform", {
    "operations": [
        {"type": "filter", "condition": "status == 'active'"},
        {"type": "map", "expression": "{'id': id, 'name': name.upper()}"}
    ]
})

workflow.add_node("CSVWriterNode", "load", {
    "file_path": "processed.csv"
})

# Connect pipeline
workflow.add_connection("extract", "data", "transform", "input")
workflow.add_connection("transform", "transformed", "load", "data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

## AI Analysis Pattern
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

# LLM-powered data analysis
workflow = WorkflowBuilder()

# Read data
workflow.add_node("JSONReaderNode", "reader", {
    "file_path": "metrics.json"
})

# Process with Python - using string-based API
workflow.add_node("PythonCodeNode", "prepare", {
    "code": """
# Access data from the connected node's result
data = input_data.get('data', [])
result = {
    "summary": {
        "total_records": len(data),
        "avg_value": sum(d.get('value', 0) for d in data) / len(data) if data else 0,
        "categories": list(set(d.get('category') for d in data))
    },
    "raw_data": data
}
"""
})

# Analyze with LLM
workflow.add_node("LLMAgentNode", "analyze", {
    "provider": "openai",
    "model": "gpt-4",
    "prompt": "Analyze this data and provide insights: {summary}"
})

# Connect and execute
workflow.add_connection("reader", "data", "prepare", "data")
workflow.add_connection("prepare", "summary", "analyze", "summary")

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

### Boolean Conditional Routing
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Data source
workflow.add_node("PythonCodeNode", "check_stage", {
    "code": "result = {'is_initial_stage': True, 'message': 'Hello World'}"
})

# Conditional routing
workflow.add_node("SwitchNode", "stage_router", {
    "condition_field": "is_initial_stage",
    "operator": "==",
    "value": True
})

# True path - handles initial confirmation
workflow.add_node("PythonCodeNode", "handle_confirmation", {
    "code": "result = {'action': 'confirmation_handled', 'data': input_data}"
})

# False path - processes data differently
workflow.add_node("PythonCodeNode", "parse_data", {
    "code": "result = {'action': 'data_parsed', 'data': input_data}"
})

# Connect workflow - only ONE path will execute
workflow.add_connection("check_stage", "result", "stage_router", "input_data")
workflow.add_connection("stage_router", "true_output", "handle_confirmation", "input_data")
workflow.add_connection("stage_router", "false_output", "parse_data", "input_data")

# Execute - only handle_confirmation will run since is_initial_stage=True
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Multi-Case Conditional Routing
```python
workflow = WorkflowBuilder()

# Input data
workflow.add_node("PythonCodeNode", "data_source", {
    "code": "result = {'priority': 'high', 'task': 'urgent_task'}"
})

# Multi-case routing
workflow.add_node("SwitchNode", "priority_router", {
    "condition_field": "priority",
    "cases": ["high", "medium", "low"]
})

# Priority-specific handlers
workflow.add_node("PythonCodeNode", "handle_high", {
    "code": "result = {'handled_by': 'urgent_processor', 'data': input_data}"
})

workflow.add_node("PythonCodeNode", "handle_medium", {
    "code": "result = {'handled_by': 'standard_processor', 'data': input_data}"
})

workflow.add_node("PythonCodeNode", "handle_low", {
    "code": "result = {'handled_by': 'batch_processor', 'data': input_data}"
})

# Connect routes - only the matching case executes
workflow.add_connection("data_source", "result", "priority_router", "input_data")
workflow.add_connection("priority_router", "case_high", "handle_high", "input_data")
workflow.add_connection("priority_router", "case_medium", "handle_medium", "input_data")
workflow.add_connection("priority_router", "case_low", "handle_low", "input_data")

# Execute - only handle_high will run since priority='high'
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Advanced: LLM-Powered Conditional Processing
```python
workflow = WorkflowBuilder()

# Data classification
workflow.add_node("LLMAgentNode", "classifier", {
    "provider": "openai",
    "model": "gpt-4",
    "prompt": "Classify this request priority as 'high', 'medium', or 'low': {request}"
})

# Extract priority from LLM response
workflow.add_node("PythonCodeNode", "extract_priority", {
    "code": """
import json
priority = llm_response.get('content', '').strip().lower()
result = {'priority': priority, 'original': llm_response}
"""
})

# Route based on LLM classification
workflow.add_node("SwitchNode", "smart_router", {
    "condition_field": "priority",
    "cases": ["high", "medium", "low"]
})

# Different processing paths
workflow.add_node("PythonCodeNode", "urgent_processing", {
    "code": "result = {'status': 'processed_urgently', 'data': input_data}"
})

workflow.add_node("PythonCodeNode", "standard_processing", {
    "code": "result = {'status': 'processed_normally', 'data': input_data}"
})

# Connect intelligent routing
workflow.add_connection("classifier", "response", "extract_priority", "llm_response")
workflow.add_connection("extract_priority", "result", "smart_router", "input_data")
workflow.add_connection("smart_router", "case_high", "urgent_processing", "input_data")
workflow.add_connection("smart_router", "case_medium", "standard_processing", "input_data")
workflow.add_connection("smart_router", "case_low", "standard_processing", "input_data")
```

## Next Steps
- [RAG Guide](../developer/07-comprehensive-rag-guide.md) - RAG patterns
- [Production Workflows](../../workflows/) - Industry examples
- [Middleware Guide](../../middleware/) - Real-time features
