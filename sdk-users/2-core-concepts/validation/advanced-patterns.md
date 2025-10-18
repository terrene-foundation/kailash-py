# Advanced Patterns - Complex Usage Scenarios

*Advanced Kailash SDK patterns for complex workflows*

## 📦 **Required Imports**

All examples in this guide assume these imports:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.ai import LLMAgentNode, EmbeddingGeneratorNode
from kailash.nodes.api import HTTPRequestNode, RESTClientNode
from kailash.nodes.logic import SwitchNode, MergeNode, WorkflowNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.transform import DataTransformerNode
from kailash.nodes.base import Node, NodeParameter
from kailash.workflow.builder import WorkflowBuilder
```

## 🔄 **Cyclic Workflow Patterns**

### **Basic Cycle Setup**
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode

workflow = WorkflowBuilder()

# Cycle-aware processor
workflow.add_node("PythonCodeNode", "processor", {
    "code": """
try:
    current_value = input_data.get('current_value', 0)
    target = input_data.get('target', 100)
    iteration = input_data.get('iteration', 0)
except NameError:
    current_value = 0
    target = 100
    iteration = 0

new_value = current_value + (target - current_value) / 10
converged = abs(new_value - target) < 1

result = {
    'current_value': new_value,
    'target': target,
    'iteration': iteration + 1,
    'converged': converged
}
"""
})

# Build BEFORE creating cycle
built_workflow = workflow.build()

# Create cycle - CRITICAL: Use "result." prefix for PythonCodeNode
cycle = built_workflow.create_cycle("processor_cycle")
cycle.connect("processor", "processor", mapping={
    "result.current_value": "input_data",
    "result.target": "target",
    "result.iteration": "iteration"
}) \
     .max_iterations(50) \
     .converge_when("converged == True") \
     .build()

# Execute with initial parameters
runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow, parameters={
    "processor": {
        "current_value": 0,
        "target": 100,
        "iteration": 0
    }
})

```

### **Complex State Management**
```python
# Advanced cycle with complex state
workflow.add_node("PythonCodeNode", "state_processor", {
    "code": """
# Complex state management with accumulation
class StateManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.values = []
            cls._instance.sum = 0
            cls._instance.best_value = float('-inf')
            cls._instance.iterations = 0
            cls._instance.average = 0
        return cls._instance

state_mgr = StateManager()

try:
    new_data = input_data.get('new_data', [])
except NameError:
    new_data = []

# Process new data
for item in new_data:
    state_mgr.values.append(item)
    state_mgr.sum += item
    if item > state_mgr.best_value:
        state_mgr.best_value = item

state_mgr.iterations += 1
state_mgr.average = state_mgr.sum / len(state_mgr.values) if state_mgr.values else 0

# Check convergence conditions
converged = (
    state_mgr.iterations >= 5 and
    len(state_mgr.values) >= 20 and
    state_mgr.average > 50
)

result = {
    'converged': converged,
    'summary': {
        'total_items': len(state_mgr.values),
        'average': state_mgr.average,
        'best': state_mgr.best_value,
        'iterations': state_mgr.iterations
    }
}
"""
})

# Build BEFORE creating cycle
built_workflow = workflow.build()

# Create cycle - CRITICAL: Use "result." prefix for PythonCodeNode
cycle = built_workflow.create_cycle("state_processing_cycle")
cycle.connect("state_processor", "state_processor", mapping={"result.summary": "input_data"}) \
     .max_iterations(20) \
     .converge_when("converged == True") \
     .build()

```

### **Convergence Check Expressions**
```python
# Simple numeric convergence
convergence_check="abs(current_value - target) < 0.01"

# Complex multi-condition convergence
convergence_check="(accuracy > 0.95 and iterations >= 10) or iterations >= 50"

# State-based convergence
convergence_check="state.get('stable_count', 0) > 5"

# Custom convergence function
convergence_check="custom_convergence_function(state, metrics)"

```

## 🔀 **Parameter Flow Architectures**

### **Configuration vs Runtime Parameter Patterns**
```python
# Understanding the new architecture
class NodeWithParameters:
    def get_parameters(self):
        """Define what parameters this node accepts"""
        return {
            "required_param": NodeParameter(str, "Required parameter", required=True),
            "optional_param": NodeParameter(int, "Optional parameter", default=42),
            "runtime_data": NodeParameter(list, "Runtime data injection")
        }

    def run(self, **kwargs):
        """Parameters are injected here at runtime"""
        required = kwargs.get("required_param")  # From config or runtime
        optional = kwargs.get("optional_param", 42)  # Default value
        data = kwargs.get("runtime_data", [])  # Often from runtime

        return {"result": f"processed {len(data)} items"}

# Configuration time (node creation)
workflow = WorkflowBuilder()
workflow.add_node("processor", NodeWithParameters(),
    required_param="configured_value",  # Static configuration
    optional_param=100                  # Override default
)

# Runtime (execution time)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "processor": {
        "runtime_data": [1, 2, 3, 4, 5],  # Dynamic data injection
        "optional_param": 200              # Runtime override of config
    }
})

```

