# Trust Benchmarks Quick Start Guide

Get started with EATP trust operations performance benchmarks in 5 minutes.

## Prerequisites

Install pytest-benchmark:

```bash
pip install pytest-benchmark
```

## Run Benchmarks

### 1. Basic Run (All Benchmarks)

```bash
cd 
pytest tests/benchmarks/trust/benchmark_trust_operations.py -v --benchmark-only
```

**Expected Output**:
```
tests/benchmarks/trust/benchmark_trust_operations.py::test_benchmark_establish_operation ✓
tests/benchmarks/trust/benchmark_trust_operations.py::test_benchmark_delegate_operation ✓
tests/benchmarks/trust/benchmark_trust_operations.py::test_benchmark_verify_quick ✓
...

================================ benchmark summary ================================
Name                                       Mean      Median     p95       Max
------------------------------------------------------------------------------------
test_benchmark_establish_operation      45.2ms     43.1ms   67.8ms   89.3ms
test_benchmark_delegate_operation       23.4ms     22.1ms   31.2ms   45.6ms
test_benchmark_verify_quick              2.1ms      2.0ms    3.1ms    4.2ms
...
```

### 2. Generate JSON Report

```bash
pytest tests/benchmarks/trust/benchmark_trust_operations.py --benchmark-json=results.json
```

This creates `results.json` with detailed benchmark data.

### 3. Generate Markdown Report

```bash
python tests/benchmarks/trust/generate_report.py results.json > performance_report.md
```

Opens in your browser or editor:
```bash
# macOS
open performance_report.md

# Linux
xdg-open performance_report.md
```

## Run Specific Benchmarks

### Only ESTABLISH Operations

```bash
pytest tests/benchmarks/trust/ -v --benchmark-only -k establish
```

### Only VERIFY Operations

```bash
pytest tests/benchmarks/trust/ -v --benchmark-only -k verify
```

### Only Cache Benchmarks

```bash
pytest tests/benchmarks/trust/ -v --benchmark-only -k cache
```

## Interpret Results

### Performance Targets

| Operation | Target | Why |
|-----------|--------|-----|
| ESTABLISH | <100ms p95 | Agent creation is infrequent |
| DELEGATE | <50ms p95 | Delegation during workflow setup |
| VERIFY QUICK | <5ms p95 | Every agent action (cache hit) |
| VERIFY STANDARD | <50ms p95 | Standard verification |
| VERIFY FULL | <100ms p95 | Sensitive operations |
| AUDIT | <20ms p95 | Should not slow down actions |
| Cache Hit | <1ms mean | In-memory lookup only |

### Status Indicators

- ✅ **PASS**: Meets performance target
- ⚠️ **WARN**: Within 20% of target (needs monitoring)
- ❌ **FAIL**: Exceeds target (needs optimization)

### Example Result

```
### Verify Quick

**Target: <5ms p95**

| Metric | Value | Status |
|--------|-------|--------|
| Mean | 2.143ms | - |
| Median | 2.087ms | - |
| p95 | 3.124ms | ✅ PASS |
| Max | 4.231ms | - |
```

**Interpretation**: Verification latency is well below the 5ms target. ✅

## Common Use Cases

### 1. Pre-Commit Performance Check

```bash
# Quick sanity check before committing
pytest tests/benchmarks/trust/ --benchmark-only --benchmark-min-rounds=10
```

### 2. Nightly CI Performance Monitoring

```bash
# Full benchmark suite with detailed results
pytest tests/benchmarks/trust/ \
  --benchmark-only \
  --benchmark-min-rounds=100 \
  --benchmark-json=nightly_results.json

python tests/benchmarks/trust/generate_report.py nightly_results.json > nightly_report.md
```

### 3. Compare Before/After Optimization

```bash
# Baseline before optimization
pytest tests/benchmarks/trust/ --benchmark-json=baseline.json

# After optimization
pytest tests/benchmarks/trust/ --benchmark-json=optimized.json

# Compare
pytest-benchmark compare baseline.json optimized.json
```

### 4. Memory Profiling

```bash
# Run memory usage benchmark
pytest tests/benchmarks/trust/ -v --benchmark-only -k memory
```

## Troubleshooting

### Issue: Benchmarks are slow

**Solution**: Check for background processes consuming CPU

```bash
# macOS
top -o cpu

# Linux
htop
```

### Issue: Inconsistent results

**Solution**: Run more rounds for stability

```bash
pytest tests/benchmarks/trust/ --benchmark-only --benchmark-min-rounds=100
```

### Issue: Import errors

**Solution**: Ensure you're in the correct directory

```bash
cd 
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
pytest tests/benchmarks/trust/
```

### Issue: "No module named pytest_benchmark"

**Solution**: Install pytest-benchmark

```bash
pip install pytest-benchmark
```

## Advanced Options

### Save Benchmark Comparison

```bash
# Save baseline
pytest tests/benchmarks/trust/ --benchmark-save=baseline

# Compare against baseline
pytest tests/benchmarks/trust/ --benchmark-compare=baseline
```

### Custom Output Format

```bash
# CSV output
pytest tests/benchmarks/trust/ --benchmark-only --benchmark-columns=mean,median,min,max --benchmark-sort=mean
```

### Disable Garbage Collection

```bash
# More consistent results (disables GC during benchmarks)
pytest tests/benchmarks/trust/ --benchmark-disable-gc
```

## Next Steps

1. **Review**: Check `performance_report.md` for detailed analysis
2. **Monitor**: Set up nightly CI benchmarks to track performance over time
3. **Optimize**: Focus on operations that exceed targets
4. **Compare**: Use `pytest-benchmark compare` to validate optimizations

## Documentation

- Full README: `tests/benchmarks/trust/README.md`
- Benchmark source: `tests/benchmarks/trust/benchmark_trust_operations.py`
- Report generator: `tests/benchmarks/trust/generate_report.py`

## Questions?

See the full documentation in `README.md` or the trust operations module:
- `/src/kaizen/trust/operations.py`
- `/src/kaizen/trust/cache.py`
- `/src/kaizen/trust/chain.py`
