# Node Connections & Data Flow

*Advanced connection patterns and data routing*

## 🔗 Basic Connection Patterns

### Simple Connections
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Data source
workflow.add_node("PythonCodeNode", "source", {
    "code": "result = {'items': [1, 2, 3, 4, 5], 'count': 5}"
})

# Processor
workflow.add_node("PythonCodeNode", "processor", {
    "code": '''
items = input_data.get('items', [])
doubled = [x * 2 for x in items]
result = {'doubled_items': doubled}
'''
})

# Simple connection (passes entire result)
workflow.add_connection("source", "result", "processor", "input_data")
```

### Nested Data Access
```python
workflow = WorkflowBuilder()

# Complex data source
workflow.add_node("PythonCodeNode", "complex_source", {
    "code": '''
result = {
    'users': [
        {'name': 'Alice', 'scores': [95, 87, 92]},
        {'name': 'Bob', 'scores': [78, 89, 84]}
    ],
    'metadata': {'total_users': 2}
}
'''
})

# Access specific nested fields
workflow.add_node("PythonCodeNode", "score_analyzer", {
    "code": '''
total_users = input_data
avg_scores = []
for user in users:
    avg = sum(user['scores']) / len(user['scores'])
    avg_scores.append({'name': user['name'], 'average': avg})
result = {'averages': avg_scores}
'''
})

# Connect with dot notation
workflow.add_connection("complex_source", "result.users", "score_analyzer", "users")
workflow.add_connection("complex_source", "result.metadata.total_users", "score_analyzer", "input_data")
```

## 🔀 Advanced Routing Patterns

### Multiple Input Sources
```python
workflow = WorkflowBuilder()

# Source 1: User data
workflow.add_node("PythonCodeNode", "user_source", {
    "code": "result = [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]"
})

# Source 2: Score data
workflow.add_node("PythonCodeNode", "score_source", {
    "code": "result = [{'user_id': 1, 'score': 95}, {'user_id': 2, 'score': 87}]"
})

# Combiner with multiple inputs
workflow.add_node("PythonCodeNode", "combiner", {
    "code": '''
# Combine users and scores
combined = []
for user in users:
    user_scores = [s for s in scores if s['user_id'] == user['id']]
    if user_scores:
        combined.append({
            'name': user['name'],
            'score': user_scores[0]['score']
        })
result = {'combined_data': combined}
'''
})

# Multiple connections to same node
workflow.add_connection("user_source", "result", "combiner", "users")
workflow.add_connection("score_source", "result", "combiner", "scores")
```

### Conditional Routing
```python
workflow = WorkflowBuilder()

# Data with scores
workflow.add_node("PythonCodeNode", "scored_data", {
    "code": "result = [{'name': 'Alice', 'score': 95}, {'name': 'Bob', 'score': 72}]"
})

# Route to different processors based on score
workflow.add_node("PythonCodeNode", "high_score_processor", {
    "code": '''
high_scorers = [item for item in input_data if item.get('score', 0) >= 90]
result = {'high_performers': high_scorers, 'category': 'excellent'}
'''
})

workflow.add_node("PythonCodeNode", "regular_processor", {
    "code": '''
regular_scorers = [item for item in input_data if item.get('score', 0) < 90]
result = {'regular_performers': regular_scorers, 'category': 'good'}
'''
})

# Same source to multiple processors
workflow.add_connection("scored_data", "result", "high_score_processor", "input_data")
workflow.add_connection("scored_data", "result", "regular_processor", "input_data")
```

## 🔄 Data Transformation Patterns

### Chain Processing
```python
workflow = WorkflowBuilder()

# Raw data
workflow.add_node("PythonCodeNode", "raw_data", {
    "code": "result = [10, 20, 30, 40, 50]"
})

# Step 1: Filter
workflow.add_node("PythonCodeNode", "filter_step", {
    "code": '''
filtered = [x for x in input_data if x > 25]
result = filtered
'''
})

# Step 2: Transform
workflow.add_node("PythonCodeNode", "transform_step", {
    "code": '''
transformed = [x * 2 for x in input_data]
result = transformed
'''
})

# Step 3: Aggregate
workflow.add_node("PythonCodeNode", "aggregate_step", {
    "code": '''
total = sum(input_data)
average = total / len(input_data) if input_data else 0
result = {'total': total, 'average': average, 'count': len(input_data)}
'''
})

# Chain connections
workflow.add_connection("raw_data", "result", "filter_step", "input_data")
workflow.add_connection("filter_step", "result", "transform_step", "input_data")
workflow.add_connection("transform_step", "result", "aggregate_step", "input_data")
```

## ✅ Connection Best Practices

### Clear Data Flow
```python
# ✅ GOOD: Clear, descriptive connections
workflow.add_connection("user_reader", "result", "validator", "users")
workflow.add_connection("validator", "validated_users", "processor", "input_data")

# ❌ AVOID: Unclear data flow
# workflow.add_connection("node1", "result", "node2", "input_data")
# workflow.add_connection("node2", "result", "node3", "input_data")
```

### Error Handling
```python
workflow.add_node("PythonCodeNode", "safe_processor", {
    "code": '''
try:
    if not input_data:
        result = {'error': 'No input data received', 'success': False}
    else:
        processed = [x * 2 for x in input_data if isinstance(x, (int, float))]
        result = {'processed': processed, 'success': True}
except Exception as e:
    result = {'error': str(e), 'success': False}
'''
})
```

## 🔗 Next Steps
- [Best Practices](01-fundamentals-best-practices.md) - Code organization
- [Workflows Guide](02-workflows.md) - Complete workflow patterns
