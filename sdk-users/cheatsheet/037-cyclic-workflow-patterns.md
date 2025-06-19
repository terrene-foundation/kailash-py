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

        # Preserve config
        targets = kwargs.get("targets", {})
        if not targets and prev_state.get("targets"):
            targets = prev_state["targets"]

        # Do work
        result = optimize(kwargs.get("metrics", {}), targets)

        # Save state
        return {
            "metrics": result,
            **self.set_cycle_state({"targets": targets})
        }

```

## 🔄 Multi-Node Cycle with Switch

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

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

# 2. Connect nodes
workflow.add_node("packager", packager)
workflow.add_node("optimizer", OptimizerNode())
workflow.add_node("switch", SwitchNode())
workflow.add_node("processor", PythonCodeNode())

# 3. Create cycle
workflow.connect("optimizer", "packager")
workflow.connect("packager", "switch", mapping={"switch_data": "data"})
workflow.connect("switch", "optimizer", output_port="continue")

```

## ⚠️ Critical Rules

1. **Preserve configuration state** - Parameters get lost after iteration 1
2. **Use packager for SwitchNode** - Creates proper input structure
3. **Map parameters explicitly** - No automatic propagation
4. **Set iteration limits** - Prevent infinite loops

## 🔧 Common Fix

```python
# Problem: Targets lost after first iteration
if not targets and prev_state.get("targets"):
    targets = prev_state["targets"]

# Save in state
return {
    "result": data,
    **self.set_cycle_state({"targets": targets})
}

```

## 🎯 Self-Contained Cycle Pattern

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

class SelfOptimizingNode(CycleAwareNode):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[]),
            "target_quality": NodeParameter(name="target_quality", type=float, required=False, default=0.8)
        }

    def run(self, **kwargs):
        prev_state = self.get_previous_state()

        # Preserve configuration
        target_quality = kwargs.get("target_quality", prev_state.get("target_quality", 0.8))

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

        return {
            "data": improved_data,
            "quality": improved_quality,
            "converged": converged,
            **self.set_cycle_state({"target_quality": target_quality})
        }

# Usage
workflow = Workflow("example", name="Example")
workflow.workflow.add_node("self_optimizer", SelfOptimizingNode())
workflow = Workflow("example", name="Example")
workflow.workflow.connect("self_optimizer", "self_optimizer",
    cycle=True,
    max_iterations=20,
    convergence_check="converged == True")

```

## 🔍 Parameter Preservation Patterns

### State-Based Preservation
```python
def run(self, **kwargs):
    prev_state = self.get_previous_state()

    # Restore configuration from state
    config = kwargs.get("config", prev_state.get("config", {}))
    learning_rate = kwargs.get("learning_rate", prev_state.get("learning_rate", 0.1))

    # Process with preserved config
    result = process_with_config(kwargs.get("data", []), config, learning_rate)

    # Always save back to state
    return {
        "result": result,
        **self.set_cycle_state({
            "config": config,
            "learning_rate": learning_rate
        })
    }

```

### Runtime Mapping Preservation
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Ensure parameters flow through cycle connections
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

## 🔄 Complex Multi-Node Patterns

### Three-Node Optimization Cycle
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

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
        target = kwargs.get("target", prev_state.get("target", 100))

        converged = quality_score >= target

        return {
            "data": kwargs.get("analyzed_data", []),
            "converged": converged,
            "quality": quality_score,
            **self.set_cycle_state({"target": target})
        }

# Connect in cycle
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

## 📊 Performance Monitoring in Cycles

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

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
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

workflow = Workflow("example", name="Example")
workflow.workflow.connect("node", "node", cycle=True, max_iterations=10)

```

### Self-Cycle with Convergence
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

workflow = Workflow("example", name="Example")
workflow.workflow.connect("node", "node",
    cycle=True,
    max_iterations=20,
    convergence_check="converged == True")

```

### Multi-Node with State Preservation
```python
# Always preserve configuration in cycle state
return {
    "result": processed_data,
    **self.set_cycle_state({"config": config, "params": params})
}

```

### SwitchNode Integration
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

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

1. **Parameters vanish after iteration 1** → Use cycle state
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
