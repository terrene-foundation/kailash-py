# Node Initialization Patterns - Critical Fixes

**Created**: 2025-06-13
**Category**: Critical Patterns
**Priority**: HIGHEST - These errors occur in 90% of custom node implementations

## 🚨 Most Common Node Initialization Errors

### 1. ❌ AttributeError: 'MyNode' object has no attribute 'my_param'

**Wrong Implementation**:
```python
class MyNode(Node):
    def __init__(self, name, **kwargs):
        super().__init__(name=name)  # Kailash validates here!
        self.my_param = kwargs.get("my_param", "default")  # Too late!
        self.threshold = kwargs.get("threshold", 0.75)

```

**Correct Implementation**:
```python
class MyNode(Node):
    def __init__(self, name, **kwargs):
        # Set ALL attributes BEFORE super().__init__()
        self.my_param = kwargs.get("my_param", "default")
        self.threshold = kwargs.get("threshold", 0.75)

        # NOW call parent init - validation will find attributes
        super().__init__(name=name)

```

**Why This Happens**: Kailash validates node parameters during `__init__()`. If attributes aren't set yet, validation fails.

### 2. ❌ 'int' object has no attribute 'required'

**Wrong Implementation**:
```python
def get_parameters(self) -> Dict[str, Any]:
    return {
        "max_tokens": self.max_tokens,  # Returns int
        "threshold": 0.75,              # Returns float
        "strategy": "default"           # Returns str
    }

```

**Correct Implementation**:
```python
from kailash.nodes.base import NodeParameter

def get_parameters(self) -> Dict[str, NodeParameter]:
    return {
        "max_tokens": NodeParameter(
            name="max_tokens",
            type=int,
            required=False,
            default=self.max_tokens,
            description="Maximum tokens allowed"
        ),
        "threshold": NodeParameter(
            name="threshold",
            type=float,
            required=False,
            default=0.75,
            description="Similarity threshold"
        ),
        "strategy": NodeParameter(
            name="strategy",
            type=str,
            required=True,
            description="Processing strategy"
        )
    }

```

### 3. ❌ Missing Abstract Methods

**Error**: Failed to initialize node - Can't instantiate abstract class

**Wrong Implementation**:
```python
class MyNode(Node):
    def __init__(self, name, **kwargs):
        self.config = kwargs
        super().__init__(name=name)

    # Missing required methods!

```

**Correct Implementation**:
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

class MyNode(Node):
    def __init__(self, "workflow_name", **kwargs):
        self.config = kwargs
        super().__init__(name=name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Required by Kailash"""
        return {
            "input_data": NodeParameter(
                name="input_data",
                type=Any,
                required=True,
                description="Input data to process"
            )
        }

    def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Required by Kailash"""
        return self.execute(inputs)

    def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Your actual logic here"""
        # Process the data
        result = self._do_something(inputs.get("input_data"))
        return {"result": result}

```

## 🔍 Provider-Specific Formats

### Ollama Embeddings Format
```python
# ❌ Wrong - Assuming list format
embeddings = result.get("embeddings", [])  # These are dicts!
for embedding in embeddings:
    vector = embedding  # This is a dict, not a list!

# ✅ Correct - Extract from dictionary
embedding_dicts = result.get("embeddings", [])
embeddings = []
for embedding_dict in embedding_dicts:
    if isinstance(embedding_dict, dict) and "embedding" in embedding_dict:
        vector = embedding_dict["embedding"]  # Extract actual vector
        embeddings.append(vector)

```

### LLMAgentNode Interface
```python
# ❌ Wrong - Using process() method
result = llm_node.execute(messages=[{"role": "user", "content": "Hello"}])

# ❌ Wrong - Missing provider
result = llm_node.execute(messages=[{"role": "user", "content": "Hello"}])

# ✅ Correct - Use run() with provider
result = llm_node.execute(
    provider="ollama",  # Required!
    model="llama3.2:3b",
    messages=[{"role": "user", "content": json.dumps(data)}]
)

```

## 📋 Node Implementation Checklist

Before testing your custom node, verify:

- [ ] All attributes set BEFORE `super().__init__()`
- [ ] `get_parameters()` returns `Dict[str, NodeParameter]`
- [ ] `run()` method implemented
- [ ] `process()` method implemented (if needed)
- [ ] Provider parameter included in all LLM/embedding calls
- [ ] Embedding format handling matches provider
- [ ] All imports from correct modules

## 🚀 Quick Fix Reference

| Error Message | Quick Fix |
|--------------|-----------|
| `'MyNode' object has no attribute 'X'` | Move `self.X = ...` before `super().__init__()` |
| `'int' object has no attribute 'required'` | Return `NodeParameter` objects from `get_parameters()` |
| `Can't instantiate abstract class` | Implement `get_parameters()` and `run()` methods |
| `'LLMAgentNode' has no attribute 'process'` | Use `.run()` instead of `.execute()` |
| `KeyError: 'provider'` | Add `provider="ollama"` to `.run()` calls |
| `TypeError: unsupported operand type(s) for *: 'dict' and 'dict'` | Extract embeddings with `emb["embedding"]` |

## 💡 Pro Tips

1. **Always test with real providers** - Mock data hides format issues
2. **Check provider docs** - Each provider has different response formats
3. **Use type hints** - Helps catch return type issues early
4. **Read error messages carefully** - They often point to the exact issue
5. **Start simple** - Get basic node working before adding features

## 🔗 Related Resources

- [07-troubleshooting.md](../../developer/07-troubleshooting.md) - Comprehensive error guide
- [04-pythoncode-node.md](../../developer/04-pythoncode-node.md) - When to use PythonCodeNode
- [comprehensive-node-catalog.md](../../nodes/comprehensive-node-catalog.md) - Find existing nodes
