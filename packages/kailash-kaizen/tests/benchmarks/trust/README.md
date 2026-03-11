# Trust Operations Performance Benchmarks

Comprehensive performance benchmarks for EATP (Enterprise Agent Trust Protocol) trust operations.

## Overview

This benchmark suite measures the performance of core trust operations with **NO MOCKING** using real implementations with in-memory stores for isolation.

## Operations Benchmarked

### 1. ESTABLISH Operation
**Target**: <100ms p95

Creates initial trust for an agent including:
- Key generation and signing
- Genesis record creation
- Capability attestations
- Constraint envelope computation
- Chain storage

### 2. DELEGATE Operation
**Target**: <50ms p95

Transfers trust from one agent to another:
- Delegator chain validation
- Capability verification
- Constraint tightening
- Delegation record signing
- Delegatee chain update

### 3. VERIFY Operations

#### VERIFY QUICK
**Target**: <5ms p95
- Expiration check only
- Cache-optimized

#### VERIFY STANDARD
**Target**: <50ms p95
- Capability matching
- Constraint evaluation
- Full chain validation

#### VERIFY FULL
**Target**: <100ms p95
- All standard checks
- Cryptographic signature verification
- Complete chain integrity

### 4. AUDIT Operation
**Target**: <20ms p95

Records agent actions:
- Trust chain hash computation
- Audit anchor creation
- Signing

### 5. Cache Performance

#### Cache Hit
**Target**: <1ms mean
- O(1) lookup performance
- 100x faster than database

#### Cache Hit Rate
**Target**: >85% under load
- Realistic access patterns (Zipf distribution)
- 1000 operations simulated

## Running Benchmarks

### Basic Run
```bash
pytest tests/benchmarks/trust/benchmark_trust_operations.py -v --benchmark-only
```

### With JSON Output
```bash
pytest tests/benchmarks/trust/benchmark_trust_operations.py --benchmark-json=results.json
```

### With HTML Report
```bash
pytest tests/benchmarks/trust/benchmark_trust_operations.py --benchmark-json=results.json
pytest-benchmark compare results.json --csv=comparison.csv
```

### Run Specific Groups
```bash
# Only ESTABLISH benchmarks
pytest tests/benchmarks/trust/ -v --benchmark-only -k establish

# Only VERIFY benchmarks
pytest tests/benchmarks/trust/ -v --benchmark-only -k verify

# Only cache benchmarks
pytest tests/benchmarks/trust/ -v --benchmark-only -k cache
```

## Requirements

Install pytest-benchmark:
```bash
pip install pytest-benchmark
```

## Architecture

### NO MOCKING Policy

All benchmarks use **real implementations** with in-memory stores:

- `InMemoryTrustStore`: Real trust store implementation using dict storage
- `InMemoryAuthorityRegistry`: Real authority registry using dict storage
- `TrustOperations`: Production implementation (no mocks)
- `TrustKeyManager`: Production cryptographic operations
- `TrustChainCache`: Production LRU cache

### Why In-Memory Stores?

1. **Isolation**: No external dependencies (PostgreSQL, Redis)
2. **Consistency**: Reproducible results across environments
3. **Speed**: Focuses on operation performance, not I/O
4. **Real Logic**: All business logic, crypto, and validation runs unchanged

## Performance Targets

All targets are **p95 latency** (95th percentile):

| Operation | Target | Rationale |
|-----------|--------|-----------|
| ESTABLISH | <100ms | Agent creation is infrequent |
| DELEGATE | <50ms | Delegation happens during workflow setup |
| VERIFY QUICK | <5ms | Called before every agent action (cache hit) |
| VERIFY STANDARD | <50ms | Standard verification for most actions |
| VERIFY FULL | <100ms | Full verification for sensitive operations |
| AUDIT | <20ms | Should not slow down agent actions |
| Cache Hit | <1ms | In-memory lookup overhead only |
| Cache Hit Rate | >85% | Effective caching under load |

## Interpreting Results

### Success Criteria

All benchmarks have assertions that fail if performance targets are not met:

```python
assert p95 < 0.100, f"ESTABLISH p95 ({p95:.3f}s) exceeds 100ms target"
```

### Example Output

```
tests/benchmarks/trust/benchmark_trust_operations.py::test_benchmark_establish_operation
  Mean: 45.2ms, Median: 43.1ms, p95: 67.8ms, Max: 89.3ms
  ✓ PASS: p95 (67.8ms) < 100ms target
```

### Benchmark Groups

Results are organized by operation type:
- `group="establish"`: Agent establishment operations
- `group="delegate"`: Trust delegation operations
- `group="verify"`: Trust verification operations
- `group="audit"`: Audit recording operations
- `group="cache"`: Cache performance tests
- `group="memory"`: Memory usage tests

## Continuous Integration

### CI Configuration

Add to your CI pipeline:

```yaml
- name: Run Trust Benchmarks
  run: |
    pytest tests/benchmarks/trust/ --benchmark-only --benchmark-json=ci_results.json

- name: Upload Results
  uses: actions/upload-artifact@v2
  with:
    name: benchmark-results
    path: ci_results.json
```

### Regression Detection

Compare results across runs:

```bash
pytest-benchmark compare baseline.json current.json --csv=comparison.csv
```

## Troubleshooting

### Benchmarks Too Slow

1. Check CPU usage (other processes)
2. Verify no network calls (should be in-memory only)
3. Check if running in debug mode
4. Increase warmup rounds: `pytest --benchmark-warmup=on`

### Inconsistent Results

1. Run more iterations: `pytest --benchmark-min-rounds=100`
2. Disable auto-calibration: `pytest --benchmark-disable-gc`
3. Check for background processes

### Out of Memory

1. Reduce cache size in `test_benchmark_cache_memory_usage`
2. Run specific benchmarks instead of full suite
3. Increase available memory

## Future Enhancements

1. **Database Comparison**: Add benchmarks with real PostgreSQL
2. **Concurrency**: Multi-threaded/async concurrent operations
3. **Load Testing**: Sustained high-load scenarios
4. **Network Latency**: Distributed trust operations
5. **Chain Depth**: Performance with deep delegation chains

## References

- EATP Week 11: Trust Operations Implementation
- pytest-benchmark documentation: https://pytest-benchmark.readthedocs.io/
- Trust Operations: `/src/kaizen/trust/operations.py`
- Trust Cache: `/src/kaizen/trust/cache.py`
