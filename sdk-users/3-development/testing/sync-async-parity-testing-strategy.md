# Sync/Async Parity Testing Strategy

**Version**: v1.0.0
**Created**: 2025-10-25
**Status**: MANDATORY - MUST be enforced in CI/CD

---

## Executive Summary

This document defines a comprehensive testing strategy that **ENFORCES** sync/async parity between `LocalRuntime` and `AsyncLocalRuntime` (and any future sync/async pairs). The strategy makes it **IMPOSSIBLE** for implementations to diverge without CI/CD catching it immediately.

### The Problem

**93% Feature Gap Discovered**: `LocalRuntime` has 16 test files for conditional execution, while `AsyncLocalRuntime` has 0. This represents a critical gap in feature parity that was not caught by existing testing.

**Root Cause**: No shared test suite, no parity validation, no CI/CD enforcement.

### The Solution

A **4-layer testing architecture**:

1. **Shared Test Suite**: Tests that run against BOTH runtimes
2. **Parity Validation Tests**: Automated checks for feature existence
3. **Runtime-Specific Tests**: Tests for implementation-specific behavior
4. **CI/CD Enforcement**: Automated parity checks that MUST pass

---

## 1. Test Architecture

### 1.1 Directory Structure

```
tests/
├── shared/                              # NEW: Shared test suite
│   ├── runtime/
│   │   ├── __init__.py
│   │   ├── conftest.py                 # Shared fixtures and parametrization
│   │   ├── test_conditional_execution.py    # Runs against both runtimes
│   │   ├── test_enterprise_features.py      # Runs against both runtimes
│   │   ├── test_analytics.py                # Runs against both runtimes
│   │   ├── test_resource_management.py      # Runs against both runtimes
│   │   ├── test_error_handling.py           # Runs against both runtimes
│   │   ├── test_monitoring.py               # Runs against both runtimes
│   │   ├── test_security.py                 # Runs against both runtimes
│   │   └── test_workflow_execution.py       # Runs against both runtimes
│   └── nodes/
│       ├── test_python_code_parity.py       # Example: PythonCodeNode vs AsyncPythonCodeNode
│       └── test_sql_parity.py               # Example: SQLNode vs AsyncSQLNode
│
├── parity/                              # NEW: Parity validation
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_runtime_method_parity.py        # Method existence checks
│   ├── test_runtime_signature_parity.py     # Method signature matching
│   ├── test_runtime_behavior_parity.py      # Behavior equivalence
│   ├── test_runtime_coverage_parity.py      # Coverage equality
│   ├── test_node_parity.py                  # Node sync/async parity
│   └── utils/
│       ├── parity_checker.py                # Reusable parity checking utilities
│       └── coverage_reporter.py             # Coverage comparison tools
│
├── unit/
│   ├── runtime/
│   │   ├── local/                       # LocalRuntime-specific tests
│   │   │   ├── test_threading.py            # Sync-specific: threading behavior
│   │   │   ├── test_blocking_io.py          # Sync-specific: blocking operations
│   │   │   └── test_sync_performance.py     # Sync-specific: performance
│   │   └── async_local/                 # AsyncLocalRuntime-specific tests
│   │       ├── test_event_loop.py           # Async-specific: event loop management
│   │       ├── test_concurrency.py          # Async-specific: concurrent execution
│   │       └── test_async_performance.py    # Async-specific: async performance
│   └── nodes/
│       ├── sync/                        # Sync node tests
│       └── async/                       # Async node tests
│
├── integration/
│   └── runtime/
│       ├── shared/                      # NEW: Shared integration tests
│       │   ├── test_database_workflows.py
│       │   ├── test_api_workflows.py
│       │   └── test_file_workflows.py
│       ├── local/                       # Sync-specific integration
│       └── async_local/                 # Async-specific integration
│
└── e2e/
    └── runtime/
        ├── shared/                      # NEW: Shared E2E tests
        │   ├── test_complete_workflows.py
        │   └── test_performance_benchmarks.py
        ├── local/                       # Sync-specific E2E
        └── async_local/                 # Async-specific E2E
```

### 1.2 Naming Conventions

**Shared Tests**:
- File: `test_<feature>.py`
- Class: `TestShared<Feature>` (e.g., `TestSharedConditionalExecution`)
- Test: `test_<behavior>` (same for both runtimes)

**Runtime-Specific Tests**:
- File: `test_<runtime>_<feature>.py` (e.g., `test_async_concurrency.py`)
- Class: `Test<Runtime><Feature>` (e.g., `TestAsyncConcurrency`)
- Test: `test_<specific_behavior>`

**Parity Tests**:
- File: `test_<component>_parity.py`
- Class: `Test<Component>Parity`
- Test: `test_<parity_aspect>_parity`

---

## 2. Shared Test Suite Design

### 2.1 Parametrized Test Pattern (RECOMMENDED)

**Why**: Single test code, runs against both runtimes automatically.

```python
# tests/shared/runtime/conftest.py
import pytest
from kailash.runtime.local import LocalRuntime
from kailash.runtime.async_local import AsyncLocalRuntime


@pytest.fixture(params=[
    pytest.param(LocalRuntime, id="sync"),
    pytest.param(AsyncLocalRuntime, id="async")
])
def runtime_class(request):
    """Parametrize tests to run against both sync and async runtimes."""
    return request.param


@pytest.fixture
def runtime_instance(runtime_class):
    """Create runtime instance for testing."""
    return runtime_class()


def execute_runtime(runtime, workflow, **kwargs):
    """
    Execute workflow with appropriate method for runtime type.

    Handles sync/async differences automatically:
    - LocalRuntime: uses execute() -> (results, run_id)
    - AsyncLocalRuntime: uses execute_workflow_async() -> results
    """
    import asyncio
    import inspect

    if inspect.iscoroutinefunction(getattr(runtime, 'execute_workflow_async', None)):
        # AsyncLocalRuntime: use async method
        return asyncio.run(runtime.execute_workflow_async(workflow, **kwargs))
    else:
        # LocalRuntime: use sync method
        results, run_id = runtime.execute(workflow, **kwargs)
        return results
```

