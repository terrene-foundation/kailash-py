# PythonCodeNode Best Practices

Maximum productivity patterns - **ALWAYS use `.from_function()`** for code > 3 lines.

## 🔒 Dual Execution Model

PythonCodeNode has **two distinct execution models** with different security and usability characteristics:

### 1. **Sandboxed String Execution** (Security-First)
- **Use Case**: User-provided code, APIs, dynamic generation
- **Security**: Restricted imports, controlled environment, timeout enforcement
- **Modules**: Only whitelisted (`math`, `json`, `datetime`, `pandas`, `numpy`, `hashlib`, etc.)
- **Trade-off**: Safe but limited capabilities

### 2. **Trusted Function Execution** (Developer-Friendly)
- **Use Case**: Business logic, IDE development, multi-line code
- **Security**: Full Python environment (developer responsibility)
- **Modules**: Any module available
- **Trade-off**: Full capabilities but requires trust

## 🚀 The Golden Rule

**String code = NO IDE support = Lost productivity**

Use `.from_function()` to get:
- ✅ Syntax highlighting
- ✅ Auto-completion
- ✅ Error detection
- ✅ Debugging
- ✅ Testing
- ✅ Full Python environment access

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
analyzer = PythonCodeNode.from_function(func=validate_data, name="analyzer")

```

### Machine Learning
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

def train_model(data: list, target_col: str) -> dict:
    """Train with proper imports."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    import pickle
    import base64
    import pandas as pd

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

trainer = PythonCodeNode.from_function(func=validate_data, name="trainer")

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

# 1. Write and test function
def validate_data(data: list) -> dict:
    # Your logic here
    return {'processed': len(data)}

# 2. Test independently
test_data = [{'id': 1}, {'id': 2}]
result = validate_data(test_data)
assert result['processed'] == 2

# 3. Create node from tested function
node = PythonCodeNode.from_function(
    func=validate_data,
    name="processor"
)

```

## Error Handling Patterns

```python
def robust_processor(data: list) -> dict:
    """Process data with comprehensive error handling."""
    try:
        # Input validation
        if not data:
            return {'result': [], 'error': None, 'count': 0}

        if not isinstance(data, list):
            raise TypeError(f"Expected list, got {type(data)}")

        processed = []
        errors = []

        for i, item in enumerate(data):
            try:
                # Process individual item
                if 'value' not in item:
                    errors.append(f"Item {i}: Missing 'value' field")
                    continue

                processed_item = {
                    'id': item.get('id', i),
                    'processed_value': item['value'] * 2,
                    'timestamp': '2024-01-01T10:00:00Z'
                }
                processed.append(processed_item)

            except Exception as e:
                errors.append(f"Item {i}: {str(e)}")

        return {
            'result': processed,
            'count': len(processed),
            'errors': errors,
            'success_rate': len(processed) / len(data) if data else 0
        }

    except Exception as e:
        return {
            'result': [],
            'count': 0,
            'error': str(e),
            'errors': [str(e)]
        }

# Create robust node
robust_node = PythonCodeNode.from_function(
    func=robust_processor,
    name="robust_processor"
)
```

## Type Hints Best Practices

```python
from typing import List, Dict, Any, Optional, Union
import pandas as pd

def typed_processor(
    data: List[Dict[str, Any]],
    threshold: float = 0.5,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Union[List[Dict], int, float]]:
    """Fully typed processing function."""
    config = config or {}

    # Process with type safety
    filtered_data = [
        item for item in data
        if isinstance(item.get('score'), (int, float))
        and item['score'] > threshold
    ]

    return {
        'filtered_data': filtered_data,
        'count': len(filtered_data),
        'average_score': sum(item['score'] for item in filtered_data) / len(filtered_data) if filtered_data else 0.0
    }

typed_node = PythonCodeNode.from_function(
    func=typed_processor,
    name="typed_processor"
)
```

## Validation Patterns

```python
from pydantic import BaseModel, Field, validator
from typing import List

class DataItem(BaseModel):
    id: int = Field(..., gt=0)
    value: float = Field(..., ge=0.0)
    category: str = Field(..., min_length=1)

    @validator('category')
    def validate_category(cls, v):
        allowed = ['A', 'B', 'C']
        if v not in allowed:
            raise ValueError(f'Category must be one of {allowed}')
        return v

def validated_processor(raw_data: List[Dict]) -> Dict:
    """Process data with Pydantic validation."""
    validated_items = []
    validation_errors = []

    for i, item in enumerate(raw_data):
        try:
            # Validate with Pydantic
            validated_item = DataItem(**item)
            validated_items.append(validated_item.dict())
        except Exception as e:
            validation_errors.append(f"Item {i}: {str(e)}")

    return {
        'validated_data': validated_items,
        'validation_errors': validation_errors,
        'success_count': len(validated_items),
        'error_count': len(validation_errors)
    }

validation_node = PythonCodeNode.from_function(
    func=validated_processor,
    name="validation_processor"
)
```

## Performance Optimization

```python
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict

def performance_processor(data: List[Dict], batch_size: int = 100) -> Dict:
    """High-performance batch processing."""
    start_time = time.time()

    def process_batch(batch: List[Dict]) -> List[Dict]:
        """Process a single batch."""
        return [
            {
                'id': item['id'],
                'processed_value': item['value'] ** 2,
                'category': item.get('category', 'unknown').upper()
            }
            for item in batch
        ]

    # Split into batches for parallel processing
    batches = [data[i:i + batch_size] for i in range(0, len(data), batch_size)]

    # Process batches in parallel
    with ThreadPoolExecutor(max_workers=4) as executor:
        batch_results = list(executor.map(process_batch, batches))

    # Flatten results
    processed_data = [item for batch in batch_results for item in batch]

    processing_time = time.time() - start_time

    return {
        'result': processed_data,
        'count': len(processed_data),
        'batches_processed': len(batches),
        'processing_time_seconds': round(processing_time, 3),
        'items_per_second': round(len(data) / processing_time, 2) if processing_time > 0 else 0
    }

performance_node = PythonCodeNode.from_function(
    func=performance_processor,
    name="performance_processor"
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
| Error Handling | ❌ Basic | ✅ Comprehensive |
| Validation | ❌ Manual | ✅ Automatic |
| Performance | ❌ Unknown | ✅ Measurable |

## Migration Guide

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
def process_records(input_data: dict) -> dict:
    data = input_data.get('records', [])
    filtered = [r for r in data if r.get('active')]
    return {'count': len(filtered)}

node = PythonCodeNode.from_function(
    func=validate_data,
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
