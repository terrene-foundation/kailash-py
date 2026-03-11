# Performance Baseline Tests

This directory contains performance baseline tests for the Kaizen framework, focusing on signature resolution system performance.

## Overview

The performance tests establish baselines and regression detection for:
- Signature parsing
- Signature compilation
- Signature validation
- Class-based signature creation
- End-to-end signature resolution

## Running Tests

### Quick Run
```bash
pytest tests/unit/performance/ -v
```

### With Performance Output
```bash
pytest tests/unit/performance/ -v -s
```

### Single Test Class
```bash
pytest tests/unit/performance/test_signature_resolution_baseline.py::TestEndToEndResolutionBaseline -v -s
```

## Test Coverage

### Signature Parsing (4 tests)
- Simple signatures (question -> answer)
- Complex signatures (multi-input, multi-output)
- Multi-modal signatures (text, image -> analysis)
- Enterprise signatures (privacy, audit features)

**Targets**: <10ms for simple, <50ms for complex
**Current**: 0.01-0.011ms (500-1000x faster than target) ✅

### Signature Compilation (4 tests)
- Simple workflow compilation
- Complex workflow compilation
- Enterprise workflow compilation (security features)
- Multi-modal workflow compilation

**Targets**: <10ms for simple, <50ms for complex
**Current**: 0.001-0.002ms (5000-10000x faster than target) ✅

### Signature Validation (3 tests)
- Simple signature validation
- Typed signature validation (with type checking)
- Multi-modal signature validation

**Targets**: <10ms for all validation
**Current**: 0.001-0.002ms (5000-10000x faster than target) ✅

### Class-Based Signatures (2 tests)
- Simple DSPy-style signatures
- Complex DSPy-style signatures (6 fields)

**Targets**: <10ms for simple, <50ms for complex
**Current**: 0.013-0.034ms (300-750x faster than target) ✅

### End-to-End Resolution (3 tests - CRITICAL PATH)
- Simple end-to-end (parse → validate → compile)
- Complex end-to-end (parse → validate → compile)
- Multi-modal end-to-end (parse → validate → compile)

**Targets**: <100ms p95
**Current**: 0.012-0.018ms (5500-8300x faster than target) ✅

### Regression Detection (2 tests)
- Parsing performance regression (threshold: <1ms)
- End-to-end performance regression (threshold: <2ms)

**Current**: 0.008-0.014ms (well under thresholds) ✅

## Performance Targets

| Operation | Target | Current P95 | Status |
|-----------|--------|-------------|--------|
| Simple parsing | <10ms | 0.010ms | ✅ 1000x faster |
| Complex parsing | <50ms | 0.011ms | ✅ 4500x faster |
| Simple compilation | <10ms | 0.002ms | ✅ 5000x faster |
| Complex compilation | <50ms | 0.001ms | ✅ 50000x faster |
| Simple validation | <10ms | 0.001ms | ✅ 10000x faster |
| End-to-end (CRITICAL) | <100ms | 0.013-0.018ms | ✅ 5500-8300x faster |

## Regression Thresholds

### Alert Thresholds (⚠️)
- Parsing: >0.5ms (3-5x current baseline)
- End-to-end: >1ms (5x current baseline)
- Memory: >50 KB (3x current peak)

### Failure Thresholds (❌)
- Parsing: >1ms (6-10x current baseline)
- End-to-end: >2ms (10x current baseline)
- Memory: >100 KB (7x current peak)

## CI/CD Integration

### Run in CI Pipeline
```bash
# Run performance tests
pytest tests/unit/performance/ -v --tb=short

# Check for regressions (exits with error if thresholds exceeded)
pytest tests/unit/performance/test_signature_resolution_baseline.py::TestRegressionDetection -v
```

### Performance Monitoring
```bash
# Generate profiling report
python scripts/profile_signature_resolution.py --output profiling_results.json

# Parse JSON results in CI
cat profiling_results.json | jq '.overall_stats.execution_time.p95'
```

## Understanding Results

### Test Output Format
```
✓ Simple parsing P95: 0.010ms (target: <10ms)
```

- **✓**: Test passed
- **P95**: 95th percentile latency (slower than 95% of runs)
- **Target**: Performance target from requirements

### Regression Detection Output
```
✓ Parsing regression check P95: 0.008ms (threshold: <1ms)
```

- Compares against 10x current baseline
- Alerts if approaching threshold (>50% of threshold)
- Fails if exceeding threshold

## Profiling Script

For detailed function-level profiling, use:
```bash
python scripts/profile_signature_resolution.py --iterations 100
```

See `adr/TODO-151-PROFILING-RESULTS.md` for detailed analysis.

## Performance Baseline Summary

**Overall Result**: ✅ ALL TARGETS EXCEEDED

- **End-to-end resolution**: 0.013-0.018ms vs 100ms target (5500-8300x faster)
- **Signature parsing**: 0.010-0.011ms vs 10-50ms targets (900-5000x faster)
- **Signature compilation**: 0.001-0.002ms vs 10-50ms targets (5000-50000x faster)
- **Signature validation**: 0.001-0.002ms vs 10ms target (5000-10000x faster)
- **Memory usage**: 8-15 KB (extremely efficient)

**Conclusion**: NO optimization needed - system already performs exceptionally well!

## Related Documentation

- **Profiling Results**: `adr/TODO-151-PROFILING-RESULTS.md`
- **Phase 1 Summary**: `adr/TODO-151-PHASE-1-COMPLETION-SUMMARY.md`
- **Profiling Script**: `scripts/profile_signature_resolution.py`
- **Raw Data**: `adr/signature_profiling_results.json`

## Maintenance

### Adding New Baseline Tests

1. Create test method in appropriate class
2. Use `measure_performance()` helper
3. Assert P95 < target threshold
4. Add print statement with target

Example:
```python
def test_my_operation_baseline(self):
    """Baseline: My operation should complete in <10ms."""
    perf = measure_performance(my_function, arg1, arg2)

    assert perf['result'].is_valid
    assert perf['p95'] < 10, f"P95 {perf['p95']:.2f}ms exceeds 10ms target"
    print(f"  ✓ My operation P95: {perf['p95']:.3f}ms (target: <10ms)")
```

### Updating Thresholds

If baseline performance changes significantly:

1. Update regression thresholds in `TestRegressionDetection`
2. Update targets in individual test docstrings
3. Update this README
4. Document changes in profiling results ADR

---

**Last Updated**: 2025-10-05
**Status**: ✅ All baselines established, all targets exceeded
