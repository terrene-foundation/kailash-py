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

## Node Categories at a Glance

### 📁 Data I/O (15+ nodes)
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# File operations
CSVReaderNode, CSVWriterNode
JSONReaderNode, JSONWriterNode
TextReaderNode, TextWriterNode

# Database
QueryRouterNode         # ⭐⭐⭐ Intelligent query routing (Phase 2)
WorkflowConnectionPool  # ⭐⭐ Production connection pooling
AsyncSQLDatabaseNode    # Async queries with reuse
SQLDatabaseNode         # Simple sync queries
VectorDatabaseNode      # Vector/embedding storage

# SharePoint
SharePointGraphReader, SharePointGraphWriter

# Streaming
KafkaConsumerNode, StreamPublisherNode
WebSocketNode, EventStreamNode

```

### 🔄 Transform (8+ nodes)
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

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
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# LLM Agents
LLMAgentNode, IterativeLLMAgentNode
ChatAgent, RetrievalAgent
FunctionCallingAgent, PlanningAgent

# Coordination
A2AAgentNode, A2ACoordinatorNode
SharedMemoryPoolNode

# Self-organizing
AgentPoolManagerNode
SelfOrganizingAgentNode
TeamFormationNode

# ML Models
TextClassifier, SentimentAnalyzer
NamedEntityRecognizer, TextSummarizer
EmbeddingGeneratorNode

```

### 🌐 API (10+ nodes)
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

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
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

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

### 🔐 Admin & Security (4+ nodes)
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.admin import (
    UserManagementNode,
    RoleManagementNode,
    PermissionCheckNode,
    AuditLogNode
)

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# User lifecycle management
UserManagementNode  # Create, update, delete, bulk operations

# Role-based access control
RoleManagementNode  # Hierarchical roles, permissions, inheritance

# Real-time permission checking
PermissionCheckNode  # RBAC/ABAC, caching, batch operations

# Security and compliance
AuditLogNode  # Comprehensive audit trails
```

**Performance Benchmarks:**
- ✅ **PermissionCheckNode**: 221 ops/sec, P95 <50ms, 97.8% cache hit rate
- ✅ **RoleManagementNode**: 10,000+ concurrent operations validated
- ✅ **Test Coverage**: 72 tests (unit + integration + E2E)

## Database Operations Decision Guide

### When to Use Each Database Node

```mermaid
graph TD
    A[Need Database Access?] --> B{Production App?}
    B -->|Yes| C{Multiple Concurrent Queries?}
    B -->|No| D{Async Support Needed?}

    C -->|Yes| E{Need Query Optimization?}
    C -->|No| F{Connection Reuse?}

    E -->|Yes| R[QueryRouterNode + WorkflowConnectionPool ⭐⭐⭐]
    E -->|No| P[WorkflowConnectionPool ⭐⭐]

    F -->|Yes| G[AsyncSQLDatabaseNode]
    F -->|No| H[SQLDatabaseNode]

    D -->|Yes| G
    D -->|No| H

    R --> M[Benefits: Auto connection mgmt, caching, pattern learning]
    P --> I[Benefits: Connection pooling, health monitoring, fault tolerance]
    G --> J[Benefits: Async execution, connection reuse]
    H --> K[Benefits: Simple, synchronous]
```

### Database Node Comparison

| Feature | QueryRouterNode + Pool | WorkflowConnectionPool | AsyncSQLDatabaseNode | SQLDatabaseNode |
|---------|------------------------|------------------------|---------------------|-----------------|
| **Use Case** | High-perf production | Production apps | Async workflows | Simple queries |
| **Connection Pooling** | ✅ Auto-managed | ✅ Min/Max pools | ❌ Single connection | ❌ No pooling |
| **Query Caching** | ✅ Prepared statements | ❌ None | ❌ None | ❌ None |
| **Read/Write Split** | ✅ Automatic | ❌ Manual | ❌ None | ❌ None |
| **Pattern Learning** | ✅ AI-optimized | ❌ Basic patterns | ❌ None | ❌ None |
| **Health Monitoring** | ✅ Smart routing | ✅ Auto-recycling | ❌ Manual checks | ❌ None |
| **Fault Tolerance** | ✅ Multi-layer | ✅ Actor-based | ⚠️ Basic retry | ❌ None |
| **Performance** | ⭐⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| **Concurrency** | Very High (1000s) | High (100s) | Medium (10s) | Low (1) |
| **Setup Complexity** | Medium-High | Medium | Low | Very Low |

### Example: Choosing the Right Node

```python
# Scenario 1: High-performance production app with query patterns
# ✅ Use QueryRouterNode + WorkflowConnectionPool (Phase 2)
pool = WorkflowConnectionPool(
    name="ecommerce_pool",
    database_type="postgresql",
    min_connections=10,
    max_connections=50,
    health_threshold=70,
    adaptive_sizing=True,        # NEW: Dynamic sizing
    enable_query_routing=True    # NEW: Pattern tracking
)

