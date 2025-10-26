# Runtime Refactoring Quick Reference
**Developer's Cheat Sheet**

**Version**: 1.0
**Date**: 2025-10-25

---

## TL;DR

**Goal**: Eliminate 2,200+ lines of duplication between LocalRuntime and AsyncLocalRuntime by extracting shared logic into mixins.

**Approach**: Mixin-based architecture with 95%+ code reuse.

**Timeline**: 5 weeks

**Breaking Changes**: None (internal refactoring only)

---

## Architecture Overview

### Before Refactoring
```
LocalRuntime (4,806 lines)
├── execute()
├── _validate_workflow()
├── _process_parameters()
├── _execute_conditional()
├── _execute_cyclic()
├── _initialize_circuit_breaker()
├── get_health_status()
└── ... (88 methods total)

AsyncLocalRuntime (1,011 lines)
├── execute_async()
├── _execute_workflow_async()
└── ... (33 methods total, missing 55 from LocalRuntime)

❌ Problem: 1,000+ lines duplicated, 2,200 lines missing in async
```

### After Refactoring
```
BaseRuntime (500 lines)
├── Shared configuration
├── Shared state management
├── Shared utilities (graph analysis)
└── Abstract methods (sync/async variants)

6 Mixins (2,700 lines, 100% shared)
├── ValidationMixin (300 lines)
├── ParameterHandlingMixin (300 lines)
├── ConditionalExecutionMixin (700 lines)
├── CycleExecutionMixin (400 lines)
├── EnterpriseFeaturesMixin (1000 lines)
└── AnalyticsMixin (500 lines)

LocalRuntime (800 lines, sync-specific only)
├── Extends: BaseRuntime + all 6 mixins
├── execute() (sync)
└── _execute_workflow_impl() (sync)

AsyncLocalRuntime (800 lines, async-specific only)
├── Extends: BaseRuntime + all 6 mixins
├── execute_async() (async)
└── _execute_workflow_impl() (async)

✅ Solution: 0 duplication, 95%+ code reuse, 100% parity
```

---

## Mixin Responsibilities

### 1. ValidationMixin (~300 lines, 8 methods)
**Purpose**: Workflow and parameter validation

**Methods** (all 100% shared):
- `validate_workflow()` - Validate workflow structure
- `_validate_connection_contracts()` - Validate connection contracts
- `_generate_enhanced_validation_error()` - Generate error messages
- `_build_connection_context()` - Build connection context
- `get_validation_metrics()` - Get validation metrics
- `reset_validation_metrics()` - Reset metrics
- `_check_workflow_access()` - Check access control
- `_should_stop_on_error()` - Check error handling policy

**Why 100% shared**: Pure validation logic, no I/O operations

---

### 2. ParameterHandlingMixin (~300 lines, 5 methods)
**Purpose**: Parameter processing and secret management

**Methods** (all 100% shared):
- `_process_workflow_parameters()` - Process workflow parameters
- `_separate_parameter_formats()` - Separate node-specific vs global params
- `_is_node_specific_format()` - Check parameter format
- `_serialize_user_context()` - Serialize user context
- `_extract_secret_requirements()` - Extract secret requirements

**Why 100% shared**: Pure transformation logic, no I/O operations

---

### 3. ConditionalExecutionMixin (~700 lines, 10 methods)
**Purpose**: Conditional routing and SwitchNode logic

**Shared Methods** (8 methods, 100% shared):
- `_has_conditional_patterns()` - Detect conditional patterns
- `_should_skip_conditional_node()` - Determine if node should skip
- `_validate_conditional_execution_prerequisites()` - Validate prerequisites
- `_validate_switch_results()` - Validate switch outputs
- `_validate_conditional_execution_results()` - Validate execution results
- `_track_conditional_execution_performance()` - Track performance
- `_log_conditional_execution_failure()` - Log failures
- `_track_fallback_usage()` - Track fallback patterns

**Split Methods** (2 methods, sync/async variants):
- `_execute_conditional_approach()` - Template method (shared logic + delegates)
- `_execute_conditional_impl()` - Abstract method (implemented by sync/async)

