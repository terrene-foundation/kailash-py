# ETL Pipeline Training - Common Mistakes and Corrections

This document shows common implementation mistakes when building ETL pipelines with Kailash SDK, followed by the correct implementations. This is designed for training LLMs to create accurate Kailash workflows.

## ACTUAL ERRORS ENCOUNTERED AND FIXES

### Error 1: AsyncLocalRuntime Import
```python
# WRONG: AsyncLocalRuntime not exported in __init__.py
from kailash.runtime import AsyncLocalRuntime
# ImportError: cannot import name 'AsyncLocalRuntime'

# CORRECT: Use LocalRuntime for synchronous execution
from kailash.runtime import LocalRuntime
```

### Error 2: Workflow Constructor Parameters
```python
# WRONG: Missing required workflow_id parameter
workflow = Workflow(name="basic_etl_pipeline")
# TypeError: Workflow.__init__() missing 1 required positional argument: 'workflow_id'

# CORRECT: Provide workflow_id as first parameter
workflow = Workflow(
    workflow_id="etl_pipeline_001",
    name="basic_etl_pipeline",
    description="ETL pipeline for customer data processing"
)
```

### Error 3: DataTransformer Initialization
```python
# WRONG: DataTransformer requires transformations at initialization
enriched_customers = DataTransformer(id="enriched_customers")
# NodeConfigurationError: Required parameter 'transformations' not provided

# CORRECT: Provide transformations at node creation
enriched_customers = DataTransformer(
    id="enriched_customers",
    transformations=[]  # Will be overridden by runtime parameters
)
```

### Error 4: MergeNode Output Key
```python
# WRONG: Assuming wrong output key from MergeNode
workflow.connect(
    "merge_node",
    "output_writer",
    mapping={"merged_data": "data"}  # KeyError: 'data'
)

# The error was actually in CSVWriterNode expecting 'data' input
# MergeNode outputs 'merged_data' correctly
# Need to check what inputs each node expects
```

### Error 5: MergeNode Input Parameters
```python
# WRONG: Using wrong parameter names for MergeNode
workflow.connect(enriched.id, merge.id, mapping={"result": "primary_data"})
workflow.connect(filtered.id, merge.id, mapping={"data": "secondary_data"})

# CORRECT: MergeNode expects data1, data2, data3, data4, data5
workflow.connect(enriched.id, merge.id, mapping={"result": "data1"})
workflow.connect(filtered.id, merge.id, mapping={"data": "data2"})
```

### Error 6: MergeNode Configuration
```python
# WRONG: Using non-existent merge parameters
parameters = {
    "merge_node": {
        "merge_key": "customer_id",
        "merge_strategy": "left"  # These don't exist
    }
}

# CORRECT: Use actual MergeNode parameters
parameters = {
    "merge_node": {
        "merge_type": "merge_dict",  # Options: concat, zip, merge_dict
        "key": "customer_id"  # For merge_dict with lists of dicts
    }
}
```

## CORRECT: Basic ETL Pipeline Structure

```python
# CORRECT: Use specialized nodes for each operation
from kailash import Workflow
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.transform import FilterNode, DataTransformer
from kailash.nodes.logic import MergeNode

workflow = Workflow(name="etl_pipeline")

# Data source nodes
reader = CSVReaderNode(name="csv_reader", file_path="data/input.csv")
workflow.add_node(reader)

# Transform nodes
filter_node = FilterNode(name="filter_active")
workflow.add_node(filter_node)
workflow.connect(reader.id, filter_node.id, mapping={"data": "data"})

# Parameters for filtering
parameters = {
    "filter_active": {
        "field": "status",
        "operator": "==", 
        "value": "active"
    }
}
```

## WRONG: Using PythonCodeNode for CSV Reading

```python
# WRONG: Don't use PythonCodeNode for operations that have dedicated nodes
from kailash.nodes.code import PythonCodeNode

# This is incorrect - CSVReaderNode exists for this purpose
csv_reader = PythonCodeNode(
    name="csv_reader",
    code="""
import csv
with open('data/input.csv', 'r') as f:
    reader = csv.DictReader(f)
    data = list(reader)
result = {"data": data}
"""
)
```

## WRONG: Using PythonCodeNode for Filtering

```python
# WRONG: Don't use PythonCodeNode for filtering
filter_node = PythonCodeNode(
    name="filter_node",
    code="""
filtered = [row for row in data if row['status'] == 'active']
result = {"filtered_data": filtered}
"""
)

# CORRECT: Use FilterNode
filter_node = FilterNode(name="filter_active")
# Configure via parameters
parameters = {
    "filter_active": {
        "field": "status",
        "operator": "==",
        "value": "active"
    }
}
```

## WRONG: Using PythonCodeNode for Data Transformation

