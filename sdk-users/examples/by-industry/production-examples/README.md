# Production Patterns & Real App Implementations

*Proven patterns from real production applications*

## 🏭 Overview

This directory contains production-tested patterns extracted from real applications in the `apps/` directory, providing concrete examples of how to build enterprise-grade solutions with Kailash SDK.

## 📁 Real Application Patterns

### AI Registry Application (Production RAG)
**Source**: `apps/ai_registry_app/`
**Scale**: 15.9x faster than Django equivalent

```python
# Advanced RAG implementation with hierarchical search
from kailash import Workflow
from kailash.nodes.ai import EmbeddingGeneratorNode, LLMAgentNode
from kailash.nodes.data import VectorStoreNode, SearchRankingNode

workflow = Workflow("production_rag", name="Production RAG Pipeline")

# Multi-stage embedding generation
workflow.add_node("embedder", EmbeddingGeneratorNode(
    provider="openai",
    model="text-embedding-ada-002",
    batch_size=100,           # Production batch processing
    retry_policy="exponential"
))

# Hierarchical vector search
workflow.add_node("vector_search", VectorStoreNode(
    provider="pinecone",
    index_name="production-knowledge",
    top_k=50,                 # Initial broad search
    include_metadata=True
))

# Re-ranking for precision
workflow.add_node("reranker", SearchRankingNode(
    model="cross-encoder/ms-marco-MiniLM-L-12-v2",
    top_k=10,                 # Final precision results
    score_threshold=0.7
))

# Context-aware response generation
workflow.add_node("generator", LLMAgentNode(
    provider="openai",
    model="gpt-4",
    temperature=0.1,          # Low temperature for accuracy
    max_tokens=2000,
    system_prompt="""You are a knowledgeable assistant. Use only the provided context to answer questions accurately and concisely."""
))

# Production error handling
workflow.add_node("fallback_handler", LLMAgentNode(
    provider="openai",
    model="gpt-3.5-turbo",    # Faster fallback model
    system_prompt="Provide a helpful response when primary search fails."
))

```

### QA Agentic Testing (27 Personas)
**Source**: `apps/qa_agentic_testing/`
**Pattern**: Multi-agent coordination with specialized roles

```python
# 27 testing personas with specialized capabilities
testing_personas = [
    {
        "id": "security_tester",
        "role": "Security Testing Specialist",
        "skills": ["penetration_testing", "vulnerability_scanning", "compliance"],
        "tools": ["owasp_zap", "burp_suite", "security_audit"],
        "focus_areas": ["authentication", "authorization", "data_protection"]
    },
    {
        "id": "performance_tester",
        "role": "Performance Testing Engineer",
        "skills": ["load_testing", "stress_testing", "benchmarking"],
        "tools": ["jmeter", "k6", "artillery"],
        "focus_areas": ["response_time", "throughput", "scalability"]
    },
    {
        "id": "ui_ux_tester",
        "role": "UI/UX Testing Specialist",
        "skills": ["usability_testing", "accessibility", "cross_browser"],
        "tools": ["selenium", "cypress", "axe_core"],
        "focus_areas": ["user_experience", "visual_regression", "accessibility"]
    }
    # ... 24 more personas
]

# Multi-agent testing coordination
from kailash.nodes.ai.a2a import A2ACoordinatorNode
from kailash.nodes.ai.self_organizing import AgentPoolManagerNode

workflow = Workflow("qa_testing_suite", name="QA Agentic Testing")

# Agent pool for 27 personas
workflow.add_node("agent_pool", AgentPoolManagerNode(
    max_active_agents=27,
    agent_definitions=testing_personas,
    specialization_enabled=True,
    dynamic_allocation=True
))

# Intelligent test coordination
workflow.add_node("test_coordinator", A2ACoordinatorNode(
    coordination_strategy="expertise_based",
    task_distribution="parallel",
    result_aggregation=True
))

# Test execution pipeline
def execute_comprehensive_testing(app_under_test):
    return runtime.execute(workflow, parameters={
        "test_coordinator": {
            "action": "coordinate_testing",
            "target_application": app_under_test,
            "testing_strategy": "comprehensive",
            "parallel_execution": True,
            "coverage_requirements": {
                "functional": 0.95,
                "security": 0.90,
                "performance": 0.85,
                "usability": 0.80
            }
        }
    })

```

