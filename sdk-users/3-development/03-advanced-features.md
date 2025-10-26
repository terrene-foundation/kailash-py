# Advanced Features - Enterprise & Complex Patterns

*Master enterprise-grade features and complex workflow patterns*

## Prerequisites

- Completed [Fundamentals](01-fundamentals.md) - Core SDK concepts
- Completed [Workflows](02-workflows.md) - Basic workflow patterns
- Understanding of async programming concepts

## Access Control & Security

### ABAC (Attribute-Based Access Control)

The SDK provides comprehensive access control management through the AccessControlManager:

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

### Role-Based Access Control (RBAC)

```python
# Create RBAC manager
acm = AccessControlManager(strategy="rbac")

# Define roles and permissions
roles = {
    "admin": ["read", "write", "execute", "delete"],
    "analyst": ["read", "execute"],
    "viewer": ["read"]
}

# Check permissions
user = UserContext(
    user_id="user123",
    roles=["analyst"],
    tenant_id="corp"
)

# Verify access
can_execute = acm.check_permission(user, "execute")  # True
can_delete = acm.check_permission(user, "delete")   # False
```

### Data Masking Based on Attributes

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
print(masked_data)  # {"ssn": "***-**-6789", "account_balance": "$1M-$10M"}
```

## Workflow Resilience

### Retry Policies

Configure retry strategies for nodes that might fail:

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Add a node with retry configuration
workflow.add_node("HTTPRequestNode", "api_call", {
    "url": "https://api.example.com/data",
    "retry_config": {
        "max_retries": 3,
        "backoff_strategy": "exponential",
        "initial_delay": 1.0,
        "max_delay": 30.0,
        "retry_on_status": [500, 502, 503, 504]
    }
})
```

### Fallback Patterns

Implement graceful degradation with fallback nodes:

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Primary LLM service
workflow.add_node("LLMAgentNode", "primary_llm", {
    "model": "gpt-4",
    "prompt": "Analyze: {data}"
})

# Fallback LLM service
workflow.add_node("LLMAgentNode", "fallback_llm", {
    "model": "claude-3-sonnet",
    "prompt": "Analyze: {data}"
})

# Simple fallback logic
workflow.add_node("PythonCodeNode", "check_primary", {
    "code": """
if primary_result.get('error'):
    result = {'use_fallback': True}
else:
    result = {'use_fallback': False, 'analysis': primary_result}
"""
})

# Connect with conditional routing
workflow.add_connection("primary_llm", "result", "check_primary", "primary_result")
workflow.add_connection("check_primary", "result.use_fallback", "fallback_llm", "should_run")
```

## Business Workflow Templates

The SDK provides pre-built business workflow templates:

```python
from kailash.workflow.templates import BusinessWorkflowTemplates
from kailash.workflow.builder import WorkflowBuilder

# Create workflow
workflow = WorkflowBuilder()

# Apply business template for data processing
template_config = {
    "data_sources": ["database", "apis", "files"],
    "processing_stages": ["validate", "transform", "enrich"],
    "output_destinations": ["warehouse", "reports"]
}

# BusinessWorkflowTemplates provides common patterns
# You can build similar patterns manually:

# Data validation stage
workflow.add_node("PythonCodeNode", "validator", {
    "code": """
# Validate input data
errors = []
if not data:
    errors.append("No data provided")
if not isinstance(data, list):
    errors.append("Data must be a list")

result = {
    "valid": len(errors) == 0,
    "errors": errors,
    "data": data if len(errors) == 0 else None
}
"""
})

# Data transformation stage
workflow.add_node("PythonCodeNode", "transformer", {
    "code": """
# Transform valid data
transformed = []
for item in validated_data:
    transformed.append({
        "id": item.get("id"),
        "processed_at": datetime.now().isoformat(),
        "value": item.get("value", 0) * 1.1  # Apply business logic
    })
result = {"transformed": transformed}
"""
})

