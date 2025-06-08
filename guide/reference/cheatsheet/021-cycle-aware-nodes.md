# Cycle-Aware Nodes

## CycleAwareNode Base Class

Inherit from `CycleAwareNode` to eliminate cycle management boilerplate and access built-in helpers.

```python
from kailash.nodes.base import CycleAwareNode, NodeParameter
from typing import Any, Dict

class QualityImproverNode(CycleAwareNode):
    """Example cycle-aware node with built-in helpers."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[]),
            "quality": NodeParameter(name="quality", type=float, required=False, default=0.0),
            "improvement_rate": NodeParameter(name="improvement_rate", type=float, required=False, default=0.1)
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        # Use built-in cycle helpers
        iteration = self.get_iteration(context)
        is_first = self.is_first_iteration(context)
        prev_state = self.get_previous_state(context)

        # Get parameters
        data = kwargs.get("data", [])
        quality = kwargs.get("quality", 0.0)
        improvement_rate = kwargs.get("improvement_rate", 0.1)

        # Log progress (built-in helper)
        if is_first:
            self.log_cycle_info(context, "Starting quality improvement process")

        # Improve quality based on iteration
        improved_quality = min(1.0, quality + (improvement_rate * (1 - quality)))

        # Accumulate quality history (built-in helper)
        quality_history = self.accumulate_values(context, "quality_history", improved_quality, max_history=20)

        # Process data
        processed_data = [x * (1 + improved_quality) for x in data]

        # Log progress periodically
        if iteration % 5 == 0:
            avg_quality = sum(quality_history) / len(quality_history) if quality_history else 0
            self.log_cycle_info(context, f"Average quality: {avg_quality:.3f}")

        return {
            "data": processed_data,
            "quality": improved_quality,
            "quality_history": quality_history[-5:],  # Return last 5 for display
            **self.set_cycle_state({
                "quality_history": quality_history,
                "best_quality": max(quality_history) if quality_history else improved_quality
            })
        }
```

## CycleAwareNode Helper Methods

### Iteration Information
```python
def run(self, context, **kwargs):
    # Get current iteration number (0-based)
    iteration = self.get_iteration(context)

    # Check if this is the first iteration
    is_first = self.is_first_iteration(context)

    # Use in logic
    if is_first:
        self.log_cycle_info(context, "Initializing process")
        initial_setup()
    else:
        self.log_cycle_info(context, f"Continuing process, iteration {iteration}")
```

### State Management
```python
def run(self, context, **kwargs):
    # Get state from previous iteration (returns {} if first iteration)
    prev_state = self.get_previous_state(context)

    # Access previous values safely
    prev_error = prev_state.get("error", float('inf'))
    learning_rate = prev_state.get("learning_rate", 0.5)

    # Process and calculate new values
    current_error = calculate_error()

    # Adaptive learning rate based on progress
    if prev_error != float('inf'):
        improvement = (prev_error - current_error) / prev_error
        if improvement < 0.01:  # Slow progress
            learning_rate *= 0.9

    # Save state for next iteration
    return {
        "result": processed_result,
        **self.set_cycle_state({
            "error": current_error,
            "learning_rate": learning_rate,
            "improvement_history": prev_state.get("improvement_history", []) + [improvement]
        })
    }
```

### Value Accumulation
```python
def run(self, context, **kwargs):
    current_value = process_data(kwargs.get("data"))

    # Accumulate values across iterations
    values_history = self.accumulate_values(
        context,
        "values",
        current_value,
        max_history=100  # Keep last 100 values
    )

    # Use accumulated values for analysis
    if len(values_history) > 5:
        recent_avg = sum(values_history[-5:]) / 5
        overall_avg = sum(values_history) / len(values_history)
        trend = "improving" if recent_avg > overall_avg else "declining"

    return {
        "current_value": current_value,
        "trend": trend,
        "history_length": len(values_history)
    }
```

