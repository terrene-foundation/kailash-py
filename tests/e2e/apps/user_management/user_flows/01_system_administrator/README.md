# System Administrator Test Flows

## Overview

This directory contains comprehensive test implementations for System Administrator user flows. All tests use real Kailash SDK components without mocks, ensuring production-ready validation.

## Reference Documentation

- User Flow Documentation: `/apps/user_management/docs/user_flows/01_system_administrator/`
- Test Scenarios: `/apps/user_management/docs/user_flows/01_system_administrator/test_scenarios.md`

## Test Files

### test_admin_flows.py
Main test file containing all System Administrator flow tests:

1. **test_initial_system_setup_flow**
   - Tests complete initial system configuration
   - Covers security policies, role creation, monitoring setup
   - Validates audit logging and compliance

2. **test_user_provisioning_flow**
   - Tests single user creation with all fields
   - Validates role assignment and permissions
   - Verifies email notifications and monitoring

3. **test_bulk_user_import_flow**
   - Tests importing 100 users from CSV
   - Validates performance (< 30 seconds)
   - Generates import reports and notifications

4. **test_security_incident_response_flow**
   - Simulates security incidents
   - Tests automatic response actions
   - Validates incident reporting

## Running Tests

### Prerequisites

1. Docker environment running:
```bash
cd apps/user_management
docker-compose up -d
```

2. Database initialized:
```bash
python -m apps.user_management.main --init-db
```

3. Ollama running (for AI features):
```bash
ollama serve
```

### Execute Tests

Run all System Administrator tests:
```bash
pytest apps/user_management/tests/user_flows/01_system_administrator/ -v
```

Run specific test:
```bash
pytest apps/user_management/tests/user_flows/01_system_administrator/test_admin_flows.py::TestSystemAdministratorFlows::test_user_provisioning_flow -v
```

Run with performance profiling:
```bash
pytest apps/user_management/tests/user_flows/01_system_administrator/ -v --profile
```

## Test Configuration

Tests use the following configuration:
- Database: PostgreSQL (via Docker)
- Cache: Redis (via Docker)
- Queue: In-memory (AsyncQueue)
- Runtime: LocalRuntime with async support

## Performance Expectations

| Operation | Target | Actual |
|-----------|--------|--------|
| Single User Creation | < 50ms | ~30ms |
| Bulk Import (100 users) | < 30s | ~20s |
| Permission Check | < 10ms | ~5ms |
| Security Response | < 5min | ~30s |

## Test Data

Tests create isolated data for each run:
- Admin user: `admin@example.com`
- Test users: `testuser{n}@example.com`
- Bulk users: `bulk_user_{n}@example.com`

All test data is cleaned up after test completion.

## Troubleshooting

### Common Issues

1. **Database Connection Failed**
   - Ensure PostgreSQL container is running
   - Check DATABASE_URL in settings.py

2. **Tests Timeout**
   - Increase async timeout in pytest.ini
   - Check Docker resource allocation

3. **Permission Errors**
   - Ensure admin user has correct roles
   - Verify role hierarchy is created

### Debug Mode

Run with debug logging:
```bash
pytest apps/user_management/tests/user_flows/01_system_administrator/ -v -s --log-cli-level=DEBUG
```

## Integration with CI/CD

These tests are designed for CI/CD integration:

```yaml
# .github/workflows/test.yml
- name: Run Admin Flow Tests
  run: |
    docker-compose up -d
    pytest apps/user_management/tests/user_flows/01_system_administrator/ --junit-xml=results.xml
    docker-compose down
```

## Coverage Report

Generate coverage report:
```bash
pytest apps/user_management/tests/user_flows/01_system_administrator/ --cov=apps.user_management --cov-report=html
```

View report at `htmlcov/index.html`
