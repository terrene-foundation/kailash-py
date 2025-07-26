# Enterprise Gateway Patterns

*Single-channel API gateway patterns for REST services and external systems integration*

## 🌐 Overview

This guide covers enterprise gateway implementation using Kailash SDK's `create_gateway()` function for single-channel API gateway deployment. For multi-channel orchestration (API + CLI + MCP), see [Nexus Patterns](nexus-patterns.md).

**Choose Your Architecture:**
- **Single-Channel API Gateway**: Use `create_gateway()` for REST-only services
- **Multi-Channel Platform**: Use `create_nexus()` for unified API, CLI, and MCP orchestration

This guide focuses on single-channel API gateway patterns with the redesigned server architecture.

## 🚀 Core Gateway Creation

### Basic Enterprise Gateway

```python
from kailash.servers.gateway import create_gateway

# Enterprise API gateway with redesigned architecture
gateway = create_gateway(
    title="Enterprise API Gateway",
    description="Production-ready single-channel API gateway",
    version="1.0.0",

    # Server type (enterprise is default)
    server_type="enterprise",  # "enterprise", "durable", "basic"

    # CORS configuration
    cors_origins=[
        "http://localhost:3000",
        "https://app.company.com",
        "https://admin.company.com"
    ],

    # Enterprise features (enabled by default)
    enable_durability=True,
    enable_resource_management=True,
    enable_async_execution=True,
    enable_health_checks=True,

    # Performance settings
    max_workers=20
)

# Returns EnterpriseWorkflowServer instance
# Run the enterprise gateway
gateway.run(host="0.0.0.0", port=8000)
```

### Advanced Gateway Configuration

```python
from kailash.servers.gateway import create_gateway
from kailash.resources.registry import ResourceRegistry
from kailash.gateway.security import SecretManager

# Custom resource management
resource_registry = ResourceRegistry()
resource_registry.register_database_pool("main_db",
    "postgresql://enterprise-db:5432/kailash")

# Enterprise security management
secret_manager = SecretManager(
    encryption_key="enterprise-secret-key",
    key_rotation_days=90,
    audit_access=True
)

# Advanced enterprise gateway
gateway = create_gateway(
    title="Secure Enterprise Platform",
    description="Advanced single-channel API gateway",
    version="2.0.0",

    # Server configuration
    server_type="enterprise",
    max_workers=50,

    # Security configuration
    cors_origins=["https://secure.company.com"],

    # Enterprise components
    resource_registry=resource_registry,
    secret_manager=secret_manager,

    # Feature toggles
    enable_durability=True,
    enable_resource_management=True,
    enable_async_execution=True,
    enable_health_checks=True
)
```

## 🔗 Core API Endpoints

### Gateway API Routes

The gateway automatically provides these enterprise endpoints:

#### **Core Information**
- `GET /` - Gateway info and available features
- `GET /health` - Detailed health check with component status
- `GET /api/stats` - Comprehensive performance statistics

#### **Session Management**
- `POST /api/sessions` - Create new user session
- `GET /api/sessions/{session_id}` - Get session details
- `DELETE /api/sessions/{session_id}` - Close session
- `GET /api/sessions` - List active sessions (admin)

#### **Workflow Operations**
- `POST /api/workflows` - Create dynamic workflow
- `GET /api/workflows/{workflow_id}` - Get workflow schema
- `GET /api/workflows` - List available workflows
- `POST /api/executions` - Execute workflow
- `GET /api/executions/{execution_id}` - Get execution status

#### **Real-time Communication**
- `WS /ws` - WebSocket endpoint with session filtering
- `GET /events` - Server-Sent Events (SSE) streaming
- `POST /api/webhooks` - Register webhook endpoint
- `DELETE /api/webhooks/{webhook_id}` - Unregister webhook

#### **Schema Discovery**
- `GET /api/schemas/nodes` - Get available node schemas
- `GET /api/schemas/nodes/{node_type}` - Get specific node schema
- `GET /api/schemas/workflows/{workflow_id}` - Get workflow schema

## 🏢 Multi-Tenant Gateway Patterns

### Tenant Isolation Setup

