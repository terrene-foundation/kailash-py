# Data Integration Patterns

**Version**: 0.2.1 | **Topic**: Data Integration | **Session 064 Learning**

Patterns for combining and normalizing data from multiple sources, based on real-world finance workflow implementations.

## 🔗 ID Normalization Patterns

### Multi-Source ID Format Mismatch
Common scenario: Different systems use different customer ID formats

```python
def normalize_customer_ids(customers: list, transactions: list) -> dict:
    """Handle ID format mismatches between data sources.
    
    Example: 
    - Customers use 'cust1', 'cust2' format
    - Transactions use 'C001', 'C002' format
    """
    import pandas as pd
    
    # Convert customer IDs from 'cust1' to 'C001' format
    customer_df = pd.DataFrame(customers)
    if 'customer_id' in customer_df.columns:
        customer_df['customer_id_norm'] = (
            customer_df['customer_id']
            .str.extract(r'(\d+)')[0]  # Extract numeric part
            .str.zfill(3)              # Pad to 3 digits
            .apply(lambda x: f'C{x}')  # Add 'C' prefix
        )
    
    # Ensure transaction IDs are in same format
    transaction_df = pd.DataFrame(transactions)
    if 'customer_id' in transaction_df.columns:
        # Assume already in correct format, just copy
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

# Connect multiple sources to normalizer
workflow.connect("customer_reader", "id_normalizer", mapping={"data": "customers"})
workflow.connect("transaction_reader", "id_normalizer", mapping={"data": "transactions"})
```

### Generic ID Normalization Function
Reusable pattern for any ID format standardization:

```python
def standardize_ids(data: list, id_field: str, format_pattern: str) -> dict:
    """Generic ID standardization function.
    
    Args:
        data: List of records with ID field
        id_field: Name of the ID field to standardize
        format_pattern: Target format (e.g., 'C{:03d}', 'USER_{:04d}')
    """
    import pandas as pd
    
    df = pd.DataFrame(data)
    
    if id_field in df.columns:
        # Extract numeric part from any format
        numeric_ids = df[id_field].str.extract(r'(\d+)')[0].astype(int)
        
        # Apply standard format
        df[f'{id_field}_norm'] = numeric_ids.apply(lambda x: format_pattern.format(x))
    
    return {'result': df.to_dict('records')}

# Usage for different ID formats
customer_normalizer = PythonCodeNode.from_function(
    name="customer_normalizer",
    func=lambda data: standardize_ids(data, 'customer_id', 'C{:03d}')
)

user_normalizer = PythonCodeNode.from_function(
    name="user_normalizer", 
    func=lambda data: standardize_ids(data, 'user_id', 'USER_{:04d}')
)
```

## 📊 DataFrame Integration Patterns

### Safe Data Merging with Validation
Merge multiple DataFrames with comprehensive error checking:

```python
def safe_data_merge(left_data: list, right_data: list, join_key: str) -> dict:
    """Safely merge two datasets with validation."""
    import pandas as pd
    
    try:
        left_df = pd.DataFrame(left_data)
        right_df = pd.DataFrame(right_data)
        
        # Validate join key exists in both datasets
        if join_key not in left_df.columns:
            return {'result': [], 'error': f'Join key {join_key} not found in left dataset'}
        
        if join_key not in right_df.columns:
            return {'result': [], 'error': f'Join key {join_key} not found in right dataset'}
        
        # Check for duplicates in join key
        left_dups = left_df[join_key].duplicated().sum()
        right_dups = right_df[join_key].duplicated().sum()
        
        if left_dups > 0 or right_dups > 0:
            return {
                'result': [],
                'error': f'Duplicate join keys found: left={left_dups}, right={right_dups}'
            }
        
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

### Multi-Source Data Aggregation
Combine data from 3+ sources:

```python
def aggregate_multiple_sources(customers: list, transactions: list, market_data: list) -> dict:
    """Aggregate data from multiple sources into unified view."""
    import pandas as pd
    
    # Convert to DataFrames
    customer_df = pd.DataFrame(customers)
    transaction_df = pd.DataFrame(transactions)
    market_df = pd.DataFrame(market_data)
    
    # Aggregate transaction data by customer
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
    
    # Merge customer data with transaction summary
    if not customer_df.empty and not transaction_summary.empty:
        enriched_df = pd.merge(
            customer_df, transaction_summary, 
            on='customer_id_norm', how='left'
        )
    else:
        enriched_df = customer_df
    
    # Add market context if available
    if not market_df.empty and 'date' in market_df.columns:
        latest_market = market_df.iloc[-1]  # Most recent market data
        enriched_df['market_context'] = latest_market.to_dict()
    
    return {
        'result': enriched_df.to_dict('records'),
        'metadata': {
            'customer_count': len(customer_df),
            'transaction_count': len(transaction_df),
            'market_data_points': len(market_df)
        }
    }

# Usage in workflow
aggregator = PythonCodeNode.from_function(
    name="multi_source_aggregator",
    func=aggregate_multiple_sources
)

