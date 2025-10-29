# Runtime Refactoring Roadmap
**Step-by-Step Implementation Plan**

**Version**: 1.0
**Date**: 2025-10-25
**Status**: Implementation Ready

---

## Quick Reference

### Current State
- **LocalRuntime**: 4,806 lines, 88 methods
- **AsyncLocalRuntime**: 1,011 lines, 33 methods
- **Duplication**: ~1,000 lines (basic execution)
- **Missing in Async**: ~2,200 lines (55 methods)
- **Code Reuse**: ~50%

### Target State
- **BaseRuntime**: ~500 lines (shared foundation)
- **6 Mixins**: ~2,700 lines (100% shared)
- **LocalRuntime**: ~800 lines (sync-specific only)
- **AsyncLocalRuntime**: ~800 lines (async-specific only)
- **Code Reuse**: 95%+
- **Duplication**: 0%

---

## Architecture At-a-Glance

```
┌─────────────────────────────────────────────────────────────────┐
│                         BaseRuntime                              │
│  • Shared configuration and state                                │
│  • Abstract execution interface                                  │
│  • Shared utility methods (graph analysis, node management)      │
│  • ~500 lines                                                    │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │
              ┌───────────────┴──────────────────────────┐
              │                                          │
              │         6 MIXINS (100% SHARED)           │
              │                                          │
              ├──────────────────────────────────────────┤
              │                                          │
              │  1. ValidationMixin (~300 lines)         │
              │     • Workflow validation                │
              │     • Connection contracts               │
              │     • Parameter validation               │
              │                                          │
              │  2. ParameterHandlingMixin (~300 lines)  │
              │     • Parameter processing               │
              │     • Secret management                  │
              │     • Format separation                  │
              │                                          │
              │  3. ConditionalExecutionMixin (~700)     │
              │     • SwitchNode logic                   │
              │     • Branch skipping                    │
              │     • Conditional routing                │
              │                                          │
              │  4. CycleExecutionMixin (~400 lines)     │
              │     • Cyclic workflow support            │
              │     • Convergence checking               │
              │     • Cycle validation                   │
              │                                          │
              │  5. EnterpriseFeaturesMixin (~1000)      │
              │     • Circuit breaker                    │
              │     • Retry policies                     │
              │     • Resource coordination              │
              │     • Health monitoring                  │
              │                                          │
              │  6. AnalyticsMixin (~500 lines)          │
              │     • Execution analytics                │
              │     • Performance tracking               │
              │     • Metrics collection                 │
              │                                          │
              └──────────────────────────────────────────┘
                              │
              ┌───────────────┴──────────────┐
              │                              │
┌─────────────┴──────────────┐  ┌───────────┴──────────────┐
│      LocalRuntime          │  │   AsyncLocalRuntime      │
│  (~800 lines)              │  │   (~800 lines)           │
│                            │  │                          │
│  • Sync execution only     │  │  • Async execution only  │
│  • execute()               │  │  • execute_async()       │
│  • _execute_impl()         │  │  • _execute_impl_async() │
│  • _prepare_inputs()       │  │  • _prepare_inputs_async │
└────────────────────────────┘  └──────────────────────────┘
```

---

## 5-Week Implementation Plan

### Week 1: Foundation (BaseRuntime)

#### Day 1-2: Create BaseRuntime
```bash
# File structure
src/kailash/runtime/
├── base.py                 # NEW: BaseRuntime class
├── local.py                # UPDATE: Extend BaseRuntime
├── async_local.py          # UPDATE: Extend BaseRuntime
└── mixins/                 # NEW: Mixin directory
    └── __init__.py

# Tasks
✅ Create src/kailash/runtime/base.py
   - Define BaseRuntime abstract class
   - Extract shared configuration
   - Extract shared state management
   - Define abstract methods

✅ Write BaseRuntime tests
   tests/unit/runtime/test_base_runtime.py
   - Test configuration validation
   - Test shared utilities
   - Test abstract method enforcement

# Success Criteria
- BaseRuntime class created
- All abstract methods defined
- Configuration validation works
- Tests pass
```

