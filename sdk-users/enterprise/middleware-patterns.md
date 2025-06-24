# Enterprise Middleware Patterns

*Advanced middleware architecture for production applications*

## 🏗️ Enterprise Middleware Architecture

### Complete Enterprise Stack
```python
from kailash.middleware import create_gateway
from kailash.middleware.auth import KailashJWTAuth
from kailash.middleware.database import SessionManager
from kailash.runtime.access_controlled import AccessControlledRuntime

# Production-grade gateway with all enterprise features
enterprise_gateway = create_gateway(
    title="Enterprise Application Platform",
    version="1.0.0",
    description="Production Kailash SDK deployment",

    # Security Configuration
    cors_origins=[
        "https://app.company.com",
        "https://admin.company.com",
        "https://api.company.com"
    ],

    # Performance Settings
    worker_processes=8,
    max_connections=1000,
    connection_pool_size=100,
    request_timeout=300,

    # Feature Flags
    enable_docs=True,
    enable_monitoring=True,
    enable_compression=True,
    enable_caching=True,

    # Enterprise Features
    multi_tenant=True,
    audit_logging=True,
    rate_limiting=True,
    health_checks=True
)

# Access-controlled runtime
runtime = AccessControlledRuntime(
    access_control_strategy="hybrid",  # RBAC + ABAC
    audit_enabled=True,
    session_isolation=True,
    resource_limits={
        "max_memory_mb": 2048,
        "max_execution_time": 600,
        "max_concurrent_workflows": 20
    }
)

# Start enterprise server
enterprise_gateway.run(
    host="0.0.0.0",
    port=8000,
    ssl_context={
        "certfile": "/ssl/cert.pem",
        "keyfile": "/ssl/key.pem"
    }
)

```

## 🔐 Enterprise Authentication & Authorization

### JWT with Enterprise Features
```python
from kailash.middleware.auth import KailashJWTAuth, EnterpriseAuthConfig

# Enterprise JWT configuration
auth_config = EnterpriseAuthConfig(
    # JWT Settings
    secret_key="your-enterprise-jwt-secret-key",
    algorithm="RS256",              # RSA for enterprise security
    token_expiry_hours=8,           # Business hours
    refresh_token_enabled=True,
    refresh_token_expiry_days=30,

    # Session Management
    session_management=True,
    concurrent_sessions_limit=3,
    session_timeout_minutes=60,

    # Security Features
    rate_limiting=True,
    max_login_attempts=5,
    lockout_duration_minutes=15,

    # Compliance
    audit_logging=True,
    password_complexity=True,
    mfa_required=True,

    # Integration
    ldap_integration=True,
    saml_sso=True,
    oauth_providers=["google", "microsoft", "okta"]
)

# Apply to gateway
enterprise_gateway.add_auth(KailashJWTAuth(auth_config))

```

### Role-Based Access Control (RBAC)
```python
from kailash.access_control import AccessControlManager, RoleDefinition

# Define enterprise roles
roles = [
    RoleDefinition(
        name="admin",
        permissions=[
            "workflow:create", "workflow:execute", "workflow:delete",
            "user:manage", "system:configure", "audit:view"
        ],
        resource_limits={
            "max_workflows": 100,
            "max_executions_per_hour": 1000
        }
    ),
    RoleDefinition(
        name="data_scientist",
        permissions=[
            "workflow:create", "workflow:execute",
            "data:read", "model:train"
        ],
        resource_limits={
            "max_workflows": 20,
            "max_executions_per_hour": 100
        }
    ),
    RoleDefinition(
        name="business_user",
        permissions=[
            "workflow:execute", "report:view"
        ],
        resource_limits={
            "max_workflows": 5,
            "max_executions_per_hour": 50
        }
    )
]

# Enterprise access control
access_manager = AccessControlManager(
    strategy="rbac",
    roles=roles,
    enforce_resource_limits=True,
    audit_access_attempts=True
)

```

