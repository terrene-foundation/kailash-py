# Common Custom Node Patterns

This guide covers frequently used patterns when creating custom nodes.

## Session 062: Centralized Data Access Pattern

Always use centralized data utilities for file operations:

```python
from examples.utils.data_paths import get_input_data_path, get_output_data_path, ensure_output_dir_exists

class FileProcessorNode(Node):
    """Process files using centralized data paths."""

    def run(self, **kwargs) -> Dict[str, Any]:
        # ✅ CORRECT: Use centralized data utilities
        input_file = get_input_data_path("customers.csv")
        output_dir = ensure_output_dir_exists("csv")
        output_file = output_dir / "processed_customers.csv"

        # Process file...
        return {"output_path": str(output_file)}

# ❌ WRONG: Hardcoded paths
# input_file = "examples/data/customers.csv"
# output_file = "outputs/processed.csv"
```

## Data Processing Pattern

Process data with validation and error handling:

```python
from typing import Any, Dict
from kailash.nodes.base import Node, NodeParameter

class DataFilterNode(Node):
    """Filter data based on conditions."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            'data': NodeParameter(
                name='data',
                type=list,  # Not List[Dict]!
                required=True,
                description='List of items to filter'
            ),
            'field': NodeParameter(
                name='field',
                type=str,
                required=True,
                description='Field name to filter by'
            ),
            'value': NodeParameter(
                name='value',
                type=Any,  # Flexible comparison value
                required=True,
                description='Value to match'
            ),
            'operation': NodeParameter(
                name='operation',
                type=str,
                required=False,
                default='equals',
                description='Comparison operation: equals, contains, greater, less'
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        data = kwargs['data']
        field = kwargs['field']
        value = kwargs['value']
        operation = kwargs.get('operation', 'equals')

        # Validate input
        if not isinstance(data, list):
            raise ValueError(f"Data must be a list, got {type(data)}")

        # Filter logic
        filtered = []
        for item in data:
            if not isinstance(item, dict):
                continue

            if field not in item:
                continue

            item_value = item[field]

            if operation == 'equals' and item_value == value:
                filtered.append(item)
            elif operation == 'contains' and str(value) in str(item_value):
                filtered.append(item)
            elif operation == 'greater' and item_value > value:
                filtered.append(item)
            elif operation == 'less' and item_value < value:
                filtered.append(item)

        return {
            'filtered_data': filtered,
            'original_count': len(data),
            'filtered_count': len(filtered)
        }
```

## API Integration Pattern

Integrate with external APIs:

```python
import json
import urllib.request
import urllib.error
from typing import Any, Dict
from kailash.nodes.base import Node, NodeParameter

class APIRequestNode(Node):
    """Make HTTP API requests."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            'url': NodeParameter(
                name='url',
                type=str,
                required=True,
                description='API endpoint URL'
            ),
            'method': NodeParameter(
                name='method',
                type=str,
                required=False,
                default='GET',
                description='HTTP method'
            ),
            'headers': NodeParameter(
                name='headers',
                type=dict,  # Not Dict[str, str]!
                required=False,
                default={},
                description='Request headers'
            ),
            'data': NodeParameter(
                name='data',
                type=Any,  # Could be dict, string, etc
                required=False,
                default=None,
                description='Request body data'
            ),
            'timeout': NodeParameter(
                name='timeout',
                type=int,
                required=False,
                default=30,
                description='Request timeout in seconds'
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        url = kwargs['url']
        method = kwargs.get('method', 'GET')
        headers = kwargs.get('headers', {})
        data = kwargs.get('data')
        timeout = kwargs.get('timeout', 30)

        # Prepare request
        if data and method in ['POST', 'PUT', 'PATCH']:
            if isinstance(data, dict):
                data = json.dumps(data).encode('utf-8')
                headers['Content-Type'] = 'application/json'
            elif isinstance(data, str):
                data = data.encode('utf-8')

        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method
        )

        try:
            # Make request
            with urllib.request.urlopen(request, timeout=timeout) as response:
                response_data = response.read().decode('utf-8')

                # Try to parse JSON
                try:
                    response_json = json.loads(response_data)
                except json.JSONDecodeError:
                    response_json = None

                return {
                    'status_code': response.status,
                    'headers': dict(response.headers),
                    'data': response_json or response_data,
                    'success': True
                }

        except urllib.error.HTTPError as e:
            return {
                'status_code': e.code,
                'error': str(e),
                'success': False
            }
        except Exception as e:
            return {
                'error': str(e),
                'success': False
            }
```

