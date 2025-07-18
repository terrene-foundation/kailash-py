# Parameter Passing Guide - Complete Reference

*Master parameter flow in Kailash workflows with confidence*

## Overview

Parameter passing is crucial for workflow success. This guide covers all parameter-related patterns, best practices, and common pitfalls.

## Prerequisites

- Completed [Fundamentals](01-fundamentals.md) - Core concepts
- Completed [Workflows](02-workflows.md) - Basic patterns
- Understanding of Python dictionaries and kwargs

## Enterprise-Grade Parameter Resolution

### 4-Phase Parameter Resolution System

Kailash implements a sophisticated **4-phase parameter resolution system** that provides enterprise-grade validation, type safety, and auto-mapping capabilities:

#### Phase 1: Parameter Declaration & Validation
- **NodeParameter schema validation**: Every parameter must be declared with type, requirements, and constraints
- **Type safety enforcement**: Automatic type checking and conversion
- **Enterprise validation**: Complex validation rules, constraints, and business logic

#### Phase 2: Multi-Source Parameter Collection
- **Runtime parameters**: From `runtime.execute(workflow, parameters={})`
- **Node configuration**: Default values from node construction
- **Connection mapping**: Dynamic data flow between nodes
- **Auto-mapping resolution**: Automatic parameter discovery and connection

#### Phase 3: Priority Resolution & Merging
- **Conflict resolution**: Intelligent priority-based parameter merging
- **Type-safe merging**: Maintains type integrity across all sources
- **Validation enforcement**: Ensures all required parameters are present

#### Phase 4: Enterprise Features
- **Auto-mapping capabilities**: `auto_map_primary=True`, `auto_map_from=["alt1"]`
- **Workflow aliases**: `workflow_alias="name"` for parameter discovery
- **Tenant isolation**: Multi-tenant parameter scoping
- **Audit trails**: Complete parameter resolution logging

### Basic Parameter Flow

```python
# Phase 1: Runtime parameters (highest priority)
runtime.execute(workflow, parameters={
    "node_id": {
        "param1": "value1",
        "param2": 123
    }
})

# Phase 2: Connection mapping (dynamic priority)
workflow.connect("source", "target", mapping={"output": "input"})

# Phase 3: Node configuration (lowest priority)
node = MyNode(config_param="default")

# Phase 4: Auto-mapping (intelligent discovery)
# Automatically discovers and maps compatible parameters
```

**Resolution Priority**: Connection inputs > Runtime parameters > Node config > Auto-mapping

## Node Parameter Declaration

### CRITICAL: Declare ALL Input Parameters

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
                default=0.8,
                description="Processing threshold"
            ),
            "config": NodeParameter(
                name="config",
                type=dict,
                required=False,
                default={},
                description="Additional configuration"
            )
        }

    def run(self, **kwargs):
        # Only declared parameters are available
        data = kwargs.get("data", [])
        threshold = kwargs.get("threshold", 0.8)
        config = kwargs.get("config", {})

        # Process data...
        filtered = [x for x in data if x > threshold]

        return {
            "result": filtered,
            "count": len(filtered),
            "threshold_used": threshold
        }
```

**Why**: The Node base class validates and filters parameters. Only declared parameters are passed to `run()`.

### Parameter Types Reference

```python
# Basic types - use Python built-ins, not typing generics
"count": NodeParameter(name="count", type=int, required=True)
"name": NodeParameter(name="name", type=str, required=False, default="")
"ratio": NodeParameter(name="ratio", type=float, required=False, default=1.0)
"active": NodeParameter(name="active", type=bool, required=False, default=True)

# Collection types
"items": NodeParameter(name="items", type=list, required=True)
"data": NodeParameter(name="data", type=dict, required=False, default={})

# ❌ WRONG - Don't use generic types
from typing import List, Dict
"items": NodeParameter(type=List[str], required=True)  # Will fail!

