# Node Selection Guide - Kailash SDK

This guide helps you choose the right node for your task and avoid overusing PythonCodeNode.

## Quick Decision Matrix

| Task | ❌ Don't Use PythonCodeNode | ✅ Use This Node Instead |
|------|---------------------------|-------------------------|
| Read CSV | `pd.read_csv()` | `CSVReaderNode` |
| Write CSV | `df.to_csv()` | `CSVWriterNode` |
| Read JSON | `json.load()` | `JSONReaderNode` |
| Write JSON | `json.dump()` | `JSONWriterNode` |
| Read text file | `open().read()` | `TextReaderNode` |
| HTTP GET/POST | `requests.get/post()` | `HTTPRequestNode` |
| REST API calls | `requests` library | `RESTClientNode` |
| GraphQL queries | GraphQL libraries | `GraphQLClientNode` |
| SQL queries | `cursor.execute()` | `SQLDatabaseNode` |
| **MongoDB-style queries** | **Raw SQL strings** | **`QueryBuilder` ⭐⭐⭐ NEW** |
| **Query result caching** | **Manual Redis operations** | **`QueryCache` ⭐⭐⭐ NEW** |
| **Enterprise async SQL** | **Manual pooling/transactions** | **`AsyncSQLDatabaseNode` ⭐⭐⭐** |
| **Concurrency control** | **Custom version checking** | **`OptimisticLockingNode` ⭐⭐ NEW** |
| **High-perf SQL** | **Manual pooling** | **`QueryRouterNode` + Pool` ⭐NEW** |
| **Transaction metrics** | **Manual timing/counting** | **`TransactionMetricsNode` ⭐NEW** |
| **Deadlock detection** | **Custom lock graphs** | **`DeadlockDetectorNode` ⭐NEW** |
| **Race conditions** | **Manual thread tracking** | **`RaceConditionDetectorNode` ⭐NEW** |
| **Performance anomalies** | **Manual baselines** | **`PerformanceAnomalyNode` ⭐NEW** |
| **Real-time monitoring** | **Custom tracing** | **`TransactionMonitorNode` ⭐NEW** |
| **Distributed transactions** | **Manual 2PC/Saga** | **`DistributedTransactionManagerNode` ⭐NEW** |
| **Saga pattern** | **Custom compensation** | **`SagaCoordinatorNode` ⭐NEW** |
| **Two-phase commit** | **Manual 2PC protocol** | **`TwoPhaseCommitCoordinatorNode` ⭐NEW** |
| Filter data | `df[df['x'] > y]` | `FilterNode` |
| Map function | `[f(x) for x in data]` | `Map` |
| Sort data | `sorted()` or `df.sort()` | `Sort` |
| If/else logic | `if condition:` | `SwitchNode` |
| Merge data | `pd.concat()` | `MergeNode` |
| LLM calls | OpenAI/Anthropic SDK | `LLMAgentNode` |
| Embeddings | OpenAI embeddings | `EmbeddingGeneratorNode` |
| **Local LLM (Ollama)** | **Direct API calls** | **`PythonCodeNode` + Ollama API** |
| **Ollama embeddings** | **Manual API requests** | **`PythonCodeNode` + nomic-embed-text** |
| Text splitting | Manual chunking | `TextSplitterNode` |
| **User management** | **Custom user auth** | **`UserManagementNode`** |
| **Role assignment** | **Manual RBAC** | **`RoleManagementNode`** |
| **Permission checks** | **Custom access control** | **`PermissionCheckNode`** |

## Decision Tree: Choosing the Right Node

### 1. Data Processing Decision Tree

```
📊 Need to process data?
├─ 📁 File-based data?
│  ├─ CSV/TSV files → CSVReaderNode
│  ├─ JSON files → JSONReaderNode
│  ├─ XML files → XMLParserNode
│  ├─ PDF documents → PDFReaderNode
│  ├─ Excel files → ExcelReaderNode
│  ├─ Plain text → TextReaderNode
│  └─ Multiple files in directory → DirectoryReaderNode
├─ 🗄️ Database data?
│  ├─ **MongoDB-style queries** → **QueryBuilder ⭐⭐⭐ NEW**
│  ├─ **Query result caching** → **QueryCache ⭐⭐⭐ NEW**
│  ├─ Production with pooling → WorkflowConnectionPool ⭐
│  ├─ **Enterprise async SQL** → **AsyncSQLDatabaseNode ⭐⭐⭐ ENHANCED**
│  ├─ **Concurrency control** → **OptimisticLockingNode ⭐⭐ NEW**
│  ├─ Simple SQL queries → SQLDatabaseNode
│  ├─ Vector embeddings → VectorDatabaseNode
│  └─ Intelligent routing → QueryRouterNode ⭐⭐⭐
├─ 🌐 API data?
│  ├─ REST APIs → RESTClientNode
│  ├─ GraphQL → GraphQLClientNode
│  ├─ Simple HTTP → HTTPRequestNode
│  └─ Rate-limited APIs → RateLimitedAPINode
└─ 📨 Streaming data?
   ├─ Kafka streams → KafkaConsumerNode
   ├─ WebSocket → WebSocketNode
   └─ Event streams → EventStreamNode
