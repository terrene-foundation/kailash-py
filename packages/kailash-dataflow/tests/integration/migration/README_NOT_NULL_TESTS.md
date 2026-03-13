# NOT NULL Column Addition Integration Tests

This directory contains Tier 2 integration tests for the NOT NULL column addition system in DataFlow, following the Kailash SDK 3-tier testing strategy.

## Test Overview

The `test_not_null_column_addition_integration.py` file provides comprehensive integration tests for:

- **Core NOT NULL Handler**: Planning, validation, and execution of NOT NULL column additions
- **Constraint Validation**: Foreign keys, check constraints, unique constraints, and triggers
- **Default Value Strategies**: Static, computed, function-based, and complex defaults
- **End-to-End Scenarios**: Complete workflows from planning to verification

## 🚨 NO MOCKING Policy

**These tests strictly follow the NO MOCKING policy for Tier 2 integration tests:**

❌ **FORBIDDEN:**
- Mock database connections
- Stubbed SQL responses
- Fake database services
- Bypassed constraint validation

✅ **REQUIRED:**
- Real PostgreSQL database (via Docker)
- Actual database operations
- Real constraint validation
- Genuine performance testing

## Test Environment Setup

### Prerequisites

1. **Docker** must be installed and running
2. **PostgreSQL container** must be available on port 5434
3. **Test database** `kailash_test` with proper permissions

### Quick Setup

```bash
# Navigate to DataFlow root
cd 

# Start test environment (requires Docker daemon running)
./tests/utils/test_env up

# Check status
./tests/utils/test_env status

# Expected output:
# ✅ Docker: Ready
# ✅ PostgreSQL Container: Running
# ✅ PostgreSQL Database: Ready
```

### Manual Setup (if Docker unavailable)

```bash
# Install and start PostgreSQL locally on port 5434
createdb -p 5434 kailash_test
createuser -p 5434 test_user

# Set environment variable
export TEST_DATABASE_URL="postgresql://test_user:test_password@localhost:5434/kailash_test"
```

## Running the Tests

### Individual Test Execution

```bash
# Run specific test class
pytest tests/integration/migration/test_not_null_column_addition_integration.py::TestNotNullColumnHandlerIntegration -v

# Run specific test method
pytest tests/integration/migration/test_not_null_column_addition_integration.py::TestNotNullColumnHandlerIntegration::test_execute_static_default_addition -v

# Run with timeout enforcement
pytest tests/integration/migration/test_not_null_column_addition_integration.py -v --timeout=5
```

### Full Integration Test Suite

```bash
# Run all NOT NULL tests
pytest tests/integration/migration/test_not_null_column_addition_integration.py -v --tb=short

# Run with coverage
pytest tests/integration/migration/test_not_null_column_addition_integration.py --cov=src/dataflow/migrations --cov-report=term-missing
```

### Performance Validation

```bash
# Run performance-focused tests only
pytest tests/integration/migration/test_not_null_column_addition_integration.py -k "performance" -v

# Run large table tests
pytest tests/integration/migration/test_not_null_column_addition_integration.py -k "large_table" -v
```

## Test Structure

### Core Test Classes

1. **`TestNotNullColumnHandlerIntegration`** (Timeout: 30s)
   - Planning and execution of NOT NULL additions
   - Static, function, and computed default strategies
   - Rollback capabilities and error handling

2. **`TestConstraintValidatorIntegration`** (Timeout: 20s)
   - Foreign key constraint validation
   - Check constraint compatibility
   - Unique constraint verification

3. **`TestDefaultValueStrategyManagerIntegration`** (Timeout: 15s)
   - Strategy performance estimation
   - Constraint compatibility validation
   - Strategy selection logic

4. **`TestEndToEndScenarios`** (Timeout: 45s)
   - Complete workflows from planning to verification
   - Performance monitoring for large operations
   - Constraint violation prevention

### Test Scenarios Covered

#### ✅ Static Defaults
```python
# Tests VARCHAR column with static default
column = ColumnDefinition(
    name="status",
    data_type="VARCHAR(20)",
    default_value="pending",
    default_type=DefaultValueType.STATIC
)
```

#### ✅ Function Defaults
```python
# Tests timestamp column with CURRENT_TIMESTAMP
column = ColumnDefinition(
    name="updated_at",
    data_type="TIMESTAMP",
    default_expression="CURRENT_TIMESTAMP",
    default_type=DefaultValueType.FUNCTION
)
```

