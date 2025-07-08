# Comprehensive Node Catalog - Kailash SDK

> **⚠️ Note**: This is the exhaustive 2455-line reference. For most use cases, start with:
> - **[node-index.md](node-index.md)** - 47-line quick reference
> - **[node-selection-guide.md](node-selection-guide.md)** - 436-line smart selection guide

This reference guide lists all available nodes in the Kailash SDK and their primary use cases. **Always prefer using these specialized nodes over PythonCodeNode when possible.**

*Total: 115+ specialized nodes across 13 categories*

## 🔗 **See Also**
- **[Fundamentals](../developer/01-fundamentals.md)** - Core concepts and node usage patterns
- **[Workflows](../developer/02-workflows.md)** - Connecting nodes in workflows
- **[Quick Reference](../developer/QUICK_REFERENCE.md)** - Common patterns and anti-patterns

## 🎯 Quick Node Selection Guide

**I need to...** → **Use this node:**

| **Task** | **Recommended Node** | **Category** |
|----------|---------------------|--------------|
| Read CSV/Excel files | `CSVReaderNode`, `ExcelReaderNode` | Data Processing |
| Call REST APIs | `HTTPRequestNode`, `RESTClientNode` | API Integration |
| Process text with AI | `LLMAgentNode`, `TextSummarizerNode` | AI/ML |
| Filter/search data | `FilterNode`, `SearchNode` | Transform |
| Send notifications | `DiscordAlertNode`, `EmailSenderNode` | Alert |
| Validate data | `DataValidatorNode`, `SchemaValidatorNode` | Transform |
| Handle authentication | `OAuth2Node`, `JWTValidatorNode` | Authentication |
| Route based on conditions | `SwitchNode`, `ConditionalRouterNode` | Logic & Control |
| Store/retrieve data | `SQLDatabaseNode`, `VectorDatabaseNode` | Data Processing |
| Transform file formats | `ConverterNode`, `DataTransformerNode` | Transform |
| **Manage user access** | `RoleManagementNode`, `PermissionCheckNode` | **Admin & Security** |
| **Check permissions** | `PermissionCheckNode`, `UserManagementNode` | **Admin & Security** |

## 🌳 Decision Tree: Choosing the Right Node

### **1. Data Processing Decision Tree**

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
│  ├─ Async SQL (single connection) → AsyncSQLDatabaseNode
│  ├─ Simple SQL queries → SQLDatabaseNode
│  ├─ Vector databases → VectorDatabaseNode
│  ├─ Graph databases → GraphDatabaseNode
│  └─ Document stores → DocumentStoreNode
├─ 🌐 Web/API data?
│  ├─ REST APIs → HTTPRequestNode
│  ├─ GraphQL → GraphQLClientNode
│  ├─ WebSocket streams → WebSocketClientNode
│  └─ Web scraping → WebScrapingNode
└─ 🔄 Real-time streaming?
   ├─ Data streams → StreamingDataNode
   ├─ Event processing → EventProcessorNode
   └─ Message queues → MessageQueueNode
```

### **2. AI/ML Decision Tree**

```
🤖 Need AI/ML capabilities?
├─ 💬 Text generation/chat?
│  ├─ General LLM tasks → LLMAgentNode
│  ├─ Conversational agents → ChatAgent
│  ├─ Cost-controlled LLM → MonitoredLLMAgentNode
│  ├─ Iterative refinement → IterativeLLMAgentNode
│  └─ Function calling → FunctionCallingAgent
├─ 📖 Text understanding?
│  ├─ Document Q&A → RetrievalAgent
│  ├─ Text classification → TextClassifier
│  ├─ Sentiment analysis → SentimentAnalyzer
│  ├─ Entity extraction → NamedEntityRecognizer
│  └─ Text summarization → TextSummarizer
├─ 🔢 Embeddings/vectors?
│  ├─ Generate embeddings → EmbeddingGeneratorNode
│  ├─ Similarity search → SimilaritySearchNode
│  └─ Vector operations → VectorOperationsNode
├─ 🤝 Multi-agent systems?
│  ├─ Agent coordination → A2AAgentNode
│  ├─ Agent orchestration → OrchestrationManagerNode
│  ├─ Self-organizing teams → SelfOrganizingAgentNode
│  └─ Problem decomposition → ProblemAnalyzerNode
└─ 🎯 ML predictions?
   ├─ General predictions → ModelPredictor
   ├─ Classification → ClassificationNode
   └─ Regression → RegressionNode
```

### **3. Integration Decision Tree**

```
🔗 Need to integrate with external systems?
├─ 🌐 Web APIs?
│  ├─ Simple HTTP requests → HTTPRequestNode
│  ├─ REST with auth → RESTClientNode
│  ├─ Rate-limited APIs → RateLimitedAPINode
│  ├─ GraphQL APIs → GraphQLClientNode
│  └─ OAuth2 flow → OAuth2Node
├─ 🔐 Authentication needed?
│  ├─ Multi-factor auth → MultiFactorAuthNode
│  ├─ JWT validation → JWTValidatorNode
│  ├─ SAML integration → SAMLAuthNode
│  └─ LDAP/AD → LDAPAuthNode
├─ 📧 Notifications?
│  ├─ Discord alerts → DiscordAlertNode
│  ├─ Email sending → EmailSenderNode
│  ├─ Slack messages → SlackNotifierNode
│  └─ SMS alerts → SMSAlertNode
└─ 🏢 Enterprise systems?
   ├─ SharePoint → SharePointConnectorNode
   ├─ Salesforce → SalesforceConnectorNode
   ├─ SAP → SAPConnectorNode
   └─ Custom systems → Use HTTPRequestNode or PythonCodeNode
```

### **4. Data Transformation Decision Tree**

```
⚙️ Need to transform data?
├─ 🔍 Filter/search?
│  ├─ Simple filtering → FilterNode
│  ├─ Text search → SearchNode
│  ├─ Advanced queries → QueryNode
│  └─ Fuzzy matching → FuzzyMatchNode
├─ 🔄 Format conversion?
│  ├─ Data type conversion → ConverterNode
│  ├─ Schema transformation → SchemaTransformerNode
│  ├─ JSON manipulation → JSONTransformerNode
│  └─ CSV operations → CSVTransformerNode
├─ 🧮 Calculations?
│  ├─ Statistical analysis → StatisticsNode
│  ├─ Mathematical operations → MathOperationsNode
│  ├─ Aggregations → AggregatorNode
│  └─ Complex formulas → Use PythonCodeNode
├─ ✅ Validation?
│  ├─ Data validation → DataValidatorNode
│  ├─ Schema validation → SchemaValidatorNode
│  ├─ Business rules → BusinessRuleValidatorNode
│  └─ Data quality checks → DataQualityNode
└─ 📏 Chunking/splitting?
   ├─ Text chunking → TextChunkerNode
   ├─ Intelligent chunking → IntelligentChunkerNode
   ├─ Data partitioning → DataPartitionerNode
   └─ Custom splitting → Use PythonCodeNode
```

### **5. Control Flow Decision Tree**

```
🔀 Need to control workflow execution?
├─ 🎯 Conditional routing?
│  ├─ Simple if/else → SwitchNode
│  ├─ Multi-condition routing → ConditionalRouterNode
│  ├─ Pattern matching → PatternMatcherNode
│  └─ Decision trees → DecisionTreeNode
├─ 🔄 Loops/iteration?
│  ├─ Simple loops → LoopNode
│  ├─ Async parallel → AsyncParallelNode
│  ├─ Map operations → MapNode
│  └─ Until condition → WhileNode
├─ 🔀 Data merging?
│  ├─ Simple merge → MergeNode
│  ├─ Complex joins → JoinNode
│  ├─ Data aggregation → AggregatorNode
│  └─ Stream merging → StreamMergerNode
├─ ⏸️ Execution control?
│  ├─ Delays → DelayNode
│  ├─ Retries → RetryNode
│  ├─ Circuit breakers → CircuitBreakerNode
│  └─ Timeouts → TimeoutNode
└─ 🎭 Error handling?
   ├─ Try/catch logic → ErrorHandlerNode
   ├─ Fallback execution → FallbackNode
   ├─ Error recovery → RecoveryNode
   └─ Custom error logic → Use PythonCodeNode