```python
# tests/shared/runtime/test_conditional_execution.py
"""
Shared tests for conditional execution across sync and async runtimes.

These tests ensure that both LocalRuntime and AsyncLocalRuntime implement
conditional execution with identical behavior and features.
"""

import pytest
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.logic.operations import SwitchNode
from kailash.nodes.code.python import PythonCodeNode
from .conftest import execute_runtime


class TestSharedConditionalExecution:
    """Test conditional execution behavior in both runtimes."""

    def test_runtime_initialization_default(self, runtime_class):
        """Test runtime initialization with default conditional_execution."""
        runtime = runtime_class()

        # Both runtimes should default to "route_data"
        assert runtime.conditional_execution == "route_data"

    def test_runtime_initialization_skip_branches(self, runtime_class):
        """Test runtime initialization with skip_branches mode."""
        runtime = runtime_class(conditional_execution="skip_branches")

        assert runtime.conditional_execution == "skip_branches"

    def test_runtime_initialization_invalid_mode(self, runtime_class):
        """Test runtime initialization with invalid conditional_execution mode."""
        with pytest.raises(ValueError) as exc_info:
            runtime_class(conditional_execution="invalid_mode")

        assert "conditional_execution" in str(exc_info.value)
        assert "invalid_mode" in str(exc_info.value)

    def test_conditional_execution_skip_branches_mode(self, runtime_class):
        """Test skip_branches mode skips inactive branches."""
        workflow = WorkflowBuilder()

        # Create conditional workflow
        workflow.add_node("SwitchNode", "switch", {
            "condition_field": "status",
            "operator": "==",
            "value": "active"
        })
        workflow.add_node("PythonCodeNode", "true_branch", {
            "code": "result = {'executed': True, 'branch': 'true'}"
        })
        workflow.add_node("PythonCodeNode", "false_branch", {
            "code": "result = {'executed': True, 'branch': 'false'}"
        })

        workflow.add_connection("switch", "true_output", "true_branch", "input")
        workflow.add_connection("switch", "false_output", "false_branch", "input")

        # Execute with skip_branches mode
        runtime = runtime_class(conditional_execution="skip_branches")
        results = execute_runtime(
            runtime,
            workflow.build(),
            parameters={"switch": {"status": "active"}}
        )

        # True branch should execute
        assert "true_branch" in results
        assert results["true_branch"]["executed"] is True

        # False branch should NOT execute (skipped)
        assert "false_branch" not in results

    def test_conditional_execution_route_data_mode(self, runtime_class):
        """Test route_data mode executes all branches (backward compatible)."""
        workflow = WorkflowBuilder()

        # Create conditional workflow
        workflow.add_node("SwitchNode", "switch", {
            "condition_field": "status",
            "operator": "==",
            "value": "active"
        })
        workflow.add_node("PythonCodeNode", "true_branch", {
            "code": "result = {'executed': True, 'branch': 'true'}"
        })
        workflow.add_node("PythonCodeNode", "false_branch", {
            "code": "result = {'executed': True, 'branch': 'false'}"
        })

        workflow.add_connection("switch", "true_output", "true_branch", "input")
        workflow.add_connection("switch", "false_output", "false_branch", "input")

        # Execute with route_data mode (default)
        runtime = runtime_class(conditional_execution="route_data")
        results = execute_runtime(
            runtime,
            workflow.build(),
            parameters={"switch": {"status": "active"}}
        )

        # Both branches should execute (backward compatible)
        assert "true_branch" in results
        assert "false_branch" in results

    def test_nested_conditional_execution(self, runtime_class):
        """Test nested conditionals with skip_branches mode."""
        workflow = WorkflowBuilder()

        # Level 1 switch
        workflow.add_node("SwitchNode", "level1", {
            "condition_field": "tier",
            "operator": "==",
            "value": "premium"
        })

        # Level 2 switches (nested in true branch)
        workflow.add_node("SwitchNode", "level2_premium", {
            "condition_field": "region",
            "operator": "==",
            "value": "US"
        })

        # Final processors
        workflow.add_node("PythonCodeNode", "premium_us", {
            "code": "result = {'path': 'premium_us'}"
        })
        workflow.add_node("PythonCodeNode", "premium_eu", {
            "code": "result = {'path': 'premium_eu'}"
        })
        workflow.add_node("PythonCodeNode", "basic", {
            "code": "result = {'path': 'basic'}"
        })

        # Connections
        workflow.add_connection("level1", "true_output", "level2_premium", "input")
        workflow.add_connection("level1", "false_output", "basic", "input")
        workflow.add_connection("level2_premium", "true_output", "premium_us", "input")
        workflow.add_connection("level2_premium", "false_output", "premium_eu", "input")

        # Execute: premium US customer
        runtime = runtime_class(conditional_execution="skip_branches")
        results = execute_runtime(
            runtime,
            workflow.build(),
            parameters={"level1": {"tier": "premium", "region": "US"}}
        )

        # Only premium_us path should execute
        assert "premium_us" in results
        assert results["premium_us"]["path"] == "premium_us"

        # Other paths should NOT execute
        assert "premium_eu" not in results
        assert "basic" not in results

    def test_conditional_execution_with_merge(self, runtime_class):
        """Test conditional branches merging back together."""
        workflow = WorkflowBuilder()

        # Split
        workflow.add_node("SwitchNode", "split", {
            "condition_field": "priority",
            "operator": "==",
            "value": "high"
        })

        # Process branches
        workflow.add_node("PythonCodeNode", "high_priority", {
            "code": "result = {'processed': True, 'priority': 'high'}"
        })
        workflow.add_node("PythonCodeNode", "normal_priority", {
            "code": "result = {'processed': True, 'priority': 'normal'}"
        })

        # Merge
        workflow.add_node("MergeNode", "merge", {})

        # Final step
        workflow.add_node("PythonCodeNode", "finalize", {
            "code": "result = {'finalized': True}"
        })

        # Connections
        workflow.add_connection("split", "true_output", "high_priority", "input")
        workflow.add_connection("split", "false_output", "normal_priority", "input")
        workflow.add_connection("high_priority", "result", "merge", "input_high")
        workflow.add_connection("normal_priority", "result", "merge", "input_normal")
        workflow.add_connection("merge", "merged", "finalize", "input")

        # Execute with skip_branches
        runtime = runtime_class(conditional_execution="skip_branches")
        results = execute_runtime(
            runtime,
            workflow.build(),
            parameters={"split": {"priority": "high"}}
        )

        # High priority branch should execute
        assert "high_priority" in results

        # Normal priority should NOT execute
        assert "normal_priority" not in results

        # Merge and finalize should execute
        assert "merge" in results
        assert "finalize" in results


class TestSharedConditionalExecutionEdgeCases:
    """Test edge cases for conditional execution."""

    def test_conditional_with_no_active_branch(self, runtime_class):
        """Test behavior when no branch is active (malformed switch)."""
        workflow = WorkflowBuilder()

        workflow.add_node("SwitchNode", "switch", {
            "condition_field": "status",
            "operator": "==",
            "value": "active"
        })
        workflow.add_node("PythonCodeNode", "processor", {
            "code": "result = {'executed': True}"
        })

        # Only connect true branch
        workflow.add_connection("switch", "true_output", "processor", "input")

        runtime = runtime_class(conditional_execution="skip_branches")
        results = execute_runtime(
            runtime,
            workflow.build(),
            parameters={"switch": {"status": "inactive"}}  # False condition
        )

        # Processor should NOT execute (no active branch)
        assert "processor" not in results

    def test_conditional_with_missing_parameters(self, runtime_class):
        """Test conditional execution with missing switch parameters."""
        workflow = WorkflowBuilder()

        workflow.add_node("SwitchNode", "switch", {
            "condition_field": "status",
            "operator": "==",
            "value": "active"
        })
        workflow.add_node("PythonCodeNode", "processor", {
            "code": "result = {'executed': True}"
        })

        workflow.add_connection("switch", "true_output", "processor", "input")

        runtime = runtime_class(conditional_execution="skip_branches")

        # Should handle missing parameters gracefully
        with pytest.raises(Exception):  # Exact exception depends on implementation
            execute_runtime(
                runtime,
                workflow.build(),
                parameters={}  # Missing switch parameters
            )
```

### 2.2 Sync/Async Execution Helper

The `execute_runtime()` helper automatically handles sync/async differences:

```python
# tests/shared/runtime/conftest.py (expanded)
import asyncio
import inspect
from typing import Any, Dict


def execute_runtime(runtime, workflow, **kwargs) -> Dict[str, Any]:
    """
    Execute workflow with appropriate method for runtime type.

    Automatically handles:
    - LocalRuntime: execute() -> (results, run_id) -> returns results
    - AsyncLocalRuntime: execute_workflow_async() -> results

    Args:
        runtime: Runtime instance (LocalRuntime or AsyncLocalRuntime)
        workflow: Workflow to execute
        **kwargs: Additional execution parameters (parameters, inputs, etc.)

    Returns:
        Execution results dictionary
    """
    # Check if runtime has async execution method
    if hasattr(runtime, 'execute_workflow_async') and \
       inspect.iscoroutinefunction(runtime.execute_workflow_async):
        # AsyncLocalRuntime: use async method
        return asyncio.run(runtime.execute_workflow_async(workflow, **kwargs))
    else:
        # LocalRuntime: use sync method
        results, run_id = runtime.execute(workflow, **kwargs)
        return results


def execute_runtime_with_run_id(runtime, workflow, **kwargs) -> tuple:
    """
    Execute workflow and return both results and run_id.

    For tests that need to verify run_id or execution tracking.

    Returns:
        Tuple of (results, run_id)
    """
    if hasattr(runtime, 'execute_workflow_async') and \
       inspect.iscoroutinefunction(runtime.execute_workflow_async):
        # AsyncLocalRuntime doesn't return run_id from execute_workflow_async
        # Need to access it differently or generate one
        results = asyncio.run(runtime.execute_workflow_async(workflow, **kwargs))
        run_id = getattr(runtime, '_last_run_id', None)  # If runtime tracks this
        return results, run_id
    else:
        # LocalRuntime returns both
        return runtime.execute(workflow, **kwargs)
```

---

## 3. Parity Validation Tests

### 3.1 Method Existence Parity