### Attribute-Based Access Control (ABAC)
```python
# Advanced ABAC policies
abac_policies = {
    "data_access": {
        "condition": "user.department == data.department AND user.clearance >= data.classification",
        "effect": "allow"
    },
    "time_based": {
        "condition": "current_time.hour >= 9 AND current_time.hour <= 17 AND current_time.weekday < 5",
        "effect": "allow"
    },
    "geo_restriction": {
        "condition": "user.location.country IN ['US', 'CA', 'GB']",
        "effect": "allow"
    }
}

access_manager = AccessControlManager(
    strategy="abac",
    policies=abac_policies,
    dynamic_evaluation=True
)

```

## 🌐 Multi-Tenant Architecture

### Tenant Isolation
```python
from kailash.middleware.tenancy import TenantManager

# Enterprise tenant management
tenant_manager = TenantManager(
    isolation_level="strict",       # Strict data isolation
    database_per_tenant=True,      # Separate databases
    resource_quotas={
        "max_workflows_per_tenant": 100,
        "max_storage_gb": 10,
        "max_api_calls_per_day": 10000
    },
    custom_domains=True,           # tenant.company.com
    billing_integration=True
)

# Tenant-aware session creation
async def create_tenant_session('tenant_id', 'user_id'):
    # Validate tenant
    tenant = await tenant_manager.get_tenant(tenant_id)
    if not tenant.active:
        raise ValueError("Tenant is not active")

    # Check resource quotas
    if not await tenant_manager.check_quota(tenant_id, "workflows"):
        raise ValueError("Tenant has exceeded workflow quota")

    # Create isolated session
    session_id = await enterprise_gateway.agent_ui.create_session(
        user_id=f"{tenant_id}:{user_id}",
        metadata={
            "tenant_id": tenant_id,
            "tenant_name": tenant.name,
            "isolation_level": "strict",
            "resource_limits": tenant.resource_limits,
            "billing_plan": tenant.billing_plan
        }
    )

    return session_id

```

### Tenant-Specific Configuration
```python
# Tenant configuration management
class TenantConfig:
    def __init__(self, 'tenant_id'):
        self.tenant_id = tenant_id
        self.config = self.load_tenant_config()

    def load_tenant_config(self):
        return {
            "features": {
                "ai_enabled": True,
                "advanced_analytics": True,
                "custom_nodes": False
            },
            "integrations": {
                "allowed_apis": ["openai", "anthropic"],
                "database_connections": ["postgresql"],
                "storage_providers": ["s3", "gcs"]
            },
            "limits": {
                "max_workflow_nodes": 50,
                "max_execution_time": 3600,
                "max_memory_mb": 4096
            }
        }

    def create_tenant_workflow(self, workflow_config):
        # Apply tenant-specific limits and features
        if len(workflow_config["nodes"]) > self.config["limits"]["max_workflow_nodes"]:
            raise ValueError("Workflow exceeds node limit")

        # Filter allowed node types
        allowed_nodes = self.get_allowed_node_types()
        for node in workflow_config["nodes"]:
            if node["type"] not in allowed_nodes:
                raise ValueError(f"Node type {node['type']} not allowed for tenant")

        return workflow_config

```

## 🚀 Real-Time Enterprise Communication

### WebSocket with Authentication
```python
from kailash.middleware.realtime import EnterpriseRealtimeMiddleware

# Enterprise WebSocket handling
class AuthenticatedWebSocketManager:
    def __init__(self, gateway):
        self.gateway = gateway
        self.active_connections = {}

    async def connect(self, websocket, 'token'):
        # Verify JWT token
        try:
            payload = jwt.decode(token, secret_key, algorithms=["RS256"])
            user_id = payload["user_id"]
            tenant_id = payload["tenant_id"]

            # Check session validity
            session_valid = await self.gateway.auth.verify_session(user_id)
            if not session_valid:
                await websocket.close(code=4001, reason="Invalid session")
                return

            # Register connection
            connection_id = f"{tenant_id}:{user_id}:{uuid.uuid4()}"
            self.active_connections[connection_id] = {
                "websocket": websocket,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "connected_at": datetime.utcnow(),
                "last_activity": datetime.utcnow()
            }

            await websocket.accept()
            await self.send_welcome_message(websocket, user_id)

        except jwt.InvalidTokenError:
            await websocket.close(code=4001, reason="Invalid token")

    async def send_to_tenant(self, 'tenant_id', message: dict):
        """Send message to all users in a tenant"""
        tenant_connections = [
            conn for conn in self.active_connections.values()
            if conn["tenant_id"] == tenant_id
        ]

        for connection in tenant_connections:
            try:
                await connection["websocket"].send_json(message)
            except Exception as e:
                # Handle disconnected clients
                await self.remove_connection(connection)

```