# Connect multiple sources
workflow.connect("customer_normalizer", "aggregator", mapping={"result": "customers"})
workflow.connect("transaction_normalizer", "aggregator", mapping={"result": "transactions"}) 
workflow.connect("market_reader", "aggregator", mapping={"data": "market_data"})
```

## 🗓️ DateTime Handling Patterns

### Safe DateTime Serialization
Handle datetime objects for JSON output:

```python
def safe_datetime_serialization(df_data: list) -> dict:
    """Convert DataFrame data with datetime objects for JSON serialization."""
    import pandas as pd
    from datetime import datetime
    
    df = pd.DataFrame(df_data)
    
    # Convert datetime columns to ISO format strings
    for col in df.columns:
        # Handle pandas datetime
        if df[col].dtype == 'datetime64[ns]':
            df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Handle mixed datetime objects
        elif any(isinstance(x, datetime) for x in df[col].dropna()):
            df[col] = pd.to_datetime(df[col]).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Handle date strings that need parsing
        elif col.lower().endswith('_date') or col.lower().endswith('_time'):
            try:
                df[col] = pd.to_datetime(df[col]).dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                pass  # Keep original format if conversion fails
    
    return {'result': df.to_dict('records')}

# Usage for JSON export preparation
serializer = PythonCodeNode.from_function(
    name="datetime_serializer",
    func=safe_datetime_serialization
)
```

### DateTime Range Filtering
Filter data by date ranges across sources:

```python
def filter_by_date_range(data: list, date_field: str, start_date: str, end_date: str) -> dict:
    """Filter records by date range."""
    import pandas as pd
    
    df = pd.DataFrame(data)
    
    if date_field not in df.columns:
        return {'result': data, 'warning': f'Date field {date_field} not found'}
    
    try:
        # Convert date column to datetime
        df[date_field] = pd.to_datetime(df[date_field])
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        
        # Filter by date range
        filtered_df = df[(df[date_field] >= start) & (df[date_field] <= end)]
        
        return {
            'result': filtered_df.to_dict('records'),
            'statistics': {
                'original_count': len(df),
                'filtered_count': len(filtered_df),
                'date_range': f'{start_date} to {end_date}'
            }
        }
        
    except Exception as e:
        return {'result': data, 'error': f'Date filtering failed: {str(e)}'}

# Usage with dynamic date ranges
date_filter = PythonCodeNode.from_function(
    name="date_filter",
    func=lambda data: filter_by_date_range(
        data, 'transaction_date', '2024-01-01', '2024-12-31'
    )
)
```

## 🔧 Validation Patterns

### Data Quality Checks
Comprehensive data validation before integration:

```python
def validate_data_quality(data: list, required_fields: list) -> dict:
    """Validate data quality before integration."""
    import pandas as pd
    
    df = pd.DataFrame(data)
    issues = []
    
    # Check required fields
    missing_fields = [field for field in required_fields if field not in df.columns]
    if missing_fields:
        issues.append(f'Missing required fields: {missing_fields}')
    
    # Check for empty data
    if df.empty:
        issues.append('Dataset is empty')
        return {'result': data, 'valid': False, 'issues': issues}
    
    # Check for null values in required fields
    for field in required_fields:
        if field in df.columns:
            null_count = df[field].isnull().sum()
            if null_count > 0:
                issues.append(f'Field {field} has {null_count} null values')
    
    # Check for duplicate IDs
    if 'customer_id' in df.columns:
        dup_count = df['customer_id'].duplicated().sum()
        if dup_count > 0:
            issues.append(f'Found {dup_count} duplicate customer IDs')
    
    # Data type validation
    numeric_fields = ['amount', 'balance', 'score']
    for field in numeric_fields:
        if field in df.columns:
            non_numeric = pd.to_numeric(df[field], errors='coerce').isnull().sum()
            if non_numeric > 0:
                issues.append(f'Field {field} has {non_numeric} non-numeric values')
    
    return {
        'result': data,
        'valid': len(issues) == 0,
        'issues': issues,
        'statistics': {
            'record_count': len(df),
            'field_count': len(df.columns),
            'null_percentage': (df.isnull().sum().sum() / (len(df) * len(df.columns))) * 100
        }
    }

# Usage with specific validation rules
validator = PythonCodeNode.from_function(
    name="data_validator",
    func=lambda data: validate_data_quality(
        data, required_fields=['customer_id', 'tier', 'status']
    )
)
```

## 💡 Best Practices

### 1. Always Normalize IDs Early
```python
# Do ID normalization immediately after reading data
workflow.connect("reader", "id_normalizer", mapping={"data": "raw_data"})
workflow.connect("id_normalizer", "merger", mapping={"result": "normalized_data"})
```

### 2. Use MergeNode for Simple Joins
```python
# For simple data merging, use MergeNode instead of custom code
merger = MergeNode(name="data_merger")
workflow.connect("source1", "merger", mapping={"data": "data1"})
workflow.connect("source2", "merger", mapping={"data": "data2"})
```

### 3. Validate Early and Often
```python
# Add validation after each major data transformation
workflow.connect("reader", "validator1", mapping={"data": "raw_data"})
workflow.connect("normalizer", "validator2", mapping={"result": "normalized_data"})
workflow.connect("merger", "validator3", mapping={"result": "merged_data"})
```

### 4. Handle Edge Cases
- Empty datasets
- Missing join keys
- Duplicate records
- Format inconsistencies
- Null values in critical fields

## 🚨 Common Pitfalls

1. **Not validating join keys exist in both datasets**
2. **Ignoring duplicate records in join keys**
3. **Hardcoding ID formats instead of extracting patterns**
4. **Not handling datetime serialization for JSON output**
5. **Skipping data quality validation before integration**

---

*Related: [033-workflow-design-process.md](033-workflow-design-process.md), [035-production-readiness.md](035-production-readiness.md)*