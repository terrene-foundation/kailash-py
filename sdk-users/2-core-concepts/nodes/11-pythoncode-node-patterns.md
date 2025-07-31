# PythonCodeNode Variable Access Patterns

## Critical Understanding: Direct Variable Injection

The PythonCodeNode **injects input parameters directly into the execution namespace**. This is fundamentally different from function parameters.

### ✅ CORRECT Pattern - Direct Variable Access

```python
from kailash.workflow.builder import WorkflowBuilder
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
local_vars = globals()         # NameError: 'locals' is not defined
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
    if 'required_param' not in globals():
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
available = {k: type(v).__name__ for k, v in globals().items()
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
if 'optional_param' in globals():
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

## Comprehensive Example: All PythonCodeNode Patterns

Here's a complete example demonstrating various ways to create and use PythonCodeNode:

```python
"""
PythonCodeNode Comprehensive Example
====================================

This example shows all the ways to create and use PythonCodeNode:
1. From Python functions
2. From Python classes
3. From code strings
4. From external files
"""

from pathlib import Path
import numpy as np
import pandas as pd

from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow


def create_function_based_node():
    """Example of creating a node from a Python function."""

    # Define a custom data processing function
    def calculate_metrics(data: pd.DataFrame, window_size: int = 5) -> pd.DataFrame:
        """Calculate rolling metrics for the data."""
        # Convert to DataFrame if needed
        if isinstance(data, list):
            data = pd.DataFrame(data)

        # Convert string columns to numeric where possible
        for col in ["value", "quantity"]:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce")

        result = data.copy()

        # Calculate rolling mean
        for column in data.select_dtypes(include=[np.number]).columns:
            result[f"{column}_rolling_mean"] = data[column].rolling(window_size).mean()
            result[f"{column}_rolling_std"] = data[column].rolling(window_size).std()

        # Add a custom metric
        if "value" in data.columns:
            result["value_zscore"] = (data["value"] - data["value"].mean()) / data["value"].std()

        # Convert DataFrame to JSON-serializable format
        return result.to_dict("records")

    # Create node from function
    return PythonCodeNode.from_function(
        func=calculate_metrics,
        name="metrics_calculator",
        description="Calculate rolling statistics and z-scores"
    )


def create_class_based_node():
    """Example of creating a stateful node from a Python class."""

    class OutlierDetector:
        """Stateful outlier detection using IQR method."""

        def __init__(self, sensitivity: float = 1.5):
            self.sensitivity = sensitivity
            self.q1 = None
            self.q3 = None
            self.iqr = None
            self.outlier_count = 0

        def process(self, data: pd.DataFrame, value_column: str = "value") -> pd.DataFrame:
            """Process data and mark outliers."""
            # Convert to DataFrame if needed
            if isinstance(data, list):
                data = pd.DataFrame(data)

            # Convert string columns to numeric
            for col in ["value", "quantity"]:
                if col in data.columns:
                    data[col] = pd.to_numeric(data[col], errors="coerce")

            result = data.copy()

            # Calculate IQR on first run
            if self.q1 is None:
                self.q1 = data[value_column].quantile(0.25)
                self.q3 = data[value_column].quantile(0.75)
                self.iqr = self.q3 - self.q1

            # Detect outliers
            lower_bound = self.q1 - self.sensitivity * self.iqr
            upper_bound = self.q3 + self.sensitivity * self.iqr

            result["is_outlier"] = (
                (data[value_column] < lower_bound) |
                (data[value_column] > upper_bound)
            )

            # Update outlier count
            new_outliers = result["is_outlier"].sum()
            self.outlier_count += new_outliers

            # Add metadata
            result["lower_bound"] = lower_bound
            result["upper_bound"] = upper_bound
            result["total_outliers"] = self.outlier_count

            # Convert to records
            return result.to_dict("records")

    # Create node from class
    return PythonCodeNode.from_class(
        cls=OutlierDetector,
        name="outlier_detector",
        description="Detect outliers using IQR method",
        method_name="process",  # Optional: specify which method to call
        init_params={"sensitivity": 2.0}  # Constructor parameters
    )


def create_code_string_node():
    """Example of creating a node from a code string."""

    code = """
# Direct variable access - no 'inputs' dict!
import statistics

# Filter high-value items
high_value_items = [item for item in data if item.get('value', 0) > threshold]

# Calculate statistics
values = [item['value'] for item in high_value_items]
stats = {
    'count': len(high_value_items),
    'mean': statistics.mean(values) if values else 0,
    'median': statistics.median(values) if values else 0,
    'total': sum(values)
}

# Prepare output
result = {
    'high_value_items': high_value_items,
    'statistics': stats,
    'threshold_used': threshold
}
"""

    return PythonCodeNode(
        name="high_value_filter",
        code=code,
        description="Filter and analyze high-value items"
    )