#### Day 3-4: Update LocalRuntime
```bash
# Tasks
✅ Update LocalRuntime to extend BaseRuntime
   - Change: class LocalRuntime(BaseRuntime)
   - Implement abstract methods
   - Remove duplicated configuration code
   - Keep all existing functionality

✅ Run existing tests
   pytest tests/integration/runtime/test_local.py -v
   pytest tests/unit/runtime/test_simple_runtime.py -v

# Success Criteria
- All existing LocalRuntime tests pass
- No breaking changes
- Backward compatibility maintained
```

#### Day 5: Update AsyncLocalRuntime
```bash
# Tasks
✅ Update AsyncLocalRuntime to extend BaseRuntime
   - Change: class AsyncLocalRuntime(BaseRuntime)
   - Implement abstract methods (async variants)
   - Remove duplicated configuration code
   - Keep all existing functionality

✅ Run existing tests
   pytest tests/integration/runtime/test_async_local.py -v
   pytest tests/integration/runtime/test_async_runtime_integration.py -v

# Success Criteria
- All existing AsyncLocalRuntime tests pass
- No breaking changes
- Backward compatibility maintained
```

---

### Week 2: Core Mixins (Validation + Parameters)

#### Day 1-2: Extract ValidationMixin
```bash
# File structure
src/kailash/runtime/mixins/
├── __init__.py
└── validation.py           # NEW: ValidationMixin

# Tasks
✅ Create ValidationMixin
   - Move validation methods from LocalRuntime
   - validate_workflow()
   - _validate_connection_contracts()
   - _generate_enhanced_validation_error()
   - _build_connection_context()
   - get_validation_metrics()
   - reset_validation_metrics()
   - _check_workflow_access()
   - _should_stop_on_error()

✅ Update LocalRuntime
   - Add ValidationMixin to inheritance
   - Remove duplicated validation methods
   - Test all validation features

✅ Update AsyncLocalRuntime
   - Add ValidationMixin to inheritance
   - Test all validation features

✅ Write mixin tests
   tests/unit/runtime/mixins/test_validation_mixin.py
   - Test each method in isolation
   - Test with minimal runtime
   - Test error cases

# Success Criteria
- ValidationMixin created with 8 methods
- LocalRuntime uses ValidationMixin
- AsyncLocalRuntime uses ValidationMixin
- All tests pass
- No duplication
```

#### Day 3-5: Extract ParameterHandlingMixin
```bash
# File structure
src/kailash/runtime/mixins/
├── validation.py
└── parameter_handling.py   # NEW: ParameterHandlingMixin

# Tasks
✅ Create ParameterHandlingMixin
   - Move parameter methods from LocalRuntime
   - _process_workflow_parameters()
   - _separate_parameter_formats()
   - _is_node_specific_format()
   - _serialize_user_context()
   - _extract_secret_requirements()

✅ Update LocalRuntime
   - Add ParameterHandlingMixin to inheritance
   - Remove duplicated parameter methods
   - Test parameter processing

✅ Update AsyncLocalRuntime
   - Add ParameterHandlingMixin to inheritance
   - Test parameter processing

✅ Write mixin tests
   tests/unit/runtime/mixins/test_parameter_handling_mixin.py
   - Test parameter processing
   - Test secret extraction
   - Test format separation

✅ Integration tests
   tests/integration/runtime/test_validation_parameter_integration.py
   - Test ValidationMixin + ParameterHandlingMixin together

# Success Criteria
- ParameterHandlingMixin created with 5 methods
- Both runtimes use ParameterHandlingMixin
- All tests pass
- No duplication
```

---

### Week 3: Execution Mixins (Conditional + Cycle)

