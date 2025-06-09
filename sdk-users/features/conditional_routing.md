# Conditional Routing in Workflows

Conditional routing enables workflows to make dynamic decisions about execution paths based on runtime data. This guide covers how to implement conditional routing using SwitchNode and MergeNode for complex workflow patterns.

## Overview

Conditional routing allows workflows to:
- Branch execution based on data conditions
- Implement retry loops with exit conditions
- Create quality improvement cycles
- Handle error conditions gracefully
- Route data through different processing paths

## Core Components

### SwitchNode

The `SwitchNode` is the primary component for conditional routing, supporting:
- **Boolean conditions**: Simple true/false branching
- **Multi-case switching**: Route to different paths based on field values
- **Complex expressions**: Support for various operators and conditions
- **Dynamic routing**: Runtime evaluation of conditions

### MergeNode

The `MergeNode` combines outputs from multiple conditional branches back into a single stream.

## Conditional Routing Patterns

### 1. Simple Boolean Routing

Route execution based on a boolean condition:

```python
from kailash import Workflow
from kailash.nodes.logic import SwitchNode
from kailash.nodes.base import Node, NodeParameter

class ValidationNode(Node):
    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=True),
            "threshold": NodeParameter(name="threshold", type=float, default=0.8)
        }

    def run(self, context, **kwargs):
        data = kwargs["data"]
        threshold = kwargs["threshold"]

        quality = sum(data) / len(data) if data else 0
        is_valid = quality >= threshold

        return {
            "data": data,
            "quality": quality,
            "is_valid": is_valid
        }

# Workflow setup
workflow = Workflow("boolean-routing", "Simple Boolean Routing")

workflow.add_node("validator", ValidationNode())
workflow.add_node("switch", SwitchNode(
    condition_field="is_valid",
    true_route="success_handler",
    false_route="retry_handler"
))
workflow.add_node("success_handler", SuccessNode())
workflow.add_node("retry_handler", RetryNode())

# Connections
workflow.connect("validator", "switch")
workflow.connect("switch", "success_handler", route="success_handler")
workflow.connect("switch", "retry_handler", route="retry_handler")
```

### 2. Multi-Case Status Routing

Route based on multiple possible status values:

```python
class StatusCheckerNode(Node):
    def run(self, context, **kwargs):
        data = kwargs.get("data", [])

        if not data:
            status = "empty"
        elif len(data) < 10:
            status = "small"
        elif len(data) < 100:
            status = "medium"
        else:
            status = "large"

        return {"data": data, "status": status}

workflow.add_node("checker", StatusCheckerNode())
workflow.add_node("router", SwitchNode(
    condition_field="status",
    routes={
        "empty": "error_handler",
        "small": "simple_processor",
        "medium": "standard_processor",
        "large": "batch_processor"
    }
))

# Connect to different processors based on data size
workflow.connect("checker", "router")
workflow.connect("router", "error_handler", route="error_handler")
workflow.connect("router", "simple_processor", route="simple_processor")
workflow.connect("router", "standard_processor", route="standard_processor")
workflow.connect("router", "batch_processor", route="batch_processor")
```

### 3. Conditional Retry Loops (Critical Pattern)

**This is the most important pattern for cyclic workflows with conditional routing:**

```python
class DataProcessorNode(Node):
    def run(self, context, **kwargs):
        data = kwargs.get("data", [])
        iteration = context.get("cycle", {}).get("iteration", 0)

        # Improve data quality on each iteration
        processed = [x * (1 + iteration * 0.1) for x in data]
        quality = min(1.0, 0.3 + iteration * 0.15)

        return {
            "data": processed,
            "quality": quality,
            "iteration": iteration
        }

class QualityCheckerNode(Node):
    def run(self, context, **kwargs):
        quality = kwargs.get("quality", 0.0)
        data = kwargs.get("data", [])
        iteration = kwargs.get("iteration", 0)

        # Decision logic
        quality_sufficient = quality >= 0.8
        max_iterations_reached = iteration >= 5

        if quality_sufficient or max_iterations_reached:
            route_decision = "finish"
        else:
            route_decision = "retry"

        return {
            "data": data,
            "quality": quality,
            "route_decision": route_decision,
            "should_continue": route_decision == "retry"
        }

# Critical Pattern: A → B → C → D → SwitchNode → (B if retry | E if finish)
workflow = Workflow("conditional-cycle", "Quality Improvement Loop")

workflow.add_node("input", InputNode())           # A
workflow.add_node("processor", DataProcessorNode())  # B
workflow.add_node("transformer", TransformNode())    # C
workflow.add_node("checker", QualityCheckerNode())   # D
workflow.add_node("switch", SwitchNode(
    condition_field="route_decision",
    routes={
        "retry": "processor",  # Back to B
        "finish": "output"     # Continue to E
    }
))
workflow.add_node("output", OutputNode())        # E

# Linear flow: A → B → C → D → Switch
workflow.connect("input", "processor")
workflow.connect("processor", "transformer",
                mapping={"data": "data", "quality": "quality"})
workflow.connect("transformer", "checker",
                mapping={"data": "data", "quality": "quality"})
workflow.connect("checker", "switch", mapping={
    "data": "data",
    "route_decision": "route_decision",
    "should_continue": "should_continue"
})

# Conditional routing from switch
workflow.connect("switch", "processor",           # Cycle back to B
    route="retry",
    mapping={"data": "data"},
    cycle=True,
    max_iterations=10,
    convergence_check="should_continue == False")

workflow.connect("switch", "output",              # Continue to E
    route="finish",
    mapping={"data": "data", "quality": "quality"})
```