### Studio App (Complete Enterprise Application)
**Source**: `apps/studio/`
**Pattern**: Full-stack enterprise application with real-time features

```python
# Complete enterprise application stack
from kailash.middleware import create_gateway
from kailash.middleware.auth import KailashJWTAuth
from kailash.middleware.realtime import RealtimeMiddleware

# Enterprise gateway with all features
studio_gateway = create_gateway(
    title="Kailash Studio",
    version="1.0.0",

    # Enterprise features
    auth_enabled=True,
    websocket_enabled=True,
    database_enabled=True,
    monitoring_enabled=True,

    # Performance configuration
    worker_processes=4,
    max_connections=1000,
    connection_pool_size=50,

    # Security
    cors_origins=["https://studio.kailash.ai"],
    rate_limiting=True,
    audit_logging=True
)

# Advanced authentication
auth_config = {
    "jwt_secret": "production-jwt-secret",
    "token_expiry_hours": 8,
    "refresh_tokens": True,
    "session_management": True,
    "mfa_enabled": True,
    "oauth_providers": ["google", "github", "microsoft"]
}

studio_gateway.add_auth(KailashJWTAuth(auth_config))

# Real-time collaboration features
@studio_gateway.websocket("/collaborate")
async def collaboration_endpoint(websocket, session_id):
    """Real-time collaboration for workflow building"""
    await websocket.accept()

    # Join collaboration room
    room_id = f"workspace_{session_id}"
    await studio_gateway.realtime.join_room(websocket, room_id)

    try:
        while True:
            # Receive collaboration events
            data = await websocket.receive_json()

            # Broadcast to other users in room
            await studio_gateway.realtime.broadcast_to_room(
                room_id,
                {
                    "type": data["type"],
                    "payload": data["payload"],
                    "user_id": data["user_id"],
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
    except Exception as e:
        await studio_gateway.realtime.leave_room(websocket, room_id)

```

## 🔧 Production Deployment Patterns

### Docker Production Setup
```dockerfile
# Production Dockerfile
FROM python:3.11-slim-bullseye

# Security updates
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -r kailash && useradd -r -g kailash kailash

# Application setup
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R kailash:kailash /app
USER kailash

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production command
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "main:app"]
```

### Kubernetes Production Deployment
```yaml
# production-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kailash-production
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: kailash-production
  template:
    metadata:
      labels:
        app: kailash-production
    spec:
      containers:
      - name: kailash
        image: kailash/production:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: kailash-secrets
              key: database-url
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: kailash-secrets
              key: jwt-secret
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
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

---
apiVersion: v1
kind: Service
metadata:
  name: kailash-production-service
  namespace: production
spec:
  selector:
    app: kailash-production
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: LoadBalancer

---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: kailash-production-ingress
  namespace: production
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  tls:
  - hosts:
    - api.kailash.ai
    secretName: kailash-tls
  rules:
  - host: api.kailash.ai
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: kailash-production-service
            port:
              number: 80
```

## 📊 Performance Optimization Patterns

### Database Optimization (15.9x Performance Gain)
```python
# High-performance database configuration
from kailash.nodes.data import AsyncSQLDatabaseNode

# Optimized database node
workflow.add_node("optimized_db", AsyncSQLDatabaseNode(
    connection_string="postgresql://user:pass@db-cluster:5432/production",

    # Connection pooling for scale
    pool_size=20,
    max_overflow=50,
    pool_recycle=3600,
    pool_pre_ping=True,

    # Query optimization
    query_cache_enabled=True,
    query_cache_size=1000,
    prepared_statements=True,

    # Async performance
    async_execution=True,
    batch_size=1000,
    connection_timeout=30,

    # Monitoring
    performance_monitoring=True,
    slow_query_threshold=1.0
))

# Batch processing pattern
workflow.add_node("batch_processor", PythonCodeNode(
    name="batch_processor",
    code='''
# Process data in optimized batches
processed_batches = []
batch_size = 1000

for i in range(0, len(data), batch_size):
    batch = data[i:i + batch_size]

    # Parallel processing within batch
    batch_result = process_batch_parallel(batch)
    processed_batches.append(batch_result)

    # Memory management
    if i % (batch_size * 10) == 0:
        gc.collect()

result = {"processed": processed_batches, "total_processed": len(data)}
''',
    input_types={"data": list}
))

```

