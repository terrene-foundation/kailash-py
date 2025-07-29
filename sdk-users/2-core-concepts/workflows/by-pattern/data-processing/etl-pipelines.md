# ETL Pipeline Patterns

**Complete guide to Extract, Transform, Load workflows** - From simple CSV processing to enterprise data warehousing.

## 📋 Pattern Overview

ETL (Extract, Transform, Load) pipelines are fundamental data processing patterns that:
- **Extract** data from various sources (databases, APIs, files)
- **Transform** data to meet business requirements (clean, aggregate, enrich)
- **Load** data into target systems (databases, data warehouses, APIs)

## 🚀 Quick Start Examples

### 30-Second CSV ETL Pipeline
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.transform import DataTransformer, FilterNode
from kailash.nodes.logic import MergeNode
from kailash.runtime.local import LocalRuntime

# Extract-Transform-Load pipeline using proper Kailash nodes (matches basic_etl_pipeline.py)
workflow = WorkflowBuilder()

# Data Sources
customers_reader = CSVReaderNode(
    id="customers_reader",
    file_path="data/customers.csv"
)
workflow.add_node("customers_reader", customers_reader)

transactions_reader = CSVReaderNode(
    id="transactions_reader",
    file_path="data/transactions.csv"
)
workflow.add_node("transactions_reader", transactions_reader)

# Data Cleansing - Filter invalid records
valid_customers = FilterNode(id="valid_customers")
workflow.add_node("valid_customers", valid_customers)
workflow.add_connection("customers_reader", "valid_customers", "data", "data")

# Transform customer data - Add calculated fields
enriched_customers = DataTransformer(
    id="enriched_customers",
    transformations=[]  # Will be provided at runtime
)
workflow.add_node("enriched_customers", enriched_customers)
workflow.add_connection("valid_customers", "enriched_customers", "filtered_data", "data")

# Filter high-value transactions
high_value_transactions = FilterNode(id="high_value_transactions")
workflow.add_node("high_value_transactions", high_value_transactions)
workflow.add_connection("transactions_reader", "high_value_transactions", "data", "data")

# Merge customer and transaction data
merge_customer_transactions = MergeNode(id="merge_customer_transactions")
workflow.add_node("merge_customer_transactions", merge_customer_transactions)
workflow.add_connection("enriched_customers", "merge_customer_transactions", "result", "data1")
workflow.add_connection("high_value_transactions", "merge_customer_transactions", "filtered_data", "data2")

# Write results
output_writer = CSVWriterNode(
    id="output_writer",
    file_path="data/outputs/enriched_customers.csv"
)
workflow.add_node("output_writer", output_writer)
workflow.add_connection("merge_customer_transactions", "output_writer", "merged_data", "data")

# Execute the pipeline (matches basic_etl_pipeline.py exactly)
runtime = LocalRuntime()
parameters = {
    "valid_customers": {
        "field": "status",
        "operator": "==",
        "value": "active"
    },
    "enriched_customers": {
        "transformations": [
            # Calculate customer lifetime value
            "lambda customer: {**customer, 'lifetime_value': float(customer.get('total_purchases', 0)) * 1.5}",
            # Add customer segment
            "lambda customer: {**customer, 'segment': 'high' if float(customer.get('lifetime_value', 0)) > 1000 else 'standard'}"
        ]
    },
    "high_value_transactions": {
        "field": "amount",
        "operator": ">=",
        "value": 100.0
    },
    "merge_customer_transactions": {
        "merge_type": "merge_dict",
        "key": "customer_id"
    }
}

result, run_id = runtime.execute(workflow, parameters=parameters)

print(f"ETL Pipeline completed successfully!")
print(f"Processed {result.get('summary_stats', {}).get('total_processed', 0)} records")

```

### Enterprise Database ETL with Real-time Processing
```python
from kailash.nodes.data import SQLDatabaseNode, KafkaConsumerNode
from kailash.nodes.logic import SwitchNode, MergeNode

# Enterprise database ETL workflow
enterprise_etl = Workflow(
    workflow_id="enterprise_etl_001",
    name="enterprise_database_etl",
    description="Production-grade database ETL with real-time capabilities"
)

# Multiple data sources
primary_db = SQLDatabaseNode(
    id="primary_db",
    connection_string="${PRIMARY_DB_URL}",
    query="SELECT * FROM customers WHERE updated_at >= %s",
    operation_type="read",
    batch_size=1000
)
enterprise_etl.add_node("primary_db", primary_db)

secondary_db = SQLDatabaseNode(
    id="secondary_db",
    connection_string="${SECONDARY_DB_URL}",
    query="SELECT customer_id, preference_data, last_activity FROM user_preferences",
    operation_type="read",
    batch_size=1000
)
enterprise_etl.add_node("secondary_db", secondary_db)

# Real-time stream processing
streaming_source = KafkaConsumerNode(
    id="streaming_events",
    bootstrap_servers="${KAFKA_BROKERS}",
    topic="customer_events",
    group_id="etl_consumer_group",
    batch_size=1000
)
enterprise_etl.add_node("streaming_events", streaming_source)

