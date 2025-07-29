# Data Integration Patterns

*Essential patterns for combining and normalizing data from multiple sources*

## 🔗 ID Normalization

### Multi-Source ID Format Fix
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

def workflow.()  # Type signature example -> dict:
    """Handle ID format mismatches between data sources.

    Example: customers='cust1', transactions='C001'
    """
    import pandas as pd

    # Convert customer IDs from 'cust1' to 'C001' format
    customer_df = pd.DataFrame(customers)
    if 'customer_id' in customer_df.columns:
        customer_df['customer_id_norm'] = (
            customer_df['customer_id']
            .str.extract(r'(\d+)')[0]  # Extract numbers
            .str.zfill(3)              # Pad to 3 digits
            .apply(lambda x: f'C{x}')  # Add 'C' prefix
        )

    # Normalize transaction IDs similarly
    transaction_df = pd.DataFrame(transactions)
    if 'customer_id' in transaction_df.columns:
        transaction_df['customer_id_norm'] = transaction_df['customer_id']

    return {
        'result': {
            'customers': customer_df.to_dict('records'),
            'transactions': transaction_df.to_dict('records')
        }
    }

# Usage
id_normalizer = PythonCodeNode.from_function(
    name="id_normalizer", func=normalize_customer_ids
)
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

### Generic ID Standardization
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

def workflow.()  # Type signature example -> dict:
    """Generic ID standardization.

    Args:
        format_pattern: e.g., 'C{:03d}', 'USER_{:04d}'
    """
    import pandas as pd
    df = pd.DataFrame(data)

    if id_field in df.columns:
        # Extract numeric part and apply format
        numeric_ids = df[id_field].str.extract(r'(\d+)')[0].astype(int)
        df[f'{id_field}_norm'] = numeric_ids.apply(lambda x: format_pattern.format(x))

    return {'result': df.to_dict('records')}

# Usage examples
customer_normalizer = PythonCodeNode.from_function(
    name="customer_normalizer",
    func=lambda data: standardize_ids(data, 'customer_id', 'C{:03d}')
)

```

## 📊 Safe Data Merging

### Merge with Validation
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

def workflow.()  # Type signature example -> dict:
    """Safely merge datasets with validation."""
    import pandas as pd

    try:
        left_df = pd.DataFrame(left_data)
        right_df = pd.DataFrame(right_data)

        # Validate join key exists
        if join_key not in left_df.columns:
            return {'result': [], 'error': f'Join key {join_key} missing in left data'}
        if join_key not in right_df.columns:
            return {'result': [], 'error': f'Join key {join_key} missing in right data'}

        # Check for duplicates
        left_dups = left_df[join_key].duplicated().sum()
        right_dups = right_df[join_key].duplicated().sum()
        if left_dups > 0 or right_dups > 0:
            return {'result': [], 'error': f'Duplicates: left={left_dups}, right={right_dups}'}

        # Perform merge
        merged_df = pd.merge(left_df, right_df, on=join_key, how='inner')

        return {
            'result': merged_df.to_dict('records'),
            'statistics': {
                'left_records': len(left_df),
                'right_records': len(right_df),
                'merged_records': len(merged_df),
                'match_rate': len(merged_df) / max(len(left_df), 1) * 100
            }
        }

    except Exception as e:
        return {'result': [], 'error': str(e)}

# Usage
data_merger = PythonCodeNode.from_function(
    name="data_merger",
    func=lambda left, right: safe_data_merge(left, right, 'customer_id_norm')
)

```

### Multi-Source Aggregation
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

