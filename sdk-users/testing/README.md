# SDK Testing Documentation

This directory contains the testing strategy and policies for the Kailash SDK.

## Key Documents

### 1. [regression-testing-strategy.md](regression-testing-strategy.md)
Defines our three-tier testing approach:
- **Tier 1**: Unit tests (fast, no dependencies)
- **Tier 2**: Integration tests (component interactions)
- **Tier 3**: E2E tests (full scenarios with Docker)

### 2. [test-organization-policy.md](test-organization-policy.md)
Enforces test file organization:
- All tests must be in `unit/`, `integration/`, or `e2e/`
- No scattered test files in root directory
- Proper classification with pytest markers

### 3. [CLAUDE.md](CLAUDE.md)
Quick reference for AI assistants working with tests.

## Current Test Status

As of latest consolidation:
- **Unit tests**: 109 files, 1223/1241 passing (98.5%)
- **Integration tests**: 40 files, 31/36 passing (86%)
- **E2E tests**: 33 files (Docker-dependent)
- **Total**: 182 properly organized test files

## Test Execution

```bash
# Run all Tier 1 tests (fast, for CI)
pytest tests/unit/ -m "not (slow or integration or e2e or requires_docker)"

# Run all Tier 2 tests
pytest tests/integration/ -m "not (slow or e2e or requires_docker)"

# Run specific component tests
pytest tests/unit/nodes/ai/

# Run with coverage
pytest --cov=kailash --cov-report=html
```

## Organization Rules

1. **No test files in `tests/` root** - Only infrastructure files
2. **Mirror source structure** - Easy to find related tests
3. **Use proper markers** - Enable tier-based execution
4. **Keep essential files only** - Remove old docs and unused scripts
