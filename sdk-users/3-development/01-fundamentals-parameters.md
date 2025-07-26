# Parameter Types & Data Flow

*Understanding parameter constraints and data flow*

## 🔧 Supported Parameter Types

### Basic Types
```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# String parameters
workflow.add_node("PythonCodeNode", "string_processor", {
    "code": "result = {'message': f'Hello {name}'}"
})

# Numeric parameters
workflow.add_node("PythonCodeNode", "math_processor", {
    "code": "result = {'sum': value1 + value2, 'product': value1 * value2}"
})

# Boolean parameters
workflow.add_node("PythonCodeNode", "conditional", {
    "code": '''
if enabled:
    result = {'status': 'processing enabled'}
else:
    result = {'status': 'processing disabled'}
'''
})

# List/Dict parameters
workflow.add_node("PythonCodeNode", "collection_processor", {
    "code": '''
total = sum(numbers)
result = {'total': total, 'config': settings}
'''
})
```

### Complex Data Structures
```python
workflow = WorkflowBuilder()

# Nested data access
workflow.add_node("PythonCodeNode", "data_source", {
    "code": '''
result = {
    'users': [
        {'id': 1, 'name': 'Alice', 'metrics': {'score': 95}},
        {'id': 2, 'name': 'Bob', 'metrics': {'score': 87}}
    ],
    'metadata': {'total_count': 2}
}
'''
})

# Access nested fields
workflow.add_node("PythonCodeNode", "analyzer", {
    "code": '''
users = input_data.get('users', [])
high_scores = [u for u in users if u.get('metrics', {}).get('score', 0) > 90]
result = {'high_performers': high_scores}
'''
})

workflow.add_connection("data_source", "result", "analyzer", "input_data")
```

## ❌ Invalid Parameter Types

### Never Use These
```python
# ❌ WRONG: Functions as parameters
# workflow.add_node("PythonCodeNode", "bad", {
#     "code": lambda x: x * 2  # Functions not serializable
# })

# ❌ WRONG: Complex objects
# workflow.add_node("PythonCodeNode", "bad", {
#     "code": some_class_instance  # Objects not serializable
# })

# ❌ WRONG: File handles
# workflow.add_node("PythonCodeNode", "bad", {
#     "file_handle": open("file.txt")  # File handles not serializable
# })
```

### Use This Instead
```python
# ✅ CORRECT: String code with file paths
workflow.add_node("PythonCodeNode", "file_processor", {
    "code": '''
with open("/path/to/file.txt", "r") as f:
    content = f.read()
result = {'content': content, 'lines': len(content.split())}
'''
})
```

## 🔗 Parameter Validation

### Runtime Validation
```python
workflow = WorkflowBuilder()

workflow.add_node("PythonCodeNode", "validator", {
    "code": '''
# Validate inputs
if not isinstance(input_data, list):
    result = {'error': 'Expected list input', 'valid': False}
elif len(input_data) == 0:
    result = {'error': 'Empty list not allowed', 'valid': False}
else:
    processed = [item * 2 for item in input_data if isinstance(item, (int, float))]
    result = {'processed': processed, 'valid': True}
'''
})
```

## ✅ Key Rules
- Use serializable types only (str, int, float, bool, list, dict)
- Validate inputs in PythonCodeNode code
- Handle edge cases (empty lists, None values)
- Use clear parameter names

## 🔗 Next Steps
- [Node Connections](01-fundamentals-connections.md) - Advanced data flow
- [Best Practices](01-fundamentals-best-practices.md) - Error handling
