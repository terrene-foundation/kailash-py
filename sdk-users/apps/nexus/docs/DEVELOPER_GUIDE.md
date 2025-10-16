# Nexus Platform Developer Guide

*Advanced patterns for building production-ready multi-channel applications*

## 🎯 Overview

Nexus is a production-ready multi-channel orchestration platform that provides unified access to workflows across API, CLI, and MCP interfaces. This guide covers advanced patterns for developers building complex applications with Nexus.

## 🏗️ Architecture Deep Dive

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Nexus Platform                          │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │ API Channel │  │ CLI Channel │  │ MCP Channel │       │
│  │ (REST/WS)   │  │ (Commands)  │  │ (AI Tools)  │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
├─────────────────────────────────────────────────────────────┤
│                 Session & Event Router                     │
│  • Cross-channel communication                             │
│  • State synchronization                                   │
│  • Event propagation                                       │
├─────────────────────────────────────────────────────────────┤
│                 Enterprise Gateway                         │
│  • Authentication & Authorization                          │
│  • Rate limiting & Circuit breakers                        │
│  • Monitoring & Logging                                    │
│  • Caching & Performance optimization                      │
├─────────────────────────────────────────────────────────────┤
│                   Kailash SDK Core                         │
│  • WorkflowBuilder & Runtime                               │
│  • Node Library (110+ nodes)                               │
│  • Parameter resolution & validation                       │
└─────────────────────────────────────────────────────────────┘
```

### Key Design Principles

1. **Zero-Config Philosophy**: Start with no configuration, add complexity as needed
2. **Multi-Channel First**: Every workflow is accessible via all three channels
3. **Session Unification**: Maintain consistent state across all channels
4. **Progressive Enhancement**: Enable enterprise features incrementally
5. **Workflow-Native**: Built on Kailash SDK's workflow engine

## 🚀 Development Patterns

### Pattern 1: Advanced Workflow Registration

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

# Enterprise Nexus with full configuration
nexus = Nexus(
    # Multi-channel configuration
    api_port=8000,
    cli_port=8001,
    mcp_port=3001,

    # Enterprise security
    enable_auth=True,
    auth_strategy="oauth2",
    enable_rate_limiting=True,
    rate_limit_per_minute=1000,

    # Performance optimization
    enable_caching=True,
    cache_backend="redis",
    cache_ttl=300,

    # Monitoring & observability
    enable_monitoring=True,
    metrics_backend="prometheus",
    enable_tracing=True,

    # Reliability patterns
    enable_circuit_breaker=True,
    circuit_breaker_failure_threshold=5,
    max_concurrent_workflows=100,

    # Session management
    enable_sessions=True,
    session_backend="redis",
    session_ttl=3600
)

# Register workflow with metadata
workflow = WorkflowBuilder()
workflow.add_node("DataProcessorNode", "processor", {
    "input_format": "json",
    "output_format": "json",
    "validation_schema": "data_schema.json"
})

nexus.register("data_processor", workflow.build(), metadata={
    "version": "1.0.0",
    "description": "Process data with validation",
    "category": "data-processing",
    "tags": ["data", "validation", "json"],
    "required_permissions": ["data.read", "data.write"],
    "expected_parameters": {
        "input_data": {"type": "object", "required": True},
        "validation_rules": {"type": "object", "required": False}
    }
})
```

### Pattern 2: Multi-Channel Event Handling

```python
from nexus import Nexus
from nexus.events import EventHandler, ChannelEvent

class CustomEventHandler(EventHandler):
    def handle_workflow_start(self, event: ChannelEvent):
        """Handle workflow start events across all channels"""
        self.logger.info(f"Workflow {event.workflow_name} started via {event.channel}")

        # Channel-specific handling
        if event.channel == "api":
            self.record_api_metric(event)
        elif event.channel == "cli":
            self.log_cli_usage(event)
        elif event.channel == "mcp":
            self.track_ai_interaction(event)

    def handle_workflow_complete(self, event: ChannelEvent):
        """Handle workflow completion with cross-channel notification"""
        result = event.result

        # Notify all active sessions
        self.notify_sessions(f"Workflow {event.workflow_name} completed")

        # Update metrics
        self.update_workflow_metrics(event.workflow_name, event.duration)

    def handle_error(self, event: ChannelEvent):
        """Handle errors with channel-specific responses"""
        error = event.error

        if event.channel == "api":
            # Return structured error response
            return {
                "error": True,
                "message": str(error),
                "code": error.code if hasattr(error, 'code') else 500
            }
        elif event.channel == "cli":
            # Log error and return exit code
            self.logger.error(f"CLI error: {error}")
            return 1
        elif event.channel == "mcp":
            # Return MCP-formatted error
            return {
                "error": {"code": -1, "message": str(error)}
            }

# Register event handler
nexus = Nexus()
nexus.register_event_handler(CustomEventHandler())
```