### 4. Error Handling with Fallback Routes

```python
class SafeProcessorNode(Node):
    def run(self, context, **kwargs):
        data = kwargs.get("data", [])

        try:
            # Attempt complex processing
            result = complex_processing(data)
            return {"data": result, "status": "success"}
        except Exception as e:
            # Fallback to simple processing
            simple_result = simple_processing(data)
            return {"data": simple_result, "status": "fallback", "error": str(e)}

workflow.add_node("processor", SafeProcessorNode())
workflow.add_node("status_check", SwitchNode(
    condition_field="status",
    routes={
        "success": "success_path",
        "fallback": "error_recovery"
    }
))

workflow.connect("processor", "status_check")
workflow.connect("status_check", "success_path", route="success")
workflow.connect("status_check", "error_recovery", route="fallback")
```

### 5. Data Filtering and Transformation

```python
class DataFilterNode(Node):
    def run(self, context, **kwargs):
        items = kwargs.get("items", [])

        # Categorize items
        high_priority = [item for item in items if item.get("priority", 0) > 7]
        medium_priority = [item for item in items if 3 <= item.get("priority", 0) <= 7]
        low_priority = [item for item in items if item.get("priority", 0) < 3]

        # Determine routing based on content
        if high_priority:
            route = "urgent_processing"
            data = high_priority
        elif medium_priority:
            route = "standard_processing"
            data = medium_priority
        else:
            route = "batch_processing"
            data = low_priority

        return {"data": data, "route": route, "item_count": len(data)}

workflow.add_node("filter", DataFilterNode())
workflow.add_node("router", SwitchNode(
    condition_field="route",
    routes={
        "urgent_processing": "urgent_handler",
        "standard_processing": "standard_handler",
        "batch_processing": "batch_handler"
    }
))
```

## Advanced Patterns

### Nested Conditional Workflows

```python
# Primary condition check
workflow.add_node("primary_check", PrimaryConditionNode())
workflow.add_node("primary_switch", SwitchNode(
    condition_field="primary_condition",
    true_route="secondary_check",
    false_route="alternative_path"
))

# Secondary condition check
workflow.add_node("secondary_check", SecondaryConditionNode())
workflow.add_node("secondary_switch", SwitchNode(
    condition_field="secondary_condition",
    true_route="final_processor",
    false_route="fallback_processor"
))

# Nested routing
workflow.connect("primary_check", "primary_switch")
workflow.connect("primary_switch", "secondary_check", route="secondary_check")
workflow.connect("primary_switch", "alternative_path", route="alternative_path")
workflow.connect("secondary_check", "secondary_switch")
workflow.connect("secondary_switch", "final_processor", route="final_processor")
workflow.connect("secondary_switch", "fallback_processor", route="fallback_processor")
```

### Merging Conditional Branches

```python
from kailash.nodes.logic import MergeNode

# Process data through different paths
workflow.add_node("condition_check", ConditionNode())
workflow.add_node("router", SwitchNode(
    condition_field="condition",
    true_route="path_a",
    false_route="path_b"
))
workflow.add_node("path_a", ProcessorA())
workflow.add_node("path_b", ProcessorB())

# Merge results back together
workflow.add_node("merger", MergeNode(
    merge_strategy="combine",  # or "latest", "first"
    output_field="merged_result"
))
workflow.add_node("final_processor", FinalProcessorNode())

# Routing and merging
workflow.connect("condition_check", "router")
workflow.connect("router", "path_a", route="path_a")
workflow.connect("router", "path_b", route="path_b")
workflow.connect("path_a", "merger")
workflow.connect("path_b", "merger")
workflow.connect("merger", "final_processor")
```

## Best Practices

### 1. Clear Route Naming
```python
# ✅ Good: Descriptive route names
routes = {
    "high_quality": "success_handler",
    "needs_improvement": "retry_processor",
    "failed_validation": "error_handler"
}

# ❌ Avoid: Generic route names
routes = {"true": "node1", "false": "node2"}
```

