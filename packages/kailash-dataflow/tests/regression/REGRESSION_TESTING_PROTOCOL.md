# DataFlow Regression Testing Protocol

## Overview

This protocol protects DataFlow's core functionality while enabling safe, incremental feature development. It prevents the over-engineering that previously broke basic operations by establishing automated gates and clear go/no-go criteria.

## Critical Protection Areas

### 1. Core Functionality (NEVER BREAK)

- `DataFlow()` instantiation
- `DataFlow(':memory:')` SQLite operations
- `@db.model` decorator functionality
- Basic CRUD node generation (11 nodes per model)
- Essential workflow execution patterns

### 2. Current Baseline Status

- **Unit Tests**: 453/490 passing (92.4%)
- **Test Files**: 142 total across all tiers
- **Core Example**: `examples/01_basic_crud.py` functional
- **Known Failures**: 37 tests in advanced features (acceptable)

## Regression Testing Workflow

### Stage 1: Pre-Development Gates

**MUST PASS before any feature development:**

```bash
# 1. Core functionality validation
python tests/regression/validate_core_functionality.py

# 2. Basic example execution
python examples/01_basic_crud.py

# 3. Essential unit tests
pytest tests/unit/test_engine_migration_integration.py::TestBasicDataFlowOperations -v

# 4. Memory database operations
pytest tests/integration/dataflow_alpha/test_real_database_operations.py::test_memory_database_basic_crud -v
```

**Success Criteria**: ALL must pass before proceeding

### Stage 2: Development Phase Gates

**Run after each significant change:**

```bash
# Quick validation (< 30 seconds)
./tests/regression/quick_validation.sh

# Core unit tests (< 2 minutes)
pytest tests/unit/test_engine_migration_integration.py tests/unit/test_gateway_integration.py -x

# Integration smoke test (< 5 minutes)
pytest tests/integration/dataflow_alpha/test_real_database_operations.py::test_basic_workflow_execution -v
```

**Go/No-Go Criteria**: If ANY fail, STOP and fix immediately

### Stage 3: Feature Completion Gates

**MUST PASS before considering feature complete:**

```bash
# Full core test suite
pytest tests/unit/test_engine_migration_integration.py tests/unit/test_gateway_integration.py tests/unit/test_legacy_api_compatibility.py -v

# Essential integration tests
pytest tests/integration/dataflow_alpha/ -k "basic or crud or workflow" -v

# E2E smoke test
pytest tests/e2e/dataflow_alpha/test_complete_user_journey.py::test_basic_user_journey -v

# Performance baseline
python tests/regression/performance_benchmark.py
```

**Regression Detection**: Compare against baseline metrics

### Stage 4: Release Gates

**Final validation before any release:**

```bash
# Complete regression suite
./tests/regression/full_regression_suite.sh

# Documentation examples validation
pytest tests/e2e/test_documentation_examples.py -v

# Backward compatibility verification
python tests/regression/backward_compatibility_check.py
```

## Automated Protection Scripts

### Quick Validation Script

Location: `tests/regression/quick_validation.sh`

**Purpose**: Fast feedback during development (< 30 seconds)
**Scope**: Core functionality only
**Triggers**: After every code change

### Full Regression Suite

Location: `tests/regression/full_regression_suite.sh`

**Purpose**: Comprehensive validation before releases
**Scope**: All critical paths and examples
**Triggers**: Before commits, before releases

### Performance Benchmark

Location: `tests/regression/performance_benchmark.py`

**Purpose**: Detect performance regressions
**Metrics**: Core operation timing, memory usage
**Baseline**: Current performance characteristics

## Feature Implementation Gates

### Gate 1: Design Validation

**Question**: Does this feature maintain zero-configuration simplicity?

**Criteria**:

- Basic `DataFlow()` usage remains unchanged
- No new required configuration for existing functionality
- @db.model decorator behavior unchanged

**Action**: If NO, redesign or reject feature

### Gate 2: Implementation Validation

**Question**: Do core tests still pass?

**Test Command**:

```bash
pytest tests/unit/test_engine_migration_integration.py::TestBasicDataFlowOperations -v
```

**Action**: If ANY fail, fix immediately or revert

### Gate 3: Integration Validation

**Question**: Do existing workflows still execute?

**Test Command**:

```bash
python examples/01_basic_crud.py
python tests/regression/validate_core_functionality.py
```

**Action**: If ANY fail, feature is too disruptive - revert

### Gate 4: Performance Validation