```python
# tests/parity/test_runtime_method_parity.py
"""
Parity tests to ensure LocalRuntime and AsyncLocalRuntime have matching methods.

These tests enforce that every public method in LocalRuntime has a corresponding
method in AsyncLocalRuntime (unless explicitly documented as runtime-specific).
"""

import inspect
import pytest
from kailash.runtime.local import LocalRuntime
from kailash.runtime.async_local import AsyncLocalRuntime


# Document runtime-specific methods that are ALLOWED to differ
ALLOWED_ASYNC_ONLY_METHODS = {
    'execute_workflow_async',       # Async-specific execution method
    '_execute_node_async',           # Async node execution
    '_execute_fully_async_workflow', # Async workflow optimization
    '_execute_mixed_workflow',       # Mixed sync/async handling
    '_execute_sync_node_async',      # Sync node in async context
    '_execute_sync_node_in_thread',  # Thread pool execution
    '_execute_sync_workflow',        # Sync workflow in async runtime
    '_execute_sync_workflow_internal',
    '_prepare_async_node_inputs',    # Async input preparation
    '_prepare_sync_node_inputs',     # Sync input preparation
}

ALLOWED_SYNC_ONLY_METHODS = {
    # Currently none - async inherits from sync
}


class TestRuntimeMethodParity:
    """Test that runtimes have matching methods."""

    def test_all_local_runtime_methods_exist_in_async(self):
        """
        Every public method in LocalRuntime must exist in AsyncLocalRuntime.

        This ensures AsyncLocalRuntime maintains full backward compatibility
        and feature parity with LocalRuntime.
        """
        local_methods = {
            name for name in dir(LocalRuntime)
            if not name.startswith('__') and callable(getattr(LocalRuntime, name))
        }

        async_methods = {
            name for name in dir(AsyncLocalRuntime)
            if not name.startswith('__') and callable(getattr(AsyncLocalRuntime, name))
        }

        # Methods in LocalRuntime but missing from AsyncLocalRuntime
        missing_methods = local_methods - async_methods - ALLOWED_SYNC_ONLY_METHODS

        assert not missing_methods, (
            f"AsyncLocalRuntime is missing {len(missing_methods)} methods from LocalRuntime:\n"
            f"{sorted(missing_methods)}\n\n"
            f"If these are intentionally async-only, add them to ALLOWED_SYNC_ONLY_METHODS."
        )

    def test_async_specific_methods_documented(self):
        """
        Async-specific methods must be documented in ALLOWED_ASYNC_ONLY_METHODS.

        This ensures we track which methods are intentionally different.
        """
        local_methods = {
            name for name in dir(LocalRuntime)
            if not name.startswith('__') and callable(getattr(LocalRuntime, name))
        }

        async_methods = {
            name for name in dir(AsyncLocalRuntime)
            if not name.startswith('__') and callable(getattr(AsyncLocalRuntime, name))
        }

        # Methods in AsyncLocalRuntime but not in LocalRuntime
        extra_methods = async_methods - local_methods

        # All extra methods should be documented
        undocumented = extra_methods - ALLOWED_ASYNC_ONLY_METHODS

        assert not undocumented, (
            f"AsyncLocalRuntime has {len(undocumented)} undocumented extra methods:\n"
            f"{sorted(undocumented)}\n\n"
            f"Add them to ALLOWED_ASYNC_ONLY_METHODS with documentation."
        )

    def test_conditional_execution_method_exists(self):
        """Test that conditional execution methods exist in both runtimes."""
        critical_methods = [
            '_should_skip_conditional_node',
            '_get_conditional_analysis',
            '_execute_conditional_approach',
            '_execute_pruned_plan',
        ]

        for method_name in critical_methods:
            assert hasattr(LocalRuntime, method_name), \
                f"LocalRuntime missing critical method: {method_name}"
            assert hasattr(AsyncLocalRuntime, method_name), \
                f"AsyncLocalRuntime missing critical method: {method_name}"

    def test_enterprise_feature_methods_exist(self):
        """Test that enterprise feature methods exist in both runtimes."""
        enterprise_methods = [
            '_check_workflow_access',        # Access control
            '_log_audit_event',              # Audit logging
            '_initialize_persistent_resources',  # Resource management
            '_cleanup_resources',            # Resource cleanup
        ]

        for method_name in enterprise_methods:
            assert hasattr(LocalRuntime, method_name), \
                f"LocalRuntime missing enterprise method: {method_name}"
            assert hasattr(AsyncLocalRuntime, method_name), \
                f"AsyncLocalRuntime missing enterprise method: {method_name}"
```

### 3.2 Method Signature Parity

```python
# tests/parity/test_runtime_signature_parity.py
"""
Parity tests for method signatures between LocalRuntime and AsyncLocalRuntime.

Ensures that corresponding methods have compatible signatures (parameters, types, defaults).
"""

import inspect
import pytest
from typing import get_type_hints
from kailash.runtime.local import LocalRuntime
from kailash.runtime.async_local import AsyncLocalRuntime


# Methods where signature differences are ALLOWED
ALLOWED_SIGNATURE_DIFFERENCES = {
    'execute',  # Sync returns (results, run_id), async has execute_workflow_async
    '_execute_node_async',  # Async-specific
    '_execute_sync_node_async',  # Async-specific
}


class TestRuntimeSignatureParity:
    """Test that method signatures match between runtimes."""

    def get_method_signature(self, cls, method_name):
        """Get method signature for comparison."""
        method = getattr(cls, method_name)
        return inspect.signature(method)

    def compare_parameters(self, local_sig, async_sig, method_name):
        """Compare parameter lists between signatures."""
        local_params = list(local_sig.parameters.keys())
        async_params = list(async_sig.parameters.keys())

        # Remove 'self'
        local_params = [p for p in local_params if p != 'self']
        async_params = [p for p in async_params if p != 'self']

        return local_params, async_params

    def test_shared_methods_have_matching_signatures(self):
        """
        Shared methods should have matching signatures.

        Verifies parameter names, order, and defaults match.
        """
        local_methods = {
            name for name in dir(LocalRuntime)
            if not name.startswith('__')
            and callable(getattr(LocalRuntime, name))
            and hasattr(AsyncLocalRuntime, name)
        }

        mismatches = []

        for method_name in local_methods:
            if method_name in ALLOWED_SIGNATURE_DIFFERENCES:
                continue

            local_sig = self.get_method_signature(LocalRuntime, method_name)
            async_sig = self.get_method_signature(AsyncLocalRuntime, method_name)

            local_params, async_params = self.compare_parameters(
                local_sig, async_sig, method_name
            )

            if local_params != async_params:
                mismatches.append({
                    'method': method_name,
                    'local_params': local_params,
                    'async_params': async_params,
                })

        assert not mismatches, (
            f"Found {len(mismatches)} method signature mismatches:\n" +
            '\n'.join([
                f"  {m['method']}:\n"
                f"    Local:  {m['local_params']}\n"
                f"    Async:  {m['async_params']}"
                for m in mismatches
            ])
        )

    def test_constructor_parameters_match(self):
        """Test that __init__ parameters match (with allowed async additions)."""
        local_init = inspect.signature(LocalRuntime.__init__)
        async_init = inspect.signature(AsyncLocalRuntime.__init__)

        local_params = set(local_init.parameters.keys()) - {'self'}
        async_params = set(async_init.parameters.keys()) - {'self'}

        # All LocalRuntime parameters should exist in AsyncLocalRuntime
        missing = local_params - async_params
        assert not missing, (
            f"AsyncLocalRuntime.__init__ missing parameters: {missing}"
        )

        # Async can have additional parameters (documented)
        async_only = async_params - local_params
        documented_async_params = {
            'max_concurrency',      # Async-specific: concurrent execution
            'enable_profiling',     # Async-specific: performance profiling
            'thread_pool_size',     # Async-specific: thread pool for sync nodes
        }

        undocumented = async_only - documented_async_params
        assert not undocumented, (
            f"AsyncLocalRuntime has undocumented extra parameters: {undocumented}"
        )

    def test_conditional_execution_parameter_type_matches(self):
        """Test conditional_execution parameter has same type in both."""
        local_init = inspect.signature(LocalRuntime.__init__)
        async_init = inspect.signature(AsyncLocalRuntime.__init__)

        local_param = local_init.parameters.get('conditional_execution')
        async_param = async_init.parameters.get('conditional_execution')

        assert local_param is not None, "LocalRuntime missing conditional_execution"
        assert async_param is not None, "AsyncLocalRuntime missing conditional_execution"

        # Check default values match
        assert local_param.default == async_param.default, (
            f"conditional_execution defaults differ: "
            f"Local={local_param.default}, Async={async_param.default}"
        )
```

### 3.3 Behavior Parity Tests

