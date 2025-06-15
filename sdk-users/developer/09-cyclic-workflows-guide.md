# Cyclic Workflows Guide

This guide covers the implementation of cyclic workflows in Kailash SDK, including parameter propagation, state management, and convergence patterns.

## Table of Contents
1. [Overview](#overview)
2. [CycleAwareNode Base Class](#cycleawarenode-base-class)
3. [Parameter Propagation](#parameter-propagation)
4. [Multi-Node Cycles](#multi-node-cycles)
5. [Convergence Patterns](#convergence-patterns)
6. [Common Pitfalls](#common-pitfalls)
7. [Production Examples](#production-examples)

## Overview

Cyclic workflows enable iterative optimization and refinement processes. They're essential for:
- Machine learning training loops
- Optimization algorithms
- Iterative refinement processes
- Self-improving systems
- Convergence-based solutions

## CycleAwareNode Base Class

The `CycleAwareNode` provides built-in support for iteration tracking and state management:

```python
from kailash.nodes.base_cycle_aware import CycleAwareNode

class OptimizationNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        # Get iteration information
        iteration = self.get_iteration(context)
        is_first = self.is_first_iteration(context)
        prev_state = self.get_previous_state(context)
        
        # Your optimization logic here
        
        # Save state for next iteration
        return {
            "metrics": optimized_metrics,
            **self.set_cycle_state({
                "history": updated_history,
                "configuration": preserved_config
            })
        }
```

### Key Methods

- `get_iteration(context)` - Current iteration number
- `is_first_iteration(context)` - Check if first iteration
- `get_previous_state(context)` - Retrieve state from previous iteration
- `set_cycle_state(state_dict)` - Save state for next iteration
- `accumulate_values(context, key, value)` - Build history over iterations
- `detect_convergence_trend(context, key, threshold, window)` - Check convergence
- `log_cycle_info(context, message)` - Iteration-aware logging

## Parameter Propagation

### Critical Pattern: State Preservation

**Problem**: Configuration parameters (targets, constraints, settings) get lost after the first iteration.

**Solution**: Preserve configuration in cycle state:

```python
class EnterpriseOptimizerNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        # Get previous state
        prev_state = self.get_previous_state(context)
        
        # Get parameters with state preservation
        targets = kwargs.get("targets", {})
        constraints = kwargs.get("constraints", {})
        
        # CRITICAL: Restore from state if not provided
        if not targets and prev_state.get("targets"):
            targets = prev_state["targets"]
        if not constraints and prev_state.get("constraints"):
            constraints = prev_state["constraints"]
        
        # Initialize on first iteration
        if self.is_first_iteration(context):
            if not targets:
                targets = self._get_default_targets()
            metrics = self._initialize_metrics(targets)
        else:
            metrics = kwargs.get("metrics", {})
        
        # Optimize
        optimized = self._optimize(metrics, targets, constraints)
        
        # Return with preserved state
        return {
            "metrics": optimized,
            "score": self._calculate_score(optimized, targets),
            **self.set_cycle_state({
                "targets": targets,
                "constraints": constraints,
                "history": self.accumulate_values(context, "scores", score)
            })
        }
```

## Multi-Node Cycles

### The Packager Pattern

When using multiple nodes in a cycle with a SwitchNode, use a packager to prepare data:

```python
def create_cyclic_workflow() -> Workflow:
    workflow = Workflow("cyclic_optimization", "Multi-node cycle")
    
    # Nodes
    optimizer = OptimizerNode(name="optimizer")
    analyzer = AnalyzerNode(name="analyzer")
    
    # Packager for switch
    def package_for_switch(
        metrics: Dict = None,
        score: float = 0.0,
        analysis: Dict = None,
        iteration: int = 0
    ) -> Dict[str, Any]:
        converged = score >= 0.95 or iteration >= 20
        
        return {
            "switch_data": {
                "converged": converged,
                "metrics": metrics or {},
                "score": score,
                "iteration": iteration,
                "analysis": analysis or {}
            }
        }
    
    packager = PythonCodeNode.from_function(
        name="packager",
        func=package_for_switch
    )
    
    switch = SwitchNode(
        name="switch",
        condition_field="converged",
        operator="==",
        value=True
    )
    
    # Connect with explicit mapping
    workflow.connect("optimizer", "analyzer", {
        "metrics": "metrics",
        "score": "score"
    })
    
    workflow.connect("optimizer", "packager", {
        "metrics": "metrics",
        "score": "score",
        "iteration": "iteration"
    })
    
    workflow.connect("analyzer", "packager", {
        "analysis": "analysis"
    })
    
    workflow.connect("packager", "switch", {
        "result.switch_data": "input_data"
    })
    
    # Create cycle
    workflow.connect(
        "switch",
        "optimizer",
        condition="false_output",
        mapping={"false_output.metrics": "metrics"},
        cycle=True,
        max_iterations=30,
        convergence_check="score >= 0.95"
    )
    
    return workflow
```

## Convergence Patterns

### 1. Score-Based Convergence
```python
# In packager
converged = optimization_score >= 0.95

# In workflow
convergence_check="optimization_score >= 0.95"
```

### 2. Multi-Criteria Convergence
```python
def check_convergence(score: float, iteration: int, improvement: float) -> bool:
    return (
        score >= 0.95 or  # Target reached
        iteration >= 50 or  # Max iterations
        improvement < 0.001  # Minimal improvement
    )
```

### 3. Adaptive Convergence
```python
class AdaptiveConvergenceNode(CycleAwareNode):
    def run(self, context, **kwargs):
        history = self.accumulate_values(context, "scores", score)
        
        # Check trend
        if len(history) > 5:
            recent_improvement = max(history[-5:]) - min(history[-5:])
            if recent_improvement < 0.001:
                return {"converged": True, "reason": "stagnation"}
        
        # Check target
        if score >= self.target:
            return {"converged": True, "reason": "target_reached"}
        
        return {"converged": False}
```

## Common Pitfalls

### 1. Lost Parameters After First Iteration

❌ **Wrong**:
```python
def run(self, context, **kwargs):
    # These will be empty after first iteration!
    targets = kwargs.get("targets", {})
    constraints = kwargs.get("constraints", {})
```

✅ **Correct**:
```python
def run(self, context, **kwargs):
    prev_state = self.get_previous_state(context)
    targets = kwargs.get("targets", {})
    
    # Restore from state if not provided
    if not targets and prev_state.get("targets"):
        targets = prev_state["targets"]
```

### 2. Incorrect Switch Input Structure

❌ **Wrong**:
```python
# Switch expects input_data with specific structure
workflow.connect("analyzer", "switch", {
    "converged": "converged"  # Switch can't find this!
})
```

✅ **Correct**:
```python
# Use packager to create proper structure
workflow.connect("packager", "switch", {
    "result.switch_data": "input_data"
})
```

### 3. Missing Iteration Tracking

❌ **Wrong**:
```python
# No way to track iterations
return {"metrics": optimized}
```

✅ **Correct**:
```python
# Include iteration for tracking
return {
    "metrics": optimized,
    "iteration": self.get_iteration(context)
}
```

## Production Examples

### Simple Self-Loop
```python
# See: sdk-users/workflows/by-pattern/cyclic/final_working_cycle.py
workflow.connect(
    "optimizer",
    "optimizer",
    mapping={
        "efficiency": "efficiency",
        "quality": "quality",
        "cost": "cost",
        "performance": "performance"
    },
    cycle=True,
    max_iterations=25,
    convergence_check="score >= 0.95"
)
```

### Complex Multi-Node Cycle
```python
# See: sdk-users/workflows/by-pattern/cyclic/cycle_aware_enhancements.py
# Features:
# - Multiple optimization nodes
# - Convergence analysis
# - Agent coordination
# - Business value tracking
```

## Best Practices

1. **Always preserve configuration state** between iterations
2. **Use explicit parameter mapping** in connections
3. **Implement proper convergence conditions** to prevent infinite loops
4. **Add iteration limits** as safety measures
5. **Log progress** at regular intervals (e.g., every 5 iterations)
6. **Test with small iteration counts** first
7. **Monitor resource usage** in production

## Runtime Configuration

```python
runtime = LocalRuntime(
    enable_cycles=True,  # Required for cyclic workflows
    enable_monitoring=True,  # Track performance
    debug=False  # Set True for detailed logging
)

results, execution_id = runtime.execute(workflow, parameters=initial_params)
```

## Debugging Tips

1. Enable debug mode in runtime
2. Add logging in packager functions
3. Check parameter flow between nodes
4. Verify convergence conditions
5. Monitor iteration counts
6. Validate state preservation

## Further Reading

- [CycleAwareNode API Reference](../api/cycle-aware-node.md)
- [Convergence Patterns](../patterns/convergence-patterns.md)
- [Optimization Workflows](../workflows/by-pattern/optimization/)
- [Training Pattern #14](../../# contrib (removed)/training/critical-patterns/14-cyclic-workflow-parameter-propagation.md)