# ✅ CORRECT - Use basic Python types
"items": NodeParameter(type=list, required=True)
```

## Connection Mapping

### Basic Connection Patterns

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# 1. Auto-mapping (when parameter names match)
workflow.connect("reader", "processor")  # data → data

# 2. Explicit mapping
workflow.connect("source", "target", mapping={"result": "data"})

# 3. Dot notation for nested data
workflow.connect("analyzer", "reporter", mapping={
    "result.summary": "summary_data",
    "result.metrics.accuracy": "accuracy"
})

# 4. Multiple mappings
workflow.connect("processor", "writer", mapping={
    "result.processed_data": "data",
    "result.metadata": "headers",
    "result.stats.total": "record_count"
})
```

### PythonCodeNode Patterns

```python
# ✅ CORRECT - Always wrap outputs in result dict
workflow.add_node("PythonCodeNode", "processor", {
    "code": """
# Input parameters are available as variables
processed = [x * 2 for x in input_data]
stats = {"count": len(processed), "sum": sum(processed)}

# MUST assign to 'result'
result = {
    "data": processed,
    "statistics": stats,
    "success": True
}
"""
})

# Connect using dot notation
workflow.connect("processor", "result.data", mapping={"consumer": "input_data"})
workflow.connect("processor", "result.statistics", mapping={"analyzer": "stats"})
```

### Complex Mapping Example

```python
# Source node outputs nested structure
workflow.add_node("PythonCodeNode", "data_source", {
    "code": """
result = {
    "customers": [
        {"id": 1, "name": "Alice", "score": 85},
        {"id": 2, "name": "Bob", "score": 92}
    ],
    "metadata": {
        "timestamp": "2024-01-01",
        "version": "1.0"
    },
    "summary": {
        "total": 2,
        "average_score": 88.5
    }
}
"""
})

# Map to multiple consumers
workflow.connect("data_source", "result.customers", mapping={"processor": "customer_list"})
workflow.connect("data_source", "result.summary.average_score", mapping={"validator": "baseline_score"})
workflow.connect("data_source", "result.metadata", mapping={"logger": "meta_info"})
```

## Cycle Parameters

### Cycle-Aware Nodes

```python
from kailash.nodes.base_cycle_aware import CycleAwareNode, NodeParameter

class IterativeOptimizerNode(CycleAwareNode):
    """Node that improves results over iterations."""

    def get_parameters(self):
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Data to optimize"
            ),
            "learning_rate": NodeParameter(
                name="learning_rate",
                type=float,
                required=False,
                default=0.01,
                description="Rate of improvement"
            ),
            "target_score": NodeParameter(
                name="target_score",
                type=float,
                required=False,
                default=0.95,
                description="Target optimization score"
            )
        }

    def run(self, **kwargs):
        # Get parameters
        data = kwargs.get("data", [])
        learning_rate = kwargs.get("learning_rate", 0.01)
        target_score = kwargs.get("target_score", 0.95)

        # Access cycle context
        context = kwargs.get("context", {})
        iteration = self.get_iteration(context)
        previous_state = self.get_previous_state(context)

        # Get previous score or start at 0
        current_score = previous_state.get("score", 0.0)

        # Improve score
        improvement = learning_rate * (1 - current_score)
        new_score = min(current_score + improvement, 1.0)

        # Check convergence
        converged = new_score >= target_score

        # Process data (example transformation)
        processed_data = [x * (1 + improvement) for x in data]

        return {
            "result": processed_data,
            "score": new_score,
            "converged": converged,
            "iteration": iteration,
            "improvement": improvement,
            **self.set_cycle_state({"score": new_score})
        }
```

### Using Cycles in Workflows

```python
workflow = WorkflowBuilder()

# Add cycle-aware node
workflow.add_node("IterativeOptimizerNode", "optimizer", {
    "learning_rate": 0.1,
    "target_score": 0.98
})

# Create self-loop for iteration
workflow.connect("optimizer", "result", mapping={"optimizer": "data"},
    cycle=True,
    max_iterations=50,
    convergence_check="converged == True"
)

# Execute with initial parameters
results, run_id = runtime.execute(workflow.build(), parameters={
    "optimizer": {
        "data": [1.0, 2.0, 3.0, 4.0, 5.0],
        "learning_rate": 0.05  # Override default
    }
})
```

### Multi-Node Cycles

