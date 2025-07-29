# Parameter Passing Guide - Complete Reference

*Master parameter flow in Kailash workflows with confidence*

## 🎯 Overview

Parameter passing has been the #1 source of confusion in Kailash SDK. This guide consolidates all parameter-related patterns, fixes, and best practices in one place.

## 🚨 Critical Updates (v0.5.1+)

### Cycle Parameter Fix
**Before v0.5.1**: Initial parameters were lost after the first iteration in cycles
**After v0.5.1**: Initial parameters are now available throughout ALL cycle iterations

```python
from kailash.workflow.builder import WorkflowBuilder
# ✅ This now works correctly in ALL iterations
runtime.execute(workflow, parameters={
    "optimizer": {
        "target_efficiency": 0.90,  # Available in all iterations
        "learning_rate": 0.01       # No longer reverts to defaults
    }
})
```

## 📋 Table of Contents

1. [Basic Parameter Flow](#basic-parameter-flow)
2. [Node Parameter Declaration](#node-parameter-declaration)
3. [Connection Mapping](#connection-mapping)
4. [Cycle Parameters](#cycle-parameters)
5. [Common Pitfalls](#common-pitfalls)
6. [Debugging Techniques](#debugging-techniques)
7. [Best Practices](#best-practices)

## Basic Parameter Flow

### How Parameters Flow Through Workflows

```python
# 1. Initial parameters from runtime.execute()
runtime.execute(workflow, parameters={
    "node_id": {
        "param1": "value1",
        "param2": 123
    }
})

# 2. Node configuration (lowest priority)
node = MyNode(config_param="default")

# 3. Connection inputs (highest priority)
workflow.add_connection("source", "target", "output", "input")
```

**Priority Order**: Connection inputs > Initial parameters > Node config

## Node Parameter Declaration

### ✅ CRITICAL: Declare ALL Input Parameters

```python
from kailash.nodes.base import Node, NodeParameter

class DataProcessorNode(Node):
    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            # MUST declare every parameter the node will receive
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Input data to process"
            ),
            "threshold": NodeParameter(
                name="threshold",
                type=float,
                required=False,
                default=0.8
            )
        }

    def run(self, **kwargs):
        data = kwargs.get("data", [])  # Will only exist if declared above
        threshold = kwargs.get("threshold", 0.8)
        # Process data...
```

**Why**: The Node base class validates and filters parameters. Only declared parameters are passed to `run()`.

### Parameter Types Reference

```python
# Basic types
"count": NodeParameter(type=int, required=True)
"name": NodeParameter(type=str, required=False, default="")
"ratio": NodeParameter(type=float, required=False, default=1.0)
"active": NodeParameter(type=bool, required=False, default=True)

# Collection types (use basic Python types, not generics)
"items": NodeParameter(type=list, required=True)  # ✅ Correct
"data": NodeParameter(type=dict, required=False, default={})  # ✅ Correct

# ❌ WRONG - Don't use generic types
"items": NodeParameter(type=List[str], required=True)  # Will fail!
```

## Connection Mapping

### Basic Connection Patterns

```python
# 1. Auto-mapping (matching names)
workflow.add_connection("reader", "result", "processor", "input")  # data → data

# 2. Explicit mapping
workflow.add_connection("source", "target", "result", "data")

# 3. Dot notation for nested data
workflow.add_connection("analyzer", "result", "reporter", "input")

# 4. Multiple mappings
workflow.add_connection("processor", "result", "writer", "input")
```

### PythonCodeNode Patterns

```python
# ✅ CORRECT - Wrap outputs in result dict
code = '''
processed = [x * 2 for x in data]
stats = {"count": len(processed), "sum": sum(processed)}
result = {"data": processed, "statistics": stats}
'''

workflow.add_connection("processor", "result", "consumer", "input")
```

## Cycle Parameters

### Initial Parameters in Cycles (v0.5.1+)

```python
# Initial parameters are now preserved throughout all iterations
workflow = WorkflowBuilder()
workflow.add_node("OptimizerNode", "optimizer", {}))
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# These parameters will be available in ALL iterations
runtime.execute(workflow, parameters={
    "optimizer": {
        "learning_rate": 0.01,    # Available in iterations 0-19
        "momentum": 0.9,          # Not lost after iteration 0
        "target_loss": 0.001      # Consistent across all iterations
    }
})
```

### Cycle-Aware Node Pattern

```python
from kailash.nodes.base_cycle_aware import CycleAwareNode

class IterativeProcessor(CycleAwareNode):
    def get_parameters(self):
        return {
            "data": NodeParameter(type=list, required=True),
            "improvement_rate": NodeParameter(type=float, required=False, default=0.1)
        }

    def run(self, **kwargs):
        # Parameters from runtime.execute() are available
        data = kwargs.get("data", [])
        improvement_rate = kwargs.get("improvement_rate", 0.1)

        # Access cycle context
        context = kwargs.get("context", {})
        iteration = self.get_iteration(context)
        prev_quality = self.get_previous_state(context).get("quality", 0.0)

        # Process with improvement
        new_quality = prev_quality + improvement_rate
        converged = new_quality >= 0.95

        return {
            "quality": new_quality,
            "converged": converged,
            "iteration": iteration,
            **self.set_cycle_state({"quality": new_quality})
        }
```

### Parameter Flow in Multi-Node Cycles

```python
# In cycles A → B → A, parameters flow like this:
# Iteration 0: A gets initial params → B gets A's output → A gets B's output
# Iteration 1+: A gets B's output + initial params → B gets A's output → ...

workflow = WorkflowBuilder()
workflow.add_node("ProcessorNode", "processor", {}))
workflow.add_node("ValidatorNode", "validator", {}))

workflow.add_connection("processor", "validator", "result", "data")
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# Initial parameters available throughout
runtime.execute(workflow, parameters={
    "processor": {"batch_size": 100},  # Always available
    "validator": {"threshold": 0.9}     # Always available
})
```

## Common Pitfalls

### 1. Missing Parameter Declaration

```python
# ❌ WRONG - Parameter not declared
class MyNode(Node):
    def get_parameters(self):
        return {
            "input": NodeParameter(type=str, required=True)
            # Missing "config" parameter!
        }

    def run(self, **kwargs):
        input_data = kwargs.get("input")
        config = kwargs.get("config", {})  # Will always be {} - not declared!
```

### 2. Using Generic Types

```python
# ❌ WRONG
"items": NodeParameter(type=List[Dict[str, Any]], required=True)

# ✅ CORRECT
"items": NodeParameter(type=list, required=True)
```

### 3. Wrong Mapping Syntax

```python
# ❌ WRONG - Old syntax
# workflow.add_connection("source", "result", "target", "input")  # Fixed mapping pattern

# ✅ CORRECT - Current syntax
workflow.add_connection("a", "b", "out", "in")
```

### 4. Not Using Context Parameter

```python
# ❌ WRONG - Context not in parameters
def get_parameters(self):
    return {"data": NodeParameter(type=list, required=True)}

# ✅ CORRECT - Context is automatic, don't declare it
def run(self, **kwargs):
    context = kwargs.get("context", {})  # Always available
    data = kwargs.get("data", [])        # Your declared params
```

## Debugging Techniques

### 1. Parameter Inspector Node

```python
class ParameterInspectorNode(Node):
    """Insert this node to debug parameter flow"""

    def get_parameters(self):
        # Accept any parameters for inspection
        return {}

    def run(self, **kwargs):
        print("=== Parameter Inspector ===")
        print(f"Received {len(kwargs)} parameters:")
        for key, value in kwargs.items():
            if key != "context":
                print(f"  {key}: {type(value).__name__} = {value}")

        context = kwargs.get("context", {})
        if "cycle" in context:
            print(f"Cycle info: iteration={context['cycle'].get('iteration')}")

        return kwargs  # Pass through all parameters
```

### 2. Connection Validation

```python
def validate_connections(workflow):
    """Check all connections have valid mappings"""
    for edge in workflow.graph.edges(data=True):
        source, target, data = edge
        mapping = data.get("mapping", {})

        print(f"{source} → {target}:")
        if mapping:
            for src, dst in mapping.items():
                print(f"  {src} → {dst}")
        else:
            print("  (auto-mapping)")
```

### 3. Runtime Parameter Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# This will show parameter flow in CyclicWorkflowExecutor
logger = logging.getLogger("kailash.workflow.cyclic_runner")
logger.setLevel(logging.DEBUG)
```

## Best Practices

### 1. Always Declare Parameters

```python
def get_parameters(self):
    """Declare EVERY parameter your node will use"""
    return {
        "primary_input": NodeParameter(type=dict, required=True),
        "config_option": NodeParameter(type=str, required=False, default="auto"),
        "threshold": NodeParameter(type=float, required=False, default=0.8),
    }
```

### 2. Use Descriptive Parameter Names

```python
# ❌ Bad
"d": NodeParameter(type=list)
"val": NodeParameter(type=float)

# ✅ Good
"customer_data": NodeParameter(type=list, description="List of customer records")
"confidence_threshold": NodeParameter(type=float, description="Min confidence (0-1)")
```

### 3. Document Parameter Flow

```python
workflow = WorkflowBuilder()

# Document the flow
workflow.add_node("CSVReaderNode", "reader", {}))      # Output: {data: [...]}
workflow.add_node("FilterNode", "filter", {}))          # Input: data, Output: {filtered: [...]}
workflow.add_node("AnalyzerNode", "analyzer", {}))      # Input: records, Output: {stats: {...}}

# Clear mappings
workflow.add_connection("reader", "result", "filter", "input")               # data → data (auto)
workflow.add_connection("filter", "analyzer", "filtered", "records")
```

### 4. Test Parameter Scenarios

```python
def test_parameter_flow():
    """Test different parameter scenarios"""

    # Test 1: Initial parameters only
    result1 = runtime.execute(workflow, parameters={
        "processor": {"batch_size": 50}
    })

    # Test 2: Override with connection
    workflow.add_connection("source", "processor", "size", "batch_size")
    result2 = runtime.execute(workflow.build())

    # Test 3: Cycle parameters
    result3 = runtime.execute(cycle_workflow, parameters={
        "optimizer": {"learning_rate": 0.01}
    })

    # Verify parameters were used correctly
    assert result1["processor"]["batch_size_used"] == 50
    assert result3["optimizer"]["final_learning_rate"] == 0.01
```

## Migration Guide

### From Old API to New (v0.5.1+)

```python
# ❌ OLD - Pre-v0.5.1
runtime.execute(workflow, parameters={"node": {"param": "value"}})
# workflow.add_connection("source", "result", "target", "input")  # Fixed mapping pattern
converge_when="done == True"
get_cycle_iteration()
get_cycle_state()

# ✅ NEW - v0.5.1+
runtime.execute(workflow, parameters={"node": {"param": "value"}})
workflow.add_connection("a", "b", "out", "in")
convergence_check="done == True"
get_iteration(context)
get_previous_state(context)
```

## Related Documentation

- [Connection Patterns Cheatsheet](../cheatsheet/005-connection-patterns.md) - Quick connection examples
- [Cycle Debugging](../cheatsheet/022-cycle-debugging-troubleshooting.md) - Cycle-specific issues
- [Troubleshooting Guide](05-troubleshooting.md) - General error resolution
- [Node Development](06-custom-development.md) - Creating custom nodes

---

*Last updated for Kailash SDK v0.5.1 - Parameter passing improvements*
