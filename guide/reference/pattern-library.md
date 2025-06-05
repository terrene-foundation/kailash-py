# Kailash Python SDK - Pattern Library

Last Updated: 2025-06-05

This pattern library documents common workflow patterns, best practices, and design patterns for building effective workflows with the Kailash Python SDK.

## Table of Contents
- [Core Patterns](#core-patterns)
- [Control Flow Patterns](#control-flow-patterns)
- [Data Processing Patterns](#data-processing-patterns)
- [Integration Patterns](#integration-patterns)
- [Error Handling Patterns](#error-handling-patterns)
- [Performance Patterns](#performance-patterns)
- [Composition Patterns](#composition-patterns)
- [Self-Organizing Agent Patterns](#self-organizing-agent-patterns)
- [Deployment Patterns](#deployment-patterns)
- [Security Patterns](#security-patterns)
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

## Self-Organizing Agent Patterns

### 15. Basic Self-Organizing Agent Pool Pattern
**Purpose**: Create autonomous agent teams that solve problems collaboratively

```python
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.ai.intelligent_agent_orchestrator import (
    OrchestrationManagerNode, IntelligentCacheNode
)
from kailash.nodes.ai.a2a import SharedMemoryPoolNode

workflow = Workflow()

# Shared infrastructure
memory = workflow.add_node(SharedMemoryPoolNode(name="memory"))
cache = workflow.add_node(IntelligentCacheNode(name="cache", ttl=3600))

# Orchestration with self-organization
orchestrator = workflow.add_node(OrchestrationManagerNode(
    name="orchestrator",
    max_iterations=5,
    quality_threshold=0.8,
    time_limit_minutes=10
))

# Execute with MCP servers
runtime = LocalRuntime()
result, _ = runtime.execute(workflow, parameters={
    "orchestrator": {
        "query": "Analyze market trends and recommend strategy",
        "mcp_servers": [
            {"name": "market_data", "command": "market-mcp"},
            {"name": "financial", "command": "finance-mcp"}
        ],
        "agent_pool_size": 10
    }
})
```

**Use Cases**:
- Research and analysis
- Strategic planning
- Complex problem solving

### 16. MCP-Enhanced Agent Pattern
**Purpose**: Agents with external tool access via MCP

```python
from kailash.nodes.ai.intelligent_agent_orchestrator import MCPAgentNode

# Create specialized agents with MCP access
research_agent = workflow.add_node(MCPAgentNode(
    name="research_agent",
    mcp_server="research_tools",
    capabilities=["research", "analysis", "summarization"],
    shared_cache=cache,
    shared_memory=memory
))

data_agent = workflow.add_node(MCPAgentNode(
    name="data_agent",
    mcp_server="data_tools",
    capabilities=["data_access", "sql", "visualization"],
    shared_cache=cache,
    shared_memory=memory
))

# Agents automatically share tool results through cache
```

**Benefits**:
- Tool capability sharing
- Prevents redundant API calls
- Cost optimization

### 17. Team Formation Strategy Pattern
**Purpose**: Different strategies for forming agent teams

```python
from kailash.nodes.ai.self_organizing import TeamFormationNode

# Capability-based team formation
team_former = workflow.add_node(TeamFormationNode(
    name="team_former",
    formation_strategy="capability_matching"  # Best for skill-specific tasks
))

# Alternative strategies:
# "swarm_based" - For exploration/discovery
# "market_based" - For resource-constrained scenarios
# "hierarchical" - For complex multi-level problems
```

### 18. Convergence Detection Pattern
**Purpose**: Automatically determine when to stop iterating

```python
from kailash.nodes.ai.intelligent_agent_orchestrator import ConvergenceDetectorNode

convergence = workflow.add_node(ConvergenceDetectorNode(
    name="convergence",
    quality_threshold=0.85,      # Stop when quality >= 85%
    improvement_threshold=0.02,   # Stop if improvement < 2%
    max_iterations=10,           # Hard limit
    timeout=600,                 # 10 minute timeout
    min_iterations=3             # Always run at least 3 times
))
```

### 19. Information Reuse Pattern
**Purpose**: Intelligent caching across agent operations

```python
# Cache expensive operations with semantic matching
cache_result = cache.run(
    action="cache",
    cache_key="market_analysis_2024",
    data={"trends": [...], "predictions": [...]},
    metadata={
        "source": "market_mcp",
        "cost": 2.50,
        "semantic_tags": ["market", "analysis", "trends"]
    },
    ttl=3600  # 1 hour TTL
)

# Later agents can retrieve by semantic similarity
similar_result = cache.run(
    action="get",
    query="stock market analysis trends",
    similarity_threshold=0.8
)
```

### 20. Coordinated Multi-Agent Pattern
**Purpose**: Agents working on different aspects of a problem

```python
from kailash.nodes.ai.a2a import A2ACoordinatorNode

coordinator = workflow.add_node(A2ACoordinatorNode(name="coordinator"))

# Register agents with specialized roles
coordinator.run(
    action="register",
    agent_info={
        "agent_id": "analyst_001",
        "capabilities": ["data_analysis", "statistics"],
        "availability": "ready"
    }
)

# Delegate tasks based on capabilities
result = coordinator.run(
    action="delegate",
    task={"type": "analysis", "description": "Analyze sales data"},
    coordination_strategy="best_match"
)

# Build consensus on solutions
consensus = coordinator.run(
    action="consensus",
    proposals=[proposal1, proposal2, proposal3],
    voting_agents=["analyst_001", "strategist_002", "researcher_003"]
)
```

**Use Cases**:
- Distributed problem solving
- Multi-perspective analysis
- Democratic decision making

### 21. MCP Ecosystem Integration Pattern
**Purpose**: Zero-code workflow builder with MCP server integration

```python
from kailash.api.gateway import WorkflowGateway
from kailash.nodes.ai.intelligent_agent_orchestrator import OrchestrationManagerNode
from kailash.nodes.mcp import MCPClientNode

# Create MCP-enabled workflow gateway
gateway = WorkflowGateway(port=8000)

# Register MCP servers for external tool access
mcp_config = {
    "research_tools": {
        "command": "python",
        "args": ["-m", "research_mcp_server"],
        "capabilities": ["web_search", "document_analysis"]
    },
    "data_tools": {
        "command": "python",
        "args": ["-m", "data_mcp_server"],
        "capabilities": ["sql_query", "visualization"]
    }
}

# Create orchestrated workflow with MCP integration
workflow = Workflow()
orchestrator = workflow.add_node(OrchestrationManagerNode(
    name="mcp_orchestrator",
    mcp_servers=list(mcp_config.keys()),
    agent_pool_size=15,
    enable_caching=True
))

# Register workflow with gateway
gateway.register_workflow("mcp_research", workflow, mcp_config=mcp_config)
gateway.start()

# Provides web UI for:
# - Drag-and-drop workflow building
# - MCP server management
# - Real-time execution monitoring
# - Interactive result visualization
```

**Features**:
- Zero-code workflow creation via web UI
- Automatic MCP server discovery and integration
- Real-time collaboration between agents and external tools
- Visual workflow builder with live statistics
- Cost optimization through intelligent caching

**Use Cases**:
- Research and analysis workflows
- Data pipeline automation
- Multi-tool orchestration
- Interactive data exploration

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

### 17. Workflow Studio Visual Development Pattern
**Purpose**: Use visual interface for workflow development and deployment

```python
# Export workflow from Python for visual editing
from kailash.utils.export import WorkflowExporter

# Create workflow programmatically
workflow = create_data_processing_workflow()

# Export for Studio import
workflow.save("workflow.yaml", format="yaml")

# Import to Studio via API
import requests
with open("workflow.yaml", "rb") as f:
    response = requests.post(
        "https://studio.kailash.ai/api/workflows/import",
        files={"workflow": f},
        headers={"Authorization": f"Bearer {token}"}
    )

# Or use Studio API client
from kailash.api.studio import StudioClient
client = StudioClient(api_key="your-api-key")
client.upload_workflow(workflow)
```

**Studio Features**:
- Drag-and-drop node palette with 66+ nodes
- Real-time parameter validation
- Visual connection mapping
- Live execution monitoring
- Export to Python/YAML/JSON

### 18. Multi-Tenant Deployment Pattern
**Purpose**: Deploy isolated workflow environments for multiple tenants

```bash
# Deploy new tenant with isolated resources
./studio/deploy-tenant.sh \
  --tenant-id acme-corp \
  --domain acme.studio.kailash.ai \
  --database-schema acme \
  --redis-db 2

# This creates:
# - Isolated Docker container
# - PostgreSQL schema for tenant data
# - Redis database for caching
# - Nginx routing configuration
```

**Tenant Isolation**:
- Separate workflow storage per tenant
- Isolated execution environments
- Per-tenant resource limits
- Independent authentication

## Security Patterns

### 16. Secure File Processing Pattern
**Purpose**: Safely process files with path validation and sanitization

```python
from kailash.security import SecurityConfig, set_security_config, safe_open
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.nodes.mixins import SecurityMixin
from kailash.nodes.base import Node

# Configure security policy
security_config = SecurityConfig(
    allowed_directories=["/app/data", "/tmp/kailash"],
    max_file_size=50 * 1024 * 1024,  # 50MB
    execution_timeout=300.0,  # 5 minutes
    enable_audit_logging=True
)
set_security_config(security_config)

# Create secure workflow
workflow = Workflow("secure_data_processing")

# File operations automatically use security validation
workflow.add_node("reader", CSVReaderNode(), file_path="/app/data/input.csv")
workflow.add_node("processor", SecureProcessorNode())
workflow.add_node("writer", CSVWriterNode(), file_path="/app/data/output.csv")

workflow.connect("reader", "processor")
workflow.connect("processor", "writer")
```

**Applications**:
- Production data processing with security constraints
- Multi-tenant file processing with isolation
- Compliance-required workflows (GDPR, HIPAA)

### 17. Secure Code Execution Pattern
**Purpose**: Execute user-provided code with sandboxing and resource limits

```python
from kailash.security import SecurityConfig
from kailash.nodes.code.python import PythonCodeNode

# Configure secure execution
secure_config = SecurityConfig(
    execution_timeout=60.0,  # 1 minute limit
    memory_limit=256 * 1024 * 1024,  # 256MB limit
    enable_audit_logging=True
)

# Secure code execution node
secure_code_node = PythonCodeNode(
    code="""
    # User-provided code runs in sandbox
    result = sum(range(input_value))
    """,
    security_config=secure_config
)

workflow = Workflow("secure_computation")
workflow.add_node("compute", secure_code_node)

# Execute with resource monitoring
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "compute": {"input_value": 1000}
})
```

**Applications**:
- User-generated analytics scripts
- Dynamic data transformations
- Sandbox environments for untrusted code

### 18. Secure Node Development Pattern
**Purpose**: Create custom nodes with built-in security features

```python
from kailash.nodes.mixins import SecurityMixin
from kailash.nodes.base import Node, NodeParameter

class SecureDataProcessorNode(SecurityMixin, Node):
    """Custom node with integrated security."""

    def get_parameters(self):
        return {
            "input_data": NodeParameter(
                type=list,
                description="Data to process",
                required=True
            )
        }

    def run(self, **kwargs):
        # Automatic input validation and sanitization
        safe_params = self.validate_and_sanitize_inputs(kwargs)

        # Log security event
        self.log_security_event("Processing data", level="INFO")

        # Process data safely
        processed_data = self.secure_process(safe_params["input_data"])

        return {"processed": processed_data}

    def secure_process(self, data):
        """Process data with security considerations."""
        # Validate data size
        if len(data) > 10000:
            raise SecurityError("Data too large for processing")

        # Process with size limits
        return [item for item in data if self.is_safe_item(item)]

    def is_safe_item(self, item):
        """Check if item is safe to process."""
        return not any(dangerous in str(item) for dangerous in ['<script>', 'eval(', 'exec('])
```

**Applications**:
- Custom business logic nodes requiring security
- Third-party integration nodes
- Nodes handling sensitive data

### 19. Authentication Security Pattern
**Purpose**: Secure API authentication with credential protection

```python
import os
from kailash.nodes.api.auth import OAuth2Node, APIKeyNode
from kailash.nodes.api.rest import RESTClientNode

# Secure credential management using environment variables
workflow = Workflow("secure_api_integration")

# OAuth2 with environment-based credentials
oauth_node = OAuth2Node(
    token_url="https://auth.example.com/token",
    client_id=os.getenv("API_CLIENT_ID"),  # From environment
    client_secret=os.getenv("API_CLIENT_SECRET"),  # From environment
    scope="read:data"
)

# API key with secure storage
api_key_node = APIKeyNode(
    api_key=os.getenv("API_KEY"),  # From environment
    placement="header",
    key_name="Authorization",
    prefix="Bearer"
)

# REST client with authentication
rest_node = RESTClientNode(
    base_url="https://api.example.com",
    auth_type="oauth2",
    auth_config={"oauth2_node": oauth_node}
)

workflow.add_node("auth", oauth_node)
workflow.add_node("api", rest_node)
workflow.connect("auth", "api")
```

**Applications**:
- Enterprise API integrations
- Multi-service authentication workflows
- Credential rotation and management

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
