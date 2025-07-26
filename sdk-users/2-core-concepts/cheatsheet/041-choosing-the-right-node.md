# 030 - Choosing the Right Node

Quick decision guide for selecting the appropriate node type instead of defaulting to PythonCodeNode.

## Decision Tree

### 1. File Operations?
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

# Reading CSV? → CSVReaderNode
node = CSVReaderNode(file_path="data.csv")

# Writing JSON? → JSONWriterNode
node = JSONWriterNode(file_path="output.json")

# Text files? → TextReaderNode/TextWriterNode
node = TextReaderNode(file_path="doc.txt")

```

### 2. API Calls?
```python
# HTTP request? → HTTPRequestNode
node = HTTPRequestNode(url="https://api.example.com", method="GET")

# REST API? → RESTClientNode
node = RESTClientNode(base_url="https://api.example.com")

# GraphQL? → GraphQLClientNode
node = GraphQLClientNode(endpoint="https://api.example.com/graphql")

```

### 3. Data Transformation?
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

# Filtering? → FilterNode
node = FilterNode(condition="age > 30")

# Mapping? → Map
node = Map(function=lambda x: x.upper())

# Sorting? → Sort
node = Sort(key="timestamp", reverse=True)

```

### 4. AI/LLM Operations?
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

# LLM calls? → LLMAgentNode
node = LLMAgentNode(provider="openai", model="gpt-4")

# Embeddings? → EmbeddingGeneratorNode
node = EmbeddingGeneratorNode(provider="openai")

# Agent coordination? → A2AAgentNode
node = A2AAgentNode(agent_id="researcher")

```

### 5. Control Flow?
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

# Conditional routing? → SwitchNode
node = SwitchNode(condition="status == 'success'")

# Merging streams? → MergeNode
node = MergeNode(merge_strategy="concat")

# Loops? → LoopNode
node = LoopNode(max_iterations=5)

```

### 6. Database Operations?
```python
# SQL queries? → SQLDatabaseNode
node = SQLDatabaseNode(
    connection_string="postgresql://...",
    query="SELECT * FROM users"
)

# Vector search? → VectorDatabaseNode
node = VectorDatabaseNode(collection="embeddings")

```

## When to Use PythonCodeNode

Only use PythonCodeNode when:

1. **Complex business logic** unique to your domain
2. **Scientific computations** not covered by existing nodes
3. **Custom validation** beyond simple filters
4. **Prototyping** before creating a custom node
5. **Integration** with specialized libraries

## Common Anti-Patterns

### ❌ Don't Do This:
```python
# Reading a file
node = PythonCodeNode(
    name="read_csv",
    code='''
    import pandas as pd
    df = pd.read_csv(file_path)
    result = {"data": df.to_dict('records')}
    '''
)

```

### ✅ Do This Instead:
```python
# Use specialized node
node = CSVReaderNode(file_path="data.csv")

```

### ❌ Don't Do This:
```python
# Making API call
node = PythonCodeNode(
    name="api_call",
    code='''
    import requests
    response = requests.get(url)
    result = {"data": response.json()}
    '''
)

```

### ✅ Do This Instead:
```python
# Use API node
node = HTTPRequestNode(url="https://api.example.com", method="GET")

```

## Quick Reference Table

| Task | Wrong (PythonCodeNode) | Right (Specialized Node) |
|------|------------------------|--------------------------|
| Read CSV | `pd.read_csv()` | `CSVReaderNode` |
| Write JSON | `json.dump()` | `JSONWriterNode` |
| HTTP Request | `requests.get()` | `HTTPRequestNode` |
| Filter Data | `df[df['x'] > y]` | `FilterNode` |
| LLM Call | `openai.chat.completions.create()` | `LLMAgentNode` |
| SQL Query | `cursor.execute()` | `SQLDatabaseNode` |
| Conditional | `if/else` logic | `SwitchNode` |
| Merge Data | `pd.concat()` | `MergeNode` |

## Performance Benefits

Using specialized nodes provides:
- **Better error handling** - Node-specific error messages
- **Type safety** - Validated inputs/outputs
- **Performance optimization** - Optimized for specific tasks
- **Easier testing** - Mock-friendly interfaces
- **Better documentation** - Clear intent

## See Also
- [Comprehensive Node Catalog](../nodes/comprehensive-node-catalog.md)
- [Common Node Patterns](004-common-node-patterns.md)
- [PythonCode Data Science Patterns](029-pythoncode-data-science-patterns.md)
