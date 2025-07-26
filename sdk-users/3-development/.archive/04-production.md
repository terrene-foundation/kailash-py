# Production - Deployment, Security & Monitoring

*Deploy secure, scalable workflows to production with confidence*

## 🎯 **Prerequisites**
- Completed [Fundamentals](01-fundamentals.md) - Core SDK concepts
- Completed [Workflows](02-workflows.md) - Basic workflow patterns
- Completed [Advanced Features](03-advanced-features.md) - Enterprise features
- Understanding of production deployment practices

## 🔗 **Related Guides**
- **[Quick Reference](QUICK_REFERENCE.md)** - Production patterns and best practices
- **[Troubleshooting](05-troubleshooting.md)** - Debug production issues

## 🔍 **Production Readiness Checklist**

### **✅ Code Quality**
- [ ] **PythonCodeNode Functions**: All code >3 lines uses `.from_function()` pattern
- [ ] **Node Names**: All custom nodes end with "Node" suffix
- [ ] **Error Handling**: Each function includes try-catch blocks
- [ ] **Input Validation**: All inputs validated before processing
- [ ] **Type Hints**: All functions have proper type annotations

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

# ✅ PRODUCTION READY
import logging
logger = logging.getLogger(__name__)

def process_customer_data(customers: list, transactions: list) -> dict:
    """Process customer data with full error handling."""
    try:
        # Validate inputs
        if not customers or not transactions:
            raise ValueError("Missing required input data")

        # Process with error handling
        result = [{"id": c, "processed": True} for c in customers]
        return {'result': result, 'status': 'success'}

    except Exception as e:
        logger.error(f"Processing failed: {e}")
        return {'result': [], 'status': 'error', 'error': str(e)}

processor = PythonCodeNode.from_function(
    name="customer_processor",
    func=process_customer_data
)

```

### **✅ Data Management**
- [ ] **File Paths**: Use centralized `get_input_data_path()` and `get_output_data_path()`
- [ ] **Data Validation**: Schema validation for all inputs
- [ ] **Large Files**: Batch processing for datasets >1000 records
- [ ] **Backup Strategy**: Output files include timestamps
- [ ] **Clean Up**: Temporary files properly removed

```python
# ✅ PRODUCTION DATA HANDLING
import os
from datetime import datetime

# Mock data path functions for example
def get_input_data_path(filename):
    return f"/input/{filename}"

def get_output_data_path(filename):
    return f"/output/{filename}"

class MockPath:
    def __init__(self, path):
        self.path = path
    def exists(self):
        return True  # Mock exists for example

# Input validation
input_file_path = get_input_data_path("customers.csv")
input_file = MockPath(input_file_path)
if not input_file.exists():
    raise FileNotFoundError(f"Required input file missing: {input_file_path}")

# Output with timestamp
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_file = get_output_data_path(f"results_{timestamp}.json")

```

### **✅ Workflow Architecture**
- [ ] **Single Responsibility**: Each node has one clear purpose
- [ ] **Fail-Fast**: Input validation at workflow start
- [ ] **Graceful Degradation**: Fallback strategies for failures
- [ ] **Progress Tracking**: Long-running workflows include progress updates
- [ ] **Resource Management**: Memory and CPU usage optimized

```python
# ✅ PRODUCTION WORKFLOW STRUCTURE
def create_production_workflow():
    workflow = WorkflowBuilder()

    # 1. Input validation (fail-fast)
    validator = PythonCodeNode.from_function(
        name="input_validator",
        func=validate_all_inputs
    )

    # 2. Main processing with error handling
    processor = PythonCodeNode.from_function(
        name="main_processor",
        func=process_with_fallback
    )

    # 3. Results validation
    result_validator = PythonCodeNode.from_function(
        name="result_validator",
        func=validate_outputs
    )

    # Connect with descriptive mappings
    workflow.add_connection("input_validator", "main_processor", "result", "validated_inputs")
    workflow.add_connection("main_processor", "result_validator", "result", "processed_data")

    return workflow

```

## 🔒 **Security & Access Control**

### **Environment-Based Configuration**
```python
# ✅ SECURE CONFIGURATION
import os
from kailash.security import SecurityConfig, set_security_config

