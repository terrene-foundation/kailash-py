# Enterprise Patterns & Best Practices

## 🏗️ Middleware Integration

### Database Layer
```python
# NEVER manually implement SQLAlchemy models
# ❌ Wrong
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)

# ✅ Correct - Extend middleware base models
from kailash.middleware.database import BaseUserModel, TenantMixin

class User(BaseUserModel, TenantMixin):
    __tablename__ = "app_users"
    # Only add app-specific fields
```

### API Gateway
```python
# NEVER create FastAPI manually
# ❌ Wrong
app = FastAPI()
@app.post("/api/users")
async def create_user(): pass

# ✅ Correct - Use enterprise gateway
from kailash.middleware import create_gateway

app = create_gateway(
    title="My App",
    workflows=my_workflows,
    enable_auth=True,
    enable_monitoring=True
)
```

## 🔐 Security Patterns

### Authentication Stack
```python
# Automatic enterprise auth with all providers
auth_config = {
    "sso_providers": ["azure", "google", "okta", "saml"],
    "mfa_methods": ["totp", "sms", "webauthn"],
    "session_management": {
        "timeout_minutes": 120,
        "max_sessions_per_user": 5
    }
}
```

### ABAC Authorization
```python
# AI-powered permission evaluation
workflow.add_node("permission_check", ABACPermissionEvaluatorNode(
    ai_reasoning=True,
    cache_results=True,
    operators=[
        "equals", "not_equals", "contains",
        "greater_than", "time_between", "distance_within"
    ]
))
```

### Threat Detection
```python
# Real-time security monitoring
workflow.add_node("threat_detector", ThreatDetectionNode(
    ml_model="security_v2",
    response_time_ms=100,
    auto_block_threshold=0.9
))
```

## 🚀 Performance Patterns

### Routing Strategy
```python
class HighPerformanceApp:
    FAST_OPERATIONS = {"health", "validate", "transform"}

    async def route_operation(self, op: str, data: dict):
        # Direct routing for <25ms operations
        if op in self.FAST_OPERATIONS:
            return await self._direct_execute(op, data)
        # MCP routing for complex operations
        return await self.mcp_server.call_tool(op, data)
```

### Caching Strategy
```python
# Multi-level caching
cache_config = {
    "l1_memory": {"size": "100MB", "ttl": 300},
    "l2_redis": {"ttl": 3600, "cluster": True},
    "l3_database": {"persistent": True}
}

@mcp_server.tool(cache_key="user:{user_id}", cache_ttl=600)
async def get_user(user_id: str):
    return await db.get_user(user_id)
```

### Connection Pooling
```python
# Database connection optimization
database_config = {
    "pool_size": 20,
    "max_overflow": 10,
    "pool_timeout": 30,
    "pool_recycle": 3600
}
```

## 📊 Monitoring & Observability

### Metrics Collection
```python
# Automatic metrics with Prometheus
from kailash.middleware.monitoring import MetricsCollector

metrics = MetricsCollector(
    export_endpoint="/metrics",
    custom_metrics={
        "business_operations": Counter("app_operations_total"),
        "processing_time": Histogram("app_processing_seconds")
    }
)
```

### Distributed Tracing
```python
# OpenTelemetry integration
tracing_config = {
    "service_name": "my-app",
    "sample_rate": 0.1,
    "exporters": ["jaeger", "datadog"]
}
```

## 🔄 Workflow Patterns

### Template Inheritance
```python
class WorkflowTemplates:
    def create_crud_template(self, entity: str) -> Workflow:
        """Reusable CRUD pattern"""
        workflow = Workflow(f"{entity}_crud")
        workflow.add_node("validate", ValidationNode())
        workflow.add_node("authorize", ABACPermissionEvaluatorNode())
        workflow.add_node("execute", DatabaseOperationNode())
        workflow.add_node("audit", AuditLogNode())
        return workflow

    def create_etl_template(self, source: str) -> Workflow:
        """Reusable ETL pattern"""
        workflow = Workflow(f"{source}_etl")
        workflow.add_node("extract", DataExtractionNode())
        workflow.add_node("transform", DataTransformer())
        workflow.add_node("validate", DataValidationNode())
        workflow.add_node("load", DatabaseWriterNode())
        return workflow
```

