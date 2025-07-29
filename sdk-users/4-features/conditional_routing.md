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
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.logic import SwitchNode
from kailash.nodes.base import Node, NodeParameter

class ValidationNode(Node):
    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=True),
            "threshold": NodeParameter(name="threshold", type=float, default=0.8)
        }

    def run(self, **kwargs):
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
workflow = WorkflowBuilder()

# Add source data
workflow.add_node("PythonCodeNode", "source", {
    "code": "result = [100, 90, 110]"  # Test data
})

workflow.add_node("PythonCodeNode", "validator", {
    "code": """
data = input_data if isinstance(input_data, list) else [100, 90, 110]
threshold = 95.0

quality = sum(data) / len(data) if data else 0
is_valid = quality >= threshold

result = {
    "data": data,
    "quality": quality,
    "is_valid": is_valid
}
"""
})

workflow.add_node("SwitchNode", "switch", {
    "condition_field": "is_valid",
    "operator": "==",
    "value": True
})

workflow.add_node("PythonCodeNode", "success_handler", {
    "code": """
quality = input_data.get('quality', 0)
result = {"result": f"Success! Quality: {quality}"}
"""
})

workflow.add_node("PythonCodeNode", "retry_handler", {
    "code": """
quality = input_data.get('quality', 0)
result = {"result": f"Retry needed. Quality: {quality}"}
"""
})

# Connections
workflow.add_connection("source", "result", "validator", "input_data")
workflow.add_connection("validator", "result", "switch", "input_data")
workflow.add_connection("switch", "true_output", "success_handler", "input_data")
workflow.add_connection("switch", "false_output", "retry_handler", "input_data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

### 2. Multi-Case Status Routing

Route based on multiple possible status values:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.logic import SwitchNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

class StatusCheckerNode(Node):
    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=True)
        }

    def run(self, **kwargs):
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

# Create workflow for multi-case routing
workflow = WorkflowBuilder()

# Add nodes
workflow.add_node("StatusCheckerNode", "checker", {}))
workflow.add_node("SwitchNode", "router", {}))
workflow.add_node("error_handler", PythonCodeNode.from_function(
    lambda data, status: {"result": f"Error: No data to process"}
))
workflow.add_node("simple_processor", PythonCodeNode.from_function(
    lambda data, status: {"result": f"Simple processing for {len(data)} items"}
))
workflow.add_node("standard_processor", PythonCodeNode.from_function(
    lambda data, status: {"result": f"Standard processing for {len(data)} items"}
))
workflow.add_node("batch_processor", PythonCodeNode.from_function(
    lambda data, status: {"result": f"Batch processing for {len(data)} items"}
))

# Connect nodes
workflow.add_connection("condition_check", "result", "router", "input_data")
workflow.add_connection("router", "path_a", "processor_a", "input_data")
workflow.add_connection("router", "path_b", "processor_b", "input_data")
workflow.add_connection("router", "default", "default_processor", "input_data")
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters

```

### 3. Conditional Retry Loops (Critical Pattern)

**This is the most important pattern for cyclic workflows with conditional routing:**

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

class DataProcessorNode(Node):
    def run(self, **kwargs):
        data = kwargs.get("data", [])
        iteration = self.context.get("cycle", {}).get("iteration", 0)

        # Improve data quality on each iteration
        processed = [x * (1 + iteration * 0.1) for x in data]
        quality = min(1.0, 0.3 + iteration * 0.15)

        return {
            "data": processed,
            "quality": quality,
            "iteration": iteration
        }

class QualityCheckerNode(Node):
    def run(self, **kwargs):
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
workflow = WorkflowBuilder()

# (This section was already fixed above - adding nodes to the existing workflow)
# The workflow nodes and connections are already properly defined above

# Conditional routing from switch
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

### 4. Error Handling with Fallback Routes

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

def complex_processing(data):
    """Simulated complex processing that might fail"""
    if not data or len(data) < 3:
        raise ValueError("Insufficient data for complex processing")
    return [x * 2 + 1 for x in data]

def simple_processing(data):
    """Fallback simple processing"""
    return [x + 1 for x in data] if data else []

class SafeProcessorNode(Node):
    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=True)
        }

    def run(self, **kwargs):
        data = kwargs.get("data", [])

        try:
            # Attempt complex processing
            result = complex_processing(data)
            return {"data": result, "status": "success"}
        except Exception as e:
            # Fallback to simple processing
            simple_result = simple_processing(data)
            return {"data": simple_result, "status": "fallback", "error": str(e)}

# Error handling workflow
workflow = WorkflowBuilder()

workflow.add_node("SafeProcessorNode", "processor", {}))
workflow.add_node("SwitchNode", "status_check", {}))
workflow.add_node("success_path", PythonCodeNode.from_function(
    lambda data, status: {"result": f"Complex processing successful: {data}"}
))
workflow.add_node("error_recovery", PythonCodeNode.from_function(
    lambda data, status, error: {"result": f"Fallback processing used: {data}, Error: {error}"}
))

workflow.add_connection("processor", "result", "status_check", "input")
workflow.add_connection("status_check", "result", "success_path", "input")
workflow.add_connection("status_check", "result", "error_recovery", "input")

```

### 5. Data Filtering and Transformation

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.logic import SwitchNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

class DataFilterNode(Node):
    def get_parameters(self):
        return {
            "items": NodeParameter(name="items", type=list, required=True)
        }

    def run(self, **kwargs):
        items = kwargs.get("items", [])

        # Categorize items
        high_priority = [item for item in items if item.get("priority", 0) > 7]
        medium_priority = [item for item in items if 3 <= item.get("priority", 0) <= 7]
        low_priority = [item for item in items if item.get("priority", 0) < 3]

        # Determine routing based on content
        if high_priority:
            # route removed, "route": route, "item_count": len(data)}

# Data filtering and transformation workflow
workflow = WorkflowBuilder()

workflow.add_node("DataFilterNode", "filter", {}))
workflow.add_node("SwitchNode", "router", {}))
workflow.add_node("urgent_processor", PythonCodeNode.from_function(
    lambda data, route, item_count: {"result": f"URGENT: Processing {item_count} high-priority items"}
))
workflow.add_node("standard_processor", PythonCodeNode.from_function(
    lambda data, route, item_count: {"result": f"STANDARD: Processing {item_count} medium-priority items"}
))
workflow.add_node("batch_processor", PythonCodeNode.from_function(
    lambda data, route, item_count: {"result": f"BATCH: Processing {item_count} low-priority items"}
))

workflow.add_connection("condition_check", "result", "router", "input_data")
workflow.add_connection("router", "path_a", "processor_a", "input_data")
workflow.add_connection("router", "path_b", "processor_b", "input_data")
workflow.add_connection("router", "default", "default_processor", "input_data")