# Production security configuration
security_config = SecurityConfig(
    allowed_directories=["/app/data", "/tmp/kailash"],
    max_file_size=50 * 1024 * 1024,  # 50MB
    execution_timeout=60.0,  # 1 minute
    memory_limit=256 * 1024 * 1024,  # 256MB
    allowed_file_extensions=['.txt', '.csv', '.json', '.yaml'],
    enable_audit_logging=True,
    enable_path_validation=True,
    enable_command_validation=True
)

set_security_config(security_config)

```

### **Credential Management**
```python
from kailash.nodes.security import CredentialManagerNode

workflow = WorkflowBuilder()

# Get credentials securely
workflow.add_node("CredentialManagerNode", "get_api_key", {}),
    credential_name="openai",
    credential_type="api_key",
    credential_sources=["vault", "aws_secrets", "env"],
    validate_on_fetch=True,
    cache_duration_seconds=1800
)

# Use credentials in another node
workflow.add_node("LLMAgentNode", "llm_call", {}),
    prompt="Analyze this data"
)

# Connect - credentials are passed securely
workflow.add_connection("get_api_key", "result", "llm_call", "input")

```

### **Access Control & Multi-Tenancy**
```python
from kailash.access_control.managers import AccessControlManager
from kailash.access_control import UserContext, NodePermission

# Create access control manager
acm = AccessControlManager(strategy="abac")

# Create user context with attributes
user = UserContext(
    user_id="analyst_001",
    tenant_id="financial_corp",
    email="analyst@corp.com",
    roles=["analyst", "portfolio_viewer"],
    attributes={
        "department": "investment.analytics",
        "clearance": "confidential",
        "region": "us_east",
        "access_level": 5
    }
)

# Check access before execution
decision = acm.check_node_access(
    user=user,
    resource_id="sensitive_portfolios",
    permission=NodePermission.EXECUTE
)

if decision.allowed:
    # Execute workflow with user context
    runtime = LocalRuntime(
        enable_security=True,
        enable_audit=True,
        user_context=user
    )
    results, run_id = runtime.execute(workflow.build())
else:
    print(f"❌ Access denied: {decision.reason}")

```

### **Data Masking & Compliance**
```python
# Define masking rules based on user attributes
masking_rules = {
    "ssn": {
        "condition": {
            "attribute_path": "user.attributes.clearance",
            "operator": "security_level_below",
            "value": "secret"
        },
        "mask_type": "partial",
        "visible_chars": 4
    },
    "account_balance": {
        "condition": {
            "attribute_path": "user.attributes.access_level",
            "operator": "less_than",
            "value": 7
        },
        "mask_type": "range",
        "ranges": ["< $1M", "$1M-$10M", "$10M-$50M", "> $50M"]
    }
}

# Apply masking automatically
masked_data = acm.mask_data(
    data={"ssn": "123-45-6789", "account_balance": 5000000},
    masking_rules=masking_rules,
    user=user
)
print(masked_data)  # {"ssn": "12*****89", "account_balance": "$1M-$10M"}

```

## 🏢 **Unified Runtime for Production**

### **Enterprise Runtime Configuration**
```python
from kailash.runtime.local import LocalRuntime
from kailash.access_control import UserContext

# Create user context for multi-tenant isolation
user_context = UserContext(
    user_id="analyst_01",
    tenant_id="acme_corp",
    email="analyst@acme.com",
    roles=["data_analyst", "viewer"],
    attributes={"department": "finance", "clearance": "high"}
)

# Enterprise runtime with all features
runtime = LocalRuntime(
    # Performance & Execution
    enable_async=True,           # Auto-detect and run async nodes
    max_concurrency=20,          # Parallel execution limit
    enable_monitoring=True,      # Automatic performance tracking

    # Security & Compliance
    enable_security=True,        # Access control enforcement
    enable_audit=True,           # Compliance audit logging
    user_context=user_context,   # Multi-tenant isolation

    # Resource Management
    resource_limits={
        "memory_mb": 4096,       # Memory limit
        "cpu_cores": 4,          # CPU limit
        "timeout_seconds": 300   # Execution timeout
    }
)

# Execute with automatic enterprise integration
results, run_id = runtime.execute(workflow, parameters=parameters)