### Event Streaming with Filtering
```python
from kailash.middleware.events import EventFilter, EventRouter

# Enterprise event filtering
class EnterpriseEventFilter:
    def __init__(self):
        self.filters = {
            "tenant_isolation": self.filter_by_tenant,
            "role_based": self.filter_by_role,
            "data_classification": self.filter_by_classification
        }

    def filter_by_tenant(self, event, user_context):
        """Ensure users only see events from their tenant"""
        if event.tenant_id != user_context.tenant_id:
            return False
        return True

    def filter_by_role(self, event, user_context):
        """Filter events based on user role"""
        required_permission = event.metadata.get("required_permission")
        if required_permission and required_permission not in user_context.permissions:
            return False
        return True

    def filter_by_classification(self, event, user_context):
        """Filter based on data classification"""
        event_classification = event.metadata.get("classification", "public")
        user_clearance = user_context.clearance_level

        classification_levels = {"public": 1, "internal": 2, "confidential": 3, "secret": 4}

        return classification_levels.get(user_clearance, 0) >= classification_levels.get(event_classification, 0)

```

## 📊 Performance & Monitoring

### Enterprise Monitoring Setup
```python
from kailash.monitoring import EnterpriseMonitor, MetricsCollector

# Comprehensive monitoring
monitor = EnterpriseMonitor(
    # Application Metrics
    app_metrics=True,
    business_metrics=True,

    # Infrastructure Metrics
    system_metrics=True,
    database_metrics=True,
    cache_metrics=True,

    # Security Metrics
    auth_metrics=True,
    access_metrics=True,

    # Export Configuration
    prometheus_enabled=True,
    grafana_dashboards=True,
    alertmanager_integration=True,

    # Storage
    metrics_retention_days=90,
    high_resolution_retention_hours=24
)

# Custom business metrics
class BusinessMetricsCollector:
    def __init__(self):
        self.metrics = {
            "workflows_completed_by_department": Counter(),
            "revenue_generated_by_workflow": Histogram(),
            "user_satisfaction_score": Gauge(),
            "sla_compliance_rate": Histogram()
        }

    def record_workflow_completion(self, 'department', revenue: float):
        self.metrics["workflows_completed_by_department"].labels(
            department=department
        ).inc()

        self.metrics["revenue_generated_by_workflow"].observe(revenue)

    def record_sla_compliance(self, execution_time: float, sla_limit: float):
        compliance_rate = min(1.0, sla_limit / execution_time)
        self.metrics["sla_compliance_rate"].observe(compliance_rate)

```

### Health Checks & Alerting
```python
from kailash.health import HealthChecker, AlertManager

# Enterprise health monitoring
health_checker = HealthChecker(
    checks=[
        "database_connectivity",
        "cache_status",
        "external_api_health",
        "disk_usage",
        "memory_usage",
        "active_sessions_count",
        "workflow_execution_rate"
    ],
    check_interval_seconds=30,
    failure_threshold=3,
    recovery_threshold=2
)

# Alert configuration
alert_manager = AlertManager(
    channels=[
        {
            "type": "slack",
            "webhook_url": "https://hooks.slack.com/services/...",
            "channel": "#platform-alerts",
            "severity_levels": ["critical", "warning"]
        },
        {
            "type": "pagerduty",
            "integration_key": "your-pagerduty-key",
            "severity_levels": ["critical"]
        },
        {
            "type": "email",
            "smtp_config": {...},
            "recipients": ["devops@company.com"],
            "severity_levels": ["critical", "warning", "info"]
        }
    ],

    # Alert rules
    rules=[
        {
            "name": "High workflow failure rate",
            "condition": "workflow_failure_rate > 0.05",
            "severity": "critical",
            "duration": "5m"
        },
        {
            "name": "Database connection issues",
            "condition": "database_health == false",
            "severity": "critical",
            "duration": "1m"
        },
        {
            "name": "High memory usage",
            "condition": "memory_usage > 0.8",
            "severity": "warning",
            "duration": "10m"
        }
    ]
)

```

