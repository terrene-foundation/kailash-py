# Trust Operations Benchmarks - File Index

Quick reference guide to all benchmark files and their purposes.

## Core Files

### 📊 `benchmark_trust_operations.py`
**Purpose**: Main benchmark test suite

**Contains**:
- 12 benchmark tests covering all EATP operations
- InMemoryTrustStore implementation (NO MOCKING)
- InMemoryAuthorityRegistry implementation (NO MOCKING)
- Comprehensive fixtures
- Performance assertions

**Run**:
```bash
pytest tests/benchmarks/trust/benchmark_trust_operations.py -v --benchmark-only
```

**Tests**:
```
ESTABLISH Group (2 tests):
  - test_benchmark_establish_operation
  - test_benchmark_establish_multiple_capabilities

DELEGATE Group (1 test):
  - test_benchmark_delegate_operation

VERIFY Group (3 tests):
  - test_benchmark_verify_quick
  - test_benchmark_verify_standard
  - test_benchmark_verify_full

AUDIT Group (1 test):
  - test_benchmark_audit_operation

CACHE Group (4 tests):
  - test_benchmark_cache_hit
  - test_benchmark_cache_miss
  - test_benchmark_cache_set
  - test_benchmark_cache_hit_rate_under_load

MEMORY Group (1 test):
  - test_benchmark_cache_memory_usage
```

---

### 📝 `generate_report.py`
**Purpose**: Generate markdown reports from benchmark JSON

**Usage**:
```bash
# Generate report
python tests/benchmarks/trust/generate_report.py results.json > report.md

# Make executable
chmod +x tests/benchmarks/trust/generate_report.py
./tests/benchmarks/trust/generate_report.py results.json > report.md
```

**Output**: Markdown report with:
- Performance metrics tables
- Status indicators (✅ PASS, ⚠️ WARN, ❌ FAIL)
- Conclusions and recommendations
- Environment information

---

## Documentation Files

### 📖 `README.md`
**Purpose**: Complete documentation

**Sections**:
1. Overview
2. Operations benchmarked (detailed)
3. Running benchmarks (all options)
4. Requirements
5. Architecture (NO MOCKING explained)
6. Performance targets (rationale)
7. Interpreting results
8. CI/CD integration
9. Troubleshooting
10. Future enhancements

**When to use**: Comprehensive reference for all benchmark features

---

### 🚀 `QUICKSTART.md`
**Purpose**: Get started in 5 minutes

**Sections**:
1. Prerequisites
2. Run benchmarks (3 simple commands)
3. Interpret results
4. Common use cases
5. Troubleshooting
6. Advanced options

**When to use**: First time running benchmarks or quick refresher

---

### 📋 `IMPLEMENTATION_SUMMARY.md`
**Purpose**: Implementation details and architecture

**Sections**:
1. Files created
2. Benchmark coverage
3. NO MOCKING architecture
4. Performance targets rationale
5. Fixtures architecture
6. Expected results
7. Future enhancements
8. Compliance with gold standards

**When to use**: Understanding how benchmarks are implemented

---

### 📚 `INDEX.md` (This File)
**Purpose**: Quick reference to all files

**When to use**: Finding the right documentation for your task

---

## Configuration Files

### `__init__.py` (package level)
**Path**: `tests/benchmarks/__init__.py`

**Purpose**: Package initialization for benchmarks

**Contents**: Simple docstring for package description

---

### `__init__.py` (trust level)
**Path**: `tests/benchmarks/trust/__init__.py`

**Purpose**: Trust benchmarks subpackage

**Contents**: Trust benchmarks package docstring

---

### `conftest.py`
**Path**: `tests/benchmarks/conftest.py`

**Purpose**: Shared pytest configuration and fixtures

**Contains**:
- `pytest_configure`: Register benchmark marker
- `pytest_benchmark_update_json`: Add metadata to JSON output
- `pytest_benchmark_generate_json`: Add performance targets to report

---

## Quick Navigation

### I want to...

#### Run benchmarks
→ Start with `QUICKSTART.md`
→ Command: `pytest tests/benchmarks/trust/benchmark_trust_operations.py --benchmark-only`

#### Understand how they work
→ Read `IMPLEMENTATION_SUMMARY.md`
→ Review `benchmark_trust_operations.py` source

#### Generate a report
→ Use `generate_report.py`
→ Command: `python tests/benchmarks/trust/generate_report.py results.json > report.md`

#### Get detailed documentation
→ Read `README.md`
→ Covers all features and options

#### Troubleshoot issues
→ See `README.md` → Troubleshooting section
→ Or `QUICKSTART.md` → Troubleshooting section

#### Integrate with CI/CD
→ See `README.md` → Continuous Integration section
→ Examples in `IMPLEMENTATION_SUMMARY.md`

#### Understand performance targets
→ See `README.md` → Performance Targets table
→ Or `IMPLEMENTATION_SUMMARY.md` → Performance Targets section

---

## File Structure

```
tests/benchmarks/
├── __init__.py                           # Benchmarks package init
├── conftest.py                           # Shared pytest configuration
└── trust/
    ├── __init__.py                       # Trust benchmarks package
    ├── benchmark_trust_operations.py     # ⭐ Main benchmark suite
    ├── generate_report.py                # 📊 Report generator
    ├── README.md                         # 📖 Complete documentation
    ├── QUICKSTART.md                     # 🚀 5-minute guide
    ├── IMPLEMENTATION_SUMMARY.md         # 📋 Implementation details
    └── INDEX.md                          # 📚 This file
```

---

## Common Commands Cheat Sheet

```bash
# Quick run (all benchmarks)
pytest tests/benchmarks/trust/benchmark_trust_operations.py --benchmark-only

# Run with JSON output
pytest tests/benchmarks/trust/benchmark_trust_operations.py --benchmark-json=results.json

# Generate markdown report
python tests/benchmarks/trust/generate_report.py results.json > report.md

# Run specific group
pytest tests/benchmarks/trust/ --benchmark-only -k verify

# Run with more iterations (stability)
pytest tests/benchmarks/trust/ --benchmark-only --benchmark-min-rounds=100

# Save baseline for comparison
pytest tests/benchmarks/trust/ --benchmark-save=baseline

# Compare against baseline
pytest tests/benchmarks/trust/ --benchmark-compare=baseline
```

---

## Performance Targets Summary

| Operation | Target | File Reference |
|-----------|--------|----------------|
| ESTABLISH | <100ms p95 | `benchmark_trust_operations.py:144` |
| DELEGATE | <50ms p95 | `benchmark_trust_operations.py:204` |
| VERIFY QUICK | <5ms p95 | `benchmark_trust_operations.py:243` |
| VERIFY STANDARD | <50ms p95 | `benchmark_trust_operations.py:270` |
| VERIFY FULL | <100ms p95 | `benchmark_trust_operations.py:297` |
| AUDIT | <20ms p95 | `benchmark_trust_operations.py:331` |
| Cache Hit | <1ms mean | `benchmark_trust_operations.py:363` |
| Cache Hit Rate | >85% | `benchmark_trust_operations.py:410` |

---

## Support

**Questions?**
1. Check `QUICKSTART.md` for common tasks
2. Read `README.md` for comprehensive documentation
3. Review `IMPLEMENTATION_SUMMARY.md` for architecture details
4. Examine `benchmark_trust_operations.py` source code

**Issues?**
1. See Troubleshooting section in `README.md`
2. Verify dependencies: `pip install pytest-benchmark`
3. Check environment: `pytest --version` and `python --version`

---

**Last Updated**: 2025-12-15
**Version**: 1.0.0
**Status**: ✅ Ready for use
