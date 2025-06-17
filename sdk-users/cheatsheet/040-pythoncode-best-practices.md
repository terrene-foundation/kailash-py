# PythonCodeNode Best Practices

Maximum productivity patterns - **ALWAYS use `.from_function()`** for code > 3 lines.

## 🚀 The Golden Rule

**String code = NO IDE support = Lost productivity**

Use `.from_function()` to get:
- ✅ Syntax highlighting
- ✅ Auto-completion
- ✅ Error detection
- ✅ Debugging
- ✅ Testing

## Quick Examples

### ❌ BAD: String Code
```python
# NO IDE SUPPORT!
node = PythonCodeNode(
    name="processor",
    code="""
df = pd.DataFrame(data)
filtered = df[df['value'] > 100]  # Hope column exists!
result = filtered.groupby('category').mean()  # No validation
"""
)

```

### ✅ GOOD: Function-Based
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

# FULL IDE SUPPORT!
def process_data(data: list, threshold: int = 100) -> dict:
    """Process data with validation."""
    df = pd.DataFrame(data)

    if 'value' not in df.columns:
        return {'error': 'Missing value column'}

    filtered = df[df['value'] > threshold]

    if filtered.empty:
        return {'result': [], 'count': 0}

    return {
        'result': filtered.to_dict('records'),
        'count': len(filtered),
        'mean': float(filtered['value'].mean())
    }

# Create node from tested function
node = PythonCodeNode.from_function(
    func=process_data,
    name="processor"
)

```

## Common Patterns

### Data Processing Pipeline
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

def clean_data(raw_data: list) -> pd.DataFrame:
    """Clean with full IDE support."""
    df = pd.DataFrame(raw_data)
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    return df.dropna()

def validate_data(df: pd.DataFrame) -> dict:
    """Analyze with type hints."""
    return {
        'mean': float(df['value'].mean()),
        'std': float(df['value'].std()),
        'quantiles': df['value'].quantile([0.25, 0.5, 0.75]).to_dict()
    }

# Create nodes
cleaner = PythonCodeNode.from_function(func=clean_data, name="cleaner")
analyzer = PythonCodeNode.from_function(func=analyze_data, name="analyzer")

```

### Machine Learning
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

def validate_data(df: pd.DataFrame) -> dict:
    """Train with proper imports."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    import pickle
    import base64

    df = pd.DataFrame(data)
    X = df.drop(target_col, axis=1)
    y = df[target_col]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = RandomForestClassifier()
    model.fit(X_train, y_train)

    # Serialize for storage
    model_bytes = pickle.dumps(model)

    return {
        'score': float(model.score(X_test, y_test)),
        'model_b64': base64.b64encode(model_bytes).decode()
    }

trainer = PythonCodeNode.from_function(func=train_model, name="trainer")

```

## When String Code is OK

Only for **very simple** operations:

```python
# 1. Simple calculations (1-2 lines)
calc = PythonCodeNode(
    name="calc",
    code="result = value * 1.1"
)

# 2. Basic transformations (2-3 lines)
transform = PythonCodeNode(
    name="transform",
    code="""
values = data.get('values', [])
result = [x * 2 for x in values if x > 0]
"""
)

# 3. Dynamic generation
def create_filter('col', val: float):
    return PythonCodeNode(
        name=f"filter_{col}",
        code=f"result = [r for r in data if r['{col}'] > {val}]"
    )

```

## Testing Pattern

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

# 1. Write and test function
def validate_data(df: pd.DataFrame) -> dict:
    # Your logic here
    return {'processed': len(data)}

# 2. Test independently
test_data = [{'id': 1}, {'id': 2}]
result = my_processor(test_data)
assert result['processed'] == 2

# 3. Create node from tested function
node = PythonCodeNode.from_function(
    func=my_processor,
    name="processor"
)

```

## Benefits Comparison

| Feature | String Code | `.from_function()` |
|---------|-------------|-------------------|
| IDE Support | ❌ None | ✅ Full |
| Debugging | ❌ Print only | ✅ Breakpoints |
| Testing | ❌ Hard | ✅ Easy |
| Refactoring | ❌ Manual | ✅ Automated |
| Type Hints | ❌ None | ✅ Full |

## Migration Guide

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

# Before (string)
node = PythonCodeNode(
    name="old",
    code="""
data = input_data['records']
filtered = [r for r in data if r['active']]
result = {'count': len(filtered)}
"""
)

# After (function)
def validate_data(df: pd.DataFrame) -> dict:
    data = input_data.get('records', [])
    filtered = [r for r in data if r.get('active')]
    return {'count': len(filtered)}

node = PythonCodeNode.from_function(
    func=process_records,
    name="new"
)

```

## Remember

**Your IDE is your superpower - use it!**

`.from_function()` gives you:
- 🎯 Code completion
- 🐛 Instant errors
- 🔍 Easy debugging
- ✅ Testability
- 📝 Documentation
- 🚀 10x productivity