**Why split**: Execution involves I/O, but validation/tracking is pure logic

---

### 4. CycleExecutionMixin (~400 lines, 7 methods)
**Purpose**: Cyclic workflow execution and convergence

**Shared Methods** (5 methods, 100% shared):
- `_workflow_has_cycles()` - Detect cycles in workflow
- `_validate_cycle_configuration()` - Validate cycle config
- `_check_cycle_convergence()` - Check convergence criteria
- `_track_cycle_iteration()` - Track iteration metrics
- `_log_cycle_diagnostics()` - Log diagnostics

**Split Methods** (2 methods, sync/async variants):
- `_execute_cyclic_workflow()` - Template method (shared logic + delegates)
- `_execute_cyclic_impl()` - Abstract method (implemented by sync/async)

**Why split**: Execution involves I/O, but validation/tracking is pure logic

---

### 5. EnterpriseFeaturesMixin (~1000 lines, 15 methods)
**Purpose**: Circuit breaker, retry policies, health monitoring

**Methods** (all 100% shared):
- `_initialize_circuit_breaker()` - Setup circuit breaker
- `_initialize_retry_policies()` - Setup retry policies
- `_initialize_resource_coordinator()` - Setup resource coordination
- `_initialize_health_monitor()` - Setup health monitoring
- `get_resource_metrics()` - Get resource metrics
- `get_execution_metrics()` - Get execution metrics
- `get_health_status()` - Get health status
- `get_health_diagnostics()` - Get health diagnostics
- `optimize_runtime_performance()` - Optimize performance
- `get_performance_report()` - Get performance report
- `get_retry_policy_engine()` - Get retry policy engine
- `get_retry_analytics()` - Get retry analytics
- `register_retry_strategy()` - Register retry strategy
- `add_retriable_exception()` - Add retriable exception
- `reset_retry_metrics()` - Reset retry metrics

**Why 100% shared**: State management and configuration, no I/O during execution

---

### 6. AnalyticsMixin (~500 lines, 12 methods)
**Purpose**: Execution analytics and performance tracking

**Methods** (all 100% shared):
- `get_execution_analytics()` - Get execution analytics
- `record_execution_performance()` - Record performance metrics
- `clear_analytics_data()` - Clear analytics
- `get_execution_plan_cached()` - Get cached execution plan
- `_create_execution_plan_cache_key()` - Create cache key
- `_record_execution_metrics()` - Record metrics
- `get_performance_report()` - Get performance report
- `set_performance_monitoring()` - Enable/disable monitoring
- `get_execution_path_debug_info()` - Get debug info
- `get_runtime_metrics()` - Get runtime metrics
- `_track_node_execution()` - Track node execution
- `_compute_execution_statistics()` - Compute statistics

**Why 100% shared**: Metric collection and computation, no I/O

---

## Pattern: Template Method

**Used in**: ConditionalExecutionMixin, CycleExecutionMixin

**Concept**: Shared logic in mixin, execution delegated to concrete class

**Example**:
```python
# In ConditionalExecutionMixin
class ConditionalExecutionMixin:
    def _execute_conditional_approach(self, workflow, inputs):
        """Template method (shared logic)."""
        # Shared: Validate prerequisites
        if not self._validate_conditional_execution_prerequisites(workflow):
            return self._execute_workflow_impl(workflow, inputs)

        # Shared: Detect patterns
        has_patterns = self._has_conditional_patterns(workflow)

        # DELEGATE to sync/async variant
        results = self._execute_conditional_impl(workflow, inputs)

        # Shared: Validate results
        is_valid, error = self._validate_conditional_execution_results(workflow, results)
        if not is_valid:
            raise WorkflowExecutionError(error)

        # Shared: Track performance
        self._track_conditional_execution_performance(...)

        return results

    @abstractmethod
    def _execute_conditional_impl(self, workflow, inputs):
        """Sync/async variant (implemented by concrete class)."""
        pass


# In LocalRuntime (sync)
class LocalRuntime(ConditionalExecutionMixin):
    def _execute_conditional_impl(self, workflow, inputs):
        """Sync implementation."""
        # Sync-specific execution logic
        return self._execute_sync(workflow, inputs)


# In AsyncLocalRuntime (async)
class AsyncLocalRuntime(ConditionalExecutionMixin):
    async def _execute_conditional_impl(self, workflow, inputs):
        """Async implementation."""
        # Async-specific execution logic
        return await self._execute_async(workflow, inputs)
```

