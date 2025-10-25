# Node Catalog

*Complete catalog of all Kailash SDK nodes with examples and usage patterns*

Version: 0.6.3 | Last Updated: 2025-07-03

## 🎯 Quick Reference

This catalog provides comprehensive documentation for all 110+ Kailash SDK nodes. For quick node selection, use the [Node Selection Guide](nodes/node-selection-guide.md).

## 📋 Node Categories

| Category | Count | Description | Quick Access |
|----------|-------|-------------|--------------|
| **AI & LLM** | 15+ | LLM agents, embeddings, vision | [AI Nodes](#ai--llm-nodes) |
| **Data** | 20+ | File readers, databases, APIs | [Data Nodes](#data-nodes) |
| **Transform** | 25+ | Data transformation, filtering | [Transform Nodes](#transform-nodes) |
| **Logic** | 15+ | Routing, merging, conditions | [Logic Nodes](#logic-nodes) |
| **API** | 10+ | HTTP, REST, GraphQL clients | [API Nodes](#api-nodes) |
| **Security** | 15+ | Auth, RBAC, ABAC, encryption | [Security Nodes](#security-nodes) |
| **Admin** | 10+ | User/role management | [Admin Nodes](#admin-nodes) |
| **Enterprise** | 10+ | Advanced enterprise features | [Enterprise Nodes](#enterprise-nodes) |

## 🤖 AI & LLM Nodes

### LLMAgentNode
**Purpose**: Execute LLM-powered conversations and tasks
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.ai import LLMAgentNode

node = LLMAgentNode(
    name="chat_agent",
    model="llama3.2:3b",
    prompt="You are a helpful assistant. Answer: {question}",
    temperature=0.7
)
```
**Key Features**: Multi-turn conversations, tool integration, streaming responses
**Use Cases**: Chatbots, content generation, analysis

### MonitoredLLMAgentNode
**Purpose**: LLM agent with comprehensive monitoring and metrics
```python
from kailash.nodes.ai import MonitoredLLMAgentNode

node = MonitoredLLMAgentNode(
    name="monitored_agent",
    model="llama3.2:3b",
    prompt="Analyze this data: {data}",
    enable_metrics=True,
    log_conversations=True
)
```
**Key Features**: Performance metrics, conversation logging, error tracking
**Use Cases**: Production LLM deployments, quality monitoring

### EmbeddingGeneratorNode
**Purpose**: Generate embeddings for text or data
```python
from kailash.nodes.ai import EmbeddingGeneratorNode

node = EmbeddingGeneratorNode(
    name="embedder",
    model="all-minilm",
    text_field="content"
)
```
**Key Features**: Multiple embedding models, batch processing
**Use Cases**: RAG systems, semantic search, clustering

### A2AAgentNode
**Purpose**: Agent-to-agent communication and coordination
```python
from kailash.nodes.ai import A2AAgentNode

node = A2AAgentNode(
    name="coordinator",
    agent_type="coordinator",
    communication_protocol="direct"
)
```
**Key Features**: Multi-agent coordination, protocol support
**Use Cases**: Multi-agent systems, distributed AI tasks

### SelfOrganizingAgentNode
**Purpose**: Self-organizing and adaptive agent behavior
```python
from kailash.nodes.ai import SelfOrganizingAgentNode

node = SelfOrganizingAgentNode(
    name="adaptive_agent",
    learning_rate=0.01,
    adaptation_strategy="reinforcement"
)
```
**Key Features**: Adaptive behavior, learning capabilities
**Use Cases**: Dynamic environments, adaptive systems

## 📊 Data Nodes

### CSVReaderNode
**Purpose**: Read and parse CSV files
```python
from kailash.nodes.data import CSVReaderNode

node = CSVReaderNode(
    name="csv_reader",
    file_path="/data/input.csv",
    delimiter=",",
    encoding="utf-8"
)
```
**Key Features**: Flexible parsing, encoding support, large file handling
**Use Cases**: Data ingestion, file processing, ETL pipelines

### JSONReaderNode
**Purpose**: Read and parse JSON files
```python
from kailash.nodes.data import JSONReaderNode

node = JSONReaderNode(
    name="json_reader",
    file_path="/data/config.json",
    schema_validation=True
)
```
**Key Features**: Schema validation, nested JSON support
**Use Cases**: Configuration loading, API data processing

### SQLDatabaseNode
**Purpose**: Execute SQL queries synchronously
```python
from kailash.nodes.data import SQLDatabaseNode

node = SQLDatabaseNode(
    name="db_query",
    connection_string="postgresql://user:pass@localhost/db",
    query="SELECT * FROM users WHERE active = true"
)
```
**Key Features**: Multiple database support, parameterized queries
**Use Cases**: Data retrieval, reporting, batch processing

### AsyncSQLDatabaseNode
**Purpose**: Execute SQL queries asynchronously
```python
from kailash.nodes.data import AsyncSQLDatabaseNode

node = AsyncSQLDatabaseNode(
    name="async_db_query",
    connection_string="postgresql://user:pass@localhost/db",
    query="SELECT * FROM large_table",
    pool_size=10
)
```
**Key Features**: Connection pooling, high performance, concurrent queries
**Use Cases**: High-throughput applications, real-time data processing

### DirectoryReaderNode
**Purpose**: Read and process multiple files from directories
```python
from kailash.nodes.data import DirectoryReaderNode

node = DirectoryReaderNode(
    name="dir_reader",
    directory_path="/data/files",
    file_pattern="*.txt",
    recursive=True
)
```
**Key Features**: Pattern matching, recursive scanning, batch processing
**Use Cases**: Bulk file processing, document ingestion

### ExcelReaderNode
**Purpose**: Read Excel files with multiple sheets
```python
from kailash.nodes.data import ExcelReaderNode

node = ExcelReaderNode(
    name="excel_reader",
    file_path="/data/report.xlsx",
    sheet_name="Sheet1",
    header_row=0
)
```
**Key Features**: Multi-sheet support, flexible header handling
**Use Cases**: Report processing, data analysis

### XMLReaderNode
**Purpose**: Parse XML documents
```python
from kailash.nodes.data import XMLReaderNode

node = XMLReaderNode(
    name="xml_reader",
    file_path="/data/config.xml",
    xpath_expression="//configuration"
)
```
**Key Features**: XPath support, namespace handling
**Use Cases**: Configuration parsing, XML data processing

## 🔄 Transform Nodes

### DataTransformerNode
**Purpose**: Transform data using configurable rules
```python
from kailash.nodes.transform import DataTransformerNode

node = DataTransformerNode(
    name="transformer",
    transformations=[
        {"type": "rename", "from": "old_name", "to": "new_name"},
        {"type": "convert", "field": "date", "to_type": "datetime"}
    ]
)
```
**Key Features**: Multiple transformation types, chaining
**Use Cases**: Data cleaning, schema mapping

### FilterNode
**Purpose**: Filter data based on conditions
```python
from kailash.nodes.transform import FilterNode

node = FilterNode(
    name="filter",
    filter_condition="age > 18 and status == 'active'",
    filter_type="pandas"
)
```
**Key Features**: Multiple filter engines, complex conditions
**Use Cases**: Data filtering, quality control

### AggregationNode
**Purpose**: Aggregate data using various functions
```python
from kailash.nodes.transform import AggregationNode

node = AggregationNode(
    name="aggregator",
    group_by=["category", "region"],
    aggregations={
        "sales": "sum",
        "orders": "count",
        "avg_value": "mean"
    }
)
```
**Key Features**: Multi-field grouping, custom aggregations
**Use Cases**: Data summarization, reporting

### JoinNode
**Purpose**: Join multiple datasets
```python
from kailash.nodes.transform import JoinNode

node = JoinNode(
    name="joiner",
    join_type="inner",
    left_key="id",
    right_key="user_id"
)
```
**Key Features**: Multiple join types, key mapping
**Use Cases**: Data integration, relationship building

### ValidationNode
**Purpose**: Validate data quality and schemas
```python
from kailash.nodes.transform import ValidationNode

node = ValidationNode(
    name="validator",
    schema={
        "id": {"type": "integer", "required": True},
        "email": {"type": "email", "required": True}
    },
    validation_level="strict"
)
```
**Key Features**: Schema validation, custom rules
**Use Cases**: Data quality assurance

## 🔀 Logic Nodes

### SwitchNode
**Purpose**: Route data based on conditions
```python
from kailash.nodes.logic import SwitchNode

node = SwitchNode(
    name="router",
    condition_field="user_type",
    routes={
        "premium": "premium_processing",
        "standard": "standard_processing",
        "default": "basic_processing"
    }
)
```
**Key Features**: Multi-path routing, default handling
**Use Cases**: Workflow branching, conditional processing

### MergeNode
**Purpose**: Merge data from multiple sources
```python
from kailash.nodes.logic import MergeNode

node = MergeNode(
    name="merger",
    merge_strategy="union",
    conflict_resolution="latest"
)
```
**Key Features**: Multiple merge strategies, conflict resolution
**Use Cases**: Data consolidation, workflow convergence

### ConditionalNode
**Purpose**: Execute conditional logic
```python
from kailash.nodes.logic import ConditionalNode

node = ConditionalNode(
    name="condition",
    condition="total_amount > 1000",
    true_path="high_value_processing",
    false_path="standard_processing"
)
```
**Key Features**: Boolean conditions, path selection
**Use Cases**: Decision making, flow control

### LoopNode
**Purpose**: Execute iterative processing
```python
from kailash.nodes.logic import LoopNode

node = LoopNode(
    name="iterator",
    loop_type="for_each",
    iteration_field="items",
    max_iterations=100
)
```
**Key Features**: Multiple loop types, safety limits
**Use Cases**: Batch processing, iterative operations

## 🌐 API Nodes

### HTTPRequestNode
**Purpose**: Make HTTP requests
```python
from kailash.nodes.api import HTTPRequestNode

node = HTTPRequestNode(
    name="http_client",
    url="https://api.example.com/data",
    method="GET",
    headers={"Authorization": "Bearer {token}"},
    timeout=30
)
```
**Key Features**: All HTTP methods, authentication, error handling
**Use Cases**: API integration, data fetching

### RESTClientNode
**Purpose**: REST API client with advanced features
```python
from kailash.nodes.api import RESTClientNode

node = RESTClientNode(
    name="rest_client",
    base_url="https://api.example.com",
    endpoint="/users",
    auth_type="oauth2",
    retry_policy={"max_retries": 3, "backoff": "exponential"}
)
```
**Key Features**: OAuth support, retry policies, pagination
**Use Cases**: Production API integration

### GraphQLClientNode
**Purpose**: GraphQL API client
```python
from kailash.nodes.api import GraphQLClientNode

node = GraphQLClientNode(
    name="graphql_client",
    endpoint="https://api.example.com/graphql",
    query="""
        query GetUser($id: ID!) {
            user(id: $id) { name email }
        }
    """,
    variables={"id": "{user_id}"}
)
```
**Key Features**: Query validation, variable substitution
**Use Cases**: GraphQL API integration

### WebSocketNode
**Purpose**: WebSocket communication
```python
from kailash.nodes.api import WebSocketNode

node = WebSocketNode(
    name="websocket",
    url="wss://api.example.com/stream",
    message_handler="json",
    auto_reconnect=True
)
```
**Key Features**: Auto-reconnection, message handling
**Use Cases**: Real-time communication, streaming data

## 🔐 Security Nodes

### AccessControlNode
**Purpose**: Implement access control policies
```python
from kailash.nodes.security import AccessControlNode

node = AccessControlNode(
    name="access_control",
    strategy="rbac",  # or "abac", "hybrid"
    resource="sensitive_data",
    required_permission="read"
)
```
**Key Features**: RBAC/ABAC/Hybrid strategies, policy enforcement
**Use Cases**: Authorization, data protection

### AuthenticationNode
**Purpose**: User authentication
```python
from kailash.nodes.security import AuthenticationNode

node = AuthenticationNode(
    name="auth",
    auth_method="jwt",
    token_field="authorization",
    validate_expiry=True
)
```
**Key Features**: Multiple auth methods, token validation
**Use Cases**: User verification, session management

### EncryptionNode
**Purpose**: Data encryption and decryption
```python
from kailash.nodes.security import EncryptionNode

node = EncryptionNode(
    name="encryptor",
    operation="encrypt",
    algorithm="AES-256",
    key_source="environment"
)
```
**Key Features**: Multiple algorithms, key management
**Use Cases**: Data protection, compliance

### ThreatDetectionNode
**Purpose**: Detect security threats
```python
from kailash.nodes.security import ThreatDetectionNode

node = ThreatDetectionNode(
    name="threat_detector",
    detection_rules=["sql_injection", "xss", "rate_limiting"],
    action_on_threat="block"
)
```
**Key Features**: Rule-based detection, automated response
**Use Cases**: Security monitoring, threat prevention

### AuditLogNode
**Purpose**: Security audit logging
```python
from kailash.nodes.security import AuditLogNode

node = AuditLogNode(
    name="audit_logger",
    log_level="INFO",
    include_user_data=True,
    retention_days=90
)
```
**Key Features**: Configurable logging, retention policies
**Use Cases**: Compliance, security monitoring

## 👥 Admin Nodes

### UserManagementNode
**Purpose**: User lifecycle management
```python
from kailash.nodes.admin import UserManagementNode

node = UserManagementNode(
    name="user_mgmt",
    operation="create",  # create, read, update, delete
    user_data={
        "username": "{username}",
        "email": "{email}",
        "role": "user"
    }
)
```
**Key Features**: CRUD operations, validation, password policies
**Use Cases**: User administration, onboarding

### RoleManagementNode
**Purpose**: Role and permission management
```python
from kailash.nodes.admin import RoleManagementNode

node = RoleManagementNode(
    name="role_mgmt",
    operation="assign",
    role_name="admin",
    target_user="{user_id}",
    permissions=["read", "write", "delete"]
)
```
**Key Features**: Role assignment, permission management
**Use Cases**: Authorization setup, role-based access

### SystemConfigNode
**Purpose**: System configuration management
```python
from kailash.nodes.admin import SystemConfigNode

node = SystemConfigNode(
    name="config_mgmt",
    config_type="application",
    settings={
        "max_connections": 100,
        "timeout": 30,
        "debug_mode": False
    }
)
```
**Key Features**: Configuration validation, versioning
**Use Cases**: System administration, deployment

### BackupNode
**Purpose**: Data backup and recovery
```python
from kailash.nodes.admin import BackupNode

node = BackupNode(
    name="backup",
    backup_type="incremental",
    target_location="/backups/",
    compression=True,
    encryption=True
)
```
**Key Features**: Multiple backup types, compression, encryption
**Use Cases**: Data protection, disaster recovery

## 🏢 Enterprise Nodes

### MultiFactorAuthNode
**Purpose**: Multi-factor authentication
```python
from kailash.nodes.enterprise import MultiFactorAuthNode

node = MultiFactorAuthNode(
    name="mfa",
    factors=["password", "totp", "sms"],
    required_factors=2,
    timeout_minutes=5
)
```
**Key Features**: Multiple factor types, flexible requirements
**Use Cases**: Enhanced security, compliance

### ComplianceNode
**Purpose**: Compliance validation and enforcement
```python
from kailash.nodes.enterprise import ComplianceNode

node = ComplianceNode(
    name="compliance",
    regulations=["GDPR", "HIPAA", "SOX"],
    validation_level="strict",
    auto_remediation=True
)
```
**Key Features**: Multi-regulation support, auto-remediation
**Use Cases**: Compliance automation, risk management

### DataGovernanceNode
**Purpose**: Data governance and lineage
```python
from kailash.nodes.enterprise import DataGovernanceNode

node = DataGovernanceNode(
    name="governance",
    track_lineage=True,
    data_classification="sensitive",
    retention_policy="7_years"
)
```
**Key Features**: Data lineage, classification, retention
**Use Cases**: Data management, compliance

### WorkflowOrchestrationNode
**Purpose**: Advanced workflow orchestration
```python
from kailash.nodes.enterprise import WorkflowOrchestrationNode

node = WorkflowOrchestrationNode(
    name="orchestrator",
    workflows=["data_pipeline", "ml_training"],
    scheduling="cron",
    dependency_management=True
)
```
**Key Features**: Multi-workflow management, scheduling
**Use Cases**: Complex automation, enterprise workflows

## 🔧 Code & Utility Nodes

### PythonCodeNode
**Purpose**: Execute Python code dynamically
```python
from kailash.nodes.code import PythonCodeNode

node = PythonCodeNode(
    name="python_exec",
    code="""
def process_data(data):
    return {"result": data.upper()}
    """,
    function_name="process_data"
)
```
**Key Features**: Dynamic execution, security sandboxing
**Use Cases**: Custom logic, data processing

### AsyncPythonCodeNode
**Purpose**: Execute Python code asynchronously with full PythonCodeNode feature parity
```python
from kailash.nodes.code import AsyncPythonCodeNode

# LEGACY PATTERN: Single result (still works)
node = AsyncPythonCodeNode(
    name="async_python",
    code="""
async def async_process(data):
    await asyncio.sleep(0.1)
    return {"result": data.processed}
    """,
    function_name="async_process"
)

# RECOMMENDED (v0.9.30+): Multi-output pattern - exports ALL variables
node = AsyncPythonCodeNode(
    name="async_multi_output",
    code="""
import asyncio

# Fetch data concurrently
async def fetch_data(id):
    await asyncio.sleep(0.1)
    return {"id": id, "value": id * 2}

ids = [1, 2, 3, 4, 5]
tasks = [fetch_data(id) for id in ids]
results = await asyncio.gather(*tasks)

# All variables are automatically exported (no 'result' needed!)
processed_data = results
total_count = len(results)
average_value = sum(r["value"] for r in results) / len(results)
processing_complete = True
    """
)
```
**Key Features**:
- ✅ **Full multi-output support** (v0.9.30+) - exports ALL variables like PythonCodeNode
- ✅ **Complete sync/async parity** - identical behavior to PythonCodeNode
- ✅ Async execution, concurrent processing (asyncio.gather, asyncio.create_task)
- ✅ Full exception handling (NameError, AttributeError, ZeroDivisionError, etc.)
- ✅ Iterator support (iter/next), frozenset, bytes, bytearray, complex
- ✅ Template resolution in nested parameters (v0.9.30+)

**Use Cases**: High-performance custom logic, async I/O operations, concurrent data processing, database queries with asyncpg/aiomysql, HTTP requests with aiohttp

**Multi-Output Pattern** (v0.9.30+): Both PythonCodeNode and AsyncPythonCodeNode export ALL non-private variables. No need to wrap in `result = {...}`.

**Available Exceptions**: NameError, AttributeError, ZeroDivisionError, StopIteration, AssertionError, ImportError, IOError, ArithmeticError

**See Also**: [dataflow-dynamic-updates](../../.claude/skills/02-dataflow/dataflow-dynamic-updates.md) for examples with DataFlow

### ScriptExecutorNode
**Purpose**: Execute external scripts
```python
from kailash.nodes.code import ScriptExecutorNode

node = ScriptExecutorNode(
    name="script_exec",
    script_path="/scripts/process.py",
    interpreter="python3",
    environment_vars={"DATA_PATH": "/data"}
)
```
**Key Features**: Multiple interpreters, environment control
**Use Cases**: Legacy script integration

## 📈 Monitoring & Metrics Nodes

### MetricsCollectorNode
**Purpose**: Collect and aggregate metrics
```python
from kailash.nodes.monitoring import MetricsCollectorNode

node = MetricsCollectorNode(
    name="metrics",
    metrics=["execution_time", "memory_usage", "error_rate"],
    aggregation_window="1m",
    export_format="prometheus"
)
```
**Key Features**: Multiple metrics, export formats
**Use Cases**: Performance monitoring, alerting

### HealthCheckNode
**Purpose**: System health monitoring
```python
from kailash.nodes.monitoring import HealthCheckNode

node = HealthCheckNode(
    name="health_check",
    checks=["database", "api", "memory"],
    timeout=10,
    alert_on_failure=True
)
```
**Key Features**: Multi-component checks, alerting
**Use Cases**: System monitoring, reliability

### AlertingNode
**Purpose**: Send alerts and notifications
```python
from kailash.nodes.monitoring import AlertingNode

node = AlertingNode(
    name="alerting",
    alert_type="email",
    recipients=["admin@example.com"],
    severity="high",
    template="System error: {error_message}"
)
```
**Key Features**: Multiple channels, templates
**Use Cases**: Incident response, notifications

## 🎯 Specialized Nodes

### RecommendationNode
**Purpose**: Generate recommendations
```python
from kailash.nodes.ml import RecommendationNode

node = RecommendationNode(
    name="recommender",
    algorithm="collaborative_filtering",
    user_id="{user_id}",
    max_recommendations=10
)
```
**Key Features**: Multiple algorithms, personalization
**Use Cases**: E-commerce, content recommendation

### OCRNode
**Purpose**: Optical character recognition
```python
from kailash.nodes.vision import OCRNode

node = OCRNode(
    name="ocr",
    image_source="{image_path}",
    language="en",
    confidence_threshold=0.8
)
```
**Key Features**: Multi-language, confidence scoring
**Use Cases**: Document processing, data extraction

### QRCodeNode
**Purpose**: QR code generation and reading
```python
from kailash.nodes.vision import QRCodeNode

node = QRCodeNode(
    name="qr_processor",
    operation="generate",  # or "read"
    data="{qr_data}",
    format="PNG"
)
```
**Key Features**: Generation and reading, multiple formats
**Use Cases**: Document processing, mobile integration

## 🔍 Search & Indexing Nodes

### ElasticsearchNode
**Purpose**: Elasticsearch integration
```python
from kailash.nodes.search import ElasticsearchNode

node = ElasticsearchNode(
    name="search",
    host="localhost:9200",
    index="documents",
    operation="search",
    query={"match": {"content": "{search_term}"}}
)
```
**Key Features**: Full-text search, complex queries
**Use Cases**: Search engines, document retrieval

### VectorSearchNode
**Purpose**: Vector similarity search
```python
from kailash.nodes.search import VectorSearchNode

node = VectorSearchNode(
    name="vector_search",
    embedding_model="sentence-transformers",
    query_vector="{embedding}",
    top_k=10,
    similarity_threshold=0.8
)
```
**Key Features**: Semantic search, similarity scoring
**Use Cases**: RAG systems, semantic search

## 📊 Data Visualization Nodes

### ChartGeneratorNode
**Purpose**: Generate charts and graphs
```python
from kailash.nodes.visualization import ChartGeneratorNode

node = ChartGeneratorNode(
    name="chart_gen",
    chart_type="line",
    data_source="{chart_data}",
    x_axis="date",
    y_axis="value",
    output_format="PNG"
)
```
**Key Features**: Multiple chart types, customization
**Use Cases**: Reporting, dashboards

### DashboardNode
**Purpose**: Create interactive dashboards
```python
from kailash.nodes.visualization import DashboardNode

node = DashboardNode(
    name="dashboard",
    widgets=[
        {"type": "chart", "config": {...}},
        {"type": "table", "config": {...}}
    ],
    layout="grid",
    auto_refresh=60
)
```
**Key Features**: Interactive widgets, real-time updates
**Use Cases**: Business intelligence, monitoring

## 🔄 Integration & ETL Nodes

### ETLPipelineNode
**Purpose**: Complete ETL pipeline
```python
from kailash.nodes.etl import ETLPipelineNode

node = ETLPipelineNode(
    name="etl_pipeline",
    extract_config={"source": "database", "query": "..."},
    transform_config={"operations": [...]},
    load_config={"target": "warehouse", "table": "facts"}
)
```
**Key Features**: Complete ETL process, configurable stages
**Use Cases**: Data warehousing, batch processing

### MessageQueueNode
**Purpose**: Message queue integration
```python
from kailash.nodes.integration import MessageQueueNode

node = MessageQueueNode(
    name="queue",
    queue_type="rabbitmq",
    queue_name="data_processing",
    operation="publish",
    message="{data}"
)
```
**Key Features**: Multiple queue systems, pub/sub
**Use Cases**: Microservices, async processing

## 💾 Storage Nodes

### S3StorageNode
**Purpose**: AWS S3 storage operations
```python
from kailash.nodes.storage import S3StorageNode

node = S3StorageNode(
    name="s3_storage",
    bucket_name="my-bucket",
    operation="upload",
    key="{file_key}",
    local_path="{file_path}"
)
```
**Key Features**: All S3 operations, security
**Use Cases**: Cloud storage, backup

### RedisNode
**Purpose**: Redis cache operations
```python
from kailash.nodes.storage import RedisNode

node = RedisNode(
    name="cache",
    operation="set",
    key="{cache_key}",
    value="{data}",
    ttl=3600
)
```
**Key Features**: All Redis operations, TTL support
**Use Cases**: Caching, session storage

## 📚 Usage Patterns

### Pattern 1: Data Pipeline
```python
# Complete data processing pipeline
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "csv_reader", {"file_path": "input.csv"})
workflow.add_node("FilterNode", "filter", {"condition": "age > 18"})
workflow.add_node("DataTransformerNode", "transform", {"transformations": [...]})
workflow.add_node("SQLDatabaseNode", "save", {"query": "INSERT INTO..."})

workflow.add_connection("csv_reader", "filter", "result", "input_data")
workflow.add_connection("filter", "transform", "result", "input_data")
workflow.add_connection("transform", "save", "result", "input_data")
```

### Pattern 2: AI Analysis Pipeline
```python
# AI-powered content analysis
workflow = WorkflowBuilder()
workflow.add_node("DirectoryReaderNode", "reader", {"directory": "/docs"})
workflow.add_node("EmbeddingGeneratorNode", "embedder", {"model": "all-minilm"})
workflow.add_node("LLMAgentNode", "analyzer", {"model": "llama3.2:3b"})
workflow.add_node("ChartGeneratorNode", "visualizer", {"chart_type": "bar"})

workflow.add_connection("reader", "embedder", "result.content", "text")
workflow.add_connection("embedder", "analyzer", "result.embeddings", "context")
workflow.add_connection("analyzer", "visualizer", "result.analysis", "data")
```

### Pattern 3: Secure API Workflow
```python
# Secure data processing with access control
workflow = WorkflowBuilder()
workflow.add_node("AuthenticationNode", "auth", {"method": "jwt"})
workflow.add_node("AccessControlNode", "acl", {"strategy": "rbac"})
workflow.add_node("HTTPRequestNode", "api_call", {"url": "https://api.example.com"})
workflow.add_node("EncryptionNode", "encrypt", {"algorithm": "AES-256"})

workflow.add_connection("auth", "acl", "result.user", "user_context")
workflow.add_connection("acl", "api_call", "result.authorized", "proceed")
workflow.add_connection("api_call", "encrypt", "result.data", "plaintext")
```

## 🔧 Node Development

### Custom Node Template
```python
from kailash.nodes import BaseNode
from kailash.schema import NodeParameter

class CustomNode(BaseNode):
    def __init__(self, name: str, custom_param: str = "default"):
        self.custom_param = custom_param
        super().__init__(name)

    def get_parameters(self):
        return {
            "custom_param": NodeParameter(
                type="string",
                description="Custom parameter description",
                default="default"
            )
        }

    def execute(self, parameters=None):
        # Custom node logic
        result = {"processed": f"Custom processing: {self.custom_param}"}
        return {"result": result}
```

## 📖 Advanced Features

### Dot Notation Mapping
Access nested node outputs using dot notation:
```python
workflow.add_connection("data_source", "processor", "result.data.items", "input_list")
```

### Auto-Mapping Parameters
Automatic parameter discovery and mapping:
```python
node = DataTransformerNode(
    name="transformer",
    auto_map_primary=True,  # Automatically map primary input
    auto_map_from=["data", "input"],  # Alternative mapping sources
    workflow_alias="transform_step"  # Workflow-level alias
)
```

### Async Node Execution
High-performance asynchronous execution:
```python
from kailash.workflow import AsyncWorkflowBuilder

builder = AsyncWorkflowBuilder()
workflow = builder.from_dict({
    "nodes": [
        {"type": "AsyncSQLDatabaseNode", "name": "db_query", ...},
        {"type": "AsyncPythonCodeNode", "name": "processor", ...}
    ],
    "connections": [...]
})

# Execute with runtime
from kailash.runtime.local import LocalRuntime
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## 🚀 Performance Tips

1. **Use Async Nodes**: For I/O-intensive operations, use async variants
2. **Connection Pooling**: Configure appropriate pool sizes for database nodes
3. **Batch Processing**: Use batch-enabled nodes for large datasets
4. **Resource Management**: Use ResourceRegistry for shared resources
5. **Monitoring**: Add MetricsCollectorNode for performance tracking

## 🔗 Related Documentation

- [Node Selection Guide](nodes/node-selection-guide.md) - Smart node selection
- [Workflow Patterns](workflows/README.md) - Common workflow patterns
- [Performance Guide](monitoring/README.md) - Performance optimization
- [Security Guide](enterprise/README.md) - Security best practices

---

*This catalog covers all 110+ Kailash SDK nodes. For the latest additions and updates, check the [Node Index](nodes/node-index.md) for quick reference.*
