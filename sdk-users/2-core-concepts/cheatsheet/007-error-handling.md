# Error Handling & Recovery

## Basic Error Handling Pattern
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.exceptions import WorkflowValidationError, NodeExecutionError

# Always wrap workflow operations in try-catch
try:
    workflow = WorkflowBuilder()
    runtime = LocalRuntime()

    # Validate before execution
    workflow.validate()

    # Execute with proper error handling
    results, run_id = runtime.execute(workflow, parameters={
        "reader": {"file_path": "/data/input.csv"}
    })

    print(f"✅ Success! Run ID: {run_id}")

except WorkflowValidationError as e:
    print(f"❌ Workflow structure error: {e}")
    print("Check node connections and parameters")

except NodeExecutionError as e:
    print(f"❌ Node '{e.node_id}' failed: {e}")
    print(f"Error details: {e.details}")

except FileNotFoundError as e:
    print(f"❌ File not found: {e}")
    print("Check file paths and permissions")

except Exception as e:
    print(f"❌ Unexpected error: {e}")
    print("Check logs for more details")

```

## Robust Workflow Pattern
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
runtime = LocalRuntime()

# Error-resistant workflow with fallbacks
def safe_file_reader(file_path: str) -> dict:
    """Safely read file with error handling"""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                data = f.read()
            return {"data": data, "success": True}
        else:
            return {"data": "", "success": False, "error": "File not found"}
    except Exception as e:
        return {"data": "", "success": False, "error": str(e)}

workflow.add_node("file_reader", PythonCodeNode.from_function(
    name="file_reader",
    func=safe_file_reader,
    input_types={"file_path": str}
))

# Error handling in data processing
def safe_data_processor(data: list) -> dict:
    """Process data with comprehensive error handling"""
    processed = []
    errors = []
    for item in data:
        try:
            if isinstance(item, dict) and "value" in item:
                processed.append({
                    "id": item.get("id", "unknown"),
                    "result": item["value"] * 2
                })
            else:
                errors.append({"item": item, "error": "Invalid format"})
        except Exception as e:
            errors.append({"item": item, "error": str(e)})

    return {
        "processed": processed,
        "errors": errors,
        "success_rate": len(processed) / (len(processed) + len(errors)) if (processed or errors) else 0
    }

workflow.add_node("data_processor", PythonCodeNode.from_function(
    name="data_processor",
    func=safe_data_processor,
    input_types={"data": list}
))

```

## Database-Specific Retry Configuration
```python
from kailash.nodes.data.async_sql import RetryConfig, RetryMetrics
from kailash.sdk_exceptions import RetryExhaustedException

# Use database-optimized retry settings
# SQLite: 10 retries, 30s timeout (file-level locking)
sqlite_config = RetryConfig.for_database("sqlite")

# PostgreSQL: 5 retries, 10s timeout (MVCC)
postgres_config = RetryConfig.for_database("postgresql")

# MySQL: 5 retries, 15s timeout (InnoDB MVCC)
mysql_config = RetryConfig.for_database("mysql")

# Apply to AsyncSQLNode
from kailash.nodes.data import AsyncSQLNode

node = AsyncSQLNode(
    node_id="db_query",
    query="SELECT * FROM users WHERE active = :active",
    retry_config=sqlite_config  # Database-specific optimization
)
```

## Handling Retry Exhaustion
```python
from kailash.sdk_exceptions import RetryExhaustedException

try:
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow, parameters={
        "db_query": {"active": True}
    })
    print("✅ Query executed successfully")

except RetryExhaustedException as e:
    # Raised when all retry attempts are exhausted
    print(f"❌ Operation: {e.operation}")
    print(f"❌ Attempts: {e.attempts}")
    print(f"❌ Last error: {e.last_error}")
    print(f"❌ Total wait time: {e.total_wait_time:.2f}s")

    # Take corrective action
    if "database is locked" in str(e.last_error):
        print("💡 Consider switching to PostgreSQL for better concurrency")
    elif "connection" in str(e.last_error).lower():
        print("💡 Check database connection settings")

except Exception as e:
    print(f"❌ Unexpected error: {e}")
```

