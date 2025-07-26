# Workflow Composition & Data Flow Mastery

*Advanced patterns for building complex workflows with proper data flow*

## 🏗️ Workflow Building Fundamentals

### Basic Composition Pattern
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# ALWAYS start with this pattern
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Add nodes with clear naming
workflow.add_node("CSVReaderNode", "step_1_extract", {}),
    file_path="/data/input.csv", has_header=True)

workflow.add_node("step_2_transform", PythonCodeNode.from_function(
    name="step_2_transform",
    func=lambda data: {'processed': len(data)}
))

workflow.add_node("JSONWriterNode", "step_3_load", {}),
    file_path="/data/output.json")

# Connect in sequence
workflow.add_connection("step_1_extract", "step_2_transform", "data", "data")
workflow.add_connection("step_2_transform", "step_3_load", "processed", "data")

# Execute
results, run_id = runtime.execute(workflow.build())

```

## 🔄 Parallel Processing Pattern

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

# Fan-out: Split data for parallel processing
def workflow.()  # Type signature example -> dict:
    """Split data into chunks for parallel processing."""
    chunk_size = len(data) // num_workers
    chunks = []
    for i in range(0, len(data), chunk_size):
        chunks.append(data[i:i + chunk_size])

    return {
        "chunk_1": chunks[0] if len(chunks) > 0 else [],
        "chunk_2": chunks[1] if len(chunks) > 1 else [],
        "chunk_3": chunks[2] if len(chunks) > 2 else []
    }

# Add splitter
splitter = PythonCodeNode.from_function(
    name="splitter", func=split_data_for_parallel
)
workflow = WorkflowBuilder()
workflow.add_node("splitter", splitter)

# Parallel workers
def workflow.()  # Type signature example -> dict:
    """Process chunk of data."""
    processed = []
    for item in chunk_data:
        processed.append({
            "id": item.get("id"),
            "processed_by": worker_id,
            "result": item.get("value", 0) * 2
        })
    return {"processed": processed}

for i in range(3):
    worker = PythonCodeNode.from_function(
        name=f"worker_{i+1}",
        func=lambda chunk_data, worker_id=f"worker_{i+1}": process_chunk(chunk_data, worker_id)
    )
workflow = WorkflowBuilder()
workflow.add_node(f"worker_{i+1}", worker)

    # Connect splitter to each worker
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Fan-in: Merge results
workflow = WorkflowBuilder()
workflow.add_node("MergeNode", "merger", {}))
for i in range(3):
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## 🌟 Conditional Branching Pattern

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

# Route data based on conditions
def workflow.()  # Type signature example -> dict:
    """Classify data for conditional routing."""
    amount = data.get("amount", 0)

    if amount > 1000:
        return {"high_value": data, "route": "high"}
    elif amount > 100:
        return {"medium_value": data, "route": "medium"}
    else:
        return {"low_value": data, "route": "low"}

classifier = PythonCodeNode.from_function(
    name="classifier", func=classify_data
)
workflow = WorkflowBuilder()
workflow.add_node("classifier", classifier)

# Different processing for each branch
def workflow.()  # Type signature example -> dict:
    return {
        "category": "premium",
        "discount": data.get("amount", 0) * 0.1,
        "priority": "high"
    }

def workflow.()  # Type signature example -> dict:
    return {
        "category": "standard",
        "discount": data.get("amount", 0) * 0.05,
        "priority": "normal"
    }

# Add processors
high_processor = PythonCodeNode.from_function(
    name="high_processor", func=process_high_value
)
standard_processor = PythonCodeNode.from_function(
    name="standard_processor", func=process_standard
)

workflow = WorkflowBuilder()
workflow.add_node("high_processor", high_processor)
workflow = WorkflowBuilder()
workflow.add_node("standard_processor", standard_processor)

# Connect branches
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## 🔄 Data Transformation Chain

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

# Sequential data transformations
def workflow.()  # Type signature example -> dict:
    """Clean and validate data."""
    cleaned = []
    for item in raw_data:
        if item.get("id") and item.get("name"):
            cleaned.append({
                "id": str(item["id"]).strip(),
                "name": item["name"].strip().title(),
                "value": float(item.get("value", 0))
            })
    return {"cleaned": cleaned}

def workflow.()  # Type signature example -> dict:
    """Enrich with calculated fields."""
    enriched = []
    for item in cleaned_data:
        enriched.append({
            **item,
            "category": "high" if item["value"] > 100 else "low",
            "processed_at": "2024-01-01T10:00:00Z"
        })
    return {"enriched": enriched}

def workflow.()  # Type signature example -> dict:
    """Aggregate statistics."""
    total_value = sum(item["value"] for item in enriched_data)
    high_value_count = len([i for i in enriched_data if i["category"] == "high"])

    return {
        "summary": {
            "total_records": len(enriched_data),
            "total_value": total_value,
            "high_value_count": high_value_count,
            "average_value": total_value / len(enriched_data) if enriched_data else 0
        },
        "details": enriched_data
    }

# Build transformation chain
transformations = [
    ("cleaner", clean_data),
    ("enricher", enrich_data),
    ("aggregator", aggregate_data)
]

for name, func in transformations:
    node = PythonCodeNode.from_function(name=name, func=func)
workflow = WorkflowBuilder()
workflow.add_node(name, node)

# Connect chain
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## 📊 State Management Pattern

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
    """Workflow with persistent state."""
    import json
    import os

    # Load existing state
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            current_state = json.load(f)
    else:
        current_state = {"counter": 0, "processed_items": []}

    # Update state with new data
    current_state["counter"] += 1
    current_state["processed_items"].extend(new_items)
    current_state["last_updated"] = "2024-01-01T10:00:00Z"

    # Save updated state
    with open(state_file, 'w') as f:
        json.dump(current_state, f)

    return {
        "state": current_state,
        "items_processed": len(new_items)
    }

state_manager = PythonCodeNode.from_function(
    name="state_manager", func=manage_workflow_state
)
workflow = WorkflowBuilder()
workflow.add_node("state_manager", state_manager)

```

