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

class ETLRetryNode(CycleAwareNode):
    """ETL processor with retry logic."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data_source": NodeParameter(name="data_source", type=str, required=False),
            "max_retries": NodeParameter(name="max_retries", type=int, required=False, default=3),
            "success_rate": NodeParameter(name="success_rate", type=float, required=False, default=0.3)
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        iteration = self.get_iteration(context)

        # Simulate success after retries
        if iteration >= 2 or iteration / kwargs.get("max_retries", 3) > kwargs.get("success_rate", 0.3):
            success = True
            data = {"processed_records": 1000}
        else:
            success = False
            data = None

        return {
            "success": success,
            "data": data,
            "retry_count": iteration + 1,
            "data_source": kwargs.get("data_source"),
            "max_retries": kwargs.get("max_retries"),
            "success_rate": kwargs.get("success_rate"),
            "converged": success or iteration >= kwargs.get("max_retries", 3) - 1
        }

# Usage
workflow = WorkflowBuilder()
workflow.add_node("ETLRetryNode", "etl", {}))
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

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

class APIPollerNode(CycleAwareNode):
    """Poll API until ready."""

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        iteration = self.get_iteration(context)

        # Simulate API becoming ready
        if iteration >= 3:
            status = "ready"
            ready = True
            data = {"result": "processed"}
        else:
            status = "pending"
            ready = False
            data = None

        return {
            "ready": ready,
            "status": status,
            "data": data,
            "poll_count": iteration + 1,
            "endpoint": kwargs.get("endpoint"),
            "max_polls": kwargs.get("max_polls", 10),
            "converged": ready or iteration >= kwargs.get("max_polls", 10) - 1
        }

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

class DataQualityNode(CycleAwareNode):
    """Iteratively improve data quality."""

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        data = kwargs.get("data", [])
        target_quality = kwargs.get("target_quality", 0.9)
        improvement_rate = kwargs.get("improvement_rate", 0.2)

        iteration = self.get_iteration(context)

        # Calculate current quality
        base_quality = 0.4
        current_quality = min(base_quality + (iteration * improvement_rate), 1.0)

        # Clean data based on quality
        threshold = int(len(data) * (1 - current_quality))
        cleaned_data = data[threshold:] if threshold < len(data) else data

        return {
            "data": cleaned_data,
            "quality_score": current_quality,
            "target_quality": target_quality,
            "improvement_rate": improvement_rate,
            "converged": current_quality >= target_quality
        }

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

class BatchProcessorNode(CycleAwareNode):
    """Process large datasets in batches."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "total_items": NodeParameter(name="total_items", type=int, required=False),
            "batch_size": NodeParameter(name="batch_size", type=int, required=False),
            "processed_count": NodeParameter(name="processed_count", type=int, required=False, default=0)
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        total_items = kwargs.get("total_items", 1000)
        batch_size = kwargs.get("batch_size", 100)

        # Get processed count from parameters (preserved across cycles)
        if self.get_iteration(context) > 0:
            processed_count = kwargs.get("processed_count", 0)
        else:
            processed_count = 0

        # Process next batch
        batch_end = min(processed_count + batch_size, total_items)
        batch_data = list(range(processed_count, batch_end))

        new_processed_count = batch_end
        progress = new_processed_count / total_items

        return {
            "batch_data": batch_data,
            "processed_count": new_processed_count,
            "total_items": total_items,
            "batch_size": batch_size,
            "progress": progress,
            "converged": new_processed_count >= total_items
        }

# Important: Map processed_count to preserve progress
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

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

class ResourceOptimizerNode(CycleAwareNode):
    """Optimize resource allocation iteratively."""

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        resources = kwargs.get("resources", {"cpu": 100, "memory": 1000})
        target_efficiency = kwargs.get("target_efficiency", 0.9)

        iteration = self.get_iteration(context)

        # Improve efficiency over iterations
        current_efficiency = min(0.6 + (iteration * 0.1), 1.0)

        # Optimize resources
        optimized = {}
        for resource, amount in resources.items():
            optimized[resource] = int(amount * (1.1 - current_efficiency))

        return {
            "resources": optimized,
            "efficiency": current_efficiency,
            "target_efficiency": target_efficiency,
            "converged": current_efficiency >= target_efficiency
        }

```

## Best Practices

### 1. State Preservation
Always map state variables explicitly:
```python
# mapping removed,
    "state_var": "state_var",
    "config": "config"
}

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
