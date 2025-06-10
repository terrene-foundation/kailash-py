# PythonCodeNode Patterns and Pitfalls

## ⚠️ Critical: Input Variable Exclusion

**The most important thing to know**: PythonCodeNode excludes input variables from its outputs to prevent circular references.

### The Problem

```python
# WRONG: This will fail with "Required output 'result' not provided"
workflow.connect("node1", "node2", mapping={"result": "result"})

# In node2's PythonCodeNode:
node2 = PythonCodeNode(
    name="processor",
    code="""
# result is available as input
print(result)  # Works fine

# But reassigning result won't work!
result = {"processed": True}  # This won't be in output!
"""
)
```

### The Solution

```python
# CORRECT: Map to different variable names
workflow.connect("node1", "node2", mapping={"result": "input_data"})

# In node2's PythonCodeNode:
node2 = PythonCodeNode(
    name="processor",
    code="""
# input_data is available as input
data = input_data.get("value")

# Now result is a NEW variable, will be in output
result = {"processed": data}
"""
)
```

## Common Patterns

### Pattern 1: Processing Pipeline
```python
# Stage 1: Discovery
discoverer = PythonCodeNode(
    name="discoverer",
    code="result = {'files': ['a.csv', 'b.json']}"
)

# Stage 2: Processing (CORRECT)
workflow.connect("discoverer", "processor", mapping={"result": "discovery_data"})
processor = PythonCodeNode(
    name="processor",
    code="""
files = discovery_data.get('files', [])
result = {'processed_count': len(files)}
"""
)
```

### Pattern 2: Data Transformation
```python
# WRONG: Same variable name
workflow.connect("reader", "transformer", mapping={"data": "data"})

# CORRECT: Descriptive names
workflow.connect("reader", "transformer", mapping={"data": "raw_data"})
transformer = PythonCodeNode(
    name="transformer",
    code="""
# Transform raw_data
cleaned = [x.strip() for x in raw_data]
result = {'cleaned_data': cleaned}
"""
)
```

### Pattern 3: Multi-Stage Processing
```python
# Use stage-specific names
workflow.connect("stage1", "stage2", mapping={"result": "stage1_output"})
workflow.connect("stage2", "stage3", mapping={"result": "stage2_output"})
```

## Data Serialization

### DataFrame Handling
```python
# WRONG: DataFrame not JSON serializable
code = """
import pandas as pd
df = pd.DataFrame(data)
result = {'dataframe': df}  # Will fail!
"""

# CORRECT: Convert to serializable format
code = """
import pandas as pd
df = pd.DataFrame(data)
result = {
    'data': df.to_dict('records'),
    'columns': df.columns.tolist(),
    'shape': list(df.shape)
}
"""
```

### NumPy Arrays
```python
# WRONG: ndarray not serializable
code = """
import numpy as np
arr = np.array([1, 2, 3])
result = {'array': arr}  # Will fail!
"""

# CORRECT: Convert to list
code = """
import numpy as np
arr = np.array([1, 2, 3])
result = {'array': arr.tolist()}
"""
```

## Memory Management

### Large Data Processing
```python
# Process in chunks to avoid memory issues
processor = PythonCodeNode(
    name="chunk_processor",
    code="""
CHUNK_SIZE = 1000
processed = []

for i in range(0, len(input_data), CHUNK_SIZE):
    chunk = input_data[i:i+CHUNK_SIZE]
    # Process chunk
    processed.extend(process_chunk(chunk))

result = {'processed': processed}
"""
)
```

## Security Considerations

### Input Validation
```python
# Always validate inputs
safe_processor = PythonCodeNode(
    name="safe_processor",
    code="""
# Validate input types
if not isinstance(input_data, dict):
    result = {'error': 'Invalid input type'}
else:
    # Safe processing
    value = input_data.get('value', 0)
    if isinstance(value, (int, float)):
        result = {'doubled': value * 2}
    else:
        result = {'error': 'Value must be numeric'}
"""
)
```

## Best Practices

1. **Use descriptive variable names** for mappings:
   - Good: `csv_data`, `api_response`, `processed_results`
   - Bad: `data`, `result`, `output`

2. **Always include the name parameter**:
   ```python
   PythonCodeNode(name="processor", code="...")  # ✓
   PythonCodeNode(code="...")  # ✗ Will fail
   ```

3. **Handle missing inputs gracefully**:
   ```python
   code = """
   # Use .get() with defaults
   value = input_data.get('value', 0)
   items = input_data.get('items', [])
   """
   ```

4. **Document your mappings**:
   ```python
   # Map discovery results to 'files_found' variable
   workflow.connect("scanner", "processor", 
                   mapping={"discovered_files": "files_found"})
   ```

## Common Errors

### "Required output 'result' not provided"
**Cause**: Variable was an input, excluded from outputs
**Fix**: Map to different variable name

### "Object of type DataFrame is not JSON serializable"
**Fix**: Use `.to_dict('records')` or `.tolist()`

### "NameError: name 'X' is not defined"
**Cause**: Expected input not provided in mapping
**Fix**: Check workflow connections and mappings

## When to Use PythonCodeNode

**Good Use Cases:**
- Complex calculations
- Data transformations
- Custom business logic
- Integration glue code

**Better Alternatives:**
- CSV files → `CSVReaderNode`
- JSON files → `JSONReaderNode`
- File discovery → `DirectoryReaderNode`
- Simple transforms → `DataTransformer`