## 🛡️ Error Recovery Pattern

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
    """Process data with error handling and recovery."""
    processed = []
    errors = []
    skipped = []

    for item in data:
        try:
            # Validate item
            if not item.get("id"):
                skipped.append({"item": item, "reason": "Missing ID"})
                continue

            # Process item
            processed_item = {
                "id": item["id"],
                "processed_value": item.get("value", 0) * 2,
                "status": "success"
            }
            processed.append(processed_item)

        except Exception as e:
            errors.append({
                "item": item,
                "error": str(e),
                "timestamp": "2024-01-01T10:00:00Z"
            })

    return {
        "processed": processed,
        "errors": errors,
        "skipped": skipped,
        "summary": {
            "total": len(data),
            "processed": len(processed),
            "errors": len(errors),
            "skipped": len(skipped)
        }
    }

def workflow.()  # Type signature example -> dict:
    """Handle and log errors."""
    retry_items = []
    logged_errors = []

    for error in errors:
        # Log error
        logged_errors.append({
            "error_id": f"err_{len(logged_errors) + 1}",
            "original_item": error["item"],
            "error_message": error["error"],
            "retry_count": 0
        })

        # Add to retry queue if retryable
        if any(keyword in error["error"].lower() for keyword in ["network", "timeout"]):
            retry_items.append(error["item"])

    return {
        "logged_errors": logged_errors,
        "retry_items": retry_items,
        "should_retry": len(retry_items) > 0
    }

# Add error handling nodes
safe_processor = PythonCodeNode.from_function(
    name="safe_processor", func=process_with_error_recovery
)
error_handler = PythonCodeNode.from_function(
    name="error_handler", func=handle_errors
)

workflow = WorkflowBuilder()
workflow.add_node("safe_processor", safe_processor)
workflow = WorkflowBuilder()
workflow.add_node("error_handler", error_handler)

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## 🔁 Simple Cycle Pattern

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
    """Basic iterative processing."""
    # Process one iteration
    new_value = current_value + 10
    converged = new_value >= target

    return {
        "current_value": new_value,
        "target": target,
        "converged": converged,
        "iteration": iteration + 1
    }

iterator = PythonCodeNode.from_function(
    name="iterator", func=iterative_processor
)
workflow = WorkflowBuilder()
workflow.add_node("iterator", iterator)

# Create cycle
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## 🎯 Nested Workflow Pattern

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

# Sub-workflow for modular design
def workflow.()  # Type signature example -> dict:
    """Validate data items."""
    valid_items = []
    invalid_items = []

    for item in data:
        if (item.get("id") and
            item.get("name") and
            isinstance(item.get("value"), (int, float))):
            valid_items.append(item)
        else:
            invalid_items.append({
                "item": item,
                "errors": [
                    "Missing ID" if not item.get("id") else None,
                    "Missing name" if not item.get("name") else None,
                    "Invalid value" if not isinstance(item.get("value"), (int, float)) else None
                ]
            })

    return {
        "valid": valid_items,
        "invalid": invalid_items,
        "validation_summary": {
            "total": len(data),
            "valid_count": len(valid_items),
            "invalid_count": len(invalid_items)
        }
    }

# Create sub-workflow
sub_workflow = WorkflowBuilder()
workflow.validator = PythonCodeNode.from_function(name="validator", func=validate_items)
workflow = WorkflowBuilder()
workflow.add_node("validator", validator)

