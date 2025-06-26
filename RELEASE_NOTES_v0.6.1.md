# Release v0.6.1 - Critical Middleware Fix

## 🚨 Critical Bug Fixes

This patch release fixes critical compatibility issues between middleware components and the v0.6.0 node architecture changes.

### What Was Broken

In v0.6.0, we removed the deprecated `.process()` method from nodes in favor of `.execute()`. However, several middleware components were still calling the old method, causing `AttributeError` exceptions.

### What's Fixed

1. **All Middleware Components Updated**
   - `APIGateway` - Fixed DataTransformer initialization and method calls
   - `AIChatMiddleware` - Updated 7 method calls
   - `AccessControl` - Updated 6 method calls
   - `MCPEnhancedServer` - Updated 2 method calls

2. **DataTransformer Validation**
   - Now correctly validates that transformations are strings
   - Prevents runtime errors from passing functions or dicts

3. **EventStore Async Cleanup**
   - Fixed async task cleanup preventing terminal crashes
   - Resolved "Task was destroyed but it is pending" warnings

## 🐳 New Test Environment

We've created a standardized Docker test environment to eliminate setup confusion:

```bash
./test-env setup   # One-time setup
./test-env up      # Start all services
./test-env test tier2  # Run integration tests
```

No more missing database schemas, Ollama models, or port conflicts!

## 📦 Installation

```bash
pip install kailash-sdk==0.6.1
```

## 🔄 Migration

Most users need no code changes. If you're using the SDK as recommended (through the runtime), everything will work automatically.

See the [migration guide](sdk-users/migration-guides/v0.6.0-to-v0.6.1-migration.md) for details.

## 📊 Test Results

- Unit Tests: 1,367 passed
- Integration Tests: All middleware components verified
- E2E Tests: Complete workflows tested
- No performance regression from v0.6.0

## 🙏 Thanks

Special thanks to users who reported these issues immediately, allowing us to provide this quick fix.

---

**Full Changelog**: https://github.com/yourusername/kailash-python-sdk/compare/v0.6.0...v0.6.1