## Monitoring Retry Behavior
```python
from kailash.nodes.data.async_sql import RetryConfig, RetryMetrics

# Create metrics tracker
metrics = RetryMetrics()

# Attach to retry config
config = RetryConfig.for_database("sqlite", metrics=metrics)

# Use in node
node = AsyncSQLNode(
    node_id="db_query",
    query="INSERT INTO orders (id, amount) VALUES (:id, :amount)",
    retry_config=config
)

# After workflow execution, check metrics
snapshot = metrics.get_metrics()
print(f"Total operations: {snapshot['total_operations']}")
print(f"Total retries: {snapshot['total_retries']}")
print(f"Failed operations: {snapshot['failed_operations']}")
print(f"Average retries: {snapshot['avg_retries_per_operation']:.2f}")
print(f"Failure rate: {snapshot['failure_rate']:.2%}")
print(f"Retry distribution: {snapshot['retry_histogram']}")

# Example output:
# Total operations: 100
# Total retries: 45
# Failed operations: 2
# Average retries: 0.45
# Failure rate: 2.00%
# Retry distribution: {0: 55, 1: 30, 2: 10, 3: 3, 5: 2}
```

## Retry Logic Pattern (Manual)
```python
import time

def execute_with_retry(workflow, parameters=None, max_retries=3):
    """Execute workflow with exponential backoff retry"""
    for attempt in range(max_retries):
        try:
            runtime = LocalRuntime()
            results, run_id = runtime.execute(workflow, parameters=parameters)
            return results, run_id

        except Exception as e:
            if attempt == max_retries - 1:
                raise  # Re-raise on final attempt

            wait_time = 2 ** attempt  # Exponential backoff
            print(f"Attempt {attempt + 1} failed: {e}")
            print(f"Retrying in {wait_time} seconds...")
            time.sleep(wait_time)

    raise Exception("All retry attempts failed")

# Usage
try:
    results, run_id = execute_with_retry(workflow, max_retries=3)
    print("✅ Workflow executed successfully")
except Exception as e:
    print(f"❌ Workflow failed after all retries: {e}")

```

## Error Validation Checklist
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

# Pre-execution validation
def validate_workflow_safely(workflow):
    """Comprehensive workflow validation"""
    try:
        # 1. Basic structure validation
        workflow.validate()

        # 2. Check node connections
        unconnected = workflow.get_unconnected_nodes()
        if unconnected:
            print(f"⚠️ Unconnected nodes: {unconnected}")

        # 3. Validate required parameters
        for node_id, node in workflow.nodes.items():
            required_params = getattr(node, 'required_parameters', [])
            missing = [p for p in required_params if not hasattr(node, p)]
            if missing:
                print(f"⚠️ Node {node_id} missing: {missing}")

        return True

    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return False

# Usage before execution
if validate_workflow_safely(workflow):
runtime = LocalRuntime()
runtime.execute(workflow.build(), workflow)
else:
    print("Fix validation errors before execution")

```

## Common Error Scenarios

### Missing File Errors
```python
# Handle missing input files
parameters = {
    "reader": {
        "file_path": "/data/input.csv",
        "fallback_path": "/data/backup.csv",  # Alternative file
        "create_if_missing": False
    }
}

```

### Memory Errors
```python
# Handle large datasets
parameters = {
    "processor": {
        "batch_size": 1000,     # Process in smaller batches
        "max_memory_mb": 512,   # Memory limit
        "disk_cache": True      # Use disk for large data
    }
}

```

### Network Errors
```python
# Handle API timeouts
parameters = {
    "api_node": {
        "timeout": 30,          # Connection timeout
        "retry_count": 3,       # Retry attempts
        "retry_delay": 5        # Delay between retries
    }
}

```

## Next Steps
- [Common Mistakes](018-common-mistakes-to-avoid.md) - What to avoid
- [Troubleshooting](../developer/07-troubleshooting.md) - Advanced debugging
- [Security](008-security-configuration.md) - Secure error handling
