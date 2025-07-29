# Advanced Features - Enterprise & Complex Patterns

*Master enterprise-grade features and complex workflow patterns*

## 🎯 **Prerequisites**
- Completed [Fundamentals](01-fundamentals.md) - Core SDK concepts
- Completed [Workflows](02-workflows.md) - Basic workflow patterns
- Understanding of async programming concepts

## ⚡ **Async Database Operations**

### **Production Database Operations with WorkflowConnectionPool** ⭐ **RECOMMENDED**
```python
from kailash.nodes.data import WorkflowConnectionPool
from kailash.runtime.local import LocalRuntime

# Create production connection pool
pool = WorkflowConnectionPool(
    name="production_pool",
    database_type="postgresql",
    host="localhost",
    port=5432,
    database="investment_db",
    user="postgres",
    password="postgres",
    min_connections=10,      # Maintain minimum connections
    max_connections=50,      # Scale up to 50 under load
    health_threshold=70,     # Auto-recycle unhealthy connections
    pre_warm=True           # Pre-warm based on patterns
)

# Initialize pool once at startup
await pool.process({"operation": "initialize"})

# Use in production workflows
async def fetch_portfolios(risk_profile):
    # Acquire connection from pool
    conn = await pool.process({"operation": "acquire"})
    conn_id = conn["connection_id"]

    try:
        # Execute query with automatic health monitoring
        result = await pool.process({
            "operation": "execute",
            "connection_id": conn_id,
            "query": """
                SELECT portfolio_id, client_name, total_value
                FROM portfolios
                WHERE risk_profile = $1
                ORDER BY total_value DESC
            """,
            "params": [risk_profile],
            "fetch_mode": "all"
        })
        return result["data"]
    finally:
        # Always release connection back to pool
        await pool.process({
            "operation": "release",
            "connection_id": conn_id
        })

# Monitor pool health
stats = await pool.process({"operation": "stats"})
print(f"Pool efficiency: {stats['queries']['executed'] / stats['connections']['created']:.1f} queries/connection")
print(f"Error rate: {stats['queries']['error_rate']:.2%}")

# Use LocalRuntime (includes async support)
runtime = LocalRuntime()
```

### **Basic Async Database Query (for simple use cases)**
```python
from kailash.nodes.data import AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime

# For simple async operations (non-production)
db_node = AsyncSQLDatabaseNode(
    name="fetch_portfolios",
    database_type="postgresql",
    host="localhost",
    port=5432,
    database="investment_db",
    user="postgres",
    password="postgres",
    query="""
    SELECT portfolio_id, client_name, total_value
    FROM portfolios
    WHERE risk_profile = $1
    ORDER BY total_value DESC
    """,
    fetch_mode="all"
)

# Execute with parameters
async def run_query():
    result = await db_node.async_run(params=["Conservative"])
    portfolios = result["data"]
    return portfolios

# Use LocalRuntime (no need for AsyncLocalRuntime)
runtime = LocalRuntime()
results = await runtime.execute_async(workflow)

```

### **Vector Similarity Search**
```python
from kailash.nodes.data import AsyncPostgreSQLVectorNode

# Create vector search node
search_node = AsyncPostgreSQLVectorNode(
    name="semantic_search",
    connection_string="postgresql://user:pass@localhost:5432/vector_db",
    table_name="document_embeddings",
    operation="search",
    vector=[0.1, 0.2, 0.3],  # Query embedding (1536 dimensions)
    distance_metric="cosine",
    limit=10,
    metadata_filter="metadata->>'category' = 'financial'"
)

# Execute search
async def semantic_search():
    result = await search_node.execute_async()
    matches = result["result"]["matches"]
    for match in matches:
        print(f"Distance: {match['distance']:.3f}")
        print(f"Content: {match['metadata']['content']}")
    return matches

```