```python
# tests/parity/test_runtime_behavior_parity.py
"""
Behavior parity tests: Ensure identical input produces identical output.

These tests verify that LocalRuntime and AsyncLocalRuntime produce the same
results for the same workflows and inputs.
"""

import pytest
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.runtime.async_local import AsyncLocalRuntime
from tests.shared.runtime.conftest import execute_runtime


class TestRuntimeBehaviorParity:
    """Test that both runtimes produce identical results."""

    def test_simple_workflow_produces_same_results(self):
        """Test that simple workflow produces identical results."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "calculate", {
            "code": "result = {'sum': 10 + 20, 'product': 10 * 20}"
        })
        built_workflow = workflow.build()

        # Execute with LocalRuntime
        local_runtime = LocalRuntime()
        local_results = execute_runtime(local_runtime, built_workflow)

        # Execute with AsyncLocalRuntime
        async_runtime = AsyncLocalRuntime()
        async_results = execute_runtime(async_runtime, built_workflow)

        # Results should be identical
        assert local_results == async_results

    def test_conditional_workflow_produces_same_results(self):
        """Test conditional workflow produces same results in both runtimes."""
        workflow = WorkflowBuilder()

        workflow.add_node("SwitchNode", "switch", {
            "condition_field": "value",
            "operator": ">",
            "value": 50
        })
        workflow.add_node("PythonCodeNode", "high", {
            "code": "result = {'category': 'high'}"
        })
        workflow.add_node("PythonCodeNode", "low", {
            "code": "result = {'category': 'low'}"
        })

        workflow.add_connection("switch", "true_output", "high", "input")
        workflow.add_connection("switch", "false_output", "low", "input")

        built_workflow = workflow.build()

        # Test with high value
        params = {"switch": {"value": 75}}

        local_runtime = LocalRuntime(conditional_execution="skip_branches")
        local_results = execute_runtime(local_runtime, built_workflow, parameters=params)

        async_runtime = AsyncLocalRuntime(conditional_execution="skip_branches")
        async_results = execute_runtime(async_runtime, built_workflow, parameters=params)

        # Both should execute only high branch
        assert "high" in local_results
        assert "high" in async_results
        assert "low" not in local_results
        assert "low" not in async_results

        assert local_results["high"] == async_results["high"]

    def test_error_handling_produces_same_behavior(self):
        """Test that error handling behaves identically."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "error_node", {
            "code": "raise ValueError('Test error')"
        })
        built_workflow = workflow.build()

        local_runtime = LocalRuntime()
        async_runtime = AsyncLocalRuntime()

        # Both should raise same exception
        with pytest.raises(Exception) as local_exc:
            execute_runtime(local_runtime, built_workflow)

        with pytest.raises(Exception) as async_exc:
            execute_runtime(async_runtime, built_workflow)

        # Exception types should match
        assert type(local_exc.value) == type(async_exc.value)
        assert str(local_exc.value) == str(async_exc.value)
```

### 3.4 Coverage Parity Validation

```python
# tests/parity/test_runtime_coverage_parity.py
"""
Coverage parity tests: Ensure test coverage is equal between runtimes.

These tests verify that LocalRuntime and AsyncLocalRuntime have equal test coverage.
"""

import subprocess
import re
import pytest


class TestRuntimeCoverageParity:
    """Test that test coverage is equal between runtimes."""

    def get_coverage_for_module(self, module_path, test_path):
        """
        Run coverage for specific module and test path.

        Returns coverage percentage as float.
        """
        cmd = [
            "coverage", "run", "--source", module_path,
            "-m", "pytest", test_path, "-v"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        # Get coverage report
        report = subprocess.run(
            ["coverage", "report"],
            capture_output=True,
            text=True
        )

        # Parse coverage percentage
        # Format: "TOTAL    123    45    63%"
        match = re.search(r'TOTAL\s+\d+\s+\d+\s+(\d+)%', report.stdout)
        if match:
            return float(match.group(1))
        return 0.0

    @pytest.mark.slow
    def test_runtime_coverage_parity(self):
        """
        Test that LocalRuntime and AsyncLocalRuntime have equal coverage.

        NOTE: This test is slow - runs full test suite twice.
        """
        # Get LocalRuntime coverage
        local_coverage = self.get_coverage_for_module(
            "src/kailash/runtime/local.py",
            "tests/shared/runtime tests/unit/runtime/local"
        )

        # Get AsyncLocalRuntime coverage
        async_coverage = self.get_coverage_for_module(
            "src/kailash/runtime/async_local.py",
            "tests/shared/runtime tests/unit/runtime/async_local"
        )

        # Coverage should be within 5% (allow for async-specific code)
        coverage_diff = abs(local_coverage - async_coverage)

        assert coverage_diff <= 5.0, (
            f"Coverage parity violation:\n"
            f"  LocalRuntime:      {local_coverage}%\n"
            f"  AsyncLocalRuntime: {async_coverage}%\n"
            f"  Difference:        {coverage_diff}%\n\n"
            f"Both runtimes should have similar test coverage."
        )

    @pytest.mark.slow
    def test_conditional_execution_coverage_parity(self):
        """
        Test conditional execution has equal coverage in both runtimes.

        This is the critical gap that was discovered (16 tests vs 0 tests).
        """
        # Count conditional execution tests
        local_tests = subprocess.run(
            ["pytest", "tests/unit/runtime/local", "-k", "conditional", "--collect-only"],
            capture_output=True,
            text=True
        )

        async_tests = subprocess.run(
            ["pytest", "tests/unit/runtime/async_local", "-k", "conditional", "--collect-only"],
            capture_output=True,
            text=True
        )

        # Also count shared tests
        shared_tests = subprocess.run(
            ["pytest", "tests/shared/runtime", "-k", "conditional", "--collect-only"],
            capture_output=True,
            text=True
        )

        # Extract test counts
        local_count = local_tests.stdout.count("test_")
        async_count = async_tests.stdout.count("test_")
        shared_count = shared_tests.stdout.count("test_")

        # Both should have shared tests + their specific tests
        # Shared tests run for both, so effective coverage should be equal
        local_effective = local_count + shared_count
        async_effective = async_count + shared_count

        assert local_effective > 0, "No LocalRuntime conditional tests found"
        assert async_effective > 0, "No AsyncLocalRuntime conditional tests found"

        # Allow 20% difference for runtime-specific tests
        ratio = min(local_effective, async_effective) / max(local_effective, async_effective)

        assert ratio >= 0.8, (
            f"Conditional execution test count disparity:\n"
            f"  LocalRuntime:      {local_count} specific + {shared_count} shared = {local_effective} total\n"
            f"  AsyncLocalRuntime: {async_count} specific + {shared_count} shared = {async_effective} total\n"
            f"  Coverage ratio:    {ratio:.2%}\n\n"
            f"Both runtimes should have similar test counts for conditional execution."
        )
```

---

## 4. CI/CD Enforcement

### 4.1 GitHub Actions Workflow