### Pattern 3: Custom Channel Configuration

```python
from nexus import Nexus
from nexus.channels import ChannelConfig, APIChannel, CLIChannel, MCPChannel

# Custom API channel configuration
api_config = ChannelConfig(
    name="enterprise_api",
    port=8000,
    middleware=[
        "cors",
        "rate_limit",
        "auth",
        "compression",
        "logging"
    ],
    cors_origins=["https://app.example.com"],
    auth_providers=["oauth2", "jwt"],
    rate_limit_strategy="sliding_window",
    compression_level=6
)

# Custom CLI channel configuration
cli_config = ChannelConfig(
    name="enterprise_cli",
    port=8001,
    enable_shell_completion=True,
    enable_history=True,
    history_size=1000,
    enable_colors=True,
    enable_progress_bars=True
)

# Custom MCP channel configuration
mcp_config = ChannelConfig(
    name="enterprise_mcp",
    port=3001,
    enable_tool_discovery=True,
    enable_resource_discovery=True,
    enable_streaming=True,
    max_concurrent_sessions=50,
    tool_timeout=30
)

# Create Nexus with custom channels
nexus = Nexus(
    api_config=api_config,
    cli_config=cli_config,
    mcp_config=mcp_config
)
```

### Pattern 4: Advanced Parameter Resolution

```python
from nexus import Nexus
from nexus.parameters import ParameterResolver, ParameterSource

class CustomParameterResolver(ParameterResolver):
    def resolve_parameters(self, workflow_name: str, channel: str, raw_params: dict) -> dict:
        """Custom parameter resolution with cross-channel consistency"""

        # Base parameter resolution
        resolved = super().resolve_parameters(workflow_name, channel, raw_params)

        # Channel-specific parameter handling
        if channel == "api":
            # Extract from HTTP headers, query params, body
            resolved.update(self.extract_api_parameters(raw_params))
        elif channel == "cli":
            # Parse command-line arguments
            resolved.update(self.parse_cli_arguments(raw_params))
        elif channel == "mcp":
            # Extract from MCP tool parameters
            resolved.update(self.extract_mcp_parameters(raw_params))

        # Apply workflow-specific transformations
        if workflow_name == "data_processor":
            resolved = self.transform_data_processor_params(resolved)

        # Validate parameters
        self.validate_parameters(workflow_name, resolved)

        return resolved

    def extract_api_parameters(self, raw_params: dict) -> dict:
        """Extract parameters from API request"""
        return {
            "request_id": raw_params.get("headers", {}).get("x-request-id"),
            "user_id": raw_params.get("headers", {}).get("x-user-id"),
            "data": raw_params.get("body", {})
        }

    def parse_cli_arguments(self, raw_params: dict) -> dict:
        """Parse CLI arguments into structured parameters"""
        args = raw_params.get("args", [])
        kwargs = raw_params.get("kwargs", {})

        return {
            "cli_args": args,
            "cli_options": kwargs,
            "data": kwargs.get("data") or (args[0] if args else {})
        }

    def extract_mcp_parameters(self, raw_params: dict) -> dict:
        """Extract parameters from MCP tool call"""
        return {
            "tool_name": raw_params.get("tool_name"),
            "tool_id": raw_params.get("tool_id"),
            "data": raw_params.get("parameters", {})
        }

# Register custom parameter resolver
nexus = Nexus()
nexus.register_parameter_resolver(CustomParameterResolver())
```

### Pattern 5: Session Management

