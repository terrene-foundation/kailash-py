# Workflows - Creation & Execution Patterns

*Master workflow building, connections, and execution*

## 🎯 **Prerequisites**
- Completed [Fundamentals](01-fundamentals.md) - Core SDK concepts
- Understanding of nodes and parameters

## 🏗️ **Workflow Creation Patterns**

### **Basic Workflow Structure**
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Always create with ID and name
workflow = WorkflowBuilder()

# Add nodes with configuration
workflow.add_node("CSVReaderNode", "reader", {}),
    file_path="/data/input.csv",
    has_header=True,
    delimiter=","
)

# Connect nodes to create data flow
workflow.add_connection("reader", "processor", "data", "input_data")

# Validate structure before execution
workflow.validate()

# Execute with runtime
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

### **Progressive Workflow Building**
```python
def build_data_pipeline():
    """Build a complete data processing pipeline"""
    workflow = WorkflowBuilder()

    # 1. Data Input Layer
    workflow.add_node("CSVReaderNode", "csv_reader", {}),
        file_path="/data/customers.csv",
        has_header=True,
        delimiter=","
    )

    workflow.add_node("JSONReaderNode", "json_config", {}),
        file_path="/config/processing_rules.json"
    )

    # 2. Data Processing Layer
    workflow.add_node("PythonCodeNode", "validator", {})

valid_customers = []
invalid_customers = []

for customer in customer_data:
    if (customer.get("email") and "@" in customer["email"] and
        customer.get("age", 0) >= 18):
        valid_customers.append(customer)
    else:
        invalid_customers.append(customer)

result = {
    "valid": valid_customers,
    "invalid": invalid_customers,
    "validation_summary": {
        "total": len(customer_data),
        "valid_count": len(valid_customers),
        "invalid_count": len(invalid_customers),
        "success_rate": len(valid_customers) / len(customer_data) if customer_data else 0
    }
}
''',
        input_types={"customer_data": list}
    ))

    workflow.add_node("PythonCodeNode", "enricher", {})
processing_rules = inputs.get("processing_rules", {})

# Apply processing rules to enrich customer data
enriched_customers = []

for customer in valid_data:
    enriched = customer.copy()

    # Add calculated fields
    enriched["full_name"] = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
    enriched["age_group"] = "senior" if customer.get("age", 0) >= 65 else "adult"
    enriched["email_domain"] = customer["email"].split("@")[1] if "@" in customer["email"] else ""

    # Apply rules from config
    for rule in processing_rules.get("enrichment_rules", []):
        if rule["condition"] == "age_based_discount":
            enriched["discount_rate"] = 0.1 if customer.get("age", 0) >= 65 else 0.05

    enriched_customers.append(enriched)

result = {
    "enriched": enriched_customers,
    "enrichment_stats": {
        "processed_count": len(enriched_customers),
        "rules_applied": len(processing_rules.get("enrichment_rules", []))
    }
}
''',
        input_types={"valid_data": list, "processing_rules": dict}
    ))

    # 3. Data Output Layer
    workflow.add_node("CSVWriterNode", "csv_writer", {}),
        file_path="/data/enriched_customers.csv",
        include_header=True
    )

    workflow.add_node("JSONWriterNode", "json_writer", {}),
        file_path="/data/processing_summary.json",
        indent=2
    )

    # 4. Connect the pipeline
    workflow.add_connection("csv_reader", "validator", "data", "customer_data")
    workflow.add_connection("validator", "enricher", "valid", "valid_data")
    workflow.add_connection("json_config", "enricher", "data", "processing_rules")
    workflow.add_connection("enricher", "csv_writer", "enriched", "data")
    workflow.add_connection("enricher", "json_writer", "enrichment_stats", "data")

    return workflow

```

## 🔗 **Connection Patterns & Data Flow**

### **Basic Connection Types**
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

# 1. Automatic mapping (when names match)
workflow = WorkflowBuilder()
workflow.add_connection("reader", "result", "processor", "input")
# Automatically maps: reader.data → processor.data

# 2. Explicit simple mapping
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# 3. Nested data access with dot notation
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

### **Advanced Connection Patterns**
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

# Fan-out: One source to multiple targets
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Fan-in: Multiple sources to one target
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Conditional routing with SwitchNode
workflow = WorkflowBuilder()
workflow.add_node("SwitchNode", "router", {}),
    conditions=[
        {"output": "urgent", "expression": "priority == 'high' and urgency > 8"},
        {"output": "normal", "expression": "priority in ['medium', 'low']"},
        {"output": "review", "expression": "requires_review == True"}
    ],
    default_output="unprocessed"
)

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