### Caching Strategies
```python
from kailash.middleware.cache import ProductionCacheManager

# Multi-level caching
cache_manager = ProductionCacheManager(
    levels=[
        {
            "name": "memory",
            "type": "redis",
            "connection": "redis://redis-cluster:6379/0",
            "ttl": 300,           # 5 minutes
            "max_size": "1GB"
        },
        {
            "name": "disk",
            "type": "file_system",
            "path": "/cache/disk",
            "ttl": 3600,          # 1 hour
            "max_size": "10GB"
        },
        {
            "name": "cdn",
            "type": "cloudflare",
            "api_key": "cf-api-key",
            "ttl": 86400,         # 24 hours
            "geographic_distribution": True
        }
    ]
)

# Cache-aware workflow
@cache_manager.cached(ttl=600, key_pattern="workflow_{workflow_id}_{params_hash}")
async def execute_cached_workflow('workflow_id', parameters: dict):
    """Execute workflow with intelligent caching"""
    return await runtime.execute(workflow, parameters=parameters)

```

## 🛡️ Production Security Patterns

### Security Hardening
```python
from kailash.security import ProductionSecurityConfig

# Production security configuration
security_config = ProductionSecurityConfig(
    # Input validation
    input_sanitization=True,
    sql_injection_protection=True,
    xss_protection=True,
    csrf_protection=True,

    # Encryption
    encryption_at_rest=True,
    encryption_in_transit=True,
    field_level_encryption=["ssn", "credit_card", "personal_data"],

    # Access control
    rate_limiting_per_endpoint=True,
    ip_whitelisting=True,
    geo_blocking=["CN", "RU", "KP"],  # Block specific countries

    # Monitoring
    intrusion_detection=True,
    anomaly_detection=True,
    audit_logging=True,

    # Compliance
    gdpr_compliance=True,
    hipaa_compliance=True,
    sox_compliance=True
)

# Security middleware stack
security_middleware = [
    "rate_limiter",
    "ip_filter",
    "input_validator",
    "auth_verifier",
    "audit_logger",
    "threat_detector"
]

```

### Threat Detection
```python
from kailash.nodes.security import ThreatDetectionNode

workflow.add_node("threat_detector", ThreatDetectionNode(
    detection_rules=[
        {
            "name": "brute_force_login",
            "pattern": "failed_login_count > 5 in 5_minutes",
            "action": "block_ip",
            "duration": 3600
        },
        {
            "name": "sql_injection_attempt",
            "pattern": "contains_sql_keywords AND special_characters",
            "action": "block_request",
            "severity": "high"
        },
        {
            "name": "unusual_data_access",
            "pattern": "data_access_volume > 10x_baseline",
            "action": "alert_security_team",
            "severity": "medium"
        }
    ],

    # Machine learning for advanced detection
    ml_enabled=True,
    anomaly_threshold=0.95,
    learning_period_days=30,

    # Integration
    siem_integration=True,
    alert_channels=["slack", "email", "sms"]
))

```

## 📈 Monitoring & Observability

### Production Monitoring Stack
```python
from kailash.monitoring import ProductionMonitor

# Comprehensive monitoring setup
monitor = ProductionMonitor(
    # Application metrics
    application_metrics={
        "workflow_execution_time": "histogram",
        "workflow_success_rate": "gauge",
        "active_sessions": "gauge",
        "api_request_rate": "counter",
        "database_connection_pool": "gauge"
    },

    # Business metrics
    business_metrics={
        "revenue_per_workflow": "histogram",
        "user_satisfaction_score": "gauge",
        "feature_adoption_rate": "counter",
        "conversion_rate": "gauge"
    },

    # Infrastructure metrics
    infrastructure_metrics={
        "cpu_usage": "gauge",
        "memory_usage": "gauge",
        "disk_io": "counter",
        "network_io": "counter"
    },

    # Export configuration
    exporters=["prometheus", "datadog", "newrelic"],
    retention_policy="30d",
    high_resolution_retention="24h"
)

# Custom dashboards
dashboards = {
    "executive": {
        "metrics": ["revenue_per_workflow", "user_satisfaction_score", "conversion_rate"],
        "refresh_interval": "5m",
        "alerts": ["sla_breach", "revenue_drop"]
    },
    "engineering": {
        "metrics": ["workflow_execution_time", "error_rate", "cpu_usage"],
        "refresh_interval": "30s",
        "alerts": ["high_error_rate", "performance_degradation"]
    },
    "operations": {
        "metrics": ["active_sessions", "database_connections", "disk_usage"],
        "refresh_interval": "1m",
        "alerts": ["resource_exhaustion", "service_down"]
    }
}

```

