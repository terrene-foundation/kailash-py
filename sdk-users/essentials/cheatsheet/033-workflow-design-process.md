# Workflow Design Process

**Version**: 0.2.1 | **Topic**: Workflow Design | **Session 064 Learning**

Systematic approach to designing robust workflows based on real-world finance workflow implementations.

## 🎯 Design Process

### 1. **Start with Data Flow**
Always begin by mapping your data sources, transformations, and outputs.

```python
"""
Data Sources:
- customers.csv (customer profiles, tiers)
- transactions.csv (payment history)
- market_data.csv (external reference data)

Outputs:
- risk_report.json (analysis results)
- alerts.json (high-risk customers)
"""
```

### 2. **Identify All Data Sources Early**
```python
# ✅ PLAN FIRST - Document all data sources
from examples.utils.data_paths import get_input_data_path

# Map all required inputs
input_files = {
    'customers': get_input_data_path("customers.csv"),
    'transactions': get_input_data_path("transactions.csv"),
    'market_data': get_input_data_path("market_data.csv")
}

# Validate all inputs exist before workflow creation
for name, path in input_files.items():
    if not path.exists():
        raise FileNotFoundError(f"Required input file missing: {name} at {path}")
```

### 3. **Use Existing Nodes Before Custom Code**
Check the node catalog before writing PythonCodeNode:

```python
# ❌ DON'T write custom code for standard operations
processor = PythonCodeNode(
    name="csv_reader",
    code="import pandas as pd; result = pd.read_csv(file_path).to_dict('records')"
)

# ✅ USE existing nodes for standard operations
reader = CSVReaderNode(name="csv_reader", file_path=data_path)
```

## 🏗️ Common Design Patterns

### Pattern 1: ETL with Validation
Extract → Transform → Load with validation at each step

```python
def create_etl_workflow():
    workflow = Workflow("etl-pattern", "ETL with Validation")

    # Extract
    source_reader = CSVReaderNode(name="source", file_path=input_path)
    workflow.add_node("source", source_reader)

    # Validate input
    validator = PythonCodeNode.from_function(name="validator", func=validate_input)
    workflow.add_node("validator", validator)

    # Transform
    transformer = PythonCodeNode.from_function(name="transformer", func=transform_data)
    workflow.add_node("transformer", transformer)

    # Load
    writer = JSONWriterNode(name="writer", file_path=output_path)
    workflow.add_node("writer", writer)

    # Connect with error handling
    workflow.connect("source", "validator", mapping={"data": "raw_data"})
    workflow.connect("validator", "transformer", mapping={"result": "validated_data"})
    workflow.connect("transformer", "writer", mapping={"result": "data"})

    return workflow
```

### Pattern 2: Multi-Source Data Integration
Combine multiple data sources with proper ID normalization

```python
def create_integration_workflow():
    workflow = Workflow("integration", "Multi-Source Data Integration")

    # Multiple data sources
    customer_reader = CSVReaderNode(name="customer_reader", file_path=customer_path)
    transaction_reader = CSVReaderNode(name="transaction_reader", file_path=transaction_path)

    # ID normalization (handles format mismatches)
    id_normalizer = PythonCodeNode.from_function(
        name="id_normalizer",
        func=normalize_customer_ids
    )

    # Data merger
    merger = MergeNode(name="merger")

    # Connect sources to normalizer
    workflow.connect("customer_reader", "id_normalizer", mapping={"data": "customers"})
    workflow.connect("transaction_reader", "id_normalizer", mapping={"data": "transactions"})

    return workflow
```

## 🎯 Design Principles

### 1. **Single Responsibility**
Each node should have one clear purpose:

```python
# ❌ BAD - One node doing too much
def process_everything(data):
    # Reads CSV, validates, transforms, analyzes, and writes output
    # Too many responsibilities!
    pass

# ✅ GOOD - Each node has one responsibility
reader = CSVReaderNode(name="reader")           # Read data
validator = PythonCodeNode.from_function(name="validator", func=validate)  # Validate
transformer = PythonCodeNode.from_function(name="transformer", func=transform)  # Transform
writer = JSONWriterNode(name="writer")          # Write results
```

### 2. **Explicit Data Flow**
Make data transformations obvious in connections:

```python
# ✅ CLEAR data flow with descriptive mapping names
workflow.connect("customer_reader", "risk_calculator",
                mapping={"data": "customer_profiles"})
workflow.connect("transaction_reader", "risk_calculator",
                mapping={"data": "transaction_history"})
workflow.connect("risk_calculator", "ai_analyzer",
                mapping={"result": "calculated_metrics"})
```

### 3. **Fail-Fast Validation**
Validate inputs early in the pipeline:

```python
def validate_workflow_inputs(customers: list, transactions: list) -> dict:
    """Validate all inputs before processing begins."""
    errors = []

    # Check required fields
    if not customers:
        errors.append("Customer data is empty")

    if not transactions:
        errors.append("Transaction data is empty")

    # Validate data quality
    customer_df = pd.DataFrame(customers)
    required_customer_fields = ['customer_id', 'tier']
    missing_fields = [f for f in required_customer_fields if f not in customer_df.columns]

    if missing_fields:
        errors.append(f"Missing customer fields: {missing_fields}")

    if errors:
        return {'result': None, 'errors': errors, 'valid': False}

    return {'result': {'customers': customers, 'transactions': transactions}, 'valid': True}
```

## 🚀 Quick Start Checklist

When designing a new workflow:

1. **📋 Plan**: Document data sources, transformations, outputs
2. **🔍 Research**: Check existing nodes before writing custom code
3. **⚡ Start Simple**: Build basic flow first, add complexity later
4. **🧪 Test Early**: Test each function independently before creating nodes
5. **🔗 Connect**: Use descriptive mapping names for clarity
6. **✅ Validate**: Add input validation and error handling
7. **📊 Monitor**: Include progress tracking for long-running workflows
8. **📝 Document**: Add clear descriptions for each node and connection

## 🔧 Workflow Validation Checklist

- [ ] All PythonCodeNode code >3 lines uses `.from_function()`
- [ ] All input files exist and are accessible
- [ ] All node names end with "Node" suffix
- [ ] All connections use descriptive mapping names
- [ ] Input validation at workflow entry points
- [ ] Error handling for external operations
- [ ] ID normalization for multi-source data
- [ ] Output files use centralized data paths

## 💡 Pro Tips

### Data Integration
- **Always normalize IDs early** to prevent downstream mismatches
- **Use MergeNode** for combining data from multiple sources
- **Handle datetime serialization** for JSON outputs

### Performance
- **Batch large datasets** (>1000 records) for processing
- **Use existing nodes** instead of custom code when possible
- **Cache expensive operations** when appropriate

### Debugging
- **Test functions independently** before creating nodes
- **Use descriptive node and connection names**
- **Add progress logging** for long-running workflows

---

**Remember**: Good workflow design is like good architecture - it should be obvious how it works!

*Related: [034-data-integration-patterns.md](034-data-integration-patterns.md), [035-production-readiness.md](035-production-readiness.md)*
