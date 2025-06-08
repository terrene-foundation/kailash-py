# Mistake 068: PythonCodeNode DataFrame Serialization

## Problem
PythonCodeNode fails with "Node outputs must be JSON-serializable" when returning pandas DataFrames or numpy arrays directly.

## Example Error
```python
# This causes an error:
workflow.add_node("processor", PythonCodeNode(
    name="processor",
    code='''
import pandas as pd
df = pd.DataFrame({'A': [1, 2, 3], 'B': [4, 5, 6]})
result = {"dataframe": df}  # ❌ DataFrame not JSON-serializable
'''
))

# Error: Node outputs must be JSON-serializable. Failed keys: ['result']
```

## Root Cause
1. Node outputs must be JSON-serializable for workflow state management
2. DataFrames, numpy arrays, and other complex objects aren't natively JSON-serializable
3. The validation happens in `BaseNode.validate_outputs()` which uses `json.dumps()`

## Solution
Convert data science objects to JSON-serializable formats before returning:

```python
# Correct approach:
workflow.add_node("processor", PythonCodeNode(
    name="processor",
    code='''
import pandas as pd
import numpy as np

# Create DataFrame
df = pd.DataFrame({'A': [1, 2, 3], 'B': [4, 5, 6]})

# Convert to serializable formats
result = {
    "dataframe_dict": df.to_dict('records'),  # List of row dicts
    "dataframe_json": df.to_json(),           # JSON string
    "columns": df.columns.tolist(),           # Column names
    "shape": df.shape,                        # Tuple (serializable)
    "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()}
}

# For numpy arrays
arr = np.array([1, 2, 3, 4])
result["array"] = arr.tolist()  # Convert to list
result["array_shape"] = arr.shape
'''
))
```

## Common Patterns

### 1. DataFrame Serialization Options
```python
# Row-oriented (list of dicts)
df.to_dict('records')  # [{'A': 1, 'B': 4}, {'A': 2, 'B': 5}, ...]

# Column-oriented (dict of lists)
df.to_dict('list')     # {'A': [1, 2, 3], 'B': [4, 5, 6]}

# Index-oriented (dict of dicts)
df.to_dict('index')    # {0: {'A': 1, 'B': 4}, 1: {'A': 2, 'B': 5}, ...}

# JSON string
df.to_json()           # '{"A":{"0":1,"1":2},"B":{"0":4,"1":5}}'

# CSV string
df.to_csv(index=False) # 'A,B\n1,4\n2,5\n3,6'
```

### 2. Preserving Index
```python
# Index is lost in to_dict('records')
df_with_index = df.set_index('id')

# Preserve index by resetting
result = {
    "data": df_with_index.reset_index().to_dict('records'),
    "index_name": df_with_index.index.name
}
```

### 3. Handling MultiIndex
```python
# MultiIndex DataFrames need special handling
if isinstance(df.index, pd.MultiIndex):
    result = {
        "data": df.reset_index().to_dict('records'),
        "index_names": list(df.index.names)
    }
```

### 4. Round-trip Pattern
```python
# Serialization in one node
result = {
    "df_data": df.to_dict('records'),
    "df_columns": df.columns.tolist(),
    "df_dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()}
}

# Deserialization in next node
df_data = data.get('df_data', [])
if df_data:
    df = pd.DataFrame(df_data)
    # Optionally restore dtypes
    dtypes = data.get('df_dtypes', {})
    for col, dtype_str in dtypes.items():
        if dtype_str == 'int64':
            df[col] = df[col].astype('int64')
```

## Prevention
1. Always convert DataFrames before returning from PythonCodeNode
2. Include metadata (columns, dtypes, shape) for proper reconstruction
3. Consider using CSV/JSON files for large datasets instead of passing through workflow
4. Document serialization format in node descriptions

## Related
- [013-json-serialization-failures.md](013-json-serialization-failures.md)
- [070-data-science-workflow-patterns.md](070-data-science-workflow-patterns.md)
- Security module's `sanitize_input()` now allows DataFrame inputs
