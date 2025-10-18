# Cycle Scenario Patterns

Real-world patterns for implementing cyclic workflows that solve common business problems.

## Key Design Principles

1. **Single Node Cycles**: Keep cycles simple with single nodes that handle all logic
   - Consolidate retry logic, decision-making, and processing into one node
   - Avoid using SwitchNode for conditional routing in cycles
2. **Explicit State Management**: Use node parameters for state that must persist
   - Parameters passed through cycles preserve their values
   - Use get_parameters() to define all persistent state
3. **Clear Convergence**: Always define clear convergence conditions
   - Use a `converged` field in the output
   - Set convergence_check="converged == True"
4. **Field-Specific Mapping**: Map each field explicitly in cycle connections
   - NEVER use generic # mapping removed, "field2": "field2"}

## Common Scenario Patterns

### 1. ETL with Retry Pattern

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

# ETL processor with retry logic using PythonCodeNode
workflow.add_node("PythonCodeNode", "etl_retry", {
    "code": """
# ETL processor with retry logic
max_retries = parameters.get("max_retries", 3)
success_rate = parameters.get("success_rate", 0.3)
iteration = context.get("iteration", 0)

# Simulate success after retries
if iteration >= 2 or iteration / max_retries > success_rate:
    success = True
    data = {"processed_records": 1000}
else:
    success = False
    data = None

result = {
    "success": success,
    "data": data,
    "retry_count": iteration + 1,
    "max_retries": max_retries,
    "success_rate": success_rate,
    "converged": success or iteration >= max_retries - 1
}
"""
})

# Usage - create cycle with intermediate evaluator node (self-connections not allowed)
workflow.add_node("PythonCodeNode", "retry_evaluator", {
    "code": "result = {'should_retry': not input_data.get('converged', False)}"
})
workflow.add_connection("etl_retry", "result", "retry_evaluator", "input")

# Build BEFORE creating cycle
built_workflow = workflow.build()

# Create cycle - CRITICAL: Use "result." prefix for PythonCodeNode
cycle = built_workflow.create_cycle("etl_retry_cycle")
cycle.connect("retry_evaluator", "etl_retry", mapping={
    "result.should_retry": "input_data",
    "result.retry_count": "retry_count",
    "result.max_retries": "max_retries"
}) \
     .max_iterations(10) \
     .converge_when("converged == True") \
     .build()

```

### 2. API Polling Pattern

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

# API polling logic using PythonCodeNode
workflow.add_node("PythonCodeNode", "api_poller", {
    "code": """
# Poll API until ready
max_polls = parameters.get("max_polls", 10)
iteration = context.get("iteration", 0)

# Simulate API becoming ready
if iteration >= 3:
    status = "ready"
    ready = True
    data = {"result": "processed"}
else:
    status = "pending"
    ready = False
    data = None

result = {
    "ready": ready,
    "status": status,
    "data": data,
    "poll_count": iteration + 1,
    "endpoint": parameters.get("endpoint"),
    "max_polls": max_polls,
    "converged": ready or iteration >= max_polls - 1
}
"""
})

```

### 3. Data Quality Improvement

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

# Data quality improvement logic using PythonCodeNode
workflow.add_node("PythonCodeNode", "data_quality", {
    "code": """
# Iteratively improve data quality
data = input_data.get("data", [])
target_quality = parameters.get("target_quality", 0.9)
improvement_rate = parameters.get("improvement_rate", 0.2)
iteration = context.get("iteration", 0)

# Calculate current quality
base_quality = 0.4
current_quality = min(base_quality + (iteration * improvement_rate), 1.0)

# Clean data based on quality
threshold = int(len(data) * (1 - current_quality))
cleaned_data = data[threshold:] if threshold < len(data) else data

result = {
    "data": cleaned_data,
    "quality_score": current_quality,
    "target_quality": target_quality,
    "improvement_rate": improvement_rate,
    "converged": current_quality >= target_quality
}
"""
})