```yaml
# .github/workflows/sync-async-parity.yml
name: Sync/Async Parity Enforcement

on:
  push:
    branches: [ main, develop, dataflow ]
  pull_request:
    branches: [ main, develop, dataflow ]

jobs:
  parity-tests:
    name: Sync/Async Parity Tests
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e ".[test]"
        pip install coverage pytest-cov

    - name: Run Parity Validation Tests
      run: |
        pytest tests/parity/ -v --tb=short
      continue-on-error: false  # MUST pass

    - name: Run Shared Test Suite
      run: |
        pytest tests/shared/runtime/ -v --tb=short
      continue-on-error: false  # MUST pass

    - name: Check Coverage Parity
      run: |
        # LocalRuntime coverage
        coverage run --source=src/kailash/runtime/local.py \
          -m pytest tests/shared/runtime tests/unit/runtime/local -v
        coverage report --fail-under=85 > local_coverage.txt
        LOCAL_COV=$(grep TOTAL local_coverage.txt | awk '{print $4}' | sed 's/%//')

        # AsyncLocalRuntime coverage
        coverage erase
        coverage run --source=src/kailash/runtime/async_local.py \
          -m pytest tests/shared/runtime tests/unit/runtime/async_local -v
        coverage report --fail-under=85 > async_coverage.txt
        ASYNC_COV=$(grep TOTAL async_coverage.txt | awk '{print $4}' | sed 's/%//')

        # Compare coverage
        echo "LocalRuntime coverage: $LOCAL_COV%"
        echo "AsyncLocalRuntime coverage: $ASYNC_COV%"

        # Calculate difference
        DIFF=$(echo "$LOCAL_COV - $ASYNC_COV" | bc | sed 's/-//')
        echo "Coverage difference: $DIFF%"

        # Fail if difference > 5%
        if (( $(echo "$DIFF > 5.0" | bc -l) )); then
          echo "ERROR: Coverage parity violation (difference: $DIFF%)"
          echo "LocalRuntime:      $LOCAL_COV%"
          echo "AsyncLocalRuntime: $ASYNC_COV%"
          exit 1
        fi

        echo "✅ Coverage parity check passed"

  conditional-execution-parity:
    name: Conditional Execution Feature Parity
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e ".[test]"

    - name: Count Conditional Execution Tests
      run: |
        # Count tests for each runtime
        LOCAL_COUNT=$(pytest tests/unit/runtime/local tests/shared/runtime \
          -k conditional --collect-only -q | grep "test session starts" | awk '{print $1}')

        ASYNC_COUNT=$(pytest tests/unit/runtime/async_local tests/shared/runtime \
          -k conditional --collect-only -q | grep "test session starts" | awk '{print $1}')

        echo "LocalRuntime conditional tests: $LOCAL_COUNT"
        echo "AsyncLocalRuntime conditional tests: $ASYNC_COUNT"

        # Both should have tests
        if [ "$LOCAL_COUNT" -eq 0 ]; then
          echo "ERROR: No conditional execution tests for LocalRuntime"
          exit 1
        fi

        if [ "$ASYNC_COUNT" -eq 0 ]; then
          echo "ERROR: No conditional execution tests for AsyncLocalRuntime"
          exit 1
        fi

        # Calculate ratio
        if [ "$LOCAL_COUNT" -gt "$ASYNC_COUNT" ]; then
          RATIO=$(echo "scale=2; $ASYNC_COUNT / $LOCAL_COUNT" | bc)
        else
          RATIO=$(echo "scale=2; $LOCAL_COUNT / $ASYNC_COUNT" | bc)
        fi

        echo "Test count ratio: $RATIO"

        # Ratio should be at least 0.8 (80%)
        if (( $(echo "$RATIO < 0.8" | bc -l) )); then
          echo "ERROR: Conditional execution test disparity"
          echo "  LocalRuntime:      $LOCAL_COUNT tests"
          echo "  AsyncLocalRuntime: $ASYNC_COUNT tests"
          echo "  Ratio:             $RATIO (minimum: 0.80)"
          exit 1
        fi

        echo "✅ Conditional execution parity check passed"

  method-signature-parity:
    name: Method Signature Parity
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e ".[test]"

    - name: Check Method Parity
      run: |
        python tests/parity/utils/check_method_parity.py
      continue-on-error: false  # MUST pass

    - name: Generate Parity Report
      if: failure()
      run: |
        python tests/parity/utils/generate_parity_report.py > parity_report.md

    - name: Upload Parity Report
      if: failure()
      uses: actions/upload-artifact@v3
      with:
        name: parity-report
        path: parity_report.md

  integration-parity:
    name: Integration Test Parity
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e ".[test]"

    - name: Start Test Infrastructure
      run: |
        cd tests/utils
        ./test-env up
        ./test-env status

    - name: Run Shared Integration Tests
      run: |
        pytest tests/integration/runtime/shared/ -v --tb=short
      continue-on-error: false  # MUST pass

    - name: Teardown Test Infrastructure
      if: always()
      run: |
        cd tests/utils
        ./test-env down
```

### 4.2 Pre-commit Hook

```bash
# .git/hooks/pre-commit (or use pre-commit framework)
#!/bin/bash
set -e

echo "🔍 Running sync/async parity checks..."

# Quick parity validation
echo "  → Method existence parity..."
pytest tests/parity/test_runtime_method_parity.py -v -x

echo "  → Signature parity..."
pytest tests/parity/test_runtime_signature_parity.py -v -x

# Run shared tests (fast subset)
echo "  → Shared test suite (quick)..."
pytest tests/shared/runtime/test_conditional_execution.py::TestSharedConditionalExecution::test_runtime_initialization_default -v
pytest tests/shared/runtime/test_conditional_execution.py::TestSharedConditionalExecution::test_conditional_execution_skip_branches_mode -v

echo "✅ Parity checks passed"
```

### 4.3 PR Check Requirements

```yaml
# .github/workflows/pr-checks.yml
name: PR Requirements

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  parity-gate:
    name: Sync/Async Parity Gate
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        pip install -e ".[test]"

    - name: Check for Runtime Changes
      id: check_changes
      run: |
        # Check if runtime files were modified
        git diff --name-only origin/main...HEAD | grep -E "(src/kailash/runtime/local\.py|src/kailash/runtime/async_local\.py)" > /dev/null
        echo "runtime_changed=$?" >> $GITHUB_OUTPUT

    - name: Validate Parity for Runtime Changes
      if: steps.check_changes.outputs.runtime_changed == '0'
      run: |
        echo "⚠️  Runtime files changed - enforcing parity requirements"

        # Check that BOTH runtimes have corresponding changes
        LOCAL_CHANGED=$(git diff --name-only origin/main...HEAD | grep "local\.py" | wc -l)
        ASYNC_CHANGED=$(git diff --name-only origin/main...HEAD | grep "async_local\.py" | wc -l)

        if [ "$LOCAL_CHANGED" -gt 0 ] && [ "$ASYNC_CHANGED" -eq 0 ]; then
          echo "❌ LocalRuntime changed but AsyncLocalRuntime unchanged"
          echo "   New features must be implemented in BOTH runtimes"
          exit 1
        fi

        if [ "$ASYNC_CHANGED" -gt 0 ] && [ "$LOCAL_CHANGED" -eq 0 ]; then
          # This is OK - async can have async-specific changes
          echo "✅ AsyncLocalRuntime-only changes (allowed)"
        fi

        # Run full parity validation
        pytest tests/parity/ -v

        echo "✅ Parity validation passed"
```

---

## 5. Test Coverage Plan

### 5.1 Current State (Baseline)

```bash
# Run this to establish baseline
pytest tests/unit/runtime/local -v --cov=src/kailash/runtime/local \
  --cov-report=term-missing > local_baseline.txt

pytest tests/unit/runtime/async_local -v --cov=src/kailash/runtime/async_local \
  --cov-report=term-missing > async_baseline.txt
```

**Current Gap Analysis**:

| Feature Area | LocalRuntime Tests | AsyncLocalRuntime Tests | Gap |
|-------------|-------------------|------------------------|-----|
| Conditional Execution | 16 files (26 tests) | 0 files (0 tests) | **100%** |
| Enterprise Features | 8 files | 2 files | 75% |
| Error Handling | 12 files | 3 files | 75% |
| Resource Management | 5 files | 2 files | 60% |
| Analytics | 4 files | 1 file | 75% |
| **TOTAL** | **45 test files** | **5 test files** | **89%** |

### 5.2 Target State

**Coverage Requirements**:

- **Minimum Coverage**: 85% for both runtimes
- **Parity Threshold**: Coverage difference ≤ 5%
- **Test Count Ratio**: ≥ 80% (allowing for runtime-specific tests)

**Target by Feature Area**:

| Feature Area | Target LocalRuntime | Target AsyncLocalRuntime | Shared Tests |
|-------------|-------------------|------------------------|--------------|
| Conditional Execution | 10 tests | 10 tests | **20 shared tests** |
| Enterprise Features | 5 tests | 5 tests | 15 shared tests |
| Error Handling | 8 tests | 8 tests | 20 shared tests |
| Resource Management | 4 tests | 4 tests | 10 shared tests |
| Analytics | 3 tests | 3 tests | 8 shared tests |
| **TOTAL** | **30 specific** | **30 specific** | **73 shared** |

### 5.3 Gap Closure Timeline

**Phase 1: Foundation (Week 1)**
- ✅ Create shared test infrastructure (`conftest.py`, helpers)
- ✅ Create parity validation tests (method/signature)
- ✅ Set up CI/CD workflows
- ✅ Establish baseline coverage metrics

**Phase 2: Conditional Execution (Week 2)**
- ✅ Port existing LocalRuntime conditional tests to shared suite
- ✅ Verify AsyncLocalRuntime passes all shared tests
- ✅ Add async-specific conditional tests
- Target: 20 shared + 10 specific = 30 total tests

**Phase 3: Enterprise Features (Week 3)**
- ✅ Create shared tests for access control, audit, monitoring
- ✅ Port existing tests to shared suite
- Target: 15 shared + 10 specific = 25 total tests

**Phase 4: Error Handling & Resources (Week 4)**
- ✅ Create shared error handling tests
- ✅ Create shared resource management tests
- Target: 30 shared + 15 specific = 45 total tests

**Phase 5: Full Coverage (Week 5-6)**
- ✅ Complete remaining feature areas
- ✅ Achieve 85%+ coverage for both runtimes
- ✅ Coverage difference < 5%
- ✅ All CI/CD checks passing

---

## 6. Migration Strategy

### 6.1 Migrating Existing Tests to Shared Suite

**Step-by-Step Process**:

1. **Identify Portable Tests**
   ```bash
   # Find tests that test behavior, not implementation
   grep -r "def test_" tests/unit/runtime/test_conditional_execution.py | \
     grep -v "_internal\|_private\|threading\|blocking"
   ```

