# Kailash Nexus Test Plan

## Overview

This document outlines the comprehensive test plan for Kailash Nexus zero-configuration platform. Tests follow the 3-tier strategy from the SDK testing guidelines.

## Test Coverage Matrix

### Tier 1: Unit Tests (Fast, Isolated)
Location: `tests/unit/`

| Component | Test File | Coverage Areas |
|-----------|-----------|----------------|
| Core | `test_core.py` | Zero-parameter init, workflow registration, health endpoint, progressive enhancement |
| Discovery | `test_discovery.py` | Pattern matching, import handling, validation, auto-registration |
| Plugins | `test_plugins.py` | Plugin base class, auth plugin, monitoring plugin, isolation |
| Channels | `test_channels.py` | Smart defaults, port management, unified config, health checks |

**Execution**: `pytest tests/unit -v`
**Requirements**: No external dependencies, < 1s per test

### Tier 2: Integration Tests (Real Services)
Location: `tests/integration/`

| Component | Test File | Coverage Areas |
|-----------|-----------|----------------|
| Nexus Integration | `test_nexus_integration.py` | Real gateway startup, cross-channel access, session management |
| Channel Integration | `test_channel_integration.py` | API execution, CLI commands, MCP tool discovery |

**Execution**:
```bash
./tests/utils/test-env up
pytest tests/integration -v
./tests/utils/test-env down
```
**Requirements**: Docker services, real SDK components

### Tier 3: End-to-End Tests (Complete Flows)
Location: `tests/e2e/`

| User Persona | Test File | Coverage Areas |
|--------------|-----------|----------------|
| Data Scientist | `test_user_flows.py::TestDataScientistFlow` | Create → Run → Iterate workflow |
| DevOps Engineer | `test_user_flows.py::TestDevOpsEngineerFlow` | Deploy → Monitor → Scale |
| AI Developer | `test_user_flows.py::TestAIDeveloperFlow` | Create → MCP expose → Agent use |
| Production | `test_production_scenarios.py` | Performance, reliability, enterprise |

**Execution**:
```bash
./tests/utils/test-env up
pytest tests/e2e -v
./tests/utils/test-env down
```
**Requirements**: Full infrastructure, real user scenarios

## Test Execution Strategy

### 1. Unit Tests (Run First)
```bash
# Run all unit tests
pytest tests/unit -v

# Run specific component
pytest tests/unit/test_core.py -v

# Run with coverage
pytest tests/unit --cov=nexus --cov-report=html
```

### 2. Integration Tests (Requires Docker)
```bash
# Start test environment
./tests/utils/test-env up

# Run integration tests
pytest tests/integration -v

# Cleanup
./tests/utils/test-env down
```

### 3. E2E Tests (Full Stack)
```bash
# Start test environment
./tests/utils/test-env up

# Run all E2E tests
pytest tests/e2e -v

# Run specific persona
pytest tests/e2e/test_user_flows.py::TestDataScientistFlow -v

# Cleanup
./tests/utils/test-env down
```

### 4. All Tests
```bash
# Run complete test suite
./run_tests.sh

# Or manually
pytest tests/ -v
```

## Performance Baselines

Based on test requirements:

| Metric | Target | Test Coverage |
|--------|--------|---------------|
| Startup Time | < 2 seconds | `test_startup_performance` |
| Request Latency | < 100ms avg | `test_request_latency` |
| Throughput | > 1000 rps | `test_concurrent_requests` |
| Zero Config | 0 parameters | `test_nexus_zero_parameters` |

## Test Data

### Workflow Patterns
- `workflows/*.py` - Standard pattern
- `*.workflow.py` - Suffix pattern
- `workflow_*.py` - Prefix pattern

### Test Workflows
1. Simple: Single PythonCodeNode
2. Complex: Multi-node with connections
3. Error: Workflow that raises exceptions
4. Async: Using AsyncHTTPRequestNode

## CI/CD Integration

```yaml
# .github/workflows/test.yml
name: Test Nexus

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Unit Tests
        run: pytest tests/unit -v

      - name: Integration Tests
        run: |
          ./tests/utils/test-env up
          pytest tests/integration -v
          ./tests/utils/test-env down

      - name: E2E Tests
        run: |
          ./tests/utils/test-env up
          pytest tests/e2e -v
          ./tests/utils/test-env down
```

## Known Issues & Limitations

1. **Port Conflicts**: Tests use ports 8000-8010, ensure they're free
2. **Docker Required**: Integration and E2E tests need Docker
3. **Async Tests**: Some MCP tests require pytest-asyncio
4. **Resource Usage**: E2E tests may use significant CPU/memory

## Test Maintenance

### Adding New Tests
1. Determine tier (unit/integration/e2e)
2. Create in appropriate directory
3. Follow existing patterns
4. Update this document

### Test Review Checklist
- [ ] All public methods have unit tests
- [ ] Integration tests use real services (no mocks)
- [ ] E2E tests cover complete user flows
- [ ] Performance tests validate requirements
- [ ] Error cases are tested
- [ ] Documentation is updated
