# Parameter Passing Guide - Enterprise Patterns

*Master enterprise-grade parameter passing with security, validation, and compliance*

## Overview

Parameter passing in Kailash is designed with **security-first principles**. This guide covers enterprise patterns, security requirements, and gold standard implementations.

## Prerequisites

- Completed [Fundamentals](01-fundamentals.md) - Core concepts
- Completed [Workflows](02-workflows.md) - Basic patterns
- Understanding of Python dictionaries and kwargs
- Familiarity with type annotations

## 🎯 Critical Understanding: Security by Design

The Kailash SDK requires **explicit parameter declaration** as a security feature, not a limitation. This aligns with enterprise best practices used by AWS, Google, and Microsoft.

### Why Explicit Declaration?

```python
# SDK's WorkflowParameterInjector logic (simplified)
def inject_parameters(self, node_instance, workflow_params):
    declared_params = node_instance.get_parameters()  # SDK checks this

    injected_params = {}
    for param_name, param_value in workflow_params.items():
        if param_name in declared_params:  # Only if explicitly declared
            injected_params[param_name] = param_value
        # else: parameter is ignored (security feature)

    return injected_params
```

**Security Benefits**:
- Prevents arbitrary parameter injection attacks
- Validates all inputs before execution
- Provides audit trails for compliance
- Prevents code injection through parameters

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
workflow.add_connection("source", "target", "output", "input")

# Phase 3: Node configuration (lowest priority)
node = MyNode(config_param="default")

# Phase 4: Auto-mapping (intelligent discovery)
# Automatically discovers and maps compatible parameters
```

**Resolution Priority**: Connection inputs > Runtime parameters > Node config > Auto-mapping

## Enterprise Parameter Patterns

### Pattern 1: Workflow-Specific Entry Nodes (Recommended)

Create dedicated entry nodes for each workflow type to ensure type safety and validation:

```python
from kailash.nodes.base import Node, NodeParameter
from typing import Dict, Any

class UserManagementEntryNode(Node):
    """Entry node specifically for user management workflows.

    Enterprise Pattern: Explicit parameter contracts for security.
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Declare ALL parameters with enterprise validation."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation: create_user, update_user, delete_user, get_user"
            ),
            "user_data": NodeParameter(
                name="user_data",
                type=dict,
                required=False,
                description="User data for create/update operations"
            ),
            "user_id": NodeParameter(
                name="user_id",
                type=str,
                required=False,
                description="User ID for get/update/delete operations"
            ),
            "tenant_id": NodeParameter(
                name="tenant_id",
                type=str,
                required=True,
                description="Tenant identifier for multi-tenancy"
            ),
            "requestor_id": NodeParameter(
                name="requestor_id",
                type=str,
                required=True,
                description="ID of user making the request"
            ),
            "audit_context": NodeParameter(
                name="audit_context",
                type=dict,
                required=False,
                default={},
                description="Audit context for compliance"
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Process with business logic validation."""
        # All parameters are validated by SDK before reaching here
        operation = kwargs["operation"]  # Required, guaranteed to exist
        tenant_id = kwargs["tenant_id"]  # Required, guaranteed to exist
        requestor_id = kwargs["requestor_id"]  # Required, guaranteed to exist

        # Business logic validation
        if operation in ["update", "delete", "get"] and not kwargs.get("user_id"):
            raise ValueError(f"user_id required for {operation} operation")

        if operation in ["create", "update"] and not kwargs.get("user_data"):
            raise ValueError(f"user_data required for {operation} operation")

        # Prepare output for downstream nodes
        return {
            "result": {
                "operation": operation,
                "user_data": kwargs.get("user_data"),
                "user_id": kwargs.get("user_id"),
                "tenant_id": tenant_id,
                "requestor_id": requestor_id,
                "audit_context": kwargs.get("audit_context", {})
            }
        }
```

### Pattern 2: SecureGovernedNode for Enterprise Security

For production deployments, use `SecureGovernedNode` which provides connection parameter validation:

```python
from kailash.nodes.governance import SecureGovernedNode
from pydantic import BaseModel, Field
from typing import Optional, Literal

class UserManagementContract(BaseModel):
    """Pydantic contract for type safety and validation."""
    operation: Literal["create", "update", "delete", "get"]
    user_data: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None
    tenant_id: str
    requestor_id: str

    class Config:
        extra = "forbid"  # Security: reject unknown parameters

