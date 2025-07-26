# Cyclic Workflow Patterns

*Essential patterns for building cyclic workflows*

## 🚀 Quick Setup

```python
from kailash.nodes.base_cycle_aware import CycleAwareNode

class OptimizerNode(CycleAwareNode):
    def run(self, **kwargs):
        # Get state
        iteration = self.get_iteration()
        prev_state = self.get_previous_state()

        # Initial parameters now persist automatically (v0.5.1+)
        targets = kwargs.get("targets", {})  # Available in ALL iterations
        learning_rate = kwargs.get("learning_rate", 0.01)  # No longer lost!

        # Do work
        result = optimize(kwargs.get("metrics", {}), targets, learning_rate)

        # Save dynamic state (not needed for initial params)
        return {
            "metrics": result,
            **self.set_cycle_state({"last_result": result})
        }

```

## 🔄 Multi-Node Cycle with Switch

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

# 1. Create packager
def package_for_switch(metrics=None, score=0.0, iteration=0):
    return {
        "switch_data": {
            "converged": score >= 0.95,
            "metrics": metrics or {},
            "score": score,
            "iteration": iteration
        }
    }

packager = PythonCodeNode.from_function("packager", package_for_switch)

# 2. Connect nodes using WorkflowBuilder
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "packager", {
    "code": """
result = {
    "switch_data": {
        "converged": score >= 0.95,
        "metrics": metrics or {},
        "score": score,
        "iteration": iteration
    }
}
"""
})
workflow.add_node("PythonCodeNode", "optimizer", {"code": "result = optimize_data(input_data)"})
workflow.add_node("SwitchNode", "switch", {
    "condition_field": "converged",
    "operator": "==",
    "value": True
})
workflow.add_node("PythonCodeNode", "processor", {"code": "result = process_final_result(input_data)"})

# 3. Create cycle using CycleBuilder API
workflow.add_connection("optimizer", "result", "packager", "metrics")
workflow.add_connection("packager", "result", "switch", "input_data")

# Create cycle with CycleBuilder
cycle_builder = workflow.create_cycle("optimization_cycle")
cycle_builder.connect("switch", "false_output", "optimizer", "input_data") \
             .max_iterations(50) \
             .converge_when("converged == True") \
             .timeout(300) \
             .build()

# Exit path
workflow.add_connection("switch", "true_output", "processor", "input_data")

```

## ⚠️ Critical Rules

1. **~~Preserve configuration state~~ (Fixed in v0.5.1+)** - Initial parameters now persist across all iterations!
2. **Use packager for SwitchNode** - Creates proper input structure
3. **Map parameters explicitly** - No automatic propagation
4. **Set iteration limits** - Prevent infinite loops

## 🔧 Updated Pattern (v0.5.1+)

```python
# Initial parameters now persist automatically!
targets = kwargs.get("targets", {})  # Available in ALL iterations
learning_rate = kwargs.get("learning_rate", 0.01)  # No longer lost

# State preservation still useful for dynamic values
prev_state = self.get_previous_state()
accumulated_results = prev_state.get("results", [])
accumulated_results.append(data)

return {
    "result": data,
    **self.set_cycle_state({"results": accumulated_results})
}

```

## 🎯 Self-Contained Cycle Pattern

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

class SelfOptimizingNode(CycleAwareNode):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[]),
            "target_quality": NodeParameter(name="target_quality", type=float, required=False, default=0.8)
        }

    def run(self, **kwargs):
        prev_state = self.get_previous_state()

        # Initial parameters persist automatically (v0.5.1+)
        target_quality = kwargs.get("target_quality", 0.8)  # Available in ALL iterations!

        # Process data
        data = kwargs.get("data", [])
        current_quality = calculate_quality(data)

        # Improve quality
        if current_quality < target_quality:
            improved_data = improve_data(data)
            improved_quality = calculate_quality(improved_data)
        else:
            improved_data = data
            improved_quality = current_quality

        # Built-in convergence check
        converged = improved_quality >= target_quality

        # Track improvement history
        improvement_history = prev_state.get("improvement_history", [])
        improvement_history.append(improved_quality - current_quality)

        return {
            "data": improved_data,
            "quality": improved_quality,
            "converged": converged,
            **self.set_cycle_state({"improvement_history": improvement_history})
        }

# Usage with WorkflowBuilder
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "self_optimizer", {
    "code": """
# Simulate self-optimization logic
target_quality = target_quality if 'target_quality' in locals() else 0.8
data = data if 'data' in locals() else []

# Simple quality calculation
current_quality = sum(data) / len(data) if data else 0.0

# Improve data
if current_quality < target_quality:
    improved_data = [x * 1.1 for x in data]  # Simple improvement
    improved_quality = sum(improved_data) / len(improved_data) if improved_data else 0.0
else:
    improved_data = data
    improved_quality = current_quality

converged = improved_quality >= target_quality

result = {
    "data": improved_data,
    "quality": improved_quality,
    "converged": converged
}
"""
})

# Create self-improvement cycle
cycle_builder = workflow.create_cycle("self_optimization")
cycle_builder.connect("self_optimizer", "result", "self_optimizer", "input_data") \
             .max_iterations(20) \
             .converge_when("converged == True") \
             .timeout(600) \
             .build()

```

