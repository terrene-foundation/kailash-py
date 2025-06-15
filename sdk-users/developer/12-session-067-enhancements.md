# Session 067 Enhancements - Enterprise Workflow Automation

This guide covers the new enterprise-grade enhancements introduced in Session 067, including business workflow templates, data lineage tracking, and automatic credential rotation.

## 🏭 Business Workflow Templates

Pre-built templates for common enterprise workflow patterns that can be customized for your organization.

### Available Templates

```python
from kailash.workflow.templates import BusinessWorkflowTemplates
from kailash.workflow import Workflow

# Create a workflow to use with templates
workflow = Workflow("enterprise_pipeline", "Enterprise Data Pipeline")

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

# 4. Data Processing Pipeline
BusinessWorkflowTemplates.data_processing_pipeline(
    workflow,
    data_sources=["database", "files", "apis"],
    processing_stages=["clean", "transform", "analyze"],
    output_destinations=["warehouse", "reports", "alerts"]
)
```

### Template Customization

Each template returns a node ID that you can use to customize the workflow:

```python
# Get the template node ID
template_node_id = BusinessWorkflowTemplates.investment_data_pipeline(
    workflow,
    data_sources=["bloomberg"],
    analysis_types=["risk"],
    notification_channels=["email"]
)

# Add additional processing after the template
workflow.add_node("custom_analysis", CustomAnalysisNode())
workflow.connect(template_node_id, "custom_analysis")
```

## 📊 Data Lineage Tracking

Track data transformations, access patterns, and compliance requirements throughout your workflows.

### Basic Data Lineage

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

### Compliance-Aware Lineage

```python
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

# Get compliance report
compliance_report = DataLineageNode(
    name="compliance_reporter",
    operation="generate_compliance_report",
    compliance_frameworks=["GDPR", "SOX", "HIPAA"],
    report_format="detailed",
    include_recommendations=True
)
```

### Access Pattern Analysis

```python
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

## 🔄 Batch Processing Optimization

Intelligent batch processing with automatic optimization and rate limiting.

### Basic Batch Processing

```python
from kailash.nodes.enterprise.batch_processor import BatchProcessorNode

# Process large datasets in optimized batches
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

### Advanced Batch Configuration

```python
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

### Batch Processing Strategies

```python
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

## 🔐 Automatic Credential Rotation

Zero-downtime credential rotation with enterprise notifications and audit trails.

### Basic Credential Rotation

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

### Enterprise Credential Rotation

```python
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

### Credential Rotation Operations

```python
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

# Get audit log
audit_retriever = RotatingCredentialNode(
    name="audit_retriever",
    operation="get_audit_log",
    credential_name="api_service_token"  # Optional: specific credential
)

# Stop rotation
rotation_stopper = RotatingCredentialNode(
    name="rotation_stopper",
    operation="stop_rotation",
    credential_name="api_service_token"
)
```

### Scheduled Credential Rotation

```python
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

## 🔗 Combining Session 067 Features

Create comprehensive enterprise workflows that use all new features:

```python
from kailash.workflow import Workflow
from kailash.workflow.templates import BusinessWorkflowTemplates
from kailash.nodes.enterprise.data_lineage import DataLineageNode
from kailash.nodes.enterprise.batch_processor import BatchProcessorNode
from kailash.nodes.security.rotating_credentials import RotatingCredentialNode

# Create enterprise workflow
workflow = Workflow("enterprise_data_platform", "Enterprise Data Platform")

# 1. Set up credential rotation
workflow.add_node("credential_rotation", RotatingCredentialNode(
    name="credential_rotation",
    operation="start_rotation",
    credential_name="platform_credentials",
    check_interval=3600,
    expiration_threshold=86400,
    refresh_sources=["vault", "aws_secrets"],
    zero_downtime=True,
    notification_webhooks=["https://alerts.company.com/webhook"]
))

# 2. Apply business workflow template
template_node = BusinessWorkflowTemplates.data_processing_pipeline(
    workflow,
    data_sources=["database", "apis", "files"],
    processing_stages=["validate", "transform", "enrich"],
    output_destinations=["warehouse", "reports"]
)

# 3. Add data lineage tracking
workflow.add_node("lineage_tracker", DataLineageNode(
    name="lineage_tracker",
    operation="track_transformation",
    source_info={"system": "Source", "table": "raw_data"},
    transformation_type="enrichment",
    compliance_frameworks=["GDPR", "SOX"],
    audit_trail_enabled=True
))

# 4. Add batch processing optimization
workflow.add_node("batch_processor", BatchProcessorNode(
    name="batch_processor",
    operation="process_data_batches",
    batch_size=1000,
    processing_strategy="adaptive_parallel",
    max_concurrent_batches=10,
    rate_limit_per_second=50,
    enable_performance_monitoring=True
))

# Connect the workflow
workflow.connect(template_node, "lineage_tracker")
workflow.connect("lineage_tracker", "batch_processor")
```

## 🎯 Best Practices

### 1. Credential Rotation
- Use proactive rotation policies for production systems
- Always enable zero-downtime rotation for high-availability services
- Set up comprehensive notification channels for rotation events
- Monitor audit logs regularly for security compliance

### 2. Data Lineage
- Track all data transformations, especially for regulated data
- Enable compliance frameworks relevant to your industry
- Use access pattern analysis to detect anomalies
- Generate regular compliance reports for audits

### 3. Batch Processing
- Start with adaptive strategies and tune based on performance
- Monitor performance metrics to optimize batch sizes
- Use appropriate error handling for your data quality requirements
- Consider rate limiting when processing external APIs

### 4. Workflow Templates
- Customize templates to match your organization's standards
- Add organization-specific nodes after applying templates
- Use templates as starting points, not rigid constraints
- Document customizations for team knowledge sharing

## 🔍 Example: Complete Enterprise Pipeline

See `/examples/feature_examples/` for comprehensive examples of each feature:
- `validation/node_validation_example.py` - Real-world validation scenarios
- `security/secure_logging_example.py` - Production logging patterns
- `integrations/oauth2_enhanced_example.py` - Multi-provider OAuth flows
- `ai/llm_monitoring_example.py` - Ollama integration and monitoring
- `code/python_import_management_example.py` - Security scanning workflows

Each example demonstrates production-ready patterns using Docker and Ollama integration as requested.