class EnterpriseUserNode(SecureGovernedNode):
    """Enterprise-grade user management with security validation."""

    @classmethod
    def get_parameter_contract(cls):
        return UserManagementContract

    @classmethod
    def get_connection_contract(cls):
        """Define connection parameters for security."""
        return None  # Override if receiving connection parameters

    def run_governed(self, **kwargs):
        """Execute with pre-validated parameters."""
        # All parameters are validated against contract
        operation = kwargs["operation"]
        tenant_id = kwargs["tenant_id"]

        # Your secure business logic here
        result = self._process_user_operation(operation, kwargs)

        return {"result": result}
```

**Security Features of SecureGovernedNode**:
- ✅ Validates both workflow AND connection parameters
- ✅ Prevents SQL injection through connection parameters
- ✅ Automatic audit logging of security violations
- ✅ Context-aware SQL injection detection
- ✅ Performance monitoring built-in

### Pattern 3: Parameter Declaration Best Practices

```python
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
workflow.add_connection("processor", "result.data", "consumer", "input_data")
workflow.add_connection("processor", "result.statistics", "analyzer", "stats")
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
workflow.add_connection("data_source", "result.customers", "processor", "customer_list")
workflow.add_connection("data_source", "result.summary.average_score", "validator", "baseline_score")
workflow.add_connection("data_source", "result.metadata", "logger", "meta_info")
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
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

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
workflow.add_connection("processor", "result.data", "validator", "input_data")
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

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

## Enterprise Anti-Patterns (What NOT to Do)

### Anti-Pattern 1: Empty Parameter Declaration

```python
# ❌ WRONG - No parameters declared (SECURITY RISK)
class BadEntryNode(Node):
    def get_parameters(self):
        return {}  # SDK will inject nothing!

    def run(self, **kwargs):
        # kwargs will always be empty!
        operation = kwargs.get('operation')  # Always None
        # This is a SECURITY FEATURE, not a bug

# ✅ CORRECT - Explicit parameter declaration
class GoodEntryNode(Node):
    def get_parameters(self):
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation to perform"
            ),
            "data": NodeParameter(
                name="data",
                type=dict,
                required=True,
                description="Input data"
            )
        }
```

### Anti-Pattern 2: Attempting Dynamic Parameter Injection

```python
# ❌ WRONG - Trying to bypass security
class DynamicParameterNode(Node):
    def get_parameters(self):
        # These patterns DO NOT WORK (by design)
        return {
            "*": NodeParameter(accept_all=True),  # Not supported!
            "**kwargs": NodeParameter(type=dict),  # Not supported!
            "dynamic": NodeParameter(dynamic=True) # Not supported!
        }

# ✅ CORRECT - Define all expected parameters
class ExplicitParameterNode(Node):
    def get_parameters(self):
        return {
            "user_data": NodeParameter(type=dict, required=False),
            "config": NodeParameter(type=dict, required=False),
            "options": NodeParameter(type=dict, required=False)
        }
```

### Anti-Pattern 3: Using PythonCodeNode for Complex Business Logic

```python
# ❌ WRONG - Complex logic in string code
workflow.add_node("PythonCodeNode", "business_logic", {
    "code": """
# 100+ lines of business logic in a string
# Hard to test, debug, maintain
# Security risk with string execution
# No IDE support, no type checking
"""
})

# ✅ CORRECT - Create a proper custom node
class BusinessLogicNode(SecureGovernedNode):
    """Properly implemented business logic with security."""

    @classmethod
    def get_parameter_contract(cls):
        return BusinessLogicContract

    def run_governed(self, **kwargs):
        # Testable, maintainable, secure code
        return self._process_business_logic(kwargs)
```

## Common Pitfalls and Solutions

### 1. Missing Parameter Declaration

```python
# ❌ WRONG - Parameter not declared
class MyNode(Node):
    def get_parameters(self):
        return {
            "input": NodeParameter(name="input", type=str, required=True)
            # Missing "config" parameter!
        }

    def run(self, **kwargs):
        input_data = kwargs.get("input")
        config = kwargs.get("config", {})  # Will always be {} - not declared!

# ✅ CORRECT - Declare all parameters
class MyNode(Node):
    def get_parameters(self):
        return {
            "input": NodeParameter(name="input", type=str, required=True),
            "config": NodeParameter(name="config", type=dict, required=False, default={})
        }
```

### 2. Wrong Connection Syntax