#### Day 1-3: Extract ConditionalExecutionMixin
```bash
# File structure
src/kailash/runtime/mixins/
├── validation.py
├── parameter_handling.py
└── conditional_execution.py # NEW: ConditionalExecutionMixin

# Tasks
✅ Create ConditionalExecutionMixin
   - Move conditional methods from LocalRuntime
   - _has_conditional_patterns() (shared)
   - _should_skip_conditional_node() (shared)
   - _validate_conditional_execution_prerequisites() (shared)
   - _validate_switch_results() (shared)
   - _validate_conditional_execution_results() (shared)
   - _track_conditional_execution_performance() (shared)
   - _log_conditional_execution_failure() (shared)
   - _track_fallback_usage() (shared)
   - _execute_conditional_approach() (template method)
   - _execute_conditional_impl() (abstract - sync/async variant)

✅ Update LocalRuntime
   - Add ConditionalExecutionMixin to inheritance
   - Implement _execute_conditional_impl() (sync)
   - Remove duplicated conditional methods
   - Test conditional execution

✅ Update AsyncLocalRuntime
   - Add ConditionalExecutionMixin to inheritance
   - Implement _execute_conditional_impl() (async)
   - Test conditional execution

✅ Write mixin tests
   tests/unit/runtime/mixins/test_conditional_execution_mixin.py
   - Test pattern detection
   - Test branch skipping logic
   - Test switch validation
   - Test performance tracking

✅ Integration tests
   tests/integration/runtime/test_conditional_execution_integration.py
   - Test conditional workflows in sync runtime
   - Test conditional workflows in async runtime
   - Test parity (sync == async results)

# Success Criteria
- ConditionalExecutionMixin created with 10 methods
- 8 methods 100% shared
- 2 methods sync/async variants
- Both runtimes implement _execute_conditional_impl()
- All tests pass
- Parity maintained
```

#### Day 4-5: Extract CycleExecutionMixin
```bash
# File structure
src/kailash/runtime/mixins/
├── validation.py
├── parameter_handling.py
├── conditional_execution.py
└── cycle_execution.py       # NEW: CycleExecutionMixin

# Tasks
✅ Create CycleExecutionMixin
   - Move cycle methods from LocalRuntime
   - _workflow_has_cycles() (shared)
   - _validate_cycle_configuration() (shared)
   - _check_cycle_convergence() (shared)
   - _track_cycle_iteration() (shared)
   - _log_cycle_diagnostics() (shared)
   - _execute_cyclic_workflow() (template method)
   - _execute_cyclic_impl() (abstract - sync/async variant)

✅ Update LocalRuntime
   - Add CycleExecutionMixin to inheritance
   - Implement _execute_cyclic_impl() (sync)
   - Remove duplicated cycle methods
   - Test cyclic execution

✅ Update AsyncLocalRuntime
   - Add CycleExecutionMixin to inheritance
   - Implement _execute_cyclic_impl() (async)
   - Test cyclic execution

✅ Write mixin tests
   tests/unit/runtime/mixins/test_cycle_execution_mixin.py
   - Test cycle detection
   - Test convergence checking
   - Test iteration tracking

✅ Integration tests
   tests/integration/runtime/test_cycle_execution_integration.py
   - Test cyclic workflows in sync runtime
   - Test cyclic workflows in async runtime
   - Test parity

# Success Criteria
- CycleExecutionMixin created with 7 methods
- 5 methods 100% shared
- 2 methods sync/async variants
- Both runtimes implement _execute_cyclic_impl()
- All tests pass
```

---

### Week 4: Enterprise Mixins