# Connect stages
workflow.add_connection("validator", "result.data", "transformer", "validated_data")
```

## Data Lineage & Compliance

### Data Lineage Tracking

Track data transformations for compliance and auditing:

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

# Add to workflow
workflow.add_node("DataLineageNode", "lineage_tracker", {
    "operation": "track_transformation",
    "source_info": {
        "system": "Source",
        "table": "raw_data"
    },
    "transformation_type": "enrichment",
    "compliance_frameworks": ["GDPR", "SOX"],
    "audit_trail_enabled": True
})
```

### Compliance Reporting

Generate compliance reports and analyze access patterns:

```python
# Compliance report generation
workflow.add_node("DataLineageNode", "compliance_reporter", {
    "operation": "generate_compliance_report",
    "compliance_frameworks": ["GDPR", "SOX", "HIPAA"],
    "report_format": "detailed",
    "include_recommendations": True
})

# Access pattern analysis
workflow.add_node("DataLineageNode", "access_analyzer", {
    "operation": "analyze_access_patterns",
    "time_range_days": 30,
    "include_user_analysis": True,
    "detect_anomalies": True,
    "compliance_frameworks": ["SOC2", "ISO27001"]
})
```

## Batch Processing Optimization

### Intelligent Batch Processing

Process large datasets efficiently with the BatchProcessorNode:

```python
from kailash.nodes.enterprise.batch_processor import BatchProcessorNode

# Basic batch processing
batch_processor = BatchProcessorNode(
    name="data_processor",
    operation="process_data_batches",
    data_source="large_customer_dataset",
    batch_size=1000,
    processing_strategy="parallel",
    max_concurrent_batches=10
)

# Add to workflow
workflow.add_node("BatchProcessorNode", "batch_processor", {
    "operation": "process_data_batches",
    "batch_size": 1000,
    "processing_strategy": "adaptive_parallel",
    "max_concurrent_batches": 10,
    "rate_limit_per_second": 50,
    "enable_performance_monitoring": True
})
```

### Advanced Batch Configuration

Configure batch processing for different scenarios:

```python
# Rate-limited API processing
workflow.add_node("BatchProcessorNode", "api_batch_processor", {
    "operation": "process_data_batches",
    "data_source": "api_data",

    # Batch optimization
    "batch_size": 500,
    "adaptive_batch_sizing": True,
    "min_batch_size": 100,
    "max_batch_size": 2000,

    # Concurrency control
    "processing_strategy": "adaptive_parallel",
    "max_concurrent_batches": 15,
    "rate_limit_per_second": 50,

    # Error handling
    "error_handling": "continue_with_logging",
    "max_retry_attempts": 3,
    "retry_delay_seconds": 5,

    # Performance monitoring
    "enable_performance_monitoring": True,
    "performance_threshold_ms": 5000
})

# Streaming strategy for real-time data
workflow.add_node("BatchProcessorNode", "streaming_processor", {
    "operation": "process_data_batches",
    "processing_strategy": "streaming",
    "stream_buffer_size": 1000,
    "stream_timeout_seconds": 30
})
```

## Automatic Credential Rotation

### Basic Credential Rotation

Keep credentials secure with automatic rotation:

```python
from kailash.nodes.security.rotating_credentials import RotatingCredentialNode

# Start automatic rotation
credential_rotator = RotatingCredentialNode(
    name="api_rotator",
    operation="start_rotation",
    credential_name="api_service_token",
    check_interval=3600,  # Check every hour
    expiration_threshold=86400,  # Rotate 24 hours before expiry
    refresh_sources=["vault", "aws_secrets"]
)

# Add to workflow
workflow.add_node("RotatingCredentialNode", "credential_rotator", {
    "operation": "start_rotation",
    "credential_name": "api_key",
    "check_interval": 3600,
    "expiration_threshold": 86400,
    "refresh_sources": ["vault"]
})
```

