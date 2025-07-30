# Troubleshooting Conditional Execution

This guide helps diagnose and resolve common issues with the conditional execution feature in Kailash SDK.

## Quick Diagnostics

### 1. Check if Conditional Execution is Enabled

```python
from kailash.runtime.local import LocalRuntime

# Check current mode
runtime = LocalRuntime()
print(f"Conditional execution mode: {runtime.conditional_execution}")
# Output: "route_data" (default) or "skip_branches" (conditional)
```

### 2. Verify Workflow Compatibility

```python
from kailash.runtime.local import LocalRuntime

runtime = LocalRuntime(
    enable_compatibility_reporting=True,
    conditional_execution="skip_branches"
)

results, run_id = runtime.execute(workflow)

# Check compatibility report
report = runtime.get_compatibility_report()
if report:
    print(f"Compatibility: {report.overall_compatibility}")
    for pattern in report.detected_patterns:
        print(f"- {pattern.pattern_type}: {pattern.compatibility}")
```

## Common Issues and Solutions

### Issue 1: Conditional Execution Not Activating

**Symptoms:**
- All nodes execute despite using `conditional_execution="skip_branches"`
- No performance improvement observed

**Possible Causes:**

1. **No SwitchNodes in workflow**
   ```python
   # Check if workflow has switches
   from kailash.analysis import ConditionalBranchAnalyzer

   analyzer = ConditionalBranchAnalyzer(workflow)
   switch_nodes = analyzer._find_switch_nodes()
   print(f"Found {len(switch_nodes)} SwitchNodes")
   ```

2. **Cycles detected (automatic fallback)**
   ```python
   # Cycles force fallback to route_data mode
   if workflow.has_cycles():
       print("Workflow has cycles - conditional execution disabled")
   ```

3. **Unsupported patterns**
   - Complex merge patterns
   - Cross-dependent switches
   - Dynamic workflow modifications

**Solutions:**
- Add SwitchNodes for conditional routing
- Refactor cycles to use exit conditions instead
- Check compatibility report for unsupported patterns

### Issue 2: Downstream Nodes Not Executing

**Symptoms:**
- Nodes after SwitchNodes don't execute
- Missing expected results

**Possible Causes:**

1. **Incorrect connection mapping**
   ```python
   # Wrong: connecting to wrong output port
   workflow.add_connection("switch", "output", "processor", "input")

   # Correct: use specific conditional outputs
   workflow.add_connection("switch", "true_output", "processor", "input")
   workflow.add_connection("switch", "false_output", "alt_processor", "input")
   ```

2. **All conditions evaluate to false**
   ```python
   # Debug switch results
   runtime = LocalRuntime(conditional_execution="skip_branches", debug=True)
   # Check logs for switch evaluation results
   ```

**Solutions:**
- Verify connection port names match SwitchNode outputs
- Add debug logging to check switch conditions
- Ensure switch input data is properly formatted

### Issue 3: Performance Not Improving

**Symptoms:**
- Conditional execution enabled but no speed improvement
- Similar execution times to route_data mode

**Possible Causes:**

1. **Few branches to skip**
   ```python
   # Monitor actual skip rate
   runtime = LocalRuntime(
       conditional_execution="skip_branches",
       enable_performance_monitoring=True
   )

   results, _ = runtime.execute(workflow)
   metrics = runtime.get_execution_metrics()
   print(f"Nodes skipped: {metrics.skipped_nodes}/{metrics.node_count}")
   ```

2. **Graph analysis overhead**
   - Very small workflows (< 10 nodes)
   - Simple linear workflows without branches

3. **Heavy preprocessing in Phase 1**
   - Complex switch dependencies
   - Many switch nodes requiring inputs

**Solutions:**
- Use for workflows with significant branching (>20% skippable)
- Consider route_data mode for small workflows
- Optimize switch conditions for faster evaluation

### Issue 4: Merge Nodes Receiving Partial Inputs

**Symptoms:**
- MergeNode errors with missing inputs
- Incomplete data aggregation

**Possible Causes:**

1. **MergeNode expects all inputs**
   ```python
   # Configure merge node for conditional inputs
   merge_node = MergeNode(
       name="aggregator",
       skip_none=True  # Handle missing inputs gracefully
   )
   ```

