# Cycle API Migration Report - Integration Tests

## Summary

Found 6 integration test files using the deprecated `workflow.connect()` with `cycle=True` pattern. These should be migrated to the new CycleBuilder API or marked as backward compatibility tests.

## Files to Update

### 1. `/tests/integration/workflows/test_cyclic_workflows.py`
- **Usage Count**: 12 instances of `workflow.connect(..., cycle=True)`
- **Purpose**: Tests basic cyclic workflow functionality
- **Recommendation**: KEEP for backward compatibility testing, as it validates the old API still works

### 2. `/tests/integration/workflows/test_cyclic_examples.py`
- **Usage Count**: 9 instances of `workflow.connect(..., cycle=True)`
- **Purpose**: Tests cyclic workflow execution patterns
- **Recommendation**: MIGRATE to CycleBuilder API to demonstrate modern patterns

### 3. `/tests/integration/workflows/test_core_cycle_execution.py`
- **Usage Count**: 11 instances of `workflow.connect(..., cycle=True)`
- **Purpose**: Tests core cycle execution functionality
- **Recommendation**: MIGRATE to CycleBuilder API as these are core functionality tests

### 4. `/tests/integration/workflows/test_convergence_safety.py`
- **Usage Count**: 9 instances of `workflow.connect(..., cycle=True)`
- **Purpose**: Tests convergence and safety framework
- **Recommendation**: MIGRATE to CycleBuilder API to test safety with modern API

### 5. `/tests/integration/workflows/test_convergence_basic.py`
- **Usage Count**: 7 instances of `workflow.connect(..., cycle=True)`
- **Purpose**: Tests basic convergence functionality
- **Recommendation**: MIGRATE to CycleBuilder API for consistency

### 6. `/tests/integration/workflows/test_cycle_core.py`
- **Usage Count**: 8 instances of `workflow.connect(..., cycle=True)`
- **Purpose**: Core integration tests for cyclic workflows
- **Note**: This file already has 1 test using the new CycleBuilder API (`test_simple_self_cycle`)
- **Recommendation**: MIGRATE remaining tests to CycleBuilder API

## Migration Pattern

### Old API:
```python
workflow.connect(
    "source_node",
    "target_node",
    mapping={"result.field": "input_field"},
    cycle=True,
    max_iterations=10,
    convergence_check="condition",
    cycle_id="my_cycle"
)
```

### New CycleBuilder API:
```python
workflow.create_cycle("my_cycle") \
    .connect("source_node", "target_node", {"result.field": "input_field"}) \
    .max_iterations(10) \
    .converge_when("condition") \
    .build()
```

## Backward Compatibility Strategy

1. **Keep one test file** (`test_cyclic_workflows.py`) using the old API to ensure backward compatibility
2. **Migrate all other files** to use the new CycleBuilder API
3. **Add comments** in backward compatibility tests explaining why they use the old API

## Additional Notes

- The new CycleBuilder API provides better IDE support and method chaining
- It's more discoverable and type-safe
- Additional features available: `.timeout()`, `.memory_limit()`, `.when()`, `.nested_in()`
- The old API still works through the same underlying `workflow.connect()` method

## Next Steps

1. Decide which files to keep for backward compatibility testing
2. Create migration scripts to update the selected files
3. Run tests after migration to ensure functionality is preserved