```python
from kailash.nodes.admin.tenant_isolation import TenantIsolationManager
from kailash.nodes.data import SQLDatabaseNode
from kailash.workflow.builder import WorkflowBuilder

# Multi-tenant gateway configuration with correct imports
multi_tenant_gateway = create_gateway(
    title="Multi-Tenant Enterprise Platform",
    description="Isolated tenant environments",

    # Enhanced session management for tenants
    max_sessions=10000,  # Higher limit for multiple tenants

    # Tenant-aware database
    database_url="postgresql://multi-tenant-db:5432/kailash"
)

# Create tenant isolation manager (not a workflow node)
db_node = SQLDatabaseNode(
    connection_string="postgresql://multi-tenant-db:5432/kailash",
    name="tenant_db"
)
tenant_manager = TenantIsolationManager(db_node)

# Permission checking workflow with tenant scope
tenant_workflow = WorkflowBuilder()

tenant_workflow.add_node("PermissionCheckNode", "check_tenant_perms", {
    "permission_format": "tenant_id:resource_id:permission",
    "enforce_tenant_scope": True
})

# Build workflow
tenant_isolation = tenant_workflow.build(
    workflow_id="tenant_isolation",
    name="Tenant Isolation Workflow"
)
```

### Tenant-Aware Session Management

```python
# Create tenant-scoped session
async def create_tenant_session(tenant_id: str, user_id: str):
    """Create session with tenant isolation using TenantIsolationManager."""

    # Validate user has access to the tenant
    is_valid = tenant_manager.validate_user_tenant_access(
        user_id=user_id,
        target_tenant_id=tenant_id
    )

    if not is_valid:
        raise PermissionError(f"User {user_id} denied access to tenant {tenant_id}")

    # Enforce tenant isolation
    tenant_manager.enforce_tenant_isolation(
        user_id=user_id,
        user_tenant_id=tenant_id,
        operation_tenant_id=tenant_id
    )

    # Create isolated session
    session_id = await gateway.agent_ui.create_session(
        user_id=f"{tenant_id}:{user_id}",
        metadata={
            "tenant_id": tenant_id,
            "isolation_level": "strict",
            "validated_by": "TenantIsolationManager"
        }
    )

    return session_id
```

## 🔄 Real-Time Communication Patterns

### WebSocket Integration

```python
# Frontend WebSocket connection
async function connectToGateway(sessionId) {
    const ws = new WebSocket(`ws://localhost:8000/ws?session_id=${sessionId}`);

    ws.onopen = () => {
        console.log('Connected to enterprise gateway');

        // Subscribe to workflow events
        ws.send(JSON.stringify({
            type: 'subscribe',
            events: ['workflow_started', 'workflow_completed', 'system_error']
        }));
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        switch(data.type) {
            case 'workflow_completed':
                updateWorkflowStatus(data.workflow_id, 'completed');
                break;
            case 'system_error':
                showSystemError(data.error);
                break;
            default:
                console.log('Gateway event:', data);
        }
    };

    ws.onerror = (error) => {
        console.error('Gateway connection error:', error);
        // Implement reconnection logic
        setTimeout(() => connectToGateway(sessionId), 5000);
    };

    return ws;
}
```

### Server-Sent Events (SSE)

```python
# SSE streaming for unidirectional communication
async function streamEvents(sessionId) {
    const eventSource = new EventSource(
        `http://localhost:8000/events?session_id=${sessionId}`
    );

    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);

        // Handle real-time workflow updates
        if (data.type === 'workflow_progress') {
            updateProgressBar(data.workflow_id, data.progress);
        }
    };

    eventSource.onerror = (error) => {
        console.error('SSE connection error:', error);
        // SSE automatically reconnects
    };

    return eventSource;
}
```

### Webhook Configuration

```python
from kailash.api.middleware import RealtimeMiddleware, AgentUIMiddleware

# Setup webhook support through RealtimeMiddleware
agent_ui = AgentUIMiddleware(max_sessions=1000)
realtime = RealtimeMiddleware(agent_ui)

# Register webhook endpoints
realtime.register_webhook(
    webhook_id="external_system_updates",
    url="https://external-system.com/webhook",
    event_types=["workflow.completed", "workflow.failed", "system.error"],
    headers={
        "Authorization": "Bearer your-webhook-token",
        "Content-Type": "application/json",
        "X-Source": "KailashSDK"
    },
    secret="webhook-signature-secret"  # For HMAC verification
)

# Register another webhook for different events
realtime.register_webhook(
    webhook_id="analytics_events",
    url="https://analytics.company.com/events",
    event_types=["workflow.completed"],
    headers={"Authorization": "Bearer analytics-token"}
)