```python
# ❌ WRONG - Using old/incorrect parameter names
# workflow.add_connection("source", "result", "target", "input")  # Fixed mapping pattern
# workflow.add_connection("source", "result", "target", "input")  # Fixed output mapping

# ✅ CORRECT - Current syntax
workflow.add_connection("a", "result", "b", "data")
workflow.add_connection("a", "b", "result", "data")
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
workflow.add_connection("problematic_node", "result", "inspector", "debug_input")
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

## Security Best Practices

### Context-Aware SQL Injection Prevention

The SDK implements sophisticated context-aware validation to balance security with user experience:

```python
# User content fields - NO SQL scanning (allows O'Brien, user--admin)
user_fields = {
    'username', 'first_name', 'last_name', 'email', 'display_name',
    'user_id', 'requestor_id', 'created_by', 'updated_by'
}

# SQL construction fields - ALWAYS scan for injection
sql_fields = {
    'query', 'sql', 'where', 'filter', 'order_by', 'group_by',
    'where_clause', 'filter_condition', 'select', 'from', 'join'
}
```

**Example Validation**:
```python
# ✅ ALLOWED: User content
{"username": "O'Brien"}           # Apostrophe OK in user fields
{"first_name": "user--admin"}     # Dashes OK in user fields

# 🚨 BLOCKED: SQL construction
{"query": "'; DROP TABLE users;"}     # SQL injection blocked
{"where": "1=1 OR admin='true'"}      # Logic bombs blocked
```

### Connection Parameter Security

Always validate connection parameters to prevent injection attacks:

```python
class SecureDatabaseNode(SecureGovernedNode):
    """Database node with connection parameter validation."""

    @classmethod
    def get_connection_contract(cls):
        """Define connection parameters for security."""
        class DatabaseConnectionContract(BaseModel):
            params: List[Any] = Field(description="SQL parameters")
            query: Optional[str] = Field(default=None)

            @field_validator('params')
            @classmethod
            def validate_params_list(cls, v):
                if not isinstance(v, list):
                    raise ValueError("params must be a list for SQL safety")
                return v

        return DatabaseConnectionContract
```

### Audit Trail Implementation

```python
class AuditedNode(SecureGovernedNode):
    """Node with comprehensive audit logging."""

    def execute(self, **kwargs):
        # Log parameter access for compliance
        self.audit_logger.log_parameter_access(
            node_class=self.__class__.__name__,
            parameters=self._sanitize_for_logging(kwargs),
            sensitivity=self._classify_parameters(kwargs),
            user_context=kwargs.get('requestor_id', 'unknown')
        )

        return super().execute(**kwargs)
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
workflow.add_connection("source", "result", "result.customers", "input")
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
workflow.add_connection("producer", "result", "consumer", "input")

# Also works with deeper nesting
workflow.add_connection("producer", "result", "consumer", "input")

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
        data_parameters= kwargs.get("data_inputs", {})
        config_parameters= kwargs.get("config_inputs", {})
        other_parameters= kwargs.get("other_inputs", {})

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
workflow.add_connection("source1", "merger", "result", "data_source1")  # Matches data_*
workflow.add_connection("source2", "merger", "result", "data_source2")  # Matches data_*
workflow.add_connection("db_config", "merger", "result", "config_db")   # Matches config_*

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
workflow.add_connection("analytics", "result", "reporter", "input")

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

## Enterprise Summary

### Key Principles

1. **Security by Design**: Explicit parameter declaration prevents injection attacks
2. **Type Safety**: Strong typing with validation contracts
3. **Audit Compliance**: Complete parameter access logging
4. **Performance**: <2ms validation overhead per node
5. **User Experience**: Context-aware validation (no false positives on names like O'Brien)

### Industry Alignment

This approach aligns with enterprise standards used by:
- **AWS**: CloudFormation parameter schemas
- **Google**: Cloud Deployment Manager configs
- **Microsoft**: Azure Resource Manager templates
- **Salesforce**: Apex parameter validation

### Migration Path

For existing projects:
1. Audit nodes with empty `get_parameters()`
2. Define parameter contracts using patterns above
3. Migrate to `SecureGovernedNode` for production
4. Enable connection parameter validation
5. Implement audit logging

## Related Guides

**Prerequisites:**
- [Fundamentals](01-fundamentals.md) - Core concepts
- [Workflows](02-workflows.md) - Workflow basics

**Advanced Topics:**
- [Custom Development](05-custom-development.md) - Creating custom nodes with security
- [SecureGovernedNode Guide](../7-gold-standards/enterprise-parameter-passing-gold-standard.md) - Complete security patterns
- [Troubleshooting](../2-core-concepts/validation/common-mistakes.md) - Common parameter issues

**Enterprise Patterns:**
- [Security Patterns](../5-enterprise/security-patterns.md) - Comprehensive security guide
- [Compliance Patterns](../5-enterprise/compliance-patterns.md) - Audit and compliance

---

**Master enterprise-grade parameter passing with security, validation, and compliance built-in!**