---

## Decision Matrix: Shared vs Split

| Method Type | Shared? | Reason | Example |
|-------------|---------|--------|---------|
| **Pure Logic** | ✅ Yes | No I/O, no async needed | `_has_conditional_patterns()` |
| **Validation** | ✅ Yes | Pure logic, no I/O | `_validate_switch_results()` |
| **Tracking/Metrics** | ✅ Yes | State updates, no I/O | `_track_performance()` |
| **Graph Analysis** | ✅ Yes | Pure logic, no I/O | `_workflow_has_cycles()` |
| **Configuration** | ✅ Yes | State management, no I/O | `_initialize_circuit_breaker()` |
| **Execution (I/O)** | ❌ No | I/O operations differ | `_execute_workflow_impl()` |
| **Node Execution** | ❌ No | Async nodes need await | `_execute_node_impl()` |

**Rule of Thumb**: If it doesn't do I/O or call async methods, it's 100% shared.

---

## Code Examples

### Example 1: Using ValidationMixin

```python
# Before refactoring (LocalRuntime)
class LocalRuntime:
    def execute(self, workflow, parameters=None):
        # Validation logic (500 lines, duplicated in AsyncLocalRuntime)
        errors = []
        if not self.enable_cycles:
            try:
                nx.find_cycle(workflow.graph)
                errors.append("Workflow contains cycles")
            except nx.NetworkXNoCycle:
                pass
        # ... 495 more lines of validation ...

        if errors and self.connection_validation == "strict":
            raise WorkflowValidationError(errors)

        # Execute workflow
        return self._execute_workflow_impl(workflow, parameters)


# After refactoring (LocalRuntime)
class LocalRuntime(BaseRuntime, ValidationMixin, ...):
    def execute(self, workflow, parameters=None):
        # Validation logic now in ValidationMixin (shared with AsyncLocalRuntime)
        errors = self.validate_workflow(workflow)  # From ValidationMixin

        if errors and self.connection_validation == "strict":
            raise WorkflowValidationError(errors)

        # Execute workflow
        return self._execute_workflow_impl(workflow, parameters)


# AsyncLocalRuntime gets validation for free!
class AsyncLocalRuntime(BaseRuntime, ValidationMixin, ...):
    async def execute_async(self, workflow, parameters=None):
        # SAME validation logic (from ValidationMixin)
        errors = self.validate_workflow(workflow)  # From ValidationMixin

        if errors and self.connection_validation == "strict":
            raise WorkflowValidationError(errors)

        # Execute workflow (async variant)
        return await self._execute_workflow_impl(workflow, parameters)
```

### Example 2: Using ConditionalExecutionMixin (Template Method)

```python
# In ConditionalExecutionMixin
class ConditionalExecutionMixin:
    def _has_conditional_patterns(self, workflow):
        """Shared logic - pure analysis, no I/O."""
        for node_id, node_instance in workflow._node_instances.items():
            if type(node_instance).__name__ == "SwitchNode":
                return True
        return False

    def _execute_conditional_approach(self, workflow, inputs):
        """Template method - shared validation + delegates execution."""
        # Shared: Detect patterns
        if not self._has_conditional_patterns(workflow):
            # Fallback to regular execution
            return self._execute_workflow_impl(workflow, inputs)

        # DELEGATE to sync/async variant
        results = self._execute_conditional_impl(workflow, inputs)

        # Shared: Validate results
        is_valid, error = self._validate_conditional_execution_results(workflow, results)
        if not is_valid:
            raise WorkflowExecutionError(error)

        return results

    @abstractmethod
    def _execute_conditional_impl(self, workflow, inputs):
        """Abstract - implemented by sync/async."""
        pass


# LocalRuntime (sync)
class LocalRuntime(ConditionalExecutionMixin):
    def _execute_conditional_impl(self, workflow, inputs):
        """Sync implementation."""
        # Sync-specific conditional execution
        for node_id in execution_order:
            if self._should_skip_conditional_node(workflow, node_id, inputs, executed_nodes):
                continue
            result = self._execute_node_impl(workflow, node_id, inputs)  # Sync
            results[node_id] = result
        return results


# AsyncLocalRuntime (async)
class AsyncLocalRuntime(ConditionalExecutionMixin):
    async def _execute_conditional_impl(self, workflow, inputs):
        """Async implementation."""
        # Async-specific conditional execution
        for node_id in execution_order:
            if self._should_skip_conditional_node(workflow, node_id, inputs, executed_nodes):
                continue
            result = await self._execute_node_impl(workflow, node_id, inputs)  # Async
            results[node_id] = result
        return results
```

