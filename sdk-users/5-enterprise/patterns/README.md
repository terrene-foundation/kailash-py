# Architecture Patterns - SDK User Guide

*Simplified architectural guidance for building with Kailash SDK*

## 📋 Quick Architecture Decisions

Before building any application, make these key decisions:

1. **Workflow Pattern** → How will you construct workflows?
2. **Interface Routing** → How will users interact with your app?
3. **Performance Strategy** → What are your latency/throughput needs?
4. **Deployment Model** → Where and how will you deploy?

## 🎯 Common Architecture Patterns

### 1. **Microservice Pattern**
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
from kailash.api.gateway import create_gateway

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Each workflow as a separate service
gateway = create_gateway(
    workflows={
        "user-service": user_workflow,
        "order-service": order_workflow,
        "analytics": analytics_workflow
    },
    config={"enable_service_discovery": True}
)

```
**When to use**: Multiple teams, independent scaling, service isolation

### 2. **Monolithic Pattern**
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

# All workflows in single deployment
app = create_gateway(
    workflows={**user_workflows, **order_workflows, **admin_workflows},
    config={"enable_shared_state": True}
)

```
**When to use**: Small teams, simpler deployment, shared resources

### 3. **Event-Driven Pattern**
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
from kailash.nodes.events import EventListenerNode

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Workflows triggered by events
workflow.add_node("EventListenerNode", "listener", {})

```
**When to use**: Reactive systems, loose coupling, async processing

### 4. **Batch Processing Pattern**
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode, BatchReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Scheduled bulk operations
workflow.add_node("BatchReaderNode", "reader", {})

```
**When to use**: Large data volumes, scheduled jobs, ETL pipelines

## 🏗️ Architectural Components

### Core Layers

1. **Interface Layer** - How users interact
   - REST API (`WorkflowAPIGateway`)
   - WebSocket (`RealtimeMiddleware`)
   - CLI (`DirectExecution`)
   - MCP Tools (`MCPIntegration`)

2. **Business Logic Layer** - Your workflows
   - Workflows define business processes
   - Nodes implement specific operations
   - Connections define data flow

3. **Data Layer** - Storage and retrieval
   - Database nodes (`SQLDatabaseNode`, `AsyncSQLDatabaseNode`)
   - File storage (`CSVReaderNode`, `JSONWriterNode`)
   - Cache (`IntelligentCacheNode`)
   - Vector stores (RAG nodes)

4. **Integration Layer** - External systems
   - APIs (`HTTPRequestNode`, `RESTClientNode`)
   - Message queues (`EventPublisherNode`)
   - AI services (`LLMAgentNode`)
   - MCP servers (`mcp_servers` config)

## 🔄 Common Integration Patterns

### API Gateway Pattern
```python
from kailash.api.gateway import create_gateway

# Central API for all workflows
gateway = create_gateway(
    workflows=all_workflows,
    config={
        "enable_auth": True,
        "enable_monitoring": True,
        "rate_limiting": {"requests_per_minute": 1000}
    }
)

```

### Middleware Stack Pattern
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

# Layer middleware for cross-cutting concerns
gateway = create_gateway(
    workflows=workflows,
    middleware=[
        AuthenticationMiddleware(),
        LoggingMiddleware(),
        CachingMiddleware(),
        ErrorHandlingMiddleware()
    ]
)

```

### Agent Distribution Pattern
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
from kailash.nodes.coordination import A2ACoordinatorNode
from kailash.nodes.management import AgentPoolManagerNode

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Distribute AI workload across agents
workflow.add_node("A2ACoordinatorNode", "coordinator", {})
workflow.add_node("AgentPoolManagerNode", "pool", {})

```

## 📊 Performance Patterns

### Caching Strategy
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
from kailash.nodes.cache import InMemoryCacheNode, RedisCacheNode, IntelligentCacheNode

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Multi-level caching
workflow.add_node("InMemoryCacheNode", "l1_cache", {})
workflow.add_node("RedisCacheNode", "l2_cache", {})
workflow.add_node("IntelligentCacheNode", "l3_cache", {})

```

### Async Processing
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

# Parallel execution
runtime = LocalRuntime(
    enable_async=True,
    max_concurrency=20,
    worker_pool_size=10
)

```

### Load Balancing
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
from kailash.nodes.network import LoadBalancerNode

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Distribute across multiple instances
workflow.add_node("LoadBalancerNode", "balancer", {})

