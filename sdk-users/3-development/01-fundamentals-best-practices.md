# Best Practices & Code Organization

*Essential patterns for maintainable workflows*

## 📊 Node Naming Conventions

### Descriptive Names
```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# ✅ GOOD: Clear, descriptive node names
workflow.add_node("CSVReaderNode", "user_data_reader", {
    "file_path": "users.csv"
})

workflow.add_node("PythonCodeNode", "email_validator", {
    "code": '''
valid_emails = []
for user in input_data:
    email = user.get('email', '')
    if '@' in email and '.' in email:
        valid_emails.append(user)
result = {'valid_users': valid_emails}
'''
})

workflow.add_node("JSONWriterNode", "validated_output", {
    "file_path": "validated_users.json"
})

# ❌ AVOID: Generic, unclear names
# workflow.add_node("CSVReaderNode", "reader", {...})
# workflow.add_node("PythonCodeNode", "processor", {...})
# workflow.add_node("JSONWriterNode", "writer", {...})
```

### Consistent Patterns
```python
# ✅ GOOD: Consistent naming pattern
workflow.add_node("CSVReaderNode", "sales_data_reader", {...})
workflow.add_node("PythonCodeNode", "sales_data_validator", {...})
workflow.add_node("PythonCodeNode", "sales_data_aggregator", {...})
workflow.add_node("JSONWriterNode", "sales_report_writer", {...})

# Data flow pattern: [source]_[operation]_[target]
workflow.add_node("PythonCodeNode", "user_score_calculator", {...})
workflow.add_node("PythonCodeNode", "score_trend_analyzer", {...})
```

## 🔧 Parameter Organization

### Configuration vs Runtime Data
```python
workflow = WorkflowBuilder()

# ✅ GOOD: Configuration in node setup
workflow.add_node("PythonCodeNode", "data_processor", {
    "code": '''
# Configuration values embedded in code
THRESHOLD = 0.8
MAX_ITEMS = 100

# Process runtime data
filtered = [item for item in input_data if item.get('score', 0) > THRESHOLD]
limited = filtered[:MAX_ITEMS]
result = {'processed_items': limited, 'total_processed': len(limited)}
'''
})

# ✅ GOOD: Runtime data through connections
workflow.add_connection("data_source", "result", "data_processor", "input_data")
```

### Environment-Specific Settings
```python
import os

# ✅ GOOD: Environment variables for deployment settings
workflow.add_node("PythonCodeNode", "api_client", {
    "code": f'''
import os
API_URL = os.getenv('API_URL', 'https://api.example.com')
API_KEY = os.getenv('API_KEY', 'default-key')

# Use environment settings
result = {{'api_url': API_URL, 'configured': True}}
'''
})
```

## 🛡️ Error Handling Patterns

### Defensive Programming
```python
workflow.add_node("PythonCodeNode", "robust_processor", {
    "code": '''
# Validate inputs
if not input_data:
    result = {'error': 'No input data provided', 'success': False}
elif not isinstance(input_data, list):
    result = {'error': 'Expected list input', 'success': False}
else:
    try:
        # Safe processing
        processed = []
        for item in input_data:
            if isinstance(item, dict) and 'value' in item:
                processed.append(item['value'] * 2)
            else:
                # Skip invalid items rather than failing
                continue

        result = {
            'processed': processed,
            'success': True,
            'processed_count': len(processed),
            'skipped_count': len(input_data) - len(processed)
        }
    except Exception as e:
        result = {'error': f'Processing failed: {str(e)}', 'success': False}
'''
})
```

### Graceful Degradation
```python
workflow.add_node("PythonCodeNode", "graceful_processor", {
    "code": '''
# Attempt primary processing, fall back if needed
try:
    # Try complex processing
    result = complex_algorithm(input_data)
except Exception as primary_error:
    try:
        # Fall back to simple processing
        result = {'fallback_result': simple_algorithm(input_data), 'fallback_used': True}
    except Exception as fallback_error:
        # Last resort: return error info
        result = {
            'error': f'All processing failed. Primary: {primary_error}, Fallback: {fallback_error}',
            'success': False
        }

def complex_algorithm(data):
    # Complex processing logic
    return {'advanced_result': [x ** 2 for x in data]}

def simple_algorithm(data):
    # Simple fallback
    return [x * 2 for x in data if isinstance(x, (int, float))]
'''
})
```

## 📋 Code Organization

### Modular Code Blocks
```python
# ✅ GOOD: Break complex logic into functions
workflow.add_node("PythonCodeNode", "modular_processor", {
    "code": '''
def validate_user(user):
    """Validate user data structure"""
    required_fields = ['id', 'name', 'email']
    return all(field in user for field in required_fields)

def calculate_score(user):
    """Calculate user score from metrics"""
    metrics = user.get('metrics', {})
    return sum(metrics.values()) / len(metrics) if metrics else 0

def process_users(users):
    """Main processing logic"""
    valid_users = [user for user in users if validate_user(user)]
    scored_users = []

    for user in valid_users:
        score = calculate_score(user)
        scored_users.append({
            'id': user['id'],
            'name': user['name'],
            'score': score
        })

    return scored_users

# Execute main logic
processed = process_users(input_data)
result = {'processed_users': processed, 'count': len(processed)}
'''
})
```

### Documentation in Code
```python
workflow.add_node("PythonCodeNode", "documented_processor", {
    "code": '''
"""
Process sales data and calculate monthly trends.
Input: List of sales records with date, amount, product_id
Output: Monthly aggregation with trends
"""

# Group sales by month
monthly_sales = {}
for sale in input_data:
    month = sale.get('date', '')[:7]  # YYYY-MM format
    if month not in monthly_sales:
        monthly_sales[month] = []
    monthly_sales[month].append(sale.get('amount', 0))

# Calculate monthly totals and trends
monthly_totals = {}
for month, amounts in monthly_sales.items():
    monthly_totals[month] = {
        'total': sum(amounts),
        'count': len(amounts),
        'average': sum(amounts) / len(amounts) if amounts else 0
    }

result = {'monthly_trends': monthly_totals}
'''
})
```

## ✅ Workflow Organization

### Logical Grouping
```python
# ✅ GOOD: Group related operations
def create_data_ingestion_workflow():
    workflow = WorkflowBuilder()

    # Data ingestion phase
    workflow.add_node("CSVReaderNode", "raw_data_reader", {...})
    workflow.add_node("PythonCodeNode", "data_validator", {...})
    workflow.add_node("PythonCodeNode", "data_cleaner", {...})

    # Processing phase
    workflow.add_node("PythonCodeNode", "feature_calculator", {...})
    workflow.add_node("PythonCodeNode", "trend_analyzer", {...})

    # Output phase
    workflow.add_node("JSONWriterNode", "results_writer", {...})
    workflow.add_node("PythonCodeNode", "summary_reporter", {...})

    # Connect phases logically
    workflow.add_connection("raw_data_reader", "result", "data_validator", "input_data")
    workflow.add_connection("data_validator", "result", "data_cleaner", "input_data")
    # ... more connections

    return workflow
```

## 🔗 Next Steps
- [Workflows Guide](02-workflows.md) - Complete workflow patterns
- [Advanced Features](03-advanced-features.md) - Enterprise patterns
- [Production Guide](04-production.md) - Deployment best practices
