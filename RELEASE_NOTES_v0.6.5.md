# Release v0.6.5 - Enterprise AsyncSQL & Production Testing Excellence

## 🎯 Overview

This release delivers enterprise-grade enhancements to AsyncSQL with optimistic locking, comprehensive testing improvements achieving 100% pass rate, and production-ready documentation. All features are fully backward compatible.

## ⭐ Major Features

### 🚀 AsyncSQL Enterprise Enhancements

#### Transaction Management Modes
- **Auto Mode (default)**: Each query in its own transaction with automatic commit/rollback
- **Manual Mode**: Explicit transaction control for multi-step operations
- **None Mode**: No transaction wrapping for read-only operations

```python
# Manual transaction example
node = AsyncSQLDatabaseNode(database_type="postgresql", transaction_mode="manual")
await node.begin_transaction()
try:
    await node.async_run(query="UPDATE accounts SET balance = balance - 100 WHERE id = 1")
    await node.async_run(query="UPDATE accounts SET balance = balance + 100 WHERE id = 2")
    await node.commit()
except Exception:
    await node.rollback()
```

#### Optimistic Locking Integration
- Version-based concurrency control with conflict detection
- Four conflict resolution strategies: fail-fast, retry, merge, last-writer-wins
- Batch operations support with per-record conflict handling
- Performance metrics for lock contention monitoring

```python
lock_manager = OptimisticLockingNode(default_conflict_resolution=ConflictResolution.RETRY)
result = await lock_manager.execute(
    action="update_with_version",
    table_name="users",
    record_id=123,
    update_data={"name": "Updated"},
    expected_version=current_version
)
```

#### Advanced Parameter Handling
- PostgreSQL ANY() array operations with automatic conversion
- Complex data type serialization (JSON, arrays, dates/datetime)
- Named parameter support with database-specific conversion

```python
# PostgreSQL array example
await node.async_run(
    query="SELECT * FROM users WHERE id = ANY(:user_ids)",
    params={"user_ids": [1, 2, 3, 4, 5]}  # Auto-converted
)
```

### 🧪 Testing Excellence

- **100% Test Pass Rate**: All AsyncSQL unit, integration, and E2E tests passing
- **Strict Policy Compliance**: Zero mocking in integration/E2E tests
- **Enhanced Test Infrastructure**: Improved Docker container management
- **Documentation Validation**: All code examples tested and working

## 🐛 Bug Fixes

- **PostgreSQL ANY() Parameters**: Fixed list parameter conversion for array operations
- **DNS/Network Error Retries**: Added missing error patterns for network failures
- **Optimistic Locking Version Check**: Fixed WHERE clause detection for version validation
- **DataFrame JSON Serialization**: Fixed handling of date/datetime in DataFrames
- **E2E Transaction Timeouts**: Added timeout configurations to prevent deadlocks
- **Pool Sharing Event Loop Issues**: Fixed event loop detection for shared connection pools

## 📚 Documentation

### New Documentation
- **[AsyncSQL Enterprise Patterns Cheatsheet](sdk-users/cheatsheet/047-asyncsql-enterprise-patterns.md)**: Production patterns with transactions and locking
- **[OptimisticLockingNode Guide](sdk-users/nodes/03-data-nodes.md#optimisticlockingnode-)**: Complete concurrency control documentation
- **[Updated Node Selection Guide](sdk-users/nodes/node-selection-guide.md)**: AsyncSQL promoted to ⭐⭐⭐ enterprise status

### Enhanced Documentation
- Complete AsyncSQL documentation rewrite with all enterprise features
- Cross-referenced examples validated with temporary tests
- Updated cheatsheet index with new enterprise patterns

## 🔧 Technical Details

### Test Results
- **Unit Tests**: 16/16 AsyncSQL tests passing (< 1s execution)
- **Integration Tests**: 100% pass rate with real PostgreSQL (no mocks)
- **E2E Tests**: Complete transaction scenarios validated
- **Documentation Tests**: All examples validated programmatically

### Internal Improvements
- Enhanced retry logic with DNS/network error handling
- Improved connection pool sharing across workflow instances
- Better event loop management for async operations
- Stricter query validation with admin operation controls

## 🚀 Upgrade Guide

This release is fully backward compatible. To use the new features:

1. Update to v0.6.5: `pip install kailash==0.6.5`
2. Review the new [AsyncSQL Enterprise Patterns](sdk-users/cheatsheet/047-asyncsql-enterprise-patterns.md)
3. Consider using transaction modes for your use case
4. Implement optimistic locking for concurrent updates

## 📋 What's Next

- Enhanced monitoring and observability features
- Additional database adapter support
- Performance optimization for high-volume operations
- Extended conflict resolution strategies

## 🙏 Acknowledgments

Thanks to all contributors and testers who helped achieve 100% test coverage and ensure production readiness.

---

**Full Changelog**: [v0.6.4...v0.6.5](https://github.com/kailash-sdk/kailash/compare/v0.6.4...v0.6.5)
