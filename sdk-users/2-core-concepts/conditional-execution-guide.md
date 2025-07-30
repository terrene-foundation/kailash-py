# Conditional Execution Guide

## Overview

Conditional execution in Kailash SDK allows workflows to skip unreachable branches entirely, providing significant performance improvements over traditional data routing approaches. Instead of executing all nodes and routing `None` values, conditional execution analyzes your workflow and only executes nodes that are actually reachable based on SwitchNode results.


## Key Benefits

- **20-50% Performance Improvement**: Skip unnecessary node execution
- **Industry-Standard Behavior**: True if/else conditional execution
- **Backward Compatible**: Opt-in feature, existing workflows unchanged
- **Production Ready**: Comprehensive error handling and monitoring

## Quick Start

### Basic Conditional Execution

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.logic.operations import SwitchNode
from kailash.nodes.code.python import PythonCodeNode

# Create workflow with conditional logic
workflow = WorkflowBuilder()

# Add data source
workflow.add_node("PythonCodeNode", "data_source", {
    "code": "result = {'user_type': 'premium', 'status': 'active'}"
})

# Add conditional switch
workflow.add_node("SwitchNode", "user_type_switch", {
    "condition_field": "user_type",
    "operator": "==",
    "value": "premium"
})

# Add conditional processors
workflow.add_node("PythonCodeNode", "premium_processor", {
    "code": "result = {'discount': 30, 'features': ['all'], 'priority': 'high'}"
})

workflow.add_node("PythonCodeNode", "basic_processor", {
    "code": "result = {'discount': 5, 'features': ['basic'], 'priority': 'normal'}"
})

# Connect workflow
workflow.add_connection("data_source", "result", "user_type_switch", "input_data")
workflow.add_connection("user_type_switch", "true_output", "premium_processor", "input")
workflow.add_connection("user_type_switch", "false_output", "basic_processor", "input")

# Execute with conditional execution (skip unreachable branches)
runtime = LocalRuntime(conditional_execution="skip_branches")
results, run_id = runtime.execute(workflow.build())

print(f"Executed nodes: {list(results.keys())}")
# Output: ['data_source', 'user_type_switch', 'premium_processor']
# Note: basic_processor was skipped entirely!
```

### Performance Comparison

```python
import time
from kailash.runtime.local import LocalRuntime

# Same workflow as above

# Traditional approach (executes all nodes)
runtime_traditional = LocalRuntime(conditional_execution="route_data")
start_time = time.time()
results_traditional, _ = runtime_traditional.execute(workflow.build())
traditional_time = time.time() - start_time

# Conditional execution approach (skips unreachable nodes)
runtime_conditional = LocalRuntime(conditional_execution="skip_branches")
start_time = time.time()
results_conditional, _ = runtime_conditional.execute(workflow.build())
conditional_time = time.time() - start_time

# Performance improvement
improvement = (traditional_time - conditional_time) / traditional_time * 100
print(f"Performance improvement: {improvement:.1f}%")
print(f"Traditional: {len(results_traditional)} nodes executed")
print(f"Conditional: {len(results_conditional)} nodes executed")
```

## Configuration Options

### Conditional Execution Modes

```python
from kailash.runtime.local import LocalRuntime

# Default mode: Traditional data routing (backward compatible)
runtime_default = LocalRuntime()  # same as conditional_execution="route_data"

# Explicit traditional mode
runtime_traditional = LocalRuntime(conditional_execution="route_data")

# New conditional execution mode
runtime_conditional = LocalRuntime(conditional_execution="skip_branches")
```

| Mode | Behavior | Performance | Use Case |
|------|----------|-------------|----------|
| `route_data` | Execute all nodes, route `None` for skipped branches | Baseline | Existing workflows, debugging |
| `skip_branches` | Skip unreachable branches entirely | 20-50% faster | New workflows, production optimization |

## Advanced Patterns

### Hierarchical Switch Execution (NEW in v0.9.0)

When workflows contain multiple interdependent switches, the SDK now automatically optimizes their execution using hierarchical layers:

**Key Benefits**:
- **Parallel execution** within layers
- **Dependency-aware** execution order
- **Automatic optimization** for 2+ dependent switches
- **15-30% performance gain** for complex conditionals

**How it Works**:
1. Analyzes switch dependencies
2. Groups switches into execution layers
3. Executes each layer in parallel
4. Respects dependencies between layers

**Example**:
```python
# Automatically uses hierarchical execution when beneficial
runtime = LocalRuntime(conditional_execution="skip_branches", debug=True)