```

## Advanced Patterns

### Nested Conditional Workflows

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.logic import SwitchNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

class PrimaryConditionNode(Node):
    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=dict, required=True)
        }

    def run(self, **kwargs):
        data = kwargs.get("data", {})
        # Primary condition: check if data has required fields
        primary_condition = all(key in data for key in ["name", "value"])
        return {"data": data, "primary_condition": primary_condition}

class SecondaryConditionNode(Node):
    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=dict, required=True),
            "primary_condition": NodeParameter(name="primary_condition", type=bool, required=True)
        }

    def run(self, **kwargs):
        data = kwargs.get("data", {})
        primary_condition = kwargs.get("primary_condition")
        # Secondary condition: check if value is within acceptable range
        secondary_condition = data.get("value", 0) > 10
        return {
            "data": data,
            "primary_condition": primary_condition,
            "secondary_condition": secondary_condition
        }

# Nested conditional workflow
workflow = WorkflowBuilder()

# Primary condition check
workflow.add_node("PrimaryConditionNode", "primary_check", {}))
workflow.add_node("SwitchNode", "primary_switch", {}))

# Secondary condition check
workflow.add_node("SecondaryConditionNode", "secondary_check", {}))
workflow.add_node("SwitchNode", "secondary_switch", {}))

# Processing nodes
workflow.add_node("final_processor", PythonCodeNode.from_function(
    lambda data, primary_condition, secondary_condition: {
        "result": f"Final processing: {data['name']} with value {data['value']}"
    }
))
workflow.add_node("fallback_processor", PythonCodeNode.from_function(
    lambda data, primary_condition, secondary_condition: {
        "result": f"Fallback processing: {data['name']} with low value {data['value']}"
    }
))
workflow.add_node("alternative_path", PythonCodeNode.from_function(
    lambda data, primary_condition: {
        "result": f"Alternative processing: incomplete data {data}"
    }
))

# Nested routing
workflow.add_connection("primary_check", "result", "primary_switch", "input")
workflow.add_connection("primary_switch", "result", "secondary_check", "input")
workflow.add_connection("primary_switch", "result", "alternative_path", "input")
workflow.add_connection("secondary_check", "result", "secondary_switch", "input")
workflow.add_connection("secondary_switch", "result", "final_processor", "input")
workflow.add_connection("secondary_switch", "result", "fallback_processor", "input")

```

### Merging Conditional Branches

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.logic import MergeNode, SwitchNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

class ConditionNode(Node):
    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=dict, required=True)
        }

    def run(self, **kwargs):
        data = kwargs.get("data", {})
        # Simple condition based on data type
        condition = data.get("type") == "premium"
        return {"data": data, "condition": condition}

# Merging conditional branches workflow
workflow = WorkflowBuilder()

# Process data through different paths
workflow.add_node("ConditionNode", "condition_check", {}))
workflow.add_node("SwitchNode", "router", {}))
workflow.add_node("path_a", PythonCodeNode.from_function(
    lambda data, condition: {"result": f"Premium processing for {data}", "path": "A"}
))
workflow.add_node("path_b", PythonCodeNode.from_function(
    lambda data, condition: {"result": f"Standard processing for {data}", "path": "B"}
))

# Merge results back together
workflow.add_node("MergeNode", "merger", {}))
workflow.add_node("final_processor", PythonCodeNode.from_function(
    lambda merged_result: {"final_result": f"Final processing of merged data: {merged_result}"}
))

# Routing and merging
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow.add_connection("path_a", "result", "merger", "input")
workflow.add_connection("path_b", "result", "merger", "input")
workflow.add_connection("merger", "result", "final_processor", "input")

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
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# ✅ Good: Clear condition field names
class DecisionNode(Node):
    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=True),
            "threshold": NodeParameter(name="threshold", type=float, default=0.8)
        }

    def run(self, **kwargs):
        data = kwargs.get("data", [])
        threshold = kwargs.get("threshold", 0.8)

        # Process data (example processing)
        processed_data = [x * 1.1 for x in data] if data else []
        quality = sum(processed_data) / len(processed_data) if processed_data else 0
        success = quality > threshold

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
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# ✅ Good: Proper cycle configuration with SwitchNode
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# ✅ Good: Clear convergence conditions
workflow.add_connection("switch", "result", "finish_node", "input")

```

### 4. Error Handling
```python
class RobustSwitchNode(Node):
    def get_parameters(self):
        return {
            "condition": NodeParameter(name="condition", type=str, required=False)
        }

    def run(self, **kwargs):
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
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

class LoggingNode(Node):
    def get_parameters(self):
        return {
            "condition": NodeParameter(name="condition", type=str, required=False),
            "route": NodeParameter(name="route", type=str, required=False),
            "data": NodeParameter(name="data", type=list, required=False)
        }

    def run(self, **kwargs):
        condition = kwargs.get("condition", "N/A")
        # route removed, "N/A")
        data = kwargs.get("data", [])
        data_size = len(data) if data else 0

        print(f"Debug: condition={condition}, # route removed, data_size={data_size}")
        return kwargs  # Pass through