```

## 🔒 Security Patterns

### Authentication & Authorization
```python
from kailash.access_control import AccessControlManager, PolicyEngine, AccessControlledRuntime

# Multi-layer security
runtime = AccessControlledRuntime(
    user_context=user,
    access_manager=AccessControlManager(
        strategy="hybrid",  # RBAC + ABAC
        policy_engine=PolicyEngine()
    )
)

```

### Data Protection
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
from kailash.nodes.security import EncryptionNode, DataValidationNode

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Encryption and validation
workflow.add_node("EncryptionNode", "encryptor", {})
workflow.add_node("DataValidationNode", "validator", {})

```

## 🚀 Deployment Patterns

### Container Deployment
```dockerfile
FROM python:3.11-slim
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "-m", "kailash.api.gateway", "--workflows", "all"]
```

### Serverless Deployment
```python
import json
from kailash.runtime.local import LocalRuntime

# AWS Lambda handler
def lambda_handler(event, context):
    runtime = LocalRuntime()
    workflow = load_workflow(event["workflow_id"])
    results, run_id = runtime.execute(
        workflow,
        parameters=event["parameters"]
    )
    return {"statusCode": 200, "body": json.dumps(results)}

```

### Kubernetes Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kailash-app
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: kailash
        image: myapp/kailash:latest
        env:
        - name: KAILASH_WORKERS
          value: "10"
```

## 📐 Decision Framework

### Choose Your Architecture

| **If you need...** | **Use this pattern** | **Key components** |
|-------------------|---------------------|-------------------|
| Simple REST API | API Gateway | `create_gateway()` |
| Real-time updates | WebSocket + SSE | `RealtimeMiddleware` |
| AI tool integration | MCP Integration | `mcp_servers` config |
| High throughput | Async + Caching | `LocalRuntime(enable_async=True)` |
| Multi-tenant | Access Control | `AccessControlledRuntime` |
| Microservices | Service Mesh | Multiple gateways + discovery |

### Performance Guidelines

| **Latency Target** | **Architecture Choice** |
|-------------------|----------------------|
| <10ms | Direct execution, in-memory cache |
| <100ms | API Gateway with caching |
| <1s | Standard REST API |
| >1s | Async processing with callbacks |

### Scale Guidelines

| **Load Profile** | **Architecture Choice** |
|-----------------|----------------------|
| <100 req/s | Single instance |
| 100-1000 req/s | Load balanced instances |
| >1000 req/s | Distributed + caching |
| Burst traffic | Auto-scaling + queue |

## 🔗 Related Resources

- **[Decision Matrix](../decision-matrix.md)** - Detailed decision guide
- **[Developer Guide](../developer/)** - Implementation details
- **[Production Patterns](../production-patterns/)** - Real examples
- **[Apps Guide](../../apps/ARCHITECTURAL_GUIDE.md)** - Complete app guide

## 💡 Quick Tips

1. **Start Simple** - Use `create_gateway()` for most apps
2. **Add Complexity Gradually** - Don't over-engineer early
3. **Monitor Everything** - Enable monitoring from day 1
4. **Cache Aggressively** - Most workflows benefit from caching
5. **Test at Scale** - Load test before production

## 🎯 Example: E-commerce Architecture

```python
from kailash.api.gateway import create_gateway

# E-commerce platform architecture
gateway = create_gateway(
    workflows={
        # User management
        "user": user_workflow,
        "auth": auth_workflow,

        # Product catalog
        "catalog": product_workflow,
        "search": search_workflow,

        # Order processing
        "cart": cart_workflow,
        "checkout": checkout_workflow,
        "payment": payment_workflow,

        # Analytics
        "analytics": analytics_workflow,
        "reports": reporting_workflow
    },
    config={
        "enable_auth": True,
        "enable_monitoring": True,
        "enable_ai_chat": True,
        "enable_realtime": True,
        "database_url": "postgresql://...",
        "redis_url": "redis://...",
        "rate_limiting": {
            "authenticated": 1000,
            "anonymous": 100
        }
    }
)

# Deploy with auto-scaling
gateway.run(
    host="0.0.0.0",
    port=8000,
    workers=4,
    enable_auto_scaling=True
)

```

This architecture provides:
- Modular workflow organization
- Built-in auth and monitoring
- Real-time updates for cart/orders
- AI chat for customer support
- Scalable deployment