2. **Create Shared Test File**
   ```python
   # tests/shared/runtime/test_conditional_execution.py
   # Copy test, add parametrization, use execute_runtime helper
   ```

3. **Verify Both Runtimes Pass**
   ```bash
   pytest tests/shared/runtime/test_conditional_execution.py -v
   # Should show: test_name[sync] PASSED, test_name[async] PASSED
   ```

4. **Remove Duplicates from Runtime-Specific Tests**
   ```bash
   # Keep only runtime-specific tests in unit/runtime/local/
   # Keep only async-specific tests in unit/runtime/async_local/
   ```

**Example Migration**:

**Before** (tests/unit/runtime/test_conditional_execution.py):
```python
def test_runtime_initialization_default():
    runtime = LocalRuntime()
    assert runtime.conditional_execution == "route_data"
```

**After** (tests/shared/runtime/test_conditional_execution.py):
```python
def test_runtime_initialization_default(runtime_class):
    """Test default conditional_execution in both runtimes."""
    runtime = runtime_class()
    assert runtime.conditional_execution == "route_data"
```

### 6.2 Parallel Development vs Sequential

**RECOMMENDATION: Parallel Development**

**Why**:
- Faster delivery (weeks vs months)
- Can be done by multiple developers
- Immediate value (catches new gaps early)

**Approach**:

```mermaid
graph TD
    A[Start] --> B[Create Infrastructure]
    B --> C1[Team 1: Parity Tests]
    B --> C2[Team 2: Shared Tests - Conditional]
    B --> C3[Team 3: Shared Tests - Enterprise]
    C1 --> D[CI/CD Setup]
    C2 --> D
    C3 --> D
    D --> E[Full Validation]
    E --> F[Production Ready]
```

**Work Packages**:

1. **Package A: Infrastructure** (1 developer, 2 days)
   - Create directory structure
   - Set up conftest.py with fixtures
   - Create execute_runtime helper
   - Document patterns

2. **Package B: Parity Validation** (1 developer, 3 days)
   - Method existence tests
   - Signature parity tests
   - Coverage parity tests
   - CI/CD scripts

3. **Package C: Conditional Execution** (1 developer, 5 days)
   - Migrate 26 tests to shared suite
   - Verify AsyncLocalRuntime implementation
   - Add async-specific tests
   - Integration tests

4. **Package D: Enterprise Features** (1 developer, 5 days)
   - Access control tests
   - Audit logging tests
   - Monitoring tests
   - Resource management tests

5. **Package E: CI/CD** (1 developer, 3 days)
   - GitHub Actions workflows
   - Pre-commit hooks
   - PR requirements
   - Coverage reporting

**Timeline**: 2-3 weeks with 3 developers, 4-6 weeks with 1 developer

---

## 7. Ongoing Maintenance

### 7.1 Adding New Features with Parity

**MANDATORY Process for New Runtime Features**:

```python
# 1. Write shared test FIRST (TDD)
# tests/shared/runtime/test_new_feature.py

def test_new_feature_basic(runtime_class):
    """Test new feature works in both runtimes."""
    runtime = runtime_class(enable_new_feature=True)
    # Test implementation...
    assert runtime.new_feature_enabled

# 2. Run test - should FAIL for both
pytest tests/shared/runtime/test_new_feature.py -v
# Expected: test_new_feature_basic[sync] FAILED
# Expected: test_new_feature_basic[async] FAILED

# 3. Implement in LocalRuntime
# src/kailash/runtime/local.py

def __init__(self, enable_new_feature=False, ...):
    self.enable_new_feature = enable_new_feature

def new_feature_method(self):
    # Implementation...
    pass

# 4. Run test - should PASS for sync, FAIL for async
pytest tests/shared/runtime/test_new_feature.py -v
# Expected: test_new_feature_basic[sync] PASSED
# Expected: test_new_feature_basic[async] FAILED  ← Parity violation!

# 5. Implement in AsyncLocalRuntime
# src/kailash/runtime/async_local.py
# (Inherits from LocalRuntime, may need override for async behavior)

async def new_feature_method_async(self):
    # Async implementation...
    pass

# 6. Run test - should PASS for both
pytest tests/shared/runtime/test_new_feature.py -v
# Expected: test_new_feature_basic[sync] PASSED
# Expected: test_new_feature_basic[async] PASSED  ← Parity achieved!

# 7. CI/CD will enforce this automatically
```

**CI/CD will BLOCK PR if**:
- Shared test added but only passes for one runtime
- LocalRuntime changed without AsyncLocalRuntime test
- Coverage gap exceeds threshold

### 7.2 Quarterly Parity Audits

**Automated Quarterly Report**:

```python
# tests/parity/utils/generate_quarterly_report.py
"""Generate comprehensive parity audit report."""

import subprocess
import json
from datetime import datetime


def generate_parity_report():
    """Generate quarterly parity audit report."""

    report = {
        'date': datetime.now().isoformat(),
        'method_parity': check_method_parity(),
        'signature_parity': check_signature_parity(),
        'coverage_parity': check_coverage_parity(),
        'test_count_parity': check_test_count_parity(),
        'behavior_parity': check_behavior_parity(),
    }

    # Generate markdown report
    markdown = f"""
# Sync/Async Parity Audit Report

**Date**: {report['date']}

## Summary

| Check | Status | Details |
|-------|--------|---------|
| Method Parity | {'✅ PASS' if report['method_parity']['passed'] else '❌ FAIL'} | {report['method_parity']['summary']} |
| Signature Parity | {'✅ PASS' if report['signature_parity']['passed'] else '❌ FAIL'} | {report['signature_parity']['summary']} |
| Coverage Parity | {'✅ PASS' if report['coverage_parity']['passed'] else '❌ FAIL'} | {report['coverage_parity']['summary']} |
| Test Count Parity | {'✅ PASS' if report['test_count_parity']['passed'] else '❌ FAIL'} | {report['test_count_parity']['summary']} |
| Behavior Parity | {'✅ PASS' if report['behavior_parity']['passed'] else '❌ FAIL'} | {report['behavior_parity']['summary']} |

## Detailed Results

### Method Parity
{report['method_parity']['details']}

### Coverage Metrics
- **LocalRuntime**: {report['coverage_parity']['local_coverage']}%
- **AsyncLocalRuntime**: {report['coverage_parity']['async_coverage']}%
- **Difference**: {report['coverage_parity']['difference']}%

### Test Counts
- **LocalRuntime**: {report['test_count_parity']['local_count']} tests
- **AsyncLocalRuntime**: {report['test_count_parity']['async_count']} tests
- **Shared Tests**: {report['test_count_parity']['shared_count']} tests

## Recommendations

{generate_recommendations(report)}
"""

    return markdown


if __name__ == '__main__':
    report = generate_parity_report()
    with open('parity_audit_report.md', 'w') as f:
        f.write(report)
    print("Quarterly parity audit report generated: parity_audit_report.md")
```

**Schedule**: Run automatically on 1st of each quarter, send to team.

### 7.3 Automated Monitoring

**Daily Parity Dashboard**:

```yaml
# .github/workflows/daily-parity-check.yml
name: Daily Parity Monitoring

on:
  schedule:
    - cron: '0 8 * * *'  # 8 AM daily
  workflow_dispatch:      # Manual trigger

jobs:
  daily-check:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: pip install -e ".[test]"

    - name: Run Parity Checks
      run: |
        pytest tests/parity/ -v --json-report --json-report-file=parity_report.json

    - name: Generate Dashboard
      run: |
        python tests/parity/utils/generate_dashboard.py

    - name: Upload to Dashboard
      run: |
        # Upload to internal monitoring system
        curl -X POST https://monitoring.internal/parity-dashboard \
          -H "Content-Type: application/json" \
          -d @parity_dashboard.json

    - name: Notify on Failure
      if: failure()
      run: |
        # Send Slack notification
        curl -X POST ${{ secrets.SLACK_WEBHOOK }} \
          -H "Content-Type: application/json" \
          -d '{
            "text": "⚠️ Daily parity check failed!",
            "blocks": [
              {
                "type": "section",
                "text": {
                  "type": "mrkdwn",
                  "text": "*Sync/Async Parity Check Failed*\n\nView details: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
                }
              }
            ]
          }'
```

---

## 8. Complete CI/CD Configuration

### 8.1 Full GitHub Actions Workflow

