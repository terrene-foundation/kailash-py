# PythonCodeNode Data Science Patterns

Essential patterns for data science workflows using PythonCodeNode with pandas, numpy, and scikit-learn.

## DataFrame Processing

### Basic Operations & Serialization
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

# ✅ ALWAYS use .from_function() for complex operations
def process_dataframe(data: list) -> dict:
    """Process DataFrame with proper serialization."""
    import pandas as pd
    import numpy as np

    df = pd.DataFrame(data)

    # Operations
    df['total'] = df['price'] * df['quantity']
    summary = df.groupby('category').agg({
        'total': ['sum', 'mean'],
        'quantity': 'count'
    })

    # CRITICAL: Serialize before returning
    return {
        'data': df.to_dict('records'),      # List of dicts
        'summary': summary.to_dict('index'), # Nested dict
        'shape': df.shape,                   # Tuple
        'columns': df.columns.tolist()       # List
    }

processor = PythonCodeNode.from_function(
    func=process_dataframe,
    name="df_processor"
)

```

### Serialization Formats
```python
# Different formats for different needs
result = {
    'records': df.to_dict('records'),    # [{col: val}, ...] - loses index
    'list': df.to_dict('list'),         # {col: [vals]} - column-oriented
    'dict': df.to_dict('dict'),         # {col: {idx: val}} - preserves index
    'json': df.to_json(orient='split'), # JSON string with schema
    'values': df.values.tolist()        # Nested list (no columns)
}

# Preserve index explicitly
result = {
    'data': df.reset_index().to_dict('records'),
    'index_name': df.index.name or 'index'
}

```

## NumPy Array Handling

### Array Serialization
```python
def process_arrays(data: dict) -> dict:
    """Handle NumPy arrays with proper serialization."""
    import numpy as np

    # Arrays must be converted to lists
    arr = np.array(data['values'])
    processed = np.sqrt(arr)

    return {
        'result': processed.tolist(),        # ✅ Convert to list
        'mean': float(np.mean(processed)),   # ✅ Convert scalars
        'std': float(np.std(processed)),
        'shape': arr.shape,                  # Tuples are OK
        'dtype': str(arr.dtype)              # Convert dtype to string
    }

```

## Machine Learning Integration

### Model Training Pattern
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

def train_model(data: list, target_col: str = 'target') -> dict:
    """Train model with proper serialization."""
    import pandas as pd
    from sklearn.model_selection import train_test_split
    from sklearn.ensemble import RandomForestClassifier
    import pickle
    import base64

    df = pd.DataFrame(data)
    X = df.drop(target_col, axis=1)
    y = df[target_col]

    # Split and train
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = RandomForestClassifier(n_estimators=100)
    model.fit(X_train, y_train)

    # Serialize model for storage
    model_bytes = pickle.dumps(model)
    model_b64 = base64.b64encode(model_bytes).decode('utf-8')

    return {
        'train_score': float(model.score(X_train, y_train)),
        'test_score': float(model.score(X_test, y_test)),
        'feature_importance': dict(zip(X.columns, model.feature_importances_)),
        'model_base64': model_b64
    }

trainer = PythonCodeNode.from_function(func=train_model, name="trainer")

```

## Visualization Patterns

### Plot to Base64
```python
def create_visualization(data: list) -> dict:
    """Generate plot as base64 string."""
    import pandas as pd
    import matplotlib.pyplot as plt
    import base64
    from io import BytesIO

    df = pd.DataFrame(data)

    # Create plot
    fig, ax = plt.subplots(figsize=(10, 6))
    df.groupby('category')['value'].mean().plot(kind='bar', ax=ax)
    ax.set_title('Average Value by Category')

    # Convert to base64
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.read()).decode('utf-8')
    plt.close()

    return {
        'plot_base64': img_base64,
        'plot_type': 'bar',
        'categories': df['category'].unique().tolist()
    }

```

## Error Handling

### Safe Processing Pattern
```python
def safe_data_processor(data) -> dict:
    """Process data with comprehensive error handling."""
    import pandas as pd
    import numpy as np

    errors = []
    warnings = []

    # Safe DataFrame creation
    try:
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict) and 'records' in data:
            df = pd.DataFrame(data['records'])
        else:
            df = pd.DataFrame()
    except:
        errors.append("Failed to create DataFrame")
        return {'errors': errors, 'success': False}

    # Safe operations
    if df.empty:
        warnings.append("Empty DataFrame")
        return {'warnings': warnings, 'data': [], 'success': True}

    # Numeric conversion with tracking
    for col in df.columns:
        if df[col].dtype == 'object':
            try:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                null_count = df[col].isna().sum()
                if null_count > 0:
                    warnings.append(f"{col}: {null_count} non-numeric")
            except:
                pass

    return {
        'data': df.to_dict('records'),
        'stats': df.describe().to_dict() if len(df.select_dtypes(include=[np.number]).columns) > 0 else {},
        'warnings': warnings,
        'success': True
    }

```

## Memory-Efficient Processing

### Chunked Processing
```python
def process_large_dataset(data: list, chunk_size: int = 1000) -> dict:
    """Process data in chunks for memory efficiency."""
    import pandas as pd
    import numpy as np

    results = []

    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        df_chunk = pd.DataFrame(chunk)

        # Process chunk
        chunk_stats = {
            'mean': float(df_chunk['value'].mean()),
            'count': len(df_chunk),
            'chunk_id': i // chunk_size
        }
        results.append(chunk_stats)

    # Aggregate results
    total_mean = np.average(
        [r['mean'] for r in results],
        weights=[r['count'] for r in results]
    )

    return {
        'chunk_results': results,
        'total_mean': float(total_mean),
        'total_records': sum(r['count'] for r in results)
    }

```

## Common Gotchas & Solutions

| Issue | Solution |
|-------|----------|
| DataFrame not JSON-serializable | Use `.to_dict('records')` |
| NumPy array not serializable | Use `.tolist()` |
| NumPy scalars (np.float64) | Use `float()`, `int()` |
| Model serialization | Use pickle + base64 |
| Index preservation | Reset index or store separately |
| Platform-specific types | Check with `hasattr()` |
| Memory issues | Process in chunks |

## Quick Reference

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

# Always serialize DataFrames
df.to_dict('records')  # Most common
df.to_json(orient='split')  # With schema

# Always convert NumPy
arr.tolist()  # Arrays
float(scalar)  # Scalars
str(dtype)  # Data types

# Always handle errors
try:
    # operations
except:  # Use bare except in sandbox
    # fallback

# Always use .from_function() for >3 lines
node = PythonCodeNode.from_function(func=my_func, name="processor")

```