```python
from nexus import Nexus
from nexus.sessions import SessionManager, Session

class EnterpriseSessionManager(SessionManager):
    def create_session(self, channel: str, user_id: str = None) -> Session:
        """Create session with enhanced metadata"""
        session = super().create_session(channel, user_id)

        # Add enterprise metadata
        session.metadata.update({
            "tenant_id": self.get_tenant_id(user_id),
            "permissions": self.get_user_permissions(user_id),
            "rate_limits": self.get_rate_limits(user_id),
            "created_at": datetime.now().isoformat(),
            "channel": channel
        })

        return session

    def sync_session_state(self, session_id: str, state: dict):
        """Sync session state across all channels"""
        session = self.get_session(session_id)

        # Update session state
        session.state.update(state)

        # Notify all channels for this session
        for channel in session.active_channels:
            self.notify_channel(channel, session_id, state)

    def cleanup_expired_sessions(self):
        """Enhanced session cleanup with logging"""
        expired_sessions = self.get_expired_sessions()

        for session in expired_sessions:
            self.logger.info(f"Cleaning up expired session: {session.id}")
            self.cleanup_session_resources(session)
            self.remove_session(session.id)

# Configure session management
nexus = Nexus(
    enable_sessions=True,
    session_backend="redis",
    session_ttl=3600,
    session_cleanup_interval=300
)
nexus.register_session_manager(EnterpriseSessionManager())
```

## 🔧 Advanced Configuration

### Production Configuration

```python
from nexus import Nexus
from nexus.config import ProductionConfig

# Production-ready configuration
config = ProductionConfig(
    # Performance tuning
    max_concurrent_workflows=1000,
    workflow_timeout=300,
    enable_async_execution=True,

    # Security hardening
    enable_https=True,
    ssl_cert_path="/etc/ssl/certs/nexus.crt",
    ssl_key_path="/etc/ssl/private/nexus.key",
    enable_csrf_protection=True,

    # Monitoring & logging
    log_level="INFO",
    log_format="json",
    enable_metrics=True,
    metrics_port=9090,
    enable_health_checks=True,
    health_check_interval=30,

    # Database connections
    redis_url="redis://redis-cluster:6379/0",
    postgres_url="postgresql://user:pass@postgres:5432/nexus",

    # External services
    auth_service_url="https://auth.example.com",
    monitoring_service_url="https://monitoring.example.com"
)

nexus = Nexus(config=config)
```

### Kubernetes Deployment

```yaml
# nexus-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nexus-platform
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nexus-platform
  template:
    metadata:
      labels:
        app: nexus-platform
    spec:
      containers:
      - name: nexus
        image: kailash/nexus:latest
        ports:
        - containerPort: 8000
          name: api
        - containerPort: 8001
          name: cli
        - containerPort: 3001
          name: mcp
        - containerPort: 9090
          name: metrics
        env:
        - name: NEXUS_CONFIG_FILE
          value: "/config/nexus.yaml"
        - name: REDIS_URL
          value: "redis://redis-service:6379/0"
        - name: POSTGRES_URL
          valueFrom:
            secretKeyRef:
              name: nexus-secrets
              key: postgres-url
        volumeMounts:
        - name: config
          mountPath: /config
        - name: ssl-certs
          mountPath: /etc/ssl/certs
          readOnly: true
      volumes:
      - name: config
        configMap:
          name: nexus-config
      - name: ssl-certs
        secret:
          secretName: nexus-tls
```

## 🧪 Testing Strategies

### Unit Testing

```python
import pytest
from nexus import Nexus
from nexus.testing import NexusTestClient

class TestNexusWorkflows:
    def setup_method(self):
        """Setup test Nexus instance"""
        self.nexus = Nexus(
            api_port=8080,  # Use different port for testing
            mcp_port=3080,
            enable_auth=False,  # Disable auth for testing
            enable_rate_limiting=False
        )
        self.client = NexusTestClient(self.nexus)

    def test_workflow_registration(self):
        """Test workflow registration"""
        workflow = self.create_test_workflow()

        # Register workflow
        self.nexus.register("test_workflow", workflow)

        # Verify registration
        workflows = self.nexus.list_workflows()
        assert "test_workflow" in workflows

    def test_api_channel_execution(self):
        """Test workflow execution via API channel"""
        workflow = self.create_test_workflow()
        self.nexus.register("test_workflow", workflow)

        # Execute via API
        response = self.client.post("/api/workflows/test_workflow/execute", {
            "data": {"test": "value"}
        })

        assert response.status_code == 200
        assert "result" in response.json()

    def test_cli_channel_execution(self):
        """Test workflow execution via CLI channel"""
        workflow = self.create_test_workflow()
        self.nexus.register("test_workflow", workflow)

        # Execute via CLI
        result = self.client.cli("execute test_workflow --data '{\"test\": \"value\"}'")

        assert result.exit_code == 0
        assert "result" in result.output

    def test_mcp_channel_execution(self):
        """Test workflow execution via MCP channel"""
        workflow = self.create_test_workflow()
        self.nexus.register("test_workflow", workflow)

        # Execute via MCP
        result = self.client.mcp_call("test_workflow", {
            "data": {"test": "value"}
        })

        assert result["success"] is True
        assert "result" in result
```