### **Data Transformation Chains**
```python
# Create a multi-stage transformation pipeline
def create_transformation_chain():
    workflow = WorkflowBuilder()
workflow.method()  # Example
    # Stage 1: Raw data cleaning
    workflow.add_node("PythonCodeNode", "cleaner", {})

cleaned_data = []
for item in raw_data:
    if item and isinstance(item, dict):
        # Clean and normalize
        cleaned = {
            "id": str(item.get("id", "")).strip(),
            "name": item.get("name", "").strip().title(),
            "email": item.get("email", "").strip().lower(),
            "value": float(item.get("value", 0))
        }
        if cleaned["id"] and cleaned["name"]:
            cleaned_data.append(cleaned)

result = {"cleaned": cleaned_data, "cleaned_count": len(cleaned_data)}
''',
        input_types={"raw_data": list}
    ))

    # Stage 2: Data validation
    workflow.add_node("PythonCodeNode", "validator", {})

import re
email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

validated_data = []
validation_errors = []

for item in cleaned_data:
    errors = []

    # Validate email
    if not re.match(email_pattern, item["email"]):
        errors.append("invalid_email")

    # Validate value range
    if item["value"] < 0 or item["value"] > 10000:
        errors.append("value_out_of_range")

    if not errors:
        validated_data.append(item)
    else:
        validation_errors.append({"item": item, "errors": errors})

result = {
    "validated": validated_data,
    "errors": validation_errors,
    "validation_summary": {
        "passed": len(validated_data),
        "failed": len(validation_errors),
        "success_rate": len(validated_data) / (len(validated_data) + len(validation_errors)) if (validated_data or validation_errors) else 0
    }
}
''',
        input_types={"cleaned_data": list}
    ))

    # Stage 3: Data enrichment
    workflow.add_node("PythonCodeNode", "enricher", {})

enriched_data = []

for item in validated_data:
    enriched = item.copy()

    # Add computed fields
    enriched["email_domain"] = item["email"].split("@")[1]
    enriched["value_category"] = (
        "high" if item["value"] > 1000 else
        "medium" if item["value"] > 100 else
        "low"
    )
    enriched["name_length"] = len(item["name"])
    enriched["processed_timestamp"] = "2024-01-01T10:00:00Z"

    enriched_data.append(enriched)

result = {
    "enriched": enriched_data,
    "enrichment_stats": {
        "total_enriched": len(enriched_data),
        "fields_added": 4
    }
}
''',
        input_types={"validated_data": list}
    ))

    # Connect the transformation chain
    workflow.add_connection("cleaner", "validator", "cleaned", "cleaned_data")
    workflow.add_connection("validator", "enricher", "validated", "validated_data")

    return workflow

```

## 🐍 **PythonCodeNode Mastery**

### **Essential PythonCodeNode Patterns**
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

# ✅ CORRECT PythonCodeNode pattern
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature and item.get("value", 0) > threshold:
        processed_items.append({
            "id": item.get("id"),
            "processed_value": item["value"] * 2,
            "category": "high" if item["value"] > 500 else "normal"
        })

# ✅ ALWAYS wrap output in result dictionary
result = {
    "processed": processed_items,
    "total_processed": len(processed_items),
    "threshold_used": threshold
}
''',
    input_types={               # ✅ CRITICAL: Define all input types
        "data": list,           # From connected nodes or runtime
        "threshold": int        # From configuration or runtime
    }
))

```

### **Advanced PythonCodeNode Patterns**
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

# Complex data processing with error handling
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature.isoformat(),
    "items_processed": 0,
    "errors": [],
    "batches": 0
}

processed_results = []
batch_size = config.get("batch_size", 100)

# Process in batches
for i in range(0, len(input_data), batch_size):
    batch = input_data[i:i + batch_size]
    stats["batches"] += 1

    batch_results = []
    for item in batch:
        try:
            # Complex processing logic
            if config["mode"] == "advanced":
                processed_item = {
                    "id": item.get("id"),
                    "original_value": item.get("value", 0),
                    "processed_value": item.get("value", 0) ** 2,
                    "metadata": {
                        "batch_number": stats["batches"],
                        "processing_mode": config["mode"],
                        "timestamp": datetime.now().isoformat()
                    }
                }
            else:
                processed_item = {
                    "id": item.get("id"),
                    "value": item.get("value", 0) * 2
                }

            batch_results.append(processed_item)
            stats["items_processed"] += 1

        except Exception as e:
            error_info = {
                "item_id": item.get("id", "unknown"),
                "error": str(e),
                "batch": stats["batches"]
            }
            stats["errors"].append(error_info)

            if debug_mode:
                print(f"Error processing item {item.get('id')}: {e}")

    processed_results.extend(batch_results)

stats["end_time"] = datetime.now().isoformat()
stats["success_rate"] = stats["items_processed"] / len(input_data) if input_data else 0

result = {
    "processed_data": processed_results,
    "processing_stats": stats,
    "summary": {
        "total_input": len(input_data),
        "total_output": len(processed_results),
        "error_count": len(stats["errors"]),
        "batch_count": stats["batches"]
    }
}
''',
    input_types={
        "input_data": list,
        "config": dict,
        "debug_mode": bool
    }
))