```

## 🎯 Common Use Case Patterns

### **ETL Workflows**
```
Data Source → Transform → Load
├─ CSVReaderNode → DataValidatorNode → SQLDatabaseNode
├─ APIRequestNode → JSONTransformerNode → VectorDatabaseNode
└─ DirectoryReaderNode → TextChunkerNode → EmbeddingGeneratorNode
```
**See:** [Workflow patterns](../developer/02-workflows.md) for complete ETL examples

### **AI-Powered Document Processing**
```
Document Input → Processing → AI Analysis → Output
├─ PDFReaderNode → TextChunkerNode → LLMAgentNode → TextSummarizerNode
├─ DirectoryReaderNode → IntelligentChunkerNode → EmbeddingGeneratorNode → VectorDatabaseNode
└─ WebScrapingNode → NamedEntityRecognizer → DataValidatorNode → SQLDatabaseNode
```

### **Real-time Alert Systems**
```
Data Monitor → Analysis → Decision → Alert
├─ StreamingDataNode → StatisticsNode → SwitchNode → DiscordAlertNode
├─ DatabaseWatcherNode → AnomalyDetectorNode → ConditionalRouterNode → EmailSenderNode
└─ APIPollingNode → DataValidatorNode → ThresholdNode → SlackNotifierNode
```

### **Authentication & Security Workflows**
```
Request → Authentication → Authorization → Access
├─ HTTPRequestNode → JWTValidatorNode → RoleBasedAccessNode → DataFilterNode
├─ OAuth2Node → MultiFactorAuthNode → PermissionCheckNode → AuditLogNode
└─ SAMLAuthNode → LDAPAuthNode → PolicyEvaluatorNode → SecurityLogNode
```
**See:** [Advanced Features](../developer/03-advanced-features.md) for enterprise security patterns

### **RAG (Retrieval-Augmented Generation)**
```
Query → Retrieval → Generation → Response
├─ TextEmbeddingNode → VectorSearchNode → LLMAgentNode → ResponseFormatterNode
├─ QueryAnalysisNode → DocumentRetrieverNode → ContextMergerNode → ChatAgent
└─ IntentClassifierNode → KnowledgeBaseNode → RetrievalAgent → AnswerValidatorNode
```

## 🚀 Performance Optimization Patterns

### **High-Throughput Data Processing**
- Use `AsyncSQLDatabaseNode` instead of `SQLDatabaseNode` for concurrent database operations
- Use `BatchProcessorNode` for bulk operations instead of individual record processing
- Use `StreamingDataNode` for large datasets instead of loading everything into memory

### **Cost-Optimized AI Workflows**
- Use `MonitoredLLMAgentNode` to track and limit AI costs
- Use `IntelligentCacheNode` to cache LLM responses and reduce API calls
- Use `TextChunkerNode` to optimize prompt sizes before sending to LLM

### **Fault-Tolerant Workflows**
- Add `RetryNode` after API calls that might fail
- Use `CircuitBreakerNode` to prevent cascading failures
- Use `FallbackNode` to provide alternative processing paths

## ⚠️ Anti-Patterns: What NOT to Do

### **❌ Don't Chain Too Many PythonCodeNodes**
```python
# Bad: Multiple PythonCodeNodes in sequence
workflow.add_node("step1", PythonCodeNode(...))
workflow.add_node("step2", PythonCodeNode(...))
workflow.add_node("step3", PythonCodeNode(...))

# Good: Use specialized nodes
workflow.add_node("reader", CSVReaderNode(...))
workflow.add_node("filter", FilterNode(...))
workflow.add_node("validator", DataValidatorNode(...))

```

### **❌ Don't Use PythonCodeNode for Standard Operations**
```python
# Bad: Reinventing the wheel
PythonCodeNode(code="data = pd.read_csv('file.csv'); result = data")

# Good: Use dedicated node
CSVReaderNode(file_path="file.csv")

```

### **❌ Don't Ignore Error Handling**
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Bad: No error handling
HTTPRequestNode(url="https://api.example.com")

# Good: Add error handling
HTTPRequestNode(url="https://api.example.com")
→ ErrorHandlerNode()
→ FallbackNode()

```

### **❌ Don't Use Synchronous Nodes for High-Volume Data**
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Bad: Synchronous for large datasets
SQLDatabaseNode(query="SELECT * FROM huge_table")

# Good: Use async for performance
AsyncSQLDatabaseNode(query="SELECT * FROM huge_table")

```

### **❌ Don't Create Monolithic Workflows**
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Bad: Everything in one giant PythonCodeNode
PythonCodeNode(code="""
    # 200 lines of mixed logic
    data = read_file()
    cleaned = clean_data()
    validated = validate()
    result = process()
""")

# Good: Break into logical nodes
CSVReaderNode() → DataCleanerNode() → DataValidatorNode() → ProcessorNode()

```

## 🎯 Quick Selection Cheatsheet

**"I want to..."** → **"Use this pattern:"**

| Goal | Pattern | Nodes |
|------|---------|-------|
| Process files from a folder | Read → Filter → Process | `DirectoryReaderNode` → `FilterNode` → `ProcessorNode` |
| Build a chatbot | Receive → Understand → Respond | `InputNode` → `LLMAgentNode` → `ResponseFormatterNode` |
| Monitor API health | Poll → Check → Alert | `APIPollingNode` → `HealthCheckNode` → `AlertNode` |
| Extract data from PDFs | Read → Parse → Structure | `PDFReaderNode` → `TextExtractorNode` → `StructuredDataNode` |
| Validate user input | Receive → Validate → Route | `InputNode` → `DataValidatorNode` → `SwitchNode` |
| Send notifications | Trigger → Format → Send | `TriggerNode` → `MessageFormatterNode` → `NotificationNode` |
| Process images | Load → Analyze → Extract | `ImageLoaderNode` → `ImageAnalyzerNode` → `DataExtractorNode` |
| Handle file uploads | Receive → Validate → Store | `FileReceiverNode` → `FileValidatorNode` → `FileStorageNode` |

## ⭐ Core SDK Improvements

**Dynamic Workflow Compatibility**: All nodes in this catalog now work seamlessly with `WorkflowBuilder.from_dict()` thanks to automatic parameter mapping. The SDK automatically handles constructor differences between nodes, ensuring robust dynamic workflow creation.

**✅ Enhanced Features**:
- Automatic `id` ↔ `name` parameter mapping
- Constructor validation during node registration
- Improved error diagnostics with signature details
- Full compatibility with middleware dynamic workflows

### **5. Admin & Security Decision Tree**

```
🔐 Need user/permission management?
├─ 👥 User account management?
│  ├─ Create/update users → UserManagementNode
│  ├─ Bulk user operations → UserManagementNode (bulk_create/bulk_update)
│  ├─ User authentication → OAuth2Node + UserManagementNode
│  └─ User lifecycle → UserManagementNode (activate/deactivate)
├─ 🏢 Role-based access control?
│  ├─ Simple role assignment → RoleManagementNode (assign_user)
│  ├─ Hierarchical roles → RoleManagementNode (create_role + parent_roles)
│  ├─ Permission inheritance → RoleManagementNode (get_effective_permissions)
│  └─ Bulk role management → RoleManagementNode (bulk_assign/bulk_unassign)
├─ ✅ Permission checking?
│  ├─ Single permission check → PermissionCheckNode (check_permission)
│  ├─ Batch permissions → PermissionCheckNode (batch_check)
│  ├─ Resource hierarchy → PermissionCheckNode (check_hierarchical)
│  ├─ Multi-user checks → PermissionCheckNode (bulk_user_check)
│  └─ Permission debugging → PermissionCheckNode (explain_permission)
├─ 🛡️ Advanced access control?
│  ├─ Attribute-based (ABAC) → PermissionCheckNode + ABACPermissionEvaluatorNode
│  ├─ Context-aware decisions → PermissionCheckNode (validate_conditions)
│  ├─ Time-based permissions → PermissionCheckNode + ABAC conditions
│  └─ Dynamic policies → ABACPermissionEvaluatorNode
└─ 📊 Audit and compliance?
   ├─ User action logging → AuditLogNode
   ├─ Security event tracking → AuditLogNode + ThreatDetectionNode
   ├─ Access monitoring → PermissionCheckNode (with audit=True)
   └─ Compliance reporting → AuditLogNode + compliance queries
```

