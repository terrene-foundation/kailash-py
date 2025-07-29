# Creating Your First Workflow

Learn how to build and deploy your first workflow with Nexus in minutes.

## Overview

This guide walks you through creating a complete workflow from scratch, demonstrating Nexus's revolutionary workflow-native architecture. You'll learn how a single workflow registration automatically exposes API endpoints, CLI commands, and MCP tools.

## Prerequisites

- Nexus installed (see [Installation Guide](installation.md))
- Basic Python knowledge
- 5 minutes of your time

## Your First Workflow

### Step 1: Basic Workflow Creation

Create a simple data processing workflow:

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

# Create Nexus instance
app = Nexus()

# Build your first workflow
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "fetch", {
    "url": "https://httpbin.org/json",
    "method": "GET"
})
workflow.add_node("JSONReaderNode", "parse", {})
workflow.add_connection("fetch", "parse", "response", "input")

# Register workflow (automatically creates API, CLI, and MCP interfaces)
app.register("my-first-workflow", workflow)

# Start the platform
app.start()
```

### Step 2: Test Your Workflow

Once started, your workflow is automatically available through multiple channels:

**API Access:**
```bash
curl -X POST http://localhost:8000/workflows/my-first-workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"inputs": {}}'
```

**Health Check:**
```bash
curl http://localhost:8000/health
```

### Step 3: Interactive Testing

Create a test script to validate your workflow:

```python
import requests
import time

# Wait for server to start
time.sleep(2)

# Test workflow execution
response = requests.post(
    "http://localhost:8000/workflows/my-first-workflow/execute",
    json={"inputs": {}}
)

print(f"Status: {response.status_code}")
print(f"Result: {response.json()}")
```

## Real-World Example: Data Pipeline

Let's create a more comprehensive workflow that demonstrates practical patterns:

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus(api_port=8001)

# Build data processing pipeline
pipeline = WorkflowBuilder()

# Fetch data from API
pipeline.add_node("HTTPRequestNode", "fetch_data", {
    "url": "https://jsonplaceholder.typicode.com/posts/1",
    "method": "GET",
    "headers": {"Accept": "application/json"}
})

# Parse JSON response
pipeline.add_node("JSONReaderNode", "parse_json", {})

# Transform data with Python logic
pipeline.add_node("PythonCodeNode", "transform", {
    "code": """
def transform_data(data):
    result = data.copy()
    result['processed_at'] = '2024-01-01T00:00:00Z'
    result['word_count'] = len(result.get('body', '').split())
    return result
    """
})

# Connect the pipeline
pipeline.add_connection("fetch_data", "parse_json", "response", "input")
pipeline.add_connection("parse_json", "transform", "output", "data")

# Register as enterprise workflow
app.register("data-pipeline", pipeline)

# Start with enterprise features
app.start()
```

### Testing the Pipeline

```python
import requests
import json

def test_data_pipeline():
    """Test the data processing pipeline"""

    # Execute workflow
    response = requests.post(
        "http://localhost:8001/workflows/data-pipeline/execute",
        json={"inputs": {}}
    )

    if response.status_code == 200:
        result = response.json()

        # Verify transformation
        if 'processed_at' in result and 'word_count' in result:
            print("✅ Pipeline executed successfully!")
            print(f"Word count: {result['word_count']}")
        else:
            print("❌ Transformation failed")
    else:
        print(f"❌ Request failed: {response.status_code}")

# Run test
test_data_pipeline()
```

## Multi-Channel Access

Your workflow is now available through all channels:

### 1. REST API
```bash
# Execute workflow
curl -X POST http://localhost:8001/workflows/data-pipeline/execute

# Get workflow schema
curl http://localhost:8001/workflows/data-pipeline/schema

# Health check
curl http://localhost:8001/health
```

### 2. CLI Interface (when implemented)
```bash
# Execute via CLI
nexus run data-pipeline

# List workflows
nexus list

# Get workflow info
nexus info data-pipeline
```

### 3. MCP Protocol (for AI agents)
Your workflow automatically becomes available as MCP tools for AI agents to discover and execute.

## Advanced Features

### Error Handling

Add robust error handling to your workflows:

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus(api_port=8002)

# Resilient workflow with error handling
workflow = WorkflowBuilder()

# Add error handling node
workflow.add_node("HTTPRequestNode", "api_call", {
    "url": "https://httpbin.org/status/200",
    "method": "GET",
    "timeout": 30,
    "retry_count": 3
})

# Add validation
workflow.add_node("SwitchNode", "validate", {
    "conditions": [
        {"field": "status_code", "operator": "eq", "value": 200}
    ]
})

# Success path
workflow.add_node("JSONReaderNode", "process_success", {})

# Error path
workflow.add_node("PythonCodeNode", "handle_error", {
    "code": """
def handle_error(data):
    return {
        'error': True,
        'status': data.get('status_code', 'unknown'),
        'message': 'API call failed'
    }
    """
})

# Connect with conditional logic
workflow.add_connection("api_call", "response", "validate", "input_data")
workflow.add_connection("validate", "true_output", "process_success", "input")
workflow.add_connection("validate", "false_output", "handle_error", "input")

app.register("resilient-workflow", workflow)
app.start()
```

### Testing Error Handling

```python
import requests

def test_error_handling():
    """Test workflow error handling"""

    # Test success case
    response = requests.post(
        "http://localhost:8002/workflows/resilient-workflow/execute",
        json={"inputs": {}}
    )

    result = response.json()
    print(f"Result: {result}")

    if 'error' in result:
        print(f"Error handled: {result['message']}")
    else:
        print("✅ Workflow completed successfully")

test_error_handling()
```

## Performance Optimization

Monitor and optimize your workflow performance:

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time

app = Nexus(api_port=8003)

# Performance-optimized workflow
workflow = WorkflowBuilder()

# Add performance monitoring
workflow.add_node("PythonCodeNode", "start_timer", {
    "code": """
import time
def start_timer(data):
    return {'start_time': time.time(), 'input': data}
    """
})

# Main processing
workflow.add_node("HTTPRequestNode", "process", {
    "url": "https://httpbin.org/delay/1",
    "method": "GET"
})

# End timing
workflow.add_node("PythonCodeNode", "end_timer", {
    "code": """
import time
def end_timer(data):
    end_time = time.time()
    start_time = data.get('start_time', end_time)
    return {
        'duration_ms': (end_time - start_time) * 1000,
        'result': data,
        'performance': 'measured'
    }
    """
})

# Connect performance pipeline
workflow.add_connection("start_timer", "process", "output", "input")
workflow.add_connection("process", "end_timer", "response", "input")

app.register("performance-workflow", workflow)
app.start()
```

## Next Steps

Now that you've created your first workflow, explore these advanced topics:

1. **[Basic Usage](basic-usage.md)** - Learn core Nexus patterns
2. **[Multi-Channel Usage](../user-guides/multi-channel-usage.md)** - Master all three channels
3. **[Enterprise Features](../user-guides/enterprise-features.md)** - Production capabilities
4. **[Architecture Overview](../technical/architecture-overview.md)** - Understand the revolutionary design

## Key Takeaways

✅ **Single Registration** → Multiple interfaces (API, CLI, MCP)
✅ **Zero Configuration** → Production-ready by default
✅ **Enterprise Features** → Built-in durability, monitoring, security
✅ **Revolutionary Architecture** → Workflow-native vs request-response

Your first workflow demonstrates Nexus's core innovation: **workflow-native orchestration** that automatically provides multi-channel access with enterprise capabilities enabled by default.