## Transformation Pattern

Transform data between formats:

```python
import csv
import json
from io import StringIO
from typing import Any, Dict
from kailash.nodes.base import Node, NodeParameter

class FormatConverterNode(Node):
    """Convert between data formats."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            'data': NodeParameter(
                name='data',
                type=Any,  # Flexible input
                required=True,
                description='Data to convert'
            ),
            'from_format': NodeParameter(
                name='from_format',
                type=str,
                required=True,
                description='Source format: json, csv, text'
            ),
            'to_format': NodeParameter(
                name='to_format',
                type=str,
                required=True,
                description='Target format: json, csv, text'
            ),
            'options': NodeParameter(
                name='options',
                type=dict,
                required=False,
                default={},
                description='Format-specific options'
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        data = kwargs['data']
        from_format = kwargs['from_format']
        to_format = kwargs['to_format']
        options = kwargs.get('options', {})

        # Parse input based on format
        if from_format == 'json':
            if isinstance(data, str):
                parsed = json.loads(data)
            else:
                parsed = data
        elif from_format == 'csv':
            if isinstance(data, str):
                reader = csv.DictReader(StringIO(data))
                parsed = list(reader)
            else:
                parsed = data
        elif from_format == 'text':
            parsed = str(data).split('\n')
        else:
            raise ValueError(f"Unknown from_format: {from_format}")

        # Convert to target format
        if to_format == 'json':
            if isinstance(parsed, str):
                result = parsed
            else:
                result = json.dumps(parsed, indent=options.get('indent', 2))
        elif to_format == 'csv':
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                output = StringIO()
                writer = csv.DictWriter(output, fieldnames=parsed[0].keys())
                writer.writeheader()
                writer.writerows(parsed)
                result = output.getvalue()
            else:
                raise ValueError("CSV conversion requires list of dictionaries")
        elif to_format == 'text':
            if isinstance(parsed, list):
                result = '\n'.join(str(item) for item in parsed)
            else:
                result = str(parsed)
        else:
            raise ValueError(f"Unknown to_format: {to_format}")

        return {
            'converted': result,
            'from_format': from_format,
            'to_format': to_format
        }
```

## Aggregation Pattern

Aggregate data with multiple operations:

```python
from typing import Any, Dict
from kailash.nodes.base import Node, NodeParameter

class DataAggregatorNode(Node):
    """Aggregate data with various operations."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            'data': NodeParameter(
                name='data',
                type=list,
                required=True,
                description='List of numeric values or dicts'
            ),
            'operation': NodeParameter(
                name='operation',
                type=str,
                required=True,
                description='Aggregation: sum, mean, min, max, count, groupby'
            ),
            'field': NodeParameter(
                name='field',
                type=str,
                required=False,
                default=None,
                description='Field to aggregate (for dict items)'
            ),
            'group_by': NodeParameter(
                name='group_by',
                type=str,
                required=False,
                default=None,
                description='Field to group by (for groupby operation)'
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        data = kwargs['data']
        operation = kwargs['operation']
        field = kwargs.get('field')
        group_by = kwargs.get('group_by')

        if not isinstance(data, list):
            raise ValueError("Data must be a list")

        # Extract values
        if field and data and isinstance(data[0], dict):
            values = [item.get(field, 0) for item in data]
        else:
            values = data

        # Perform aggregation
        if operation == 'sum':
            result = sum(values)
        elif operation == 'mean':
            result = sum(values) / len(values) if values else 0
        elif operation == 'min':
            result = min(values) if values else None
        elif operation == 'max':
            result = max(values) if values else None
        elif operation == 'count':
            result = len(values)
        elif operation == 'groupby' and group_by:
            # Group by operation
            groups = {}
            for item in data:
                if isinstance(item, dict) and group_by in item:
                    key = item[group_by]
                    if key not in groups:
                        groups[key] = []
                    groups[key].append(item)
            result = groups
        else:
            raise ValueError(f"Unknown operation: {operation}")

        return {
            'result': result,
            'operation': operation,
            'count': len(data)
        }
```

## Simplifying Complex Routing Workflows

Instead of complex multi-path routing with SwitchNode, use linear processing:

### ❌ AVOID: Complex Multi-Path Routing
```python
# Complex routing that's hard to debug and maintain
workflow.add_node("router", SwitchNode(
    name="router",
    condition_field="decision",
    condition_type="string"
))
workflow.connect("scorer", "router", mapping={"result": "input_data"})
workflow.connect("router", "approved_processor", condition="approved")
workflow.connect("router", "declined_processor", condition="declined")
workflow.connect("router", "review_processor", condition="review")

# Need separate nodes for each path
workflow.add_node("approved_processor", PythonCodeNode(...))
workflow.add_node("declined_processor", PythonCodeNode(...))
workflow.add_node("review_processor", PythonCodeNode(...))
```

