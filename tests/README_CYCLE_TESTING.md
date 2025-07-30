# Cycle Testing Classification Guide

This document explains how to properly classify cycle-related tests according to the Kailash SDK 3-tier testing strategy.

## Test Classification Overview

### Tier 1: Unit Tests (tests/unit/)
**Target**: <1 second per test, NO I/O, NO external dependencies

**What to test**:
- ✅ Cycle detection algorithms (`workflow.has_cycles()`)
- ✅ Edge separation logic (`separate_dag_and_cycle_edges()`)
- ✅ Execution order calculation (`get_execution_order()`)
- ✅ Mathematical iteration logic (termination conditions)
- ✅ Data mapping algorithms (cycle connection mappings)
- ✅ Switch node condition evaluation logic

**Example**: `tests/unit/runtime/test_cycle_determinism.py`
```python
def test_cycle_detection_deterministic(self):
    """Test cycle detection without full execution."""
    workflow = create_workflow_with_cycle()

    # Test multiple calls return consistent results
    results = [workflow.has_cycles() for _ in range(5)]
    assert all(r == results[0] for r in results)
```

### Tier 2: Integration Tests (tests/integration/)
**Target**: <5 seconds per test, real infrastructure, NO MOCKING

**What to test**:
- ✅ LocalRuntime + CyclicWorkflowExecutor interaction
- ✅ Full cycle execution pipeline
- ✅ Node execution within cycles
- ✅ Task tracking with cycles (if using real TaskManager)
- ✅ Multi-component cycle behaviors

**Example**: `tests/integration/runtime/test_cycle_determinism_integration.py`
```python
@pytest.mark.integration
@pytest.mark.timeout(5)
def test_simple_cycle_deterministic_execution(self):
    """Test full cycle execution pipeline."""
    workflow = create_cyclic_workflow()
    runtime = LocalRuntime(enable_cycles=True, enable_monitoring=False)

    # Execute multiple times to verify determinism
    results = []
    for _ in range(3):
        result, _ = runtime.execute(workflow, task_manager=None)
        results.append(result)

    # Verify deterministic behavior
    assert all_results_identical(results)
```

### Tier 3: End-to-End Tests (tests/e2e/)
**Target**: <10 seconds per test, complete infrastructure, NO MOCKING

**What to test**:
- ✅ Complete user workflows with cycles
- ✅ Cycles with real database operations
- ✅ Cycles with file I/O and external services
- ✅ Full TaskManager integration with persistence
- ✅ Monitoring and metrics collection during cycles

**Example**: `tests/e2e/workflows/test_cyclic_data_processing.py`
```python
@pytest.mark.e2e
@pytest.mark.timeout(10)
def test_complete_cyclic_data_pipeline(self):
    """Test complete data processing pipeline with cycles."""
    # Uses real database, files, and full infrastructure
    workflow = build_data_processing_workflow_with_cycles()
    runtime = LocalRuntime()  # Full enterprise features

    result, run_id = runtime.execute(workflow)
    verify_database_state(run_id)
    verify_output_files(run_id)
```

## Common Classification Mistakes

### ❌ Wrong: Unit tests that use LocalRuntime
```python
# This is actually an integration test, not a unit test
def test_cycle_execution(self):
    runtime = LocalRuntime()  # Full runtime = integration test
    result = runtime.execute(workflow)
```

### ✅ Correct: Unit tests that test algorithms directly
```python
# This is a proper unit test
def test_cycle_detection_algorithm(self):
    workflow = WorkflowBuilder().build()
    # Test just the algorithm, not the full execution
    assert workflow.has_cycles() == expected_result
```

### ❌ Wrong: Integration tests with mocking
```python
# NO MOCKING allowed in integration tests
@pytest.mark.integration
@patch('database.connect')  # ❌ FORBIDDEN
def test_cycle_with_database(mock_db):
    pass
```

### ✅ Correct: Integration tests with real components
```python
# Use real components, no mocking
@pytest.mark.integration
def test_cycle_with_real_runtime(self):
    runtime = LocalRuntime(enable_monitoring=False)  # Real runtime
    # Use task_manager=None to avoid I/O in tests
    result = runtime.execute(workflow, task_manager=None)
```

## Performance Guidelines

### Unit Tests Must Be Fast
- **Target**: <1 second total for all unit tests in a file
- **Disable monitoring**: `enable_monitoring=False`
- **No task tracking**: `task_manager=None`
- **No print statements**: Avoid I/O during test execution
- **Test algorithms**: Not full execution pipelines

### Integration Tests Can Be Slower
- **Target**: <5 seconds per test
- **Real components**: LocalRuntime, CyclicWorkflowExecutor
- **Minimal infrastructure**: Only what's needed for component interaction
- **No external services**: Unless testing specific integrations

### E2E Tests Can Be Slowest
- **Target**: <10 seconds per test
- **Full infrastructure**: All services from `tests/utils/test-env`
- **Complete workflows**: End-to-end user scenarios
- **Real persistence**: Files, databases, monitoring

## Test Environment Setup

### Unit Tests: No Setup Required
```python
# Unit tests run independently
class TestCycleUnit:
    def test_algorithm(self):
        # No setup needed
        pass
```

### Integration Tests: Minimal Setup
```python
# May need basic setup, but avoid heavy infrastructure
class TestCycleIntegration:
    def setup_method(self):
        # Minimal setup only
        pass
```

### E2E Tests: Full Infrastructure
```bash
# Must run before E2E tests
./tests/utils/test-env up
./tests/utils/test-env status
```

## Example Test Structure

```
tests/
├── unit/
│   └── runtime/
│       └── test_cycle_determinism.py          # <1s, algorithms only
├── integration/
│   └── runtime/
│       └── test_cycle_determinism_integration.py  # <5s, runtime + executor
└── e2e/
    └── workflows/
        └── test_cyclic_data_processing.py     # <10s, complete scenarios
```

## Debugging Hanging Tests

If tests hang or timeout:

1. **Check Test Classification**: Are you using full execution in a unit test?
2. **Disable Monitoring**: Use `enable_monitoring=False`
3. **Disable Task Tracking**: Use `task_manager=None`
4. **Remove Print Statements**: Avoid I/O during execution
5. **Check Async Handling**: Ensure proper event loop cleanup
6. **Move to Higher Tier**: Complex execution may belong in integration/e2e

## Summary

- **Unit Tests**: Test algorithms and data structures in isolation
- **Integration Tests**: Test component interactions with real runtime
- **E2E Tests**: Test complete user workflows with full infrastructure
- **No Mocking**: Allowed only in Tier 1 (Unit) tests
- **Performance**: <1s unit, <5s integration, <10s e2e
- **Classification**: Based on what you're testing, not how fast it runs