```yaml
# .github/workflows/comprehensive-parity-enforcement.yml
name: Comprehensive Sync/Async Parity Enforcement

on:
  push:
    branches: [ main, develop, dataflow ]
    paths:
      - 'src/kailash/runtime/**'
      - 'tests/shared/runtime/**'
      - 'tests/parity/**'
      - 'tests/unit/runtime/**'
      - 'tests/integration/runtime/**'
  pull_request:
    branches: [ main, develop, dataflow ]

env:
  COVERAGE_THRESHOLD: 85
  PARITY_THRESHOLD: 5.0
  TEST_RATIO_THRESHOLD: 0.8

jobs:
  parity-validation:
    name: Parity Validation Tests
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
        cache: 'pip'

    - name: Install dependencies
      run: |
        pip install -e ".[test]"

    - name: Method Existence Parity
      run: |
        pytest tests/parity/test_runtime_method_parity.py -v --tb=short

    - name: Method Signature Parity
      run: |
        pytest tests/parity/test_runtime_signature_parity.py -v --tb=short

    - name: Behavior Parity
      run: |
        pytest tests/parity/test_runtime_behavior_parity.py -v --tb=short

    - name: Upload Parity Results
      if: always()
      uses: actions/upload-artifact@v3
      with:
        name: parity-validation-results
        path: |
          parity_report.xml
          parity_report.html

  shared-test-suite:
    name: Shared Test Suite (Both Runtimes)
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
        cache: 'pip'

    - name: Install dependencies
      run: |
        pip install -e ".[test]"

    - name: Run Shared Tests
      run: |
        pytest tests/shared/runtime/ -v \
          --junitxml=shared_tests.xml \
          --cov=src/kailash/runtime \
          --cov-report=html:shared_coverage_html \
          --cov-report=term

    - name: Verify Both Runtimes Tested
      run: |
        # Verify tests ran for both sync and async
        if ! grep -q "test_.*\[sync\]" shared_tests.xml; then
          echo "❌ No sync runtime tests found"
          exit 1
        fi
        if ! grep -q "test_.*\[async\]" shared_tests.xml; then
          echo "❌ No async runtime tests found"
          exit 1
        fi
        echo "✅ Both runtimes tested"

    - name: Upload Shared Test Results
      if: always()
      uses: actions/upload-artifact@v3
      with:
        name: shared-test-results
        path: |
          shared_tests.xml
          shared_coverage_html/

  coverage-parity:
    name: Coverage Parity Check
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
        cache: 'pip'

    - name: Install dependencies
      run: |
        pip install -e ".[test]" coverage

    - name: LocalRuntime Coverage
      run: |
        coverage run --source=src/kailash/runtime/local.py \
          -m pytest tests/shared/runtime tests/unit/runtime/local -v
        coverage report --fail-under=${{ env.COVERAGE_THRESHOLD }} | tee local_coverage.txt
        coverage html -d local_coverage_html
        LOCAL_COV=$(grep TOTAL local_coverage.txt | awk '{print $4}' | sed 's/%//')
        echo "LOCAL_COVERAGE=$LOCAL_COV" >> $GITHUB_ENV

    - name: AsyncLocalRuntime Coverage
      run: |
        coverage erase
        coverage run --source=src/kailash/runtime/async_local.py \
          -m pytest tests/shared/runtime tests/unit/runtime/async_local -v
        coverage report --fail-under=${{ env.COVERAGE_THRESHOLD }} | tee async_coverage.txt
        coverage html -d async_coverage_html
        ASYNC_COV=$(grep TOTAL async_coverage.txt | awk '{print $4}' | sed 's/%//')
        echo "ASYNC_COVERAGE=$ASYNC_COV" >> $GITHUB_ENV

    - name: Compare Coverage
      run: |
        echo "Coverage Results:"
        echo "  LocalRuntime:      ${{ env.LOCAL_COVERAGE }}%"
        echo "  AsyncLocalRuntime: ${{ env.ASYNC_COVERAGE }}%"

        # Calculate absolute difference
        DIFF=$(python3 -c "print(abs(${{ env.LOCAL_COVERAGE }} - ${{ env.ASYNC_COVERAGE }}))")
        echo "  Difference:        $DIFF%"
        echo "  Threshold:         ${{ env.PARITY_THRESHOLD }}%"

        # Check threshold
        if (( $(python3 -c "print(int($DIFF > ${{ env.PARITY_THRESHOLD }}))") )); then
          echo "❌ Coverage parity violation!"
          exit 1
        fi

        echo "✅ Coverage parity check passed"

    - name: Upload Coverage Reports
      if: always()
      uses: actions/upload-artifact@v3
      with:
        name: coverage-reports
        path: |
          local_coverage.txt
          async_coverage.txt
          local_coverage_html/
          async_coverage_html/

  conditional-execution-parity:
    name: Conditional Execution Feature Parity
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
        cache: 'pip'

    - name: Install dependencies
      run: |
        pip install -e ".[test]"

    - name: Count Tests
      run: |
        # Shared conditional tests
        SHARED_COUNT=$(pytest tests/shared/runtime -k conditional --collect-only -q | tail -1 | awk '{print $1}')
        echo "Shared conditional tests: $SHARED_COUNT"

        # LocalRuntime-specific
        LOCAL_COUNT=$(pytest tests/unit/runtime/local -k conditional --collect-only -q | tail -1 | awk '{print $1}')
        echo "LocalRuntime-specific:    $LOCAL_COUNT"

        # AsyncLocalRuntime-specific
        ASYNC_COUNT=$(pytest tests/unit/runtime/async_local -k conditional --collect-only -q | tail -1 | awk '{print $1}')
        echo "AsyncLocalRuntime-specific: $ASYNC_COUNT"

        # Effective coverage (shared + specific)
        LOCAL_EFFECTIVE=$((SHARED_COUNT + LOCAL_COUNT))
        ASYNC_EFFECTIVE=$((SHARED_COUNT + ASYNC_COUNT))

        echo "Effective coverage:"
        echo "  LocalRuntime:      $LOCAL_EFFECTIVE tests"
        echo "  AsyncLocalRuntime: $ASYNC_EFFECTIVE tests"

        # Both must have tests
        if [ "$LOCAL_EFFECTIVE" -eq 0 ]; then
          echo "❌ No LocalRuntime conditional tests"
          exit 1
        fi

        if [ "$ASYNC_EFFECTIVE" -eq 0 ]; then
          echo "❌ No AsyncLocalRuntime conditional tests"
          exit 1
        fi

        # Calculate ratio
        RATIO=$(python3 -c "print(min($LOCAL_EFFECTIVE, $ASYNC_EFFECTIVE) / max($LOCAL_EFFECTIVE, $ASYNC_EFFECTIVE))")
        echo "Test ratio: $RATIO"

        # Check threshold
        if (( $(python3 -c "print(int($RATIO < ${{ env.TEST_RATIO_THRESHOLD }}))") )); then
          echo "❌ Test count disparity: $RATIO < ${{ env.TEST_RATIO_THRESHOLD }}"
          exit 1
        fi

        echo "✅ Conditional execution parity passed"

  integration-parity:
    name: Integration Test Parity
    runs-on: ubuntu-latest
    timeout-minutes: 30

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
        cache: 'pip'

    - name: Install dependencies
      run: |
        pip install -e ".[test]"

    - name: Run Shared Integration Tests
      env:
        TEST_DATABASE_URL: postgresql://test_user:test_pass@localhost:5432/test_db
      run: |
        pytest tests/integration/runtime/shared/ -v --tb=short

    - name: Upload Integration Results
      if: always()
      uses: actions/upload-artifact@v3
      with:
        name: integration-test-results
        path: integration_tests.xml

  parity-report:
    name: Generate Parity Report
    runs-on: ubuntu-latest
    needs: [parity-validation, shared-test-suite, coverage-parity, conditional-execution-parity]
    if: always()

    steps:
    - uses: actions/checkout@v3

    - name: Download All Artifacts
      uses: actions/download-artifact@v3

    - name: Generate Comprehensive Report
      run: |
        python tests/parity/utils/generate_parity_report.py \
          --output parity_report.md

    - name: Comment on PR
      if: github.event_name == 'pull_request'
      uses: actions/github-script@v6
      with:
        script: |
          const fs = require('fs');
          const report = fs.readFileSync('parity_report.md', 'utf8');

          github.rest.issues.createComment({
            issue_number: context.issue.number,
            owner: context.repo.owner,
            repo: context.repo.repo,
            body: report
          });

    - name: Upload Final Report
      uses: actions/upload-artifact@v3
      with:
        name: comprehensive-parity-report
        path: parity_report.md
```

---

## 9. Summary & Checklist

### 9.1 Implementation Checklist

