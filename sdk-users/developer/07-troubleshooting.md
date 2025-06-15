# Troubleshooting Custom Nodes

Common issues and their solutions when developing custom nodes.

## Session 061/062 Breaking Changes

### ✅ Session 061: Node Creation Without Required Params

**New Behavior**: Nodes can be created without required parameters (validated at execution):

```python
# ✅ Now OK: Create node without required params
node = CSVReaderNode(name="reader")  # Missing file_path - OK!

# ✅ Configure before execution
node.configure(file_path="data.csv")
result = node.execute()

# ✅ Or pass at runtime
runtime.execute(workflow, parameters={"reader": {"file_path": "data.csv"}})
```

**Old Behavior**: Required parameters during construction caused errors.

### ✅ Session 062: Centralized Data Paths

**New Pattern**: Use centralized data utilities:

```python
# ✅ CORRECT: Centralized data access
from examples.utils.data_paths import get_input_data_path
file_path = str(get_input_data_path("customers.csv"))

# ❌ OLD: Hardcoded paths (now discouraged)
# file_path = "examples/data/customers.csv"
```

**Migration**: Update hardcoded paths to use centralized utilities.

### ✅ Session 064: PythonCodeNode Output Consistency Fix

**Framework Fix**: All PythonCodeNode outputs now consistently wrapped in `"result"` key:

```python
# ✅ FIXED: Both dict and non-dict returns work consistently
def returns_dict(data):
    return {"processed": data, "count": len(data)}

def returns_simple(x):
    return x * 2

# Both outputs are wrapped in {"result": ...}
node1 = PythonCodeNode.from_function(func=returns_dict)
node2 = PythonCodeNode.from_function(func=returns_simple)

# ✅ Always connect using "result" key
workflow.connect("node1", "node2", {"result": "input_data"})
```

**Previously**: Dict returns caused validation errors ("Required output 'result' not provided").

### ✅ Session 062: PythonCodeNode Best Practices

**New Default**: Use `.from_function()` for code > 3 lines:

```python
# ✅ BEST: Full IDE support
def process_data(input_data: list) -> dict:
    """Process with syntax highlighting, debugging, etc."""
    import pandas as pd
    df = pd.DataFrame(input_data)
    return {"count": len(df), "data": df.to_dict('records')}

node = PythonCodeNode.from_function(
    func=process_data,
    name="processor"
)

# ✅ String code only for specific cases:
# - Dynamic code generation
# - User-provided code
# - Simple one-liners
# - Template-based code
node = PythonCodeNode(name="calc", code="result = value * 2")
```

**Migration Tool**: Use `scripts/refactor-pythoncode-strings.py` to convert existing code.

## Issue: Node Initialization Order (Most Common!)

### Error: "'MyNode' object has no attribute 'my_param'"
```
AttributeError: 'MyNode' object has no attribute 'my_param'
```

### Cause: Attributes Set After super().__init__()
```python
# ❌ WRONG - Attributes set too late
class MyNode(Node):
    def __init__(self, name: str, **kwargs):
        super().__init__(name=name)  # Kailash validates here!
        self.my_param = kwargs.get("my_param", "default")  # Too late!

# ✅ CORRECT - Set attributes first
class MyNode(Node):
    def __init__(self, name: str, **kwargs):
        # Set ALL attributes BEFORE super().__init__()
        self.my_param = kwargs.get("my_param", "default")
        self.threshold = kwargs.get("threshold", 0.75)

        # NOW call parent init
        super().__init__(name=name)
```

**Why**: Kailash validates node parameters during `__init__()`. Attributes must exist before validation.

## Issue: get_parameters() Return Type

### Error: "'int' object has no attribute 'required'"
```
AttributeError: 'int' object has no attribute 'required'
```

### Cause: Returning Raw Values Instead of NodeParameter
```python
# ❌ WRONG - Returns raw values
def get_parameters(self) -> Dict[str, Any]:
    return {
        "max_tokens": self.max_tokens,  # int object
        "threshold": 0.75               # float object
    }

# ✅ CORRECT - Return NodeParameter objects
def get_parameters(self) -> Dict[str, NodeParameter]:
    return {
        "max_tokens": NodeParameter(
            name="max_tokens",
            type=int,
            required=False,
            default=self.max_tokens,
            description="Maximum tokens"
        ),
        "threshold": NodeParameter(
            name="threshold",
            type=float,
            required=False,
            default=0.75,
            description="Threshold value"
        )
    }
```

