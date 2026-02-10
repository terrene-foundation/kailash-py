# Basic Usage Guide

Master the fundamental patterns and concepts of Nexus platform development.

## Overview

This guide covers the essential usage patterns you'll use daily with Nexus. After completing this guide, you'll understand the core concepts and be ready to build production workflows.

## Core Concepts

### 1. Platform Initialization

Nexus follows the FastAPI-style explicit instance pattern:

```python
from nexus import Nexus

# Basic instance
app = Nexus()

# Configured instance
app = Nexus(
    api_port=8080,
    mcp_port=3001,
    enable_auth=False,     # Progressive enhancement
    enable_monitoring=False  # Progressive enhancement
)
```

### 2. Workflow Registration

The core innovation: single registration → multi-channel access

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

# Build workflow
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "api_call", {
    "url": "https://api.example.com/data",
    "method": "GET"
})

# Revolutionary: Register once, available everywhere
app.register("data-fetcher", workflow.build())
```

### 3. Platform Lifecycle

```python
# Check status before starting
health = app.health_check()
print(f"Platform type: {health['platform_type']}")
print(f"Architecture: {health['architecture']}")

# Start platform
app.start()

# Platform now serves:
# - REST API: http://localhost:8000/workflows/data-fetcher/execute
# - CLI commands: nexus run data-fetcher
# - MCP tools: Available to AI agents

# Stop gracefully
app.stop()
```

## Common Patterns

### HTTP Data Processing

Build robust data processing pipelines:

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

# Build data processing workflow
workflow = WorkflowBuilder()

# Fetch data
workflow.add_node("HTTPRequestNode", "fetch", {
    "url": "https://jsonplaceholder.typicode.com/users",
    "method": "GET",
    "headers": {"Accept": "application/json"},
    "timeout": 30
})

# Parse JSON
workflow.add_node("JSONReaderNode", "parse", {})

# Transform data
workflow.add_node("PythonCodeNode", "transform", {
    "code": """
def process_users(data):
    # Extract user information
    users = data if isinstance(data, list) else [data]

    processed = []
    for user in users:
        processed.append({
            'id': user.get('id'),
            'name': user.get('name'),
            'email': user.get('email'),
            'company': user.get('company', {}).get('name', 'Unknown'),
            'processed_at': '2024-01-01T00:00:00Z'
        })

    return {'users': processed, 'count': len(processed)}
""",
    "function_name": "process_users"
})

app.register("user-processor", workflow.build())
app.start()
```

### Database Operations

Integrate with databases using enterprise features:

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

# Database workflow
workflow = WorkflowBuilder()

# Connect to database
workflow.add_node("SQLDatabaseNode", "db_connect", {
    "connection_string": "sqlite:///example.db",
    "query": "SELECT * FROM users WHERE active = 1",
    "operation": "select"
})

# Process results
workflow.add_node("PythonCodeNode", "process_results", {
    "code": """
def format_results(data):
    rows = data.get('result', [])
    return {
        'total_users': len(rows),
        'active_users': [
            {'id': row[0], 'name': row[1], 'email': row[2]}
            for row in rows
        ]
    }
""",
    "function_name": "format_results"
})

app.register("user-query", workflow.build())
app.start()
```

### File Processing

Handle file operations with built-in nodes:

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

# File processing workflow
workflow = WorkflowBuilder()

# Read CSV file
workflow.add_node("CSVReaderNode", "read_csv", {
    "file_path": "./data/input.csv",
    "has_header": True
})

# Transform data
workflow.add_node("PythonCodeNode", "analyze_data", {
    "code": """
def analyze_csv_data(data):
    rows = data.get('rows', [])

    if not rows:
        return {'error': 'No data found'}

    # Basic analysis
    total_rows = len(rows)
    columns = data.get('headers', [])

    return {
        'analysis': {
            'total_rows': total_rows,
            'column_count': len(columns),
            'columns': columns,
            'sample_row': rows[0] if rows else None
        }
    }
""",
    "function_name": "analyze_csv_data"
})

app.register("csv-analyzer", workflow.build())
app.start()
```

## Error Handling

Implement robust error handling patterns:

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

# Resilient workflow with error handling
workflow = WorkflowBuilder()