```

### **Progressive Feature Adoption**
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

# Stage 1: Basic development
runtime = LocalRuntime()

# Stage 2: Add monitoring
runtime = LocalRuntime(enable_monitoring=True)

# Stage 3: Add compliance
runtime = LocalRuntime(
    enable_monitoring=True,
    enable_audit=True,
    user_context=user_context
)

# Stage 4: Full enterprise
runtime = LocalRuntime(
    enable_monitoring=True,
    enable_audit=True,
    enable_security=True,
    enable_async=True,
    user_context=user_context,
    resource_limits={"memory_mb": 4096, "cpu_cores": 4}
)

```

## 📊 **Performance & Monitoring**

### **Phase 3: Production-Grade Connection Management**

#### **Circuit Breaker Protection**
```python
from kailash.core.resilience.circuit_breaker import CircuitBreakerManager, CircuitBreakerConfig

# Setup circuit breaker for database operations
cb_manager = CircuitBreakerManager()
cb_config = CircuitBreakerConfig(
    failure_threshold=5,        # Open after 5 failures
    recovery_timeout=30,        # Wait 30s before trying half-open
    error_rate_threshold=0.5,   # Open at 50% error rate
    min_calls=10               # Minimum calls before calculating error rate
)

circuit_breaker = cb_manager.get_or_create("database", cb_config)

# Use circuit breaker with async operations
async def protected_db_operation():
    return db_node.run(query="SELECT * FROM users")

try:
    result = await circuit_breaker.call(protected_db_operation)
    print("Operation succeeded:", result)
except Exception as e:
    if "Circuit breaker is OPEN" in str(e):
        print("Circuit breaker prevented operation - system is recovering")
    else:
        print("Operation failed:", e)

# Monitor circuit breaker status
status = circuit_breaker.get_status()
print(f"State: {status['state']}, Failed calls: {status['metrics']['failed_calls']}")
```

#### **Comprehensive Metrics Collection**
```python
from kailash.core.monitoring.connection_metrics import ConnectionMetricsCollector

# Create metrics collector for connection pool
metrics_collector = ConnectionMetricsCollector("production_pool")

# Track database queries with detailed metrics
with metrics_collector.track_query("SELECT", "users"):
    result = db_node.run(query="SELECT * FROM users WHERE active = true")

# Track connection acquisition performance
with metrics_collector.track_acquisition():
    # Connection pool operations
    pass

# Get comprehensive metrics
all_metrics = metrics_collector.get_all_metrics()
print(f"Query throughput: {all_metrics['rates']['queries_per_second']:.1f} qps")
print(f"Average execution time: {all_metrics['percentiles']['query_execution_ms']['p95']:.1f}ms")
print(f"Error rate: {all_metrics['rates']['error_rate']:.1%}")

# Export to Prometheus format
prometheus_metrics = metrics_collector.export_prometheus()
print("Prometheus metrics:", prometheus_metrics)
```

#### **Query Pipelining for High Performance**
```python
from kailash.nodes.data.query_pipeline import QueryPipelineNode

# Create query pipeline with batching
pipeline = QueryPipelineNode(
    name="high_performance_pipeline",
    connection_string="postgresql://user:pass@localhost:5432/db",
    batch_size=50,              # Process 50 queries per batch
    flush_interval=1.0,         # Auto-flush every 1 second
    max_queue_size=1000,        # Queue up to 1000 queries
    execution_strategy="parallel"  # parallel, sequential, transactional, best_effort
)

# Add queries to pipeline (non-blocking)
for user_id in range(1000):
    pipeline.add_query(
        f"UPDATE users SET last_seen = NOW() WHERE id = {user_id}",
        query_type="UPDATE"
    )

# Execute pipeline with automatic batching
result = pipeline.run()
print(f"Processed {result['queries_executed']} queries in {result['batches_processed']} batches")
print(f"Throughput: {result['queries_per_second']:.1f} qps")
```

#### **Real-time Monitoring Dashboard**
```python
from kailash.nodes.monitoring.connection_dashboard import ConnectionDashboardNode

# Create monitoring dashboard
dashboard = ConnectionDashboardNode(
    name="production_dashboard",
    metrics_collector=metrics_collector,
    circuit_breaker=circuit_breaker,
    websocket_port=8765,
    enable_prometheus_export=True,
    refresh_interval=5.0
)

# Start dashboard server (non-blocking)
dashboard_info = dashboard.run()
print(f"Dashboard available at: {dashboard_info['dashboard_url']}")
print(f"WebSocket endpoint: {dashboard_info['websocket_url']}")
print(f"Prometheus metrics: {dashboard_info['prometheus_url']}")

# Dashboard provides real-time metrics via WebSocket:
# - Connection pool utilization
# - Query performance histograms
# - Circuit breaker status
# - Error rates and categorization
# - Throughput trends
```