## Issue: LLMAgentNode Interface

### Error: "'LLMAgentNode' object has no attribute 'process'"
```python
# ❌ WRONG - Using process() method
result = llm_node.process(messages=[...])

# ✅ CORRECT - Use run() with provider
result = llm_node.execute(
    provider="ollama",  # Required!
    model="llama3.2:3b",
    messages=[{"role": "user", "content": json.dumps(data)}]
)
```

### Error: "KeyError: 'provider'"
```python
# ❌ WRONG - Missing provider parameter
result = llm_node.execute(messages=[...])

# ✅ CORRECT - Always include provider
result = llm_node.execute(
    provider="ollama",
    model="llama3.2:3b",
    messages=[...]
)
```

## Issue: Ollama Embedding Format

### Error: "TypeError: unsupported operand type(s) for *: 'dict' and 'dict'"
```python
# ❌ WRONG - Assuming embeddings are lists
embeddings = result.get("embeddings", [])
similarity = cosine_similarity(embeddings[0], embeddings[1])  # Fails!

# ✅ CORRECT - Extract vectors from dictionaries
embedding_dicts = result.get("embeddings", [])
embeddings = []
for embedding_dict in embedding_dicts:
    if isinstance(embedding_dict, dict) and "embedding" in embedding_dict:
        vector = embedding_dict["embedding"]  # Extract actual vector
        embeddings.append(vector)
    elif isinstance(embedding_dict, list):
        embeddings.append(embedding_dict)  # Already a vector
```

**Provider Response Formats**:
- **Ollama**: `{"embeddings": [{"embedding": [0.1, 0.2, ...]}, ...]}`
- **OpenAI**: `{"embeddings": [[0.1, 0.2, ...], ...]}`

## Issue: "Can't instantiate abstract class"

### Error Message
```
TypeError: Can't instantiate abstract class MyNode with abstract method get_parameters
```

### Causes and Solutions

#### Cause 1: Using Generic Types
```python
# ❌ This causes the error
from typing import List
def get_parameters(self):
    return {
        'items': NodeParameter(type=List[str], ...)  # Generic type!
    }

# ✅ Solution: Use basic types
def get_parameters(self):
    return {
        'items': NodeParameter(type=list, ...)  # Basic type
    }
```

#### Cause 2: Wrong Return Type
```python
# ❌ Wrong return type
def get_parameters(self):
    return []  # Returns list instead of dict

# ✅ Correct return type
def get_parameters(self) -> Dict[str, NodeParameter]:
    return {}  # Returns dict
```

#### Cause 3: Missing Method Implementation
```python
# ❌ Missing run method
class MyNode(Node):
    def get_parameters(self):
        return {}
    # No run method!

# ✅ Implement both required methods
class MyNode(Node):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {}

    def run(self, **kwargs) -> Dict[str, Any]:
        return {}
```

## Issue: Parameter Validation Errors

### Error: "Parameter 'X' is required"
```python
# Problem: Required parameter not provided
workflow.add_node("node", MyNode())  # Missing required param

# Solution: Provide required parameters
workflow.add_node("node", MyNode(), required_param="value")
```

### Error: "Invalid type for parameter"
```python
# Problem: Wrong type provided
workflow.add_node("node", MyNode(), count="five")  # String for int

# Solution: Provide correct type
workflow.add_node("node", MyNode(), count=5)
```

## Issue: Import Errors

### HTTPClientNode Not Found
```python
# ❌ Old import (deprecated)
from kailash.nodes.api import HTTPClientNode
# ImportError: cannot import name 'HTTPClientNode'

# ✅ New import
from kailash.nodes.api import HTTPRequestNode
```

### Missing Type Imports
```python
# ❌ Missing Tuple import
def method(self) -> Tuple[str, int]:  # NameError: name 'Tuple' is not defined

# ✅ Complete imports
from typing import Any, Dict, List, Tuple, Optional
```

## Issue: Runtime Type Errors

