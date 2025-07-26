# Workflow Connection Patterns

*Advanced data flow and routing strategies*

## 🔗 Connection Fundamentals

### Basic Connection Types
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Data source
workflow.add_node("PythonCodeNode", "data_source", {
    "code": "result = {'users': [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]}"
})

# 1. Simple connection (entire result)
workflow.add_node("PythonCodeNode", "simple_processor", {
    "code": "result = {'processed_count': len(input_data.get('users', []))}"
})

workflow.add_connection("data_source", "result", "simple_processor", "input_data")

# 2. Nested field access with dot notation
workflow.add_node("PythonCodeNode", "users_processor", {
    "code": "result = {'user_names': [u['name'] for u in input_data]}"
})

workflow.add_connection("data_source", "result.users", "users_processor", "input_data")
```

### Multiple Input Connections
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

# Multiple connections to same node with different input names
workflow.add_connection("user_source", "result", "combiner", "users")
workflow.add_connection("score_source", "result", "combiner", "scores")
```

## 🔀 Advanced Routing Patterns

### Fan-Out (One-to-Many)
```python
workflow = WorkflowBuilder()

# Single data source
workflow.add_node("PythonCodeNode", "data_source", {
    "code": "result = [{'name': 'Alice', 'score': 95}, {'name': 'Bob', 'score': 72}]"
})

# Multiple processors for different purposes
workflow.add_node("PythonCodeNode", "high_score_processor", {
    "code": '''
high_scorers = [item for item in input_data if item.get('score', 0) >= 90]
result = {'high_performers': high_scorers, 'category': 'excellent'}
'''
})

workflow.add_node("PythonCodeNode", "name_processor", {
    "code": '''
names = [item['name'] for item in input_data if 'name' in item]
result = {'all_names': names, 'name_count': len(names)}
'''
})

workflow.add_node("PythonCodeNode", "stats_processor", {
    "code": '''
scores = [item.get('score', 0) for item in input_data]
result = {
    'avg_score': sum(scores) / len(scores) if scores else 0,
    'max_score': max(scores) if scores else 0,
    'min_score': min(scores) if scores else 0
}
'''
})

# Fan-out: same source to multiple processors
workflow.add_connection("data_source", "result", "high_score_processor", "input_data")
workflow.add_connection("data_source", "result", "name_processor", "input_data")
workflow.add_connection("data_source", "result", "stats_processor", "input_data")
```

### Fan-In (Many-to-One)
```python
workflow = WorkflowBuilder()

# Multiple data sources
workflow.add_node("PythonCodeNode", "sales_data", {
    "code": "result = [{'region': 'North', 'amount': 1000}, {'region': 'South', 'amount': 1500}]"
})

workflow.add_node("PythonCodeNode", "marketing_data", {
    "code": "result = [{'campaign': 'A', 'spend': 500}, {'campaign': 'B', 'spend': 800}]"
})

workflow.add_node("PythonCodeNode", "customer_data", {
    "code": "result = [{'segment': 'Premium', 'count': 100}, {'segment': 'Standard', 'count': 300}]"
})

# Aggregator that combines all sources
workflow.add_node("PythonCodeNode", "aggregator", {
    "code": '''
# Calculate totals from different data sources
total_sales = sum(item['amount'] for item in sales_data)
total_marketing = sum(item['spend'] for item in marketing_data)
total_customers = sum(item['count'] for item in customer_data)

result = {
    'total_sales': total_sales,
    'total_marketing_spend': total_marketing,
    'total_customers': total_customers,
    'roi': (total_sales - total_marketing) / total_marketing if total_marketing > 0 else 0
}
'''
})

# Fan-in: multiple sources to one aggregator
workflow.add_connection("sales_data", "result", "aggregator", "sales_data")
workflow.add_connection("marketing_data", "result", "aggregator", "marketing_data")
workflow.add_connection("customer_data", "result", "aggregator", "customer_data")
```

## 🔄 Data Transformation Chains

### Sequential Processing
```python
workflow = WorkflowBuilder()

# Raw data
workflow.add_node("PythonCodeNode", "raw_data", {
    "code": "result = [10, 20, 30, 40, 50, 5, 15, 25]"
})

# Step 1: Filter
workflow.add_node("PythonCodeNode", "filter_step", {
    "code": '''
filtered = [x for x in input_data if x > 15]
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

# Step 3: Sort
workflow.add_node("PythonCodeNode", "sort_step", {
    "code": '''
sorted_data = sorted(input_data, reverse=True)
result = sorted_data
'''
})

# Step 4: Aggregate
workflow.add_node("PythonCodeNode", "aggregate_step", {
    "code": '''
total = sum(input_data)
average = total / len(input_data) if input_data else 0
result = {
    'total': total,
    'average': average,
    'count': len(input_data),
    'max': max(input_data) if input_data else 0
}
'''
})

# Chain connections
workflow.add_connection("raw_data", "result", "filter_step", "input_data")
workflow.add_connection("filter_step", "result", "transform_step", "input_data")
workflow.add_connection("transform_step", "result", "sort_step", "input_data")
workflow.add_connection("sort_step", "result", "aggregate_step", "input_data")
```