```

### 2. AI/ML Decision Tree

```
🤖 Need AI/ML functionality?
├─ 💬 Chat/LLM?
│  ├─ Simple chat → LLMAgentNode
│  ├─ With monitoring → MonitoredLLMAgentNode
│  ├─ Multi-turn → IterativeLLMAgentNode (real MCP execution)
│  └─ Local LLM → PythonCodeNode + Ollama
├─ 🔗 Agent coordination?
│  ├─ Agent-to-agent → A2AAgentNode
│  ├─ Self-organizing → SelfOrganizingAgentNode
│  ├─ Team formation → TeamFormationNode
│  └─ Shared memory → SharedMemoryPoolNode
├─ 📊 Text analysis?
│  ├─ Embeddings → EmbeddingGeneratorNode
│  ├─ Classification → TextClassifier
│  ├─ Sentiment → SentimentAnalyzer
│  └─ Summarization → TextSummarizerNode
└─ 🔍 RAG/Search?
   ├─ Simple RAG → SimpleRAGWorkflowNode
   ├─ Advanced RAG → AdvancedRAGWorkflowNode
   ├─ Hierarchical → HierarchicalRAGNode
   └─ Hybrid retrieval → HybridRetrieverNode
```

### 3. Logic and Control Decision Tree

```
🔀 Need control flow?
├─ ⚡ Conditional routing?
│  ├─ Simple if/else → SwitchNode
│  ├─ Complex conditions → ConditionalRouterNode
│  └─ Async conditions → AsyncSwitchNode
├─ 🔄 Iteration/loops?
│  ├─ Simple loops → LoopNode
│  ├─ While loops → WhileNode
│  └─ Convergence → ConvergenceCheckerNode
├─ 🤝 Data merging?
│  ├─ Simple merge → MergeNode
│  ├─ Async merge → AsyncMergeNode
│  └─ Stream merge → StreamMergerNode
└─ 🏗️ Composition?
   ├─ Nested workflows → WorkflowNode
   ├─ Parallel execution → AsyncParallelNode
   └─ Error handling → ErrorHandlerNode
```

### 4. Monitoring & Observability Decision Tree

```
📊 Need monitoring/observability?
├─ 📈 Performance metrics?
│  ├─ Transaction metrics → TransactionMetricsNode
│  ├─ Real-time monitoring → TransactionMonitorNode
│  └─ Performance anomalies → PerformanceAnomalyNode
├─ 🔍 Concurrency issues?
│  ├─ Deadlock detection → DeadlockDetectorNode
│  └─ Race conditions → RaceConditionDetectorNode
├─ 📊 Export formats?
│  ├─ Prometheus metrics → TransactionMetricsNode (export_format="prometheus")
│  ├─ CloudWatch metrics → TransactionMetricsNode (export_format="cloudwatch")
│  └─ OpenTelemetry → TransactionMonitorNode (distributed tracing)
└─ 🚨 Alerting needs?
   ├─ Threshold alerts → TransactionMonitorNode (alert_thresholds)
   ├─ Anomaly alerts → PerformanceAnomalyNode (anomaly detection)
   └─ Deadlock alerts → DeadlockDetectorNode (automatic resolution)