### Convergence Detection
```python
def run(self, context, **kwargs):
    current_error = calculate_error(kwargs.get("data"))

    # Detect convergence trend
    is_converging = self.detect_convergence_trend(
        context,
        "error_values",
        current_error,
        threshold=0.1,  # Values must be within 10% of each other
        window=5        # Check last 5 values
    )

    return {
        "error": current_error,
        "is_converging": is_converging,
        "should_continue": not is_converging
    }
```

## ConvergenceCheckerNode Patterns

### Basic Threshold Convergence
```python
from kailash.nodes.logic import ConvergenceCheckerNode

# Add convergence checker to workflow
workflow.add_node("convergence", ConvergenceCheckerNode())

# Execute with threshold mode
runtime.execute(workflow, parameters={
    "convergence": {
        "threshold": 0.85,
        "mode": "threshold"
    }
})

# Connect with data pass-through
workflow.connect("processor", "convergence",
    mapping={"quality": "value", "data": "data"})
workflow.connect("convergence", "next_node",
    mapping={"data": "data", "converged": "is_done"})
```

### Stability-Based Convergence
```python
# Check for stability (low variance in recent values)
runtime.execute(workflow, parameters={
    "convergence": {
        "mode": "stability",
        "stability_window": 5,      # Check last 5 values
        "min_variance": 0.01        # Variance threshold
    }
})
```

### Improvement Rate Convergence
```python
# Check if improvement rate is too slow
runtime.execute(workflow, parameters={
    "convergence": {
        "mode": "improvement",
        "min_improvement": 0.02,    # Minimum 2% improvement
        "improvement_window": 3     # Check last 3 iterations
    }
})
```

### Combined Convergence Criteria
```python
# Multiple criteria must be met
runtime.execute(workflow, parameters={
    "convergence": {
        "mode": "combined",
        "threshold": 0.9,           # Value threshold
        "stability_window": 3,      # Stability check
        "min_variance": 0.005       # Low variance required
    }
})
```

## NodeParameter Patterns for Cycles

### ✅ Correct: Use required=False with defaults
```python
def get_parameters(self) -> Dict[str, NodeParameter]:
    return {
        "data": NodeParameter(
            name="data",
            type=list,
            required=False,     # Always False for cycle nodes
            default=[],         # Provide default
            description="Input data to process"
        ),
        "threshold": NodeParameter(
            name="threshold",
            type=float,
            required=False,     # Always False
            default=0.8,        # Provide default
            description="Quality threshold"
        )
    }
```

### ✅ Correct: Use simple types
```python
# Use simple types, not Union types
"value": NodeParameter(name="value", type=float, required=False, default=0.0)

# Not: Union[float, int] - this causes validation errors
```

### ✅ Correct: Pass-through data parameter
```python
def get_parameters(self) -> Dict[str, NodeParameter]:
    return {
        "value": NodeParameter(name="value", type=float, required=False),
        "data": NodeParameter(
            name="data",
            type=Any,
            required=False,
            description="Pass-through data to preserve in output"
        )
    }

def run(self, context, **kwargs):
    # Process the value
    value = kwargs.get("value", 0.0)
    result = process_value(value)

    # Always pass through data if provided
    output = {"processed_value": result}
    if "data" in kwargs:
        output["data"] = kwargs["data"]

    return output
```

## MultiCriteriaConvergenceNode Pattern

### Configuration Persistence
```python
from kailash.nodes.logic import MultiCriteriaConvergenceNode

class PersistentMultiCriteriaNode(MultiCriteriaConvergenceNode):
    """Handles criteria persistence across iterations."""

    def run(self, context, **kwargs):
        # Store criteria on first iteration, reuse on subsequent iterations
        if self.is_first_iteration(context):
            criteria = kwargs.get("criteria", {})
            self._stored_criteria = criteria
            self.log_cycle_info(context, f"Stored {len(criteria)} criteria")
        else:
            criteria = getattr(self, "_stored_criteria", {})
            if not criteria:
                self.log_cycle_info(context, "Warning: No stored criteria found")

        # Update kwargs with stored criteria
        kwargs["criteria"] = criteria

        # Call parent implementation
        return super().run(context, **kwargs)

# Usage in workflow
workflow.add_node("multi_convergence", PersistentMultiCriteriaNode())

# Execute with multiple criteria
runtime.execute(workflow, parameters={
    "multi_convergence": {
        "criteria": {
            "accuracy": {"threshold": 0.95, "mode": "threshold"},
            "latency": {"threshold": 20, "mode": "threshold", "direction": "minimize"},
            "cost": {"threshold": 200, "mode": "threshold", "direction": "minimize"}
        },
        "require_all": True  # All criteria must be met
    }
})
```