**Question**: Is performance within acceptable bounds?

**Criteria**:

- Basic CRUD operations: < 10ms overhead
- Memory usage: < 5% increase
- Startup time: < 100ms increase

**Action**: If exceeded, optimize or revert

## Over-Engineering Prevention

### Complexity Limits

1. **New Dependencies**: Requires explicit approval
2. **Configuration Options**: Must be optional with sensible defaults
3. **API Changes**: Backward compatibility required
4. **Migration Changes**: Must be non-destructive

### Warning Signs

- Core tests start failing
- Basic examples need modification
- Configuration becomes required
- Startup time increases significantly

### Emergency Procedures

When regression detected:

1. **STOP** all development immediately
2. **REVERT** to last known good state
3. **ANALYZE** root cause
4. **FIX** with minimal changes
5. **VALIDATE** full regression suite

## Performance Benchmarks

### Core Operation Baselines

```
DataFlow() instantiation: ~2ms
@db.model registration: ~1ms
Basic CRUD workflow: ~15ms
Memory database operations: ~5ms
Node generation (11 nodes): ~3ms
```

### Memory Usage Baselines

```
Base DataFlow instance: ~8MB
Single model registration: ~1MB
Basic workflow execution: ~2MB additional
```

### Performance Monitoring

- Track operation timing in CI
- Alert on >20% performance degradation
- Maintain performance history graphs

## Test Organization

### Tier 1: Unit Tests (< 1 second)

**Core Protection**: Essential DataFlow operations

```bash
pytest tests/unit/test_engine_migration_integration.py::TestBasicDataFlowOperations
pytest tests/unit/test_gateway_integration.py::TestBasicGatewayOperations
pytest tests/unit/test_legacy_api_compatibility.py::TestBackwardCompatibility
```

### Tier 2: Integration Tests (< 5 seconds)

**Real Infrastructure**: No mocking allowed

```bash
pytest tests/integration/dataflow_alpha/test_real_database_operations.py
pytest tests/integration/test_dataflow_crud_integration.py
```

### Tier 3: End-to-End Tests (< 10 seconds)

**Complete Workflows**: Full user scenarios

```bash
pytest tests/e2e/dataflow_alpha/test_complete_user_journey.py
pytest tests/e2e/test_documentation_examples.py
```

## Continuous Integration Integration

### Pre-Commit Hooks

```bash
# Fast validation before commit
tests/regression/quick_validation.sh
```

### CI Pipeline Gates

```yaml
stages:
  - core_validation: # Gate 1: Core functionality
  - integration_tests: # Gate 2: Integration validation
  - performance_check: # Gate 3: Performance validation
  - full_regression: # Gate 4: Complete validation
```

### Failure Actions

- **Core Validation Fails**: Block all commits
- **Integration Fails**: Require manual review
- **Performance Regression**: Alert and require justification
- **Full Regression Fails**: Block release

## Rollback Procedures

### Automatic Rollback Triggers

1. Core functionality tests fail
2. Basic examples fail to execute
3. Performance degrades >50%
4. Memory usage increases >100%

### Manual Rollback Decision Points

1. Integration test failure rate >10%
2. E2E test execution time doubles
3. New configuration becomes required
4. Backward compatibility breaks

### Rollback Process

```bash
# 1. Identify last known good commit
git log --oneline tests/regression/validation_history.log

# 2. Revert to safe state
git revert <bad-commit-range>

# 3. Validate rollback
./tests/regression/full_regression_suite.sh

# 4. Document incident
echo "$(date): Rolled back due to regression" >> tests/regression/rollback_log.md
```

## Success Metrics

### Green Light Indicators

- All core tests passing (453+ tests)
- Examples execute without modification
- Performance within 10% of baseline
- Memory usage stable
- Zero breaking changes

### Yellow Light Indicators

- Non-core test failures acceptable
- Performance degradation <20%
- New optional configuration
- Documentation updates needed

### Red Light Indicators (STOP DEVELOPMENT)

- Any core test failure
- Basic examples require modification
- Performance degradation >20%
- Required configuration changes
- Backward compatibility breaks

## Implementation Notes

This protocol prioritizes DataFlow's core value proposition: zero-configuration database operations that "just work". Any feature that threatens this simplicity should be rejected or significantly redesigned.

The regression testing approach uses a layered defense:

1. Quick feedback during development
2. Comprehensive validation before commits
3. Full regression before releases
4. Continuous monitoring in production

This ensures DataFlow remains reliable while enabling careful, incremental improvement.
