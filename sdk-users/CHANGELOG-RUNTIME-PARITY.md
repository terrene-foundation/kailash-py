# Runtime Parity Changelog

## v0.9.31+ (Latest)

### Return Structure Unification

**AsyncLocalRuntime now returns tuple `(results, run_id)`** matching LocalRuntime for complete parity.

**Before**:
```python
# AsyncLocalRuntime (OLD - inconsistent)
result = await runtime.execute_workflow_async(workflow, inputs)
# Returned nested dict with metadata
```

**After**:
```python
# AsyncLocalRuntime (NEW - consistent)
results, run_id = await runtime.execute_workflow_async(workflow, inputs)
# Returns same tuple structure as LocalRuntime
```

**Migration**: Update code to use tuple unpacking instead of accessing nested dict.

---

# Runtime Parity Improvements (v0.9.31)

**What Changed**: AsyncLocalRuntime and LocalRuntime now return identical structures, ensuring consistent developer experience across sync and async execution.

## Return Structure Unification

### Before (Inconsistent)

**LocalRuntime:**
```python
from kailash.runtime import LocalRuntime

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters=inputs)
# Returns: (Dict[str, Any], str)
```

**AsyncLocalRuntime (OLD):**
```python
from kailash.runtime import AsyncLocalRuntime

runtime = AsyncLocalRuntime()
result = await runtime.execute_workflow_async(workflow, inputs)
# Returned: Dict[str, Any] with nested structure:
# {
#     "results": {...},
#     "errors": {...},
#     "total_duration": 1.23,
#     "workflow_id": "..."
# }
```

### After (Consistent)

**Both runtimes now return the same structure:**

```python
# LocalRuntime (unchanged)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters=inputs)

# AsyncLocalRuntime (NOW CONSISTENT!)
runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_workflow_async(workflow, inputs)

# Both return: (Dict[str, Any], str)
# - results: Node outputs keyed by node ID
# - run_id: Unique execution identifier
```

## Benefits

1. **Seamless Migration**: Switch between sync and async runtimes without code changes
2. **Consistent Testing**: Same assertions work for both runtimes
3. **Predictable Behavior**: Identical return structures reduce confusion
4. **Easier Debugging**: Same result format regardless of runtime choice

## Parameter Naming

**Note**: Parameter names differ between runtimes due to their different origins:

- **LocalRuntime**: Uses `parameters` keyword
- **AsyncLocalRuntime**: Uses `inputs` keyword

```python
# LocalRuntime
results, run_id = runtime.execute(workflow, parameters={"key": "value"})

# AsyncLocalRuntime
results, run_id = await runtime.execute_workflow_async(workflow, inputs={"key": "value"})
```

**Tip**: Use the shared test helper `execute_runtime()` which automatically normalizes parameter names when testing both runtimes.

## Conditional Execution Support

AsyncLocalRuntime now automatically detects and handles conditional workflows (SwitchNode):

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "condition", {
    "code": "result = {'value': True}"
})
workflow.add_node("SwitchNode", "switch", {
    "condition_path": "condition.result.value"
})
workflow.add_node("PythonCodeNode", "true_branch", {
    "code": "result = {'msg': 'Condition was true'}"
})
workflow.add_node("PythonCodeNode", "false_branch", {
    "code": "result = {'msg': 'Condition was false'}"
})

# Both runtimes handle this identically
results, run_id = await async_runtime.execute_workflow_async(workflow.build(), {})
# Only executes nodes in the true branch, skips false branch
```

## Testing with Both Runtimes

Use the shared test fixtures for parity testing:

```python
import pytest
from tests.shared.runtime.conftest import runtime_class, execute_runtime

def test_my_workflow(runtime_class):
    """Test runs automatically against both LocalRuntime and AsyncLocalRuntime"""
    runtime = runtime_class()
    workflow = create_my_workflow()

    # execute_runtime() handles parameter normalization
    results = execute_runtime(runtime, workflow, parameters={"input": "test"})

    # Same assertions work for both runtimes
    assert results["output"]["result"] == expected_value
```

**Test Fixtures:**
- `runtime_class`: Parametrized fixture that provides both runtime classes
- `runtime_instance`: Creates runtime instance for testing
- `execute_runtime()`: Normalizes parameters and return structures
- `execute_runtime_with_run_id()`: Returns both results and run_id
- `is_async_runtime()`: Check if runtime is async
- `is_sync_runtime()`: Check if runtime is sync

## Migration Guide

If you're using AsyncLocalRuntime, update your code:

**OLD CODE:**
```python
result = await runtime.execute_workflow_async(workflow, inputs)

# Access results
node_output = result["results"]["my_node"]

# Check errors
if result["errors"]:
    print(f"Errors: {result['errors']}")

# Get execution time
duration = result["total_duration"]
```

**NEW CODE:**
```python
results, run_id = await runtime.execute_workflow_async(workflow, inputs)

# Access results (same as LocalRuntime)
node_output = results["my_node"]

# Errors are now raised as exceptions
try:
    results, run_id = await runtime.execute_workflow_async(workflow, inputs)
except Exception as e:
    print(f"Workflow failed: {e}")

# Use timing for execution monitoring
import time
start = time.time()
results, run_id = await runtime.execute_workflow_async(workflow, inputs)
duration = time.time() - start
```

## CI/CD Integration

The codebase now includes automated parity checks:

- **Method Existence Parity**: Verifies both runtimes have the same methods
- **Signature Parity**: Ensures method signatures match where expected
- **Behavior Parity**: Tests that both runtimes produce identical results
- **Coverage Parity**: Monitors test coverage consistency (±5% threshold)
- **Shared Test Suite**: Runs same tests against both runtimes

See `.github/workflows/sync-async-parity.yml` for implementation details.

## Related Documentation

- [Unified Async Runtime Guide](3-development/10-unified-async-runtime-guide.md) - Complete async runtime documentation
- [3-Tier Testing Strategy](.claude/skills/12-testing-strategies/test-3tier-strategy.md) - Testing best practices
- [CLAUDE.md](../CLAUDE.md) - Essential patterns and critical rules

## Upgrade Notes

**Breaking Changes**: None - this is a non-breaking change that improves consistency.

**Recommended Actions**:
1. Update code accessing AsyncLocalRuntime results to use tuple unpacking
2. Replace nested result access (`result["results"]["node"]`) with direct access (`results["node"]`)
3. Update error handling to use try/except instead of checking `result["errors"]`
4. Consider using shared test fixtures for runtime parity testing

## Support

For questions or issues:
- Check the [Unified Async Runtime Guide](3-development/10-unified-async-runtime-guide.md)
- Review [Runtime Parity Tests](../tests/shared/runtime/)
- Open an issue on GitHub