# Debug output shows hierarchical execution:
# DEBUG: Detected 3 execution layers in switch hierarchy
# INFO: Using hierarchical switch execution for optimized performance
# DEBUG: Hierarchical execution summary: {
#   'execution_layers': [['user_type'], ['region', 'feature'], ['limit']],
#   'max_depth': 3
# }
```

### Multiple SwitchNodes (Hierarchical)

```python
# Create hierarchical conditional workflow
workflow = WorkflowBuilder()

workflow.add_node("DataSourceNode", "data_source", {
    "data": {"user_type": "premium", "region": "US", "status": "active"}
})

# First level: User type check
workflow.add_node("SwitchNode", "type_switch", {
    "condition_field": "user_type",
    "operator": "==",
    "value": "premium"
})

# Second level: Region check (only for premium users)
workflow.add_node("SwitchNode", "region_switch", {
    "condition_field": "region",
    "operator": "==",
    "value": "US"
})

# Third level: Status check (only for US premium users)
workflow.add_node("SwitchNode", "status_switch", {
    "condition_field": "status",
    "operator": "==",
    "value": "active"
})

# Final processors
workflow.add_node("PythonCodeNode", "us_premium_active", {
    "code": "result = {'discount': 30, 'priority': 'highest'}"
})

workflow.add_node("PythonCodeNode", "us_premium_inactive", {
    "code": "result = {'discount': 20, 'priority': 'high'}"
})

workflow.add_node("PythonCodeNode", "intl_premium", {
    "code": "result = {'discount': 15, 'priority': 'high'}"
})

workflow.add_node("PythonCodeNode", "basic_user", {
    "code": "result = {'discount': 5, 'priority': 'normal'}"
})

# Connect hierarchical structure
workflow.add_connection("data_source", "result", "type_switch", "input_data")

# Premium path
workflow.add_connection("type_switch", "true_output", "region_switch", "input_data")
workflow.add_connection("type_switch", "false_output", "basic_user", "input")

# US premium path
workflow.add_connection("region_switch", "true_output", "status_switch", "input_data")
workflow.add_connection("region_switch", "false_output", "intl_premium", "input")

# Final destinations
workflow.add_connection("status_switch", "true_output", "us_premium_active", "input")
workflow.add_connection("status_switch", "false_output", "us_premium_inactive", "input")

# Execute with conditional execution
runtime = LocalRuntime(conditional_execution="skip_branches")
results, run_id = runtime.execute(workflow.build())

# For user_type=premium, region=US, status=active:
# Only executes: data_source → type_switch → region_switch → status_switch → us_premium_active
# Skips: us_premium_inactive, intl_premium, basic_user (significant performance gain!)
```

### Merge Nodes with Conditional Inputs

```python
from kailash.nodes.logic.operations import MergeNode

workflow = WorkflowBuilder()

# Data source with multiple flags
workflow.add_node("DataSourceNode", "data_source", {
    "data": {"process_a": True, "process_b": False, "process_c": True}
})

# Multiple conditional branches
for branch in ["a", "b", "c"]:
    workflow.add_node("SwitchNode", f"switch_{branch}", {
        "condition_field": f"process_{branch}",
        "operator": "==",
        "value": True
    })

    workflow.add_node("PythonCodeNode", f"processor_{branch}", {
        "code": f"result = {{'data_{branch}': 'processed_{branch}', 'value_{branch}': {ord(branch) * 100}}}"
    })

    # Connect each branch
    workflow.add_connection("data_source", "result", f"switch_{branch}", "input_data")
    workflow.add_connection(f"switch_{branch}", "true_output", f"processor_{branch}", "input")

# Intelligent merge node (handles partial inputs)
workflow.add_node("MergeNode", "merge_results", {
    "merge_type": "merge_dict",
    "skip_none": True  # Skip None inputs from conditional branches
})

# Connect all processors to merge
for branch in ["a", "b", "c"]:
    workflow.add_connection(f"processor_{branch}", "result", "merge_results", f"data{ord(branch) - ord('a') + 1}")