workflow.add_node("LoggingNode", "debug", {}))
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow.add_connection("debug", "result", "switch", "input")

   ```

2. **Monitor Cycle State**
   ```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

class CycleMonitorNode(Node):
    def get_parameters(self):
        return {}  # No specific parameters required

    def run(self, **kwargs):
        cycle_info = self.context.get("cycle", {})
        print(f"Cycle iteration: {cycle_info.get('iteration', 0)}")
        return kwargs  # Pass through

   ```

3. **Validate Routes**
   ```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Add validation before switching
class RouteValidatorNode(Node):
    def get_parameters(self):
        return {
            "route_decision": NodeParameter(name="route_decision", type=str, required=True)
        }

    def run(self, **kwargs):
        # route removed)
        valid_routes = ["retry", "finish", "error"]

        if route not in valid_routes:
            return {"route_decision": "error", "validation_error": f"Invalid route: {route}"}

        return kwargs

   ```

## Migration from Other Patterns

### From Simple Cycles
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Before: Simple cycle without conditions
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# After: Conditional cycle with SwitchNode
workflow.add_node("SwitchNode", "switch", {}))
workflow.add_connection("processor", "result", "switch", "input")
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()
workflow.add_connection("switch", "result", "output", "input")

```

### From Complex Node Logic
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

def condition_a(data):
    return len(data) > 10

def condition_b(data):
    return len(data) > 5

def process_path_a(data):
    return {"result": f"Path A: Large dataset processing for {len(data)} items"}

def process_path_b(data):
    return {"result": f"Path B: Medium dataset processing for {len(data)} items"}

def process_default(data):
    return {"result": f"Default: Small dataset processing for {len(data)} items"}

# Before: Complex logic in single node
class ComplexProcessorNode(Node):
    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=True)
        }

    def run(self, **kwargs):
        data = kwargs["data"]

        if condition_a(data):
            return process_path_a(data)
        elif condition_b(data):
            return process_path_b(data)
        else:
            return process_default(data)

# After: Separated concerns with SwitchNode
class ConditionEvaluatorNode(Node):
    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=True)
        }

    def run(self, **kwargs):
        data = kwargs["data"]

        if condition_a(data):
            path = "path_a"
        elif condition_b(data):
            path = "path_b"
        else:
            path = "default"

        return {"data": data, "path": path}

workflow = WorkflowBuilder()
workflow.add_node("ConditionEvaluatorNode", "condition_check", {}))
workflow.add_node("SwitchNode", "router", {}))
workflow.add_node("processor_a", PythonCodeNode.from_function(
    lambda data, path: process_path_a(data)
))
workflow.add_node("processor_b", PythonCodeNode.from_function(
    lambda data, path: process_path_b(data)
))
workflow.add_node("default_processor", PythonCodeNode.from_function(
    lambda data, path: process_default(data)
))

workflow.add_connection("condition_check", "result", "router", "input_data")
workflow.add_connection("router", "path_a", "processor_a", "input_data")
workflow.add_connection("router", "path_b", "processor_b", "input_data")
workflow.add_connection("router", "default", "default_processor", "input_data")

```

## Conclusion

Conditional routing with SwitchNode provides powerful capabilities for creating dynamic, responsive workflows. The key patterns covered in this guide enable:

- **Quality improvement loops**: Iterative processing until conditions are met
- **Error handling**: Graceful degradation and recovery paths
- **Data routing**: Processing optimization based on data characteristics
- **Complex decision trees**: Multi-stage conditional logic

Use these patterns to build robust, maintainable workflows that can adapt to varying runtime conditions while maintaining clear separation of concerns.