### **Complete Async Workflow**
```python
from kailash.workflow import Workflow
from kailash.nodes.data import AsyncSQLDatabaseNode
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.async_local import AsyncLocalRuntime

async def create_portfolio_analysis():
    """Create comprehensive async portfolio analysis workflow."""
    workflow = WorkflowBuilder()

    # 1. Fetch portfolio data
    workflow.add_node("AsyncSQLDatabaseNode", "fetch_portfolios", {}) symbol, close_price
            FROM market_prices
            ORDER BY symbol, price_date DESC
        )
        SELECT
            p.portfolio_id,
            p.client_name,
            SUM(pos.quantity * lp.close_price) as current_value
        FROM portfolios p
        JOIN positions pos ON p.portfolio_id = pos.portfolio_id
        JOIN latest_prices lp ON pos.symbol = lp.symbol
        GROUP BY p.portfolio_id, p.client_name
        ORDER BY current_value DESC
        """,
        fetch_mode="all"
    ))

    # 2. Calculate portfolio metrics
    def calculate_metrics(portfolio_data):
        """Calculate portfolio performance metrics."""
        portfolios = portfolio_data["data"]

        metrics = {
            "total_portfolios": len(portfolios),
            "total_aum": sum(p["current_value"] for p in portfolios),
            "top_portfolio": max(portfolios, key=lambda x: x["current_value"]),
            "avg_portfolio_value": sum(p["current_value"] for p in portfolios) / len(portfolios)
        }

        return {"result": metrics}

    workflow.add_node("calculate_metrics", PythonCodeNode.from_function(
        name="calculate_metrics",
        func=calculate_metrics
    ))

    # Connect nodes
    workflow.add_connection("fetch_portfolios", "result", "calculate_metrics", "input")

    return workflow

# Execute workflow
async def main():
    workflow = await create_portfolio_analysis()
    runtime = AsyncLocalRuntime()

    result, run_id = await runtime.execute(workflow.build())
    metrics = result["calculate_metrics"]["result"]

    print(f"Total AUM: ${metrics['total_aum']:,.2f}")
    print(f"Top Portfolio: {metrics['top_portfolio']['client_name']}")
    print(f"Average Value: ${metrics['avg_portfolio_value']:,.2f}")

# Run the workflow
import asyncio
asyncio.run(main())

```

## 🔒 **Access Control & Security**

### **ABAC (Attribute-Based Access Control)**
```python
from kailash.access_control.managers import AccessControlManager
from kailash.access_control import UserContext, NodePermission, AttributeCondition, AttributeOperator

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

# Check access with complex conditions
decision = acm.check_node_access(
    user=user,
    resource_id="sensitive_portfolios",
    permission=NodePermission.EXECUTE
)

if decision.allowed:
    print("✅ Access granted")
else:
    print(f"❌ Access denied: {decision.reason}")

```

### **Data Masking Based on Attributes**
```python
# Define masking rules
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

# Apply masking
masked_data = acm.mask_data(
    data={"ssn": "123-45-6789", "account_balance": 5000000},
    masking_rules=masking_rules,
    user=user
)
print(masked_data)  # {"ssn": "12*****89", "account_balance": "$1M-$10M"}

```

## 🔄 **Workflow Resilience**

### **Retry Policies & Circuit Breakers**
```python
from kailash.workflow import Workflow, RetryStrategy

workflow = WorkflowBuilder()

# Add a node that might fail
workflow.add_node("HTTPRequestNode", "fetch_data", {}), url="https://api.example.com/data")

# Configure retry policy
workflow.configure_retry(
    "fetch_data",
    max_retries=3,
    strategy=RetryStrategy.EXPONENTIAL,  # or LINEAR, IMMEDIATE, FIBONACCI
    base_delay=2.0,  # seconds
    max_delay=30.0,
    retry_on=[ConnectionError, TimeoutError]  # specific exceptions
)

# Add circuit breaker to prevent cascading failures
workflow.configure_circuit_breaker(
    "fetch_data",
    failure_threshold=5,      # Open after 5 failures
    success_threshold=2,      # Close after 2 successes
    timeout=60.0             # Try again after 60 seconds
)

```

### **Fallback Nodes & Graceful Degradation**
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