## 🔄 Integration with Enterprise Systems

### Enterprise Directory Integration
```python
from kailash.integrations import LDAPIntegration, SAMLIntegration

# Active Directory / LDAP integration
ldap_config = LDAPIntegration(
    server="ldaps://ldap.company.com:636",
    base_dn="dc=company,dc=com",
    user_dn="ou=Users,dc=company,dc=com",
    group_dn="ou=Groups,dc=company,dc=com",

    # Authentication
    bind_user="cn=kailash-service,ou=ServiceAccounts,dc=company,dc=com",
    bind_password="service-account-password",

    # User mapping
    user_attributes={
        "username": "sAMAccountName",
        "email": "mail",
        "first_name": "givenName",
        "last_name": "sn",
        "department": "department",
        "title": "title"
    },

    # Group mapping for roles
    group_role_mapping={
        "CN=KailashAdmins,OU=Groups,DC=company,DC=com": "admin",
        "CN=DataScientists,OU=Groups,DC=company,DC=com": "data_scientist",
        "CN=BusinessUsers,OU=Groups,DC=company,DC=com": "business_user"
    }
)

# SAML SSO integration
saml_config = SAMLIntegration(
    entity_id="https://kailash.company.com",
    acs_url="https://kailash.company.com/auth/saml/acs",
    sso_url="https://sso.company.com/saml/login",

    # Certificate configuration
    x509_cert_file="/ssl/saml.crt",
    private_key_file="/ssl/saml.key",

    # Attribute mapping
    attribute_mapping={
        "email": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
        "first_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
        "last_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
        "groups": "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups"
    }
)

```

### Enterprise Database Integration
```python
from kailash.middleware.database import EnterpriseSessionManager

# Enterprise database configuration
db_config = {
    "primary": {
        "url": "postgresql://user:pass@primary-db-cluster:5432/kailash",
        "pool_size": 20,
        "max_overflow": 50,
        "pool_recycle": 3600
    },
    "replica": {
        "url": "postgresql://user:pass@replica-db-cluster:5432/kailash",
        "pool_size": 10,
        "max_overflow": 20
    },
    "analytics": {
        "url": "postgresql://user:pass@analytics-db:5432/kailash_analytics",
        "pool_size": 5,
        "max_overflow": 10
    }
}

# Multi-database session manager
session_manager = EnterpriseSessionManager(
    databases=db_config,
    read_write_splitting=True,
    connection_pooling=True,
    query_optimization=True,

    # Enterprise features
    encryption_at_rest=True,
    backup_integration=True,
    compliance_logging=True
)

```

## 🛡️ Security Hardening

### Advanced Security Configuration
```python
from kailash.security import EnterpriseSecurityConfig

security_config = EnterpriseSecurityConfig(
    # Encryption
    encryption_at_rest=True,
    encryption_in_transit=True,
    key_rotation_days=90,

    # Network Security
    ip_whitelist=["10.0.0.0/8", "172.16.0.0/12"],
    require_ssl=True,
    ssl_version="TLSv1.3",

    # Input Validation
    input_sanitization=True,
    sql_injection_protection=True,
    xss_protection=True,

    # Audit & Compliance
    detailed_audit_logging=True,
    audit_log_retention_days=2555,  # 7 years
    compliance_frameworks=["SOC2", "GDPR", "HIPAA"],

    # Threat Protection
    ddos_protection=True,
    rate_limiting_per_user=True,
    anomaly_detection=True,

    # Data Protection
    pii_detection=True,
    data_loss_prevention=True,
    field_level_encryption=True
)

```

## 📈 Scaling Patterns

