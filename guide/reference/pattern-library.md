# Kailash Python SDK - Pattern Library

Last Updated: 2025-06-04

This pattern library documents common workflow patterns, best practices, and design patterns for building effective workflows with the Kailash Python SDK.

## Table of Contents
- [Core Patterns](#core-patterns)
- [Control Flow Patterns](#control-flow-patterns)
- [Data Processing Patterns](#data-processing-patterns)
- [Integration Patterns](#integration-patterns)
- [Error Handling Patterns](#error-handling-patterns)
- [Performance Patterns](#performance-patterns)
- [Composition Patterns](#composition-patterns)
- [Deployment Patterns](#deployment-patterns)
- [Best Practices](#best-practices)

## Core Patterns

### 1. Linear Pipeline Pattern (ETL)
**Purpose**: Sequential data processing from source to destination

```python
from kailash.workflow import Workflow
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.writers import JSONWriterNode

workflow = Workflow()

# Add nodes
reader = CSVReaderNode(config={"file_path": "input.csv"})
transformer = PythonCodeNode(
    config={
        "code": """
result = []
for row in data:
    row['processed'] = True
    result.append(row)
""",
        "imports": []
    }
)
writer = JSONWriterNode(config={"file_path": "output.json"})

workflow.add_node("reader", reader)
workflow.add_node("transformer", transformer)
workflow.add_node("writer", writer)

# Connect in sequence
workflow.connect("reader", "transformer")
workflow.connect("transformer", "writer")
```

**Use Cases**:
- Data migration
- Report generation
- Batch processing

### 2. Direct Node Execution Pattern
**Purpose**: Quick operations without workflow orchestration

```python
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import JSONWriterNode

# Direct execution
csv_reader = CSVReaderNode(config={"file_path": "data.csv"})
data = csv_reader.execute()

# Process data
processed_data = [{"id": row["id"], "name": row["name"].upper()} 
                  for row in data["data"]]

# Write results
json_writer = JSONWriterNode(config={"file_path": "output.json"})
json_writer.execute(data=processed_data)
```

**Use Cases**:
- Prototyping
- Simple scripts
- One-off operations

## Control Flow Patterns

### 3. Conditional Routing Pattern
**Purpose**: Route data based on conditions

```python
from kailash.workflow import Workflow
from kailash.nodes.logic.operations import SwitchNode, MergeNode
from kailash.runtime import LocalRuntime

workflow = Workflow()

# Switch node for routing
switch = SwitchNode(
    config={
        "condition": "status",
        "outputs": {
            "completed": "status == 'completed'",
            "pending": "status == 'pending'",
            "failed": "status == 'failed'"
        }
    }
)

# Different processing paths
completed_processor = PythonCodeNode(
    config={"code": "result = 'Archived: ' + str(data)"}
)
pending_processor = PythonCodeNode(
    config={"code": "result = 'Queue for retry: ' + str(data)"}
)
failed_processor = PythonCodeNode(
    config={"code": "result = 'Send to error queue: ' + str(data)"}
)

# Merge results
merger = MergeNode(config={"merge_strategy": "concat"})

# Build workflow
workflow.add_node("router", switch)
workflow.add_node("process_completed", completed_processor)
workflow.add_node("process_pending", pending_processor)
workflow.add_node("process_failed", failed_processor)
workflow.add_node("merger", merger)

# Connect conditional paths
workflow.connect("router", "process_completed", "completed")
workflow.connect("router", "process_pending", "pending")
workflow.connect("router", "process_failed", "failed")
workflow.connect("process_completed", "merger")
workflow.connect("process_pending", "merger")
workflow.connect("process_failed", "merger")
```

**Use Cases**:
- Status-based processing
- Error routing
- A/B testing

### 4. Multi-Level Routing Pattern
**Purpose**: Complex decision trees with nested conditions

```python
# First level: Status routing
status_switch = SwitchNode(
    config={
        "condition": "status",
        "outputs": ["active", "inactive"]
    }
)

# Second level: Tier routing for active customers
tier_switch = SwitchNode(
    config={
        "condition": "tier",
        "outputs": ["gold", "silver", "bronze"]
    }
)

# Connect nested routing
workflow.connect("status_router", "tier_router", "active")
workflow.connect("tier_router", "gold_processor", "gold")
workflow.connect("tier_router", "silver_processor", "silver")
workflow.connect("tier_router", "bronze_processor", "bronze")
```

## Data Processing Patterns

### 5. Parallel Processing Pattern
**Purpose**: Process multiple data streams concurrently

```python
from kailash.workflow import Workflow
from kailash.runtime import ParallelRuntime
from kailash.nodes.base_async import AsyncNode
from kailash.nodes.logic.async_operations import AsyncMergeNode

workflow = Workflow()

# Multiple async data sources
source1 = AsyncHTTPRequestNode(
    config={"url": "https://api1.example.com/data"}
)
source2 = AsyncHTTPRequestNode(
    config={"url": "https://api2.example.com/data"}
)
source3 = AsyncHTTPRequestNode(
    config={"url": "https://api3.example.com/data"}
)

# Async merge
merger = AsyncMergeNode(
    config={
        "merge_strategy": "dict_merge",
        "wait_for_all": True
    }
)

# Add nodes
workflow.add_node("source1", source1)
workflow.add_node("source2", source2)
workflow.add_node("source3", source3)
workflow.add_node("merger", merger)

# Connect all sources to merger
workflow.connect("source1", "merger")
workflow.connect("source2", "merger")
workflow.connect("source3", "merger")

# Execute with parallel runtime
runtime = ParallelRuntime()
result = await runtime.execute(workflow)
```

**Use Cases**:
- Multi-source data aggregation
- Parallel API calls
- Distributed processing

### 6. Batch Processing Pattern
**Purpose**: Process large datasets in chunks

```python
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.code.python import PythonCodeNode

# Batch processor node
batch_processor = PythonCodeNode(
    config={
        "code": """
import pandas as pd

# Process in batches
batch_size = 1000
results = []

for i in range(0, len(data), batch_size):
    batch = data[i:i+batch_size]
    # Process batch
    processed_batch = [process_record(r) for r in batch]
    results.extend(processed_batch)

result = results
""",
        "imports": ["pandas"]
    }
)
```

**Use Cases**:
- Large file processing
- Memory-efficient operations
- Stream processing

## Integration Patterns

### 7. API Gateway Pattern
**Purpose**: Unified interface for multiple workflows

```python
from kailash.api.gateway import WorkflowGateway
from kailash.api.workflow_api import WorkflowAPI

# Create gateway
gateway = WorkflowGateway(port=8000)

# Register multiple workflows
gateway.register_workflow("data_processing", data_workflow)
gateway.register_workflow("ml_pipeline", ml_workflow)
gateway.register_workflow("report_generation", report_workflow)

# Add middleware
gateway.add_middleware(AuthenticationMiddleware())
gateway.add_middleware(RateLimitingMiddleware())

# Start gateway
gateway.start()
```

**Use Cases**:
- Microservices architecture
- Multi-tenant systems
- API-first design

### 8. External Service Integration Pattern
**Purpose**: Integrate with external APIs and services

```python
from kailash.nodes.api.rest import RESTClientNode
from kailash.nodes.api.auth import OAuth2Node

# OAuth authentication
auth_node = OAuth2Node(
    config={
        "client_id": "your_client_id",
        "client_secret": "your_secret",
        "token_url": "https://auth.example.com/token"
    }
)

# API client with auth
api_client = RESTClientNode(
    config={
        "base_url": "https://api.example.com",
        "headers": {"Authorization": "Bearer {token}"},
        "rate_limit": 100,  # requests per minute
        "retry_count": 3
    }
)

# Connect auth to API client
workflow.connect("auth", "api_client")
```

**Use Cases**:
- Third-party integrations
- Cloud service connections
- External data sources

## Error Handling Patterns

### 9. Circuit Breaker Pattern
**Purpose**: Prevent cascading failures

```python
from kailash.nodes.code.python import PythonCodeNode

circuit_breaker = PythonCodeNode(
    config={
        "code": """
import time

# Circuit breaker state
if not hasattr(self, '_failures'):
    self._failures = 0
    self._last_failure = 0
    self._circuit_open = False

# Check circuit state
if self._circuit_open:
    if time.time() - self._last_failure > 60:  # 1 minute timeout
        self._circuit_open = False
        self._failures = 0
    else:
        result = {"error": "Circuit breaker is open"}
        return result

try:
    # Attempt operation
    result = perform_operation(data)
    self._failures = 0
except Exception as e:
    self._failures += 1
    self._last_failure = time.time()
    
    if self._failures >= 5:
        self._circuit_open = True
    
    result = {"error": str(e), "failures": self._failures}
""",
        "imports": ["time"]
    }
)
```

**Use Cases**:
- External API calls
- Database connections
- Network operations

### 10. Retry with Backoff Pattern
**Purpose**: Resilient error recovery

```python
retry_node = PythonCodeNode(
    config={
        "code": """
import time
import random

max_retries = 3
base_delay = 1.0

for attempt in range(max_retries):
    try:
        result = perform_operation(data)
        break
    except Exception as e:
        if attempt == max_retries - 1:
            raise
        
        # Exponential backoff with jitter
        delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
        time.sleep(delay)
""",
        "imports": ["time", "random"]
    }
)
```

## Performance Patterns

### 11. Caching Pattern
**Purpose**: Reduce redundant computations

```python
from kailash.nodes.code.python import PythonCodeNode

caching_node = PythonCodeNode(
    config={
        "code": """
import hashlib
import json

# Simple in-memory cache
if not hasattr(self, '_cache'):
    self._cache = {}

# Generate cache key
cache_key = hashlib.md5(
    json.dumps(data, sort_keys=True).encode()
).hexdigest()

# Check cache
if cache_key in self._cache:
    result = self._cache[cache_key]
else:
    # Compute result
    result = expensive_computation(data)
    self._cache[cache_key] = result

# Optional: Cache eviction
if len(self._cache) > 1000:
    # Remove oldest entries
    self._cache = dict(list(self._cache.items())[-500:])
""",
        "imports": ["hashlib", "json"]
    }
)
```

**Use Cases**:
- Expensive computations
- API responses
- Database queries

### 12. Stream Processing Pattern
**Purpose**: Process data as it arrives

```python
from kailash.nodes.data.streaming import EventStreamNode
from kailash.nodes.code.python import PythonCodeNode

# Stream consumer
stream_consumer = EventStreamNode(
    config={
        "stream_url": "ws://stream.example.com",
        "event_types": ["data_update", "status_change"]
    }
)

# Stream processor
stream_processor = PythonCodeNode(
    config={
        "code": """
# Process each event as it arrives
if event_type == 'data_update':
    result = process_data_update(data)
elif event_type == 'status_change':
    result = handle_status_change(data)
else:
    result = data
""",
        "imports": []
    }
)

workflow.connect("stream_consumer", "stream_processor")
```

## Composition Patterns

### 13. Nested Workflow Pattern
**Purpose**: Reuse workflows as components

```python
from kailash.workflow import Workflow
from kailash.nodes.logic.workflow import WorkflowNode

# Main workflow
main_workflow = Workflow()

# Sub-workflow as a node
data_prep_node = WorkflowNode(
    config={
        "workflow_path": "workflows/data_preparation.yaml",
        "input_mapping": {
            "raw_data": "data"
        },
        "output_mapping": {
            "cleaned_data": "data"
        }
    }
)

ml_pipeline_node = WorkflowNode(
    config={
        "workflow_path": "workflows/ml_pipeline.yaml"
    }
)

# Compose workflows
main_workflow.add_node("data_prep", data_prep_node)
main_workflow.add_node("ml_pipeline", ml_pipeline_node)
main_workflow.connect("data_prep", "ml_pipeline")
```

**Use Cases**:
- Modular design
- Workflow reuse
- Complex orchestration

### 14. Dynamic Workflow Generation Pattern
**Purpose**: Create workflows programmatically

```python
def create_processing_workflow(steps):
    """Dynamically create workflow based on configuration"""
    workflow = Workflow()
    
    previous_node = None
    for i, step in enumerate(steps):
        node_id = f"step_{i}"
        
        # Create node based on step type
        if step["type"] == "transform":
            node = PythonCodeNode(config={"code": step["code"]})
        elif step["type"] == "filter":
            node = PythonCodeNode(
                config={"code": f"result = [r for r in data if {step['condition']}]"}
            )
        elif step["type"] == "aggregate":
            node = PythonCodeNode(
                config={"code": step["aggregation_code"]}
            )
        
        workflow.add_node(node_id, node)
        
        if previous_node:
            workflow.connect(previous_node, node_id)
        
        previous_node = node_id
    
    return workflow

# Create custom workflow
steps = [
    {"type": "filter", "condition": "r['age'] > 18"},
    {"type": "transform", "code": "result = [{'name': r['name'].upper()} for r in data]"},
    {"type": "aggregate", "aggregation_code": "result = len(data)"}
]

dynamic_workflow = create_processing_workflow(steps)
```

## Deployment Patterns

### 15. Export Pattern
**Purpose**: Export workflows for different environments

```python
from kailash.utils.export import WorkflowExporter

exporter = WorkflowExporter(workflow)

# Export to different formats
exporter.to_yaml("workflow.yaml")
exporter.to_json("workflow.json")
exporter.to_docker("./docker-export")
exporter.to_kubernetes("./k8s-manifests")

# With custom configuration
export_config = {
    "include_dependencies": True,
    "version": "1.0.0",
    "metadata": {
        "author": "team@example.com",
        "description": "Data processing pipeline"
    }
}

exporter.to_yaml("workflow.yaml", config=export_config)
```

### 16. Configuration Management Pattern
**Purpose**: Separate configuration from code

```python
import yaml

# Load configuration
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

# Create workflow with configuration
workflow = Workflow()

for node_config in config["nodes"]:
    node_class = globals()[node_config["type"]]
    node = node_class(config=node_config["config"])
    workflow.add_node(node_config["id"], node)

for connection in config["connections"]:
    workflow.connect(
        connection["from"],
        connection["to"],
        connection.get("output_key")
    )
```

## Best Practices

### 1. Node Design
- **Single Responsibility**: Each node should do one thing well
- **Clear Interfaces**: Define explicit input/output schemas
- **Error Handling**: Handle errors gracefully with meaningful messages
- **Documentation**: Include docstrings with examples

### 2. Workflow Design
- **Modularity**: Build small, reusable workflows
- **Composition**: Combine simple workflows for complex tasks
- **Validation**: Always validate workflows before execution
- **Testing**: Test workflows with edge cases

### 3. Performance
- **Async Operations**: Use async nodes for I/O operations
- **Batch Processing**: Process data in chunks for large datasets
- **Caching**: Cache expensive computations
- **Parallel Execution**: Use parallel runtime for independent operations

### 4. Error Handling
- **Fail Fast**: Validate inputs early
- **Graceful Degradation**: Continue with partial data when possible
- **Retry Logic**: Implement smart retry with backoff
- **Monitoring**: Log errors and track failures

### 5. Code Organization
```python
# Good: Clear, self-documenting workflow
workflow = Workflow()

# Data ingestion phase
csv_reader = CSVReaderNode(config={"file_path": "customers.csv"})
data_validator = PythonCodeNode(config={
    "code": "result = validate_customer_data(data)"
})
workflow.add_node("read_customers", csv_reader)
workflow.add_node("validate_data", data_validator)
workflow.connect("read_customers", "validate_data")

# Processing phase
enrichment = PythonCodeNode(config={
    "code": "result = enrich_customer_data(data)"
})
workflow.add_node("enrich_data", enrichment)
workflow.connect("validate_data", "enrich_data")
```

### 6. Testing Patterns
```python
from kailash.runtime.testing import TestRuntime

# Unit test individual nodes
def test_data_processor():
    node = DataProcessorNode(config={"threshold": 10})
    test_data = {"value": 15}
    result = node.execute(data=test_data)
    assert result["passed"] == True

# Integration test workflows
def test_workflow():
    runtime = TestRuntime()
    test_input = {"customers": [...]}
    result = runtime.execute(workflow, parameters=test_input)
    assert len(result["processed_customers"]) > 0
```

## Pattern Selection Guide

| Use Case | Recommended Pattern |
|----------|-------------------|
| Simple ETL | Linear Pipeline |
| Quick scripts | Direct Node Execution |
| Business rules | Conditional Routing |
| Multiple data sources | Parallel Processing |
| External APIs | Integration + Error Handling |
| Large datasets | Batch/Stream Processing |
| Microservices | API Gateway |
| Complex orchestration | Nested Workflows |
| Production deployment | Export + Config Management |

## See Also
- [Node Catalog](node-catalog.md) - Complete node reference
- [API Registry](api-registry.yaml) - API specifications
- [Validation Guide](validation-guide.md) - Code validation rules