# Primary service
workflow.add_node("LLMAgentNode", "primary_llm", {}))

# Fallback service
workflow.add_node("LLMAgentNode", "fallback_llm", {}))

# Minimal fallback
workflow.add_node("minimal_analysis", PythonCodeNode.from_function(
    name="minimal_analysis",
    func=lambda data: {"result": {"analysis": "Basic analysis", "confidence": 0.5}}
))

# Configure fallback chain
workflow.add_fallback("primary_llm", "fallback_llm")
workflow.add_fallback("fallback_llm", "minimal_analysis")

# Execute with monitoring
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Get resilience metrics
metrics = workflow.get_resilience_metrics()
print(f"Circuit breaker state: {metrics['circuit_breakers']}")
print(f"Dead letter queue size: {metrics['dead_letter_queue_size']}")

```

### **Dead Letter Queue & Error Tracking**
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

# Execute workflow with error tracking
try:
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow, parameters={"data": data})
except Exception as e:
    # Check dead letter queue
    dlq = workflow.get_dead_letter_queue()
    for failed in dlq:
        print(f"Failed at {failed['timestamp']}: {failed['error']}")
        print(f"Node: {failed['node']}, Attempts: {failed['attempts']}")

    # Clear after processing
    workflow.clear_dead_letter_queue()

```

## 🔐 **SharePoint Multi-Authentication**

### **Certificate-Based Authentication**
```python
from kailash.nodes.data import SharePointGraphReaderEnhanced

# Certificate authentication (most secure)
sp_node = SharePointGraphReaderEnhanced()
result = await sp_node.execute(
    auth_method="certificate",
    tenant_id="your-tenant-id",
    client_id="your-app-client-id",
    certificate_path="/secure/certs/sharepoint.pem",
    site_url="https://company.sharepoint.com/sites/project",
    operation="list_files",
    library_name="Documents"
)

```

### **Managed Identity & Multi-Tenant Support**
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

# System-assigned managed identity
sp_node = SharePointGraphReaderEnhanced()
result = await sp_node.execute(
    auth_method="managed_identity",
    use_system_identity=True,
    site_url="https://company.sharepoint.com/sites/project",
    operation="list_files"
)

# Multi-tenant configuration
tenants = [
    {
        "name": "tenant1",
        "auth_method": "certificate",
        "tenant_id": "tenant1-id",
        "client_id": "app1-id",
        "certificate_thumbprint": "ABCD1234"
    },
    {
        "name": "tenant2",
        "auth_method": "managed_identity",
        "site_url": "https://tenant2.sharepoint.com/sites/data"
    }
]

# Add node for each tenant
for tenant in tenants:
    workflow.add_node(f"sp_{tenant['name']}", SharePointGraphReaderEnhanced(
        name=f"sp_{tenant['name']}",
        **tenant,
        operation="list_files",
        library_name="Shared Documents"
    ))

```

## 🏭 **Enterprise Workflow Templates**

### **Business Workflow Templates**
```python
from kailash.workflow.templates import BusinessWorkflowTemplates

workflow = WorkflowBuilder()

# 1. Investment Data Pipeline
BusinessWorkflowTemplates.investment_data_pipeline(
    workflow,
    data_sources=["bloomberg", "yahoo", "alpha_vantage"],
    analysis_types=["risk", "performance", "compliance"],
    notification_channels=["email", "slack", "teams"]
)

# 2. Document AI Processing
BusinessWorkflowTemplates.document_ai_pipeline(
    workflow,
    document_types=["invoice", "contract", "receipt"],
    ai_providers=["azure", "aws", "google"],
    output_formats=["json", "structured_data"],
    compliance_required=True
)

# 3. API Integration Template
BusinessWorkflowTemplates.api_integration_template(
    workflow,
    api_endpoints=["https://api1.com", "https://api2.com"],
    integration_patterns=["polling", "webhook", "streaming"],
    data_transformations=["normalize", "enrich", "validate"]
)