```

### 4. Batch Processing with Checkpoints

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

# Batch processing logic using PythonCodeNode
workflow.add_node("PythonCodeNode", "batch_processor", {
    "code": """
# Process large datasets in batches
total_items = parameters.get("total_items", 1000)
batch_size = parameters.get("batch_size", 100)
iteration = context.get("iteration", 0)

# Get processed count from parameters (preserved across cycles)
if iteration > 0:
    processed_count = input_data.get("processed_count", 0)
else:
    processed_count = 0

# Process next batch
batch_end = min(processed_count + batch_size, total_items)
batch_data = list(range(processed_count, batch_end))

new_processed_count = batch_end
progress = new_processed_count / total_items

result = {
    "batch_data": batch_data,
    "processed_count": new_processed_count,
    "total_items": total_items,
    "batch_size": batch_size,
    "progress": progress,
    "converged": new_processed_count >= total_items
}
"""
})

# Important: Map processed_count to preserve progress with intermediate node
workflow.add_node("PythonCodeNode", "batch_evaluator", {
    "code": "result = {'continue_processing': not input_data.get('converged', False)}"
})
workflow.add_connection("batch_processor", "result", "batch_evaluator", "input")

# Build BEFORE creating cycle
built_workflow = workflow.build()

# Create cycle - CRITICAL: Use "result." prefix and map all state fields
cycle = built_workflow.create_cycle("batch_processing_cycle")
cycle.connect("batch_evaluator", "batch_processor", mapping={
    "result.processed_count": "input_data",
    "result.total_items": "total_items",
    "result.batch_size": "batch_size"
}) \
     .max_iterations(100) \
     .converge_when("converged == True") \
     .build()

```

### 5. Resource Optimization

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

# Resource optimization logic using PythonCodeNode
workflow.add_node("PythonCodeNode", "resource_optimizer", {
    "code": """
# Optimize resource allocation iteratively
resources = parameters.get("resources", {"cpu": 100, "memory": 1000})
target_efficiency = parameters.get("target_efficiency", 0.9)
iteration = context.get("iteration", 0)

# Improve efficiency over iterations
current_efficiency = min(0.6 + (iteration * 0.1), 1.0)

# Optimize resources
optimized = {}
for resource, amount in resources.items():
    optimized[resource] = int(amount * (1.1 - current_efficiency))

result = {
    "resources": optimized,
    "efficiency": current_efficiency,
    "target_efficiency": target_efficiency,
    "converged": current_efficiency >= target_efficiency
}
"""
})

```

## Best Practices

### 1. State Preservation
Always map state variables explicitly:
```python
# Example field mapping for cycle connections
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'state_var': input_data.get('state_var', 0) + 1, 'config': input_data.get('config', {}), 'done': input_data.get('state_var', 0) >= 5}"
})

# Build BEFORE creating cycle
built_workflow = workflow.build()

# Create cycle with explicit field mapping
cycle = built_workflow.create_cycle("state_preservation_cycle")
# CRITICAL: Use "result." prefix for PythonCodeNode
cycle.connect("processor", "processor", mapping={
    "result.state_var": "input_data",
    "result.config": "config"
}) \
     .max_iterations(10) \
     .converge_when("done == True") \
     .build()

```

### 2. Convergence Patterns
Use clear convergence conditions:
```python
# Iteration-based
convergence_patterns = {
    "converged": iteration >= max_iterations
}

# Goal-based
convergence_patterns = {
    "converged": quality_score >= target_quality
}

# Success-based
convergence_patterns = {
    "converged": success or retry_count >= max_retries
}

```

### 3. Parameter Passing
For parameters that must persist across iterations:
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

def get_parameters(self):
    return {
        "persistent_param": NodeParameter(name="persistent_param", type=int, required=False)
    }

# In run method
if self.get_iteration(context) > 0:
    value = kwargs.get("persistent_param", default)

```

### 4. Error Handling
Build resilience into cycles:
```python
try:
    result = process_data(data)
    success = True
except Exception as e:
    result = None
    success = False
    if iteration >= max_retries - 1:
        raise  # Re-raise on final attempt

return {
    "success": success,
    "result": result,
    "converged": success or iteration >= max_retries - 1
}

```

## Common Pitfalls

1. **Using complex multi-node cycles** - Keep cycles simple with single nodes
2. **Generic output mapping** - Always use specific field mapping
3. **Missing convergence conditions** - Every cycle needs clear exit criteria
4. **Not preserving counters/state** - Map all state variables explicitly

## Related Patterns
- [019-cyclic-workflows-basics.md](019-cyclic-workflows-basics.md) - Basic cycle concepts
- [027-cycle-aware-testing-patterns.md](027-cycle-aware-testing-patterns.md) - Testing cycles
- [030-cycle-state-persistence-patterns.md](030-cycle-state-persistence-patterns.md) - State management