### Integration Testing

```python
import pytest
from nexus import Nexus
from nexus.testing import NexusIntegrationTest

class TestNexusIntegration(NexusIntegrationTest):
    def test_cross_channel_session_sync(self):
        """Test session synchronization across channels"""
        # Create session via API
        api_session = self.create_api_session()
        session_id = api_session["session_id"]

        # Update session state
        self.update_session_state(session_id, {"user_data": "test"})

        # Verify state is synced to CLI
        cli_session = self.get_cli_session(session_id)
        assert cli_session["state"]["user_data"] == "test"

        # Verify state is synced to MCP
        mcp_session = self.get_mcp_session(session_id)
        assert mcp_session["state"]["user_data"] == "test"

    def test_enterprise_features(self):
        """Test enterprise features integration"""
        nexus = Nexus(
            enable_auth=True,
            enable_rate_limiting=True,
            enable_monitoring=True
        )

        # Test auth integration
        assert nexus.auth_manager is not None

        # Test rate limiting
        assert nexus.rate_limiter is not None

        # Test monitoring
        assert nexus.metrics_collector is not None
```

## 📊 Monitoring & Observability

### Metrics Collection

```python
from nexus import Nexus
from nexus.monitoring import MetricsCollector, PrometheusExporter

class CustomMetricsCollector(MetricsCollector):
    def collect_workflow_metrics(self, workflow_name: str, duration: float, success: bool):
        """Collect workflow execution metrics"""
        # Increment execution counter
        self.increment_counter(f"workflow_executions_total", {
            "workflow": workflow_name,
            "success": str(success).lower()
        })

        # Record duration histogram
        self.record_histogram(f"workflow_duration_seconds", duration, {
            "workflow": workflow_name
        })

    def collect_channel_metrics(self, channel: str, request_count: int, error_count: int):
        """Collect channel-specific metrics"""
        self.set_gauge(f"channel_active_requests", request_count, {
            "channel": channel
        })

        self.increment_counter(f"channel_errors_total", {
            "channel": channel
        }, value=error_count)

# Configure monitoring
nexus = Nexus(
    enable_monitoring=True,
    metrics_backend="prometheus",
    metrics_port=9090
)
nexus.register_metrics_collector(CustomMetricsCollector())
```

### Health Checks

```python
from nexus import Nexus
from nexus.health import HealthChecker

class CustomHealthChecker(HealthChecker):
    def check_database_health(self) -> dict:
        """Check database connectivity"""
        try:
            # Test database connection
            self.db_client.ping()
            return {"status": "healthy", "latency": "5ms"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def check_external_services(self) -> dict:
        """Check external service dependencies"""
        services = {}

        for service_name, service_url in self.external_services.items():
            try:
                response = requests.get(f"{service_url}/health", timeout=5)
                services[service_name] = {
                    "status": "healthy" if response.status_code == 200 else "unhealthy",
                    "response_time": response.elapsed.total_seconds()
                }
            except Exception as e:
                services[service_name] = {
                    "status": "unhealthy",
                    "error": str(e)
                }

        return services

# Configure health checks
nexus = Nexus(enable_health_checks=True)
nexus.register_health_checker(CustomHealthChecker())
```

## 🔐 Security Patterns

### Authentication & Authorization