---

## Testing Strategy

### 1. Mixin Isolation Tests
**Goal**: Test each mixin independently

```python
# tests/unit/runtime/mixins/test_validation_mixin.py

class MinimalRuntimeWithValidation(ValidationMixin, BaseRuntime):
    """Minimal runtime for testing ValidationMixin in isolation."""
    def __init__(self, **kwargs):
        BaseRuntime.__init__(self, **kwargs)
        ValidationMixin.__init__(self)

    def _execute_workflow_impl(self, workflow, inputs):
        pass  # Not needed for validation tests


def test_validate_workflow_detects_cycles():
    """Test cycle detection in workflow validation."""
    runtime = MinimalRuntimeWithValidation(enable_cycles=False)

    # Create workflow with cycle
    workflow = create_cyclic_workflow()

    # Test validation
    errors = runtime.validate_workflow(workflow)

    assert len(errors) == 1
    assert "cycle" in errors[0].lower()
```

### 2. Integration Tests
**Goal**: Test mixins working together

```python
# tests/integration/runtime/test_mixin_integration.py

def test_validation_and_parameter_mixins():
    """Test ValidationMixin + ParameterHandlingMixin together."""
    runtime = LocalRuntime(connection_validation="strict")

    workflow = create_workflow_with_parameters()

    # Should validate workflow AND process parameters
    results, run_id = runtime.execute(
        workflow, parameters={"node1": {"param": "value"}}
    )

    assert results is not None
```

### 3. Parity Tests
**Goal**: Ensure LocalRuntime and AsyncLocalRuntime produce identical results

```python
# tests/integration/runtime/test_sync_async_parity.py

def test_execution_parity():
    """Test that sync and async produce identical results."""
    workflow = create_test_workflow()
    parameters = {"input": "data"}

    # Execute in sync runtime
    sync_runtime = LocalRuntime()
    sync_results, _ = sync_runtime.execute(workflow, parameters=parameters)

    # Execute in async runtime
    async_runtime = AsyncLocalRuntime()
    async_results, _ = asyncio.run(
        async_runtime.execute_async(workflow, parameters=parameters)
    )

    # Verify identical results
    assert sync_results == async_results
```

---

## Common Patterns

### Pattern 1: Shared Helper + Sync/Async Wrapper

**Problem**: Need to share logic but also support sync/async I/O

**Solution**: Extract pure logic to shared helper, sync/async wrappers call it