**Phase 1: Infrastructure**
- [ ] Create `tests/shared/runtime/` directory
- [ ] Create `tests/parity/` directory
- [ ] Implement `conftest.py` with parametrization
- [ ] Implement `execute_runtime()` helper
- [ ] Document shared test patterns

**Phase 2: Parity Validation**
- [ ] Create `test_runtime_method_parity.py`
- [ ] Create `test_runtime_signature_parity.py`
- [ ] Create `test_runtime_behavior_parity.py`
- [ ] Create `test_runtime_coverage_parity.py`
- [ ] Verify all parity tests pass

**Phase 3: Shared Test Suite - Conditional Execution**
- [ ] Migrate 26 conditional tests to shared suite
- [ ] Verify AsyncLocalRuntime passes all tests
- [ ] Add async-specific conditional tests
- [ ] Achieve 20+ shared tests

**Phase 4: Shared Test Suite - Other Features**
- [ ] Enterprise features (15 tests)
- [ ] Error handling (20 tests)
- [ ] Resource management (10 tests)
- [ ] Analytics (8 tests)
- [ ] Total: 73+ shared tests

**Phase 5: CI/CD**
- [ ] Create `.github/workflows/sync-async-parity.yml`
- [ ] Create `.github/workflows/pr-checks.yml`
- [ ] Create `.github/workflows/daily-parity-check.yml`
- [ ] Set up pre-commit hooks
- [ ] Configure branch protection rules

**Phase 6: Validation**
- [ ] All parity tests pass (100%)
- [ ] Coverage ≥ 85% for both runtimes
- [ ] Coverage difference ≤ 5%
- [ ] Test count ratio ≥ 80%
- [ ] CI/CD enforces parity on every PR

### 9.2 Success Criteria

**✅ Parity Achieved When:**

1. **Method Parity**: Every LocalRuntime method exists in AsyncLocalRuntime
2. **Signature Parity**: Shared methods have identical signatures
3. **Behavior Parity**: Same inputs produce same outputs
4. **Coverage Parity**: Coverage difference ≤ 5%
5. **Test Count Parity**: Test count ratio ≥ 80%
6. **CI/CD Enforcement**: All checks pass automatically

**✅ Ongoing Success:**

1. **New features**: Automatically tested in both runtimes
2. **Regression prevention**: CI/CD blocks parity violations
3. **Quarterly audits**: Automated reports confirm parity
4. **Daily monitoring**: Dashboard tracks parity metrics

---

## 10. File References

**Strategy Documents**:
- This document: `sdk-users/3-development/testing/sync-async-parity-testing-strategy.md`
- 3-Tier Strategy: `sdk-users/3-development/testing/regression-testing-strategy.md`
- NO MOCKING Policy: `sdk-users/7-gold-standards/mock-directives-for-testing.md`

**Test Directories**:
- Shared tests: `tests/shared/runtime/`
- Parity tests: `tests/parity/`
- LocalRuntime tests: `tests/unit/runtime/local/`
- AsyncLocalRuntime tests: `tests/unit/runtime/async_local/`

**CI/CD Configuration**:
- Parity workflow: `.github/workflows/sync-async-parity.yml`
- PR checks: `.github/workflows/pr-checks.yml`
- Daily monitoring: `.github/workflows/daily-parity-check.yml`

**Implementation Files**:
- LocalRuntime: `src/kailash/runtime/local.py`
- AsyncLocalRuntime: `src/kailash/runtime/async_local.py`

---

## Appendix A: Utility Scripts

### A.1 Check Method Parity Script

```python
# tests/parity/utils/check_method_parity.py
"""
Utility script to check method parity between LocalRuntime and AsyncLocalRuntime.

Usage:
    python tests/parity/utils/check_method_parity.py
"""

import inspect
import sys
from kailash.runtime.local import LocalRuntime
from kailash.runtime.async_local import AsyncLocalRuntime


ALLOWED_ASYNC_ONLY = {
    'execute_workflow_async',
    '_execute_node_async',
    '_execute_fully_async_workflow',
    '_execute_mixed_workflow',
    '_execute_sync_node_async',
    '_execute_sync_node_in_thread',
    '_execute_sync_workflow',
    '_execute_sync_workflow_internal',
    '_prepare_async_node_inputs',
    '_prepare_sync_node_inputs',
}


def main():
    local_methods = {
        name for name in dir(LocalRuntime)
        if not name.startswith('__') and callable(getattr(LocalRuntime, name))
    }

    async_methods = {
        name for name in dir(AsyncLocalRuntime)
        if not name.startswith('__') and callable(getattr(AsyncLocalRuntime, name))
    }

    # Check for missing methods
    missing = local_methods - async_methods

    if missing:
        print("❌ PARITY VIOLATION: AsyncLocalRuntime missing methods:")
        for method in sorted(missing):
            print(f"   - {method}")
        sys.exit(1)

    # Check for undocumented async-only methods
    extra = (async_methods - local_methods) - ALLOWED_ASYNC_ONLY

    if extra:
        print("⚠️  WARNING: Undocumented async-only methods:")
        for method in sorted(extra):
            print(f"   - {method}")
        print("\nAdd these to ALLOWED_ASYNC_ONLY if intentional.")
        sys.exit(1)

    print("✅ Method parity check passed")
    print(f"   LocalRuntime:      {len(local_methods)} methods")
    print(f"   AsyncLocalRuntime: {len(async_methods)} methods")
    sys.exit(0)


if __name__ == '__main__':
    main()
```

### A.2 Generate Parity Report Script

```python
# tests/parity/utils/generate_parity_report.py
"""
Generate comprehensive parity report for sync/async runtimes.

Usage:
    python tests/parity/utils/generate_parity_report.py --output report.md
"""

import argparse
import inspect
import subprocess
from datetime import datetime
from kailash.runtime.local import LocalRuntime
from kailash.runtime.async_local import AsyncLocalRuntime


def get_method_count():
    local = len([m for m in dir(LocalRuntime) if not m.startswith('__')])
    async_ = len([m for m in dir(AsyncLocalRuntime) if not m.startswith('__')])
    return local, async_


def get_test_count():
    # Count tests
    result = subprocess.run(
        ['pytest', 'tests/shared/runtime', '--collect-only', '-q'],
        capture_output=True,
        text=True
    )
    shared = result.stdout.count('test_')

    result = subprocess.run(
        ['pytest', 'tests/unit/runtime/local', '--collect-only', '-q'],
        capture_output=True,
        text=True
    )
    local = result.stdout.count('test_')

    result = subprocess.run(
        ['pytest', 'tests/unit/runtime/async_local', '--collect-only', '-q'],
        capture_output=True,
        text=True
    )
    async_ = result.stdout.count('test_')

    return shared, local, async_


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='parity_report.md')
    args = parser.parse_args()

    local_methods, async_methods = get_method_count()
    shared_tests, local_tests, async_tests = get_test_count()

    report = f"""
# Sync/Async Parity Report

**Generated**: {datetime.now().isoformat()}

## Summary

| Metric | LocalRuntime | AsyncLocalRuntime | Status |
|--------|-------------|------------------|--------|
| Methods | {local_methods} | {async_methods} | {'✅' if local_methods <= async_methods else '❌'} |
| Specific Tests | {local_tests} | {async_tests} | {'✅' if abs(local_tests - async_tests) < 5 else '⚠️'} |
| Shared Tests | {shared_tests} | {shared_tests} | ✅ |

## Method Parity

- **LocalRuntime**: {local_methods} public methods
- **AsyncLocalRuntime**: {async_methods} public methods
- **Status**: {'✅ PASS - All LocalRuntime methods present in AsyncLocalRuntime' if local_methods <= async_methods else '❌ FAIL - Missing methods in AsyncLocalRuntime'}

## Test Coverage

### Shared Tests
{shared_tests} tests run against both runtimes (parametrized)

### Runtime-Specific Tests
- **LocalRuntime**: {local_tests} tests
- **AsyncLocalRuntime**: {async_tests} tests

### Effective Coverage
- **LocalRuntime**: {shared_tests + local_tests} total tests
- **AsyncLocalRuntime**: {shared_tests + async_tests} total tests

## Next Steps

{'No issues found - parity maintained! ✅' if local_methods <= async_methods and abs(local_tests - async_tests) < 5 else 'Address parity violations above'}
"""

    with open(args.output, 'w') as f:
        f.write(report)

    print(f"Parity report generated: {args.output}")


if __name__ == '__main__':
    main()
```

---

**END OF STRATEGY DOCUMENT**

---

**Version History**:
- v1.0.0 (2025-10-25): Initial comprehensive strategy
- Next review: 2025-11-25 (1 month)