# Final processor
workflow.add_node("PythonCodeNode", "final_processor", {
    "code": """
total_value = 0
processed_branches = []

for key, value in merged_data.items():
    if 'value_' in str(value):
        for k, v in value.items():
            if k.startswith('value_'):
                total_value += v
                processed_branches.append(k.split('_')[1])

result = {
    'total_value': total_value,
    'processed_branches': processed_branches,
    'branch_count': len(processed_branches)
}
"""
})

workflow.add_connection("merge_results", "merged_data", "final_processor", "merged_data")

runtime = LocalRuntime(conditional_execution="skip_branches")
results, run_id = runtime.execute(workflow.build())

# With process_a=True, process_b=False, process_c=True:
# Only processor_a and processor_c execute
# processor_b is skipped entirely
# MergeNode intelligently handles partial inputs
```

## Performance Optimization

### Large Workflows

```python
# For workflows with many conditional branches
workflow = WorkflowBuilder()

# Data source
workflow.add_node("DataSourceNode", "data_source", {
    "data": {"feature_flags": ["feature_1", "feature_3", "feature_7"], "user_id": "12345"}
})

# Create 10 feature processors, but only 3 will execute
for i in range(10):
    feature_name = f"feature_{i}"

    workflow.add_node("SwitchNode", f"feature_{i}_switch", {
        "condition_field": "feature_flags",
        "operator": "contains",
        "value": feature_name
    })

    workflow.add_node("PythonCodeNode", f"feature_{i}_processor", {
        "code": f"result = {{'feature': '{feature_name}', 'processed': True, 'value': {i * 10}}}"
    })

    workflow.add_connection("data_source", "result", f"feature_{i}_switch", "input_data")
    workflow.add_connection(f"feature_{i}_switch", "true_output", f"feature_{i}_processor", "input")

runtime = LocalRuntime(conditional_execution="skip_branches")
results, run_id = runtime.execute(workflow.build())

# Performance: ~70% reduction in executed nodes
# Only features 1, 3, and 7 execute, others are skipped entirely
```

### Monitoring and Analytics

```python
# Get detailed execution analytics
runtime = LocalRuntime(conditional_execution="skip_branches")
results, run_id = runtime.execute(workflow.build())

# Access execution analytics
analytics = runtime.get_execution_analytics()

print(f"Total conditional executions: {analytics['conditional_execution_stats']['total_executions']}")
print(f"Average performance improvement: {analytics['conditional_execution_stats']['average_performance_improvement']:.2%}")
print(f"Execution patterns: {len(analytics['execution_patterns'])}")

# Health diagnostics
diagnostics = runtime.get_health_diagnostics()
print(f"Runtime health: {diagnostics['runtime_health']}")
print(f"Cache hit rate: {diagnostics['cache_statistics']['hit_rate']:.2%}")
```

## Best Practices

### 1. Design for Conditional Execution

```python
# ✅ GOOD: Clear conditional structure
workflow.add_node("SwitchNode", "user_check", {
    "condition_field": "user_type",
    "operator": "==",
    "value": "premium"
})

# ❌ AVOID: Complex conditions that are hard to analyze
workflow.add_node("PythonCodeNode", "complex_logic", {
    "code": "result = complex_function(input) if check_condition(input) else None"
})
```

### 2. Use Appropriate Operators

```python
# Supported operators for optimal conditional execution:
operators = [
    "==", "!=",           # Equality
    "<", "<=", ">", ">=", # Comparison
    "contains", "in",     # Membership
    "is_null", "is_not_null"  # Null checks
]
# Note: startswith, endswith, and matches are not yet implemented
```

### 3. Structure Hierarchical Logic

```python
# ✅ GOOD: Clear hierarchy
data_source → type_switch → region_switch → final_processor

# ❌ AVOID: Complex cross-dependencies
switch_a ↔ switch_b ↔ switch_c (circular dependencies)
```

### 4. Monitor Performance

```python
# Regularly check performance impact
runtime = LocalRuntime(conditional_execution="skip_branches", enable_monitoring=True)

# Set up performance gates
if analytics['conditional_execution_stats']['average_performance_improvement'] < 0.15:
    print("Warning: Conditional execution providing < 15% improvement")
```

## Troubleshooting

### Common Issues

#### 1. No Performance Improvement

**Symptoms**: Conditional execution enabled but no performance gain

**Causes & Solutions**:
```python
# Cause: Workflow has no conditional logic
# Solution: Add SwitchNodes for conditional branches