# Advanced data quality checks
quality_checker = DataTransformer(
    id="quality_checker",
    transformations=[
        """
# Comprehensive data quality assessment
import re
from datetime import datetime, timedelta

quality_report = {
    "total_records": 0,
    "quality_scores": {},
    "data_issues": [],
    "recommendations": [],
    "processing_metadata": {
        "check_timestamp": datetime.now().isoformat(),
        "quality_rules_applied": []
    }
}

# Define quality rules
quality_rules = {
    "completeness": {
        "required_fields": ["customer_id", "email", "created_date"],
        "weight": 0.3
    },
    "validity": {
        "email_pattern": r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
        "date_formats": ['%Y-%m-%d', '%m/%d/%Y', '%Y-%m-%d %H:%M:%S'],
        "weight": 0.25
    },
    "consistency": {
        "status_values": ["active", "inactive", "pending", "suspended"],
        "weight": 0.2
    },
    "timeliness": {
        "max_age_days": 30,
        "weight": 0.15
    },
    "uniqueness": {
        "unique_fields": ["customer_id", "email"],
        "weight": 0.1
    }
}

processed_records = []
seen_values = {"customer_id": set(), "email": set()}

for i, record in enumerate(data):
    record_score = 100.0
    record_issues = []

    # Completeness check
    missing_fields = [field for field in quality_rules["completeness"]["required_fields"]
                     if not record.get(field)]
    if missing_fields:
        completeness_penalty = (len(missing_fields) / len(quality_rules["completeness"]["required_fields"])) * 100
        record_score -= completeness_penalty * quality_rules["completeness"]["weight"]
        record_issues.append(f"Missing fields: {missing_fields}")

    # Validity checks
    email = record.get("email", "")
    if email and not re.match(quality_rules["validity"]["email_pattern"], email):
        record_score -= 25 * quality_rules["validity"]["weight"]
        record_issues.append("Invalid email format")

    # Date validity
    created_date = record.get("created_date")
    if created_date:
        date_valid = False
        for fmt in quality_rules["validity"]["date_formats"]:
            try:
                datetime.strptime(str(created_date), fmt)
                date_valid = True
                break
            except ValueError:
                continue
        if not date_valid:
            record_score -= 20 * quality_rules["validity"]["weight"]
            record_issues.append("Invalid date format")

    # Consistency checks
    status = record.get("status", "").lower()
    if status and status not in quality_rules["consistency"]["status_values"]:
        record_score -= 15 * quality_rules["consistency"]["weight"]
        record_issues.append(f"Invalid status: {status}")

    # Timeliness check
    if created_date:
        try:
            for fmt in quality_rules["validity"]["date_formats"]:
                try:
                    record_date = datetime.strptime(str(created_date), fmt)
                    age_days = (datetime.now() - record_date).days
                    if age_days > quality_rules["timeliness"]["max_age_days"]:
                        staleness_penalty = min(age_days / 365 * 50, 50)  # Cap at 50%
                        record_score -= staleness_penalty * quality_rules["timeliness"]["weight"]
                        record_issues.append(f"Stale data: {age_days} days old")
                    break
                except ValueError:
                    continue
        except:
            pass

    # Uniqueness checks
    customer_id = record.get("customer_id")
    if customer_id:
        if customer_id in seen_values["customer_id"]:
            record_score -= 30 * quality_rules["uniqueness"]["weight"]
            record_issues.append("Duplicate customer_id")
        else:
            seen_values["customer_id"].add(customer_id)

    if email:
        if email in seen_values["email"]:
            record_score -= 25 * quality_rules["uniqueness"]["weight"]
            record_issues.append("Duplicate email")
        else:
            seen_values["email"].add(email)

    # Assign quality grade
    if record_score >= 90:
        quality_grade = "A"
    elif record_score >= 80:
        quality_grade = "B"
    elif record_score >= 70:
        quality_grade = "C"
    elif record_score >= 60:
        quality_grade = "D"
    else:
        quality_grade = "F"

    # Enhanced record with quality metadata
    enhanced_record = dict(record)
    enhanced_record.update({
        "quality_score": round(record_score, 2),
        "quality_grade": quality_grade,
        "quality_issues": record_issues,
        "quality_check_timestamp": datetime.now().isoformat()
    })

    processed_records.append(enhanced_record)

    # Collect issues for reporting
    if record_issues:
        quality_report["data_issues"].extend([f"Record {i}: {issue}" for issue in record_issues])

# Calculate overall quality metrics
if processed_records:
    avg_quality_score = sum(r["quality_score"] for r in processed_records) / len(processed_records)
    grade_distribution = {}
    for record in processed_records:
        grade = record["quality_grade"]
        grade_distribution[grade] = grade_distribution.get(grade, 0) + 1

    quality_report.update({
        "total_records": len(processed_records),
        "average_quality_score": round(avg_quality_score, 2),
        "grade_distribution": grade_distribution,
        "high_quality_records": sum(1 for r in processed_records if r["quality_score"] >= 80),
        "low_quality_records": sum(1 for r in processed_records if r["quality_score"] < 60)
    })

    # Generate recommendations
    if avg_quality_score < 70:
        quality_report["recommendations"].append("Overall data quality below threshold - implement data governance")

    if grade_distribution.get("F", 0) > len(processed_records) * 0.1:
        quality_report["recommendations"].append("High number of failing records - review data sources")

    if len(seen_values["customer_id"]) < len(processed_records):
        quality_report["recommendations"].append("Duplicate customer IDs detected - implement deduplication")

result = {
    "quality_checked_data": processed_records,
    "quality_report": quality_report
}
"""
    ]
)
enterprise_etl.add_node("quality_checker", quality_checker)

# Data merger for multiple sources
data_merger = MergeNode(
    id="data_merger",
    merge_strategy="left_join",
    join_keys=["customer_id"]
)
enterprise_etl.add_node("data_merger", data_merger)

# Route based on quality scores
quality_router = SwitchNode(
    id="quality_router",
    condition="quality_score >= 80"
)
enterprise_etl.add_node("quality_router", quality_router)

# High-quality data processing
premium_processor = DataTransformer(
    id="premium_processor",
    transformations=[
        """
# Premium processing for high-quality data
from datetime import datetime
import json

premium_records = []
for record in data:
    if record.get("quality_score", 0) >= 80:
        # Advanced enrichment for high-quality records
        enriched_record = dict(record)

        # AI-powered segmentation (simplified)
        total_value = float(record.get("total_value", 0))
        engagement_score = float(record.get("engagement_score", 0))
        recency_days = int(record.get("days_since_signup", 0))

        # Multi-dimensional scoring
        value_score = min(total_value / 10000 * 100, 100)  # Normalize to 100
        engagement_normalized = min(engagement_score, 100)
        recency_score = max(100 - (recency_days / 365 * 50), 0)  # Decay over time

        composite_score = (value_score * 0.4 + engagement_normalized * 0.4 + recency_score * 0.2)

        # Advanced segmentation
        if composite_score >= 80:
            tier = "Platinum"
            priority = "Critical"
        elif composite_score >= 60:
            tier = "Gold"
            priority = "High"
        elif composite_score >= 40:
            tier = "Silver"
            priority = "Medium"
        else:
            tier = "Bronze"
            priority = "Low"

        enriched_record.update({
            "composite_score": round(composite_score, 2),
            "customer_tier": tier,
            "service_priority": priority,
            "premium_processing": True,
            "enrichment_timestamp": datetime.now().isoformat()
        })

        premium_records.append(enriched_record)

result = {"premium_processed": premium_records}
"""
    ]
)
enterprise_etl.add_node("premium_processor", premium_processor)

