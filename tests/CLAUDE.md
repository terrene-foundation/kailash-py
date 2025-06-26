# Test Suite Quick Reference

## 🚀 Quick Start - Docker Test Environment

**IMPORTANT: Use the standardized test environment to avoid setup issues!**

```bash
# From project root:
./test-env setup   # One-time setup (downloads models, initializes databases)
./test-env up      # Start all test services
./test-env test tier2  # Run integration tests

# Note: test-env script is in tests/utils/ with a symlink in project root
```

**No more manual database setup, no more missing Ollama models, no more port conflicts!**

See [test-environment/README.md](test-environment/README.md) for complete documentation.

## 📚 Full Documentation
See **[# contrib (removed)/testing/](../# contrib (removed)/testing/)** for complete testing guidelines.

## 🚀 Quick Commands

```bash
# Using the test environment script (RECOMMENDED)
./test-env test tier1  # Run Unit tests - Fast, no dependencies
./test-env test tier2  # Run Integration tests - Component interactions
./test-env test tier3  # Run E2E tests - Full scenarios with Docker

# Or manually with pytest
pytest tests/unit/ -m "not (slow or integration or e2e or requires_docker)"
pytest tests/integration/ -m "not (slow or e2e or requires_docker)"
pytest tests/e2e/
```

## 📁 Structure
- `unit/` - Fast isolated tests (Tier 1)
- `integration/` - Component interaction tests (Tier 2)
- `e2e/` - End-to-end scenarios (Tier 3)
- `test-environment/` - Docker setup and configuration

## ⚠️ Key Rules
1. **NO test files in root** - Use unit/, integration/, or e2e/
2. **Mirror source structure** - Easy navigation
3. **Use proper markers** - Enable tier execution
4. **Use real Docker services** - No mocking in integration/e2e tests