```

### **PythonCodeNode with External Libraries**
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

# Using external libraries safely
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "data_science_processor", {})
try:
    import pandas as pd
    import numpy as np
    from datetime import datetime
except ImportError as e:
    result = {"error": f"Missing required library: {e}", "success": False}
else:
    try:
        # Convert to pandas DataFrame
        # Access inputs
        data = inputs.get("data", [])

        # Convert to pandas DataFrame
        df = pd.DataFrame(data)

        # Perform data science operations
        df['value_normalized'] = (df['value'] - df['value'].mean()) / df['value'].std()
        df['value_percentile'] = df['value'].rank(pct=True)
        df['category'] = pd.cut(df['value'], bins=3, labels=['low', 'medium', 'high'])

        # Statistical analysis
        stats = {
            "mean": float(df['value'].mean()),
            "median": float(df['value'].median()),
            "std": float(df['value'].std()),
            "min": float(df['value'].min()),
            "max": float(df['value'].max()),
            "count": len(df)
        }

        # Convert back to list of dictionaries
        processed_data = df.to_dict('records')

        result = {
            "processed_data": processed_data,
            "statistics": stats,
            "success": True,
            "processing_timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        result = {
            "error": str(e),
            "success": False,
            "original_data_count": len(data) if 'data' in locals() else 0
        }
''',
    input_types={"data": list}
))

```

## 📁 **Directory & File Processing**

### **DirectoryReaderNode Patterns**
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

# Basic directory scanning
workflow = WorkflowBuilder()
workflow.add_node("DirectoryReaderNode", "scanner", {}),
    directory_path="/data/inputs",
    file_pattern="*.csv",
    recursive=True,
    include_metadata=True,
    max_files=100
)

# Advanced file discovery with filtering
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature,
    "filtered_files": 0,
    "size_filtered": 0,
    "date_filtered": 0
}

# Filter criteria
max_file_size = 50 * 1024 * 1024  # 50MB
min_date = datetime.now() - timedelta(days=30)  # Last 30 days

for file_path in file_list:
    try:
        file_stats = os.stat(file_path)
        file_size = file_stats.st_size
        file_date = datetime.fromtimestamp(file_stats.st_mtime)

        # Apply filters
        if file_size > max_file_size:
            processing_stats["size_filtered"] += 1
            continue

        if file_date < min_date:
            processing_stats["date_filtered"] += 1
            continue

        # File passes filters
        discovered_files.append({
            "path": file_path,
            "size": file_size,
            "modified_date": file_date.isoformat(),
            "extension": os.path.splitext(file_path)[1],
            "basename": os.path.basename(file_path)
        })
        processing_stats["filtered_files"] += 1

    except Exception as e:
        print(f"Error processing {file_path}: {e}")

result = {
    "discovered_files": discovered_files,
    "processing_stats": processing_stats,
    "filter_criteria": {
        "max_size_mb": max_file_size / (1024 * 1024),
        "min_age_days": 30
    }
}
''',
    input_types={"file_list": list}
))

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

### **Batch File Processing**
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

# Process multiple files in sequence
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

    try:
        file_data = None
        record_count = 0

        if file_extension == ".csv":
            file_data = []
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    file_data.append(row)
                    record_count += 1

        elif file_extension == ".json":
            with open(file_path, 'r', encoding='utf-8') as f:
                file_data = json.load(f)
                record_count = len(file_data) if isinstance(file_data, list) else 1

        if file_data is not None:
            processed_files.append({
                "file_path": file_path,
                "file_name": file_info["basename"],
                "record_count": record_count,
                "file_size": file_info["size"],
                "data": file_data[:100] if isinstance(file_data, list) else file_data,  # Limit data size
                "processing_status": "success"
            })
            total_records += record_count

    except Exception as e:
        processing_errors.append({
            "file_path": file_path,
            "error": str(e),
            "file_size": file_info.get("size", 0)
        })

result = {
    "processed_files": processed_files,
    "processing_errors": processing_errors,
    "summary": {
        "total_files_processed": len(processed_files),
        "total_errors": len(processing_errors),
        "total_records": total_records,
        "success_rate": len(processed_files) / len(discovered_files) if discovered_files else 0
    }
}
''',
    input_types={"discovered_files": list}
))