# Connect the enterprise ETL workflow
enterprise_etl.connect("primary_db", "quality_checker", # mapping removed)
enterprise_etl.connect("quality_checker", "data_merger", # mapping removed)
enterprise_etl.connect("secondary_db", "data_merger", # mapping removed)
enterprise_etl.connect("data_merger", "quality_router", # mapping removed)
enterprise_etl.connect("quality_router", "premium_processor",
                      output_key="true_output", # mapping removed)

# Multiple output destinations
data_warehouse = SQLDatabaseNode(
    id="data_warehouse",
    connection_string="${WAREHOUSE_DB_URL}",
    query="INSERT INTO processed_customers VALUES (%s, %s, %s, %s, %s)",
    operation_type="write",
    batch_size=500
)
enterprise_etl.add_node("data_warehouse", data_warehouse)
enterprise_etl.connect("premium_processor", "data_warehouse", # mapping removed)

```

## 📊 Data Processing Patterns

### Database ETL Pipeline
```python
from kailash.nodes.data import SQLReaderNode, SQLWriterNode

workflow = WorkflowBuilder()

# Extract from source database
workflow.add_node("SQLReaderNode", "extract_source", {}))

# Transform with complex business logic
workflow.add_node("PythonCodeNode", "transform_data", {})

# Data Quality Checks
quality_report = {
    "total_records": len(df),
    "null_values": df.isnull().sum().to_dict(),
    "duplicate_records": df.duplicated().sum()
}

# Handle missing values
numeric_columns = df.select_dtypes(include=[np.number]).columns
for col in numeric_columns:
    df[col] = df[col].fillna(df[col].median())

categorical_columns = df.select_dtypes(include=['object']).columns
for col in categorical_columns:
    df[col] = df[col].fillna('Unknown')

# Business transformations
if 'order_date' in df.columns:
    df['order_date'] = pd.to_datetime(df['order_date'])
    df['order_year'] = df['order_date'].dt.year
    df['order_month'] = df['order_date'].dt.month
    df['order_quarter'] = df['order_date'].dt.quarter

# Customer segmentation logic
if 'customer_id' in df.columns and 'order_value' in df.columns:
    customer_metrics = df.groupby('customer_id').agg({
        'order_value': ['sum', 'mean', 'count'],
        'order_date': ['min', 'max']
    }).round(2)

    customer_metrics.columns = ['total_value', 'avg_order', 'order_count', 'first_order', 'last_order']
    customer_metrics = customer_metrics.reset_index()

    # RFM Analysis (Recency, Frequency, Monetary)
    reference_date = datetime.now()
    customer_metrics['recency'] = (reference_date - pd.to_datetime(customer_metrics['last_order'])).dt.days
    customer_metrics['frequency'] = customer_metrics['order_count']
    customer_metrics['monetary'] = customer_metrics['total_value']

    # Scoring (1-5 scale)
    customer_metrics['recency_score'] = pd.qcut(customer_metrics['recency'], 5, labels=[5,4,3,2,1])
    customer_metrics['frequency_score'] = pd.qcut(customer_metrics['frequency'].rank(method='first'), 5, labels=[1,2,3,4,5])
    customer_metrics['monetary_score'] = pd.qcut(customer_metrics['monetary'], 5, labels=[1,2,3,4,5])

    # Combine scores
    customer_metrics['rfm_score'] = (
        customer_metrics['recency_score'].astype(str) +
        customer_metrics['frequency_score'].astype(str) +
        customer_metrics['monetary_score'].astype(str)
    )

    # Segment classification
    def classify_customer(rfm_score):
        if rfm_score in ['555', '554', '544', '545', '454', '455', '445']:
            return 'Champions'
        elif rfm_score in ['543', '444', '435', '355', '354', '345', '344', '335']:
            return 'Loyal Customers'
        elif rfm_score in ['512', '511', '422', '421', '412', '411', '311']:
            return 'Potential Loyalists'
        elif rfm_score in ['533', '532', '531', '523', '522', '521', '515', '514', '513', '425', '424', '413', '414', '415', '315', '314', '313']:
            return 'New Customers'
        elif rfm_score in ['155', '154', '144', '214', '215', '115', '114']:
            return 'Cannot Lose Them'
        elif rfm_score in ['331', '321', '231', '241', '251']:
            return 'At Risk'
        elif rfm_score in ['132', '123', '122', '212', '211']:
            return "Hibernating"
        else:
            return 'Others'

    customer_metrics['customer_segment'] = customer_metrics['rfm_score'].apply(classify_customer)

    # Merge back with original data
    df = df.merge(customer_metrics[['customer_id', 'customer_segment', 'rfm_score']],
                  on='customer_id', how='left')

# Data enrichment
df['processing_timestamp'] = datetime.now().isoformat()
df['data_quality_score'] = calculate_quality_score(df)

# Final validation
transformed_records = len(df)
if transformed_records < len(pd.DataFrame(data)) * 0.8:  # Lost more than 20% of data
    quality_report['warning'] = f"Significant data loss: {transformed_records} records remaining"

result = {
    "transformed_data": df.to_dict('records'),
    "quality_report": quality_report,
    "transformation_summary": {
        "records_processed": len(df),
        "columns_added": len(df.columns) - len(pd.DataFrame(data).columns),
        "segments_created": df['customer_segment'].nunique() if 'customer_segment' in df.columns else 0
    }
}

def calculate_quality_score(dataframe):
    """Calculate overall data quality score."""
    null_percentage = dataframe.isnull().sum().sum() / (len(dataframe) * len(dataframe.columns))
    duplicate_percentage = dataframe.duplicated().sum() / len(dataframe)
    quality_score = max(0, 1 - null_percentage - duplicate_percentage)
    return round(quality_score * 100, 2)
'''
))

# Load to data warehouse
workflow.add_node("SQLWriterNode", "load_warehouse", {}))

# Connect pipeline
workflow.add_connection("extract_source", "transform_data", "data", "data")
workflow.add_connection("transform_data", "load_warehouse", "transformed_data", "data")

# Execute with database connections
runtime.execute(workflow, parameters={
    "extract_source": {
        "query": "SELECT * FROM orders WHERE created_date >= '2024-01-01'",
        "connection_string": "postgresql://user:pass@localhost/source_db"
    },
    "load_warehouse": {
        "table_name": "processed_orders",
        "connection_string": "postgresql://user:pass@localhost/warehouse_db",
        "if_exists": "replace"
    }
})

```

### Multi-Source Data Integration
```python
from kailash.nodes.logic import MergeNode
from kailash.nodes.api import RestClientNode

workflow = WorkflowBuilder()

# Extract from multiple sources
workflow.add_node("SQLReaderNode", "extract_database", {}))
workflow.add_node("RestClientNode", "extract_api", {}))
workflow.add_node("CSVReaderNode", "extract_files", {}))

# Merge different data sources
workflow.add_node("MergeNode", "merge_sources", {}))

# Transform unified data
workflow.add_node("PythonCodeNode", "transform_unified", {}) else []
api_data = api_response.get('data', []) if isinstance(api_response, dict) else []
file_data = file_data if isinstance(file_data, list) else []

# Data source tracking
for record in db_data:
    record['data_source'] = 'database'
    record['extraction_timestamp'] = datetime.now().isoformat()

for record in api_data:
    record['data_source'] = 'api'
    record['extraction_timestamp'] = datetime.now().isoformat()

for record in file_data:
    record['data_source'] = 'file'
    record['extraction_timestamp'] = datetime.now().isoformat()

# Combine all data sources
unified_data = db_data + api_data + file_data

if not unified_data:
    result = {"error": "No data from any source", "unified_records": []}
else:
    # Create unified DataFrame
    df = pd.DataFrame(unified_data)

    # Schema standardization
    required_columns = ['id', 'name', 'email', 'value', 'data_source']
    for col in required_columns:
        if col not in df.columns:
            df[col] = None

    # Data type standardization
    if 'id' in df.columns:
        df['id'] = df['id'].astype(str)
    if 'value' in df.columns:
        df['value'] = pd.to_numeric(df['value'], errors='coerce').fillna(0)
    if 'email' in df.columns:
        df['email'] = df['email'].str.lower().str.strip()

    # Deduplication across sources (prefer database > api > file)
    source_priority = {'database': 1, 'api': 2, 'file': 3}
    df['source_priority'] = df['data_source'].map(source_priority)

    # Keep record with highest priority for each ID
    df_deduplicated = df.sort_values('source_priority').drop_duplicates(subset=['id'], keep='first')

    # Data quality scoring
    df_deduplicated['completeness_score'] = df_deduplicated.apply(
        lambda row: sum(1 for val in row[required_columns[:-1]] if pd.notna(val)) / (len(required_columns) - 1),
        axis=1
    )

    # Business logic transformations
    df_deduplicated['data_freshness'] = df_deduplicated['data_source'].map({
        'database': 'real_time',
        'api': 'near_real_time',
        'file': 'batch'
    })

    # Integration metadata
    integration_summary = {
        'total_sources': len(df['data_source'].unique()),
        'source_breakdown': df['data_source'].value_counts().to_dict(),
        'deduplication_removed': len(df) - len(df_deduplicated),
        'average_completeness': df_deduplicated['completeness_score'].mean(),
        'integration_timestamp': datetime.now().isoformat()
    }

    result = {
        "unified_records": df_deduplicated.to_dict('records'),
        "integration_summary": integration_summary,
        "data_quality_metrics": {
            "total_records": len(df_deduplicated),
            "source_distribution": df_deduplicated['data_source'].value_counts().to_dict(),
            "average_completeness": round(df_deduplicated['completeness_score'].mean() * 100, 2)
        }
    }
'''
))

# Load to unified data store
workflow.add_node("SQLWriterNode", "load_unified", {}))

# Connect multi-source pipeline
workflow.add_connection("extract_database", "merge_sources", "data", "database_data")
workflow.add_connection("extract_api", "merge_sources", "response", "api_response")
workflow.add_connection("extract_files", "merge_sources", "data", "file_data")
workflow.add_connection("merge_sources", "transform_unified", "merged", "input")
workflow.add_connection("transform_unified", "load_unified", "unified_records", "data")

```

## 🔄 Real-Time ETL Patterns

### Streaming ETL with Change Detection
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

workflow = WorkflowBuilder()

# Continuous data extraction
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "stream_extractor", {}):
    """Extract data that has changed since last processing."""

    # In production, this would connect to change data capture (CDC) systems
    # For demo, simulate with timestamp-based extraction
    current_time = datetime.now()

    # Simulate data with various change types
    extracted_records = []
    for i in range(10):  # Batch of 10 records
        record = {
            'id': f'record_{i}',
            'data': f'Sample data {i}',
            'last_modified': (current_time.timestamp() - i * 60),  # Spread over last 10 minutes
            'change_type': 'INSERT' if i < 5 else 'UPDATE' if i < 8 else 'DELETE',
            'checksum': hashlib.md5(f'Sample data {i}'.encode()).hexdigest()
        }
        extracted_records.append(record)

    return extracted_records

# Extract current batch
extracted_data = extract_incremental_data()

# Add extraction metadata
result = {
    "extracted_records": extracted_data,
    "extraction_timestamp": datetime.now().isoformat(),
    "batch_size": len(extracted_data),
    "extraction_method": "incremental_cdc"
}
'''
))

# Real-time transformation
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "stream_transformer", {})
processing_results = []

for record in extracted_records:
    change_type = record.get('change_type', 'INSERT')

    if change_type == 'DELETE':
        # Handle deletion
        processed_record = {
            'id': record['id'],
            'operation': 'DELETE',
            'processing_timestamp': datetime.now().isoformat(),
            'status': 'marked_for_deletion'
        }
    elif change_type in ['INSERT', 'UPDATE']:
        # Transform data for insert/update
        processed_record = {
            'id': record['id'],
            'operation': change_type,
            'processed_data': record['data'].upper(),  # Example transformation
            'data_quality_score': len(record['data']) / 100,  # Simple quality metric
            'processing_timestamp': datetime.now().isoformat(),
            'source_checksum': record['checksum'],
            'status': 'processed'
        }

    processing_results.append(processed_record)

# Stream processing metrics
processing_summary = {
    'records_processed': len(processing_results),
    'operations_breakdown': {
        'inserts': sum(1 for r in processing_results if r['operation'] == 'INSERT'),
        'updates': sum(1 for r in processing_results if r['operation'] == 'UPDATE'),
        'deletes': sum(1 for r in processing_results if r['operation'] == 'DELETE')
    },
    'average_quality_score': sum(r.get('data_quality_score', 0) for r in processing_results) / len(processing_results),
    'processing_latency_ms': 50  # Simulated processing time
}

result = {
    "processed_records": processing_results,
    "processing_summary": processing_summary,
    "stream_metadata": {
        "processing_timestamp": datetime.now().isoformat(),
        "batch_id": f"batch_{int(datetime.now().timestamp())}"
    }
}
'''
))

# Incremental loading with conflict resolution
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "incremental_loader", {})
loading_results = []

# Simulate database operations
for record in processed_records:
    operation = record['operation']
    record_id = record['id']

    if operation == 'DELETE':
        # Soft delete implementation
        loading_result = {
            'record_id': record_id,
            'operation': 'SOFT_DELETE',
            'status': 'success',
            'deleted_timestamp': datetime.now().isoformat()
        }
    elif operation in ['INSERT', 'UPDATE']:
        # Upsert implementation
        loading_result = {
            'record_id': record_id,
            'operation': 'UPSERT',
            'status': 'success',
            'upserted_timestamp': datetime.now().isoformat(),
            'conflict_resolution': 'timestamp_based'
        }

    loading_results.append(loading_result)

# Track loading metrics
loading_summary = {
    'records_loaded': len(loading_results),
    'successful_loads': sum(1 for r in loading_results if r['status'] == 'success'),
    'failed_loads': sum(1 for r in loading_results if r['status'] == 'failed'),
    'loading_timestamp': datetime.now().isoformat(),
    'throughput_records_per_second': len(loading_results) / 0.1  # Simulated 100ms processing
}

result = {
    "loading_results": loading_results,
    "loading_summary": loading_summary,
    "pipeline_complete": True
}
'''
))

# Connect streaming pipeline
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## 📈 Advanced ETL Patterns

### Data Lake ETL with Partitioning
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

workflow = WorkflowBuilder()

# Extract with metadata
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature:
        self.data_lake_path = data_lake_path
        self.extraction_metadata = {}

    def discover_partitions(self, table_name):
        """Discover available data partitions."""
        partition_path = f"{self.data_lake_path}/{table_name}"

        # Simulate partition discovery (year/month/day structure)
        partitions = []
        base_date = datetime.now() - timedelta(days=30)

        for i in range(30):  # Last 30 days
            partition_date = base_date + timedelta(days=i)
            partition = {
                'year': partition_date.year,
                'month': partition_date.month,
                'day': partition_date.day,
                'partition_path': f"{partition_path}/year={partition_date.year}/month={partition_date.month:02d}/day={partition_date.day:02d}",
                'estimated_size_mb': 150 + (i * 10),  # Simulated growing data
                'record_count': 1000 + (i * 100),
                'last_modified': partition_date.isoformat()
            }
            partitions.append(partition)

        return partitions

    def extract_partition_data(self, partition_info):
        """Extract data from specific partition."""
        # Simulate reading from data lake partition
        records = []
        for i in range(partition_info['record_count']):
            record = {
                'id': f"{partition_info['year']}{partition_info['month']:02d}{partition_info['day']:02d}_{i}",
                'event_timestamp': partition_info['last_modified'],
                'partition_year': partition_info['year'],
                'partition_month': partition_info['month'],
                'partition_day': partition_info['day'],
                'data_value': f"Sample data for {partition_info['partition_path']} record {i}",
                'file_size_bytes': 1024 + (i * 10)
            }
            records.append(record)

        return records

# Initialize extractor and process partitions
extractor = DataLakeExtractor()

# Discover available partitions for processing
target_table = "events"
available_partitions = extractor.discover_partitions(target_table)

# Extract data from recent partitions (last 7 days)
recent_partitions = available_partitions[-7:]  # Last 7 partitions
extracted_data = []

for partition in recent_partitions:
    partition_data = extractor.extract_partition_data(partition)
    extracted_data.extend(partition_data)

# Extraction summary
extraction_summary = {
    'total_partitions_processed': len(recent_partitions),
    'total_records_extracted': len(extracted_data),
    'partitions_metadata': recent_partitions,
    'extraction_timestamp': datetime.now().isoformat(),
    'data_lake_path': extractor.data_lake_path
}

result = {
    "extracted_data": extracted_data,
    "extraction_summary": extraction_summary,
    "partition_info": recent_partitions
}
'''
))

# Transform with schema evolution
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature:
        self.schema_versions = {
            'v1.0': ['id', 'event_timestamp', 'data_value'],
            'v2.0': ['id', 'event_timestamp', 'data_value', 'partition_year', 'partition_month'],
            'v3.0': ['id', 'event_timestamp', 'data_value', 'partition_year', 'partition_month', 'partition_day', 'file_size_bytes']
        }
        self.current_schema = 'v3.0'

    def detect_schema_version(self, sample_record):
        """Detect schema version from record structure."""
        record_fields = set(sample_record.keys())

        for version, fields in sorted(self.schema_versions.items(), reverse=True):
            if set(fields).issubset(record_fields):
                return version

        return 'unknown'

    def transform_to_current_schema(self, records):
        """Transform records to current schema."""
        if not records:
            return []

        # Detect source schema
        source_schema = self.detect_schema_version(records[0])

        transformed_records = []
        for record in records:
            # Start with original record
            transformed = record.copy()

            # Add missing fields based on schema evolution
            if 'partition_year' not in transformed:
                # Extract from timestamp or default
                event_time = pd.to_datetime(transformed.get('event_timestamp', datetime.now()))
                transformed['partition_year'] = event_time.year
                transformed['partition_month'] = event_time.month
                transformed['partition_day'] = event_time.day

            if 'file_size_bytes' not in transformed:
                # Estimate based on data_value length
                transformed['file_size_bytes'] = len(str(transformed.get('data_value', ''))) * 8

            # Add transformation metadata
            transformed['schema_version'] = self.current_schema
            transformed['source_schema'] = source_schema
            transformed['transformation_timestamp'] = datetime.now().isoformat()

            # Data quality enhancements
            transformed['data_completeness'] = self.calculate_completeness(transformed)

            transformed_records.append(transformed)

        return transformed_records

    def calculate_completeness(self, record):
        """Calculate data completeness score."""
        required_fields = self.schema_versions[self.current_schema]
        completed_fields = sum(1 for field in required_fields if record.get(field) is not None)
        return completed_fields / len(required_fields)

# Transform extracted data
transformer = SchemaEvolutionTransformer()
extracted_records = extraction_result.get('extracted_data', [])

# Apply schema transformation
transformed_data = transformer.transform_to_current_schema(extracted_records)

# Calculate transformation metrics
transformation_metrics = {
    'records_transformed': len(transformed_data),
    'schema_migrations_applied': len(set(r.get('source_schema') for r in transformed_data)),
    'average_completeness': sum(r['data_completeness'] for r in transformed_data) / len(transformed_data) if transformed_data else 0,
    'target_schema_version': transformer.current_schema,
    'transformation_timestamp': datetime.now().isoformat()
}

result = {
    "transformed_data": transformed_data,
    "transformation_metrics": transformation_metrics,
    "schema_evolution_summary": {
        "source_schemas_detected": list(set(r.get('source_schema') for r in transformed_data)),
        "target_schema": transformer.current_schema,
        "fields_added": len(transformer.schema_versions[transformer.current_schema])
    }
}
'''
))

# Load to data warehouse with partitioning
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature:
        self.warehouse_path = warehouse_path
        self.partition_strategy = "date_based"

    def create_partition_key(self, record):
        """Create partition key from record."""
        if self.partition_strategy == "date_based":
            year = record.get('partition_year', datetime.now().year)
            month = record.get('partition_month', datetime.now().month)
            return f"year={year}/month={month:02d}"

        return "default"

    def load_to_warehouse(self, transformed_records):
        """Load records to partitioned warehouse."""
        # Group records by partition
        partition_groups = {}
        for record in transformed_records:
            partition_key = self.create_partition_key(record)
            if partition_key not in partition_groups:
                partition_groups[partition_key] = []
            partition_groups[partition_key].append(record)

        # Load each partition
        loading_results = []
        for partition_key, records in partition_groups.items():
            partition_result = {
                'partition_key': partition_key,
                'record_count': len(records),
                'loading_status': 'success',
                'loading_timestamp': datetime.now().isoformat(),
                'warehouse_path': f"{self.warehouse_path}/events/{partition_key}",
                'compression_ratio': 0.7,  # Simulated compression
                'index_created': True
            }
            loading_results.append(partition_result)

        return loading_results

    def create_loading_summary(self, loading_results):
        """Create summary of loading operation."""
        total_records = sum(r['record_count'] for r in loading_results)
        total_partitions = len(loading_results)

        return {
            'total_records_loaded': total_records,
            'partitions_created': total_partitions,
            'average_records_per_partition': total_records / total_partitions if total_partitions > 0 else 0,
            'loading_completed_timestamp': datetime.now().isoformat(),
            'warehouse_location': self.warehouse_path,
            'partition_strategy': self.partition_strategy
        }

# Load transformed data to warehouse
loader = PartitionedDataWarehouseLoader()
transformed_records = transformation_result.get('transformed_data', [])

# Perform partitioned loading
loading_results = loader.load_to_warehouse(transformed_records)
loading_summary = loader.create_loading_summary(loading_results)

# Final ETL pipeline summary
pipeline_summary = {
    'pipeline_execution_id': f"etl_{int(datetime.now().timestamp())}",
    'total_processing_time_seconds': 45,  # Simulated
    'data_freshness_minutes': 5,  # Data is 5 minutes old
    'pipeline_efficiency_score': 0.92,  # 92% efficiency
    'data_quality_score': transformation_result.get('transformation_metrics', {}).get('average_completeness', 0.8)
}

result = {
    "loading_results": loading_results,
    "loading_summary": loading_summary,
    "pipeline_summary": pipeline_summary,
    "warehouse_metadata": {
        "partition_strategy": loader.partition_strategy,
        "total_partitions": len(loading_results),
        "data_warehouse_path": loader.warehouse_path
    }
}
'''
))

# Connect data lake pipeline
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## 🎯 Production ETL Best Practices

### Error Handling and Data Quality
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

workflow = WorkflowBuilder()

# Data quality validation node
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature:
        self.quality_rules = {
            'completeness_threshold': 0.95,  # 95% of fields must be complete
            'uniqueness_threshold': 0.98,    # 98% of IDs must be unique
            'validity_threshold': 0.90,      # 90% of data must pass format validation
            'consistency_threshold': 0.85    # 85% consistency across related fields
        }
        self.quality_report = {}

    def validate_completeness(self, df):
        """Check data completeness."""
        completeness_scores = {}
        for column in df.columns:
            non_null_ratio = df[column].notna().sum() / len(df)
            completeness_scores[column] = non_null_ratio

        overall_completeness = sum(completeness_scores.values()) / len(completeness_scores)

        return {
            'overall_score': overall_completeness,
            'column_scores': completeness_scores,
            'passed': overall_completeness >= self.quality_rules['completeness_threshold'],
            'failing_columns': [col for col, score in completeness_scores.items()
                              if score < self.quality_rules['completeness_threshold']]
        }

    def validate_uniqueness(self, df, unique_columns=['id']):
        """Check data uniqueness."""
        uniqueness_results = {}

        for column in unique_columns:
            if column in df.columns:
                total_count = len(df[column])
                unique_count = df[column].nunique()
                uniqueness_ratio = unique_count / total_count if total_count > 0 else 0

                uniqueness_results[column] = {
                    'uniqueness_ratio': uniqueness_ratio,
                    'duplicate_count': total_count - unique_count,
                    'passed': uniqueness_ratio >= self.quality_rules['uniqueness_threshold']
                }

        overall_passed = all(result['passed'] for result in uniqueness_results.values())

        return {
            'column_results': uniqueness_results,
            'overall_passed': overall_passed
        }

    def validate_formats(self, df):
        """Validate data formats."""
        format_validations = {}

        # Email format validation
        if 'email' in df.columns:
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            valid_emails = df['email'].str.match(email_pattern, na=False).sum()
            total_emails = df['email'].notna().sum()
            format_validations['email'] = {
                'valid_count': valid_emails,
                'total_count': total_emails,
                'validity_ratio': valid_emails / total_emails if total_emails > 0 else 0
            }

        # Date format validation
        date_columns = [col for col in df.columns if 'date' in col.lower()]
        for col in date_columns:
            try:
                pd.to_datetime(df[col], errors='coerce')
                valid_dates = pd.to_datetime(df[col], errors='coerce').notna().sum()
                total_dates = df[col].notna().sum()
                format_validations[col] = {
                    'valid_count': valid_dates,
                    'total_count': total_dates,
                    'validity_ratio': valid_dates / total_dates if total_dates > 0 else 0
                }
            except:
                format_validations[col] = {'validity_ratio': 0, 'error': 'format_validation_failed'}

        return format_validations

    def run_full_validation(self, data):
        """Run comprehensive data quality validation."""
        if not data:
            return {'error': 'No data provided for validation'}

        df = pd.DataFrame(data)

        # Run all validations
        completeness_result = self.validate_completeness(df)
        uniqueness_result = self.validate_uniqueness(df)
        format_result = self.validate_formats(df)

        # Calculate overall quality score
        quality_scores = []
        if completeness_result['overall_score'] is not None:
            quality_scores.append(completeness_result['overall_score'])

        uniqueness_scores = [r['uniqueness_ratio'] for r in uniqueness_result['column_results'].values()]
        if uniqueness_scores:
            quality_scores.append(sum(uniqueness_scores) / len(uniqueness_scores))

        format_scores = [r['validity_ratio'] for r in format_result.values() if 'validity_ratio' in r]
        if format_scores:
            quality_scores.append(sum(format_scores) / len(format_scores))

        overall_quality_score = sum(quality_scores) / len(quality_scores) if quality_scores else 0

        # Determine if data passes quality gates
        quality_passed = (
            completeness_result['passed'] and
            uniqueness_result['overall_passed'] and
            overall_quality_score >= 0.80  # 80% overall threshold
        )

        return {
            'overall_quality_score': round(overall_quality_score * 100, 2),
            'quality_passed': quality_passed,
            'completeness': completeness_result,
            'uniqueness': uniqueness_result,
            'format_validation': format_result,
            'validation_timestamp': datetime.now().isoformat(),
            'record_count': len(df),
            'quality_gates': {
                'completeness_gate': completeness_result['passed'],
                'uniqueness_gate': uniqueness_result['overall_passed'],
                'format_gate': len([r for r in format_result.values() if r.get('validity_ratio', 0) >= 0.9]) > 0
            }
        }

# Run data quality validation
validator = DataQualityValidator()
quality_results = validator.run_full_validation(input_data)

result = quality_results
'''
))

# Error handling and recovery
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature:
        self.error_strategies = {
            'data_quality_failure': 'quarantine_and_alert',
            'transformation_error': 'retry_with_fallback',
            'loading_error': 'retry_with_backoff',
            'network_error': 'exponential_backoff'
        }
        self.recovery_attempts = {}

    def classify_error(self, error_type, error_details):
        """Classify error and determine recovery strategy."""

        error_classification = {
            'error_type': error_type,
            'severity': 'low',
            'recovery_strategy': 'none',
            'alert_required': False,
            'quarantine_data': False
        }

        if error_type == 'data_quality_failure':
            quality_score = error_details.get('overall_quality_score', 0)
            if quality_score < 50:
                error_classification.update({
                    'severity': 'high',
                    'recovery_strategy': 'quarantine_and_alert',
                    'alert_required': True,
                    'quarantine_data': True
                })
            elif quality_score < 80:
                error_classification.update({
                    'severity': 'medium',
                    'recovery_strategy': 'data_cleaning',
                    'alert_required': True
                })

        elif error_type == 'transformation_error':
            error_classification.update({
                'severity': 'medium',
                'recovery_strategy': 'retry_with_fallback',
                'alert_required': True
            })

        elif error_type == 'loading_error':
            error_classification.update({
                'severity': 'high',
                'recovery_strategy': 'retry_with_backoff',
                'alert_required': True
            })

        return error_classification

    def execute_recovery_strategy(self, error_classification, original_data):
        """Execute appropriate recovery strategy."""

        strategy = error_classification['recovery_strategy']
        recovery_result = {
            'strategy_executed': strategy,
            'recovery_timestamp': datetime.now().isoformat(),
            'recovery_successful': False,
            'recovered_data': None,
            'actions_taken': []
        }

        if strategy == 'quarantine_and_alert':
            # Quarantine bad data and alert operators
            recovery_result.update({
                'recovery_successful': True,
                'recovered_data': {'quarantined_records': len(original_data)},
                'actions_taken': [
                    'Data quarantined for manual review',
                    'Alert sent to data quality team',
                    'Pipeline halted for investigation'
                ]
            })

        elif strategy == 'data_cleaning':
            # Attempt automated data cleaning
            cleaned_count = int(len(original_data) * 0.8)  # Simulate 80% recovery
            recovery_result.update({
                'recovery_successful': True,
                'recovered_data': {'cleaned_records': cleaned_count},
                'actions_taken': [
                    f'Automated cleaning recovered {cleaned_count} records',
                    'Invalid records logged for review',
                    'Pipeline continued with cleaned data'
                ]
            })

        elif strategy == 'retry_with_fallback':
            # Retry with simpler transformation logic
            recovery_result.update({
                'recovery_successful': True,
                'recovered_data': {'fallback_processed': len(original_data)},
                'actions_taken': [
                    'Retried with simplified transformation',
                    'Complex transformations skipped',
                    'Basic data structure preserved'
                ]
            })

        return recovery_result

    def handle_etl_error(self, error_type, error_details, original_data):
        """Main error handling orchestration."""

        # Classify the error
        error_classification = self.classify_error(error_type, error_details)

        # Execute recovery strategy
        recovery_result = self.execute_recovery_strategy(error_classification, original_data)

        # Create incident report
        incident_report = {
            'incident_id': f"etl_incident_{int(datetime.now().timestamp())}",
            'incident_timestamp': datetime.now().isoformat(),
            'error_classification': error_classification,
            'recovery_result': recovery_result,
            'data_impact': {
                'original_record_count': len(original_data),
                'recovered_record_count': recovery_result.get('recovered_data', {}).get('cleaned_records', 0),
                'data_loss_percentage': 0 if recovery_result['recovery_successful'] else 100
            },
            'recommendations': self.generate_recommendations(error_classification)
        }

        return incident_report

    def generate_recommendations(self, error_classification):
        """Generate recommendations for preventing similar errors."""

        recommendations = []
        error_type = error_classification['error_type']

        if error_type == 'data_quality_failure':
            recommendations.extend([
                'Implement upstream data validation',
                'Add data quality monitoring alerts',
                'Review data source quality processes',
                'Consider implementing data contracts'
            ])

        elif error_type == 'transformation_error':
            recommendations.extend([
                'Add more comprehensive error handling in transformations',
                'Implement data type validation before transformation',
                'Add unit tests for transformation logic',
                'Consider schema validation'
            ])

        elif error_type == 'loading_error':
            recommendations.extend([
                'Implement connection pooling',
                'Add retry logic with exponential backoff',
                'Monitor target system capacity',
                'Implement circuit breaker pattern'
            ])

        return recommendations

# Handle any errors from previous stages
error_handler = ETLErrorHandler()

# Check if quality validation failed
quality_data = quality_validation_results
data_quality_failed = not quality_data.get('quality_passed', True)

if data_quality_failed:
    # Handle data quality failure
    incident_report = error_handler.handle_etl_error(
        'data_quality_failure',
        quality_data,
        input_data
    )
    result = {
        'error_handled': True,
        'incident_report': incident_report,
        'pipeline_status': 'error_recovery_mode'
    }
else:
    # No errors, continue normally
    result = {
        'error_handled': False,
        'pipeline_status': 'normal_operation',
        'quality_validation': quality_data
    }
'''
))

```

## 🔗 Integration Patterns

### ETL with External Systems
```python
# Complete ETL workflow with external system integration
def create_enterprise_etl_workflow():
    """Create production-ready ETL workflow with full integration."""

    workflow = WorkflowBuilder()

    # 1. Extract from multiple sources
    workflow.add_node("SQLReaderNode", "extract_erp", {}))        # ERP system
    workflow.add_node("RestClientNode", "extract_crm", {}))       # CRM API
    workflow.add_node("CSVReaderNode", "extract_files", {}))      # File uploads

    # 2. Data quality validation
    workflow.add_node("validate_quality", data_quality_check_node)

    # 3. Error handling
    workflow.add_node("handle_errors", error_handler_node)

    # 4. Data transformation
    workflow.add_node("transform_data", advanced_transformation_node)

    # 5. Load to data warehouse
    workflow.add_node("SQLWriterNode", "load_warehouse", {}))

    # 6. Update data catalog
    workflow.add_node("update_catalog", catalog_update_node)

    # 7. Send notifications
    workflow.add_node("notify_completion", notification_node)

    # Connect the complete pipeline
    # [connections implementation]

    return workflow

# Execute with full monitoring
parameters = {
    "extract_erp": {
        "query": "SELECT * FROM transactions WHERE modified_date >= NOW() - INTERVAL '1 day'",
        "connection_string": "postgresql://user:pass@erp-db:5432/production"
    },
    "extract_crm": {
        "url": "https://api.crm.company.com/customers",
        "headers": {"Authorization": "Bearer {api_key}"},
        "method": "GET"
    },
    "load_warehouse": {
        "table_name": "fact_transactions",
        "connection_string": "postgresql://user:pass@warehouse:5432/analytics",
        "if_exists": "append"
    }
}

```

## 📋 ETL Best Practices Checklist

### Data Quality
- [ ] **Schema Validation**: Validate data structure before processing
- [ ] **Completeness Checks**: Ensure required fields are present
- [ ] **Format Validation**: Verify data formats (emails, dates, etc.)
- [ ] **Uniqueness Constraints**: Check for duplicate records
- [ ] **Range Validation**: Ensure numeric values are within expected ranges

### Error Handling
- [ ] **Retry Logic**: Implement exponential backoff for transient failures
- [ ] **Circuit Breakers**: Prevent cascade failures in external systems
- [ ] **Dead Letter Queues**: Handle permanently failed records
- [ ] **Alerting**: Notify operators of critical failures
- [ ] **Rollback Capabilities**: Ability to undo failed transformations

### Performance
- [ ] **Parallel Processing**: Process independent data streams concurrently
- [ ] **Incremental Loading**: Only process changed data
- [ ] **Compression**: Reduce storage and transfer costs
- [ ] **Indexing**: Optimize database access patterns
- [ ] **Resource Monitoring**: Track CPU, memory, and I/O usage

### Monitoring & Observability
- [ ] **Pipeline Metrics**: Track throughput, latency, and error rates
- [ ] **Data Lineage**: Trace data from source to destination
- [ ] **Audit Trails**: Log all data transformations
- [ ] **Quality Metrics**: Monitor data quality over time
- [ ] **SLA Monitoring**: Track against business requirements

### Security & Compliance
- [ ] **Data Encryption**: Encrypt data in transit and at rest
- [ ] **Access Control**: Restrict access based on roles
- [ ] **PII Handling**: Properly handle personally identifiable information
- [ ] **Audit Logging**: Log all data access and modifications
- [ ] **Compliance**: Meet regulatory requirements (GDPR, HIPAA, etc.)

---

*This comprehensive ETL guide covers patterns from simple CSV processing to enterprise-scale data warehousing. Use these patterns as building blocks for your specific data processing needs.*
