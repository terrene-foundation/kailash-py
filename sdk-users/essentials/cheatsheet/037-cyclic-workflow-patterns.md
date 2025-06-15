# Cyclic Workflow Patterns

## Quick Setup

```python
from kailash.nodes.base_cycle_aware import CycleAwareNode

class OptimizerNode(CycleAwareNode):
    def run(self, context, **kwargs):
        # Get state
        iteration = self.get_iteration(context)
        prev_state = self.get_previous_state(context)
        
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

## Multi-Node Cycle with Switch

```python
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
workflow.connect("optimizer", "analyzer", {"metrics": "metrics"})
workflow.connect("optimizer", "packager", {"metrics": "metrics", "score": "score"})
workflow.connect("analyzer", "packager", {"analysis": "analysis"})
workflow.connect("packager", "switch", {"result.switch_data": "input_data"})

# 3. Create cycle
workflow.connect(
    "switch", "optimizer",
    condition="false_output",
    mapping={"false_output.metrics": "metrics"},
    cycle=True,
    max_iterations=30,
    convergence_check="score >= 0.95"
)
```

## Critical Rules

1. **Preserve configuration state** - Parameters get lost after iteration 1
2. **Use packager for SwitchNode** - Creates proper input structure
3. **Map parameters explicitly** - No automatic propagation
4. **Set iteration limits** - Prevent infinite loops

## Common Fix

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