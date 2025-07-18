# Nexus - Multi-Channel Platform

Nexus is a revolutionary platform that exposes workflows through API, CLI, and MCP interfaces from a single codebase. This guide is for users who have installed Nexus via PyPI.

## Installation

```bash
# Install Nexus directly
pip install kailash-nexus

# Or as part of Kailash SDK
pip install kailash[nexus]
```

## Quick Start

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

# Zero-configuration startup
app = Nexus()

# Create a workflow
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "process", {
    "code": """
# Process input data with the specified operation
input_data = parameters.get('input_data', [])
operation = parameters.get('operation', 'sum')

if operation == 'sum':
    result_value = sum(input_data)
elif operation == 'avg':
    result_value = sum(input_data) / len(input_data) if input_data else 0
else:
    result_value = len(input_data)

result = {
    'result': result_value,
    'operation': operation,
    'count': len(input_data)
}
"""
})

# Register workflow once
app.register("process_data", workflow)

# Start all channels
app.start()

# Now available as:
# - REST API: POST /workflows/process_data
# - CLI: nexus run process_data --input-data "[1,2,3]" --operation sum
# - MCP: AI agents can call process_data tool
```

## Key Features

### 🔄 Single Codebase → Multiple Channels
Register workflows once, automatically available as REST API, CLI commands, and MCP tools.

### 🎯 Zero Configuration
Start with `app = Nexus()` and `app.start()` - no routing, no CLI setup, no MCP server configuration.

### 🔐 Enterprise Orchestration
Multi-tenancy, RBAC, session management, and cross-channel synchronization built-in.

### 🤖 Real MCP Integration
AI agents can discover and execute your workflows as tools with full parameter validation.

## Multi-Channel Architecture

### REST API Channel
```bash
# Automatic REST endpoints
GET  /workflows                    # List all workflows
POST /workflows/{name}             # Execute workflow
GET  /workflows/{name}/info        # Workflow metadata
GET  /executions/{run_id}          # Execution status
GET  /docs                         # OpenAPI documentation
GET  /health                       # Health checks
```

### CLI Channel
```bash
# Automatic CLI commands
nexus list                              # List workflows
nexus run process_data --help          # Show workflow help
nexus run process_data --input-data "[1,2,3]"  # Execute workflow
nexus status {run_id}                   # Check execution status
nexus logs {run_id}                     # View execution logs
```

### MCP Channel
AI agents automatically discover workflows as tools with full parameter validation and documentation.

## Advanced Features

### Complex Workflow Registration
```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus(
    enable_auth=True,
    enable_monitoring=True,
    rate_limit=1000
)

# Register complex Kailash workflows
def create_analysis_workflow():
    workflow = WorkflowBuilder()
    workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
    workflow.add_node("LLMAgentNode", "analyzer", {
        "model": "gpt-4",
        "use_real_mcp": True,
        "prompt": "Analyze this data and provide insights"
    })
    workflow.add_connection("reader", "data", "analyzer", "input")
    return workflow

app.register("data_analysis", create_analysis_workflow())

# Fine-tune configuration
app.api.cors_enabled = True
app.api.docs_enabled = True
app.monitoring.interval = 30

app.start()
```

### Cross-Channel Session Management
```python
# Sessions persist across all channels
app = Nexus()

# Start workflow via API
response = requests.post("/workflows/process_data", json={...})
run_id = response.json()["run_id"]

# Check status via CLI
# nexus status {run_id}

# AI agents can also access execution results
# MCP tool: get_execution_result(run_id)
```

### Enterprise Authentication
```python
# Multi-channel authentication
app = Nexus(enable_auth=True)

# JWT tokens work across all channels
# API: Authorization: Bearer {token}
# CLI: nexus login --token {token}
# MCP: Authentication headers passed through
```

### Real-time Monitoring
```python
# Unified monitoring across channels
app = Nexus(enable_monitoring=True)