```

### **Template Customization**
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

# Get the template node ID for further customization
template_node_id = BusinessWorkflowTemplates.investment_data_pipeline(
    workflow,
    data_sources=["bloomberg"],
    analysis_types=["risk"],
    notification_channels=["email"]
)

# Add additional processing after the template
workflow.add_node("CustomAnalysisNode", "custom_analysis", {}))
workflow.add_connection(template_node_id, "custom_analysis")

```

## 📊 **Data Lineage & Compliance**

### **Basic Data Lineage Tracking**
```python
from kailash.nodes.enterprise.data_lineage import DataLineageNode

# Track data transformation
lineage_node = DataLineageNode(
    name="customer_lineage",
    operation="track_transformation",
    source_info={
        "system": "CRM",
        "table": "customers",
        "fields": ["name", "email", "purchase_history"]
    },
    transformation_type="anonymization",
    target_info={
        "system": "Analytics",
        "table": "customer_segments"
    }
)

workflow.add_node("lineage_tracker", lineage_node)

```

### **Compliance-Aware Lineage**
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

# Track with compliance frameworks
compliance_lineage = DataLineageNode(
    name="gdpr_lineage",
    operation="track_transformation",
    source_info={"system": "EU_CRM", "table": "eu_customers"},
    transformation_type="pseudonymization",
    compliance_frameworks=["GDPR", "CCPA"],
    include_access_patterns=True,
    audit_trail_enabled=True,
    data_classification="PII"
)

# Generate compliance report
compliance_report = DataLineageNode(
    name="compliance_reporter",
    operation="generate_compliance_report",
    compliance_frameworks=["GDPR", "SOX", "HIPAA"],
    report_format="detailed",
    include_recommendations=True
)

# Analyze data access patterns
access_analyzer = DataLineageNode(
    name="access_analyzer",
    operation="analyze_access_patterns",
    time_range_days=30,
    include_user_analysis=True,
    detect_anomalies=True,
    compliance_frameworks=["SOC2", "ISO27001"]
)

```

## 🔄 **Batch Processing Optimization**

### **Intelligent Batch Processing**
```python
from kailash.nodes.enterprise.batch_processor import BatchProcessorNode

# Basic batch processing with auto-optimization
batch_processor = BatchProcessorNode(
    name="data_processor",
    operation="process_data_batches",
    data_source="large_customer_dataset",
    batch_size=1000,  # Auto-optimized based on data characteristics
    processing_strategy="parallel",
    max_concurrent_batches=10
)

workflow.add_node("batch_processor", batch_processor)

```

### **Advanced Batch Configuration**
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

# Advanced batch processing with rate limiting
advanced_processor = BatchProcessorNode(
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

```

### **Batch Processing Strategies**
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

# Different processing strategies
strategies = [
    "sequential",       # Process one batch at a time
    "parallel",        # Fixed parallel processing
    "adaptive_parallel", # Adjust parallelism based on performance
    "streaming",       # Stream processing for real-time data
    "burst"           # High-speed burst processing with resource scaling
]

# Example with streaming strategy
streaming_processor = BatchProcessorNode(
    name="streaming_processor",
    operation="process_data_batches",
    processing_strategy="streaming",
    stream_buffer_size=1000,
    stream_timeout_seconds=30
)

```

## 🔐 **Automatic Credential Rotation**

### **Basic Credential Rotation**
```python
from kailash.nodes.security.rotating_credentials import RotatingCredentialNode

# Start automatic rotation for API credentials
credential_rotator = RotatingCredentialNode(
    name="api_rotator",
    operation="start_rotation",
    credential_name="api_service_token",
    check_interval=3600,  # Check every hour
    expiration_threshold=86400,  # Rotate 24 hours before expiry
    refresh_sources=["vault", "aws_secrets"]
)

workflow.add_node("credential_rotator", credential_rotator)

```

### **Enterprise Credential Rotation**
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

# Enterprise-grade rotation with notifications
enterprise_rotator = RotatingCredentialNode(
    name="enterprise_rotator",
    operation="start_rotation",
    credential_name="production_api_key",

    # Rotation policy
    check_interval=1800,  # Check every 30 minutes
    expiration_threshold=172800,  # Rotate 48 hours before expiry
    rotation_policy="proactive",  # proactive, reactive, scheduled

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

```