# Gateway will automatically expose webhook management endpoints:
# POST /api/webhooks - Register new webhook
# GET /api/webhooks - List registered webhooks
# DELETE /api/webhooks/{webhook_id} - Unregister webhook
```

## 🔐 Gateway Security Patterns

### Authentication Integration

```python
# JWT authentication with enterprise features
auth_manager = MiddlewareAuthManager(
    secret_key="enterprise-jwt-secret",
    token_expiry_hours=8,  # Business hours

    # Enterprise features
    enable_api_keys=True,
    enable_audit=True,
    enable_refresh_tokens=True,

    # Security settings
    require_https=True,
    enable_rate_limiting=True,
    max_login_attempts=5,

    # Database for persistence
    database_url="postgresql://auth-db:5432/kailash_auth"
)

# Apply to gateway
secure_gateway = create_gateway(
    title="Secure Enterprise Gateway",
    auth_manager=auth_manager,
    cors_origins=["https://secure.company.com"],
    enable_docs=False  # Disable in production
)
```

### Rate Limiting Patterns

```python
from kailash.nodes.api import RateLimitedAPINode, RateLimitConfig

# Rate limiting configuration
rate_config = RateLimitConfig(
    max_requests=100,      # Requests per time window
    time_window=60.0,      # 1 minute window
    strategy="token_bucket", # or "sliding_window", "fixed_window"
    burst_limit=150,       # Allow burst traffic
    backoff_factor=1.5,    # Exponential backoff multiplier
    max_backoff=300.0      # Maximum backoff time in seconds
)

# Simple rate-limited API pattern using HTTPRequestNode with retries
api_workflow = WorkflowBuilder()

# Add HTTP request with built-in retry and rate limiting behavior
api_workflow.add_node("HTTPRequestNode", "external_api", {
    "url": "https://api.external-service.com/data",
    "method": "GET",
    "retry_attempts": 3,
    "retry_delay": 2,
    "timeout": 30,
    "headers": {
        "User-Agent": "KailashSDK/1.0",
        "Accept": "application/json"
    }
})

# Handle responses with rate limit detection
api_workflow.add_node("PythonCodeNode", "handle_response", {
    "code": """
if hasattr(response, 'status_code') and response.status_code == 429:
    # Rate limited by server
    retry_after = response.headers.get('Retry-After', 60)
    result = {'status': 'rate_limited', 'retry_after': int(retry_after)}
elif 'error' in response and 'rate limit' in str(response['error']).lower():
    result = {'status': 'rate_limited', 'retry_after': 60}
else:
    result = {'status': 'success', 'data': response}
"""
})

api_workflow.add_connection("external_api", "result", "response", "input")
```

## 🌍 External System Integration

### HTTP API Integration

```python
from kailash.nodes.api import HTTPRequestNode, RESTClientNode

# External system integration workflow
integration_workflow = WorkflowBuilder()

# HTTP request to external API
integration_workflow.add_node("HTTPRequestNode", "external_api", {
    "url": "https://api.partner-system.com/v1/data",
    "method": "GET",
    "headers": {
        "Authorization": "Bearer ${api_token}",
        "Content-Type": "application/json",
        "User-Agent": "KailashSDK/1.0"
    },
    "timeout": 30,
    "retry_attempts": 3,
    "retry_delay": 2
})

# REST client for complex API interactions
integration_workflow.add_node("RESTClientNode", "rest_client", {
    "base_url": "https://api.enterprise-system.com",
    "auth_type": "bearer",
    "auth_token": "${enterprise_api_key}",
    "default_headers": {
        "Accept": "application/json",
        "X-Client-ID": "terrene-foundation"
    }
})

# Process external data
integration_workflow.add_node("PythonCodeNode", "process_external", {
    "code": """
# Transform external API response to internal format
transformed_data = {
    'id': external_data.get('external_id'),
    'name': external_data.get('display_name'),
    'status': external_data.get('state', 'unknown'),
    'metadata': {
        'source': 'external_api',
        'processed_at': datetime.now().isoformat()
    }
}

result = {'transformed': transformed_data}
"""
})

integration_workflow.add_connection("external_api", "result", "response", "input")
```

### Database Integration

```python
from kailash.nodes.data import AsyncSQLDatabaseNode

# Database integration in gateway context
db_workflow = WorkflowBuilder()

# Enterprise database connection
db_workflow.add_node("AsyncSQLDatabaseNode", "enterprise_db", {
    "connection_string": "postgresql://enterprise-user:pass@db-cluster:5432/enterprise",
    "pool_size": 20,
    "max_overflow": 50,
    "pool_recycle": 3600,
    "echo": False,  # Disable SQL logging in production

    # Query configuration
    "query": """
    SELECT id, name, status, tenant_id, created_at
    FROM enterprise_records
    WHERE tenant_id = :tenant_id AND status = :status
    ORDER BY created_at DESC
    LIMIT :limit
    """,

    # Parameters will be injected at runtime
    "query_params": {
        "tenant_id": "${session.tenant_id}",
        "status": "active",
        "limit": 100
    }
})

