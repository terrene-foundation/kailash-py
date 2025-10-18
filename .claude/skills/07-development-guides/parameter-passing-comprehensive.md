# Parameter Passing Comprehensive

You are an expert in comprehensive parameter passing patterns for Kailash SDK. This is the complete enterprise guide, not the quick reference.

## Source Documentation
- `./sdk-users/7-gold-standards/parameter_passing_comprehensive.md`

## Core Responsibilities

### 1. Three Ways to Pass Parameters

**1. Static Parameters (Design Time)**
```python
workflow.add_node("HTTPRequestNode", "api_call", {
    "url": "https://api.example.com",  # Static
    "method": "GET"
})
```

**2. Dynamic Parameters (Runtime)**
```python
runtime.execute(workflow.build(), parameters={
    "api_call": {"url": "https://different-api.com"}  # Override at runtime
})
```

**3. Connection-Based (Data Flow)**
```python
workflow.add_connection("source", "target", "output_key", "input_key")
# Data flows from source output to target input
```

### 2. Parameter Priority
```
Connection-based > Dynamic > Static
(Highest priority)     (Lowest priority)
```

### 3. Environment Variables
```python
workflow.add_node("HTTPRequestNode", "api_call", {
    "url": "${API_URL}",  # References $API_URL from environment
    "headers": {
        "Authorization": "Bearer ${API_TOKEN}"
    }
})
```

### 4. Complex Parameter Patterns
```python
# Nested parameters
workflow.add_node("PythonCodeNode", "complex", {
    "code": """
config = {
    'database': {
        'host': os.getenv('DB_HOST'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'credentials': {
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD')
        }
    }
}

result = {'config': config}
"""
})
```

### 5. Parameter Validation
```python
workflow.add_node("PythonCodeNode", "validator", {
    "code": """
# Validate parameters
required = ['api_url', 'api_key', 'data']
missing = [p for p in required if p not in locals()]

if missing:
    raise ValueError(f"Missing required parameters: {missing}")

# Type validation
if not isinstance(data, dict):
    raise TypeError("data must be a dictionary")

result = {'validated': True}
"""
})
```

### 6. Default Parameters
```python
workflow.add_node("PythonCodeNode", "with_defaults", {
    "code": """
# Use defaults for missing parameters
timeout = locals().get('timeout', 30)
retries = locals().get('retries', 3)
batch_size = locals().get('batch_size', 100)

result = {
    'timeout': timeout,
    'retries': retries,
    'batch_size': batch_size
}
"""
})
```

### 7. Parameter Transformation
```python
workflow.add_node("PythonCodeNode", "transform_params", {
    "code": """
# Transform parameters before use
api_url = base_url.rstrip('/') + '/api/v1/endpoint'
headers = {
    'Authorization': f'Bearer {api_token}',
    'Content-Type': 'application/json',
    'X-Custom-Header': custom_value
}

result = {'url': api_url, 'headers': headers}
"""
})
```

### 8. Batch Parameter Passing
```python
workflow.add_node("PythonCodeNode", "batch_processor", {
    "code": """
# Process batch of items with parameters
items = input_items
batch_size = locals().get('batch_size', 100)

results = []
for i in range(0, len(items), batch_size):
    batch = items[i:i+batch_size]
    batch_result = process_batch(batch, **processing_params)
    results.extend(batch_result)

result = {'results': results, 'total': len(results)}
"""
})
```

## When to Engage
- User asks about "parameter passing guide", "comprehensive parameters", "enterprise parameters"
- User has complex parameter needs
- User needs parameter validation
- User wants parameter best practices

## Integration with Other Skills
- Route to **sdk-fundamentals** for basic concepts
- Route to **workflow-creation-guide** for workflow building
- Route to **advanced-features** for advanced patterns