### **Performance Optimization**
```python
from kailash.tracking import MetricsCollector

metrics = MetricsCollector()

# Monitor execution
with metrics.timer("workflow_execution"):
    results, run_id = runtime.execute(workflow, parameters=parameters)

# Track resource usage
metrics.record_memory_usage()
metrics.record_processing_time()
print(f"Workflow completed in {metrics.get_duration('workflow_execution'):.2f}s")

```

### **Batch Processing for Scale**
```python
from kailash.nodes.enterprise.batch_processor import BatchProcessorNode

# Advanced batch processing with rate limiting
batch_processor = BatchProcessorNode(
    name="rate_limited_processor",
    operation="process_data_batches",
    data_source="api_data",

    # Batch optimization
    batch_size=500,
    adaptive_batch_sizing=True,
    min_batch_size=100,
    max_batch_size=2000,

    # Concurrency control
    processing_strategy="adaptive_parallel",
    max_concurrent_batches=15,
    rate_limit_per_second=50,

    # Error handling
    error_handling="continue_with_logging",
    max_retry_attempts=3,
    retry_delay_seconds=5,

    # Performance monitoring
    enable_performance_monitoring=True,
    performance_threshold_ms=5000
)

workflow.add_node("batch_processor", batch_processor)

```

### **Memory-Efficient Processing**
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

# Stream processing for large datasets
workflow.add_node("stream_processor", "PythonCodeNode",
    name="stream_processor",
    code='''
import gc

# Process data in memory-efficient chunks
chunk_size = 100
processed_count = 0
memory_usage = []

for i in range(0, len(data), chunk_size):
    chunk = data[i:i + chunk_size]

    # Process chunk
    for item in chunk:
        if item.get("process", True):
            processed_count += 1

    # Memory management
    if i % (chunk_size * 10) == 0:
        gc.collect()
        memory_usage.append(f"Processed {i + len(chunk)} items")

    # Clear chunk reference
    del chunk

result = {
    "processed_count": processed_count,
    "memory_checkpoints": memory_usage,
    "efficiency_metrics": {
        "items_per_chunk": chunk_size,
        "total_chunks": len(range(0, len(data), chunk_size)),
        "memory_managed": True
    }
}
''',
    input_types={"data": list}
))

```

## 🔄 **Error Handling & Recovery**

### **Resilient Workflow Patterns**
```python
from kailash.workflow import Workflow, RetryStrategy

workflow = WorkflowBuilder()

# Configure retry policies
workflow.add_node("HTTPRequestNode", "api_call", {}), url="https://api.example.com/data")
workflow.configure_retry(
    "api_call",
    max_retries=3,
    strategy=RetryStrategy.EXPONENTIAL,
    base_delay=2.0,
    max_delay=30.0,
    retry_on=[ConnectionError, TimeoutError]
)

# Add circuit breaker
workflow.configure_circuit_breaker(
    "api_call",
    failure_threshold=5,
    success_threshold=2,
    timeout=60.0
)

# Configure fallback chain
workflow.add_node("LLMAgentNode", "primary_service", {}), model="gpt-4")
workflow.add_node("LLMAgentNode", "fallback_service", {}), model="claude-3-sonnet")
workflow.add_node("minimal_fallback", PythonCodeNode.from_function(
    name="fallback",
    func=lambda text: {"result": {"analysis": "Basic analysis", "confidence": 0.5}}
))

workflow.add_fallback("primary_service", "fallback_service")
workflow.add_fallback("fallback_service", "minimal_fallback")