### Alerting & Incident Response
```python
from kailash.alerting import AlertManager, IncidentResponse

# Production alerting
alert_manager = AlertManager(
    channels=[
        {
            "name": "critical_alerts",
            "type": "pagerduty",
            "escalation_policy": "platform_team",
            "severity_levels": ["critical"]
        },
        {
            "name": "team_notifications",
            "type": "slack",
            "channel": "#platform-alerts",
            "severity_levels": ["warning", "critical"]
        }
    ],

    # Alert rules
    rules=[
        {
            "name": "service_down",
            "condition": "up == 0",
            "severity": "critical",
            "duration": "1m",
            "runbook_url": "https://wiki.company.com/runbooks/service-down"
        },
        {
            "name": "high_error_rate",
            "condition": "error_rate > 0.05",
            "severity": "warning",
            "duration": "5m",
            "runbook_url": "https://wiki.company.com/runbooks/error-rate"
        }
    ]
)

# Automated incident response
incident_response = IncidentResponse(
    auto_remediation={
        "high_memory_usage": "restart_service",
        "database_connection_exhaustion": "scale_connection_pool",
        "disk_full": "cleanup_logs"
    },

    escalation_matrix={
        "critical": ["platform_team", "engineering_manager", "cto"],
        "warning": ["platform_team"],
        "info": ["platform_team"]
    }
)

```

## 📚 Production Deployment Checklist

### Pre-Production Validation
- [ ] **Performance Testing**: Load, stress, and endurance testing completed
- [ ] **Security Audit**: Penetration testing and vulnerability assessment
- [ ] **Compliance Review**: GDPR, HIPAA, SOX compliance verification
- [ ] **Disaster Recovery**: Backup and recovery procedures tested
- [ ] **Monitoring Setup**: All dashboards, alerts, and runbooks ready
- [ ] **Documentation**: Deployment, operational, and troubleshooting docs
- [ ] **Team Training**: On-call rotation and incident response training

### Production Deployment Steps
1. **Blue-Green Deployment**: Zero-downtime deployment strategy
2. **Feature Flags**: Gradual rollout with instant rollback capability
3. **Health Checks**: Comprehensive application and dependency health
4. **Monitoring Activation**: Real-time monitoring and alerting
5. **Performance Validation**: Baseline performance metrics established
6. **Security Validation**: Security controls and audit trails active

### Post-Deployment Operations
- [ ] **Performance Monitoring**: Continuous performance baseline tracking
- [ ] **Security Monitoring**: 24/7 threat detection and response
- [ ] **Capacity Planning**: Resource utilization and scaling projections
- [ ] **Incident Response**: On-call procedures and escalation paths
- [ ] **Regular Audits**: Security, compliance, and operational reviews
- [ ] **Continuous Improvement**: Performance optimization and feature enhancement

## 🔗 Related Resources

### Core Documentation
- [Enterprise Patterns](../enterprise/) - Enterprise architecture and security
- [Middleware Guide](../middleware/) - Production middleware setup
- [Developer Guide](../developer/) - Advanced development patterns

### Real Examples
- [Studio App](../../apps/studio/) - Complete enterprise application
- [AI Registry](../../apps/ai_registry_app/) - High-performance RAG system
- [QA Testing](../../apps/qa_agentic_testing/) - Multi-agent testing suite

### Infrastructure
- [Docker Deployment](../workflows/by-pattern/infrastructure/docker-deployment.md)
- [Kubernetes Patterns](../workflows/by-pattern/infrastructure/kubernetes-deployment.md)
- [Monitoring Setup](../workflows/by-pattern/monitoring/)

---

**Ready for Production?** These patterns are battle-tested in real applications processing millions of requests. Start with the pattern that matches your use case and scale from there.