### **Data Flow from External Sources**
```python
# Pattern 1: Pure configuration (no external data)
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {}), file_path="data.csv")
# No runtime parameters needed

# Pattern 2: Pure runtime injection
workflow.add_node("PythonCodeNode", "processor", {}))

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "processor": {"injected_data": [1, 2, 3, 4, 5]}
})

# Pattern 3: Hybrid (config + runtime)
workflow.add_node("CSVReaderNode", "reader", {}),
    file_path="default.csv",  # Configuration default
    delimiter=","             # Configuration setting
)

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "reader": {
        "file_path": "runtime.csv",  # Runtime override
        "encoding": "utf-8"          # Runtime addition
    }
})

```

### **Complex Parameter Mapping**
```python
# Multi-source parameter aggregation
def create_complex_workflow():
    workflow = WorkflowBuilder()

    # Node with multiple parameter sources
    aggregator_node = PythonCodeNode(
        name="aggregator",
        code='''
# Process parameters from multiple sources
result = {
    "config": config_setting,
    "runtime": runtime_override,
    "external": list(external_input.keys()) if external_input else [],
    "total": len(runtime_override) + len(external_input) if external_input else len(runtime_override)
}
''',
        input_types={
            "config_setting": str,     # From node configuration
            "runtime_override": list,  # From runtime parameters
            "external_input": dict     # From previous node output
        }
    )

    workflow.add_node("aggregator", aggregator_node,
        config_setting="production_mode"  # Configuration parameter
    )
    return workflow

# Usage with multiple parameter sources
workflow = create_complex_workflow()

# Runtime parameters (dynamic)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "aggregator": {
        "runtime_override": [1, 2, 3, 4, 5],  # Runtime injection
        # external_input comes from connected nodes
    }
})

```

## 🔧 **WorkflowBuilder Advanced Patterns**

### **Builder vs Direct Comparison**
```python
# Method 1: Direct Workflow (Recommended)
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {}), file_path="data.csv")
workflow.add_node("PythonCodeNode", "processor", {}))
workflow.add_connection("reader", "processor", "data", "input_data")

# Method 2: WorkflowBuilder (Alternative)
from kailash.workflow.builder import WorkflowBuilder

builder = WorkflowBuilder()
reader_id = builder.add_node("CSVReaderNode", config={"file_path": "data.csv"})
proc_id = builder.add_node("ProcessorNode", config={})
builder.add_connection(reader_id, "data", proc_id, "input")  # 4 parameters
workflow = builder.build()

```

### **Dynamic Workflow Generation**
```python
def create_processing_pipeline(processing_steps):
    """Generate workflow dynamically from configuration"""
    builder = WorkflowBuilder()

    # Add input node
    input_id = builder.add_node("CSVReaderNode",
        config={"file_path": "input.csv"})

    previous_id = input_id

    # Add processing steps
    for i, step in enumerate(processing_steps):
        if step["type"] == "filter":
            node_id = builder.add_node("DataTransformerNode", config={
                "operations": [{"type": "filter", "condition": step["condition"]}]
            })
        elif step["type"] == "python":
            node_id = builder.add_node("PythonCodeNode", config={
                "name": f"step_{i}",
                "code": step["code"],
                "input_types": step.get("input_types", {})
            })

        builder.add_connection(previous_id, "data", node_id, "data")
        previous_id = node_id

    # Add output node
    output_id = builder.add_node("CSVWriterNode",
        config={"file_path": "output.csv"})
    builder.add_connection(previous_id, "data", output_id, "data")

    return builder.build()

# Usage
processing_config = [
    {"type": "filter", "condition": "age > 18"},
    {"type": "python", "code": "result = {'processed': data}", "input_types": {"data": list}}
]

workflow = create_processing_pipeline(processing_config)

```

## 🔀 **Advanced Connection Patterns**

### **Multi-Path Routing**
```python
# Complex routing with multiple conditions
workflow = WorkflowBuilder()
workflow.add_node("SwitchNode", "classifier", {}),
    conditions=[
        {"output": "critical", "expression": "priority == 'critical' and urgency > 9"},
        {"output": "high", "expression": "priority == 'high' or urgency > 7"},
        {"output": "normal", "expression": "priority == 'normal' and urgency <= 7"},
        {"output": "low", "expression": "priority == 'low'"}
    ],
    default_output="unprocessed"
)

# Connect to different processing paths
workflow.add_connection("source", "result", "target", "input")  # Fixed output mapping
workflow.add_connection("source", "result", "target", "input")  # Fixed output mapping
workflow.add_connection("source", "result", "target", "input")  # Fixed output mapping
workflow.add_connection("source", "result", "target", "input")  # Fixed output mapping
workflow.add_connection("source", "result", "target", "input")  # Fixed output mapping

```