```

## 🔄 **Cyclic Workflows & Convergence**

### **Basic Iterative Processing**
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

# Simple iterative optimization
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature < 0.01
iteration += 1

result = {
    "current_value": new_value,
    "target_value": target_value,
    "learning_rate": learning_rate,
    "iteration": iteration,
    "error": error,
    "converged": converged,
    "adjustment": adjustment
}
''',
    input_types={
        "current_value": float,
        "target_value": float,
        "learning_rate": float,
        "iteration": int
    }
))

# Create cyclic connection
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

### **Complex State Preservation**
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

# Advanced cycle with complex state
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature for item in new_data) / len(new_data)

# Update state
state["history"].append(current_result)
state["iteration_count"] += 1

# Track best result
if state["best_result"] is None or current_result > state["best_result"]:
    state["best_result"] = current_result

# Convergence tracking
state["convergence_window"].append(current_result)
if len(state["convergence_window"]) > 5:
    state["convergence_window"].pop(0)

# Check stability
if len(state["convergence_window"]) >= 5:
    variance = sum((x - sum(state["convergence_window"])/5)**2 for x in state["convergence_window"]) / 5
    if variance < 0.1:
        state["stable_iterations"] += 1
    else:
        state["stable_iterations"] = 0

# Convergence criteria
converged = (
    state["stable_iterations"] >= 3 and
    state["iteration_count"] >= 10
) or state["iteration_count"] >= 50

result = {
    "state": state,
    "current_result": current_result,
    "converged": converged,
    "convergence_info": {
        "variance": variance if 'variance' in locals() else 0,
        "stable_iterations": state["stable_iterations"],
        "window_size": len(state["convergence_window"])
    }
}
''',
    input_types={"state": dict, "new_data": list}
))

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## 🚀 **Workflow Execution Patterns**

### **Basic Execution**
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

# Standard execution pattern
runtime = LocalRuntime()

# Execute with default configuration
runtime = LocalRuntime()
runtime.execute(workflow.build(), workflow)

# Execute with parameter overrides
runtime = LocalRuntime()
# Parameters setup
workflow.{
    "reader": {"file_path": "custom_data.csv"},
    "processor": {"threshold": 150, "debug_mode": True}
})

```

### **Advanced Execution with Monitoring**
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

# Enhanced execution with monitoring
runtime = LocalRuntime(
    max_workers=4,
    timeout=600.0,
    enable_logging=True
)

# Execute with comprehensive monitoring
start_time = time.time()
try:
runtime = LocalRuntime()
runtime.execute(workflow.build(), workflow,
# Parameters setup
workflow.{
            "data_source": {"file_path": "/data/large_dataset.csv"},
            "processor": {"batch_size": 1000, "enable_profiling": True}
        },
        timeout=300.0
    )

    execution_time = time.time() - start_time

    print(f"✅ Execution completed successfully!")
    print(f"Run ID: {run_id}")
    print(f"Execution time: {execution_time:.2f} seconds")
    print(f"Results keys: {list(results.keys())}")

    # Access specific results
    if "processor" in results:
        processor_result = results["processor"]
        print(f"Processed items: {processor_result.get('total_processed', 0)}")

except Exception as e:
    execution_time = time.time() - start_time
    print(f"❌ Execution failed after {execution_time:.2f} seconds")
    print(f"Error: {e}")

```

## 📊 **Best Practices Summary**

### **Workflow Design Principles**
1. **Clear naming**: Use descriptive node IDs and workflow names
2. **Logical flow**: Organize nodes in logical processing order
3. **Error handling**: Include validation and error recovery
4. **Modularity**: Break complex logic into separate nodes
5. **Documentation**: Include meaningful descriptions

### **PythonCodeNode Best Practices**
1. **Always include name**: Required parameter for all PythonCodeNode instances
2. **Define input_types**: Critical for proper parameter mapping
3. **Handle missing inputs**: Use try/except for optional parameters
4. **Wrap outputs**: Always return results in a dictionary
5. **Error resilience**: Handle exceptions gracefully

### **Connection Best Practices**
1. **Explicit mapping**: Use clear output→input mapping names
2. **Validate connections**: Ensure data types match between nodes
3. **Logical flow**: Connect nodes in processing order
4. **Handle branching**: Use SwitchNode for conditional routing
5. **Merge properly**: Use MergeNode for combining data streams

## 🔗 **Related Guides**

**Essential References:**
- **[Fundamentals](01-fundamentals.md)** - Core SDK concepts and node basics
- **[Quick Reference](QUICK_REFERENCE.md)** - PythonCodeNode patterns and common fixes

**Next Steps:**
- **[Advanced Features](03-advanced-features.md)** - Enterprise and advanced patterns
- **[Production](04-production.md)** - Production deployment and security
- **[Troubleshooting](05-troubleshooting.md)** - Debug and solve workflow issues

---

**Master these workflow patterns to build robust, scalable data processing pipelines!**