### Horizontal Scaling
```python
from kailash.scaling import HorizontalScaler

# Auto-scaling configuration
scaler = HorizontalScaler(
    min_instances=2,
    max_instances=20,
    target_cpu_utilization=70,
    target_memory_utilization=80,

    # Scaling policies
    scale_up_cooldown=300,    # 5 minutes
    scale_down_cooldown=600,  # 10 minutes

    # Health-based scaling
    health_check_grace_period=120,
    unhealthy_threshold=2,

    # Load balancing
    load_balancer_type="application",
    sticky_sessions=True,
    session_affinity_duration=3600
)

# Kubernetes integration
k8s_config = {
    "deployment_name": "terrene-foundation",
    "namespace": "production",
    "resource_requests": {
        "cpu": "500m",
        "memory": "1Gi"
    },
    "resource_limits": {
        "cpu": "2000m",
        "memory": "4Gi"
    }
}

```

## 🚀 Optimized Middleware Example

Here's a complete example showing how to maximize performance by using SDK nodes throughout the middleware layer:

```python
"""
Optimized Middleware Example - Maximizing SDK Node Usage
=======================================================

This example demonstrates how to maximize performance by using Kailash SDK nodes,
workflows, and runtime throughout the middleware layer instead of custom code.

Key optimizations demonstrated:
1. Session management using workflows
2. Event processing with BatchProcessorNode
3. Credential management with RotatingCredentialNode
4. Database operations with AsyncSQLDatabaseNode
5. Caching with DataTransformer (as cache)
6. Rate limiting with SDK patterns
7. Monitoring with DataLineageNode
"""

import asyncio
import logging
from datetime import datetime, timedelta

from kailash.middleware import AgentUIMiddleware, EventStream
from kailash.nodes.admin import PermissionCheckNode
from kailash.nodes.data import AsyncSQLDatabaseNode
from kailash.nodes.enterprise import BatchProcessorNode, DataLineageNode
from kailash.nodes.security import AuditLogNode, RotatingCredentialNode
from kailash.nodes.transform import DataTransformer
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)


class OptimizedAgentUIMiddleware(AgentUIMiddleware):
    """
    Enhanced AgentUIMiddleware that maximizes SDK node usage.

    This implementation replaces custom code with SDK nodes for:
    - Session management
    - Event processing
    - Database operations
    - Caching
    - Security
    - Monitoring
    """

    def __init__(self, **kwargs):
        """Initialize with additional SDK nodes for optimization."""
        # Store database_url before calling super()
        self.database_url = kwargs.get("database_url")
        super().__init__(**kwargs)

        # Initialize additional SDK nodes for performance
        self._init_performance_nodes()

        # Create workflow-based processors
        self._init_workflow_processors()

    def _init_performance_nodes(self):
        """Initialize SDK nodes for performance optimization."""

        # Batch processor for event handling
        self.event_batch_processor = BatchProcessorNode(
            name="event_batch_processor"
        )

        # Rotating credentials for security
        self.rotating_credentials = RotatingCredentialNode(
            name="middleware_rotating_creds",
            credential_name="middleware_secrets",
            rotation_interval_days=30
        )

        # Data lineage for tracking
        self.data_lineage = DataLineageNode(
            name="middleware_lineage_tracker"
        )

        # Permission checker for authorization
        self.permission_checker = PermissionCheckNode(
            name="middleware_permission_check"
        )

        # Audit logger for compliance
        self.audit_logger = AuditLogNode(
            name="middleware_audit_log"
        )

        # Data transformer for caching
        self.cache_transformer = DataTransformer(
            name="middleware_cache"
        )

        # Async SQL node for database operations
        if self.enable_persistence:
            self.async_db = AsyncSQLDatabaseNode(
                name="middleware_async_db",
                connection_string=self.database_url
            )

    def _init_workflow_processors(self):
        """Create workflow-based processors for common operations."""

        # Session management workflow
        self.session_workflow = (
            WorkflowBuilder("session_management")
            .add_node("PermissionCheckNode", "check_permissions")
            .add_node("DataTransformer", "validate_session", {
                "transformation_type": "validation"
            })
            .add_node("AsyncSQLDatabaseNode", "store_session", {
                "query": "INSERT INTO sessions (id, user_id, data) VALUES (?, ?, ?)"
            })
            .add_connection("check_permissions", "result", "validate_session", "input_data")
            .add_connection("validate_session", "result", "store_session", "params")
            .build()
        )

        # Event processing workflow
        self.event_workflow = (
            WorkflowBuilder("event_processing")
            .add_node("BatchProcessorNode", "batch_events", {
                "batch_size": 100,
                "timeout": 5.0
            })
            .add_node("DataLineageNode", "track_lineage")
            .add_node("AuditLogNode", "log_events")
            .add_connection("batch_events", "result", "track_lineage", "data")
            .add_connection("track_lineage", "result", "log_events", "events")
            .build()
        )

    async def process_agent_request(self, request_data):
        """Process agent request using SDK nodes."""

        # Use permission checker node
        permission_result = await self.permission_checker.run_async({
            "operation": "check_permission",
            "user_id": request_data.get("user_id"),
            "resource_id": request_data.get("workflow_id"),
            "permission": "execute"
        })

        if not permission_result["result"]["check"]["allowed"]:
            raise PermissionError("Access denied")

        # Process with batch processor for efficiency
        batch_result = await self.event_batch_processor.run_async({
            "items": [request_data],
            "process_function": self._process_single_request
        })

        # Track data lineage
        await self.data_lineage.run_async({
            "source": "agent_request",
            "target": "workflow_execution",
            "data": batch_result["result"]
        })

        return batch_result["result"][0]

    async def handle_websocket_connection(self, websocket, path):
        """Handle WebSocket using SDK components."""

        # Rotate credentials if needed
        creds_result = await self.rotating_credentials.run_async({
            "action": "get_current"
        })

        # Use SDK-based session management
        session_result = await self.runtime.execute_workflow_async(
            self.session_workflow,
            {"websocket": websocket, "credentials": creds_result["result"]}
        )

        # Process events with workflow
        while True:
            try:
                message = await websocket.recv()
                event_result = await self.runtime.execute_workflow_async(
                    self.event_workflow,
                    {"event": message, "session": session_result["results"]}
                )

                await websocket.send(json.dumps(event_result))

            except websockets.exceptions.ConnectionClosed:
                break


# Usage example
async def main():
    """Demonstrate optimized middleware usage."""

    # Create optimized middleware
    middleware = OptimizedAgentUIMiddleware(
        database_url="postgresql://user:pass@localhost/kailash",
        enable_persistence=True,
        enable_auth=True,
        enable_monitoring=True
    )

    # All operations now use SDK nodes for maximum performance
    print("✅ Middleware initialized with SDK node optimization")
    print("📊 Performance improvements:")
    print("  - 70% reduction in custom code")
    print("  - Built-in caching and batching")
    print("  - Automatic credential rotation")
    print("  - Comprehensive audit logging")
    print("  - Data lineage tracking")


if __name__ == "__main__":
    asyncio.run(main())
```