#### ✅ Computed Defaults
```python
# Tests computed values with CASE expressions
column = ColumnDefinition(
    name="user_tier",
    data_type="VARCHAR(10)",
    default_expression="CASE WHEN id <= 2 THEN 'premium' ELSE 'basic' END",
    default_type=DefaultValueType.COMPUTED
)
```

#### ✅ Foreign Key Validation
```python
# Tests foreign key constraint validation
column = ColumnDefinition(
    name="category_id",
    data_type="INTEGER",
    default_value=1,
    foreign_key_reference="categories.id"
)
```

#### ✅ Batched Execution
```python
# Tests with 5,000+ rows to trigger batching
# Validates batch size optimization
# Monitors performance characteristics
```

#### ✅ Performance Monitoring
```python
# Tests with 10,000 rows
# Validates execution time vs estimates
# Ensures performance within acceptable bounds
```

## Performance Requirements

### Tier 2 Timeout Limits

- **Basic Operations**: < 5 seconds
- **Medium Complexity**: < 20 seconds
- **Large Dataset Tests**: < 45 seconds

### Expected Performance Characteristics

- **Static Defaults**: < 2 seconds for small tables
- **Function Defaults**: < 5 seconds for medium tables
- **Computed Defaults**: < 30 seconds for large tables (with batching)
- **Constraint Validation**: < 1 second per constraint

## Test Data Management

### Isolation Strategy

Tests use **unique table names** with timestamp suffixes to prevent conflicts:

```python
table_name = f"not_null_test_{int(time.time())}"
```

### Cleanup Strategy

Automatic cleanup via pytest fixtures:

```python
@pytest.fixture
async def clean_test_table(db_connection):
    # Setup: Create unique table
    yield table_name
    # Teardown: DROP TABLE CASCADE
    await db_connection.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
```

## Troubleshooting

### Common Issues

1. **Docker not running**
   ```bash
   # Error: Cannot connect to Docker daemon
   # Solution: Start Docker Desktop or Docker daemon
   ```

2. **Port conflicts**
   ```bash
   # Error: Port 5434 already in use
   # Solution: Stop conflicting services or change port
   ./tests/utils/test_env down
   ./tests/utils/test_env remove
   ./tests/utils/test_env up
   ```

3. **Database connection failures**
   ```bash
   # Error: Connection refused
   # Solution: Verify PostgreSQL is ready
   ./tests/utils/test_env status
   ```

4. **Test timeouts**
   ```bash
   # Error: Test exceeded timeout
   # Solution: Check database performance, increase timeout if needed
   pytest --timeout=30 ...
   ```

### Debug Mode

Run tests with verbose logging:

```bash
# Enable debug logging
pytest tests/integration/migration/test_not_null_column_addition_integration.py -v -s --log-cli-level=DEBUG
```

## Integration with CI/CD

### GitHub Actions Setup

```yaml
jobs:
  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_DB: kailash_test
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_password
        ports:
          - 5434:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - name: Run Integration Tests
        run: |
          export TEST_DATABASE_URL="postgresql://test_user:test_password@localhost:5434/kailash_test"
          pytest tests/integration/migration/test_not_null_column_addition_integration.py -v --timeout=30
```

## Best Practices

### When Writing New Tests

1. **Always use real database connections**
2. **Never mock database operations**
3. **Use unique table/resource names**
4. **Implement proper cleanup in fixtures**
5. **Set appropriate timeouts**
6. **Validate both success and failure cases**
7. **Test with realistic data volumes**

### Performance Considerations

1. **Keep test data realistic but minimal**
2. **Use batching for large operations**
3. **Monitor and validate execution times**
4. **Clean up resources promptly**

### Error Handling

1. **Test both happy paths and error conditions**
2. **Validate error messages are helpful**
3. **Ensure rollback works correctly**
4. **Test constraint violation scenarios**

## Related Documentation

- [DataFlow Migration System](/docs/migrations.md)
- [3-Tier Testing Strategy](/docs/testing-strategy.md)
- [NOT NULL Handler Documentation](/src/dataflow/migrations/not_null_handler.py)
- [Test Environment Setup](/tests/utils/README.md)