### Error Handling
```python
# Comprehensive error handling with retry
error_config = {
    "retry_policy": {
        "max_attempts": 3,
        "backoff_multiplier": 2,
        "max_backoff": 60
    },
    "error_handlers": {
        "ValidationError": "return_400",
        "AuthenticationError": "return_401",
        "DatabaseError": "retry_then_fail"
    }
}
```

## 🧪 Testing Patterns

### QA Framework Integration
```python
# Automatic test generation
async def validate_application():
    tester = AutonomousQATester()

    # Auto-discover application
    await tester.discover_app(".")

    # Generate test personas
    personas = await tester.generate_personas()

    # Create test scenarios
    scenarios = await tester.generate_scenarios(personas)

    # Execute with reporting
    results = await tester.execute_tests()
    report = tester.generate_report("qa_report.html")

    assert results.success_rate > 95
```

### Performance Testing
```python
# Load testing configuration
load_test_config = {
    "scenarios": [
        {"name": "normal_load", "users": 100, "duration": "5m"},
        {"name": "peak_load", "users": 500, "duration": "2m"},
        {"name": "stress_test", "users": 1000, "duration": "1m"}
    ],
    "targets": {
        "response_time_p95": 100,  # ms
        "error_rate": 0.01,  # 1%
        "requests_per_second": 1000
    }
}
```

## 🌐 Integration Patterns

### External API Integration
```python
# Resilient API client with circuit breaker
api_client_config = {
    "base_url": "https://api.external.com",
    "timeout": 30,
    "retry_attempts": 3,
    "circuit_breaker": {
        "failure_threshold": 5,
        "recovery_timeout": 60,
        "expected_exception": "RequestException"
    }
}
```

### Message Queue Integration
```python
# Async task processing
queue_config = {
    "broker": "redis://localhost:6379",
    "queues": {
        "high_priority": {"max_workers": 10},
        "default": {"max_workers": 5},
        "low_priority": {"max_workers": 2}
    },
    "task_timeout": 300,
    "result_backend": "redis://localhost:6379/1"
}
```

## 📦 Deployment Patterns

### Container Configuration
```yaml
# Multi-stage Docker build
FROM python:3.11-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
CMD ["your-app", "server"]
```

### Kubernetes Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app-deployment
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    spec:
      containers:
      - name: app
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

## 🎯 Decision Matrix

| Requirement | Pattern | Implementation |
|------------|---------|----------------|
| <5ms response | Direct execution | Bypass MCP routing |
| LLM integration | MCP routing | Use tool interface |
| >10 workflows | Class-based | Template inheritance |
| Multi-tenant | Middleware DB | TenantMixin |
| High security | ABAC + AI | ABACPermissionEvaluator |
| Real-time updates | WebSocket | RealtimeMiddleware |
| Batch processing | Queue workers | Redis + AsyncWorkers |

## 📋 Compliance Checklist

- [ ] GDPR: Data export/deletion endpoints
- [ ] SOC2: Audit logging enabled
- [ ] HIPAA: Encryption at rest/transit
- [ ] PCI: No credit card data in logs
- [ ] ISO27001: Access control matrix
- [ ] CCPA: User consent management

## 🚨 Anti-Patterns to Avoid

1. **Manual ORM Models** → Use middleware base models
2. **Direct FastAPI** → Use create_gateway()
3. **Custom auth** → Use enterprise auth stack
4. **String node names** → End with "Node" suffix
5. **Missing result wrapper** → PythonCodeNode needs {"result": ...}
6. **Hardcoded paths** → Use path utilities
7. **Sync database ops** → Always use async
8. **No monitoring** → Enable metrics by default
9. **Manual testing only** → Use QA framework
10. **Single routing strategy** → Use hybrid approach