### Enterprise Credential Management

Configure enterprise-grade credential rotation:

```python
# Zero-downtime rotation with notifications
workflow.add_node("RotatingCredentialNode", "enterprise_rotator", {
    "operation": "start_rotation",
    "credential_name": "production_api_key",

    # Rotation policy
    "check_interval": 1800,  # Every 30 minutes
    "expiration_threshold": 172800,  # 48 hours before expiry
    "rotation_policy": "proactive",

    # Refresh sources (tried in order)
    "refresh_sources": ["vault", "aws_secrets", "azure_key_vault"],
    "refresh_config": {
        "vault": {"path": "secret/prod/api-keys"},
        "aws_secrets": {"region": "us-east-1"},
        "azure_key_vault": {"vault_url": "https://company-kv.vault.azure.net/"}
    },

    # Zero-downtime rotation
    "zero_downtime": True,
    "rollback_on_failure": True,

    # Notifications
    "notification_webhooks": ["https://alerts.company.com/webhook"],
    "notification_emails": ["devops@company.com"],

    # Audit
    "audit_log_enabled": True
})

# Scheduled rotation
workflow.add_node("RotatingCredentialNode", "scheduled_rotator", {
    "operation": "start_rotation",
    "credential_name": "weekly_api_key",
    "rotation_policy": "scheduled",
    "schedule_cron": "0 2 * * 1",  # Every Monday at 2 AM
    "zero_downtime": True
})
```

## Comprehensive Enterprise Example

Here's a complete enterprise workflow combining multiple advanced features:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create enterprise workflow
workflow = WorkflowBuilder()

# 1. Set up credential rotation
workflow.add_node("RotatingCredentialNode", "credential_rotation", {
    "operation": "start_rotation",
    "credential_name": "platform_credentials",
    "check_interval": 3600,
    "expiration_threshold": 86400,
    "refresh_sources": ["vault"],
    "zero_downtime": True
})

# 2. Data ingestion with access control
workflow.add_node("PythonCodeNode", "access_check", {
    "code": """
from kailash.access_control.managers import AccessControlManager
from kailash.access_control import UserContext, NodePermission

acm = AccessControlManager(strategy="abac")
user = UserContext(
    user_id=user_id,
    tenant_id=tenant_id,
    roles=user_roles,
    attributes=user_attributes
)

decision = acm.check_node_access(
    user=user,
    resource_id="enterprise_data",
    permission=NodePermission.EXECUTE
)

result = {
    "allowed": decision.allowed,
    "reason": decision.reason if not decision.allowed else None
}
"""
})

# 3. Batch processing with monitoring
workflow.add_node("BatchProcessorNode", "batch_processor", {
    "operation": "process_data_batches",
    "batch_size": 1000,
    "processing_strategy": "adaptive_parallel",
    "max_concurrent_batches": 10,
    "enable_performance_monitoring": True
})

# 4. Data lineage tracking
workflow.add_node("DataLineageNode", "lineage_tracker", {
    "operation": "track_transformation",
    "source_info": {"system": "Source", "table": "raw_data"},
    "transformation_type": "enrichment",
    "compliance_frameworks": ["GDPR", "SOX"],
    "audit_trail_enabled": True
})

# 5. Result aggregation
workflow.add_node("PythonCodeNode", "aggregate_results", {
    "code": """
# Aggregate all results
summary = {
    "processed_batches": batch_results.get("batch_count", 0),
    "lineage_tracked": lineage_results.get("tracking_id") is not None,
    "credentials_rotated": credential_results.get("rotation_status") == "success",
    "total_records": batch_results.get("total_records", 0),
    "processing_time": batch_results.get("total_duration", 0)
}

result = {"summary": summary}
"""
})