### Working with Any Type
```python
# When using Any type, validate at runtime
def run(self, **kwargs):
    data = kwargs['data']  # type: Any

    # ✅ Add runtime validation
    if not isinstance(data, list):
        raise ValueError(f"Expected list, got {type(data)}")

    # Safe to use as list now
    for item in data:
        process(item)
```

## Issue: Cache Decorator Not Found

### Error: "@cached_query not defined"
```python
# ❌ This decorator doesn't exist in Kailash
@cached_query
def my_method(self):
    pass

# ✅ Use Python's built-in caching
from functools import lru_cache

@lru_cache(maxsize=128)
def my_method(self):
    pass
```

## Issue: Node Not Registered

### Node not available in workflow
```python
# Problem: Custom node not registered
workflow.add_node("MyNode", "node1")  # Error: Unknown node type

# Solution 1: Use node instance directly
from my_module import MyCustomNode
workflow.add_node("node1", MyCustomNode())

# Solution 2: Register the node
from kailash.nodes import register_node
register_node("MyNode", MyCustomNode)
workflow.add_node("MyNode", "node1")
```

## Debugging Tips

### 1. Test Node in Isolation
```python
# Test your node directly
node = MyCustomNode(name="test")

# Check parameters
params = node.get_parameters()
print("Parameters:", params)

# Test with valid inputs
result = node.execute(param1="value1", param2=123)
print("Result:", result)
```

### 2. Enable Verbose Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Your node will now show detailed logs
```

### 3. Check Parameter Schema
```python
# Verify parameter definitions
node = MyCustomNode(name="test")
for name, param in node.get_parameters().items():
    print(f"{name}: type={param.type}, required={param.required}")
```

### 4. Use Type Checking
```python
# Add type hints and use mypy
from typing import Any, Dict
from kailash.nodes.base import Node, NodeParameter

class MyNode(Node):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        # Type checker will validate this
        return {}
```

### Issue: PythonCodeNode Errors

### Error: "Required output 'result' not provided"
```python
# ❌ Problem: Variable was an input, excluded from outputs
workflow.connect("node1", "node2", mapping={"result": "result"})
# In node2:
code = """
data = result.get("data")
result = {"processed": data}  # Won't be in output!
"""

# ✅ Solution: Map to different variable name
workflow.connect("node1", "node2", mapping={"result": "input_data"})
code = """
data = input_data.get("data")
result = {"processed": data}  # Will be in output!
"""
```

### Error: "TypeError: PythonCodeNode.__init__() missing 1 required positional argument: 'name'"
```python
# ❌ Missing name parameter
node = PythonCodeNode(code="result = {}")

# ✅ Always include name
node = PythonCodeNode(name="processor", code="result = {}")
```

### Error: "Object of type DataFrame is not JSON serializable"
```python
# ❌ DataFrame not serializable
code = """
import pandas as pd
df = pd.DataFrame(data)
result = {"dataframe": df}  # Will fail!
"""

# ✅ Convert to serializable format
code = """
import pandas as pd
df = pd.DataFrame(data)
result = {"data": df.to_dict('records')}
"""
```

### Error: "Object of type ndarray is not JSON serializable"
```python
# ❌ NumPy array not serializable
code = """
import numpy as np
arr = np.array([1, 2, 3])
result = {"array": arr}  # Will fail!
"""

# ✅ Convert to list
code = """
import numpy as np
arr = np.array([1, 2, 3])
result = {"array": arr.tolist()}
"""
```

## Issue: DataTransformer Dict Output Bug

### Problem: Dict becomes list of keys
```python
# DataTransformer passes only keys when outputting dicts
# First transformer outputs: {"files": [...], "count": 5}
# Second transformer receives: ["files", "count"]  # Just keys!

# ✅ Workaround: Check type and handle both cases
transformations = [
    """
if isinstance(data, list):
    # Bug case - received keys only
    print("WARNING: DataTransformer dict bug detected")
    # Handle gracefully or use mock data
else:
    # Normal case - received full dict
    files = data.get("files", [])
"""
]
```

## Issue: File Processing Errors

### Error: "NameError: name 'data' is not defined"
```python
# ❌ TextReaderNode outputs 'text', not 'data'
workflow.connect("text_reader", "processor", mapping={"data": "data"})