# HTTP request with retry logic
workflow.add_node("HTTPRequestNode", "api_call", {
    "url": "https://httpbin.org/status/500",  # Simulates error
    "method": "GET",
    "timeout": 10,
    "retry_count": 3,
    "retry_delay": 1
})

# Error detection
workflow.add_node("SwitchNode", "check_status", {
    "conditions": [
        {"field": "status_code", "operator": "eq", "value": 200},
        {"field": "status_code", "operator": "gte", "value": 400}
    ]
})

# Success handler
workflow.add_node("PythonCodeNode", "handle_success", {
    "code": """
def process_success(data):
    return {
        'status': 'success',
        'data': data,
        'processed_at': __import__('datetime').datetime.now().isoformat()
    }
""",
    "function_name": "process_success"
})

# Error handler
workflow.add_node("PythonCodeNode", "handle_error", {
    "code": """
def process_error(data):
    status_code = data.get('status_code', 'unknown')
    error_msg = data.get('error', 'Unknown error')

    return {
        'status': 'error',
        'error_code': status_code,
        'error_message': error_msg,
        'retry_count': data.get('retry_count', 0),
        'failed_at': __import__('datetime').datetime.now().isoformat()
    }
""",
    "function_name": "process_error"
})

app.register("resilient-api", workflow.build())
app.start()
```

## Testing Your Workflows

Test workflows before deployment:

```python
import requests
import time

def test_workflow(workflow_name, inputs=None, port=8000):
    """Test a registered workflow"""

    # Wait for server startup
    time.sleep(1)

    # Execute workflow
    response = requests.post(
        f"http://localhost:{port}/workflows/{workflow_name}/execute",
        json={"inputs": inputs or {}}
    )

    if response.status_code == 200:
        result = response.json()
        print(f"✅ {workflow_name} succeeded")
        print(f"Result: {result}")
        return True
    else:
        print(f"❌ {workflow_name} failed: {response.status_code}")
        print(f"Error: {response.text}")
        return False

# Test your workflows
def run_tests():
    # Test basic workflow
    test_workflow("user-processor")

    # Test database workflow
    test_workflow("user-query")

    # Test file processing
    test_workflow("csv-analyzer")

    # Test error handling
    test_workflow("resilient-api")

# Run tests after starting server
run_tests()
```

## Configuration Management

Configure Nexus for different environments:

```python
from nexus import Nexus

def create_development_app():
    """Development configuration"""
    return Nexus(
        api_port=8000,
        enable_auth=False,
        enable_monitoring=False
    )

def create_staging_app():
    """Staging configuration"""
    return Nexus(
        api_port=8001,
        enable_auth=True,
        enable_monitoring=True
    )

def create_production_app():
    """Production configuration"""
    return Nexus(
        api_port=80,
        enable_auth=True,
        enable_monitoring=True,
        rate_limit=1000  # Requests per minute
    )

# Environment-based initialization
import os

environment = os.getenv('NEXUS_ENV', 'development')

if environment == 'production':
    app = create_production_app()
elif environment == 'staging':
    app = create_staging_app()
else:
    app = create_development_app()

print(f"Nexus configured for {environment}")
```

## Health Monitoring

Monitor your platform health:

```python
from nexus import Nexus

app = Nexus()

# Register some workflows first
# ... workflow registration code ...

# Get comprehensive health status
def check_platform_health():
    health = app.health_check()

    print("🏥 Platform Health Report")
    print(f"Status: {health['status']}")
    print(f"Platform Type: {health['platform_type']}")
    print(f"Architecture: {health['architecture']}")
    print(f"Registered Workflows: {health['workflows']}")

    # Check revolutionary capabilities
    caps = health.get('revolutionary_capabilities', {})
    print("\n🚀 Revolutionary Capabilities:")
    print(f"  Durable-First Design: {caps.get('durable_first_design', False)}")
    print(f"  Multi-Channel Native: {caps.get('multi_channel_native', False)}")
    print(f"  Enterprise Default: {caps.get('enterprise_default', False)}")
    print(f"  Cross-Channel Sync: {caps.get('cross_channel_sync', False)}")

    # Check performance metrics
    metrics = health.get('performance_metrics', {})
    if metrics:
        print("\n📊 Performance Metrics:")
        for metric, data in metrics.items():
            avg_time = data.get('average', 0)
            target_met = data.get('target_met', False)
            status = "✅" if target_met else "⚠️"
            print(f"  {status} {metric}: {avg_time:.3f}s")

    return health['status'] == 'healthy'