#### Day 1-3: Extract EnterpriseFeaturesMixin
```bash
# File structure
src/kailash/runtime/mixins/
├── validation.py
├── parameter_handling.py
├── conditional_execution.py
├── cycle_execution.py
└── enterprise_features.py   # NEW: EnterpriseFeaturesMixin

# Tasks
✅ Create EnterpriseFeaturesMixin
   - Move enterprise methods from LocalRuntime
   - _initialize_circuit_breaker() (shared)
   - _initialize_retry_policies() (shared)
   - _initialize_resource_coordinator() (shared)
   - _initialize_health_monitor() (shared)
   - get_resource_metrics() (shared)
   - get_execution_metrics() (shared)
   - get_health_status() (shared)
   - get_health_diagnostics() (shared)
   - optimize_runtime_performance() (shared)
   - get_performance_report() (shared)
   - get_retry_policy_engine() (shared)
   - get_retry_analytics() (shared)
   - register_retry_strategy() (shared)
   - add_retriable_exception() (shared)
   - reset_retry_metrics() (shared)

✅ Update LocalRuntime
   - Add EnterpriseFeaturesMixin to inheritance
   - Remove duplicated enterprise methods
   - Test enterprise features

✅ Update AsyncLocalRuntime
   - Add EnterpriseFeaturesMixin to inheritance
   - Test enterprise features

✅ Write mixin tests
   tests/unit/runtime/mixins/test_enterprise_features_mixin.py
   - Test circuit breaker initialization
   - Test retry policy registration
   - Test health monitoring
   - Test resource metrics

# Success Criteria
- EnterpriseFeaturesMixin created with 15 methods
- All 15 methods 100% shared
- No sync/async variants needed
- Both runtimes use same enterprise features
- All tests pass
```

#### Day 4-5: Extract AnalyticsMixin
```bash
# File structure
src/kailash/runtime/mixins/
├── validation.py
├── parameter_handling.py
├── conditional_execution.py
├── cycle_execution.py
├── enterprise_features.py
└── analytics.py             # NEW: AnalyticsMixin

# Tasks
✅ Create AnalyticsMixin
   - Move analytics methods from LocalRuntime
   - get_execution_analytics() (shared)
   - record_execution_performance() (shared)
   - clear_analytics_data() (shared)
   - get_execution_plan_cached() (shared)
   - _create_execution_plan_cache_key() (shared)
   - _record_execution_metrics() (shared)
   - get_performance_report() (shared)
   - set_performance_monitoring() (shared)
   - get_execution_path_debug_info() (shared)
   - get_runtime_metrics() (shared)
   - _track_node_execution() (shared)
   - _compute_execution_statistics() (shared)

✅ Update LocalRuntime
   - Add AnalyticsMixin to inheritance
   - Remove duplicated analytics methods
   - Test analytics

✅ Update AsyncLocalRuntime
   - Add AnalyticsMixin to inheritance
   - Test analytics

✅ Write mixin tests
   tests/unit/runtime/mixins/test_analytics_mixin.py
   - Test analytics collection
   - Test performance tracking
   - Test metrics computation

# Success Criteria
- AnalyticsMixin created with 12 methods
- All 12 methods 100% shared
- Both runtimes use same analytics
- All tests pass
```

---

### Week 5: Integration and Testing

#### Day 1-2: Integration Testing
```bash
# Tasks
✅ Test all mixin combinations
   tests/integration/runtime/test_all_mixins_integration.py
   - Test all 6 mixins together
   - Test LocalRuntime with all mixins
   - Test AsyncLocalRuntime with all mixins
   - Test complex workflows

✅ Test parity
   tests/integration/runtime/test_sync_async_parity.py
   - Test that sync and async produce identical results
   - Test all execution modes (normal, conditional, cyclic)
   - Test all enterprise features
   - Test all analytics

✅ Test backward compatibility
   tests/integration/runtime/test_backward_compatibility.py
   - Run all existing tests
   - Ensure no breaking changes
   - Verify existing workflows work

# Success Criteria
- All integration tests pass
- Parity maintained (sync == async)
- Backward compatibility 100%
```

#### Day 3: Performance Testing
```bash
# Tasks
✅ Benchmark before/after
   tests/performance/test_runtime_performance.py
   - Measure execution time before refactoring
   - Measure execution time after refactoring
   - Ensure no regression (should be same or better)

✅ Memory profiling
   - Profile memory usage before/after
   - Ensure no memory leaks

# Success Criteria
- No performance regression
- Memory usage same or better
```