```python
# Shared helper (100% shared)
class ParameterHandlingMixin:
    def _extract_connection_mapping(self, edge_data):
        """Pure logic - 100% shared."""
        if "mapping" in edge_data:
            return edge_data["mapping"]
        elif "connections" in edge_data:
            return self._convert_legacy_format(edge_data["connections"])
        else:
            return {"result": "input"}


# Sync wrapper
class LocalRuntime(ParameterHandlingMixin):
    def _prepare_node_inputs_impl(self, workflow, node_id, node_outputs, inputs):
        """Sync variant - uses shared helper."""
        for predecessor in workflow.graph.predecessors(node_id):
            edge_data = self.get_edge_data(workflow, predecessor, node_id)

            # Use shared helper (100% same as async!)
            mapping = self._extract_connection_mapping(edge_data)

            # Apply mapping (sync)
            for source_path, target_param in mapping.items():
                inputs[target_param] = node_outputs[predecessor][source_path]

        return inputs


# Async wrapper
class AsyncLocalRuntime(ParameterHandlingMixin):
    async def _prepare_node_inputs_impl(self, workflow, node_id, node_outputs, inputs):
        """Async variant - uses SAME shared helper."""
        for predecessor in workflow.graph.predecessors(node_id):
            edge_data = self.get_edge_data(workflow, predecessor, node_id)

            # Use shared helper (100% same as sync!)
            mapping = self._extract_connection_mapping(edge_data)

            # Apply mapping (async - but logic is same)
            for source_path, target_param in mapping.items():
                inputs[target_param] = node_outputs[predecessor][source_path]

        return inputs
```

### Pattern 2: Template Method for Complex Flows

**Problem**: Complex workflow with shared validation + split execution

**Solution**: Template method in mixin, abstract implementation in concrete class

```python
# In mixin
class ConditionalExecutionMixin:
    def _execute_conditional_approach(self, workflow, inputs):
        """Template method (shared structure, delegated execution)."""
        # Shared: Validate
        if not self._validate_conditional_execution_prerequisites(workflow):
            return self._execute_workflow_impl(workflow, inputs)

        # Delegate: Execute
        results = self._execute_conditional_impl(workflow, inputs)

        # Shared: Validate results
        is_valid, error = self._validate_conditional_execution_results(workflow, results)
        if not is_valid:
            raise WorkflowExecutionError(error)

        # Shared: Track
        self._track_conditional_execution_performance(...)

        return results

    @abstractmethod
    def _execute_conditional_impl(self, workflow, inputs):
        pass


# In concrete classes
class LocalRuntime(ConditionalExecutionMixin):
    def _execute_conditional_impl(self, workflow, inputs):
        """Sync implementation."""
        # Sync-specific logic
        pass


class AsyncLocalRuntime(ConditionalExecutionMixin):
    async def _execute_conditional_impl(self, workflow, inputs):
        """Async implementation."""
        # Async-specific logic
        pass
```

---

## Migration Checklist

### For Each Mixin Extraction

```
✅ Step 1: Create Mixin File
   □ Create src/kailash/runtime/mixins/{mixin_name}.py
   □ Define mixin class
   □ Add docstring (purpose, methods, shared vs split)

✅ Step 2: Extract Methods
   □ Copy methods from LocalRuntime
   □ Identify shared vs split methods
   □ Extract shared helpers
   □ Define abstract methods for split

✅ Step 3: Update LocalRuntime
   □ Add mixin to inheritance
   □ Remove duplicated methods
   □ Implement abstract methods (sync)
   □ Test all features

✅ Step 4: Update AsyncLocalRuntime
   □ Add mixin to inheritance
   □ Remove duplicated methods (if any)
   □ Implement abstract methods (async)
   □ Test all features

✅ Step 5: Write Tests
   □ Create tests/unit/runtime/mixins/test_{mixin_name}.py
   □ Test each method in isolation
   □ Test error cases
   □ Test edge cases

✅ Step 6: Integration Tests
   □ Test mixin with LocalRuntime
   □ Test mixin with AsyncLocalRuntime
   □ Test mixin combinations
   □ Test parity (sync == async)

✅ Step 7: Run All Tests
   □ pytest tests/unit/runtime/mixins/ -v
   □ pytest tests/integration/runtime/ -v
   □ pytest tests/integration/runtime/test_sync_async_parity.py -v

✅ Step 8: Verify
   □ No duplication
   □ Backward compatibility maintained
   □ All tests pass
   □ Parity maintained
```

---

## Common Pitfalls

### Pitfall 1: Forgetting to Initialize Mixin
```python
# ❌ WRONG
class LocalRuntime(BaseRuntime, ValidationMixin):
    def __init__(self, **kwargs):
        BaseRuntime.__init__(self, **kwargs)
        # Missing: ValidationMixin.__init__(self)

# ✅ CORRECT
class LocalRuntime(BaseRuntime, ValidationMixin):
    def __init__(self, **kwargs):
        BaseRuntime.__init__(self, **kwargs)
        ValidationMixin.__init__(self)  # Initialize mixin!
```

