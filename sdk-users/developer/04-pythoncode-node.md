# PythonCodeNode Patterns and Pitfalls

## 🚀 Best Practice: Use `.from_function()` for Better Developer Experience

**STRONGLY RECOMMENDED**: For any non-trivial code (more than 3-5 lines), use the `.from_function()` method instead of string code blocks.

### Why `.from_function()` is Superior

1. **IDE Support**: Full syntax highlighting, auto-completion, and type hints
2. **Error Detection**: Immediate syntax and type errors in your IDE
3. **Debugging**: Set breakpoints and step through code
4. **Refactoring**: Use IDE refactoring tools safely
5. **Testing**: Functions can be unit tested independently
6. **Readability**: Clean, maintainable code structure

### Quick Comparison

❌ **AVOID** - String-based code (no IDE support):
```python
node = PythonCodeNode(
    name="processor",
    code="""
def process_data(data):
    # No syntax highlighting here!
    # No auto-completion!
    # No type checking!
    result = []
    for item in data:
        if item['value'] > 100:  # Hope the key exists!
            result.append(item)
    return {'filtered': result}
"""
)
```

✅ **PREFERRED** - Function-based (full IDE support):
```python
def process_data(data: list) -> dict:
    """Process data with full IDE support."""
    # Full syntax highlighting!
    # Auto-completion works!
    # Type hints validated!
    result = []
    for item in data:
        if item.get('value', 0) > 100:  # IDE shows available methods
            result.append(item)
    return {'filtered': result}

# Create node from function
node = PythonCodeNode.from_function(
    func=process_data,
    name="data_processor",
    description="Filter high-value items"
)
```

## When to Use String Code vs `.from_function()`

### Use `.from_function()` (Default Choice) When:
- **Complex Logic**: More than 3-5 lines of code
- **IDE Support Needed**: Want syntax highlighting, auto-completion, debugging
- **Testing Required**: Function needs unit testing
- **Reusable Code**: Logic will be used elsewhere
- **Type Safety**: Want type hints and validation

### Use String Code When:

#### 1. **Dynamic Code Generation**
```python
# Code must be constructed at runtime
def create_filter_node(field: str, operator: str, value: Any):
    code = f"result = [x for x in input_data if x['{field}'] {operator} {value}]"
    return PythonCodeNode(name=f"filter_{field}", code=code)
```

#### 2. **User-Provided Code**
```python
# Code comes from users via UI/API/config
user_code = load_user_transformation(user_id)
node = PythonCodeNode(name="user_transform", code=user_code)
```

#### 3. **Workflow Runtime Variables**
```python
# Accessing variables only available during execution
node = PythonCodeNode(
    name="runtime_context",
    code="""
# These are injected by workflow runtime
result = {
    'run_id': workflow_run_id,
    'timestamp': workflow_start_time,
    'previous_outputs': accumulated_results
}
"""
)
```

#### 4. **Template-Based Generation**
```python
# Using code templates with placeholders
QUERY_TEMPLATE = "result = df[df['{col}'].{method}()].to_dict('records')"
node = PythonCodeNode(
    name="query",
    code=QUERY_TEMPLATE.format(col=column, method=aggregation)
)
```

#### 5. **Workflow Serialization**
```python
# Loading from database/file storage
stored_workflow = load_from_db(workflow_id)
node = PythonCodeNode(
    name=stored_workflow['node_name'],
    code=stored_workflow['node_code']  # Stored as string
)
```

#### 6. **Simple One-Liners**
```python
# Truly trivial operations
node = PythonCodeNode(name="add_tax", code="result = input_value * 1.08")
```

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

## 🔄 Output Handling (Framework Update)

**Important**: As of the latest framework version, all PythonCodeNode outputs are consistently wrapped in a `"result"` key, regardless of whether your function returns a dict, list, or other type.

### Consistent Behavior
```python
# Function returning a simple value
def simple_func(x):
    return x * 2

# Function returning a dict
def dict_func(data):
    return {"processed": data, "count": len(data)}

# Both are wrapped consistently in {"result": ...}
node1 = PythonCodeNode.from_function(func=simple_func)  # Output: {"result": 42}
node2 = PythonCodeNode.from_function(func=dict_func)    # Output: {"result": {"processed": [...], "count": 5}}
```

### Connection Patterns
```python
# Always connect using "result" key
workflow.connect("node1", "node2", {"result": "input_data"})
workflow.connect("node2", "node3", {"result": "processed_data"})
```

### Backward Compatibility
- Existing workflows continue to work unchanged
- String-based code nodes work as before
- Only affects the internal wrapping logic for consistency

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

## Functions Must Be Defined in Scope

### The Problem: External Function References
```python
# ❌ WRONG: Function defined outside node's scope
def calculate_payment(principal, rate, months):
    monthly_rate = rate / 12
    if monthly_rate == 0:
        return principal / months
    payment = principal * (monthly_rate * (1 + monthly_rate)**months) / ((1 + monthly_rate)**months - 1)
    return round(payment, 2)

# This won't work - calculate_payment not available in code string
node = PythonCodeNode(
    name="processor",
    code="payment = calculate_payment(amount, rate, 36)"  # NameError!
)
```

### Solution 1: Use .from_function() (PREFERRED for >3 lines)
```python
# ✅ BEST: Use from_function for complex logic
def process_loan_application(application_data: dict) -> dict:
    """Process loan with payment calculation."""

    def calculate_payment(principal, rate, months):
        monthly_rate = rate / 12
        if monthly_rate == 0:
            return principal / months
        payment = principal * (monthly_rate * (1 + monthly_rate)**months) / ((1 + monthly_rate)**months - 1)
        return round(payment, 2)

    amount = application_data['amount']
    rate = application_data['interest_rate']
    terms = application_data.get('terms_months', 36)

    monthly_payment = calculate_payment(amount, rate, terms)

    return {
        'approved_amount': amount,
        'monthly_payment': monthly_payment,
        'total_cost': monthly_payment * terms
    }

# Create node from function
node = PythonCodeNode.from_function(
    func=process_loan_application,
    name="loan_processor",
    description="Calculate loan terms and payments"
)
```

### Solution 2: Inline Simple Calculations
```python
# ✅ OK: For truly simple calculations, inline the logic
node = PythonCodeNode(
    name="simple_calc",
    code="result = {'payment': (amount * rate * (1 + rate)**months) / ((1 + rate)**months - 1)}"
)
```

### Why This Matters
- **Scope Isolation**: PythonCodeNode executes in isolated namespace
- **No Global Access**: Can't access functions defined outside
- **Best Practice**: Use .from_function() for any non-trivial logic

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