#### Day 4: Documentation
```bash
# Tasks
✅ Update architecture docs
   docs/architecture/runtime-architecture.md
   - Document new mixin architecture
   - Document BaseRuntime responsibilities
   - Document each mixin's purpose

✅ Update API docs
   docs/api/runtime.md
   - Update LocalRuntime docs
   - Update AsyncLocalRuntime docs
   - Add mixin reference

✅ Create migration guide
   docs/migration/runtime-refactoring-migration.md
   - Guide for users (no changes needed)
   - Guide for contributors (internal changes)

# Success Criteria
- All documentation updated
- Migration guide complete
- Examples updated
```

#### Day 5: Code Review and Cleanup
```bash
# Tasks
✅ Final review
   - Review all mixin implementations
   - Review LocalRuntime
   - Review AsyncLocalRuntime
   - Review tests

✅ Remove deprecated code
   - Remove commented-out code
   - Remove unused imports
   - Clean up formatting

✅ Update CHANGELOG
   - Document refactoring
   - List new mixins
   - Note backward compatibility

✅ Merge to main
   - Create PR
   - Get approval
   - Merge

# Success Criteria
- Code review approved
- All tests pass in CI/CD
- Merged to main
```

---

## Testing Strategy

### Unit Tests (Mixin Isolation)
```bash
# Test each mixin independently
tests/unit/runtime/mixins/
├── test_validation_mixin.py
├── test_parameter_handling_mixin.py
├── test_conditional_execution_mixin.py
├── test_cycle_execution_mixin.py
├── test_enterprise_features_mixin.py
└── test_analytics_mixin.py

# Strategy
1. Create minimal runtime with only one mixin
2. Test each method independently
3. Mock dependencies
4. Test error cases
```

### Integration Tests (Mixin Combinations)
```bash
# Test mixins working together
tests/integration/runtime/
├── test_validation_parameter_integration.py
├── test_conditional_cycle_integration.py
├── test_enterprise_analytics_integration.py
└── test_all_mixins_integration.py

# Strategy
1. Create real runtime with multiple mixins
2. Test mixin interactions
3. Test complex workflows
4. Test error propagation
```

### Parity Tests (Sync == Async)
```bash
# Test that LocalRuntime and AsyncLocalRuntime produce identical results
tests/integration/runtime/test_sync_async_parity.py

# Strategy
1. Run same workflow in both runtimes
2. Compare results (must be identical)
3. Compare metrics (must be identical)
4. Test all execution modes
```

### Performance Tests
```bash
# Ensure no performance regression
tests/performance/test_runtime_performance.py

# Strategy
1. Benchmark before refactoring
2. Benchmark after refactoring
3. Compare (should be same or better)
```

---

## CI/CD Integration

### GitHub Actions Workflow
```yaml
name: Runtime Refactoring CI

on:
  pull_request:
    paths:
      - 'src/kailash/runtime/**'

jobs:
  test-mixins:
    name: Test Mixins
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: pip install -e .
      - run: pytest tests/unit/runtime/mixins/ -v

  test-integration:
    name: Test Integration
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: pip install -e .
      - run: pytest tests/integration/runtime/ -v

  test-parity:
    name: Test Parity
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: pip install -e .
      - run: pytest tests/integration/runtime/test_sync_async_parity.py -v

  check-duplication:
    name: Check Duplication
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: python scripts/check_runtime_duplication.py

  performance:
    name: Performance Test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: pip install -e .
      - run: pytest tests/performance/test_runtime_performance.py -v
```

---

## Success Metrics

