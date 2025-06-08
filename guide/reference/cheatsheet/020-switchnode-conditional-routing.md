# SwitchNode Conditional Routing

## SwitchNode Mapping Requirements

### ✅ Correct: Use "output" Key for Complete Data Transfer
```python
# SwitchNode expects input_data parameter
# Use "output" key to transfer complete output dictionary
workflow.connect("processor", "quality_switch",
    mapping={"output": "input_data"})  # Entire output → input_data

# SwitchNode configuration
runtime.execute(workflow, parameters={
    "quality_switch": {
        "condition_field": "needs_improvement",  # Field within input_data
        "operator": "==",
        "value": True
    }
})
```

### ✅ Correct: Specific Field Mapping for Simple Data
```python
# When you know the specific field to pass
workflow.connect("processor", "switch",
    mapping={"status": "input_data"})  # Specific field → input_data

# Or map specific fields to specific switch fields
workflow.connect("processor", "switch",
    mapping={
        "data": "input_data",
        "quality_score": "threshold"
    })
```

### ❌ Wrong: Missing input_data Mapping
```python
# This fails - SwitchNode requires input_data parameter
workflow.connect("processor", "switch")  # No mapping
# Result: ValueError: Required parameter 'input_data' not provided

# This also fails - wrong parameter name
workflow.connect("processor", "switch",
    mapping={"result": "data"})  # Wrong - needs "input_data"
```

### ❌ Wrong: Empty Mapping in Cycles
```python
# Empty mapping transfers nothing
workflow.connect("switch", "processor",
    mapping={},  # Empty mapping = no data transfer
    cycle=True)
# Result: Nodes receive no data in cycle iterations
```

### ❌ Wrong: Generic "output" Mapping Fails in Cycles
```python
# This fails - output mapping doesn't preserve individual fields
workflow.connect("processor", "processor",
    mapping={"output": "output"},  # Generic mapping fails
    cycle=True)
# Result: Individual fields not preserved between iterations
# polling_count, quality_score, etc. reset each iteration
```

## SwitchNode Configuration Patterns

### Complete SwitchNode Setup for Cycles
```python
# Source node for initial data
class DataSourceNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        return {"data": kwargs.get("data", [])}

workflow = Workflow("switch-cycle", "Switch Cycle")
workflow.add_node("data_source", DataSourceNode())
workflow.add_node("processor", ProcessorNode())
workflow.add_node("quality_switch", SwitchNode())

# Initial data flow
workflow.connect("data_source", "processor", mapping={"data": "data"})

# Processor to switch - complete output transfer
workflow.connect("processor", "quality_switch",
    mapping={"output": "input_data"})

# Cycle back based on condition
workflow.connect("quality_switch", "processor",
    condition="false_output",  # Use switch output port
    mapping={"improved_data": "data"},
    cycle=True,
    max_iterations=10)

# Execute with proper parameters
runtime.execute(workflow, parameters={
    "data_source": {"data": [1, 2, 3, 60, 4, 5]},
    "quality_switch": {
        "condition_field": "needs_improvement",
        "operator": "==",
        "value": True
    }
})
```

## Critical Pattern: A → B → C → D → SwitchNode → (B if retry | E if finish)

This is the most important pattern for implementing iterative processing with conditional exit conditions.

```python
from kailash import Workflow
from kailash.nodes.logic import SwitchNode
from kailash.nodes.base import Node, NodeParameter

# Example: Quality Improvement Loop with Conditional Exit
workflow = Workflow("conditional-cycle", "Quality Improvement with Exit")

# A: Input data
workflow.add_node("input", InputNode())

# B: Process data (target for retry)
workflow.add_node("processor", DataProcessorNode())

# C: Transform/enhance data
workflow.add_node("transformer", DataTransformerNode())

# D: Check if we should continue or finish
workflow.add_node("quality_checker", QualityCheckerNode())

# SwitchNode: Route based on quality check
workflow.add_node("switch", SwitchNode(
    condition_field="should_continue",
    operator="==",
    value=True
))

# E: Final output (when finished)
workflow.add_node("output", OutputNode())

# Linear flow: A → B → C → D → SwitchNode
workflow.connect("input", "processor")
workflow.connect("processor", "transformer")
workflow.connect("transformer", "quality_checker")
workflow.connect("quality_checker", "switch")

# Conditional routing from SwitchNode
workflow.connect("switch", "processor",           # Back to B (retry)
    condition="false_output",                      # When should_continue == False
    mapping={"false_output.data": "data"},
    cycle=True,
    max_iterations=20,
    convergence_check="should_continue == False")

workflow.connect("switch", "output",              # To E (finish)
    condition="true_output",                       # When should_continue == True
    mapping={"true_output.data": "data"})
```

## SwitchNode Configuration Patterns

### Boolean Condition Routing
```python
# Simple true/false routing
switch = SwitchNode(
    condition_field="is_valid",
    operator="==",
    value=True
)

# Output: true_output or false_output
workflow.connect("switch", "success_handler",
    condition="true_output",
    mapping={"true_output": "data"})
workflow.connect("switch", "retry_handler",
    condition="false_output",
    mapping={"false_output": "data"})
```