def workflow.()  # Type signature example -> dict:
    """Aggregate data from multiple sources."""
    import pandas as pd

    customer_df = pd.DataFrame(customers)
    transaction_df = pd.DataFrame(transactions)
    market_df = pd.DataFrame(market_data)

    # Aggregate transactions by customer
    if 'customer_id_norm' in transaction_df.columns:
        transaction_summary = transaction_df.groupby('customer_id_norm').agg({
            'amount': ['sum', 'mean', 'count'],
            'transaction_date': 'max'
        }).reset_index()

        # Flatten column names
        transaction_summary.columns = [
            'customer_id_norm', 'total_amount', 'avg_amount',
            'transaction_count', 'last_transaction_date'
        ]
    else:
        transaction_summary = pd.DataFrame()

    # Merge customer data with transactions
    if not customer_df.empty and not transaction_summary.empty:
        enriched_df = pd.merge(
            customer_df, transaction_summary,
            on='customer_id_norm', how='left'
        )
    else:
        enriched_df = customer_df

    # Add market context
    if not market_df.empty and 'date' in market_df.columns:
        latest_market = market_df.iloc[-1]
        enriched_df['market_context'] = latest_market.to_dict()

    return {
        'result': enriched_df.to_dict('records'),
        'metadata': {
            'customer_count': len(customer_df),
            'transaction_count': len(transaction_df)
        }
    }

# Usage
aggregator = PythonCodeNode.from_function(
    name="aggregator", func=aggregate_multiple_sources
)
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## 🗓️ DateTime Handling

### Safe DateTime Serialization
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

def workflow.()  # Type signature example -> dict:
    """Convert datetime objects for JSON serialization."""
    import pandas as pd
    from datetime import datetime

    df = pd.DataFrame(df_data)

    # Convert datetime columns to strings
    for col in df.columns:
        if df[col].dtype == 'datetime64[ns]':
            df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S')
        elif any(isinstance(x, datetime) for x in df[col].dropna()):
            df[col] = pd.to_datetime(df[col]).dt.strftime('%Y-%m-%d %H:%M:%S')
        elif col.lower().endswith(('_date', '_time')):
            try:
                df[col] = pd.to_datetime(df[col]).dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                pass  # Keep original if conversion fails

    return {'result': df.to_dict('records')}

# Usage
serializer = PythonCodeNode.from_function(
    name="datetime_serializer", func=safe_datetime_serialization
)

```

### Date Range Filtering
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

def workflow.()  # Type signature example -> dict:
    """Filter records by date range."""
    import pandas as pd

    df = pd.DataFrame(data)
    if date_field not in df.columns:
        return {'result': data, 'warning': f'Date field {date_field} not found'}

    try:
        df[date_field] = pd.to_datetime(df[date_field])
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)

        filtered_df = df[(df[date_field] >= start) & (df[date_field] <= end)]

        return {
            'result': filtered_df.to_dict('records'),
            'statistics': {
                'original_count': len(df),
                'filtered_count': len(filtered_df)
            }
        }
    except Exception as e:
        return {'result': data, 'error': f'Date filtering failed: {str(e)}'}

# Usage
date_filter = PythonCodeNode.from_function(
    name="date_filter",
    func=lambda data: filter_by_date_range(
        data, 'transaction_date', '2024-01-01', '2024-12-31'
    )
)

```

## 🔧 Data Validation

### Quality Checks
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

def workflow.()  # Type signature example -> dict:
    """Validate data quality before integration."""
    import pandas as pd

    df = pd.DataFrame(data)
    issues = []

    # Check required fields
    missing_fields = [field for field in required_fields if field not in df.columns]
    if missing_fields:
        issues.append(f'Missing fields: {missing_fields}')

    # Check for empty data
    if df.empty:
        return {'result': data, 'valid': False, 'issues': ['Dataset is empty']}

    # Check for null values
    for field in required_fields:
        if field in df.columns:
            null_count = df[field].isnull().sum()
            if null_count > 0:
                issues.append(f'{field} has {null_count} null values')

    # Check for duplicates
    if 'customer_id' in df.columns:
        dup_count = df['customer_id'].duplicated().sum()
        if dup_count > 0:
            issues.append(f'{dup_count} duplicate customer IDs')

    # Validate numeric fields
    numeric_fields = ['amount', 'balance', 'score']
    for field in numeric_fields:
        if field in df.columns:
            non_numeric = pd.to_numeric(df[field], errors='coerce').isnull().sum()
            if non_numeric > 0:
                issues.append(f'{field} has {non_numeric} non-numeric values')

    return {
        'result': data,
        'valid': len(issues) == 0,
        'issues': issues,
        'statistics': {
            'record_count': len(df),
            'field_count': len(df.columns)
        }
    }

