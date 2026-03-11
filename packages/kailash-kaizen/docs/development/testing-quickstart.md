# Kaizen Testing Quick Start Guide

## 🚀 Get Started in 30 Seconds

### 1. Run Unit Tests (Development)
```bash
./scripts/test-tier1-unit.sh --fast
```
**Expected**: Fast feedback (<30 seconds), 466+ tests passing

### 2. Run Integration Tests (Pre-commit)
```bash
./scripts/test-tier2-integration.sh --setup
```
**Expected**: Real services validation (2-3 minutes)

### 3. Run Complete Suite (CI/Production)
```bash
./scripts/test-all-tiers.sh --coverage
```
**Expected**: Full system validation (5-10 minutes)

## 🎯 Quick Commands Reference

| Use Case | Command | Time | Purpose |
|----------|---------|------|---------|
| **Development** | `./scripts/test-tier1-unit.sh --fast` | <30s | Quick feedback |
| **Specific Test** | `./scripts/test-tier1-unit.sh --file test_name` | <10s | Debug single test |
| **Pre-commit** | `./scripts/test-tier2-integration.sh` | 2-3m | Integration check |
| **Feature Testing** | `./scripts/test-tier3-e2e.sh --smoke` | 1-2m | Critical paths |
| **Full Validation** | `./scripts/test-all-tiers.sh` | 5-10m | Complete suite |
| **Performance** | `./scripts/test-all-tiers.sh --performance` | 5-10m | Performance check |

## 🏗️ 3-Tier System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   TIER 1 (UNIT)                            │
│  • Speed: <1s per test                                     │
│  • Isolated: No external deps                              │
│  • Mocking: Allowed                                        │
│  • Focus: Individual components                            │
│  Command: ./scripts/test-tier1-unit.sh                     │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                TIER 2 (INTEGRATION)                        │
│  • Speed: <5s per test                                     │
│  • Real Services: PostgreSQL, Redis, MinIO                 │
│  • NO MOCKING: Use real infrastructure                     │
│  • Focus: Service interactions                             │
│  Command: ./scripts/test-tier2-integration.sh              │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                   TIER 3 (E2E)                             │
│  • Speed: <10s per test                                    │
│  • Complete Stack: All services + workflows                │
│  • NO MOCKING: End-to-end real scenarios                   │
│  • Focus: User workflows                                   │
│  Command: ./scripts/test-tier3-e2e.sh                      │
└─────────────────────────────────────────────────────────────┘
```

## 🚨 Common Issues & Solutions

### ❌ Unit Tests Timeout (>1s)
**Problem**: Tests taking too long
**Solution**:
```bash
./scripts/test-tier1-unit.sh --performance --verbose
# Look for slow tests, optimize or move to integration tier
```

### ❌ Infrastructure Not Ready
**Problem**: Integration tests failing
**Solution**:
```bash
./scripts/test-tier2-integration.sh --setup
./scripts/test-tier2-integration.sh --check
```

### ❌ Tests Flaky
**Problem**: Inconsistent test results
**Solution**:
```bash
./scripts/test-all-tiers.sh --continue-on-failure
# Identify patterns, check resource constraints
```

## 📊 Understanding Results

### ✅ Good Test Run
```
✓ Tier 1 (Unit): PASSED (466/480 tests, 30s)
✓ Tier 2 (Integration): PASSED (All services, 2m)
✓ Tier 3 (E2E): PASSED (Complete workflows, 5m)
```

### ⚠️ Performance Issues
```
✗ Tier 1 (Unit): FAILED (14 timeout violations)
```
**Action**: Optimize slow unit tests or move to appropriate tier

### ❌ Infrastructure Issues
```
✗ Tier 2 (Integration): FAILED (PostgreSQL not available)
```
**Action**: Run `./scripts/test-tier2-integration.sh --setup`

## 🎛️ Advanced Usage

### Development Workflow
```bash
# Start development session
./scripts/test-tier1-unit.sh --fast

# Test specific feature
./scripts/test-tier1-unit.sh --file test_my_feature --verbose

# Pre-commit validation
./scripts/test-tier2-integration.sh

# Feature complete validation
./scripts/test-tier3-e2e.sh --smoke
```

### CI/CD Pipeline
```bash
# Stage 1: Fast validation
./scripts/test-tier1-unit.sh --fast --coverage

# Stage 2: Integration validation
./scripts/test-tier2-integration.sh --setup

# Stage 3: Full validation
./scripts/test-all-tiers.sh --performance
```

### Performance Monitoring
```bash
# Monitor performance trends
./scripts/test-all-tiers.sh --performance > perf_report.txt

# Check tier compliance
./scripts/test-tier1-unit.sh --performance --verbose
```

## 🏆 Gold Standard Compliance

Your tests achieve Gold Standard when:

✅ **Tier 1**: <1000ms per test, isolated, fast feedback
✅ **Tier 2**: <5000ms per test, real services, NO MOCKING
✅ **Tier 3**: <10000ms per test, complete workflows, NO MOCKING
✅ **Coverage**: >95% pass rate with performance compliance
✅ **Infrastructure**: Automated Docker service management
✅ **Monitoring**: Real-time performance validation

## 📚 Need More Help?

- **Full Documentation**: `tests/GOLD_STANDARD_TESTING_SYSTEM.md`
- **Script Help**: `./scripts/test-all-tiers.sh --help`
- **Fixture Usage**: `tests/fixtures/consolidated_test_fixtures.py`
- **Performance Details**: `tests/utils/test_performance_monitor.py`

---
**Quick Start Version**: 1.0 | **Last Updated**: 2025-09-29