## 🔍 Parameter Preservation Patterns

### State-Based Preservation (Updated for v0.5.1+)
```python
def run(self, **kwargs):
    prev_state = self.get_previous_state()

    # Initial parameters now persist automatically!
    config = kwargs.get("config", {})  # Available in ALL iterations
    learning_rate = kwargs.get("learning_rate", 0.1)  # No longer lost

    # Use state for dynamic/accumulated values
    processed_count = prev_state.get("processed_count", 0)
    error_history = prev_state.get("error_history", [])

    # Process with config
    result = process_with_config(kwargs.get("data", []), config, learning_rate)
    processed_count += len(result)

    # Save only dynamic state (not initial params)
    return {
        "result": result,
        **self.set_cycle_state({
            "processed_count": processed_count,
            "error_history": error_history + [result.get("error", 0)]
        })
    }

```

### Runtime Mapping Preservation
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

# Ensure parameters flow through cycle connections
workflow = WorkflowBuilder()
# Workflow connections go here

```

## 🔄 Complex Multi-Node Patterns

### Three-Node Optimization Cycle
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

# Node 1: Data Processor
class DataProcessorNode(CycleAwareNode):
    def run(self, **kwargs):
        data = kwargs.get("data", [])
        processed = [item * 1.1 for item in data]
        return {"processed_data": processed}

# Node 2: Quality Analyzer
class QualityAnalyzerNode(CycleAwareNode):
    def run(self, **kwargs):
        data = kwargs.get("processed_data", [])
        quality_score = sum(data) / len(data) if data else 0
        return {"quality_score": quality_score, "analyzed_data": data}

# Node 3: Convergence Controller
class ConvergenceControllerNode(CycleAwareNode):
    def run(self, **kwargs):
        prev_state = self.get_previous_state()

        quality_score = kwargs.get("quality_score", 0)
        target = kwargs.get("target", 100)  # Available in ALL iterations (v0.5.1+)

        converged = quality_score >= target

        # Track progress history
        progress_history = prev_state.get("progress_history", [])
        progress_history.append(quality_score)

        return {
            "data": kwargs.get("analyzed_data", []),
            "converged": converged,
            "quality": quality_score,
            **self.set_cycle_state({"progress_history": progress_history})
        }

# Connect in cycle
workflow = WorkflowBuilder()
# Workflow connections go here
workflow = WorkflowBuilder()
# Workflow connections go here
workflow = WorkflowBuilder()
# Workflow connections go here

```

## 📊 Performance Monitoring in Cycles

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

class MonitoredCycleNode(CycleAwareNode):
    def run(self, **kwargs):
        import time
        start_time = time.time()

        iteration = self.get_iteration()
        prev_state = self.get_previous_state()

        # Track performance history
        performance_history = prev_state.get("performance_history", [])

        # Process data
        result = expensive_processing(kwargs.get("data", []))

        # Record performance
        processing_time = time.time() - start_time
        performance_history.append({
            "iteration": iteration,
            "processing_time": processing_time,
            "result_size": len(result) if isinstance(result, list) else 1
        })

        # Keep only last 10 records
        performance_history = performance_history[-10:]

        # Calculate averages
        avg_time = sum(p["processing_time"] for p in performance_history) / len(performance_history)

        # Performance-based convergence
        converged = len(performance_history) >= 5 and avg_time < 0.1

        return {
            "result": result,
            "converged": converged,
            "avg_processing_time": avg_time,
            **self.set_cycle_state({"performance_history": performance_history})
        }

```

## ⚡ Quick Patterns Reference

### Simple Self-Cycle
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
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

```

### Self-Cycle with Convergence
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
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

```

### Multi-Node with State Preservation (Updated for v0.5.1+)
```python
# Initial params persist automatically - use state for dynamic values only
return {
    "result": processed_data,
    **self.set_cycle_state({
        "processed_count": len(processed_data),
        "last_result": processed_data[-1] if processed_data else None
    })
}

```

### SwitchNode Integration
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

# Package data for SwitchNode
return {
    "processed": data,
    "switch_input": {
        "should_continue": not converged,
        "data": data,
        "metadata": metadata
    }
}

```

## 🚨 Common Pitfalls

1. **~~Parameters vanish after iteration 1~~ (Fixed in v0.5.1+)** → Initial params now persist automatically
2. **SwitchNode expects packaged data** → Create input_data structure
3. **Infinite cycles** → Always set max_iterations
4. **Complex multi-node cycles** → Use direct cycles when possible

## 🎯 Best Practices

1. Start with self-contained nodes
2. Use explicit parameter mapping
3. Preserve configuration in state
4. Add convergence conditions
5. Monitor performance
6. Test with small iteration limits first

---
*Related: [021-cycle-aware-nodes.md](021-cycle-aware-nodes.md), [022-cycle-debugging-troubleshooting.md](022-cycle-debugging-troubleshooting.md)*