```

### **Comprehensive Error Handling**
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

import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
def robust_api_call(data: list) -> dict:
    """API call with automatic retry logic."""
    try:
        # Mock external API call
        response = [{"id": i, "processed": True} for i in range(len(data))]
        logger.info(f"API call successful for {len(data)} records")
        return {'result': response, 'status': 'success'}

    except APITimeoutError as e:
        logger.warning(f"API timeout, retrying: {e}")
        raise  # Will be retried

    except APIRateLimitError as e:
        logger.warning(f"Rate limit hit, backing off: {e}")
        raise  # Will be retried with exponential backoff

    except Exception as e:
        logger.error(f"Unrecoverable API error: {e}")
        return {'result': [], 'status': 'error', 'error': str(e)}

# Use in workflow
workflow.add_node("robust_api", PythonCodeNode.from_function(
    name="robust_api",
    func=robust_api_call
))

```

## 🚀 **Deployment Patterns**

### **Docker Production Deployment**
```dockerfile
# Secure Docker deployment
FROM python:3.12-slim

# Create non-root user
RUN groupadd -r kailash && useradd -r -g kailash kailash

# Set security-focused environment
ENV PYTHONPATH=/app
ENV KAILASH_SECURITY_MODE=strict

# Copy application
COPY --chown=kailash:kailash . /app
WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Switch to non-root user
USER kailash

# Run with security limits
CMD ["python", "-m", "kailash", "--security-mode", "strict"]
```

### **Kubernetes Production Configuration**
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: kailash-app
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000
  containers:
  - name: kailash
    image: kailash:latest
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities:
        drop:
        - ALL
    resources:
      limits:
        memory: "4Gi"
        cpu: "2000m"
      requests:
        memory: "2Gi"
        cpu: "1000m"
    env:
    - name: KAILASH_SECURITY_MODE
      value: "strict"
    - name: MAX_WORKERS
      value: "8"
    - name: MEMORY_LIMIT_MB
      value: "3072"
```

### **Environment Configuration**
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

import os
from dataclasses import dataclass

@dataclass
class ProductionConfig:
    """Production environment configuration."""
    max_workers: int = int(os.getenv('MAX_WORKERS', '4'))
    timeout_seconds: int = int(os.getenv('TIMEOUT_SECONDS', '300'))
    memory_limit_mb: int = int(os.getenv('MEMORY_LIMIT_MB', '2048'))
    log_level: str = os.getenv('LOG_LEVEL', 'INFO')
    enable_audit: bool = os.getenv('ENABLE_AUDIT', 'true').lower() == 'true'
    enable_security: bool = os.getenv('ENABLE_SECURITY', 'true').lower() == 'true'

    def validate(self):
        """Validate configuration before startup."""
        if self.max_workers < 1:
            raise ValueError("MAX_WORKERS must be positive")
        if self.timeout_seconds < 30:
            raise ValueError("TIMEOUT_SECONDS must be at least 30")
        if self.memory_limit_mb < 512:
            raise ValueError("MEMORY_LIMIT_MB must be at least 512")

# Use in production
config = ProductionConfig()
config.validate()

runtime = LocalRuntime(
    max_workers=config.max_workers,
    timeout=config.timeout_seconds,
    enable_audit=config.enable_audit,
    enable_security=config.enable_security,
    resource_limits={
        "memory_mb": config.memory_limit_mb,
        "timeout_seconds": config.timeout_seconds
    }
)

```

## 📋 **Monitoring & Health Checks**

### **Health Check Endpoints**
```python
from flask import Flask, jsonify
from kailash.monitoring import HealthChecker

app = Flask(__name__)
health_checker = HealthChecker()

@app.route('/health')
def health_check():
    """Health check endpoint for load balancers."""
    status = health_checker.check_all()

    return jsonify({
        'status': 'healthy' if status['overall'] else 'unhealthy',
        'checks': status['checks'],
        'timestamp': status['timestamp']
    }), 200 if status['overall'] else 503

@app.route('/metrics')
def metrics():
    """Metrics endpoint for monitoring systems."""
    return jsonify({
        'workflows_executed': metrics.get_counter('workflows_executed'),
        'average_duration': metrics.get_average('workflow_duration'),
        'error_rate': metrics.get_rate('workflow_errors'),
        'memory_usage': metrics.get_current('memory_usage_mb')
    })

@app.route('/ready')
def readiness_check():
    """Readiness check for Kubernetes."""
    return jsonify({'status': 'ready'}), 200

```

