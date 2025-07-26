# Enterprise Patterns & Architecture

*Production-grade patterns for enterprise Kailash SDK deployments*

## 🏢 Overview

This directory contains enterprise-specific patterns, architectures, and best practices for deploying Kailash SDK in large-scale production environments.

## 📁 Directory Structure

| Component | Purpose | When to Use |
|-----------|---------|-------------|
| **[Middleware Patterns](middleware-patterns.md)** | Advanced middleware architecture | Real-time agent-UI applications |
| **[Session Management](../developer/28-enterprise-security-nodes-guide.md)** | Enterprise session handling | Multi-tenant, high-scale systems |
| **[Security Guide](../developer/28-enterprise-security-nodes-guide.md)** | Production security patterns | Enterprise security requirements |
| **[Performance](../developer/04-production.md)** | Scale and optimization | High-throughput workflows |
| **[Monitoring](../developer/34-monitoring-observability-guide.md)** | Production monitoring | Enterprise observability |
| **[Deployment](../developer/04-production.md)** | Production deployment | Container orchestration |

## 🎯 Quick Decision Matrix

### Choose Your Enterprise Pattern

| **Use Case** | **Primary Component** | **Key Features** |
|--------------|----------------------|------------------|
| **Real-time Dashboard** | AgentUIMiddleware + RealtimeMiddleware | WebSocket events, session isolation |
| **Multi-tenant SaaS** | AccessControlledRuntime + RBAC | Tenant isolation, role-based access |
| **High-throughput API** | API Gateway + Connection pooling | Rate limiting, caching, monitoring |
| **Agent Coordination** | A2A + Self-organizing nodes | Dynamic agent pools, intelligent routing |
| **Secure Enterprise** | JWT + ABAC + ThreatDetection | Multi-factor auth, threat monitoring |
| **Distributed Transactions** | DTM + Saga/2PC patterns | Automatic pattern selection, compensation logic |

## 🚀 Quick Start Patterns

### Basic Enterprise Setup
```python
from kailash.api.middleware import create_gateway
from kailash.runtime.access_controlled import AccessControlledRuntime
from kailash.security import SecurityConfig

# Enterprise gateway with full security
gateway = create_gateway(
    title="Enterprise Application",
    cors_origins=["https://app.company.com"],
    enable_docs=True,
    security_config=SecurityConfig(
        jwt_secret="enterprise-secret-key",
        enable_rate_limiting=True,
        max_requests_per_minute=1000
    )
)

# Access-controlled runtime
runtime = AccessControlledRuntime(
    access_control_strategy="rbac",  # Role-based access control
    default_permissions=["read"],
    audit_enabled=True
)

gateway.run(host="0.0.0.0", port=8000)

```

### Multi-Tenant Architecture
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

# Tenant-isolated middleware
gateway = create_gateway(
    title="Multi-Tenant Platform",
    tenant_isolation=True,
    database_per_tenant=True
)

# Tenant-aware session management
async def workflow.()  # Type signature example:
    return await gateway.agent_ui.create_session(
        user_id=f"{tenant_id}:{user_id}",
        metadata={
            "tenant_id": tenant_id,
            "isolation_level": "strict",
            "resource_limits": {
                "max_concurrent_workflows": 10,
                "max_memory_mb": 1024
            }
        }
    )

```

### High-Scale Agent Coordination
```python
from kailash.nodes.ai.a2a import A2ACoordinatorNode
from kailash.nodes.ai.self_organizing import AgentPoolManagerNode

# Enterprise agent pool
workflow.add_node("AgentPoolManagerNode", "agent_pool", {}))

# High-throughput coordinator
workflow.add_node("coordinator", A2ACoordinatorNode(
    max_concurrent_tasks=200,     # Enterprise throughput
    task_queue_limit=10000,
    coordination_strategy="weighted_round_robin",
    performance_monitoring=True
))

```

### Enterprise Transaction Management
```python
from kailash.nodes.transaction import DistributedTransactionManagerNode

# Automatic pattern selection for enterprise transactions
dtm = DistributedTransactionManagerNode(
    transaction_name="enterprise_order_processing",
    state_storage="database",
    storage_config={
        "db_pool": enterprise_db_pool,
        "table_name": "enterprise_transaction_states"
    }
)

# Create transaction with enterprise requirements
await dtm.async_run(
    operation="create_transaction",
    requirements={
        "consistency": "strong",        # Enterprise data consistency
        "availability": "high",         # 99.9% uptime requirement
        "timeout": 300,                # 5-minute timeout
        "isolation_level": "serializable"
    },
    context={
        "enterprise_id": "ENT001",
        "compliance_required": True,
        "audit_trail": True
    }
)

# Add enterprise service participants
enterprise_services = [
    {"id": "crm_service", "2pc": True, "saga": True},
    {"id": "erp_service", "2pc": True, "saga": True},
    {"id": "billing_service", "2pc": False, "saga": True},  # Legacy
    {"id": "audit_service", "2pc": True, "saga": True}
]

for service in enterprise_services:
    await dtm.async_run(
        operation="add_participant",
        participant_id=service["id"],
        endpoint=f"https://internal.{service['id']}.company.com/api/v1/transactions",
        supports_2pc=service["2pc"],
        supports_saga=service["saga"],
        timeout=60,
        retry_count=3
    )