```python
# Create a cycle between processor and validator
workflow = WorkflowBuilder()

workflow.add_node("DataProcessorNode", "processor")
workflow.add_node("QualityValidatorNode", "validator")

# Connect in a cycle
workflow.connect("processor", "result.data", mapping={"validator": "input_data"})
workflow.connect("validator", "result.validated_data", mapping={"processor": "data"},
    cycle=True,
    max_iterations=10,
    convergence_check="quality_score >= 0.95"
)

# Initial parameters for both nodes
runtime.execute(workflow.build(), parameters={
    "processor": {
        "data": initial_data,
        "processing_mode": "iterative"
    },
    "validator": {
        "threshold": 0.8,
        "strict_mode": True
    }
})
```

## Common Pitfalls and Solutions

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

# ✅ CORRECT - Declare all parameters
class MyNode(Node):
    def get_parameters(self):
        return {
            "input": NodeParameter(type=str, required=True),
            "config": NodeParameter(type=dict, required=False, default={})
        }
```

### 2. Wrong Connection Syntax

```python
# ❌ WRONG - Using old/incorrect parameter names
workflow.connect("a", "b", parameter_mapping={"out": "in"})
workflow.connect("a", "b", output_mapping={"result": "data"})

# ✅ CORRECT - Current syntax
workflow.connect("a", "result", mapping={"b": "data"})
workflow.connect("a", "b", mapping={"result": "data"})
```

### 3. Not Wrapping PythonCodeNode Output

```python
# ❌ WRONG - Direct assignment
workflow.add_node("PythonCodeNode", "processor", {
    "code": "processed_data = [x * 2 for x in data]"
})

# ✅ CORRECT - Wrap in result dict
workflow.add_node("PythonCodeNode", "processor", {
    "code": """
processed_data = [x * 2 for x in data]
result = {"processed": processed_data}
"""
})
```

### 4. Forgetting Context Parameter

```python
# ❌ WRONG - Trying to declare context
def get_parameters(self):
    return {
        "data": NodeParameter(type=list, required=True),
        "context": NodeParameter(type=dict, required=False)  # Don't do this!
    }

# ✅ CORRECT - Context is automatic
def run(self, **kwargs):
    data = kwargs.get("data", [])
    context = kwargs.get("context", {})  # Always available, don't declare
```

## Debugging Techniques

### Parameter Inspector Node

```python
class ParameterInspectorNode(Node):
    """Insert this node to debug parameter flow."""

    def get_parameters(self):
        # Accept any parameters by not restricting
        return {}

    def run(self, **kwargs):
        print("=== Parameter Inspector ===")
        print(f"Received {len(kwargs)} parameters:")

        for key, value in sorted(kwargs.items()):
            if key != "context":
                value_type = type(value).__name__
                value_preview = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                print(f"  {key}: {value_type} = {value_preview}")

        # Check for cycle context
        context = kwargs.get("context", {})
        if "cycle" in context:
            cycle_info = context["cycle"]
            print(f"\nCycle information:")
            print(f"  Iteration: {cycle_info.get('iteration', 0)}")
            print(f"  Previous state: {cycle_info.get('previous_state', {})}")

        # Pass through all parameters
        return {"result": kwargs}

# Use in workflow for debugging
workflow.add_node("ParameterInspectorNode", "inspector")
workflow.connect("problematic_node", "result", mapping={"inspector": "debug_input"})
```

### Logging Parameter Flow

```python
import logging

# Enable debug logging for parameter flow
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("kailash.workflow")
logger.setLevel(logging.DEBUG)

# This will show detailed parameter passing information
```

## Best Practices

### 1. Always Declare Parameters

```python
def get_parameters(self):
    """Declare EVERY parameter your node will use."""
    return {
        "primary_input": NodeParameter(
            name="primary_input",
            type=dict,
            required=True,
            description="Main input data"
        ),
        "config_option": NodeParameter(
            name="config_option",
            type=str,
            required=False,
            default="auto",
            description="Configuration mode"
        ),
        "threshold": NodeParameter(
            name="threshold",
            type=float,
            required=False,
            default=0.8,
            description="Processing threshold (0-1)"
        ),
    }