# Run health check
if check_platform_health():
    print("\n✅ Platform is healthy!")
else:
    print("\n❌ Platform health issues detected")
```

## Progressive Enhancement

Add advanced features as needed using the plugin system:

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, TenantConfig, RateLimitConfig, AuditConfig

# Start simple
app = Nexus()

# Add authentication with NexusAuthPlugin
# Basic auth (JWT + audit logging)
auth = NexusAuthPlugin.basic_auth(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"])
)
app.add_plugin(auth)

# Or for SaaS apps (JWT + RBAC + tenant isolation + audit)
auth = NexusAuthPlugin.saas_app(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={"admin": ["*"], "editor": ["read:*", "write:*"], "viewer": ["read:*"]},
    tenant_isolation=TenantConfig(admin_role="admin"),
)
app.add_plugin(auth)

# CORS, rate limiting, and monitoring are set at construction time
app = Nexus(
    cors_origins=["https://myapp.com"],
    rate_limit=500,             # Requests per minute
    enable_monitoring=True,
    preset="saas",              # Preconfigured middleware stack
)
app.add_plugin(auth)
app.start()
```

You can also add custom middleware and routers directly:

```python
from nexus import Nexus

app = Nexus()

# Add custom FastAPI middleware
app.add_middleware(SomeMiddlewareClass, option="value")

# Include additional FastAPI routers
app.include_router(my_router, prefix="/custom")

# Register handlers for simple workflows
@app.handler("ping", description="Health ping")
async def ping() -> dict:
    return {"status": "ok"}

app.start()
```

## Best Practices

### 1. Workflow Organization

```python
# Organize workflows by domain (always call .build() on WorkflowBuilder instances)
app.register("user-management/create", user_create_workflow.build())
app.register("user-management/update", user_update_workflow.build())
app.register("data-processing/transform", transform_workflow.build())
app.register("data-processing/validate", validate_workflow.build())
```

### 2. Error Handling

```python
# Always include error handling nodes
workflow.add_node("SwitchNode", "error_check", {
    "conditions": [
        {"field": "error", "operator": "exists"}
    ]
})

workflow.add_node("PythonCodeNode", "log_error", {
    "code": """
def log_error(data):
    import logging
    logger = logging.getLogger(__name__)
    logger.error(f"Workflow error: {data.get('error')}")
    return data
"""
})
```

### 3. Resource Management

```python
import os

# Use connection pooling for databases (never hardcode credentials)
workflow.add_node("SQLDatabaseNode", "db_operation", {
    "connection_string": os.environ["DATABASE_URL"],
    "pool_size": 10,
    "max_overflow": 20
})
```

### 4. Performance Optimization

```python
# Add performance monitoring to critical workflows
workflow.add_node("PythonCodeNode", "start_timer", {
    "code": "import time; return {'start': time.time()}"
})

# ... business logic nodes ...

workflow.add_node("PythonCodeNode", "end_timer", {
    "code": """
import time
def calculate_duration(data):
    duration = time.time() - data.get('start', time.time())
    return {'duration_ms': duration * 1000, 'result': data}
"""
})
```

## Next Steps

Now that you understand basic usage patterns:

1. **[Multi-Channel Usage](../user-guides/multi-channel-usage.md)** - Master API, CLI, and MCP channels
2. **[Enterprise Features](../user-guides/enterprise-features.md)** - Production capabilities
3. **[Architecture Overview](../technical/architecture-overview.md)** - Deep technical understanding
4. **[Performance Guide](../technical/performance-guide.md)** - Optimization techniques

## Key Takeaways

✅ **Explicit Instances** → Clear, configurable platform setup
✅ **Single Registration** → Multi-channel automatic exposure
✅ **Progressive Enhancement** → Add features as needed
✅ **Enterprise Default** → Production features built-in
✅ **Health Monitoring** → Built-in observability

Nexus transforms traditional request-response APIs into **workflow-native platforms** with zero configuration and enterprise capabilities enabled by default.