# ✅ Use correct output name
workflow.connect("text_reader", "processor", mapping={"text": "data"})
```

### Using DirectoryReaderNode Incorrectly
```python
# ❌ DirectoryReaderNode doesn't read file content
discoverer = DirectoryReaderNode(name="reader")  # Only lists files!

# ✅ Use for discovery, then read with appropriate node
discoverer = DirectoryReaderNode(name="discoverer")
csv_reader = CSVReaderNode(name="csv_reader")
# Connect them properly...
```

## Issue: SwitchNode with List Data

### Error: "Required parameter 'input_data' not provided"
```python
# ❌ WRONG: SwitchNode expects single item, not list
risk_assessments = [{'decision': 'approved'}, {'decision': 'declined'}]
workflow.connect("scorer", "router", mapping={"result": "input_data"})
# SwitchNode can't route a list!

# ✅ SOLUTION: Process all items in one node
def process_all_decisions(risk_assessments: list) -> dict:
    approved = [a for a in risk_assessments if a['decision'] == 'approved']
    declined = [a for a in risk_assessments if a['decision'] == 'declined']
    return {
        'approved': {'count': len(approved), 'items': approved},
        'declined': {'count': len(declined), 'items': declined}
    }

workflow.add_node("decision_processor", PythonCodeNode.from_function(
    func=process_all_decisions,
    name="decision_processor"
))
```

## Issue: JSON Parsing in CSV Data

### Error: "SyntaxError: '{' was never closed" with eval()
```python
# CSV files often contain JSON strings in columns
# Example: location,"{""city"":""New York"",""state"":""NY""}"

# ❌ WRONG: Using eval() for JSON parsing
location = eval(txn.get('location', '{}'))  # DANGEROUS and can fail!

# ✅ CORRECT: Safe JSON parsing with error handling
def parse_json_field(field_value: str, default: dict = None) -> dict:
    """Safely parse JSON string from CSV field."""
    if default is None:
        default = {}

    try:
        import json
        return json.loads(field_value)
    except (json.JSONDecodeError, TypeError):
        return default

# Usage in node
location_str = txn.get('location', '{}')
location = parse_json_field(location_str)
```

## Issue: Type Conversion from CSV

### Error: "'>' not supported between instances of 'str' and 'int'"
```python
# ❌ WRONG: CSV data is always strings
if transaction['amount'] > 5000:  # Will fail!
    process_high_value(transaction)

# ✅ CORRECT: Convert types appropriately
amount = float(transaction.get('amount', 0))
if amount > 5000:
    process_high_value(transaction)

# ✅ BEST: Robust conversion function
def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

amount = safe_float(transaction.get('amount'))
```

## Common Mistakes Checklist

- [ ] **Setting attributes AFTER super().__init__() - #1 MOST COMMON ERROR**
- [ ] **Returning raw values from get_parameters() instead of NodeParameter objects**
- [ ] **Using .process() on LLMAgentNode instead of .run()**
- [ ] **Missing provider parameter in LLM/embedding calls**
- [ ] **Not extracting vectors from Ollama embedding dictionaries**
- [ ] Using `List[T]`, `Dict[K,V]` instead of `list`, `dict`
- [ ] Missing `run()` method implementation
- [ ] Wrong return type from `get_parameters()`
- [ ] Not handling optional parameters with defaults
- [ ] Using deprecated class names (HTTPClientNode)
- [ ] Not validating `Any` type parameters at runtime
- [ ] Forgetting to import required types
- [ ] Not providing required parameters when adding to workflow
- [ ] **Mapping PythonCodeNode outputs to same variable name as inputs**
- [ ] **Forgetting name parameter in PythonCodeNode**
- [ ] **Not serializing DataFrames and NumPy arrays**
- [ ] **Using manual file operations instead of DirectoryReaderNode**
- [ ] **Not handling DataTransformer dict output bug**
- [ ] **Using SwitchNode for list processing**
- [ ] **Using eval() for JSON parsing**
- [ ] **Not converting CSV string data to appropriate types**

---

*Need more help? Check the [examples/](examples/) directory for working implementations.*