# Process database results
db_workflow.add_node("PythonCodeNode", "process_db_results", {
    "code": """
# Format database results for API response
records = []
for row in db_results:
    records.append({
        'id': row['id'],
        'name': row['name'],
        'status': row['status'],
        'created_at': row['created_at'].isoformat()
    })

result = {
    'records': records,
    'count': len(records),
    'tenant_id': db_results[0]['tenant_id'] if records else None
}
"""
})

db_workflow.add_connection("enterprise_db", "result", "result", "input")
```

## 🔍 Service Discovery Patterns

### MCP Service Discovery

```python
from kailash.nodes.enterprise import MCPServiceDiscoveryNode

# Service discovery workflow for multi-tenant environment
discovery_workflow = WorkflowBuilder()

# MCP service discovery
discovery_workflow.add_node("MCPServiceDiscoveryNode", "discover_services", {
    "tenant_context": {
        "id": "${tenant_id}",
        "compliance_zones": ["gdpr", "hipaa"],
        "service_tier": "enterprise"
    },

    # Service requirements
    "required_capabilities": ["analytics", "data_processing"],
    "preferred_providers": ["internal", "trusted_partners"],

    # Discovery settings
    "cache_duration": 300,  # 5 minutes
    "health_check": True,
    "load_balancing": "round_robin"
})

# Service health validation
discovery_workflow.add_node("PythonCodeNode", "validate_services", {
    "code": """
healthy_services = []
for service in discovered_services:
    if service.get('health', {}).get('status') == 'healthy':
        healthy_services.append({
            'id': service['id'],
            'endpoint': service['endpoint'],
            'capabilities': service['capabilities'],
            'latency': service.get('health', {}).get('latency', 0)
        })

# Sort by latency for optimal performance
healthy_services.sort(key=lambda s: s['latency'])

result = {
    'services': healthy_services,
    'count': len(healthy_services),
    'discovery_timestamp': datetime.now().isoformat()
}
"""
})

discovery_workflow.add_connection("discover_services", "result", "services", "input")
```

## 📊 Gateway Monitoring & Analytics

### Performance Monitoring

```python
# Built-in gateway statistics
async def get_gateway_stats():
    """Get comprehensive gateway performance statistics."""

    # Gateway provides built-in stats endpoint
    stats_response = await gateway.get("/api/stats")

    return {
        "active_sessions": stats_response["sessions"]["active"],
        "total_requests": stats_response["requests"]["total"],
        "average_response_time": stats_response["performance"]["avg_response_time"],
        "error_rate": stats_response["errors"]["rate"],
        "uptime": stats_response["system"]["uptime"],

        # Real-time metrics
        "websocket_connections": stats_response["realtime"]["websocket_count"],
        "sse_connections": stats_response["realtime"]["sse_count"],
        "webhook_deliveries": stats_response["webhooks"]["delivered"],

        # Security metrics
        "failed_auth_attempts": stats_response["security"]["failed_auth"],
        "rate_limit_hits": stats_response["security"]["rate_limits"],

        # Database metrics
        "db_connections": stats_response["database"]["active_connections"],
        "db_query_time": stats_response["database"]["avg_query_time"]
    }
```

### Health Check Endpoint

```python
# Gateway automatically provides /health endpoint
# Returns comprehensive health status:
{
    "status": "healthy",
    "timestamp": "2024-01-01T12:00:00Z",
    "components": {
        "database": {"status": "healthy", "latency": 5},
        "authentication": {"status": "healthy", "last_check": "2024-01-01T11:59:00Z"},
        "websockets": {"status": "healthy", "active_connections": 245},
        "external_apis": {"status": "degraded", "failed_checks": 1}
    },
    "version": "1.0.0",
    "uptime": 86400
}
```

## 🚀 Dynamic Workflow Creation

### Runtime Workflow Generation

```python
# Create workflows dynamically through the gateway
async def create_dynamic_workflow(session_id: str, workflow_config: dict):
    """Create and register a workflow at runtime."""

    # Validate workflow configuration
    validated_config = await gateway.agent_ui.validate_workflow_config(
        workflow_config
    )

    if not validated_config["valid"]:
        raise ValueError(f"Invalid workflow: {validated_config['errors']}")

    # Create dynamic workflow
    workflow_id = await gateway.agent_ui.create_dynamic_workflow(
        session_id=session_id,
        workflow_config=workflow_config
    )

    return {
        "workflow_id": workflow_id,
        "status": "created",
        "endpoints": {
            "execute": f"/api/executions",
            "schema": f"/api/schemas/workflows/{workflow_id}",
            "status": f"/api/workflows/{workflow_id}"
        }
    }