# Usage
validator = PythonCodeNode.from_function(
    name="validator",
    func=lambda data: validate_data_quality(
        data, required_fields=['customer_id', 'tier', 'status']
    )
)

```

## 🗄️ Modern Query Builder & Cache Integration

### QueryBuilder for Complex Data Queries
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.data.query_builder import QueryBuilder, create_query_builder
from kailash.nodes.data.query_cache import QueryCache

# Create workflow with query builder
workflow = WorkflowBuilder()

# Add query builder node for complex customer queries
workflow.add_node("QueryBuilder", "customer_query", {
    "database_type": "postgresql",
    "table": "customers",
    "query_config": {
        "where": [
            {"field": "age", "operator": "$gte", "value": 18},
            {"field": "status", "operator": "$in", "value": ["active", "premium"]},
            {"field": "region", "operator": "$eq", "value": "US"}
        ],
        "select": ["id", "name", "email", "tier", "last_login"],
        "order_by": [{"field": "last_login", "direction": "desc"}],
        "limit": 100
    }
})

# Add query cache for performance
workflow.add_node("QueryCache", "cache_results", {
    "redis_host": "localhost",
    "redis_port": 6379,
    "cache_ttl": 300,  # 5 minutes
    "cache_key_prefix": "customer_query",
    "invalidation_strategy": "pattern_based"
})

# Connect for cached query execution
workflow.add_connection("customer_query", "result", "cache_results", "input")
```

### Multi-Database Query Integration
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.data.query_builder import create_query_builder

workflow = WorkflowBuilder()

# PostgreSQL customer data
workflow.add_node("QueryBuilder", "pg_customers", {
    "database_type": "postgresql",
    "connection_string": "postgresql://user:pass@localhost:5432/customers",
    "table": "customers",
    "query_config": {
        "where": [{"field": "status", "operator": "$eq", "value": "active"}],
        "select": ["customer_id", "name", "tier"]
    }
})

# MySQL transaction data
workflow.add_node("QueryBuilder", "mysql_transactions", {
    "database_type": "mysql",
    "connection_string": "mysql://user:pass@localhost:3306/transactions",
    "table": "transactions",
    "query_config": {
        "where": [
            {"field": "date", "operator": "$gte", "value": "2024-01-01"},
            {"field": "amount", "operator": "$gt", "value": 100}
        ],
        "select": ["customer_id", "amount", "date"],
        "order_by": [{"field": "date", "direction": "desc"}]
    }
})

# Join results with PythonCodeNode
workflow.add_node("PythonCodeNode", "join_data", {
    "code": """
import pandas as pd

# Convert to DataFrames
customers_df = pd.DataFrame(pg_customers)
transactions_df = pd.DataFrame(mysql_transactions)

# Join on customer_id
joined_df = pd.merge(
    customers_df,
    transactions_df,
    on='customer_id',
    how='inner'
)

# Aggregate by customer
result_df = joined_df.groupby(['customer_id', 'name', 'tier']).agg({
    'amount': ['sum', 'count', 'mean']
}).reset_index()

# Flatten columns
result_df.columns = ['customer_id', 'name', 'tier', 'total_amount', 'transaction_count', 'avg_amount']

result = result_df.to_dict('records')
"""
})