### Multi-Case Routing
```python
# Route to different handlers based on status
switch = SwitchNode(
    condition_field="status",
    cases=["success", "warning", "error"]
)

# Output: case_success, case_warning, case_error, default
workflow.connect("switch", "success_processor",
    condition="case_success",
    mapping={"case_success": "data"})
workflow.connect("switch", "warning_processor",
    condition="case_warning",
    mapping={"case_warning": "data"})
workflow.connect("switch", "error_processor",
    condition="case_error",
    mapping={"case_error": "data"})
workflow.connect("switch", "default_processor",
    condition="default",
    mapping={"default": "data"})
```

### Numeric Threshold Routing
```python
# Route based on numeric thresholds
switch = SwitchNode(
    condition_field="score",
    operator=">=",
    value=0.8
)

# true_output for score >= 0.8, false_output for score < 0.8
workflow.connect("switch", "high_score_handler",
    condition="true_output")
workflow.connect("switch", "low_score_handler",
    condition="false_output")
```

## ConvergencePackager Pattern (For Cyclic SwitchNode)

When using SwitchNode in cycles, you often need to package convergence output properly:

```python
from kailash.nodes.base import CycleAwareNode

class ConvergencePackager(CycleAwareNode):
    """Packages convergence checker output for SwitchNode."""

    def get_parameters(self):
        return {
            "input": NodeParameter(name="input", type=dict, required=False),
            "converged": NodeParameter(name="converged", type=bool, required=False),
            "data": NodeParameter(name="data", type=Any, required=False),
            "value": NodeParameter(name="value", type=float, required=False)
        }

    def run(self, context, **kwargs):
        # Handle cyclic executor's parameter bundling
        if "input" in kwargs and len(kwargs) == 1:
            input_data = kwargs["input"]
        else:
            input_data = kwargs

        self.log_cycle_info(context, f"Packager routing: converged={input_data.get('converged')}")

        # Package for SwitchNode
        return {"input_data": input_data}

# Usage in workflow
workflow.add_node("convergence", ConvergenceCheckerNode())
workflow.add_node("packager", ConvergencePackager())
workflow.add_node("switch", SwitchNode(
    condition_field="converged",
    operator="==",
    value=True
))

workflow.connect("convergence", "packager")
workflow.connect("packager", "switch", mapping={"input_data": "input_data"})
```

## Quality Improvement Loop Example

```python
class QualityCheckerNode(Node):
    """Evaluates data quality and decides whether to continue or finish."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[]),
            "quality": NodeParameter(name="quality", type=float, required=False, default=0.0),
            "threshold": NodeParameter(name="threshold", type=float, required=False, default=0.85)
        }

    def run(self, context, **kwargs):
        data = kwargs.get("data", [])
        quality = kwargs.get("quality", 0.0)
        threshold = kwargs.get("threshold", 0.85)

        # Get iteration info
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        # Decision logic
        quality_sufficient = quality >= threshold
        max_iterations_reached = iteration >= 10

        # Should we continue processing?
        should_continue = not (quality_sufficient or max_iterations_reached)

        # Determine reason
        if quality_sufficient:
            reason = f"Quality threshold reached: {quality:.3f} >= {threshold}"
        elif max_iterations_reached:
            reason = f"Max iterations reached: {iteration}"
        else:
            reason = f"Quality insufficient: {quality:.3f} < {threshold}, continuing..."

        return {
            "data": data,
            "quality": quality,
            "should_continue": should_continue,
            "quality_sufficient": quality_sufficient,
            "reason": reason,
            "iteration": iteration
        }

# Workflow setup
workflow.add_node("processor", DataProcessorNode())
workflow.add_node("quality_checker", QualityCheckerNode())
workflow.add_node("switch", SwitchNode(
    condition_field="should_continue",
    operator="==",
    value=False  # Continue when should_continue is False
))
workflow.add_node("output", OutputNode())

# Flow: Process → Check → Switch
workflow.connect("processor", "quality_checker")
workflow.connect("quality_checker", "switch")

# Conditional routing
workflow.connect("switch", "processor",        # Continue processing
    condition="false_output",
    mapping={"false_output.data": "data"},
    cycle=True,
    max_iterations=20)

workflow.connect("switch", "output",           # Finish processing
    condition="true_output",
    mapping={"true_output.data": "data", "true_output.quality": "final_quality"})
```

## Error Handling with SwitchNode