```

### 2. Use Clear Naming

```python
# ❌ Poor naming
"d": NodeParameter(type=list)
"val": NodeParameter(type=float)
"cfg": NodeParameter(type=dict)

# ✅ Clear naming
"customer_data": NodeParameter(type=list, description="List of customer records")
"confidence_threshold": NodeParameter(type=float, description="Min confidence (0-1)")
"processing_config": NodeParameter(type=dict, description="Processing configuration")
```

### 3. Document Parameter Flow

```python
# Add comments to clarify parameter flow
workflow = WorkflowBuilder()

# Data source outputs: {result: {customers: [...], metadata: {...}}}
workflow.add_node("CustomerDataNode", "source")

# Processor expects: {customer_list: [...], config: {...}}
workflow.add_node("ProcessorNode", "processor")

# Clear mapping with documentation
workflow.connect(
    "source", "result.customers",    # From nested output
    "processor", "customer_list",     # To expected input
    # mapping={"result.customers": "customer_list"}  # Alternative syntax
)
```

### 4. Validate Parameters Early

```python
def run(self, **kwargs):
    # Get and validate parameters
    data = kwargs.get("data", [])
    if not isinstance(data, list):
        raise TypeError(f"Expected list for 'data', got {type(data).__name__}")

    threshold = kwargs.get("threshold", 0.8)
    if not 0 <= threshold <= 1:
        raise ValueError(f"Threshold must be between 0 and 1, got {threshold}")

    # Process with validated parameters
    # ...
```

## Testing Parameter Flow

```python
def test_parameter_scenarios():
    """Test different parameter passing scenarios."""

    # Test 1: Initial parameters only
    result1 = runtime.execute(workflow.build(), parameters={
        "processor": {"batch_size": 50, "mode": "fast"}
    })

    # Test 2: Connection overrides initial parameters
    workflow_with_connection = WorkflowBuilder()
    workflow_with_connection.add_connection(
        "source", "result.config.batch_size",
        "processor", "batch_size"
    )
    result2 = runtime.execute(workflow_with_connection.build())

    # Test 3: Cycle with persistent parameters
    cycle_workflow = create_cycle_workflow()
    result3 = runtime.execute(cycle_workflow, parameters={
        "optimizer": {
            "learning_rate": 0.01,
            "momentum": 0.9
        }
    })

    # Verify parameters were used correctly
    assert result1["processor"]["result"]["batch_size_used"] == 50
    assert result3["optimizer"]["result"]["final_learning_rate"] == 0.01
```

## Advanced Parameter Injection

### Auto-Mapping Parameters

Kailash supports automatic parameter mapping for flexible node design:

```python
from kailash.nodes.base import Node, NodeParameter

class FlexibleProcessorNode(Node):
    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            # Primary auto-mapping - receives any unmapped parameter
            "primary_input": NodeParameter(
                name="primary_input",
                type=dict,
                required=True,
                auto_map_primary=True,  # Gets any unmapped parameters
                description="Primary data input"
            ),

            # Alternative name mapping
            "config_data": NodeParameter(
                name="config_data",
                type=dict,
                required=False,
                auto_map_from=["config", "settings", "options"],  # Any of these names work
                description="Configuration parameters"
            ),

            # Specific parameter
            "batch_size": NodeParameter(
                name="batch_size",
                type=int,
                required=False,
                default=32,
                description="Processing batch size"
            )
        }

    def run(self, **kwargs):
        primary_input = kwargs.get("primary_input", {})
        config_data = kwargs.get("config_data", {})
        batch_size = kwargs.get("batch_size", 32)

        return {
            "result": {
                "processed": True,
                "input_keys": list(primary_input.keys()),
                "config_applied": len(config_data),
                "batch_size": batch_size
            }
        }
```

### Dot Notation Access

Use dot notation for accessing nested output data:

```python
workflow = WorkflowBuilder()

# Producer node with nested output
workflow.add_node("DataProducerNode", "producer", {
    "data_type": "analytics"
})

# Consumer using dot notation to access nested data
workflow.add_node("DataConsumerNode", "consumer", {
    "threshold": 0.5
})

# Connect using dot notation for nested access
workflow.connect(
    "producer", "consumer",
    "result.analytics.metrics",  # Source: nested path
    "input_metrics"              # Target: parameter name
)