## Advanced Cycle-Aware Patterns

### Adaptive Processing
```python
class AdaptiveProcessorNode(CycleAwareNode):
    """Adapts processing based on iteration progress."""

    def run(self, context, **kwargs):
        iteration = self.get_iteration(context)
        prev_state = self.get_previous_state(context)

        # Get adaptive parameters
        base_learning_rate = kwargs.get("learning_rate", 0.1)
        data = kwargs.get("data", [])

        # Adapt learning rate based on progress
        if iteration > 0:
            prev_error = prev_state.get("error", float('inf'))
            current_error = calculate_error(data)

            if current_error >= prev_error:  # No improvement
                learning_rate = base_learning_rate * 0.8  # Reduce
            else:
                learning_rate = base_learning_rate * 1.1  # Increase
        else:
            learning_rate = base_learning_rate
            current_error = calculate_error(data)

        # Process with adaptive rate
        processed_data = process_with_rate(data, learning_rate)

        # Save state and return
        return {
            "data": processed_data,
            "error": current_error,
            "learning_rate": learning_rate,
            **self.set_cycle_state({
                "error": current_error,
                "learning_rate": learning_rate
            })
        }
```

### Progress Monitoring
```python
class ProgressMonitorNode(CycleAwareNode):
    """Monitors and reports progress across iterations."""

    def run(self, context, **kwargs):
        iteration = self.get_iteration(context)
        data = kwargs.get("data", [])

        # Calculate current metrics
        current_score = calculate_score(data)

        # Track progress
        scores = self.accumulate_values(context, "scores", current_score)

        # Calculate progress indicators
        if len(scores) > 1:
            improvement = scores[-1] - scores[-2]
            avg_improvement = sum(scores[i] - scores[i-1] for i in range(1, len(scores))) / (len(scores) - 1)
            is_improving = improvement > 0
            improvement_rate = improvement / scores[-2] if scores[-2] != 0 else 0
        else:
            improvement = 0
            avg_improvement = 0
            is_improving = True
            improvement_rate = 0

        # Log progress periodically
        if iteration % 3 == 0:
            self.log_cycle_info(context,
                f"Progress: Score={current_score:.3f}, "
                f"Improvement={improvement:.3f}, "
                f"Rate={improvement_rate:.1%}")

        return {
            "data": data,
            "score": current_score,
            "improvement": improvement,
            "avg_improvement": avg_improvement,
            "is_improving": is_improving,
            "improvement_rate": improvement_rate,
            "should_continue": abs(improvement) > 0.01  # Continue if improving
        }
```

## Integration with Regular Nodes

### Mixing CycleAware and Regular Nodes
```python
# You can mix cycle-aware and regular nodes in the same workflow
workflow = Workflow("mixed-cycle", "Mixed Node Types")

# Regular input node
workflow.add_node("input", CSVReaderNode(), file_path="data.csv")

# Cycle-aware processing node
workflow.add_node("processor", AdaptiveProcessorNode())

# Regular transformation node
workflow.add_node("transformer", DataTransformerNode(),
    operations=[{"type": "normalize"}])

# Cycle-aware convergence node
workflow.add_node("convergence", ConvergenceCheckerNode())

# Regular output node
workflow.add_node("output", JSONWriterNode(), file_path="result.json")

# Connect in cycle
workflow.connect("input", "processor")
workflow.connect("processor", "transformer")
workflow.connect("transformer", "convergence")
workflow.connect("convergence", "processor",
    mapping={"data": "data"},
    cycle=True,
    max_iterations=50,
    convergence_check="converged == True")
workflow.connect("convergence", "output",
    mapping={"data": "data"})
```
