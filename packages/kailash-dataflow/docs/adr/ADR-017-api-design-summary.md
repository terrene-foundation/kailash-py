# ADR-017: Test Mode API Design Summary

## Executive Summary

This document provides a **concise summary** of the test mode API design for DataFlow async testing improvements (ADR-017). For complete API specifications, see `ADR-017-test-mode-api-spec.md`.

---

## Key Design Decisions

### 1. Three-Level Test Mode Control

**Decision**: Provide three ways to enable test mode, prioritized in order:

1. **Explicit parameter** (highest priority)
   ```python
   db = DataFlow("postgresql://...", test_mode=True)  # Force enable
   ```

2. **Global class method** (medium priority)
   ```python
   DataFlow.enable_test_mode()  # All instances use test mode
   db = DataFlow("postgresql://...")
   ```

3. **Auto-detection** (lowest priority, default)
   ```python
   db = DataFlow("postgresql://...")  # Detects pytest automatically
   ```

**Rationale**:
- Flexibility: Developers choose the pattern that fits their workflow
- Backward compatible: Auto-detection works without code changes
- Explicit control: Override auto-detection when needed

---

### 2. Graceful Degradation for Cleanup

**Decision**: All cleanup methods return metrics instead of raising exceptions.

**API Pattern**:
```python
metrics = await db.cleanup_stale_pools()
# Always returns dict with:
# - 'stale_pools_cleaned': int
# - 'cleanup_failures': int
# - 'cleanup_errors': List[str]
```

**Rationale**:
- Test teardown should never fail due to cleanup issues
- Metrics provide visibility for debugging
- Partial cleanup is better than no cleanup

---

### 3. Opt-In Aggressive Cleanup

**Decision**: Aggressive cleanup is opt-in via `test_mode_aggressive_cleanup` parameter.

```python
# Conservative (default)
db = DataFlow("postgresql://...", test_mode=True)

# Aggressive (opt-in)
db = DataFlow("postgresql://...", test_mode=True,
              test_mode_aggressive_cleanup=True)
```

**Rationale**:
- Conservative default prevents surprising behavior
- Opt-in for tests that need maximum isolation
- Performance impact is user-controlled

---

### 4. Async-First Cleanup Design

**Decision**: All cleanup methods are async (use `await`).

**API**:
```python
# Correct (async)
metrics = await db.cleanup_stale_pools()

# Incorrect (sync) - will not work
metrics = db.cleanup_stale_pools()  # ❌ Missing await
```

**Rationale**:
- Consistent with AsyncSQLDatabaseNode design
- Proper async cleanup prevents "event loop is closed" errors
- Aligns with pytest-asyncio patterns

---

### 5. Enhanced Observability

**Decision**: Provide metrics for all cleanup operations.

**Metrics API**:
```python
# Lifecycle metrics
metrics = db.get_cleanup_metrics()
# Returns: {
#   'active_pools': 3,
#   'test_mode_enabled': True,
#   'pool_keys': [...],
#   'event_loop_ids': [...]
# }

# Cleanup metrics
cleanup = await db.cleanup_stale_pools()
# Returns: {
#   'stale_pools_found': 2,
#   'stale_pools_cleaned': 2,
#   'cleanup_duration_ms': 45.2,
#   'cleanup_errors': []
# }
```

**Rationale**:
- Visibility helps debug pool issues
- Metrics enable performance optimization
- Failure details aid troubleshooting

---

## API Surface Overview

### DataFlow Class Enhancements

| Method | Type | Purpose |
|--------|------|---------|
| `__init__(test_mode=None)` | Instance | Constructor with test mode control |
| `enable_test_mode()` | Class | Enable test mode globally |
| `disable_test_mode()` | Class | Disable global test mode |
| `is_test_mode_enabled()` | Class | Check global test mode status |
| `cleanup_stale_pools()` | Instance (async) | Remove stale pools proactively |
| `cleanup_all_pools()` | Instance (async) | Remove all pools (teardown) |
| `get_cleanup_metrics()` | Instance | Get pool lifecycle metrics |

### AsyncSQLDatabaseNode Enhancements

| Method | Type | Purpose |
|--------|------|---------|
| `_cleanup_closed_loop_pools()` | Class (async) | Remove pools from closed loops |
| `clear_shared_pools(graceful=True)` | Class (async) | Clear all pools with metrics |

---

## Implementation Roadmap

### Phase 1: Core API (Week 1)

**Deliverables**:
- [ ] Add `test_mode` parameter to DataFlow constructor
- [ ] Implement `_detect_test_environment()` method
- [ ] Add global test mode class methods
- [ ] Add test mode logging

**Files Modified**:
- `/packages/kailash-dataflow/src/dataflow/core/engine.py` (primary)

**Tests**:
- Unit tests for test mode detection
- Unit tests for global test mode control
- Unit tests for logging

---

### Phase 2: Cleanup Methods (Week 2)

