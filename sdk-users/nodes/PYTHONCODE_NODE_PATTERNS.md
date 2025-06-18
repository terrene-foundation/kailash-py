# PythonCodeNode Variable Access Patterns

## Critical Understanding: Direct Variable Injection

The PythonCodeNode **injects input parameters directly into the execution namespace**. This is fundamentally different from function parameters.

### ✅ CORRECT Pattern - Direct Variable Access

```python
# When you pass inputs: {"query": "hello", "threshold": 5}
code = """
# Variables are directly available - no 'inputs' dict!
processed_query = query.upper()  # Direct access to 'query'
if len(processed_query) > threshold:  # Direct access to 'threshold'
    result = {'processed': processed_query, 'valid': True}
else:
    result = {'error': 'Query too short', 'valid': False}
"""
```

### ❌ WRONG Pattern - Dictionary Access

```python
# This will fail - there is no 'inputs' dictionary
code = """
query = inputs.get('query', '')  # NameError: 'inputs' is not defined
threshold = inputs['threshold']   # NameError: 'inputs' is not defined
"""
```

## Available vs Restricted Built-ins

### ✅ Available Built-ins

```python
code = """
# Basic types and functions
items = list(range(10))
filtered = [x for x in items if x > 5]
result = {
    'count': len(filtered),
    'sum': sum(filtered),
    'max': max(filtered) if filtered else None,
    'type': type(filtered).__name__
}
"""
```

### ❌ Restricted Built-ins

```python
code = """
# These will fail - not in allowed builtins
available_vars = dir()        # NameError: 'dir' is not defined
local_vars = locals()         # NameError: 'locals' is not defined
global_vars = globals()       # NameError: 'globals' is not defined
eval('2 + 2')                # NameError: 'eval' is not defined
"""
```

## Output Pattern Requirements

### Rule 1: Always Set 'result' Variable

```python
# ✅ CORRECT
code = """
processed_data = [x * 2 for x in input_list]
result = {'data': processed_data}  # Must set 'result'
"""

# ❌ WRONG
code = """
processed_data = [x * 2 for x in input_list]
# No 'result' variable - outputs will be empty!
"""
```

### Rule 2: Input Variables Are Excluded from Output

```python
# Given inputs: {"data": [1, 2, 3], "multiplier": 2}
code = """
data = [x * multiplier for x in data]  # Modifying input variable
processed = [x + 1 for x in data]       # New variable

# Only 'processed' will be in output, not 'data' or 'multiplier'
result = {'processed': processed}
"""
# Output: {"processed": [3, 5, 7], "result": {"processed": [3, 5, 7]}}
```

### Rule 3: Output Must Be JSON Serializable

```python
# ✅ CORRECT - Converting to serializable formats
code = """
import pandas as pd
import numpy as np

df = pd.DataFrame(data)
arr = np.array([1, 2, 3])

result = {
    'dataframe': df.to_dict('records'),  # Convert DataFrame
    'array': arr.tolist(),               # Convert numpy array
    'mean': float(df['value'].mean())    # Convert numpy scalar
}
"""

# ❌ WRONG - Non-serializable objects
code = """
import pandas as pd
df = pd.DataFrame(data)
result = df  # DataFrame is not JSON serializable!
"""
```

## Common Patterns

### Pattern 1: Conditional Processing

```python
code = """
# Direct variable access with conditional logic
if operation == 'uppercase':
    result = {'text': text.upper()}
elif operation == 'lowercase':
    result = {'text': text.lower()}
else:
    result = {'error': f'Unknown operation: {operation}'}
"""
```

### Pattern 2: Data Transformation

```python
code = """
# Transform list of dictionaries
transformed = []
for item in items:
    transformed.append({
        'id': item.get('id'),
        'value': item.get('value', 0) * scale_factor,
        'label': item.get('name', 'Unknown').upper()
    })

result = {
    'items': transformed,
    'count': len(transformed),
    'total': sum(t['value'] for t in transformed)
}
"""
```

### Pattern 3: Error Handling

```python
code = """
try:
    # Check if required variables exist
    if 'required_param' not in locals():
        raise ValueError('Missing required_param')

    processed = process_data(required_param)
    result = {'success': True, 'data': processed}

except Exception as e:
    result = {'success': False, 'error': str(e)}
"""
```

### Pattern 4: Working with DataFrames

```python
code = """
import pandas as pd

# Create DataFrame from input
df = pd.DataFrame(records)

# Perform operations
df['total'] = df['quantity'] * df['price']
summary = df.groupby('category')['total'].sum()

# Convert to serializable format
result = {
    'records': df.to_dict('records'),
    'summary': summary.to_dict(),
    'stats': {
        'total_revenue': float(df['total'].sum()),
        'avg_price': float(df['price'].mean()),
        'unique_categories': df['category'].nunique()
    }
}
"""
```

### Pattern 5: Using from_function()

```python
def process_data(items: list, threshold: float = 0.5) -> dict:
    """Process items with threshold filtering."""
    filtered = [item for item in items if item['score'] > threshold]
    return {
        'result': {
            'filtered': filtered,
            'count': len(filtered),
            'percentage': len(filtered) / len(items) * 100 if items else 0
        }
    }

# Create node from function
node = PythonCodeNode.from_function(
    name="data_processor",
    func=process_data
)
```

## Connection Patterns

### Avoiding Variable Name Conflicts

```python
# ❌ WRONG - Same variable name causes issues
builder.add_connection("generator", "result", "processor", "result")

# ✅ CORRECT - Different variable names
builder.add_connection("generator", "result", "processor", "input_data")

# In processor node:
code = """
# 'input_data' is available, not 'result'
processed = transform(input_data)
result = {'transformed': processed}
"""
```

### Chaining Transformations

```python
# Node 1: Generate data
code1 = """
data = [{'id': i, 'value': i * 10} for i in range(10)]
result = {'items': data}
"""

# Connection: node1.result -> node2.raw_data
builder.add_connection("node1", "result", "node2", "raw_data")

# Node 2: Process data
code2 = """
# Access nested data using the mapped variable name
items = raw_data.get('items', [])
filtered = [item for item in items if item['value'] > 50]
result = {'filtered_items': filtered}
"""
```

## Debugging Tips

### 1. Check Variable Availability

```python
code = """
# Print available variables for debugging
import json
available = {k: type(v).__name__ for k, v in locals().items()
            if not k.startswith('_')}
print(f"Available variables: {json.dumps(available, indent=2)}")

# Your actual processing
result = {'debug': available}
"""
```

### 2. Safe Variable Access

```python
code = """
# Safely check for optional parameters
if 'optional_param' in locals():
    value = optional_param
else:
    value = 'default'

result = {'value': value}
"""
```

### 3. Type Validation

```python
code = """
# Validate input types
if not isinstance(data, list):
    result = {'error': f'Expected list, got {type(data).__name__}'}
else:
    processed = [str(x).upper() for x in data]
    result = {'processed': processed}
"""
```

## Summary

1. **Variables are injected directly** - no `inputs` dictionary
2. **Restricted builtins** - no `locals()`, `dir()`, `eval()`
3. **Must set `result` variable** for output
4. **Input variables excluded** from output
5. **Output must be JSON serializable**
6. **Use different variable names** in connections to avoid conflicts