### **Credential Rotation Operations**
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

# Check rotation status
status_checker = RotatingCredentialNode(
    name="status_checker",
    operation="check_status",
    credential_name="api_service_token"
)

# Force immediate rotation
immediate_rotator = RotatingCredentialNode(
    name="immediate_rotator",
    operation="rotate_now",
    credential_name="emergency_rotation_needed",
    zero_downtime=True,
    rollback_on_failure=True
)

# Scheduled rotation using cron expressions
scheduled_rotator = RotatingCredentialNode(
    name="scheduled_rotator",
    operation="start_rotation",
    credential_name="weekly_api_key",
    rotation_policy="scheduled",
    schedule_cron="0 2 * * 1",  # Every Monday at 2 AM
    zero_downtime=True,
    notification_webhooks=["https://alerts.company.com/scheduled-rotation"]
)

```

## 🔗 **Comprehensive Enterprise Example**

### **Complete Enterprise Workflow**
```python
from kailash.workflow import Workflow
from kailash.workflow.templates import BusinessWorkflowTemplates
from kailash.nodes.enterprise.data_lineage import DataLineageNode
from kailash.nodes.enterprise.batch_processor import BatchProcessorNode
from kailash.nodes.security.rotating_credentials import RotatingCredentialNode

# Create enterprise workflow
workflow = WorkflowBuilder()

# 1. Set up credential rotation
workflow.add_node("RotatingCredentialNode", "credential_rotation", {}))

# 2. Apply business workflow template
template_node = BusinessWorkflowTemplates.data_processing_pipeline(
    workflow,
    data_sources=["database", "apis", "files"],
    processing_stages=["validate", "transform", "enrich"],
    output_destinations=["warehouse", "reports"]
)

# 3. Add data lineage tracking
workflow.add_node("DataLineageNode", "lineage_tracker", {}))

# 4. Add batch processing optimization
workflow.add_node("BatchProcessorNode", "batch_processor", {}))

# Connect the workflow
workflow.add_connection(template_node, "lineage_tracker")
workflow.add_connection("lineage_tracker", "result", "batch_processor", "input")

# Execute with comprehensive monitoring
runtime = LocalRuntime(
    max_workers=8,
    timeout=600.0,
    enable_logging=True,
    memory_monitoring=True
)

results, run_id = runtime.execute(workflow, parameters={
    "batch_processor": {"data_source": "production_dataset"},
    "lineage_tracker": {"audit_level": "detailed"}
})

```

## 📊 **Best Practices Summary**

### **Enterprise Development Guidelines**
1. **Security First**: Always use proper authentication and encryption
2. **Resilience Built-in**: Configure retries, fallbacks, and circuit breakers
3. **Monitoring Everything**: Enable comprehensive logging and metrics
4. **Compliance Ready**: Track data lineage and maintain audit trails
5. **Performance Optimized**: Use batch processing and async operations

### **Production Readiness**
1. **Access Control**: Implement RBAC/ABAC for all sensitive operations
2. **Credential Management**: Use automatic rotation with zero downtime
3. **Data Governance**: Track transformations and ensure compliance
4. **Error Handling**: Plan for graceful degradation and recovery
5. **Resource Management**: Monitor and optimize memory and CPU usage

## 🔗 **Related Guides**

**Prerequisites:**
- **[Fundamentals](01-fundamentals.md)** - Core SDK concepts and parameter types
- **[Workflows](02-workflows.md)** - Basic workflow creation and execution

**See Also:**
- **[Quick Reference](QUICK_REFERENCE.md)** - Enterprise runtime patterns and credential management

**Next Steps:**
- **[Production](04-production.md)** - Production deployment and monitoring
- **[Troubleshooting](05-troubleshooting.md)** - Debug and solve complex issues

---

**These advanced features enable enterprise-grade workflows with security, compliance, and resilience built-in!**