### **Data Lineage & Compliance Tracking**
```python
from kailash.nodes.enterprise.data_lineage import DataLineageNode

# Track data transformations for compliance
workflow.add_node("DataLineageNode", "lineage_tracker", {}))

# Generate compliance reports
compliance_report = DataLineageNode(
    name="compliance_reporter",
    operation="generate_compliance_report",
    compliance_frameworks=["GDPR", "SOX", "HIPAA"],
    report_format="detailed",
    include_recommendations=True
)

```

## 🔐 **Credential Rotation & Security**

### **Automatic Credential Rotation**
```python
from kailash.nodes.security.rotating_credentials import RotatingCredentialNode

# Enterprise-grade credential rotation
enterprise_rotator = RotatingCredentialNode(
    name="enterprise_rotator",
    operation="start_rotation",
    credential_name="production_api_key",

    # Rotation policy
    check_interval=1800,  # Check every 30 minutes
    expiration_threshold=172800,  # Rotate 48 hours before expiry
    rotation_policy="proactive",

    # Refresh sources (tried in order)
    refresh_sources=["vault", "aws_secrets", "azure_key_vault"],
    refresh_config={
        "vault": {"path": "secret/prod/api-keys"},
        "aws_secrets": {"region": "us-east-1"},
        "azure_key_vault": {"vault_url": "https://company-kv.vault.azure.net/"}
    },

    # Zero-downtime rotation
    zero_downtime=True,
    rollback_on_failure=True,

    # Notifications
    notification_webhooks=["https://alerts.company.com/webhook"],
    notification_emails=["devops@company.com", "security@company.com"],

    # Audit
    audit_log_enabled=True
)

workflow.add_node("credential_rotator", enterprise_rotator)

```

## 🧪 **Testing & Validation**

### **Production Test Suite**
```python
import pytest
from unittest.mock import Mock, patch

def test_workflow_with_production_data():
    """Test workflow with realistic production data volumes."""
    # Load production-sized test data
    large_dataset = load_test_data(size=10000)

    # Execute workflow
    runtime = LocalRuntime(enable_monitoring=True)
    results, run_id = runtime.execute(workflow, parameters={"data": large_dataset})

    # Validate results
    assert results["final_output"]["status"] == "success"
    assert len(results["final_output"]["result"]) > 0
    assert all("customer_id" in record for record in results["final_output"]["result"])

def test_error_handling():
    """Test workflow handles errors gracefully."""
    # Test with malformed data
    bad_data = [{"invalid": "data"}]

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow, parameters={"data": bad_data})

    # Should handle gracefully, not crash
    assert "error" in results["final_output"]
    assert results["final_output"]["status"] == "error"

@patch('external_service.api_call')
def test_external_service_failure(mock_api):
    """Test workflow handles external service failures."""
    mock_api.side_effect = ConnectionError("Service unavailable")

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow, parameters={"data": test_data})

    # Should fallback gracefully
    assert results["final_output"]["status"] in ["fallback_success", "error"]
    assert "fallback_applied" in results["final_output"]

```

## 📋 **Pre-Deployment Checklist**

### **Code Review**
- [ ] All PythonCodeNode uses `.from_function()` for code >3 lines
- [ ] No hardcoded file paths or credentials
- [ ] Error handling implemented for all external calls
- [ ] Input validation at workflow entry points
- [ ] Memory usage optimized for large datasets

### **Testing**
- [ ] Unit tests pass with 90%+ coverage
- [ ] Integration tests pass with production-sized data
- [ ] Performance tests meet SLA requirements
- [ ] Error scenarios tested and handled gracefully
- [ ] Security scan completed with no critical issues

### **Infrastructure**
- [ ] Environment variables configured
- [ ] Resource limits set appropriately
- [ ] Monitoring and alerting configured
- [ ] Backup and recovery procedures tested
- [ ] Rollback plan documented and tested

### **Documentation**
- [ ] API documentation updated
- [ ] Deployment guide current
- [ ] Troubleshooting guide includes new workflows
- [ ] Change log updated
- [ ] Team training completed

## 🔗 **Next Steps**

- **[Troubleshooting](05-troubleshooting.md)** - Debug and solve production issues
- **[Custom Development](06-custom-development.md)** - Build custom nodes and extensions

---

**Production deployment requires careful attention to security, performance, and monitoring. Use this guide to ensure your workflows are enterprise-ready!**