### Parallel Processing with Merge
```python
workflow = WorkflowBuilder()

# Data source
workflow.add_node("PythonCodeNode", "data_source", {
    "code": "result = [{'value': 10}, {'value': 20}, {'value': 30}]"
})

# Parallel branch 1: Statistical analysis
workflow.add_node("PythonCodeNode", "stats_analyzer", {
    "code": '''
values = [item['value'] for item in input_data]
result = {
    'mean': sum(values) / len(values),
    'max': max(values),
    'min': min(values)
}
'''
})

# Parallel branch 2: Value transformation
workflow.add_node("PythonCodeNode", "value_transformer", {
    "code": '''
transformed = [{'original': item['value'], 'doubled': item['value'] * 2} for item in input_data]
result = {'transformed_values': transformed}
'''
})

# Merge results
workflow.add_node("PythonCodeNode", "merger", {
    "code": '''
# Combine results from both branches
merged_result = {
    'statistics': stats,
    'transformations': transformations,
    'analysis_complete': True
}
result = merged_result
'''
})

# Parallel connections
workflow.add_connection("data_source", "result", "stats_analyzer", "input_data")
workflow.add_connection("data_source", "result", "value_transformer", "input_data")

# Merge connections
workflow.add_connection("stats_analyzer", "result", "merger", "stats")
workflow.add_connection("value_transformer", "result", "merger", "transformations")
```

## 🎯 Conditional Routing

### Score-Based Routing
```python
workflow = WorkflowBuilder()

# Data with scores
workflow.add_node("PythonCodeNode", "scored_data", {
    "code": '''
result = [
    {'name': 'Alice', 'score': 95},
    {'name': 'Bob', 'score': 72},
    {'name': 'Charlie', 'score': 88},
    {'name': 'Diana', 'score': 45}
]
'''
})

# Router that categorizes by score
workflow.add_node("PythonCodeNode", "score_router", {
    "code": '''
high_scorers = [item for item in input_data if item.get('score', 0) >= 90]
medium_scorers = [item for item in input_data if 70 <= item.get('score', 0) < 90]
low_scorers = [item for item in input_data if item.get('score', 0) < 70]

result = {
    'high': high_scorers,
    'medium': medium_scorers,
    'low': low_scorers
}
'''
})

# Specialized processors
workflow.add_node("PythonCodeNode", "high_processor", {
    "code": '''
result = {
    'message': f'Excellent performance: {len(input_data)} high performers',
    'reward': 'bonus',
    'performers': input_data
}
'''
})

workflow.add_node("PythonCodeNode", "medium_processor", {
    "code": '''
result = {
    'message': f'Good performance: {len(input_data)} medium performers',
    'action': 'recognition',
    'performers': input_data
}
'''
})

workflow.add_node("PythonCodeNode", "low_processor", {
    "code": '''
result = {
    'message': f'Needs improvement: {len(input_data)} low performers',
    'action': 'coaching',
    'performers': input_data
}
'''
})

# Route to specialized processors
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
```

## ✅ Connection Best Practices

### Clear Data Flow
```python
# ✅ GOOD: Descriptive connection mapping
workflow.add_connection("user_reader", "result", "validator", "raw_users")
workflow.add_connection("validator", "validated_users", "enricher", "clean_users")
workflow.add_connection("enricher", "enriched_data", "writer", "output_data")

# ❌ AVOID: Generic parameter names
# workflow.add_connection("node1", "result", "node2", "input_data")
# workflow.add_connection("node2", "result", "node3", "input_data")
```

### Error-Safe Connections
```python
workflow.add_node("PythonCodeNode", "safe_processor", {
    "code": '''
# Defensive programming for connections
input_data = input_data if 'input_data' in globals() else []

if not input_data:
    result = {'error': 'No input data received', 'success': False}
elif not isinstance(input_data, list):
    result = {'error': 'Expected list input', 'success': False}
else:
    try:
        processed = [x * 2 for x in input_data if isinstance(x, (int, float))]
        result = {'processed': processed, 'success': True}
    except Exception as e:
        result = {'error': str(e), 'success': False}
'''
})
```

## 🔗 Next Steps
- [PythonCodeNode Patterns](02-workflows-python-code.md) - Advanced processing
- [Workflow Execution](02-workflows-execution.md) - Runtime optimization
- [Cyclic Workflows](02-workflows-cycles.md) - Iterative processing
