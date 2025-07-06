# Tests Directory - Claude Code Instructions

## 🚨 CRITICAL: Always Use Test Environment Before Running Tests

**NEVER run tests directly without the test environment!** The test environment ensures:
- Correct database setup with proper ports (PostgreSQL on 5434, not 5432)
- Ollama models are available
- Redis is running
- All test data is properly seeded

## 🚀 Test Environment Setup (REQUIRED)

```bash
# From project root:
./test-env setup   # One-time setup (downloads models, initializes databases)
./test-env up      # Start all test services (PostgreSQL, Redis, Ollama)
./test-env test tier1  # Run unit tests
./test-env test tier2  # Run integration tests
./test-env test tier3  # Run E2E tests

# Check if services are running:
./test-env status
```

## 📋 Test Execution Checklist

Before running ANY tests:
1. ✅ Run `./test-env up` to start Docker services
2. ✅ Verify services with `./test-env status`
3. ✅ Use `./test-env test tier<N>` for consistent execution

## 🗄️ Database Configuration

The test environment uses:
- **Host**: localhost
- **Port**: 5434 (NOT 5432!)
- **Database**: kailash_test
- **User**: test_user
- **Password**: test_password

## 🧪 Test Structure

```
tests/
├── unit/          # Tier 1: Fast, no external dependencies
├── integration/   # Tier 2: Component interactions with Docker
├── e2e/          # Tier 3: Full end-to-end scenarios
└── utils/        # Test utilities and Docker configuration
```

## ⚠️ Common Issues and Solutions

### "Connection refused" or "Database not found"
- **Solution**: Run `./test-env up` - you forgot to start the test environment

### "Model not found" (Ollama)
- **Solution**: Run `./test-env setup` - models haven't been downloaded

### "Foreign key constraint violation"
- **Solution**: Tests are not using proper test data fixtures from base classes

### "WorkflowConnectionPool is not JSON serializable"
- **Solution**: Use direct asyncpg connections in AsyncPythonCodeNode, not pool objects

## 🔧 E2E Test Infrastructure

For E2E tests, always:
1. Extend `DurableGatewayTestBase` for proper setup/teardown
2. Use `E2ETestConfig.get_async_db_code()` for database operations
3. Use test data helpers (`get_test_customer()`, `create_test_order()`)
4. Never create random IDs - use consistent test data

## 🚨 Node Execution Policy

**ALWAYS use `.execute()` to run nodes:**
```python
# ✅ CORRECT
result = node.execute(params)

# ❌ WRONG
result = node.run(params)
result = node.process(params)
result = node.call(params)
```

## 📝 Quick Reference

```bash
# Start test environment (ALWAYS DO THIS FIRST!)
./test-env up

# Run specific test tiers
./test-env test tier1    # Unit tests only
./test-env test tier2    # Integration tests
./test-env test tier3    # E2E tests

# Run specific test file
pytest tests/e2e/test_durable_gateway_real_world.py -v

# Run with coverage
./test-env test tier2 --cov

# Stop services when done
./test-env down
```

## 🎯 Test Guidelines

1. **Unit Tests (Tier 1)**: Mock external dependencies
2. **Integration Tests (Tier 2)**: Use real Docker services
3. **E2E Tests (Tier 3)**: Full scenarios with real infrastructure

## 📚 Full Documentation

See **[# contrib (removed)/testing/](../# contrib (removed)/testing/)** for complete testing documentation.

## ⚡ Performance Tips

- Run tier 1 tests for fast feedback during development
- Run tier 2/3 tests before committing
- Use `-x` flag to stop on first failure: `pytest -x`
- Use `-k` to run specific tests: `pytest -k "test_order_processing"`