router = QueryRouterNode(
    name="smart_router",
    connection_pool="ecommerce_pool",
    enable_read_write_split=True,  # Optimize read queries
    cache_size=2000,               # Cache prepared statements
    pattern_learning=True          # Learn from patterns
)

# Use router for all queries - no manual connection management!
result = await router.process({
    "query": "SELECT * FROM products WHERE category = ?",
    "parameters": ["electronics"]
})

# Scenario 2: Production app without complex patterns
# ✅ Use WorkflowConnectionPool alone
pool = WorkflowConnectionPool(
    name="app_pool",
    database_type="postgresql",
    min_connections=5,
    max_connections=20,
    health_threshold=70
)

# Scenario 3: Data pipeline with sequential processing
# ✅ Use AsyncSQLDatabaseNode
async_db = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="analytics"
)

# Scenario 4: Simple script or one-off query
# ✅ Use SQLDatabaseNode
simple_db = SQLDatabaseNode(
    connection_string="postgresql://user:pass@localhost/db"
)
```

## Common Anti-Patterns

### 1. File Operations
```python
# ❌ WRONG - Using PythonCodeNode for file I/O
def read_csv_node():
    code = '''
import pandas as pd
df = pd.read_csv(file_path)
result = {"data": df.to_dict('records')}
'''
    return PythonCodeNode(name="reader", code=code)

# ✅ RIGHT - Use specialized node
node = CSVReaderNode(file_path="data.csv")

```

### 2. API Calls
```python
# ❌ WRONG - Using PythonCodeNode for HTTP
def api_call_node():
    code = '''
import requests
response = requests.get(url, headers=headers)
result = {"data": response.json()}
'''
    return PythonCodeNode(name="api", code=code)

# ✅ RIGHT - Use API node
node = HTTPRequestNode(
    url="https://api.example.com",
    method="GET",
    headers={"Authorization": "Bearer token"}
)

```

### 3. Data Filtering
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# ❌ WRONG - Using PythonCodeNode for filtering
def filter_node():
    code = '''
df = pd.DataFrame(data)
filtered = df[df['age'] > 30]
result = {"data": filtered.to_dict('records')}
'''
    return PythonCodeNode(name="filter", code=code)

# ✅ RIGHT - Use FilterNode
node = FilterNode(condition="age > 30")

```

### 4. LLM Integration

#### Cloud LLMs (OpenAI, Anthropic)
```python
# ❌ WRONG - Using PythonCodeNode for cloud LLM calls
def llm_node():
    code = '''
import openai
response = openai.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": prompt}]
)
result = {"response": response.choices[0].message.content}
'''
    return PythonCodeNode(name="llm", code=code)

# ✅ RIGHT - Use LLMAgentNode for cloud providers
node = LLMAgentNode(
    provider="openai",
    model="gpt-4",
    system_prompt="You are a helpful assistant"
)
```

#### Local LLMs (Ollama) - EXCEPTION: Use PythonCodeNode
```python
# ✅ CORRECT - Ollama requires PythonCodeNode for reliability
def ollama_llm(prompt, model="llama3.2:1b"):
    """Production-ready Ollama integration."""
    import requests

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 200}
            },
            timeout=30
        )

        if response.status_code == 200:
            return {
                "response": response.json()["response"],
                "success": True,
                "model": model
            }
        else:
            return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Use with PythonCodeNode for Ollama
ollama_node = PythonCodeNode.from_function(ollama_llm, name="ollama")

# ❌ DON'T use LLMAgentNode with Ollama in cycles - causes context conflicts
# ✅ DO use PythonCodeNode wrapper for Ollama in all scenarios
```

#### Ollama Embeddings
```python
# ✅ CORRECT - Ollama embeddings with PythonCodeNode
def ollama_embeddings(texts):
    """Extract embeddings using Ollama nomic-embed-text."""
    import requests

    embeddings = []
    for text in texts:
        try:
            response = requests.post(
                "http://localhost:11434/api/embeddings",
                json={"model": "nomic-embed-text:latest", "prompt": text},
                timeout=10
            )

            if response.status_code == 200:
                # CRITICAL: Extract embedding from response
                embeddings.append(response.json().get("embedding", []))
        except Exception as e:
            print(f"Embedding failed for '{text}': {e}")

    return {
        "embeddings": embeddings,
        "success": len(embeddings) > 0,
        "dimensions": len(embeddings[0]) if embeddings else 0
    }

embed_node = PythonCodeNode.from_function(ollama_embeddings, name="embedder")

# ❌ DON'T use EmbeddingGeneratorNode with Ollama - format incompatibility
# ✅ DO use direct API calls for consistent embedding extraction
```

