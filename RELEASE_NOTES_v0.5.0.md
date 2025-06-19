# Kailash SDK v0.5.0 Release Notes

## 🎉 Major Architecture Refactoring Release

We're excited to announce the release of Kailash SDK v0.5.0, a major update that addresses critical architectural issues and delivers significant performance improvements.

### 🚀 Key Highlights

#### 1. **10-100x Performance Boost**
- LRU caching for parameter resolution delivers dramatic speed improvements
- Cached parameter lookups now complete in 1-10μs (previously 100-1000μs)
- Smart cache invalidation ensures consistency

#### 2. **Clear Async/Sync Separation**
- No more runtime surprises with auto-detection
- Explicit `Node` and `AsyncNode` base classes
- Predictable execution patterns
- Better error messages and debugging

#### 3. **Automatic Resource Management**
- Built-in connection pooling
- Automatic cleanup with context managers
- No more memory leaks in long-running applications
- 5-10x throughput improvement from resource reuse

#### 4. **Standardized API**
- Consistent `execute()` method across all nodes
- Clear separation: `run()` for sync, `async_run()` for async
- Better error handling and stack traces
- Backward compatible for basic usage

### 📊 Performance Metrics

```
Parameter Resolution: 10-100x faster
Resource Reuse: 5-10x throughput gain
Async Execution: 3-5x concurrency improvement
Memory Usage: Stable (no leaks)
```

### 🔧 Breaking Changes

1. **AsyncNode Import Path**
   ```python
   # OLD
   from kailash.nodes.base_async import AsyncNode

   # NEW
   from kailash.nodes.base import AsyncNode
   ```

2. **Context Parameter Removed**
   ```python
   # OLD
   def run(self, context, **kwargs):

   # NEW
   def run(self, **kwargs):
   ```

3. **Async Method Name**
   ```python
   # OLD
   async def run_async(self, context, **kwargs):

   # NEW
   async def async_run(self, **kwargs):
   ```

### 🆕 New Features

- **UserManagementNode**: Complete enterprise user management (9 methods)
- **AuditLogNode**: Comprehensive audit trail support (5 methods)
- **ResourcePool**: Thread-safe resource management
- **AsyncResourcePool**: Async-aware resource pooling
- **Parameter Cache**: High-performance LRU caching system

### 📚 Documentation

- Comprehensive migration guide: `sdk-users/migration-guides/v0.5.0-architecture-refactoring.md`
- Updated all SDK documentation for new patterns
- New architectural decision records (ADRs)
- Performance tuning guidelines

### 🐛 Bug Fixes

- Fixed async/sync execution deadlocks
- Resolved memory leaks in resource management
- Fixed parameter resolution bottlenecks
- Corrected circular import issues
- Fixed resource cleanup in error scenarios

### 📈 Migration Path

1. Update your imports for AsyncNode
2. Remove context parameters from run methods
3. Rename async methods if using custom async nodes
4. Enjoy the performance improvements!

See the comprehensive migration guide for detailed instructions.

### 🙏 Thank You

This release represents a major step forward in SDK stability and performance. Thank you to all users who provided feedback and helped identify these critical improvements.

### 📦 Installation

```bash
pip install kailash==0.5.0
```

### 🔗 Resources

- [Full Changelog](changelogs/releases/v0.5.0-2025-01-19.md)
- [Migration Guide](sdk-users/migration-guides/v0.5.0-architecture-refactoring.md)
- [Architecture Documentation](# contrib (removed)/architecture/core-sdk-improvements/ARCHITECTURAL_REFACTORING_TEST_REPORT.md)

---

**Happy Building! 🚀**

The Kailash Team