# Use sub-workflow in main workflow
workflow = WorkflowBuilder()
workflow.add_node("WorkflowNode", "validation_step", {}))
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## 🔧 Performance Monitoring

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
    """Monitor workflow performance."""
    import time
    import psutil
    import os

    # Capture performance metrics
    start_time = time.time()
    current_process = psutil.Process(os.getpid())
    memory_usage = current_process.memory_info().rss / 1024 / 1024  # MB
    cpu_percent = current_process.cpu_percent()

    # Process data and measure time
    processed_data = [item for item in data if item.get("valid", True)]
    processing_time = time.time() - start_time

    return {
        "data": processed_data,
        "performance": {
            "processing_time_seconds": processing_time,
            "memory_usage_mb": memory_usage,
            "cpu_percent": cpu_percent,
            "items_processed": len(processed_data),
            "items_per_second": len(processed_data) / processing_time if processing_time > 0 else 0
        }
    }

performance_monitor = PythonCodeNode.from_function(
    name="performance_monitor", func=monitor_performance
)
workflow = WorkflowBuilder()
workflow.add_node("performance_monitor", performance_monitor)

```

## 🔍 Data Flow Debugging

```python
def create_debug_node('node_id', 'debug_name'):
    """Create debug node to inspect data flow."""
    def debug_function(data):
        import json

        # Log input data
        print(f"DEBUG [{debug_name}]: Input data:")
        data_str = json.dumps(data, indent=2) if isinstance(data, (dict, list)) else str(data)
        print(data_str[:500] + "..." if len(data_str) > 500 else data_str)

        # Pass data through unchanged
        return {
            "debug_output": data,
            "debug_info": {
                "node": debug_name,
                "data_type": str(type(data)),
                "data_size": len(data) if isinstance(data, (list, dict)) else 1
            }
        }

    return PythonCodeNode.from_function(name=node_id, func=debug_function)

# Insert debug nodes between processing steps
debug_node = create_debug_node("debug_1", "After Data Load")
workflow.add_node("debug_1", debug_node)
workflow.add_connection("data_loader", "debug_1", "data", "data")
workflow.add_connection("debug_1", "processor", "debug_output", "data")

```

## 📚 Quick Reference

### Composition Checklist
1. **Clear Naming** - Use descriptive node IDs and workflow names
2. **Proper Connections** - Map outputs to inputs correctly
3. **Error Handling** - Include error recovery patterns
4. **Data Validation** - Validate data at key points
5. **Performance** - Monitor processing time and memory
6. **Debugging** - Add debug nodes for complex workflows

### Key Patterns
- **Sequential**: A → B → C (linear processing)
- **Parallel**: A → (B1, B2, B3) → C (fan-out/fan-in)
- **Conditional**: A → Switch → (B1 | B2 | B3) (branching)
- **Cyclic**: A → B → A (iterative processing)
- **Nested**: A → SubWorkflow → C (modular design)

### Best Practices
1. Use `PythonCodeNode.from_function()` for complex logic
2. Keep individual functions focused and testable
3. Use meaningful variable names in mappings
4. Add error handling at critical points
5. Include performance monitoring for long-running workflows
6. Use debug nodes during development

### Common Connection Patterns
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

# Simple pass-through
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Nested field access
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Multiple outputs
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Fan-out to multiple nodes
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## 🚀 Advanced Example

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

def create_comprehensive_workflow():
    """Create a comprehensive workflow with all patterns."""
    workflow = WorkflowBuilder()
workflow.method()  # Example
    # 1. Input validation
    validator = PythonCodeNode.from_function(
        name="validator",
        func=lambda data: {"valid": data} if isinstance(data, list) else {"error": "Invalid input"}
    )
workflow = WorkflowBuilder()
workflow.add_node("validator", validator)

    # 2. Parallel processing
    splitter = PythonCodeNode.from_function(name="splitter", func=split_data_for_parallel)
workflow = WorkflowBuilder()
workflow.add_node("splitter", splitter)
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

    # 3. Workers
    for i in range(3):
        worker = PythonCodeNode.from_function(
            name=f"worker_{i+1}",
            func=lambda chunk: {"processed": [item * 2 for item in chunk]}
        )
workflow = WorkflowBuilder()
workflow.add_node(f"worker_{i+1}", worker)
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

    # 4. Merge results
    merger = MergeNode(strategy="combine")
workflow = WorkflowBuilder()
workflow.add_node("merger", merger)
    for i in range(3):
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

    # 5. Final aggregation
    aggregator = PythonCodeNode.from_function(
        name="aggregator",
        func=lambda combined_data: {
            "final_result": sum(combined_data.values(), []),
            "total_items": sum(len(chunk) for chunk in combined_data.values())
        }
    )
workflow = WorkflowBuilder()
workflow.add_node("aggregator", aggregator)
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

    return workflow

# Usage
comprehensive_workflow = create_comprehensive_workflow()
runtime = LocalRuntime()
runtime = LocalRuntime()
# Parameters setup
workflow.{
    "validator": {"data": list(range(100))}
})

```

---
*Related: [037-cyclic-workflow-patterns.md](037-cyclic-workflow-patterns.md), [038-integration-mastery.md](038-integration-mastery.md)*