This optimized example demonstrates:
- **SDK Node Usage**: Replaces custom implementations with SDK nodes
- **Workflow Integration**: Uses workflows for complex operations
- **Performance**: Batch processing and caching for efficiency
- **Security**: Built-in credential rotation and permission checking
- **Monitoring**: Automatic data lineage and audit logging
- **Maintainability**: Less custom code, more reliability

## 📚 Quick Reference

### Enterprise Setup Checklist
- [ ] JWT authentication with enterprise features
- [ ] RBAC/ABAC access control
- [ ] Multi-tenant isolation
- [ ] Real-time communication with authentication
- [ ] Comprehensive monitoring and alerting
- [ ] Enterprise directory integration
- [ ] Database clustering and backup
- [ ] Security hardening and compliance
- [ ] Horizontal scaling configuration
- [ ] CI/CD pipeline integration

### Key Components
- **AgentUIMiddleware** - Session management and workflow execution
- **RealtimeMiddleware** - WebSocket communication with auth
- **APIGateway** - REST API with enterprise features
- **AccessControlledRuntime** - RBAC/ABAC enforcement
- **EnterpriseMonitor** - Comprehensive monitoring
- **TenantManager** - Multi-tenant isolation

### Related Guides
- [Session Management](session-management-guide.md) - Advanced session patterns
- [Security Guide](enterprise-security-guide.md) - Comprehensive security
- [Performance](performance-optimization.md) - Scale and optimization
- [Deployment](production-deployment.md) - Production deployment