**Deliverables**:
- [ ] Implement `cleanup_stale_pools()` with metrics
- [ ] Implement `cleanup_all_pools()` with metrics
- [ ] Implement `get_cleanup_metrics()`
- [ ] Enhance `AsyncSQLDatabaseNode._cleanup_closed_loop_pools()`
- [ ] Enhance `AsyncSQLDatabaseNode.clear_shared_pools()`

**Files Modified**:
- `/packages/kailash-dataflow/src/dataflow/core/engine.py`
- `/src/kailash/nodes/data/async_sql.py`

**Tests**:
- Unit tests for each cleanup method
- Integration tests for cleanup patterns
- Error handling tests

---

### Phase 3: Documentation (Week 3)

**Deliverables**:
- [ ] API documentation (`docs/api/test_mode.md`)
- [ ] Testing guide (`docs/testing/`)
- [ ] Fixture patterns guide (`docs/testing/fixture-patterns.md`)
- [ ] Working examples (`docs/testing/examples/`)
- [ ] Troubleshooting guide (`docs/testing/troubleshooting.md`)

**Files Created**:
- `/packages/kailash-dataflow/docs/testing/README.md`
- `/packages/kailash-dataflow/docs/testing/fixture-patterns.md`
- `/packages/kailash-dataflow/docs/testing/examples/basic_test.py`
- `/packages/kailash-dataflow/docs/testing/examples/conftest.py`

**Tests**:
- Documentation validation tests
- Example code execution tests

---

### Phase 4: Validation (Week 4)

**Deliverables**:
- [ ] All tests passing (unit, integration, E2E)
- [ ] Performance benchmarks green (<5% regression)
- [ ] User testing complete (3+ developers)
- [ ] Final review and approval
- [ ] CHANGELOG.md updated
- [ ] Release notes drafted

**Activities**:
- Run full test suite
- Performance benchmarking
- Internal user testing
- Documentation review
- Release preparation

---

## Usage Pattern Comparison

### Before (Current)

```python
# tests/test_user.py
@pytest.mark.asyncio
async def test_user_crud():
    db = DataFlow("postgresql://...")

    @db.model
    class User:
        id: str
        name: str

    # Test operations...
    # No cleanup - pools may leak!
```

**Issues**:
- No cleanup mechanism
- "pool is closed" errors in next test
- No visibility into pool state

### After (With Test Mode API)

```python
# tests/conftest.py
@pytest.fixture(scope="function")
async def db():
    db = DataFlow("postgresql://...", test_mode=True)
    yield db
    await db.cleanup_all_pools()

# tests/test_user.py
@pytest.mark.asyncio
async def test_user_crud(db):
    @db.model
    class User:
        id: str
        name: str

    # Test operations...
    # Cleanup automatic via fixture
```

**Benefits**:
- Explicit cleanup in fixture
- Test mode auto-enabled
- Metrics for debugging
- Pool leaks prevented

---

## Integration Checklist

### DataFlow Integration

- [ ] Add `test_mode` parameter to `__init__`
- [ ] Add `_test_mode` instance attribute
- [ ] Add `_test_mode_aggressive_cleanup` instance attribute
- [ ] Add class-level `_global_test_mode` attribute
- [ ] Add class-level `_global_test_mode_lock` (threading.RLock)
- [ ] Implement `_detect_test_environment()` method
- [ ] Implement `enable_test_mode()` class method
- [ ] Implement `disable_test_mode()` class method
- [ ] Implement `is_test_mode_enabled()` class method
- [ ] Implement `cleanup_stale_pools()` instance method
- [ ] Implement `cleanup_all_pools()` instance method
- [ ] Implement `get_cleanup_metrics()` instance method
- [ ] Add test mode detection logic in `__init__`
- [ ] Add test mode logging

### AsyncSQLDatabaseNode Integration

- [ ] Convert `_cleanup_closed_loop_pools()` to async
- [ ] Add detailed logging to `_cleanup_closed_loop_pools()`
- [ ] Add graceful error handling to `_cleanup_closed_loop_pools()`
- [ ] Enhance `clear_shared_pools()` with metrics return
- [ ] Add `graceful` parameter to `clear_shared_pools()`
- [ ] Add error tracking to `clear_shared_pools()`

### Node Generation Integration

- [ ] Pass test mode to generated nodes
- [ ] Bind test mode in node classes
- [ ] Verify test mode propagation

---

## Testing Strategy

### Unit Tests (95%+ Coverage)

**Test Categories**:
1. Test mode detection (auto, explicit, global)
2. Cleanup methods (stale, all, metrics)
3. Error handling (graceful degradation)
4. Logging verification
5. Thread safety (global test mode lock)

**Location**: `/packages/kailash-dataflow/tests/test_test_mode.py`

### Integration Tests

**Test Categories**:
1. Fixture patterns (function, module, session)
2. Sequential test isolation
3. Pool reuse verification
4. Cleanup effectiveness
5. Metrics accuracy