#### When to Use Which Approach

| Scenario | Use LLMAgentNode | Use PythonCodeNode |
|----------|------------------|-------------------|
| Cloud LLMs (OpenAI, Anthropic) | ✅ Recommended | ❌ Unnecessary |
| Local LLMs (Ollama) | ❌ Context conflicts | ✅ Required |
| Cyclic workflows | ❌ Parameter issues | ✅ Reliable |
| Complex processing | ✅ Good for simple | ✅ Full control |
| A2A agent coordination | ❌ Known issues | ✅ Working pattern |

## When to Use PythonCodeNode

PythonCodeNode is appropriate for:

### 1. Complex Business Logic
```python
# Custom pricing calculation with complex rules
node = PythonCodeNode(
    name="custom_pricing",
    code='''
# Business-specific logic that doesn't fit standard nodes
base_price = product['price']
if customer['tier'] == 'platinum' and season == 'holiday':
    discount = 0.30
elif customer['tier'] == 'gold' and quantity > 100:
    discount = 0.20
else:
    discount = calculate_dynamic_discount(customer, product, market_conditions)

final_price = apply_regional_pricing(base_price * (1 - discount))
result = {"final_price": final_price, "discount": discount}
'''
)

```

### 2. Scientific Computing
```python
# Statistical analysis not covered by transform nodes
node = PythonCodeNode(
    name="statistical_analysis",
    code='''
from scipy import stats
import numpy as np

# Custom statistical tests
statistic, p_value = stats.anderson(data, dist='norm')
skewness = stats.skew(data)
kurtosis = stats.kurtosis(data)

result = {
    "anderson_statistic": statistic,
    "critical_values": list(p_value),
    "skewness": skewness,
    "kurtosis": kurtosis,
    "is_normal": p_value[2] > 0.05
}
'''
)

```

### 3. Data Science Workflows
```python
# Feature engineering specific to domain
node = PythonCodeNode(
    name="feature_engineering",
    code='''
# Domain-specific feature creation
df['days_since_last_purchase'] = (today - df['last_purchase_date']).dt.days
df['purchase_velocity'] = df['total_purchases'] / df['account_age_days']
df['seasonal_factor'] = df['purchase_date'].dt.month.map(seasonal_weights)

# Complex aggregations
customer_features = df.groupby('customer_id').agg({
    'purchase_amount': ['mean', 'std', 'max', percentile_90],
    'purchase_velocity': ['mean', 'trend'],
    'category': lambda x: x.mode()[0]
})

result = {"features": customer_features.to_dict('records')}
'''
)

```

## Best Practices

1. **Check for existing nodes first** - Review the node catalog
2. **Prefer composition** - Combine multiple specialized nodes
3. **Create custom nodes** - For repeated logic, create a proper node class
4. **Use PythonCodeNode sparingly** - Only for truly custom logic
5. **Document your choice** - Explain why PythonCodeNode was necessary

## Performance Comparison

| Aspect | PythonCodeNode | Specialized Nodes |
|--------|----------------|-------------------|
| Error Handling | Generic Python errors | Domain-specific errors |
| Validation | Manual validation needed | Built-in validation |
| Performance | Overhead of code execution | Optimized for task |
| Testing | Must test custom code | Pre-tested functionality |
| Documentation | Must document behavior | Self-documenting |
| Type Safety | Runtime type errors | Compile-time checks |

## Migration Examples

### Example 1: CSV Processing
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Before: PythonCodeNode
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("reader", PythonCodeNode(
    name="csv_reader",
    code="df = pd.read_csv(file_path); result = {'data': df.to_dict('records')}"
))

# After: Specialized nodes
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("reader", CSVReaderNode(file_path="data.csv"))

```

### Example 2: API Integration
```python
# Before: PythonCodeNode with requests
workflow.add_node("api", PythonCodeNode(
    name="api_caller",
    code="response = requests.post(url, json=payload); result = response.json()"
))

# After: RESTClientNode
workflow.add_node("api", RESTClientNode(
    base_url="https://api.example.com",
    endpoint="/data",
    method="POST"
))

```

## Conclusion

The Kailash SDK provides 66+ specialized nodes designed to handle common tasks efficiently and reliably. Before reaching for PythonCodeNode:

1. Check the comprehensive node catalog
2. Consider combining existing nodes
3. Evaluate if a custom node class would be better
4. Use PythonCodeNode only for truly unique logic

This approach leads to more maintainable, testable, and performant workflows.