**Performance Benchmarks:**
- ✅ **PermissionCheckNode**: 221 ops/sec, P95 <50ms, 97.8% cache hit rate
- ✅ **RoleManagementNode**: 10,000+ concurrent operations validated
- ✅ **Test Coverage**: 72 tests (unit + integration + E2E)

## Table of Contents

### **📋 Quick Reference**
- [🎯 Quick Node Selection Guide](#quick-node-selection-guide) - Instant node recommendations
- [🌳 Decision Trees](#decision-tree-choosing-the-right-node) - Step-by-step node selection
- [🎯 Common Use Case Patterns](#common-use-case-patterns) - Ready-to-use workflow patterns
- [⚠️ Anti-Patterns](#anti-patterns-what-not-to-do) - Common mistakes to avoid
- [🚀 Performance Optimization](#performance-optimization-patterns) - High-performance patterns

### **📚 Complete Node Catalog**
- [AI/ML Nodes](#aiml-nodes) - 30+ nodes for LLM agents, embeddings, self-organizing agents
- [Data Processing Nodes](#data-processing-nodes) - 23+ nodes for files, databases, streaming, advanced retrieval
- [RAG Toolkit Nodes](#rag-toolkit-nodes) - ⭐ NEW: 47+ nodes for comprehensive RAG implementations
- [API Integration Nodes](#api-integration-nodes) - 15+ nodes for HTTP, REST, GraphQL, rate limiting
- [Alert Nodes](#alert-nodes) - ⭐ NEW: Discord alerts with rich embeds and rate limiting
- [Logic & Control Nodes](#logic--control-nodes) - 10+ nodes for routing, merging, loops, async operations
- [Transform Nodes](#transform-nodes) - 15+ nodes for data transformation, advanced chunking, intelligent compression
- [Admin & Security Nodes](#admin--security-nodes) - 15+ nodes for role management, permission checking, user management, audit logging
- [Authentication Nodes](#authentication-nodes) - ⭐ NEW: 6+ nodes for enterprise authentication & authorization
- [Compliance Nodes](#compliance-nodes) - ⭐ NEW: 2+ nodes for regulatory compliance (GDPR, data retention)
- [Middleware Nodes](#middleware-nodes) - ⭐ ENTERPRISE: 5+ nodes for production applications
- [Enterprise Workflow Nodes](#enterprise-workflow-nodes) - ⭐ NEW: 4+ nodes for enterprise automation
- [Testing Nodes](#testing-nodes) - 1+ nodes for credential and workflow testing
- [Code Execution Nodes](#code-execution-nodes) - 1 node for custom Python code
- [When to Use PythonCodeNode](#when-to-use-pythoncodenode)

## AI/ML Nodes

### LLM Agents
- **LLMAgentNode**: General-purpose LLM agent with unified provider support
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use instead of PythonCodeNode calling OpenAI/Anthropic APIs
  node = LLMAgentNode(provider="openai", model="gpt-4")

  ```
- **MonitoredLLMAgentNode**: LLM agent with cost tracking and budget controls
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Track costs and enforce budget limits
  node = MonitoredLLMAgentNode(model="gpt-4", budget_limit=10.0, alert_threshold=0.8)

  ```
- **IterativeLLMAgentNode**: LLM agent with iterative refinement capabilities
- **ChatAgent**: Conversational agent with context management
- **RetrievalAgent**: RAG-enabled agent for document retrieval
- **FunctionCallingAgent**: Agent with function calling capabilities
- **PlanningAgent**: Agent specialized for planning and orchestration

### Agent Coordination & Communication
- **A2AAgentNode**: Agent-to-agent communication node
- **A2ACoordinatorNode**: Coordinates multiple A2A agents
- **SharedMemoryPoolNode**: Shared memory for agent coordination

### Self-Organizing Agents
- **AgentPoolManagerNode**: Manages pools of agents dynamically
- **ProblemAnalyzerNode**: Analyzes problems for optimal agent assignment
- **SelfOrganizingAgentNode**: Self-organizing agent with adaptive behavior
- **SolutionEvaluatorNode**: Evaluates solutions from multiple agents
- **TeamFormationNode**: Forms teams of agents for complex tasks

### Intelligent Orchestration
- **OrchestrationManagerNode**: Manages complex multi-agent orchestrations
- **QueryAnalysisNode**: Analyzes queries for intelligent routing
- **ConvergenceDetectorNode**: Detects convergence in iterative processes
- **IntelligentCacheNode**: Smart caching for LLM responses
- **MCPAgentNode**: MCP-enabled agent with enhanced capabilities

### Embeddings & ML Models
- **EmbeddingGeneratorNode**: Generate text embeddings with caching
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use instead of PythonCodeNode with OpenAI embeddings
  node = EmbeddingGeneratorNode(provider="openai", model="text-embedding-ada-002")

  ```
- **TextClassifier**: Classify text into categories
- **SentimentAnalyzer**: Analyze sentiment in text
- **NamedEntityRecognizer**: Extract named entities from text
- **TextSummarizer**: Summarize long text documents
- **ModelPredictor**: General ML model predictions

## Data Processing Nodes

### File Readers
- **CSVReaderNode**: Read CSV files with configurable options
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use instead of PythonCodeNode with pd.read_csv()
  node = CSVReaderNode(file_path="data.csv", headers=True, delimiter=",")

  ```
- **JSONReaderNode**: Read JSON files into Python objects
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use instead of PythonCodeNode with json.load()
  node = JSONReaderNode(file_path="data.json")

  ```
- **TextReaderNode**: Read plain text files
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use instead of PythonCodeNode with open().read()
  node = TextReaderNode(file_path="document.txt")

  ```

### File Writers
- **CSVWriterNode**: Write data to CSV files
- **JSONWriterNode**: Write data to JSON files
- **TextWriterNode**: Write text to files

### Database Operations
- **SQLDatabaseNode**: Execute SQL queries and commands
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use instead of PythonCodeNode with database connections
  node = SQLDatabaseNode(
      connection_string="postgresql://user:pass@host/db",
      query="SELECT * FROM customers WHERE age > 30"
  )

  ```
- **AsyncSQLDatabaseNode**: ⭐ NEW: High-performance async database operations
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use for high-concurrency database operations (Session 065)
  node = AsyncSQLDatabaseNode(
      database_type="postgresql",
      host="localhost", database="app_db",
      query="SELECT * FROM portfolios",
      pool_size=20, max_pool_size=50
  )

  ```
- **WorkflowConnectionPool**: ⭐⭐⭐ PRODUCTION RECOMMENDED: Enterprise-grade connection pooling
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import WorkflowConnectionPool

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Production-grade connection pool with fault tolerance
  pool = WorkflowConnectionPool(
      name="production_pool",
      database_type="postgresql",
      host="localhost", port=5432,
      database="production_db",
      user="app_user", password="secure_pass",
      min_connections=10,      # Minimum pool size
      max_connections=50,      # Maximum pool size
      health_threshold=70,     # Health score for recycling
      pre_warm=True           # Pre-warm connections
  )

  # Initialize pool
  await pool.process({"operation": "initialize"})

  # Use in high-concurrency scenarios
  async def handle_request():
      conn = await pool.process({"operation": "acquire"})
      try:
          result = await pool.process({
              "operation": "execute",
              "connection_id": conn["connection_id"],
              "query": "SELECT * FROM orders WHERE status = $1",
              "params": ["pending"],
              "fetch_mode": "all"
          })
          return result["data"]
      finally:
          await pool.process({
              "operation": "release",
              "connection_id": conn["connection_id"]
          })

  # Monitor pool health
  stats = await pool.process({"operation": "stats"})
  print(f"Pool efficiency: {stats['queries']['executed'] / stats['connections']['created']:.1f}")

  ```
- **AsyncPostgreSQLVectorNode**: ⭐ NEW: pgvector similarity search
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use for AI/ML vector operations (Session 065)
  node = AsyncPostgreSQLVectorNode(
      connection_string="postgresql://user:pass@host/vectordb",
      table_name="embeddings",
      operation="search",
      vector=[0.1, 0.2, ...],
      distance_metric="cosine"
  )

  ```

### SharePoint Integration
- **SharePointGraphReader**: Read files from SharePoint via Graph API
- **SharePointGraphWriter**: Write files to SharePoint via Graph API
- **SharePointGraphReaderEnhanced**: ⭐ NEW: Multiple authentication methods (Session 067)
  ```python
  # Certificate authentication (most secure)
  node = SharePointGraphReaderEnhanced(
      auth_method="certificate",
      certificate_path="/path/to/cert.pem",
      tenant_id="your-tenant-id",
      client_id="your-app-id"
  )

  # Managed Identity (Azure-hosted apps)
  node = SharePointGraphReaderEnhanced(
      auth_method="managed_identity",
      site_url="https://company.sharepoint.com/sites/project"
  )

  ```

### Vector Database & Embeddings
- **EmbeddingNode**: Generate embeddings from text
- **VectorDatabaseNode**: Store and query vector embeddings
- **TextSplitterNode**: Split text into chunks for embedding

### Advanced Retrieval & RAG ⭐ **NEW**
- **HybridRetrieverNode**: State-of-the-art hybrid retrieval combining dense and sparse methods
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use for production RAG systems - 20-30% better performance
  node = HybridRetrieverNode(
      fusion_strategy="rrf",  # Reciprocal Rank Fusion (gold standard)
      dense_weight=0.6,       # Semantic search weight
      sparse_weight=0.4,      # Keyword search weight
      top_k=5
  )

  ```
- **RelevanceScorerNode**: Advanced relevance scoring with embeddings
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use instead of PythonCodeNode for relevance ranking
  node = RelevanceScorerNode(
      similarity_method="cosine",
      top_k=3
  )

  ```

### Streaming Data
- **KafkaConsumerNode**: Consume messages from Kafka topics
- **StreamPublisherNode**: Publish messages to streams
- **WebSocketNode**: Handle WebSocket connections
- **EventStreamNode**: Process event streams

### Data Sources & Discovery
- **DocumentSourceNode**: Load documents as workflow input
- **QuerySourceNode**: Generate queries as workflow input
- **DirectoryReaderNode**: Read directory contents and discover files
- **FileDiscoveryNode**: Discover files matching patterns
- **EventGeneratorNode**: Generate events for workflows

### Data Retrieval
- **RelevanceScorerNode**: Score document relevance for RAG pipelines

## RAG Toolkit Nodes

### Core RAG Strategy Nodes
- **SemanticRAGNode**: Semantic chunking with dense embeddings for conceptual queries
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Best for narrative content, general Q&A, conceptual queries
  node = SemanticRAGNode(config=RAGConfig(chunk_size=1000, retrieval_k=5))

  ```
- **StatisticalRAGNode**: Statistical chunking with sparse retrieval for technical content
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Best for technical docs, code, structured content
  node = StatisticalRAGNode(config=RAGConfig(chunk_size=800, retrieval_k=3))

  ```
- **HybridRAGNode**: Combines semantic + statistical for optimal coverage (20-30% better performance)
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Best for mixed content, general purpose, maximum coverage
  node = HybridRAGNode(config=RAGConfig(), fusion_method="rrf")

  ```
- **HierarchicalRAGNode**: Multi-level processing preserving document structure
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Best for long documents, structured content, complex queries
  node = HierarchicalRAGNode(config=RAGConfig(chunk_size=1200))

  ```

### RAG Workflow Nodes
- **SimpleRAGWorkflowNode**: Basic chunk → embed → store → retrieve pipeline
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Perfect for getting started or simple document Q&A
  workflow = SimpleRAGWorkflowNode(config=RAGConfig())

  ```
- **AdvancedRAGWorkflowNode**: Multi-stage with quality checks and strategy selection
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Production-ready with monitoring and validation
  workflow = AdvancedRAGWorkflowNode(config=RAGConfig())

  ```
- **AdaptiveRAGWorkflowNode**: AI-driven strategy selection using LLM analysis
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Fully automated with intelligent optimization
  workflow = AdaptiveRAGWorkflowNode(llm_model="gpt-4", config=RAGConfig())

  ```
- **RAGPipelineWorkflowNode**: Configurable pipeline for custom requirements
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Flexible runtime configuration
  workflow = RAGPipelineWorkflowNode(default_strategy="hybrid", config=RAGConfig())

  ```

### RAG Router & Analysis Nodes
- **RAGStrategyRouterNode**: LLM-powered intelligent strategy selection
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Automatically select optimal RAG strategy based on content analysis
  router = RAGStrategyRouterNode(llm_model="gpt-4", provider="openai")

  ```
- **RAGQualityAnalyzerNode**: Quality assessment and optimization recommendations
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Analyze RAG results and suggest improvements
  analyzer = RAGQualityAnalyzerNode()

  ```
- **RAGPerformanceMonitorNode**: Performance tracking and insights over time
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Monitor system performance and generate optimization insights
  monitor = RAGPerformanceMonitorNode()

  ```

### RAG Registry & Discovery
- **RAGWorkflowRegistry**: Central registry for discovering and creating RAG components
  ```python
  # Unified interface for RAG component discovery and recommendations
  from kailash.nodes.rag import RAGWorkflowRegistry
  registry = RAGWorkflowRegistry()

  # Get strategy recommendation
  recommendation = registry.recommend_strategy(
      document_count=100, is_technical=True, performance_priority="accuracy"
  )

  # Create recommended components
  strategy = registry.create_strategy(recommendation["recommended_strategy"])
  workflow = registry.create_workflow("adaptive")

  ```

## API Integration Nodes

### HTTP Clients
- **HTTPRequestNode**: Make HTTP requests with full configuration
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use instead of PythonCodeNode with requests library
  node = HTTPRequestNode(
      url="https://api.example.com/data",
      method="GET",
      headers={"Authorization": "Bearer token"}
  )

  ```
- **AsyncHTTPRequestNode**: Asynchronous HTTP requests

### REST API Clients
- **RESTClientNode**: RESTful API client with built-in patterns
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use instead of PythonCodeNode for REST APIs
  node = RESTClientNode(
      base_url="https://api.example.com",
      endpoint="/users",
      method="POST"
  )

  ```
- **AsyncRESTClientNode**: Asynchronous REST client

### GraphQL Clients
- **GraphQLClientNode**: GraphQL API client
- **AsyncGraphQLClientNode**: Asynchronous GraphQL client

### Authentication
- **BasicAuthNode**: Basic authentication handling
- **OAuth2Node**: OAuth 2.0 authentication flow
- **APIKeyNode**: API key authentication management

### Rate Limiting & Monitoring
- **RateLimitedAPINode**: API client with built-in rate limiting
- **AsyncRateLimitedAPINode**: Async rate-limited API client
- **HealthCheckNode**: API health monitoring
- **SecurityScannerNode**: Security scanning for APIs

## Alert Nodes

### Notifications & Alerts ✅ Production Ready
- **DiscordAlertNode**: Send rich alerts to Discord channels via webhooks
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use instead of PythonCodeNode with webhook requests
  node = DiscordAlertNode(
      webhook_url="${DISCORD_WEBHOOK}",  # Environment variable support
      title="Database Connection Failed",
      message="Primary database is unreachable",
      alert_type="error",  # success, warning, error, critical, info
      embed=True,  # Rich embed with automatic color coding
      mentions=["@here"],  # User/role mentions
      context={"Server": "db-01", "Attempts": 3}  # Additional data
  )

  ```

**Key Features:**
- 🎨 **Rich embeds** with automatic color coding by severity
- 🔔 **Mentions** support (@everyone, @here, user/role IDs)
- 🔄 **Rate limiting** (30 requests/minute) with retry logic
- 🧵 **Thread support** for organized discussions
- 🔒 **Environment variable** substitution for secure webhook URLs
- 📊 **Context data** formatting as embed fields
- ⚙️ **Plain text mode** option

### Coming Soon
- **SlackAlertNode**: Slack webhook/API integration
- **EmailAlertNode**: SMTP email notifications
- **WebhookAlertNode**: Generic webhook support
- **PagerDutyAlertNode**: Incident management
- **TeamsAlertNode**: Microsoft Teams notifications

## Logic & Control Nodes

### Control Flow
- **SwitchNode**: Conditional routing (if/else logic)
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use instead of PythonCodeNode with if/else
  node = SwitchNode(
      condition="status == 'success'",
      true_output="success_path",
      false_output="error_path"
  )

  ```
- **AsyncSwitchNode**: Asynchronous conditional routing

### Data Merging
- **MergeNode**: Merge multiple data streams
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use instead of PythonCodeNode combining multiple inputs
  node = MergeNode(merge_strategy="concat")

  ```
- **AsyncMergeNode**: Asynchronous data merging

### Loops & Convergence
- **LoopNode**: Execute nodes in a loop with conditions
- **ConvergenceCheckerNode**: Check for convergence conditions
- **MultiCriteriaConvergenceNode**: Multi-criteria convergence detection

### Workflow Composition
- **WorkflowNode**: Embed workflows within workflows

## Transform Nodes

### Data Processing
- **FilterNode**: Filter data based on conditions
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use instead of PythonCodeNode with df[df['column'] > value]
  node = FilterNode(condition="age > 30")

  ```
- **Filter**: Basic filter operation
- **Map**: Apply transformations to each item
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use instead of PythonCodeNode with list comprehensions or df.apply()
  node = Map(function=lambda x: x.upper())

  ```
- **Sort**: Sort data by specified criteria
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use instead of PythonCodeNode with sorted() or df.sort_values()
  node = Sort(key="timestamp", reverse=True)

  ```
- **DataTransformer**: General-purpose data transformation

### Text Processing & Advanced Chunking
- **SemanticChunkerNode**: ⭐ **NEW** Intelligent chunking based on semantic similarity
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use for narrative text and general documents
  node = SemanticChunkerNode(
      chunk_size=1000,           # Target chunk size
      similarity_threshold=0.75,  # Topic boundary detection
      chunk_overlap=100,         # Context preservation
      window_size=3              # Similarity calculation window
  )

  ```
- **StatisticalChunkerNode**: ⭐ **NEW** Variance-based chunking for structured content
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use for technical documents and structured content
  node = StatisticalChunkerNode(
      chunk_size=1000,
      variance_threshold=0.5,     # Boundary sensitivity
      min_sentences_per_chunk=3,  # Coherence control
      max_sentences_per_chunk=15  # Size control
  )

  ```
- **ContextualCompressorNode**: ⭐ **NEW** Intelligent content compression for LLM context optimization
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use for RAG systems and token budget management
  node = ContextualCompressorNode(
      compression_target=2000,     # Target token count
      relevance_threshold=0.75,    # Minimum relevance score
      compression_strategy="extractive_summarization",  # or "abstractive_synthesis", "hierarchical_organization"
      compression_ratio=0.6        # 40% reduction target
  )
  # Achieves 50-70% token reduction while preserving relevance

  ```
- **HierarchicalChunkerNode**: Split documents into hierarchical chunks
- **ChunkTextExtractorNode**: Extract text from document chunks
- **QueryTextWrapperNode**: Wrap queries with additional context
- **ContextFormatterNode**: Format context for LLM consumption

## Authentication Nodes

### Enterprise Authentication & Authorization
- **MultiFactorAuthNode**: ⭐ NEW: Complete MFA implementation with TOTP, SMS, email
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Enterprise-grade multi-factor authentication
  node = MultiFactorAuthNode(
      operation="verify_mfa",
      mfa_methods=["totp", "sms", "email"],
      backup_codes_enabled=True,
      session_binding=True
  )

  ```

- **SessionManagementNode**: ⭐ NEW: Advanced session management with security controls
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Secure session handling with anomaly detection
  node = SessionManagementNode(
      operation="create_session",
      max_concurrent_sessions=3,
      ip_binding=True,
      device_fingerprinting=True,
      anomaly_detection=True
  )

  ```

- **SSOAuthenticationNode**: ⭐ NEW: Single sign-on with multiple identity providers
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Enterprise SSO with SAML, OIDC, Azure AD support
  node = SSOAuthenticationNode(
      auth_provider="azure_ad",  # or "okta", "auth0", "saml", "oidc"
      auto_provision_users=True,
      role_mapping_enabled=True,
      group_sync=True
  )

  ```

- **DirectoryIntegrationNode**: ⭐ NEW: Active Directory and LDAP integration
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Enterprise directory integration with group sync
  node = DirectoryIntegrationNode(
      directory_type="active_directory",  # or "ldap", "azure_ad"
      sync_groups=True,
      sync_attributes=["department", "title", "manager"],
      auto_disable_users=True
  )

  ```

- **EnterpriseAuthProviderNode**: ⭐ NEW: Unified authentication provider interface
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Centralized authentication with multiple providers
  node = EnterpriseAuthProviderNode(
      primary_provider="azure_ad",
      fallback_providers=["local", "ldap"],
      provider_failover=True,
      audit_all_attempts=True
  )

  ```

- **RiskAssessmentNode**: ⭐ NEW: Real-time authentication risk assessment
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # AI-powered authentication risk scoring
  node = RiskAssessmentNode(
      operation="assess_login_risk",
      risk_factors=["location", "device", "behavior", "time"],
      ml_model_enabled=True,
      adaptive_auth=True
  )

  ```

## Compliance Nodes

### Regulatory Compliance & Data Protection
- **GDPRComplianceNode**: ⭐ NEW: Complete GDPR compliance automation
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Comprehensive GDPR compliance workflows
  node = GDPRComplianceNode(
      operation="process_data_request",  # or "audit_consent", "anonymize_data", "export_data"
      request_type="data_export",  # or "deletion", "rectification", "portability"
      automated_verification=True,
      retention_policy_check=True,
      audit_trail=True
  )

  ```

- **DataRetentionPolicyNode**: ⭐ NEW: Automated data retention and lifecycle management
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Enterprise data retention with automated cleanup
  node = DataRetentionPolicyNode(
      operation="apply_retention_policy",
      retention_rules=[
          {"data_type": "customer_data", "retention_days": 2555},  # 7 years
          {"data_type": "log_data", "retention_days": 90},
          {"data_type": "temp_data", "retention_days": 30}
      ],
      automated_cleanup=True,
      compliance_reporting=True
  )

  ```

## Admin & Security Nodes

*Production-certified with comprehensive test suite: 23 unit tests, 45 integration tests, 6 performance E2E tests*

### Role Management
- **RoleManagementNode**: Enterprise role management with hierarchical RBAC support

  **Key Features:**
  - Hierarchical role management with inheritance
  - Dynamic permission assignment and revocation
  - Role templates and bulk operations
  - Permission dependency validation
  - Multi-tenant role isolation
  - Integration with ABAC attributes
  - **Performance**: 10,000+ concurrent operations, 221 ops/sec throughput

  **Operations (15 total):**
  - `create_role` - Create new role with hierarchy validation
  - `update_role` - Update role information and permissions
  - `delete_role` - Delete role with dependency checking
  - `list_roles` - List roles with filtering and pagination
  - `get_role` - Get detailed role information
  - `assign_user` - Assign role to user
  - `unassign_user` - Remove role from user
  - `add_permission` - Add permission to role
  - `remove_permission` - Remove permission from role
  - `bulk_assign` - Assign role to multiple users
  - `bulk_unassign` - Remove role from multiple users
  - `get_user_roles` - Get all roles for a user
  - `get_role_users` - Get all users with a role
  - `validate_hierarchy` - Validate role hierarchy integrity
  - `get_effective_permissions` - Get all permissions including inherited

  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.admin import RoleManagementNode

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Create hierarchical role structure
  node = RoleManagementNode(
      operation="create_role",
      role_data={
          "name": "Senior Analyst",
          "description": "Senior financial analyst with elevated permissions",
          "parent_roles": ["analyst"],  # Inherits from analyst role
          "permissions": ["advanced_reports", "data_export"],
          "attributes": {
              "seniority": "senior",
              "clearance_required": "confidential"
          }
      }
  )

  # Bulk user assignment with validation
  node = RoleManagementNode(
      operation="bulk_assign",
      role_id="senior_analyst",
      user_ids=["user1", "user2", "user3"],
      validate_hierarchy=True
  )

  # Get effective permissions (including inherited)
  node = RoleManagementNode(
      operation="get_effective_permissions",
      role_id="senior_analyst",
      include_inherited=True
  )

  ```

  **When to use:** For enterprise role-based access control, permission management, user-role assignment, and maintaining role hierarchies. Essential for applications requiring sophisticated authorization models.

### Permission Checking
- **PermissionCheckNode**: High-performance permission checking with RBAC/ABAC integration

  **Key Features:**
  - Real-time RBAC and ABAC evaluation
  - Multi-level permission caching for performance (97.8% cache hit rate)
  - Batch permission checking for efficiency
  - Permission explanation and debugging
  - Conditional permission evaluation
  - Integration with user and role management
  - Comprehensive audit logging
  - Multi-tenant permission isolation
  - **Performance**: P95 latency <50ms, 10,000 concurrent checks validated

  **Operations (10 total):**
  - `check_permission` - Single permission check with caching
  - `batch_check` - Check multiple permissions for a user
  - `check_node_access` - Check access to specific node types
  - `check_workflow_access` - Check workflow operation permissions
  - `get_user_permissions` - Get all permissions for a user
  - `explain_permission` - Detailed permission evaluation explanation
  - `validate_conditions` - Validate ABAC conditions and rules
  - `check_hierarchical` - Check permissions with resource hierarchy
  - `bulk_user_check` - Check permission for multiple users
  - `clear_cache` - Clear permission cache

  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.admin import PermissionCheckNode

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Single permission check with explanation
  node = PermissionCheckNode(
      operation="check_permission",
      user_id="user123",
      resource_id="sensitive_data",
      permission="read",
      cache_level="user",
      cache_ttl=300,
      explain=True  # Get detailed explanation
  )

  # Batch permission checking for efficiency
  node = PermissionCheckNode(
      operation="batch_check",
      user_id="user123",
      resource_ids=["data1", "data2", "data3"],
      permissions=["read", "write", "delete"],
      cache_level="full"
  )

  # Hierarchical resource permission check
  node = PermissionCheckNode(
      operation="check_hierarchical",
      user_id="user123",
      resource_id="org/team/project/workflow",
      permission="execute",
      check_inheritance=True  # Check parent resources
  )

  # Bulk user permission check (access matrix)
  node = PermissionCheckNode(
      operation="bulk_user_check",
      user_ids=["user1", "user2", "user3"],
      resource_id="workflow_execute",
      permission="execute"
  )

  ```

  **When to use:** For real-time authorization checks, permission validation, access control decisions, and debugging permission issues. Critical for secure enterprise applications.

### User Management
- **UserManagementNode**: Complete user lifecycle management with enterprise features

  **Key Features:**
  - Full user CRUD operations with validation
  - Bulk operations with rollback support
  - Password management with security policies
  - User attribute management for ABAC
  - Multi-tenant user isolation
  - Comprehensive audit logging
  - Integration with external identity providers
  - Advanced search, filtering, and pagination
  - **Database**: Unified SQL schema with 12+ tables, triggers, and indexes

  **Operations (14 total):**
  - `create` - Create new user with validation
  - `read` - Read user information
  - `update` - Update user details
  - `delete` - Soft delete user
  - `restore` - Restore deleted user
  - `list` - List users with pagination
  - `search` - Search users with filters
  - `bulk_create` - Create multiple users
  - `bulk_update` - Update multiple users
  - `bulk_delete` - Delete multiple users
  - `change_password` - Change user password
  - `reset_password` - Reset password with token
  - `deactivate` - Deactivate user account
  - `activate` - Activate user account

  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.admin import UserManagementNode

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Create user with ABAC attributes
  node = UserManagementNode(
      operation="create",
      user_data={
          "email": "user@company.com",
          "username": "johndoe",
          "first_name": "John",
          "last_name": "Doe",
          "roles": ["analyst", "viewer"],
          "attributes": {
              "department": "finance",
              "clearance_level": "confidential",
              "location": "US-East"
          }
      },
      abac_enabled=True
  )

  # Bulk user operations with validation
  node = UserManagementNode(
      operation="bulk_update",
      user_ids=["user1", "user2", "user3"],
      update_data={
          "status": "active",
          "attributes": {"migrated": True}
      },
      validate_before_update=True
  )

  # Advanced user search
  node = UserManagementNode(
      operation="search",
      filters={
          "status": "active",
          "roles": ["analyst"],
          "attributes.department": "finance"
      },
      limit=50,
      offset=0
  )

  ```

  **When to use:** For user account management, authentication workflows, user provisioning, and maintaining user profiles in enterprise applications.

### Audit & Compliance
- **AuditLogNode**: Enterprise-grade audit logging with structured format

  **Key Features:**
  - Structured audit logging with JSON/text output
  - Multiple log levels (INFO, WARNING, ERROR, CRITICAL)
  - Automatic timestamp inclusion
  - User association tracking
  - Event type categorization
  - Integration with enterprise logging systems
  - Compliance-ready format

  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.security import AuditLogNode

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Enterprise audit logging
  node = AuditLogNode(
      name="workflow_audit",
      log_level="INFO",
      include_timestamp=True,
      output_format="json"  # or "text"
  )

  # Log user action
  result = await node.execute(
      event_type="user_action",
      user_id="user123",
      message="User accessed sensitive data",
      event_data={
          "resource": "financial_reports",
          "action": "download",
          "ip_address": "192.168.1.100",
          "session_id": "sess_xyz"
      }
  )

  # Log security event
  result = await node.execute(
      event_type="security",
      user_id="admin456",
      message="Permission escalation attempt detected",
      event_data={
          "attempted_permission": "admin:delete_all",
          "current_role": "viewer",
          "blocked": True
      }
  )

  ```

  **When to use:** For compliance logging, security event tracking, user activity monitoring, and maintaining audit trails for regulatory requirements. Essential for SOC2, HIPAA, and other compliance frameworks.
- **SecurityEventNode**: ⭐ NEW: Security event monitoring with alerting (Session 067)
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use for security monitoring with automatic alerting
  node = SecurityEventNode(
      name="security_monitor",
      severity_threshold="MEDIUM",
      enable_alerting=True
  )
  # Usage: await node.process({"event_type": "unauthorized_access", "severity": "HIGH"})

  ```
- **CredentialManagerNode**: ⭐ NEW: Enterprise credential management (Session 067)
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Multi-source credential management with validation
  node = CredentialManagerNode(
      credential_name="api_service",
      credential_type="oauth2",
      credential_sources=["vault", "aws_secrets", "env"],
      validate_on_fetch=True,
      cache_duration_seconds=3600
  )

  ```
- **RotatingCredentialNode**: ⭐ NEW: Automatic credential rotation (Session 067)
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Zero-downtime credential rotation with notifications
  node = RotatingCredentialNode(
      operation="start_rotation",
      credential_name="api_token",
      check_interval=3600,  # Check every hour
      expiration_threshold=86400,  # Rotate 24h before expiry
      refresh_sources=["vault", "aws_secrets"],
      notification_webhooks=["https://alerts.company.com/webhook"],
      zero_downtime=True
  )

  ```

### Advanced Security Monitoring
- **ThreatDetectionNode**: ⭐ NEW: AI-powered threat detection and response
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Real-time threat detection with ML models
  node = ThreatDetectionNode(
      detection_models=["anomaly", "signature", "behavioral"],
      auto_response=True,
      threat_intelligence_feeds=["crowdstrike", "virustotal"],
      risk_scoring=True
  )

  ```

- **ABACPermissionEvaluatorNode**: ⭐ NEW: Advanced attribute-based access control
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Complex permission evaluation with 16+ operators
  node = ABACPermissionEvaluatorNode(
      policy_engine="cedar",  # or "opa", "native"
      attributes=["user.department", "resource.sensitivity", "time.hour"],
      operators=["equals", "contains", "greater_than", "in_set"],
      dynamic_evaluation=True
  )

  ```

- **BehaviorAnalysisNode**: ⭐ NEW: User behavior analytics for security
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # ML-powered behavior analysis for anomaly detection
  node = BehaviorAnalysisNode(
      analysis_type="user_behavior",  # or "network", "application"
      baseline_learning_days=30,
      anomaly_threshold=0.75,
      real_time_analysis=True
  )

  ```

### Audit & Compliance
- **AuditLogNode**: Comprehensive audit logging with compliance tags
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use instead of custom logging
  node = AuditLogNode(compliance_tags=["SOC2", "HIPAA"])

  ```

## Monitoring & Observability Nodes

### TransactionMetricsNode

**Purpose**: Collect and aggregate transaction performance metrics with enterprise export formats.

**Use cases**:
- Transaction timing and latency tracking
- Success rate monitoring
- Throughput measurement
- Custom metric collection
- Export to Prometheus, CloudWatch, DataDog, OpenTelemetry

**Example**:
```python
from kailash.nodes.monitoring import TransactionMetricsNode

# Initialize metrics collector
metrics = TransactionMetricsNode({
    "aggregation_window": 60,    # 1-minute windows
    "retention_period": 3600,    # Keep 1 hour of data
    "export_format": "prometheus",
    "custom_percentiles": [50, 75, 90, 95, 99]
})

# Track transaction
result = metrics.execute(
    operation="start_transaction",
    transaction_id="order_123",
    operation_type="order_processing"
)

# Complete with metrics
result = metrics.execute(
    operation="end_transaction",
    transaction_id="order_123",
    status="success",
    custom_metrics={"items": 5, "total": 150.00}
)

# Get aggregated metrics
result = metrics.execute(
    operation="get_metrics",
    metric_types=["latency", "throughput", "success_rate"],
    export_format="prometheus"
)
```

### TransactionMonitorNode

**Purpose**: Real-time transaction monitoring with distributed tracing and alerting.

**Use cases**:
- Live transaction tracing
- Distributed tracing (OpenTelemetry compatible)
- Real-time alerting on thresholds
- Transaction correlation
- Performance bottleneck identification

**Example**:
```python
from kailash.nodes.monitoring import TransactionMonitorNode

# Initialize monitor with alerts
monitor = TransactionMonitorNode()

result = monitor.execute(
    operation="start_monitoring",
    monitoring_interval=1.0,
    alert_thresholds={
        "latency_ms": 1000,
        "error_rate": 0.05,
        "concurrent_transactions": 100
    }
)

# Create trace
result = monitor.execute(
    operation="create_trace",
    trace_id="trace_001",
    operation_name="api_request",
    metadata={"endpoint": "/api/orders", "method": "POST"}
)

# Add spans
result = monitor.execute(
    operation="add_span",
    trace_id="trace_001",
    span_id="db_query",
    operation_name="database_query",
    start_time=time.time()
)

# Get alerts
result = monitor.execute(operation="get_alerts")
```

### DeadlockDetectorNode

**Purpose**: Detect and resolve database deadlocks using wait-for graph analysis.

**Use cases**:
- Database deadlock detection
- Lock dependency graph visualization
- Automatic victim selection
- Deadlock prevention strategies
- Lock timeout management

**Example**:
```python
from kailash.nodes.monitoring import DeadlockDetectorNode

# Initialize detector
detector = DeadlockDetectorNode({
    "detection_interval": 5.0,
    "timeout_threshold": 30.0,
    "victim_selection": "youngest"  # or "oldest", "lowest_cost"
})

# Start monitoring
result = detector.execute(operation="start_monitoring")

# Register lock acquisition
result = detector.execute(
    operation="register_lock",
    transaction_id="txn_001",
    resource_id="table_orders",
    lock_type="EXCLUSIVE"
)

# Register wait condition
result = detector.execute(
    operation="register_wait",
    transaction_id="txn_001",
    waiting_for_transaction_id="txn_002",
    resource_id="table_users"
)

# Detect deadlocks
result = detector.execute(operation="detect_deadlocks")

if result["deadlocks_detected"] > 0:
    # Automatic resolution
    detector.execute(
        operation="resolve_deadlock",
        deadlock_id=result["deadlocks"][0]["deadlock_id"],
        resolution_strategy="abort_victim"
    )
```

### RaceConditionDetectorNode

**Purpose**: Detect race conditions in concurrent resource access patterns.

**Use cases**:
- Concurrent access analysis
- Race condition identification
- Thread safety validation
- Resource contention detection
- Access pattern visualization

**Example**:
```python
from kailash.nodes.monitoring import RaceConditionDetectorNode

# Initialize detector
detector = RaceConditionDetectorNode({
    "detection_window": 10.0,
    "confidence_threshold": 0.8
})

# Start monitoring
result = detector.execute(operation="start_monitoring")

# Register resource access
result = detector.execute(
    operation="register_access",
    access_id="access_001",
    resource_id="shared_counter",
    access_type="read_write",  # or "read", "write"
    thread_id="thread_1"
)

# End access
result = detector.execute(
    operation="end_access",
    access_id="access_001"
)

# Detect race conditions
result = detector.execute(operation="detect_races")

for race in result.get("races_detected", []):
    print(f"Race condition: {race['race_type']}")
    print(f"Confidence: {race['confidence']}")
    print(f"Resources: {race['resources']}")
```

### PerformanceAnomalyNode

**Purpose**: Detect performance anomalies using statistical baselines and ML techniques.

**Use cases**:
- Performance baseline learning
- Anomaly detection (statistical & ML)
- Trend analysis
- Seasonal pattern recognition
- Automatic alerting

**Example**:
```python
from kailash.nodes.monitoring import PerformanceAnomalyNode

# Initialize detector
detector = PerformanceAnomalyNode()

# Initialize baseline
result = detector.execute(
    operation="initialize_baseline",
    metric_name="api_response_time",
    sensitivity=0.8,
    min_samples=30,
    detection_window=300  # 5 minutes
)

# Feed metric data
for value in response_times:
    result = detector.execute(
        operation="add_metric",
        metric_name="api_response_time",
        value=value,
        tags={"endpoint": "/api/users", "method": "GET"}
    )

# Detect anomalies
result = detector.execute(
    operation="detect_anomalies",
    metric_names=["api_response_time"],
    detection_methods=["statistical", "threshold_based", "iqr"]
)

# Handle anomalies
for anomaly in result.get("anomalies_detected", []):
    if anomaly["severity"] == "critical":
        # Trigger emergency response
        send_alert(anomaly)
```

**Best Practices**:
- Layer multiple monitoring nodes for comprehensive coverage
- Set thresholds based on baseline performance
- Monitor the monitors (keep overhead < 5%)
- Use appropriate sampling rates for high-volume systems
- Regularly update performance baselines

**See Also**:
- [Transaction Monitoring Cheatsheet](../cheatsheet/048-transaction-monitoring.md)
- [Monitoring Guide](monitoring-nodes.md)
- [Enterprise Production Patterns](../enterprise/production-patterns.md)

## Middleware Nodes

### Enterprise Middleware (Production Applications)

**Purpose**: Enterprise-grade middleware for building production applications with real-time agent-frontend communication, session management, and comprehensive security.

**Test Coverage**: 17/17 integration tests passing for production reliability

- **AgentUIMiddleware**: Central orchestration hub for frontend communication
  ```python
  # Use for production frontend applications
  from kailash.middleware import AgentUIMiddleware

  middleware = AgentUIMiddleware(
      enable_dynamic_workflows=True,
      max_sessions=1000,
      session_timeout_minutes=60,
      enable_persistence=True,
      database_url="postgresql://..."
  )

  # Create session for frontend client
  session_id = await middleware.create_session(user_id="user123")

  # Create dynamic workflow from frontend configuration
  workflow_id = await middleware.create_dynamic_workflow(
      session_id, workflow_config
  )

  ```

- **RealtimeMiddleware**: Multi-protocol real-time communication
  ```python
  # WebSocket, SSE, and webhook support
  from kailash.middleware import RealtimeMiddleware

  realtime = RealtimeMiddleware(agent_ui_middleware)

  # WebSocket connections with automatic reconnection
  # Server-Sent Events for unidirectional streaming
  # Webhook management for external integrations

  ```

- **APIGateway**: RESTful API layer with authentication
  ```python
  # Production API gateway with OpenAPI docs
  from kailash.middleware import create_gateway

  gateway = create_gateway(
      title="My Kailash API",
      cors_origins=["https://myapp.com"],
      enable_docs=True
  )
  gateway.agent_ui = agent_ui_middleware

  ```

- **AIChatMiddleware**: AI-powered conversation management
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # AI chat with semantic search and context
  from kailash.middleware import AIChatMiddleware

  ai_chat = AIChatMiddleware(
      agent_ui_middleware,
      enable_vector_search=True,
      vector_database_url="postgresql://...",
      default_model_provider="ollama"
  )

  # Natural language to workflow conversion
  response = await ai_chat.send_message(
      session_id,
      "Create a workflow to process CSV data"
  )

  ```

- **EventStream**: Comprehensive event management system
  ```python
  # Real-time event streaming for UI synchronization
  from kailash.middleware.events import EventStream, EventType

  # Subscribe to workflow events
  async def event_handler(event):
      print(f"Workflow {event.workflow_id}: {event.type}")

  await middleware.subscribe_to_events(
      "subscriber_id",
      event_handler,
      event_types=[EventType.WORKFLOW_COMPLETED]
  )

  ```

**Key Features**:
- **Session Management**: Multi-tenant isolation with automatic cleanup
- **Dynamic Workflows**: Runtime workflow creation using WorkflowBuilder.from_dict()
- **Real-time Communication**: WebSocket, SSE, and webhook support
- **Enterprise Security**: JWT authentication, RBAC/ABAC access control
- **Database Integration**: Persistent storage with audit trails
- **AI Integration**: Natural language workflow creation and chat interfaces

**Performance**: Sub-200ms latency, 1000+ concurrent sessions tested

**Use Instead Of**: Custom FastAPI/Flask apps, manual WebSocket handling, custom session management

## Enterprise Workflow Nodes

### Business Workflow Templates
- **BusinessWorkflowTemplates**: ⭐ NEW: Pre-built enterprise workflow templates (Session 067)
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Investment data pipeline template
  template = BusinessWorkflowTemplates.investment_data_pipeline(
      workflow,
      data_sources=["bloomberg", "yahoo"],
      analysis_types=["risk", "performance", "compliance"],
      notification_channels=["email", "slack", "teams"]
  )

  # Document AI processing template
  template = BusinessWorkflowTemplates.document_ai_pipeline(
      workflow,
      document_types=["invoice", "contract", "receipt"],
      ai_providers=["azure", "aws", "google"],
      output_formats=["json", "structured_data"],
      compliance_required=True
  )

  ```

### Data Lineage & Processing
- **DataLineageNode**: ⭐ NEW: Comprehensive data lineage tracking (Session 067)
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Track data transformations with compliance checking
  node = DataLineageNode(
      operation="track_transformation",
      source_info={"system": "CRM", "table": "customers"},
      transformation_type="anonymization",
      compliance_frameworks=["GDPR", "CCPA", "SOX", "HIPAA"],
      include_access_patterns=True,
      audit_trail_enabled=True
  )

  ```
- **BatchProcessorNode**: ⭐ NEW: Intelligent batch processing (Session 067)
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # High-performance batch processing with optimization
  node = BatchProcessorNode(
      operation="process_data_batches",
      data_source="large_dataset",
      batch_size=1000,  # Auto-optimized based on data
      processing_strategy="parallel",
      max_concurrent_batches=10,
      rate_limit_per_second=50,
      error_handling="continue_with_logging"
  )

  ```

## Testing Nodes

### Credential Testing
- **CredentialTestingNode**: Test authentication flows without external services
  ```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

  # Use for testing OAuth2, API keys, JWT, Basic auth
  node = CredentialTestingNode(
      credential_type="oauth2",
      scenario="expired"  # success, expired, invalid, network_error
  )

  ```

## Code Execution Nodes

### Python Execution
- **PythonCodeNode**: Execute arbitrary Python code
  - Use when no specialized node exists
  - For custom business logic
  - For complex data transformations not covered by transform nodes
  - For integrations without dedicated nodes

## When to Use PythonCodeNode

Use PythonCodeNode **only** when:

1. **No specialized node exists** for your use case
2. **Complex custom logic** that doesn't fit existing nodes
3. **Temporary prototyping** before creating a custom node
4. **Mathematical computations** not covered by transform nodes
5. **Custom data validation** beyond filter nodes
6. **Integration with libraries** without dedicated nodes

### Examples of When NOT to Use PythonCodeNode

❌ **Reading/Writing Files**
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Don't use PythonCodeNode:
with open('data.csv') as f:
    data = pd.read_csv(f)

# Use CSVReaderNode instead:
node = CSVReaderNode(file_path='data.csv')

```

❌ **API Calls**
```python
# Don't use PythonCodeNode:
response = requests.get('https://api.example.com/data')

# Use HTTPRequestNode instead:
node = HTTPRequestNode(url='https://api.example.com/data', method='GET')

```

❌ **Data Filtering**
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Don't use PythonCodeNode:
filtered = [x for x in data if x['age'] > 30]

# Use FilterNode instead:
node = FilterNode(condition="age > 30")

```

❌ **LLM Calls**
```python
# Don't use PythonCodeNode:
response = openai.ChatCompletion.create(...)

# Use LLMAgentNode instead:
node = LLMAgentNode(provider="openai", model="gpt-4")

```

### Examples of When to Use PythonCodeNode

✅ **Complex Business Logic**
```python
# Custom pricing calculation with multiple rules
node = PythonCodeNode(
    name="custom_pricing",
    code='''
    # Complex pricing logic specific to business
    base_price = product['price']
    if customer['tier'] == 'platinum':
        discount = 0.20
    elif customer['tier'] == 'gold' and order['quantity'] > 10:
        discount = 0.15
    else:
        discount = 0.05

    final_price = base_price * (1 - discount) * order['quantity']
    result = {"final_price": final_price, "discount_applied": discount}
    '''
)

```

✅ **Scientific Computations**
```python
# Statistical analysis not covered by existing nodes
node = PythonCodeNode(
    name="statistical_analysis",
    code='''
    import numpy as np
    from scipy import stats

    # Custom statistical test
    statistic, p_value = stats.ks_2samp(sample1, sample2)
    result = {
        "statistic": statistic,
        "p_value": p_value,
        "significant": p_value < 0.05
    }
    '''
)

```

## Best Practices

1. **Always check for existing nodes first** - Review this catalog before using PythonCodeNode
2. **Use specialized nodes for better:**
   - Error handling
   - Performance optimization
   - Integration testing
   - Documentation
   - Maintenance

3. **Create custom nodes** instead of repeated PythonCodeNode usage for the same logic
4. **Leverage node composition** - Combine multiple specialized nodes instead of one complex PythonCodeNode

## Node Discovery Tips

1. Check node imports: `from kailash.nodes import ...`
2. Use IDE autocomplete after `from kailash.nodes.`
3. Review examples in `/examples` directory
4. Check node docstrings for usage details
5. Look at test files for usage patterns