# Execute with automatic pattern selection
result = await dtm.async_run(operation="execute_transaction")
print(f"Selected pattern: {result['selected_pattern']}")
```

## 🛡️ Security Patterns

### Enterprise Authentication
```python
from kailash.middleware.auth import KailashJWTAuth
from kailash.nodes.security import MultiFactorAuthNode

# JWT with enterprise features
jwt_auth = KailashJWTAuth(
    secret_key="enterprise-jwt-secret",
    token_expiry_hours=8,          # Work day sessions
    refresh_token_enabled=True,
    session_management=True,
    audit_logging=True
)

# Multi-factor authentication
workflow.add_node("MultiFactorAuthNode", "mfa", {}))

```

### Access Control Patterns
```python
from kailash.access_control import AccessControlManager

# Enterprise access control
access_manager = AccessControlManager(
    strategy="hybrid",             # RBAC + ABAC
    policies_file="/config/policies.yaml",
    dynamic_policies=True,
    audit_enabled=True
)

# Role-based workflow access
runtime = AccessControlledRuntime(
    access_control_manager=access_manager,
    require_authorization=True,
    log_all_access=True
)

```

## 📊 Monitoring & Observability

### Production Monitoring
```python
from kailash.monitoring import ProductionMonitor

# Comprehensive monitoring
monitor = ProductionMonitor(
    metrics_enabled=True,
    health_checks=True,
    performance_tracking=True,
    alert_rules=[
        {"metric": "workflow_failure_rate", "threshold": 0.05},
        {"metric": "response_time_p95", "threshold": 2000},
        {"metric": "memory_usage", "threshold": 0.8}
    ]
)

# Integrate with gateway
gateway = create_gateway(
    title="Monitored Application",
    monitoring=monitor
)

```

### Enterprise Logging
```python
import logging
from kailash.logging import EnterpriseLogger

# Structured logging for enterprises
logger = EnterpriseLogger(
    level=logging.INFO,
    format="json",                 # Structured logs for parsing
    include_metrics=True,
    compliance_logging=True,       # For audit requirements
    pii_redaction=True            # Automatic PII protection
)

```

## 🚀 Performance & Scale

### High-Throughput Configuration
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

# High-performance gateway
gateway = create_gateway(
    title="High-Throughput API",
    worker_processes=8,            # Multiple worker processes
    max_connections=1000,
    connection_pool_size=100,
    enable_compression=True,
    cache_enabled=True,
    cache_ttl=300
)

# Async runtime for performance
runtime = AsyncLocalRuntime(
    max_concurrent_workflows=50,
    workflow_timeout=300,
    memory_limit_mb=2048,
    enable_metrics=True
)

```

### Database Optimization
```python
from kailash.nodes.data import AsyncSQLDatabaseNode

# Enterprise database configuration
workflow.add_node("AsyncSQLDatabaseNode", "enterprise_db", {}))

```

## 🔄 CI/CD Integration

### Workflow Testing
```python
# Enterprise workflow testing
import pytest
from kailash.testing import WorkflowTester

class TestEnterpriseWorkflows:
    def test_production_workflow(self):
        tester = WorkflowTester()

        # Load production workflow configuration
        workflow = tester.load_workflow_from_config("/config/production.yaml")

        # Test with production-like data
        result = tester.test_workflow(
            workflow,
            test_data="/data/production_sample.json",
            performance_requirements={
                "max_execution_time": 30,
                "max_memory_mb": 512
            }
        )

        assert result.success
        assert result.performance.execution_time < 30
        assert result.performance.memory_usage_mb < 512

```

### Deployment Pipeline
```yaml
# .github/workflows/enterprise-deploy.yml
name: Enterprise Deployment

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Enterprise Tests
        run: |
          pytest tests/enterprise/ -v --cov=workflows/

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to Production
        run: |
          docker build -t terrene-foundation:${{ github.sha }} .
          kubectl apply -f k8s/production/
```

## 📋 Compliance & Governance

### Data Governance
```python
from kailash.nodes.security import GDPRComplianceNode

# GDPR compliance
workflow.add_node("GDPRComplianceNode", "gdpr_compliance", {}))

# SOC2 compliance monitoring
workflow.add_node("ComplianceMonitorNode", "soc2_monitor", {}))

```

## 🔗 Related Resources

### Core Documentation
- **[Middleware Guide](../middleware/README.md)** - Basic middleware setup
- **[Security Guide](../developer/08-security-guide.md)** - Security fundamentals
- **[Performance Guide](../features/performance_tracking.md)** - Performance basics

### Enterprise Examples
- **[Production Apps](../../apps/)** - Real enterprise applications
- **[Enterprise Workflows](../workflows/by-enterprise/)** - Business workflow examples
- **[Security Patterns](../workflows/by-pattern/security/)** - Security implementations

### External Resources
- **[Kubernetes Deployment](https://docs.kubernetes.io/)** - Container orchestration
- **[Monitoring Stack](https://prometheus.io/)** - Metrics and alerting
- **[Security Standards](https://www.iso.org/isoiec-27001-information-security.html)** - ISO 27001 compliance

---

**Ready for Enterprise?** Start with [middleware-patterns.md](middleware-patterns.md) for the complete enterprise middleware setup guide.