### **Convergence and Merge Patterns**
```python
# Parallel processing with convergence
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "splitter", {}) // 3
result = {
    "chunk1": data[:chunk_size],
    "chunk2": data[chunk_size:chunk_size*2],
    "chunk3": data[chunk_size*2:]
}
''',
    input_types={"data": list}
))

# Parallel processors
for i in range(3):
    workflow.add_node(f"processor_{i}", PythonCodeNode(
        name=f"processor_{i}",
        code=f'''
processed = []
for item in chunk_data:
    processed.append({{
        "processed_by": "processor_{i}",
        "value": item.get("value", 0) * 2
    }})
result = {{"processed": processed}}
''',
        input_types={"chunk_data": list}
    ))

    workflow.add_connection("source", "result", "target", "input")  # Fixed mapping pattern

# Merge results
workflow.add_node("MergeNode", "merger", {}), strategy="combine")
for i in range(3):
    workflow.add_connection("source", "result", "target", "input")  # Fixed mapping pattern

```

### **Nested Workflow Patterns**
```python
# Create sub-workflow for reusable logic
def create_validation_workflow():
    sub_workflow = WorkflowBuilder()

    sub_workflow.add_node("PythonCodeNode", "validator", {}) and "id" in item and "value" in item:
        valid_items.append(item)
    else:
        invalid_items.append(item)

result = {
    "valid": valid_items,
    "invalid": invalid_items,
    "validation_summary": {
        "total": len(data),
        "valid_count": len(valid_items),
        "invalid_count": len(invalid_items),
        "success_rate": len(valid_items) / len(data) if data else 0
    }
}
''',
        input_types={"data": list}
    ))

    return sub_workflow

# Use nested workflow in main workflow
validation_workflow = create_validation_workflow()
main_workflow = WorkflowBuilder()

main_workflow.add_node("CSVReaderNode", "reader", {}), file_path="data.csv")
main_workflow.add_node("WorkflowNode", "validation", {}))
main_workflow.add_node("PythonCodeNode", "processor", {})}",
    input_types={"valid_data": list}
))

main_workflow.add_connection("reader", "validation", "data", "data")
main_workflow.add_connection("validation", "processor", "valid", "valid_data")

```

## 📊 **Performance Optimization Patterns**

### **Batch Processing**
```python
# Large dataset processing with batching
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "batch_processor", {})
num_batches = math.ceil(total_items / batch_size)

processed_batches = []
for i in range(num_batches):
    start_idx = i * batch_size
    end_idx = min((i + 1) * batch_size, total_items)
    batch = data[start_idx:end_idx]

    # Process batch
    batch_result = []
    for item in batch:
        if item.get("value", 0) > threshold:
            batch_result.append({
                "id": item.get("id"),
                "processed_value": item["value"] * multiplier,
                "batch_number": i + 1
            })

    processed_batches.append({
        "batch_id": i + 1,
        "items": batch_result,
        "original_count": len(batch),
        "processed_count": len(batch_result)
    })

result = {
    "batches": processed_batches,
    "summary": {
        "total_batches": num_batches,
        "total_items": total_items,
        "total_processed": sum(len(b["items"]) for b in processed_batches)
    }
}
''',
    input_types={"data": list, "threshold": float, "multiplier": float}
))

```

### **Memory-Efficient Processing**
```python
# Stream processing for large datasets
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "stream_processor", {}), chunk_size):
    chunk = data[i:i + chunk_size]

    # Process chunk
    for item in chunk:
        if item.get("process", True):
            processed_count += 1

    # Memory management
    if i % (chunk_size * 10) == 0:
        gc.collect()
        memory_usage.append(f"Processed {i + len(chunk)} items")

    # Clear chunk reference
    del chunk

result = {
    "processed_count": processed_count,
    "memory_checkpoints": memory_usage,
    "efficiency_metrics": {
        "items_per_chunk": chunk_size,
        "total_chunks": len(range(0, len(data), chunk_size)),
        "memory_managed": True
    }
}
''',
    input_types={"data": list}
))

```

## 🔗 **Next Steps**

- **[Critical Rules](critical-rules.md)** - Review essential patterns
- **[API Reference](api-reference.md)** - Complete method signatures
- **[Migration Guide](migration-guide.md)** - Updates and changes

---

**These advanced patterns handle complex scenarios while maintaining SDK best practices!**