# Also works with deeper nesting
workflow.connect(
    "producer", "consumer",
    "result.metadata.quality.score",  # Deep nested access
    "quality_score"
)

# Execute workflow
result = await runtime.execute(workflow.build(), parameters={
    "producer": {"data_type": "user_behavior"}
})
```

### Parameter Injection Patterns

Advanced patterns for dynamic parameter injection:

```python
class SmartMergerNode(Node):
    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            # Auto-map any inputs starting with "data_"
            "data_inputs": NodeParameter(
                name="data_inputs",
                type=dict,
                required=False,
                auto_map_pattern="data_*",  # Matches data_source1, data_source2, etc.
                description="All data inputs"
            ),

            # Auto-map configuration inputs
            "config_inputs": NodeParameter(
                name="config_inputs",
                type=dict,
                required=False,
                auto_map_pattern="config_*",  # Matches config_db, config_api, etc.
                description="All configuration inputs"
            ),

            # Fallback for everything else
            "other_inputs": NodeParameter(
                name="other_inputs",
                type=dict,
                required=False,
                auto_map_primary=True,  # Gets remaining unmapped parameters
                description="Any other parameters"
            )
        }

    def run(self, **kwargs):
        data_inputs = kwargs.get("data_inputs", {})
        config_inputs = kwargs.get("config_inputs", {})
        other_inputs = kwargs.get("other_inputs", {})

        # Merge all data sources
        merged_data = {}
        for key, value in data_inputs.items():
            if isinstance(value, dict):
                merged_data.update(value)

        return {
            "result": {
                "merged_data": merged_data,
                "data_sources": len(data_inputs),
                "config_count": len(config_inputs),
                "other_params": len(other_inputs)
            }
        }

# Usage with automatic parameter injection
workflow = WorkflowBuilder()

workflow.add_node("DataSourceNode", "source1", {"type": "database"})
workflow.add_node("DataSourceNode", "source2", {"type": "api"})
workflow.add_node("ConfigNode", "db_config", {"host": "localhost"})
workflow.add_node("SmartMergerNode", "merger")

# Auto-injected based on parameter patterns
workflow.connect("source1", "merger", mapping={"result": "data_source1"})  # Matches data_*
workflow.connect("source2", "merger", mapping={"result": "data_source2"})  # Matches data_*
workflow.connect("db_config", "merger", mapping={"result": "config_db"})   # Matches config_*

result = await runtime.execute(workflow.build())
```

### Best Practices for Parameter Injection

```python
# 1. Use auto_map_primary sparingly - only for truly generic nodes
class GenericProcessorNode(Node):
    def get_parameters(self):
        return {
            "data": NodeParameter(
                name="data",
                type=dict,
                auto_map_primary=True,  # Only when you need to accept anything
                description="Any input data"
            )
        }

# 2. Prefer specific parameter names with auto_map_from for aliases
class UserProcessorNode(Node):
    def get_parameters(self):
        return {
            "user_data": NodeParameter(
                name="user_data",
                type=dict,
                auto_map_from=["users", "user_info", "user_records"],  # Clear aliases
                description="User information data"
            )
        }

# 3. Use dot notation for clear data access patterns
workflow.connect(
    "analytics", "reporter",
    "result.user_metrics.engagement",  # Clear path
    "engagement_data"
)

# 4. Document parameter injection behavior
class FlexibleNode(Node):
    """
    Node that accepts flexible inputs via parameter injection.

    Auto-mapping behavior:
    - primary_data: Maps from any unmapped parameter
    - config: Maps from 'config', 'settings', or 'options'
    - Supports dot notation: result.data.metrics
    """
    pass
```

## Related Guides

**Prerequisites:**
- [Fundamentals](01-fundamentals.md) - Core concepts
- [Workflows](02-workflows.md) - Workflow basics

**Advanced Topics:**
- [Custom Development](05-custom-development.md) - Creating custom nodes
- [Troubleshooting](../validation/common-mistakes.md) - Common parameter issues

---

**Master parameter passing to build robust, flexible workflows that handle complex data flows with ease!**