### 2. Explicit Condition Fields
```python
# ✅ Good: Clear condition field names
class DecisionNode(Node):
    def run(self, context, **kwargs):
        return {
            "data": processed_data,
            "routing_decision": "continue" if success else "retry",
            "quality_sufficient": quality > threshold
        }

# ❌ Avoid: Ambiguous boolean flags
return {"data": data, "flag": True, "ok": success}
```

### 3. Cycle Integration
```python
# ✅ Good: Proper cycle configuration with SwitchNode
workflow.connect("switch", "retry_node",
    route="retry",
    cycle=True,
    max_iterations=10,
    convergence_check="should_continue == False")

# ✅ Good: Clear convergence conditions
workflow.connect("switch", "finish_node",
    route="finish")
```

### 4. Error Handling
```python
class RobustSwitchNode(Node):
    def run(self, context, **kwargs):
        condition = kwargs.get("condition")

        # Always provide default route
        if condition is None:
            return {"route": "default", "error": "Missing condition"}

        # Handle expected values
        if condition == "success":
            return {"route": "success_path"}
        elif condition == "retry":
            return {"route": "retry_path"}
        else:
            return {"route": "error_path", "unexpected_value": condition}
```

## Performance Considerations

### 1. Minimize Route Evaluation
- Keep condition evaluation logic simple
- Cache expensive computations
- Avoid complex nested conditions in single nodes

### 2. Cycle Optimization
- Set reasonable `max_iterations` limits
- Use efficient convergence checks
- Monitor cycle performance in production

### 3. Memory Management
- Clean up large data objects in routes
- Consider data size when routing to different processors
- Use streaming for large datasets

## Troubleshooting

### Common Issues

1. **Route Not Found**
   ```
   Error: Route 'invalid_route' not found in SwitchNode
   ```
   **Solution**: Ensure all possible condition values have corresponding routes

2. **Infinite Cycles**
   ```
   Warning: Cycle exceeded max_iterations (10)
   ```
   **Solution**: Check convergence conditions and ensure they can be satisfied

3. **Missing Condition Field**
   ```
   Error: Condition field 'status' not found in input
   ```
   **Solution**: Verify upstream nodes provide required condition fields

### Debugging Tips

1. **Add Logging Nodes**
   ```python
   workflow.add_node("debug", LoggingNode(
       fields=["condition", "route", "data_size"]
   ))
   workflow.connect("condition_check", "debug")
   workflow.connect("debug", "switch")
   ```

2. **Monitor Cycle State**
   ```python
   class CycleMonitorNode(Node):
       def run(self, context, **kwargs):
           cycle_info = context.get("cycle", {})
           print(f"Cycle iteration: {cycle_info.get('iteration', 0)}")
           return kwargs  # Pass through
   ```

3. **Validate Routes**
   ```python
   # Add validation before switching
   class RouteValidatorNode(Node):
       def run(self, context, **kwargs):
           route = kwargs.get("route_decision")
           valid_routes = ["retry", "finish", "error"]

           if route not in valid_routes:
               return {"route_decision": "error", "validation_error": f"Invalid route: {route}"}

           return kwargs
   ```

## Migration from Other Patterns

### From Simple Cycles
```python
# Before: Simple cycle without conditions
workflow.connect("processor", "processor",
    cycle=True, max_iterations=5)

# After: Conditional cycle with SwitchNode
workflow.add_node("switch", SwitchNode(
    condition_field="should_continue",
    true_route="processor",
    false_route="output"
))
workflow.connect("processor", "switch")
workflow.connect("switch", "processor", route="processor", cycle=True)
workflow.connect("switch", "output", route="output")
```

### From Complex Node Logic
```python
# Before: Complex logic in single node
class ComplexProcessorNode(Node):
    def run(self, context, **kwargs):
        data = kwargs["data"]

        if condition_a(data):
            return process_path_a(data)
        elif condition_b(data):
            return process_path_b(data)
        else:
            return process_default(data)

# After: Separated concerns with SwitchNode
workflow.add_node("condition_check", ConditionEvaluatorNode())
workflow.add_node("router", SwitchNode(
    condition_field="routing_decision",
    routes={
        "path_a": "processor_a",
        "path_b": "processor_b",
        "default": "default_processor"
    }
))
workflow.add_node("processor_a", ProcessorANode())
workflow.add_node("processor_b", ProcessorBNode())
workflow.add_node("default_processor", DefaultProcessorNode())
```

## Conclusion

Conditional routing with SwitchNode provides powerful capabilities for creating dynamic, responsive workflows. The key patterns covered in this guide enable:

- **Quality improvement loops**: Iterative processing until conditions are met
- **Error handling**: Graceful degradation and recovery paths
- **Data routing**: Processing optimization based on data characteristics
- **Complex decision trees**: Multi-stage conditional logic

Use these patterns to build robust, maintainable workflows that can adapt to varying runtime conditions while maintaining clear separation of concerns.
