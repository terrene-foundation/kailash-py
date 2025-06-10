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
| Filter data | `df[df['x'] > y]` | `FilterNode` |
| Map function | `[f(x) for x in data]` | `Map` |
| Sort data | `sorted()` or `df.sort()` | `Sort` |
| If/else logic | `if condition:` | `SwitchNode` |
| Merge data | `pd.concat()` | `MergeNode` |
| LLM calls | OpenAI/Anthropic SDK | `LLMAgentNode` |
| Embeddings | OpenAI embeddings | `EmbeddingGeneratorNode` |
| Text splitting | Manual chunking | `TextSplitterNode` |

## Node Categories at a Glance

### 📁 Data I/O (15+ nodes)
```python
# File operations
CSVReaderNode, CSVWriterNode
JSONReaderNode, JSONWriterNode
TextReaderNode, TextWriterNode

# Database
SQLDatabaseNode
VectorDatabaseNode

# SharePoint
SharePointGraphReader, SharePointGraphWriter

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
```python
# ❌ WRONG - Using PythonCodeNode for LLM calls
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

# ✅ RIGHT - Use LLMAgentNode
node = LLMAgentNode(
    provider="openai",
    model="gpt-4",
    system_prompt="You are a helpful assistant"
)
```

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
# Before: PythonCodeNode
workflow.add_node("reader", PythonCodeNode(
    name="csv_reader",
    code="df = pd.read_csv(file_path); result = {'data': df.to_dict('records')}"
))

# After: Specialized nodes
workflow.add_node("reader", CSVReaderNode(file_path="data.csv"))
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