**Location**: `/packages/kailash-dataflow/tests/integration/test_test_mode_integration.py`

### End-to-End Tests

**Test Categories**:
1. Documentation examples validation
2. Real-world workflow patterns
3. Performance impact measurement
4. User workflow simulation

**Location**: `/packages/kailash-dataflow/tests/e2e/test_documentation_examples.py`

---

## Performance Impact

### Expected Overhead

| Operation | Overhead | Frequency |
|-----------|----------|-----------|
| Test mode detection | <1ms | Once per DataFlow instance |
| `cleanup_stale_pools()` | <50ms | Once per test (in fixture) |
| `cleanup_all_pools()` | <100ms | Once per test (in fixture) |
| `get_cleanup_metrics()` | <1ms | As needed |

**Total Impact**: <150ms per test (acceptable for test suite)

### Optimization Strategies

1. **Lazy Cleanup**: Only cleanup when explicitly called
2. **Shared Pools**: Maintain connection pooling benefits
3. **Graceful Degradation**: Don't block on cleanup failures
4. **Module Scoping**: Reuse pools across tests in same module

---

## Risk Mitigation

### Risk 1: Breaking Changes

**Mitigation**: All new features are opt-in with sensible defaults
- `test_mode=None` (auto-detection) is default
- No API removals or signature changes
- Backward compatibility guaranteed

### Risk 2: Performance Regression

**Mitigation**: Conservative defaults and performance testing
- Aggressive cleanup is opt-in only
- Benchmarks in CI (fail if >5% regression)
- Lazy cleanup (only when needed)

### Risk 3: Production Impact

**Mitigation**: Test mode only activates in test environments
- Auto-detection checks for pytest
- Production environments won't have PYTEST_CURRENT_TEST
- Explicit `test_mode=False` available if needed

### Risk 4: Documentation Staleness

**Mitigation**: Automated doc validation
- Doc examples tested in CI
- Examples fail if code changes
- Quarterly documentation review

---

## Success Metrics

### Quantitative (Must Achieve)

- ✅ 95%+ unit test coverage for new code
- ✅ 100% of documented patterns tested
- ✅ <5% performance regression
- ✅ Zero breaking changes (all existing tests pass)
- ✅ <30 seconds to find fixture pattern in docs

### Qualitative (Should Achieve)

- ✅ Zero "pool is closed" errors when following docs
- ✅ Positive feedback from 3+ internal reviewers
- ✅ External contributors successfully use testing guide
- ✅ Documentation clear and instructive (not descriptive)

---

## Next Steps

### Immediate (This Week)

1. **Review**: Technical review of this API specification
2. **Approval**: Get approval from DataFlow maintainers
3. **Planning**: Finalize implementation schedule

### Phase 1 (Week 1)

1. **Implement**: Core test mode API (constructor, class methods)
2. **Test**: Unit tests for test mode detection and control
3. **Document**: Initial API documentation draft

### Phase 2 (Week 2)

1. **Implement**: Cleanup methods with metrics
2. **Enhance**: AsyncSQLDatabaseNode cleanup methods
3. **Test**: Integration tests for cleanup patterns

### Phase 3 (Week 3)

1. **Document**: Complete testing guide with examples
2. **Validate**: Automated doc testing in CI
3. **Review**: Documentation review by 2+ developers

### Phase 4 (Week 4)

1. **Validate**: Full test suite execution
2. **Benchmark**: Performance impact measurement
3. **Release**: Prepare v0.8.0 release

---

## Approval

**Author**: Claude (API Design Specialist)
**Date**: 2025-10-30
**Status**: Awaiting Review

**Reviewers**:
- [ ] DataFlow maintainer (technical review)
- [ ] Testing specialist (test strategy review)
- [ ] Documentation specialist (docs review)
- [ ] Lead architect (final approval)

**Approval Criteria**:
- API design is consistent with DataFlow patterns
- Backward compatibility guaranteed
- Test strategy is comprehensive
- Documentation plan is complete
- Performance impact is acceptable

---

## References

### Related Documents

- **ADR-017 Main**: `/packages/kailash-dataflow/adr/ADR-017-dataflow-testing-improvements.md`
- **API Specification**: `/packages/kailash-dataflow/adr/ADR-017-test-mode-api-spec.md`

### Code References

- **DataFlow Engine**: `/packages/kailash-dataflow/src/dataflow/core/engine.py`
- **AsyncSQLDatabaseNode**: `/src/kailash/nodes/data/async_sql.py`
- **Existing Test Detection**: `/src/kailash/nodes/data/async_sql.py` (lines 519-526)

### External References

- [pytest fixtures documentation](https://docs.pytest.org/en/stable/fixture.html)
- [pytest-asyncio patterns](https://pytest-asyncio.readthedocs.io/)
- [asyncpg connection pooling](https://magicstack.github.io/asyncpg/current/usage.html#connection-pools)