2. **Connection configuration**
   ```python
   # Ensure all conditional branches connect to merge
   for branch in ["true_branch", "false_branch", "default_branch"]:
       workflow.add_connection(branch, "result", "merge", branch)
   ```

**Solutions:**
- Enable `skip_none=True` on MergeNodes
- Use IntelligentMergeNode for advanced handling
- Add default values for missing inputs

## Performance Optimization Tips

### 1. Enable Performance Monitoring

```python
runtime = LocalRuntime(
    conditional_execution="skip_branches",
    enable_performance_monitoring=True,
    performance_switch_enabled=True  # Auto-switch modes
)

# Runtime will automatically switch between modes based on performance
```

### 2. Use Execution Plan Caching

```python
# Reuse execution plans for repeated runs
runtime = LocalRuntime(conditional_execution="skip_branches")

# First run creates and caches plan
results1, _ = runtime.execute(workflow, parameters={"threshold": 10})

# Subsequent runs with same switch results use cached plan
results2, _ = runtime.execute(workflow, parameters={"threshold": 10})
```

### 3. Optimize Switch Placement

```python
# Place switches early in workflow to maximize skip potential
workflow = WorkflowBuilder()

# Good: Early switching
workflow.add_node("SwitchNode", "early_switch", {...})
workflow.add_connection("source", "result", "early_switch", "input_data")

# Connect expensive branches
workflow.add_connection("early_switch", "true_output", "expensive_pipeline", "input")
```

## Debug Mode

Enable comprehensive debugging:

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

runtime = LocalRuntime(
    conditional_execution="skip_branches",
    debug=True,
    enable_compatibility_reporting=True,
    enable_performance_monitoring=True
)

results, run_id = runtime.execute(workflow)

# Check all diagnostics
print(f"Execution mode used: {runtime._last_execution_mode}")
print(f"Compatibility report: {runtime.get_compatibility_report()}")
print(f"Performance metrics: {runtime.get_execution_metrics()}")
print(f"Execution analytics: {runtime.get_analytics()}")
```

## Advanced Troubleshooting

### Analyze Execution Plan

```python
from kailash.planning import DynamicExecutionPlanner
from kailash.analysis import ConditionalBranchAnalyzer

# Manually analyze execution plan
analyzer = ConditionalBranchAnalyzer(workflow)
planner = DynamicExecutionPlanner(workflow)

# Simulate switch results
switch_results = {
    "switch1": {"true_output": {"value": True}, "false_output": None},
    "switch2": {"case_A": {"data": "A"}, "case_B": None, "default": None}
}

# Get execution plan
execution_plan = planner.create_execution_plan(switch_results)
print(f"Execution plan: {execution_plan}")

# Validate plan
is_valid, errors = planner.validate_execution_plan(execution_plan)
if not is_valid:
    print(f"Plan validation errors: {errors}")
```

### Force Specific Execution Mode

```python
# Force conditional execution (skip compatibility checks)
runtime = LocalRuntime(
    conditional_execution="skip_branches",
    _force_conditional=True  # Internal flag - use with caution
)

# Force standard execution
runtime = LocalRuntime(
    conditional_execution="route_data"
)
```

## Error Messages Reference

| Error Message | Cause | Solution |
|--------------|-------|----------|
| "Conditional execution prerequisites not met" | Workflow incompatible | Check compatibility report |
| "Invalid switch results detected" | Switch execution failed | Debug switch nodes |
| "Falling back to standard execution" | Runtime error in conditional mode | Check logs for specific error |
| "No SwitchNodes found in workflow" | Missing conditional logic | Add SwitchNodes |
| "Circular dependency detected in switch hierarchy" | Complex switch dependencies | Refactor switch relationships |

## Getting Help

1. **Enable debug logging** to see detailed execution flow
2. **Check compatibility report** for unsupported patterns
3. **Monitor performance metrics** to verify improvements
4. **Use execution analytics** to understand behavior
5. **Review examples** in the [conditional execution guide](../2-core-concepts/conditional-execution-guide.md)

For additional support, please refer to the [Kailash SDK documentation](../../README.md) or file an issue with your workflow structure and debug logs.