```

### 5. Transaction Management Decision Tree

```
🔄 Need distributed transactions?
├─ 🤖 Automatic pattern selection?
│  ├─ Mixed participant capabilities → DistributedTransactionManagerNode
│  ├─ Requirements may change → DistributedTransactionManagerNode
│  └─ Unified interface needed → DistributedTransactionManagerNode
├─ 🔄 Long-running processes?
│  ├─ High availability priority → SagaCoordinatorNode
│  ├─ Compensation logic needed → SagaCoordinatorNode
│  └─ Eventual consistency OK → SagaCoordinatorNode
├─ ⚡ Strong consistency required?
│  ├─ ACID properties needed → TwoPhaseCommitCoordinatorNode
│  ├─ Financial transactions → TwoPhaseCommitCoordinatorNode
│  └─ Immediate consistency → TwoPhaseCommitCoordinatorNode
└─ 🔧 Individual saga steps?
   └─ Custom step logic → SagaStepNode
```

## Node Categories at a Glance

### 📁 Data I/O (15+ nodes)
```python
# File operations
CSVReaderNode, CSVWriterNode
JSONReaderNode, JSONWriterNode
TextReaderNode, TextWriterNode

# Database
AsyncSQLDatabaseNode    # ⭐⭐⭐ Enterprise async SQL with transactions
OptimisticLockingNode   # ⭐⭐ Concurrency control NEW
QueryRouterNode         # ⭐⭐⭐ Intelligent query routing
WorkflowConnectionPool  # ⭐⭐ Production connection pooling
SQLDatabaseNode         # Simple sync queries
VectorDatabaseNode      # Vector/embedding storage

# Streaming
KafkaConsumerNode, StreamPublisherNode
WebSocketNode, EventStreamNode
```

### 🔄 Transform (8+ nodes)
```python
# Data processing
FilterNode      # Filter by condition
Map             # Transform each item
Sort            # Sort by criteria
DataTransformer # Complex transforms

# Text processing
HierarchicalChunkerNode
ChunkTextExtractorNode
QueryTextWrapperNode
ContextFormatterNode
```

### 🤖 AI/ML (20+ nodes)
```python
# LLM Agents
LLMAgentNode, IterativeLLMAgentNode  # Real MCP execution (v0.6.5+)
MonitoredLLMAgentNode

# Coordination
A2AAgentNode, A2ACoordinatorNode
SharedMemoryPoolNode

# Self-organizing
AgentPoolManagerNode
SelfOrganizingAgentNode
TeamFormationNode

# ML Models
TextClassifier, SentimentAnalyzer
EmbeddingGeneratorNode
```

### 🌐 API (10+ nodes)
```python
# HTTP
HTTPRequestNode, AsyncHTTPRequestNode

# REST
RESTClientNode, AsyncRESTClientNode

# GraphQL
GraphQLClientNode, AsyncGraphQLClientNode

# Auth
BasicAuthNode, OAuth2Node, APIKeyNode

# Rate limiting
RateLimitedAPINode
```

### 🔀 Logic (8+ nodes)
```python
# Control flow
SwitchNode      # Conditional routing
MergeNode       # Merge streams
LoopNode        # Iteration

# Convergence
ConvergenceCheckerNode
MultiCriteriaConvergenceNode

# Composition
WorkflowNode    # Nested workflows
```

### 🔒 Security & Admin (15+ nodes)
```python
# Authentication
OAuth2Node, JWTValidatorNode
MultiFactorAuthNode, LDAPAuthNode

# Authorization
RoleManagementNode, PermissionCheckNode
UserManagementNode, AccessControlNode

# Security
ThreatDetectionNode, EncryptionNode
SecurityScannerNode, AuditLogNode

# Compliance
GDPRComplianceNode, ComplianceNode
DataGovernanceNode
```

### 📊 Monitoring & Observability (5+ nodes)
```python
# Transaction monitoring
TransactionMetricsNode    # Metrics collection & aggregation
TransactionMonitorNode    # Real-time tracing & alerting

# Issue detection
DeadlockDetectorNode      # Database deadlock detection
RaceConditionDetectorNode # Concurrent access analysis

# Performance analysis
PerformanceAnomalyNode    # Baseline learning & anomaly detection
```

### 🔄 Distributed Transactions (4+ nodes)
```python
# Automatic pattern selection
DistributedTransactionManagerNode  # Auto-select Saga/2PC based on requirements

# Saga pattern (High availability)
SagaCoordinatorNode               # Saga orchestration with compensation
SagaStepNode                      # Individual saga steps

# Two-Phase Commit (Strong consistency)
TwoPhaseCommitCoordinatorNode     # ACID transactions with 2PC protocol
```

### 📢 Alerts & Notifications (5+ nodes)
```python
# Alert channels
DiscordAlertNode, SlackAlertNode
EmailSenderNode, TeamsAlertNode