### Code Quality Metrics
```
✅ Before Refactoring:
- LocalRuntime: 4,806 lines
- AsyncLocalRuntime: 1,011 lines
- Duplication: ~1,000 lines
- Code Reuse: ~50%

✅ After Refactoring:
- BaseRuntime: ~500 lines
- 6 Mixins: ~2,700 lines (100% shared)
- LocalRuntime: ~800 lines (sync-specific only)
- AsyncLocalRuntime: ~800 lines (async-specific only)
- Duplication: 0 lines
- Code Reuse: 95%+

✅ Reduction:
- Total lines: 5,817 → 4,800 (17% reduction)
- Duplication: 1,000 → 0 (100% elimination)
- Maintainability: Much improved (changes in one place)
```

### Testing Metrics
```
✅ Test Coverage:
- Mixin unit tests: 100%
- Integration tests: 100%
- Parity tests: 100%
- Performance tests: 100%

✅ Test Counts:
- Before: ~150 tests
- After: ~200 tests (50 new mixin tests)
```

### Development Metrics
```
✅ Development Speed:
- Before: Change requires updating 2 files (LocalRuntime + AsyncLocalRuntime)
- After: Change requires updating 1 mixin (automatically applies to both)
- Speed improvement: 2x faster

✅ Bug Risk:
- Before: High (easy to miss updating one runtime)
- After: Low (change in one place, tested in isolation)
```

---

## Risk Mitigation

### Risk 1: Breaking Changes
```
Mitigation:
✅ Keep public API identical
✅ Run all existing tests after each change
✅ Add backward compatibility tests
✅ Document any unavoidable changes
```

### Risk 2: Performance Regression
```
Mitigation:
✅ Benchmark before/after
✅ Profile memory usage
✅ Test with real workflows
✅ Optimize if needed
```

### Risk 3: Test Failures
```
Mitigation:
✅ Test after each mixin extraction
✅ Add parity tests
✅ Add integration tests
✅ Fix immediately (don't accumulate)
```

### Risk 4: Scope Creep
```
Mitigation:
✅ Stick to refactoring (no new features)
✅ Follow 5-week timeline strictly
✅ Defer non-critical changes
✅ Focus on duplication elimination
```

---

## Communication Plan

### Week 1: Kickoff
```
✅ Send email to team
   - Explain refactoring goals
   - Share timeline
   - Request code freeze on runtime files

✅ Create GitHub project
   - Track progress
   - Link issues
   - Update status daily
```

### Week 2-4: Progress Updates
```
✅ Daily standups
   - What was completed yesterday
   - What will be completed today
   - Any blockers

✅ Weekly demos
   - Show mixin extraction progress
   - Demonstrate parity tests
   - Address concerns
```

### Week 5: Launch
```
✅ Final demo
   - Show completed refactoring
   - Demonstrate parity
   - Show metrics improvement

✅ Migration guide
   - Send to all developers
   - Answer questions
   - Provide support
```

---

## Rollback Plan

### If Something Goes Wrong
```
✅ Immediate Rollback:
   1. Revert PR
   2. Return to main branch
   3. Investigate issue
   4. Fix and retry

✅ Partial Rollback:
   1. Keep completed mixins
   2. Revert problematic mixin
   3. Fix issue
   4. Re-apply

✅ Full Rollback:
   1. Revert all changes
   2. Return to original LocalRuntime/AsyncLocalRuntime
   3. Postmortem analysis
   4. Revise plan
```

---

## Post-Launch

### Week 6: Monitoring
```
✅ Monitor production
   - Watch for errors
   - Check performance
   - Gather feedback

✅ Address issues
   - Fix bugs immediately
   - Optimize if needed
   - Update docs
```

### Week 7+: Optimization
```
✅ Identify optimization opportunities
   - Profile performance
   - Identify bottlenecks
   - Optimize hot paths

✅ Add new features
   - Build on mixin architecture
   - Add new mixins as needed
   - Maintain parity
```

---

**End of Roadmap**

This roadmap provides a week-by-week, day-by-day plan for implementing the mixin architecture. Follow this plan strictly to ensure successful refactoring with zero duplication and 100% parity.