# WebSocket endpoints for real-time updates
# /ws/executions/{run_id}  - Real-time execution updates
# /ws/metrics              - Live platform metrics
# /ws/logs                 - Streaming logs
```

## Production Examples

### Data Processing Platform
```python
from nexus import Nexus
import pandas as pd

app = Nexus()

@app.workflow
def etl_pipeline(source_file: str, target_format: str = "csv") -> dict:
    """ETL pipeline for data transformation."""
    # Load data
    df = pd.read_csv(source_file)

    # Transform
    df["processed_at"] = pd.Timestamp.now()
    df = df.dropna()

    # Save
    output_file = f"processed_{source_file.split('/')[-1]}"
    if target_format == "csv":
        df.to_csv(output_file, index=False)
    elif target_format == "json":
        df.to_json(output_file, orient="records")

    return {
        "input_rows": len(df),
        "output_file": output_file,
        "format": target_format
    }

app.start()
```

### AI Agent Orchestration
```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

# Create AI analysis workflow
ai_workflow = WorkflowBuilder()

# Sentiment analysis branch
ai_workflow.add_node("SwitchNode", "router", {
    "condition": "parameters.analysis_type"
})

ai_workflow.add_node("LLMAgentNode", "sentiment_analyzer", {
    "model": "gpt-4",
    "system_prompt": "Analyze sentiment of the provided text.",
    "prompt": "{{text}}"
})

ai_workflow.add_node("LLMAgentNode", "summarizer", {
    "model": "gpt-4",
    "system_prompt": "Provide a concise summary of the text.",
    "prompt": "{{text}}"
})

# Route based on analysis type
ai_workflow.add_connection("router", "sentiment", "sentiment_analyzer", when="sentiment")
ai_workflow.add_connection("router", "summarize", "summarizer", when="summarize")

# Register workflow
app.register("ai_analysis", ai_workflow)

app.start()
```

### Enterprise Workflow Hub
```python
from nexus import Nexus

app = Nexus(
    enable_auth=True,
    enable_monitoring=True,
    rate_limit=500
)

# Register multiple enterprise workflows
workflows = {
    "customer_onboarding": create_onboarding_workflow(),
    "fraud_detection": create_fraud_workflow(),
    "risk_assessment": create_risk_workflow(),
    "compliance_check": create_compliance_workflow()
}

for name, workflow in workflows.items():
    app.register(name, workflow)

# Enterprise features
app.enable_audit_logging()
app.enable_rate_limiting()
app.start()
```

## Revolutionary Capabilities

### Durable-First Design
```python
from kailash.workflow.builder import WorkflowBuilder

# Every request is resumable from checkpoints
app = Nexus(enable_durability=True)

# Create durable workflow
durable_workflow = WorkflowBuilder()

# Process with checkpoints
durable_workflow.add_node("PythonCodeNode", "batch_processor", {
    "code": """
import json

# Get checkpoint state if resuming
checkpoint = parameters.get('checkpoint', {})
start_index = checkpoint.get('progress', 0)
processed_results = checkpoint.get('results', [])

# Process data in batches
data = parameters['data']
for i in range(start_index, len(data)):
    item = data[i]

    # Process item
    result = {'item': item, 'processed': True, 'index': i}
    processed_results.append(result)

    # Checkpoint every 10 items
    if i % 10 == 0 and i > 0:
        checkpoint_data = {
            'progress': i,
            'results': processed_results
        }
        # In real implementation, this would persist to durable storage

result = {
    'total_processed': len(processed_results),
    'results': processed_results
}
"""
})

app.register("long_running_process", durable_workflow)
```

### Event-Driven Communication
```python
# Real-time events across all channels
@app.event("workflow_completed")
def on_completion(event):
    # Notify all connected clients
    app.broadcast({
        "type": "completion",
        "workflow": event["workflow_name"],
        "result": event["result"]
    })