# Enterprise alerting
PagerDutyAlertNode, WebhookAlertNode
```

### 🗄️ Query Builder & Cache Decision Tree (NEW v0.6.6+)

```
🔍 Need to build database queries?
├─ 🐍 MongoDB-style syntax preferred?
│  ├─ Multi-tenant app → QueryBuilder with tenant()
│  ├─ Cross-database support → QueryBuilder with dialect
│  ├─ Complex WHERE conditions → QueryBuilder with $operators
│  └─ Simple queries → SQLDatabaseNode
├─ ⚡ High-performance queries?
│  ├─ Frequent repeated queries → QueryCache + QueryBuilder
│  ├─ Need cache invalidation → QueryCache with PATTERN_BASED
│  ├─ Multi-tenant caching → QueryCache with tenant isolation
│  └─ Simple caching → QueryCache with TTL strategy
└─ 🔄 Query optimization needed?
   ├─ Prevent SQL injection → QueryBuilder (automatic parameter binding)
   ├─ Database-specific optimizations → QueryBuilder with dialect
   └─ Redis caching layer → QueryCache with health monitoring
```

### 🔧 Query Builder Usage Patterns

```python
# Basic query building
from kailash.nodes.data.query_builder import create_query_builder

# Multi-tenant complex queries
builder = create_query_builder("postgresql")
builder.table("users").tenant("tenant_123")
builder.where("age", "$gt", 18).where("status", "$in", ["active", "premium"])
sql, params = builder.build_select(["name", "email"])

# Cross-database compatibility
mysql_builder = create_query_builder("mysql")
postgres_builder = create_query_builder("postgresql")
sqlite_builder = create_query_builder("sqlite")
```

### ⚡ Query Cache Usage Patterns

```python
# High-performance caching
from kailash.nodes.data.query_cache import QueryCache, CacheInvalidationStrategy

# Pattern-based invalidation for complex apps
cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED
)

# Cache with tenant isolation
cache.set(query, params, result, tenant_id="tenant_123")
cached = cache.get(query, params, tenant_id="tenant_123")

# Table-based cache invalidation
cache.invalidate_table("users", tenant_id="tenant_123")
```

## When to Use PythonCodeNode

**✅ Appropriate uses:**
- Ollama/local LLM integration
- Complex mathematical operations
- Custom business logic that doesn't fit existing nodes
- Bridging between incompatible data formats
- Temporary prototyping before creating dedicated nodes

**❌ Avoid PythonCodeNode for:**
- File I/O operations (use CSVReaderNode, etc.)
- HTTP requests (use HTTPRequestNode)
- Database queries (use SQLDatabaseNode)
- Data filtering/transformation (use FilterNode, DataTransformer)
- Authentication (use OAuth2Node, JWTValidatorNode)
- Standard ML operations (use specialized AI nodes)

## Best Practices

1. **Start with specialized nodes** - Always check if a dedicated node exists first
2. **Use decision trees** - Follow the decision trees above for systematic selection
3. **Consider performance** - Production apps should use pooled/async variants
4. **Think about monitoring** - Use monitored variants for critical workflows
5. **Plan for scale** - Choose nodes that support your expected load

## Quick Tips

- **File operations**: Always use dedicated reader/writer nodes
- **Database work**: Use QueryBuilder for MongoDB-style queries, QueryCache for high-performance caching, AsyncSQLDatabaseNode for enterprise/production, QueryRouterNode for high-performance routing, OptimisticLockingNode for concurrent updates, SQLDatabaseNode for simple cases
- **Distributed transactions**: Use DistributedTransactionManagerNode for automatic pattern selection, SagaCoordinatorNode for high availability, TwoPhaseCommitCoordinatorNode for strong consistency
- **API calls**: Use RESTClientNode for REST, HTTPRequestNode for simple HTTP
- **AI tasks**: Use LLMAgentNode family, **IterativeLLMAgentNode** for real MCP execution, avoid direct SDK calls
- **Control flow**: Use SwitchNode for conditions, MergeNode for combining data
- **Security**: Use dedicated auth/permission nodes, never roll your own

---

**For detailed node documentation**: See [comprehensive-node-catalog.md](comprehensive-node-catalog.md)
**For quick reference**: See [node-index.md](node-index.md)