def build_complete_workflow():
    """Build a complete workflow using all node types."""

    workflow = WorkflowBuilder()

    # Add data source
    workflow.add_node("CSVReaderNode", "csv_reader", {}))

    # Add function-based node
    metrics_node = create_function_based_node()
    workflow.add_node("metrics", metrics_node)

    # Add class-based node
    outlier_node = create_class_based_node()
    workflow.add_node("outliers", outlier_node)

    # Add code string node
    filter_node = create_code_string_node()
    workflow.add_node("filter", filter_node)

    # Add aggregation node using inline code
    workflow.add_node("PythonCodeNode", "aggregator", {}))
high_value_count = summary.get('statistics', {}).get('count', 0)

# Create final summary
result = {
    'total_records': len(outlier_data),
    'outliers_found': outlier_count,
    'high_value_items': high_value_count,
    'outlier_percentage': (outlier_count / len(outlier_data) * 100) if outlier_data else 0,
    'metrics': metrics_data[0] if metrics_data else {},
    'filter_summary': summary
}
"""
    ))

    # Add output node
    workflow.add_node("CSVWriterNode", "csv_writer", {}))

    # Connect the workflow
    workflow.add_connection("csv_reader", "metrics", "result", "data")
    workflow.add_connection("metrics", "outliers", "result", "data")
    workflow.add_connection("outliers", "filter", "result", "data")
    workflow.add_connection("outliers", "aggregator", "result", "outlier_data")
    workflow.add_connection("metrics", "aggregator", "result", "metrics_data")
    workflow.add_connection("filter", "aggregator", "result", "summary")
    workflow.add_connection("aggregator", "csv_writer", "result", "data")

    return workflow


def main():
    """Run the complete demonstration."""

    # Create workflow
    workflow = build_complete_workflow()

    # Prepare runtime
    runtime = LocalRuntime()

    # Execute with sample data
    results, run_id = runtime.execute(
        workflow,
        parameters={
            "csv_reader": {
                "file_path": "sample_data.csv"
            },
            "filter": {
                "threshold": 100  # Direct parameter injection
            },
            "csv_writer": {
                "file_path": "output_results.csv"
            }
        }
    )

    print(f"Workflow executed successfully! Run ID: {run_id}")
    print(f"Final summary: {results.get('aggregator', {})}")

    # Demonstrate from_file method
    external_node = PythonCodeNode.from_file(
        file_path="custom_processor.py",
        name="external_processor",
        function_name="process_data"  # Optional: specific function to use
    )

    print("Created node from external file:", external_node.name)


if __name__ == "__main__":
    main()
```

This comprehensive example demonstrates:

1. **Function-based nodes**: Converting Python functions with type hints
2. **Class-based nodes**: Using stateful classes for complex processing
3. **Code string nodes**: Direct code strings with variable injection
4. **Inline nodes**: Creating nodes directly in workflow definition
5. **File-based nodes**: Loading code from external Python files
6. **Parameter injection**: How variables are directly available
7. **Data flow**: Connecting nodes with proper output handling
8. **Best practices**: Error handling, type conversion, and serialization

Key takeaways:
- Variables are injected directly into the execution namespace
- Always set the `result` variable for output
- Convert complex types to JSON-serializable formats
- Use descriptive names to avoid variable conflicts
- Leverage different creation methods based on your needs

## ✅ Serialization Consistency (Fixed in v0.6.2+)

All PythonCodeNode outputs are consistently wrapped in a `"result"` key for reliable serialization:

```python
# All these patterns produce consistent output structure:
# results["node_id"]["result"] = {your_actual_output}

# Code string: result = {"data": processed}
# Function return: return {"data": processed}
# Class method return: return {"data": processed}
# All become: {"result": {"data": processed}}
```

This ensures reliable serialization across all PythonCodeNode creation methods (function, class, code string, inline, file-based).

When connecting nodes, always use "result" as the output key:
```python
workflow.add_connection("python_node", "result", "next_node", "input_data")
# Or access nested data:
workflow.add_connection("python_node", "result.data", "next_node", "input_data")
```

## Summary

1. **Variables are injected directly** - no `inputs` dictionary
2. **Restricted builtins** - no `globals()`, `dir()`, `eval()`
3. **Must set `result` variable** for output
4. **Input variables excluded** from output
5. **Output must be JSON serializable**
6. **Use different variable names** in connections to avoid conflicts
7. **All outputs wrapped in `"result"` key** for consistent serialization