# WebSocket: Real-time updates in web UI
# CLI: Live progress updates
# MCP: AI agents receive completion events
```

## Performance & Benchmarks

- **API Requests**: 10,000+ concurrent requests
- **CLI Commands**: Sub-second execution for simple workflows
- **MCP Tools**: 100+ simultaneous AI agent connections
- **Cross-Channel Sync**: <50ms session synchronization

### Performance Monitoring
```python
# Built-in performance monitoring
print(app.get_performance_metrics())
# {
#   "workflow_registration_time": {"average": 0.045, "target_met": True},
#   "cross_channel_sync_time": {"average": 0.032, "target_met": True},
#   "session_sync_latency": {"average": 0.028, "target_met": True}
# }
```

## Enterprise Features

### Multi-Tenant Architecture
```python
# Complete tenant isolation
app = Nexus(multi_tenant=True)

# All channels respect tenant boundaries
# API: X-Tenant-ID header
# CLI: --tenant flag
# MCP: Tenant context in tool calls
```

### Security & Compliance
```python
# Enterprise security patterns
app = Nexus()
app.enable_auth()              # JWT authentication
app.enable_rate_limiting()     # DDoS protection
app.enable_audit_logging()     # Compliance trails
app.enable_threat_detection()  # Behavior analysis
```

### Health Monitoring
```python
# Comprehensive health checks
health = app.health_check()
# {
#   "status": "healthy",
#   "platform_type": "multi-channel",
#   "channels": {"api": "active", "cli": "active", "mcp": "active"},
#   "workflows": 5,
#   "enterprise_features": {...}
# }
```

## Deployment

### Docker
```dockerfile
FROM python:3.11-slim
RUN pip install kailash-nexus
COPY app.py .
EXPOSE 8000 3001
CMD ["python", "app.py"]
```

### Environment Variables
```bash
export NEXUS_API_PORT=8000
export NEXUS_MCP_PORT=3001
export NEXUS_ENABLE_AUTH=true
export NEXUS_ENABLE_MONITORING=true
export NEXUS_RATE_LIMIT=1000
```

## Migration Guide

### From FastAPI
```python
# Before: FastAPI
from fastapi import FastAPI
app = FastAPI()

@app.post("/process")
def process_data(data: list):
    return {"result": sum(data)}

# After: Nexus (adds CLI + MCP automatically)
from nexus import Nexus
app = Nexus()

@app.workflow
def process_data(data: list) -> dict:
    return {"result": sum(data)}
```

### From Click CLI
```python
# Before: Click CLI
import click

@click.command()
@click.option('--data', multiple=True)
def process(data):
    result = sum(int(x) for x in data)
    print(f"Result: {result}")

# After: Nexus (adds API + MCP automatically)
from nexus import Nexus
app = Nexus()

@app.workflow
def process_data(data: list) -> dict:
    return {"result": sum(data)}
```

## Additional Documentation

### Guides
- [Implementation Guide](docs/IMPLEMENTATION_GUIDE.md) - Comprehensive Nexus implementation guide
- [Quick Start Guide](docs/quick-start.md) - Get started in minutes
- [Multi-Channel Usage](docs/multi-channel-usage.md) - API, CLI, and MCP patterns
- [Revolutionary Capabilities](docs/revolutionary-capabilities.md) - Advanced features
- [API Reference](docs/api-reference.md) - Complete API documentation
- [Production Deployment](docs/production-deployment.md) - Deployment best practices

### Examples
- [Basic Usage](examples/basic_usage.py) - Simple workflow registration
- [FastAPI Style Patterns](examples/fastapi_style_patterns.py) - Migration from FastAPI

## Next Steps

- Explore the documentation and examples above
- Read the [API documentation](https://pypi.org/project/kailash-nexus/)
- Join the [community](https://github.com/terrene-foundation/kailash-py)

Nexus eliminates the traditional need to build separate APIs, CLI tools, and AI agent integrations. Register once, deploy everywhere!