```python
# WRONG: Avoid PythonCodeNode for simple transformations
transform_node = PythonCodeNode(
    name="transform",
    code="""
for row in data:
    row['lifetime_value'] = float(row['total_purchases']) * 1.5
    row['segment'] = 'high' if row['lifetime_value'] > 1000 else 'standard'
result = {"data": data}
"""
)

# CORRECT: Use DataTransformer with lambda functions
transform_node = DataTransformer(name="enrich_data")
parameters = {
    "enrich_data": {
        "transformations": [
            "lambda row: {**row, 'lifetime_value': float(row.get('total_purchases', 0)) * 1.5}",
            "lambda row: {**row, 'segment': 'high' if float(row.get('lifetime_value', 0)) > 1000 else 'standard'}"
        ]
    }
}
```

## WRONG: Manual Data Merging

```python
# WRONG: Don't implement merge logic manually
merge_node = PythonCodeNode(
    name="merge",
    code="""
merged = []
for customer in customers:
    customer_txns = [t for t in transactions if t['customer_id'] == customer['id']]
    merged.append({**customer, 'transactions': customer_txns})
result = {"merged_data": merged}
"""
)

# CORRECT: Use MergeNode
merge_node = MergeNode(name="merge_data")
workflow.connect(customers.id, merge_node.id, mapping={"data": "primary_data"})
workflow.connect(transactions.id, merge_node.id, mapping={"data": "secondary_data"})
parameters = {
    "merge_data": {
        "merge_key": "customer_id",
        "merge_strategy": "left"
    }
}
```

## WRONG: Manual CSV Writing

```python
# WRONG: Don't write CSV files manually
writer_node = PythonCodeNode(
    name="writer",
    code="""
import csv
with open('output.csv', 'w', newline='') as f:
    if data:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
result = {"success": True}
"""
)

# CORRECT: Use CSVWriterNode
writer_node = CSVWriterNode(
    name="csv_writer",
    file_path="data/output.csv"
)
```

## WRONG: Complex Aggregations in PythonCodeNode

```python
# WRONG: Implementing aggregation logic manually
agg_node = PythonCodeNode(
    name="aggregate",
    code="""
from collections import defaultdict
customer_totals = defaultdict(float)
for txn in transactions:
    customer_totals[txn['customer_id']] += float(txn['amount'])
result = {"aggregated": dict(customer_totals)}
"""
)

# CORRECT: Use DataTransformer for aggregations
# First group the data, then aggregate
agg_node = DataTransformer(name="aggregate_transactions")
parameters = {
    "aggregate_transactions": {
        "transformations": [
            """
# Group transactions by customer
from collections import defaultdict
grouped = defaultdict(list)
for txn in data:
    grouped[txn['customer_id']].append(txn)

# Calculate totals
result = []
for customer_id, txns in grouped.items():
    total = sum(float(t['amount']) for t in txns)
    result.append({
        'customer_id': customer_id,
        'total_amount': total,
        'transaction_count': len(txns)
    })
"""
        ]
    }
}
```

## Complete Correct Example

```python
# CORRECT: Full ETL pipeline using appropriate nodes
from kailash import Workflow
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.transform import FilterNode, DataTransformer
from kailash.nodes.logic import MergeNode
from kailash.runtime import LocalRuntime

# Create workflow
workflow = Workflow(name="customer_etl")

# Add nodes with proper types
customers = CSVReaderNode(name="read_customers", file_path="customers.csv")
transactions = CSVReaderNode(name="read_transactions", file_path="transactions.csv")
filter_active = FilterNode(name="filter_active_customers")
enrich = DataTransformer(name="enrich_customers") 
merge = MergeNode(name="merge_data")
writer = CSVWriterNode(name="write_results", file_path="output.csv")

# Add all nodes
for node in [customers, transactions, filter_active, enrich, merge, writer]:
    workflow.add_node(node)

# Connect nodes properly
workflow.connect(customers.id, filter_active.id, mapping={"data": "data"})
workflow.connect(filter_active.id, enrich.id, mapping={"filtered_data": "data"})
workflow.connect(enrich.id, merge.id, mapping={"result": "primary_data"})
workflow.connect(transactions.id, merge.id, mapping={"data": "secondary_data"})
workflow.connect(merge.id, writer.id, mapping={"merged_data": "data"})

# Execute with parameters
runtime = LocalRuntime()
result = runtime.execute(workflow, parameters={
    "filter_active_customers": {
        "field": "status",
        "operator": "==",
        "value": "active"
    },
    "enrich_customers": {
        "transformations": [
            "lambda c: {**c, 'segment': 'vip' if float(c.get('total_spend', 0)) > 1000 else 'regular'}"
        ]
    },
    "merge_data": {
        "merge_key": "customer_id",
        "merge_strategy": "left"
    }
})
```

## Key Principles

1. **Use Specialized Nodes**: Always prefer CSVReaderNode, FilterNode, etc. over PythonCodeNode
2. **Node Naming**: All node classes end with "Node" (e.g., FilterNode, not Filter)
3. **Parameter Configuration**: Use runtime parameters for dynamic values
4. **Data Flow**: Use proper mapping between node outputs and inputs
5. **Error Handling**: Specialized nodes have built-in error handling