### Pitfall 2: Mixing Sync/Async in Shared Method
```python
# ❌ WRONG - Async in shared method
class ConditionalExecutionMixin:
    async def _has_conditional_patterns(self, workflow):  # ❌ async in shared method!
        for node_id in workflow._node_instances:
            if await self._check_node_async(node_id):  # ❌ async call
                return True
        return False

# ✅ CORRECT - Pure logic, no async
class ConditionalExecutionMixin:
    def _has_conditional_patterns(self, workflow):  # ✅ No async
        for node_id, node_instance in workflow._node_instances.items():
            if type(node_instance).__name__ == "SwitchNode":  # ✅ Pure logic
                return True
        return False
```

### Pitfall 3: Not Using Template Method for Complex Flows
```python
# ❌ WRONG - Duplicating validation logic
class LocalRuntime:
    def _execute_conditional(self, workflow, inputs):
        # Validation logic (duplicated)
        if not self._validate_prerequisites(workflow):
            return self._execute_normal(workflow, inputs)

        # Execution
        return self._do_conditional_execution(workflow, inputs)

class AsyncLocalRuntime:
    async def _execute_conditional(self, workflow, inputs):
        # Validation logic (duplicated!) ❌
        if not self._validate_prerequisites(workflow):
            return await self._execute_normal(workflow, inputs)

        # Execution
        return await self._do_conditional_execution(workflow, inputs)

# ✅ CORRECT - Template method in mixin
class ConditionalExecutionMixin:
    def _execute_conditional_approach(self, workflow, inputs):
        # Shared validation (no duplication)
        if not self._validate_prerequisites(workflow):
            return self._execute_workflow_impl(workflow, inputs)

        # Delegate to sync/async
        return self._execute_conditional_impl(workflow, inputs)

    @abstractmethod
    def _execute_conditional_impl(self, workflow, inputs):
        pass

class LocalRuntime(ConditionalExecutionMixin):
    def _execute_conditional_impl(self, workflow, inputs):
        # Sync execution only
        return self._do_conditional_execution(workflow, inputs)

class AsyncLocalRuntime(ConditionalExecutionMixin):
    async def _execute_conditional_impl(self, workflow, inputs):
        # Async execution only
        return await self._do_conditional_execution(workflow, inputs)
```

---

## Quick Commands

### Run Mixin Tests
```bash
# Test all mixins
pytest tests/unit/runtime/mixins/ -v

# Test specific mixin
pytest tests/unit/runtime/mixins/test_validation_mixin.py -v

# Test with coverage
pytest tests/unit/runtime/mixins/ --cov=src/kailash/runtime/mixins --cov-report=term-missing
```

### Run Integration Tests
```bash
# Test all integrations
pytest tests/integration/runtime/ -v

# Test parity
pytest tests/integration/runtime/test_sync_async_parity.py -v

# Test specific integration
pytest tests/integration/runtime/test_mixin_integration.py -v
```

### Check Duplication
```bash
# Check for code duplication
python scripts/check_runtime_duplication.py

# Check mixin usage
python scripts/verify_mixin_usage.py
```

### Run All Tests
```bash
# Full test suite
pytest tests/unit/runtime/ tests/integration/runtime/ -v

# With coverage
pytest tests/unit/runtime/ tests/integration/runtime/ \
  --cov=src/kailash/runtime \
  --cov-report=html
```

---

## Support

### Questions?
- **Architecture**: See `docs/runtime-refactoring-architecture.md`
- **Roadmap**: See `docs/runtime-refactoring-roadmap.md`
- **Issues**: GitHub Issues
- **Slack**: #runtime-refactoring

### Need Help?
- **Testing**: Contact testing team
- **Code Review**: Tag @runtime-reviewers
- **Debugging**: Check existing tests for patterns

---

**End of Quick Reference**

This guide provides everything you need to understand and implement the mixin architecture. Keep this handy during development!
