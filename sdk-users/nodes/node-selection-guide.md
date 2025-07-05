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
| **High-perf SQL** | **Manual pooling** | **`QueryRouterNode` + Pool` ⭐NEW** |
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
│  ├─ Production with pooling → WorkflowConnectionPool ⭐
│  ├─ Simple SQL queries → SQLDatabaseNode
│  ├─ Async SQL queries → AsyncSQLDatabaseNode
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
│  ├─ Multi-turn → IterativeLLMAgentNode
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

## Node Categories at a Glance

### 📁 Data I/O (15+ nodes)
```python
# File operations
CSVReaderNode, CSVWriterNode
JSONReaderNode, JSONWriterNode
TextReaderNode, TextWriterNode

# Database
QueryRouterNode         # ⭐⭐⭐ Intelligent query routing
WorkflowConnectionPool  # ⭐⭐ Production connection pooling
AsyncSQLDatabaseNode    # Async queries with reuse
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
LLMAgentNode, IterativeLLMAgentNode
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

### 📢 Alerts & Notifications (5+ nodes)
```python
# Alert channels
DiscordAlertNode, SlackAlertNode
EmailSenderNode, TeamsAlertNode

# Enterprise alerting
PagerDutyAlertNode, WebhookAlertNode
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
- **Database work**: Use QueryRouterNode for production, SQLDatabaseNode for simple cases
- **API calls**: Use RESTClientNode for REST, HTTPRequestNode for simple HTTP
- **AI tasks**: Use LLMAgentNode family, avoid direct SDK calls
- **Control flow**: Use SwitchNode for conditions, MergeNode for combining data
- **Security**: Use dedicated auth/permission nodes, never roll your own

---

**For detailed node documentation**: See [comprehensive-node-catalog.md](comprehensive-node-catalog.md)
**For quick reference**: See [node-index.md](node-index.md)