```python
from nexus import Nexus
from nexus.auth import AuthProvider, JWTAuthProvider

class CustomAuthProvider(AuthProvider):
    def authenticate(self, credentials: dict) -> dict:
        """Custom authentication logic"""
        # Validate credentials against your auth service
        user = self.validate_user(credentials)

        if user:
            return {
                "user_id": user["id"],
                "username": user["username"],
                "permissions": user["permissions"],
                "tenant_id": user["tenant_id"]
            }
        else:
            raise AuthenticationError("Invalid credentials")

    def authorize(self, user: dict, resource: str, action: str) -> bool:
        """Custom authorization logic"""
        required_permission = f"{resource}:{action}"
        return required_permission in user["permissions"]

# Configure authentication
nexus = Nexus(
    enable_auth=True,
    auth_provider=CustomAuthProvider(),
    auth_strategy="jwt"
)
```

## 🚀 Performance Optimization

### Connection Pooling

```python
from nexus import Nexus
from nexus.performance import ConnectionPool

# Configure connection pooling
nexus = Nexus(
    # Database connection pool
    db_pool_size=20,
    db_pool_max_connections=100,
    db_pool_timeout=30,

    # HTTP client pool
    http_pool_size=50,
    http_pool_max_connections=200,
    http_pool_timeout=15,

    # Redis connection pool
    redis_pool_size=10,
    redis_pool_max_connections=50
)
```

### Caching Strategies

```python
from nexus import Nexus
from nexus.cache import CacheManager, RedisCache

class CustomCacheManager(CacheManager):
    def get_cache_key(self, workflow_name: str, parameters: dict) -> str:
        """Generate cache key for workflow results"""
        param_hash = hashlib.md5(json.dumps(parameters, sort_keys=True).encode()).hexdigest()
        return f"workflow:{workflow_name}:{param_hash}"

    def should_cache(self, workflow_name: str, parameters: dict) -> bool:
        """Determine if workflow result should be cached"""
        # Don't cache workflows with user-specific data
        if "user_id" in parameters:
            return False

        # Cache expensive workflows
        expensive_workflows = ["data_analysis", "ml_training", "report_generation"]
        return workflow_name in expensive_workflows

# Configure caching
nexus = Nexus(
    enable_caching=True,
    cache_backend="redis",
    cache_ttl=3600,
    cache_manager=CustomCacheManager()
)
```

## 📚 Best Practices

### 1. Workflow Design

- **Keep workflows stateless** - Use external state management
- **Design for idempotency** - Workflows should be safely retryable
- **Use appropriate timeouts** - Prevent hanging workflows
- **Implement proper error handling** - Graceful degradation

### 2. Channel Configuration

- **Use appropriate ports** - Avoid conflicts with other services
- **Configure proper CORS** - Secure API access
- **Enable compression** - Reduce bandwidth usage
- **Implement rate limiting** - Prevent abuse

### 3. Security

- **Use HTTPS in production** - Encrypt all communications
- **Implement proper authentication** - Secure access to workflows
- **Use least privilege principle** - Limit permissions
- **Audit access logs** - Monitor for suspicious activity

### 4. Performance

- **Use connection pooling** - Reduce connection overhead
- **Implement caching** - Cache expensive computations
- **Monitor resource usage** - Track CPU, memory, network
- **Scale horizontally** - Add more instances as needed

### 5. Monitoring

- **Collect comprehensive metrics** - Track all important operations
- **Set up alerting** - Be notified of issues
- **Monitor health checks** - Ensure services are healthy
- **Log structured data** - Enable better analysis

## 🎯 Production Checklist

- [ ] **Security**: Enable HTTPS, authentication, authorization
- [ ] **Performance**: Configure connection pooling, caching
- [ ] **Monitoring**: Set up metrics, logging, alerting
- [ ] **High Availability**: Configure load balancing, failover
- [ ] **Backup**: Set up database backups, disaster recovery
- [ ] **Documentation**: Document APIs, workflows, operations
- [ ] **Testing**: Comprehensive unit, integration, load tests
- [ ] **CI/CD**: Automated testing, deployment pipelines

## 📖 Related Resources

- **[Nexus Overview](README.md)** - Basic concepts and quick start
- **[Nexus CLAUDE.md](CLAUDE.md)** - Quick reference for Claude Code
- **[Enterprise Patterns](../../enterprise/nexus-patterns.md)** - Advanced architectural patterns
- **[Production Deployment](../../developer/04-production.md)** - Production deployment guide

---

*This guide covers advanced Nexus development patterns. For basic usage, see [README.md](README.md).*
