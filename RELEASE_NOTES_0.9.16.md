# Release Notes - Kailash Core SDK v0.9.16

## 🎯 Release Overview
This release resolves all Tier 1 test failures and significantly improves the async runtime implementation with enterprise-grade connection pooling, retry policies, and resource management.

## ✨ Major Features

### 1. Enhanced Async Runtime with Persistent Mode
- **Persistent LocalRuntime**: New persistent mode for shared event loops and connection pools
- **Connection Pool Manager**: Enterprise-grade connection pool coordination across runtime instances
- **Resource Limit Enforcer**: Comprehensive resource management with configurable limits
- **Retry Policy Engine**: Advanced retry strategies with circuit breaker integration

### 2. Enterprise Runtime Features
- **96.7% reduction in connection growth** (from 30 to 1 connection per operation)
- **Shared connection pooling** across multiple runtime instances
- **Resource monitoring** with health checks and metrics
- **Graceful shutdown** procedures with proper resource cleanup

### 3. Test Infrastructure Improvements
- **100% Tier 1 test compliance** (4,086 tests passing)
- **Proper test organization** with database tests in integration tier
- **Real PostgreSQL usage** in integration tests (no mocking)
- **Performance test suite** with load testing framework

## 🐛 Bug Fixes

### Critical Fixes
- **AsyncSQL Connection Pooling**: Fixed connection pool isolation issue where each `runtime.execute()` created a new event loop
- **Retry Policy**: Fixed attempt counting when resource limits prevent retry
- **RetryAnalytics**: Fixed time series data collection functionality
- **Test Timeouts**: Resolved test timeout issues with optimized retry strategies

### Test Fixes
- Moved database connection tests from unit to integration tests (Tier 2)
- Updated all PostgreSQL configurations to use real test database
- Fixed import order violations in test files
- Removed all mocking from Tier 2 tests per gold standards

## 📊 Performance Improvements

### Connection Pooling Metrics
```
Before: 30 connections created for 30 operations
After:  1 connection reused for 30 operations
Improvement: 96.7% reduction in connection overhead
```

### Test Execution
- Unit tests: 4,086 passed, 13 skipped (~22s)
- Integration tests: All database pool tests passing with real PostgreSQL
- CI/CD: Full compatibility with GitHub Actions workflow

## 🔧 Technical Details

### New Components
- `src/kailash/runtime/resource_manager.py` - Complete resource management system
- `src/kailash/runtime/monitoring/runtime_monitor.py` - Runtime health monitoring
- `tests/performance/` - Full performance testing suite

### Updated Components
- `src/kailash/runtime/local.py` - Enhanced with persistent mode support
- `src/kailash/nodes/data/async_sql.py` - Fixed connection pooling
- `src/kailash/workflow/cyclic_runner.py` - Improved async handling

## 📦 Installation

```bash
pip install kailash==0.9.16
```

## 🔄 Migration Guide

### Using Persistent Runtime Mode
```python
from kailash.runtime.local import LocalRuntime

# Old pattern (creates new event loop each time)
for i in range(10):
    runtime = LocalRuntime()
    results = runtime.execute(workflow.build())  # New connection pool each time

# New pattern (shares event loop and connection pool)
runtime = LocalRuntime(persistent_mode=True)
for i in range(10):
    results = await runtime.execute_async(workflow.build())  # Reuses connection pool
```

### Connection Pool Configuration
```python
runtime = LocalRuntime(
    persistent_mode=True,
    enable_connection_sharing=True,
    connection_pool_config={
        "pool_size": 20,
        "max_overflow": 10,
        "pool_timeout": 30
    }
)
```

## ⚠️ Breaking Changes
None - Full backward compatibility maintained

## 🧪 Testing
- Run unit tests: `pytest tests/unit/ -q`
- Run integration tests: `pytest tests/integration/runtime/ -q`
- Run performance tests: `cd tests/performance && make test`

## 📚 Documentation
- Updated DataFlow specialist guide with connection pooling best practices
- New ADR for enterprise async runtime architecture
- Comprehensive bug analysis in `# contrib (removed)/bug-fix/async-sql-database-node/`

## 🏗️ Dependencies
No new dependencies added

## 🙏 Acknowledgments
Thanks to all contributors and the QA team for identifying and helping resolve the connection pooling issues.

## 📝 Full Changelog
See [GitHub PR #194](https://github.com/terrene-foundation/kailash-py/pull/194) for complete details.

---
**Release Date**: January 13, 2025
**Release Manager**: Terrene Foundation Team