# Cause: All branches always execute
# Solution: Check your data and conditions
runtime = LocalRuntime(conditional_execution="skip_branches", debug=True)
results, run_id = runtime.execute(workflow.build())
# Check debug logs for execution decisions
```

#### 2. Unexpected Results

**Symptoms**: Different results between modes

**Causes & Solutions**:
```python
# Cause: Logic depends on None values from skipped branches
# Solution: Use explicit conditional logic instead

# ❌ PROBLEMATIC: Depends on None propagation
workflow.add_node("PythonCodeNode", "depends_on_none", {
    "code": "result = 'default' if input is None else input['value']"
})

# ✅ BETTER: Use explicit conditional routing
workflow.add_node("SwitchNode", "explicit_check", {
    "condition_field": "should_process",
    "operator": "==",
    "value": True
})
```

#### 3. Complex Patterns Not Supported

**Symptoms**: Fallback to traditional execution

**Solutions**:
```python
# Check for unsupported patterns
try:
    results, run_id = runtime.execute(workflow.build())
    # Check if conditional execution was used
    analytics = runtime.get_execution_analytics()
    if analytics['conditional_execution_stats']['fallback_rate'] > 0:
        print("Some executions fell back to traditional mode")
except Exception as e:
    if "cycle" in str(e).lower():
        print("Cyclic workflows may need special handling")
```

## Migration from Traditional Execution

### Step 1: Baseline Performance

```python
# Measure current performance
runtime_traditional = LocalRuntime(conditional_execution="route_data")
start_time = time.time()
results_baseline, _ = runtime_traditional.execute(workflow.build())
baseline_time = time.time() - start_time
baseline_nodes = len(results_baseline)
```

### Step 2: Enable Conditional Execution

```python
# Test with conditional execution
runtime_conditional = LocalRuntime(conditional_execution="skip_branches")
start_time = time.time()
results_conditional, _ = runtime_conditional.execute(workflow.build())
conditional_time = time.time() - start_time
conditional_nodes = len(results_conditional)
```

### Step 3: Validate Results

```python
# Ensure results are equivalent for your use case
def validate_results(baseline, conditional):
    # Implement your business logic validation
    # Focus on final outputs, not intermediate None values
    return baseline['final_result'] == conditional['final_result']

assert validate_results(results_baseline, results_conditional)
```

### Step 4: Measure Improvement

```python
improvement = (baseline_time - conditional_time) / baseline_time * 100
node_reduction = (baseline_nodes - conditional_nodes) / baseline_nodes * 100

print(f"Time improvement: {improvement:.1f}%")
print(f"Node reduction: {node_reduction:.1f}%")

# Target: 20-50% improvement for conditional workflows
if improvement >= 20:
    print("✅ Significant improvement - deploy conditional execution")
else:
    print("⚠️ Limited improvement - review workflow structure")
```

## API Reference

### LocalRuntime Configuration

```python
LocalRuntime(
    conditional_execution: str = "route_data",  # "route_data" | "skip_branches"
    debug: bool = False,                        # Enable debug logging
    enable_monitoring: bool = True,             # Enable performance monitoring
    # ... other parameters
)
```

### Analytics Methods

```python
# Get execution analytics
analytics = runtime.get_execution_analytics()

# Get health diagnostics
diagnostics = runtime.get_health_diagnostics()

# Optimize runtime performance
optimization = runtime.optimize_runtime_performance()
```

### SwitchNode Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `==` | Equality | `value == "premium"` |
| `!=` | Inequality | `status != "inactive"` |
| `<`, `<=`, `>`, `>=` | Comparison | `score >= 85` |
| `contains` | List/string contains | `features contains "api_access"` |
| `in` | Value in list | `region in ["US", "CA"]` |
| `is_null` | Check if None | `value is_null` |
| `is_not_null` | Check if not None | `value is_not_null` |

## Related Guides

- [Workflow Builder Guide](../workflows/workflow-builder-guide.md) - Creating conditional workflows
- [Performance Optimization](../../3-development/performance-optimization.md) - General performance tips
- [Node Selection Guide](../nodes/node-selection-guide.md) - Choosing the right nodes
- [Error Handling](../../3-development/error-handling.md) - Handling execution errors