# Connect the pipeline
workflow.add_connection("pg_customers", "result", "join_data", "input")
workflow.add_connection("mysql_transactions", "result", "join_data", "input")
```

### Cached Data Pipeline with Invalidation
```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Query with caching
workflow.add_node("QueryBuilder", "data_query", {
    "database_type": "postgresql",
    "table": "analytics_data",
    "query_config": {
        "where": [
            {"field": "date", "operator": "$gte", "value": "2024-01-01"},
            {"field": "region", "operator": "$eq", "value": "US"}
        ],
        "select": ["date", "region", "revenue", "users"],
        "order_by": [{"field": "date", "direction": "asc"}]
    }
})

# Add intelligent caching
workflow.add_node("QueryCache", "smart_cache", {
    "redis_host": "localhost",
    "redis_port": 6379,
    "cache_ttl": 3600,  # 1 hour
    "invalidation_strategy": "pattern_based",
    "invalidation_patterns": [
        "analytics_data:*",
        "user_activity:*",
        "revenue:*"
    ],
    "cache_key_template": "analytics:{region}:{date_range}",
    "compression_enabled": True
})

# Pattern-based cache invalidation trigger
workflow.add_node("PythonCodeNode", "cache_invalidation", {
    "code": """
from kailash.nodes.data.query_cache import QueryCache

# If data is updated, invalidate related caches
if data_updated:
    cache = QueryCache(redis_host="localhost", redis_port=6379)
    cache.invalidate_by_pattern("analytics:*")
    cache.invalidate_by_pattern("user_activity:*")

result = {"cache_invalidated": True}
"""
})

workflow.add_connection("data_query", "result", "smart_cache", "input")
```

## 📋 Best Practices

1. **Use QueryBuilder for Complex Queries**
   ```python
   from kailash.workflow.builder import WorkflowBuilder
   from kailash.nodes.data.query_builder import QueryBuilder

   workflow = WorkflowBuilder()

   # Instead of raw SQL, use QueryBuilder
   workflow.add_node("QueryBuilder", "customer_query", {
       "database_type": "postgresql",
       "table": "customers",
       "query_config": {
           "where": [
               {"field": "age", "operator": "$gte", "value": 18},
               {"field": "status", "operator": "$eq", "value": "active"}
           ],
           "select": ["id", "name", "email"]
       }
   })
   ```

2. **Add Caching for Performance**
   ```python
   # Add QueryCache after expensive queries
   workflow.add_node("QueryCache", "cache_results", {
       "redis_host": "localhost",
       "redis_port": 6379,
       "cache_ttl": 300,
       "invalidation_strategy": "pattern_based"
   })
   workflow.add_connection("customer_query", "result", "cache_results", "input")
   ```

3. **Use MergeNode for Simple Joins**
   ```python
   from kailash.workflow.builder import WorkflowBuilder
   from kailash.nodes.logic import MergeNode

   workflow = WorkflowBuilder()
   workflow.add_node("MergeNode", "data_merger", {
       "merge_strategy": "inner_join",
       "join_key": "customer_id"
   })
   ```

4. **Validate Early and Often**
   ```python
   from kailash.workflow.builder import WorkflowBuilder
   from kailash.nodes.validation import ValidationNode

   workflow = WorkflowBuilder()

   # Add validation after each major step
   workflow.add_node("ValidationNode", "validate_input", {
       "schema": {
           "type": "object",
           "properties": {
               "customer_id": {"type": "string"},
               "amount": {"type": "number", "minimum": 0}
           },
           "required": ["customer_id", "amount"]
       }
   })

   workflow.add_connection("reader", "result", "validate_input", "input")
   workflow.add_connection("validate_input", "result", "normalizer", "input")
   ```

5. **Handle Edge Cases**
   - Empty datasets
   - Missing join keys
   - Duplicate records
   - Format inconsistencies
   - Cache misses and invalidation

## ⚠️ Common Pitfalls

- Not validating join keys exist
- Ignoring duplicate records
- Hardcoding ID formats
- Not handling datetime serialization
- Skipping data quality validation

---
*Related: [035-production-readiness.md](035-production-readiness.md), [039-workflow-composition.md](039-workflow-composition.md)*