# Connect workflow with conditional execution
workflow.add_connection("access_check", "result.allowed", "batch_processor", "should_run")
workflow.add_connection("batch_processor", "result", "lineage_tracker", "processing_info")
workflow.add_connection("batch_processor", "result", "aggregate_results", "batch_results")
workflow.add_connection("lineage_tracker", "result", "aggregate_results", "lineage_results")
workflow.add_connection("credential_rotation", "result", "aggregate_results", "credential_results")

# Execute with advanced runtime configuration
# LocalRuntime supports 29 configuration parameters for fine-tuned control
runtime = LocalRuntime(
    max_workers=8,
    timeout=600.0,
    enable_logging=True
)

# Run workflow - ALWAYS call .build() before execution
results, run_id = runtime.execute(workflow.build(), parameters={
    "access_check": {
        "user_id": "analyst_001",
        "tenant_id": "enterprise",
        "user_roles": ["analyst"],
        "user_attributes": {"clearance": "confidential"}
    },
    "batch_processor": {
        "data_source": "production_dataset"
    }
})

# Display results
summary = results.get("aggregate_results", {}).get("result", {}).get("summary", {})
print(f"Enterprise workflow completed:")
print(f"- Processed batches: {summary.get('processed_batches')}")
print(f"- Total records: {summary.get('total_records')}")
print(f"- Processing time: {summary.get('processing_time'):.2f}s")
```

## Advanced Runtime Configuration

### Runtime Parameters (29 Available)

Both `LocalRuntime` and `AsyncLocalRuntime` support extensive configuration:

```python
from kailash.runtime import LocalRuntime, AsyncLocalRuntime

# Synchronous runtime for CLI/scripts
runtime = LocalRuntime(
    max_workers=8,              # Parallel execution workers
    timeout=600.0,              # Workflow timeout in seconds
    enable_logging=True,        # Enable detailed logging
    retry_on_failure=True,      # Auto-retry failed nodes
    max_retries=3,              # Maximum retry attempts
    # ... 24 more parameters available
)

# Asynchronous runtime for Docker/FastAPI
async_runtime = AsyncLocalRuntime(
    max_workers=10,             # Concurrent async tasks
    timeout=300.0,              # Async workflow timeout
    enable_logging=True,        # Detailed async logging
    # Same parameter set as LocalRuntime
)
```

**Note**: Both runtimes inherit from `BaseRuntime` which provides:
- **ValidationMixin**: Parameter validation and type checking
- **ParameterHandlingMixin**: Template resolution (${param}) and parameter injection
- Consistent execution architecture across sync/async contexts

For custom runtime development, extend `BaseRuntime` to leverage these mixins.

## Best Practices Summary

### Enterprise Development Guidelines
1. **Security First**: Always implement proper authentication and access control
2. **Resilience Built-in**: Configure retry policies and fallback strategies
3. **Monitoring Everything**: Enable comprehensive logging and metrics
4. **Compliance Ready**: Track data lineage and maintain audit trails
5. **Performance Optimized**: Use batch processing for large datasets

### Production Readiness
1. **Access Control**: Implement RBAC/ABAC for all sensitive operations
2. **Credential Management**: Use automatic rotation with zero downtime
3. **Data Governance**: Track transformations and ensure compliance
4. **Error Handling**: Plan for failures with retry and fallback patterns
5. **Resource Management**: Monitor and optimize resource usage
6. **Runtime Selection**: Use AsyncLocalRuntime for Docker/FastAPI, LocalRuntime for CLI/scripts

## Related Guides

**Prerequisites:**
- [Fundamentals](01-fundamentals.md) - Core SDK concepts
- [Workflows](02-workflows.md) - Basic workflow patterns

**Next Steps:**
- [Production](04-production.md) - Production deployment
- [Troubleshooting](05-troubleshooting.md) - Debug complex issues
- [Custom Development](06-custom-development.md) - Build custom nodes

---

**Master these advanced features to build enterprise-grade workflows with security, compliance, and resilience built-in!**