### ✅ PREFERRED: Process All Paths in One Node
```python
# Clean, maintainable linear processing
def process_all_decisions(risk_assessments: list) -> dict:
    """Process all decision types in one place."""
    # Separate by type
    results = {
        'approved': [],
        'declined': [],
        'review': []
    }

    for assessment in risk_assessments:
        decision = assessment.get('decision', 'review')

        if decision == 'approved':
            # Process approved application
            letter = generate_approval_letter(assessment)
            results['approved'].append(letter)

        elif decision == 'declined':
            # Process declined application
            letter = generate_decline_letter(assessment)
            results['declined'].append(letter)

        else:  # review
            # Queue for manual review
            review_item = create_review_item(assessment)
            results['review'].append(review_item)

    # Return comprehensive results
    return {
        'processed': results,
        'statistics': {
            'total': len(risk_assessments),
            'approved': len(results['approved']),
            'declined': len(results['declined']),
            'review': len(results['review'])
        }
    }

# Single node handles all logic
workflow.add_node("decision_processor", PythonCodeNode.from_function(
    func=process_all_decisions,
    name="decision_processor",
    description="Process all decision types"
))

# Simple linear connection
workflow.connect("risk_scorer", "decision_processor",
                mapping={"result": "risk_assessments"})
```

### Benefits of Linear Processing:
1. **Easier to Debug**: All logic in one place
2. **Better Performance**: No routing overhead
3. **Simpler Testing**: Test one function, not multiple nodes
4. **Clearer Data Flow**: Linear path is easy to follow
5. **Flexible Logic**: Easy to add new decision types

## 🔗 Data Integration Patterns (Session 064)

### ID Normalization for Multi-Source Data
When combining data from different systems with inconsistent ID formats:

```python
def normalize_customer_ids(customers: list, transactions: list) -> dict:
    """Handle ID format mismatches between data sources."""
    import pandas as pd

    # Convert customer IDs from 'cust1' to 'C001' format
    customer_df = pd.DataFrame(customers)
    if 'customer_id' in customer_df.columns:
        customer_df['customer_id_norm'] = (
            customer_df['customer_id']
            .str.extract(r'(\d+)')[0]
            .str.zfill(3)
            .apply(lambda x: f'C{x}')
        )

    # Ensure transaction IDs match format
    transaction_df = pd.DataFrame(transactions)
    if 'customer_id' in transaction_df.columns:
        transaction_df['customer_id_norm'] = transaction_df['customer_id']

    return {
        'result': {
            'customers': customer_df.to_dict('records'),
            'transactions': transaction_df.to_dict('records')
        }
    }

# Usage in workflow
id_normalizer = PythonCodeNode.from_function(
    name="id_normalizer",
    func=normalize_customer_ids
)
```

### DataFrame Serialization for JSON Output
Handle datetime objects and complex data types:

```python
def safe_dataframe_serialization(df_data: list) -> dict:
    """Convert DataFrame data for JSON serialization."""
    import pandas as pd
    from datetime import datetime

    df = pd.DataFrame(df_data)

    # Convert datetime columns to ISO format strings
    for col in df.columns:
        if df[col].dtype == 'datetime64[ns]':
            df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S')
        elif any(isinstance(x, datetime) for x in df[col].dropna()):
            df[col] = pd.to_datetime(df[col]).dt.strftime('%Y-%m-%d %H:%M:%S')

    return {'result': df.to_dict('records')}

# Usage for safe JSON export
serializer = PythonCodeNode.from_function(
    name="json_serializer",
    func=safe_dataframe_serialization
)
```

## Best Practices in These Patterns

1. **Always validate input types** at runtime
2. **Use `Any` for flexible parameters** instead of generic types
3. **Provide meaningful error messages** for validation failures
4. **Return structured output** with metadata
5. **Handle edge cases** (empty data, missing fields)
6. **Use try-except** for external operations (API calls)
7. **Prefer linear processing** over complex routing when possible
8. **Use .from_function()** for complex logic (better IDE support)
9. **Normalize IDs early** to prevent downstream mismatches
10. **Handle datetime serialization** for JSON outputs

---

*Continue to [04-pythoncode-node.md](04-pythoncode-node.md) →*