# Example workflow configuration
example_config = {
    "name": "dynamic_data_pipeline",
    "description": "Dynamically created data processing pipeline",
    "nodes": [
        {
            "type": "HTTPRequestNode",
            "name": "fetch_data",
            "config": {
                "url": "https://api.example.com/data",
                "method": "GET"
            }
        },
        {
            "type": "PythonCodeNode",
            "name": "process_data",
            "config": {
                "code": "result = {'processed': len(data), 'timestamp': datetime.now().isoformat()}"
            }
        }
    ],
    "connections": [
        {
            "from_node": "fetch_data",
            "from_output": "response",
            "to_node": "process_data",
            "to_input": "data"
        }
    ]
}
```

## 🔧 Gateway Deployment Patterns

### Production Configuration

```python
# Production-ready gateway configuration
production_gateway = create_gateway(
    title="Enterprise Production Gateway",
    description="Production deployment with all security features",
    version="1.0.0",

    # Security configuration
    cors_origins=[
        "https://app.company.com",
        "https://admin.company.com"
    ],
    enable_docs=False,  # Disable in production

    # Authentication
    auth_manager=MiddlewareAuthManager(
        secret_key=os.environ["JWT_SECRET_KEY"],
        token_expiry_hours=8,
        enable_api_keys=True,
        enable_audit=True,
        database_url=os.environ["DATABASE_URL"]
    ),

    # Performance
    max_sessions=10000,

    # Database
    database_url=os.environ["DATABASE_URL"]
)

# Production run with SSL
if __name__ == "__main__":
    production_gateway.run(
        host="0.0.0.0",
        port=8000,
        # SSL configured at load balancer/proxy level
        access_log=True,
        workers=4  # Multiple workers for production
    )
```

### Container Deployment

```dockerfile
# Dockerfile for gateway deployment
FROM python:3.11-slim

WORKDIR /app

# Install Kailash SDK
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy gateway application
COPY gateway_app.py .
COPY config/ ./config/

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run gateway
CMD ["python", "gateway_app.py"]
```

## 📚 Quick Gateway Implementation Checklist

### Essential Gateway Components
- [ ] **Gateway Creation**: `create_gateway()` with enterprise configuration
- [ ] **Authentication**: JWT or API key authentication enabled
- [ ] **Rate Limiting**: Configured for API protection
- [ ] **Real-time Communication**: WebSocket and SSE endpoints
- [ ] **Multi-tenant Support**: Tenant isolation and scoped permissions
- [ ] **Health Monitoring**: Health checks and performance metrics
- [ ] **External Integration**: HTTP APIs and database connections
- [ ] **Security**: CORS, SSL/TLS, and audit logging
- [ ] **Service Discovery**: MCP service discovery for dynamic services
- [ ] **Documentation**: API documentation for client integration

### Gateway Endpoints Reference
- **`POST /api/sessions`** - Session management
- **`POST /api/workflows`** - Dynamic workflow creation
- **`POST /api/executions`** - Workflow execution
- **`WS /ws`** - WebSocket real-time communication
- **`GET /events`** - Server-Sent Events streaming
- **`GET /health`** - Health and status monitoring
- **`GET /api/stats`** - Performance statistics
- **`GET /api/schemas/nodes`** - Node schema discovery

### Server Architecture Options

**Single-Channel API Gateway (This Guide):**
```python
from kailash.servers.gateway import create_gateway

# Enterprise API-only gateway
gateway = create_gateway(server_type="enterprise")  # EnterpriseWorkflowServer
```

**Multi-Channel Platform (Recommended for New Projects):**
```python
from nexus import Nexus

# Unified API + CLI + MCP platform
nexus = Nexus()  # API, CLI, and MCP channels with session sync
```

### Related Enterprise Guides
- **[Nexus Patterns](nexus-patterns.md)** - Multi-channel orchestration (API + CLI + MCP)
- **[Security Patterns](security-patterns.md)** - Authentication and authorization
- **[Middleware Patterns](middleware-patterns.md)** - Advanced middleware setup
- **[Production Patterns](production-patterns.md)** - Deployment and scaling
- **[Compliance Patterns](compliance-patterns.md)** - Regulatory compliance

---

**Ready to build enterprise gateways?**
- **Single-channel API**: Start with `create_gateway()` for REST-only services
- **Multi-channel platform**: Start with `create_nexus()` for unified API, CLI, and MCP orchestration