```python
class ErrorHandlingSwitchNode(Node):
    """Demonstrates robust error handling in conditional routing."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=Any, required=False),
            "status": NodeParameter(name="status", type=str, required=False, default="unknown"),
            "error": NodeParameter(name="error", type=str, required=False)
        }

    def run(self, context, **kwargs):
        data = kwargs.get("data")
        status = kwargs.get("status", "unknown")
        error = kwargs.get("error")

        # Handle missing data
        if data is None:
            return {
                "route_decision": "error",
                "error": "No data provided",
                "data": None
            }

        # Handle error status
        if status == "error" or error:
            return {
                "route_decision": "error",
                "error": error or "Unknown error",
                "data": data
            }

        # Handle success
        if status == "success":
            return {
                "route_decision": "success",
                "data": data
            }

        # Default: retry
        return {
            "route_decision": "retry",
            "data": data,
            "message": f"Status '{status}' requires retry"
        }

# Workflow with error handling
workflow.add_node("processor", SafeProcessorNode())
workflow.add_node("error_checker", ErrorHandlingSwitchNode())
workflow.add_node("router", SwitchNode(
    condition_field="route_decision",
    cases=["success", "retry", "error"]
))

# Route to different handlers
workflow.connect("router", "success_handler", condition="case_success")
workflow.connect("router", "processor", condition="case_retry", cycle=True)
workflow.connect("router", "error_handler", condition="case_error")
```

## Complex Conditional Patterns

### Nested Decision Tree
```python
# Primary condition
workflow.add_node("primary_check", PrimaryConditionNode())
workflow.add_node("primary_switch", SwitchNode(
    condition_field="primary_result",
    operator="==",
    value="proceed"
))

# Secondary condition (when primary succeeds)
workflow.add_node("secondary_check", SecondaryConditionNode())
workflow.add_node("secondary_switch", SwitchNode(
    condition_field="secondary_result",
    cases=["optimize", "standard", "fallback"]
))

# Route through decision tree
workflow.connect("primary_check", "primary_switch")
workflow.connect("primary_switch", "secondary_check", condition="true_output")
workflow.connect("primary_switch", "fallback_processor", condition="false_output")
workflow.connect("secondary_check", "secondary_switch")
workflow.connect("secondary_switch", "optimize_processor", condition="case_optimize")
workflow.connect("secondary_switch", "standard_processor", condition="case_standard")
workflow.connect("secondary_switch", "fallback_processor", condition="case_fallback")
```

### Performance-Based Routing
```python
class PerformanceRouterNode(Node):
    """Routes based on system performance metrics."""

    def run(self, context, **kwargs):
        data = kwargs.get("data", [])
        data_size = len(data)

        # Get system metrics (simplified)
        cpu_usage = self.get_cpu_usage()  # 0.0 to 1.0
        memory_usage = self.get_memory_usage()  # 0.0 to 1.0

        # Routing decision based on load and data size
        if data_size > 10000 and cpu_usage > 0.8:
            route = "batch_processor"      # Queue for later
        elif data_size > 1000 and memory_usage > 0.9:
            route = "streaming_processor"  # Process in chunks
        elif data_size < 100:
            route = "fast_processor"       # Optimize for speed
        else:
            route = "standard_processor"   # Normal processing

        return {
            "data": data,
            "route": route,
            "cpu_usage": cpu_usage,
            "memory_usage": memory_usage,
            "data_size": data_size
        }

workflow.add_node("performance_router", PerformanceRouterNode())
workflow.add_node("switch", SwitchNode(
    condition_field="route",
    cases=["batch_processor", "streaming_processor", "fast_processor", "standard_processor"]
))
```

## Best Practices

### 1. Clear Condition Field Names
```python
# ✅ Good: Descriptive condition fields
def run(self, context, **kwargs):
    return {
        "data": processed_data,
        "routing_decision": "continue" if should_continue else "finish",
        "quality_threshold_met": quality > 0.8,
        "error_occurred": has_error
    }

# ❌ Avoid: Ambiguous condition fields
def run(self, context, **kwargs):
    return {"data": data, "flag": True, "ok": success}
```

### 2. Handle All Possible Routes
```python
# ✅ Good: Cover all cases
switch = SwitchNode(
    condition_field="status",
    cases=["success", "warning", "error"]
)
# Connect all cases: case_success, case_warning, case_error, default

# ❌ Avoid: Missing route handlers
# Only connecting case_success will cause errors for other statuses
```

### 3. Proper Cycle Configuration
```python
# ✅ Good: Clear cycle configuration
workflow.connect("switch", "retry_processor",
    condition="false_output",
    mapping={"false_output.data": "data"},
    cycle=True,
    max_iterations=20,
    convergence_check="should_continue == False")

# ✅ Good: Non-cycle exit route
workflow.connect("switch", "final_output",
    condition="true_output",
    mapping={"true_output": "final_data"})
```

## Related Patterns
- [019-cyclic-workflows-basics.md](019-cyclic-workflows-basics.md) - Basic cycle patterns
- [031-multi-path-conditional-cycle-patterns.md](031-multi-path-conditional-cycle-patterns.md) - Complex multi-path routing
- [030-cycle-state-persistence-patterns.md](030-cycle-state-persistence-patterns.md) - State handling

## Common Mistakes
- [072](../../mistakes/072-switchnode-mapping-specificity.md) - SwitchNode mapping issues
- [071](../../mistakes/071-cyclic-workflow-parameter-passing-patterns.md) - Parameter passing problems
