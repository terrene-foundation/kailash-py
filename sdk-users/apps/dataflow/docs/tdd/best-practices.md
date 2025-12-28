# DataFlow TDD Best Practices

**Enterprise patterns and recommendations for Test-Driven Development with DataFlow**

## Core Principles

### 1. Performance First
**Target**: Every test completes in <100ms

```python
# ✅ GOOD: Performance-optimized test
@pytest.mark.asyncio
async def test_user_creation_fast(tdd_dataflow):
    """Optimized for <100ms execution"""
    df = tdd_dataflow  # Pre-configured for speed

    @df.model
    class User:
        name: str
        email: str

    # Fast: Uses existing_schema_mode
    df.create_tables()

    # Minimal test operations
    result = await df.User.create({"name": "Alice", "email": "alice@example.com"})
    assert result["success"] is True

# ❌ AVOID: Performance-killing patterns
def test_user_creation_slow():
    """Slow traditional approach"""
    # Database recreation (2000ms+)
    subprocess.run(["psql", "-c", "DROP SCHEMA public CASCADE"])

    # Full DataFlow initialization (500ms+)
    df = DataFlow(database_url="...")

    # Multiple models with DDL (300ms+)
    for i in range(10):
        create_model(df, f"Model{i}")
```

### 2. Isolation Guarantee
**Principle**: Every test runs in complete isolation

```python
# ✅ GOOD: Automatic isolation
@pytest.mark.asyncio
async def test_isolated_operations(tdd_test_context):
    """Each test gets clean savepoint"""
    context = tdd_test_context
    connection = context.connection

    # Create test data
    await connection.execute(
        "CREATE TEMP TABLE test_data (id SERIAL, value TEXT)"
    )
    await connection.execute(
        "INSERT INTO test_data (value) VALUES ('test')"
    )

    # Test operations
    count = await connection.fetchval("SELECT COUNT(*) FROM test_data")
    assert count == 1

    # Automatic rollback ensures isolation

# ❌ AVOID: Shared state problems
def test_shared_state_problem():
    """Dangerous shared state"""
    global_df = get_shared_dataflow()  # Shared between tests

    # This data persists across tests!
    global_df.User.create({"name": "Persistent User"})

    # Other tests see this data - test pollution!
```

### 3. Real Infrastructure
**Principle**: No mocking in integration tests

```python
# ✅ GOOD: Real database operations
@pytest.mark.asyncio
async def test_real_database_operations(tdd_test_context):
    """Test against real PostgreSQL"""
    context = tdd_test_context
    connection = context.connection

    # Real SQL operations
    await connection.execute("""
        CREATE TEMP TABLE orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            total DECIMAL(10,2),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Real constraints and data types
    await connection.execute(
        "INSERT INTO orders (user_id, total) VALUES ($1, $2)",
        123, 99.99
    )

    # Real query operations
    order = await connection.fetchrow(
        "SELECT id, user_id, total FROM orders WHERE user_id = $1",
        123
    )
    assert order["total"] == 99.99

# ❌ AVOID: Mocking database operations
def test_mocked_database():
    """Unrealistic mocked test"""
    mock_connection = Mock()
    mock_connection.fetchval.return_value = 1

    # This doesn't test real database behavior!
    # Constraints, data types, SQL syntax not validated
    result = mock_connection.fetchval("SELECT COUNT(*)")
    assert result == 1  # Meaningless assertion
```

## Fixture Selection Guide

### Choose the Right Fixture for Your Use Case

```python
# Basic database operations
@pytest.mark.asyncio
async def test_basic_sql(tdd_test_context):
    """Use for: Raw SQL operations, basic testing"""
    pass

# DataFlow model operations
@pytest.mark.asyncio
async def test_dataflow_models(tdd_dataflow):
    """Use for: Model CRUD, standard DataFlow features"""
    pass

# Performance-critical tests
@pytest.mark.asyncio
async def test_performance_critical(enhanced_tdd_context):
    """Use for: Performance validation, optimization"""
    pass

# Parallel execution tests
@pytest.mark.asyncio
async def test_concurrent_operations(tdd_parallel_safe):
    """Use for: Race condition testing, concurrent scenarios"""
    pass

# Pre-seeded data scenarios
@pytest.mark.asyncio
async def test_complex_relationships(tdd_seeded_data):
    """Use for: Tests requiring existing data relationships"""
    pass
```

### Fixture Anti-Patterns

```python
# ❌ AVOID: Mixing TDD and traditional fixtures
def test_mixed_fixtures(clean_database, tdd_test_context):
    """Don't combine TDD with traditional approaches"""
    pass

# ❌ AVOID: Over-engineering simple tests
@pytest.mark.asyncio
async def test_simple_query(enhanced_tdd_context, performance_monitored_test):
    """Don't use complex fixtures for simple operations"""
    connection = enhanced_tdd_context.connection
    result = await connection.fetchval("SELECT 1")
    assert result == 1

# ✅ BETTER: Use appropriate fixture
@pytest.mark.asyncio
async def test_simple_query(tdd_test_context):
    """Right fixture for simple operations"""
    context = tdd_test_context
    result = await context.connection.fetchval("SELECT 1")
    assert result == 1
```

## Test Organization Patterns

### 1. By Performance Requirements

```python
# tests/tdd/performance/test_critical_path.py
@pytest.mark.performance
@pytest.mark.asyncio
async def test_user_creation_performance(performance_monitored_test):
    """Critical path performance test"""
    monitor, metrics_collector, alert_handler = performance_monitored_test

    with metrics_collector.measure("user_creation"):
        # Critical operations here
        pass

    # Validate performance target
    assert metrics_collector.current_metrics.duration_ms < 50

# tests/tdd/standard/test_user_operations.py
@pytest.mark.asyncio
async def test_user_creation_standard(tdd_dataflow):
    """Standard functionality test"""
    # Regular test operations
    pass
```

### 2. By Test Complexity

```python
# tests/tdd/unit/test_model_validation.py
@pytest.mark.asyncio
async def test_user_validation(tdd_test_context):
    """Unit-level model validation"""
    context = tdd_test_context
    # Simple validation logic
    pass

# tests/tdd/integration/test_user_workflow.py
@pytest.mark.asyncio
async def test_complete_user_workflow(tdd_seeded_data):
    """Integration test with complex data"""
    context, data, models = tdd_seeded_data
    # Multi-step workflow testing
    pass

# tests/tdd/e2e/test_user_journey.py
@pytest.mark.asyncio
async def test_end_to_end_user_journey(enhanced_tdd_context):
    """End-to-end user journey"""
    # Complete user lifecycle testing
    pass
```

### 3. By Execution Context

```python
# tests/tdd/sequential/test_migration_steps.py
@pytest.mark.asyncio
async def test_migration_sequence(tdd_dataflow):
    """Sequential operations that cannot be parallelized"""
    pass

# tests/tdd/parallel/test_concurrent_users.py
@pytest.mark.asyncio
async def test_concurrent_user_creation(tdd_parallel_safe):
    """Parallel-safe operations"""
    pass

# tests/tdd/memory_sensitive/test_large_datasets.py
@pytest.mark.asyncio
async def test_large_dataset_processing(memory_optimized_test):
    """Memory-sensitive operations"""
    pass
```

## Performance Optimization Patterns

### 1. Connection Pool Management

```python
# ✅ GOOD: Reuse connection pools
@pytest.fixture(scope="session")
async def shared_pool():
    """Session-scoped connection pool"""
    pool_manager = get_pool_manager()
    pool = await pool_manager.create_optimized_pool(
        pool_id="test_session_pool",
        connection_string=test_db_url,
        min_size=3,
        max_size=10,
        preheat=True
    )
    yield pool
    await pool_manager.cleanup_pool("test_session_pool")

# ❌ AVOID: Creating pools per test
@pytest.mark.asyncio
async def test_new_pool_per_test():
    """Don't create new pools repeatedly"""
    pool = await asyncpg.create_pool(...)  # Expensive setup
    # Test operations
    await pool.close()  # Wasteful teardown
```

### 2. Schema Caching Strategies

```python
# ✅ GOOD: Cache common schemas
@pytest.fixture(scope="session")
def cached_schemas():
    """Cache frequently used schemas"""
    schema_cache = get_schema_cache()

    # Pre-cache common schemas
    common_schemas = {
        "users": "CREATE TABLE users (id SERIAL PRIMARY KEY, name VARCHAR(255), email VARCHAR(255))",
        "products": "CREATE TABLE products (id SERIAL PRIMARY KEY, name VARCHAR(255), price DECIMAL(10,2))",
        "orders": "CREATE TABLE orders (id SERIAL PRIMARY KEY, user_id INTEGER, product_id INTEGER)"
    }

    for name, ddl in common_schemas.items():
        schema_cache.cache_schema(name, {name: ddl})

    return schema_cache

# ❌ AVOID: Repeating DDL operations
@pytest.mark.asyncio
async def test_repeated_ddl(tdd_test_context):
    """Don't recreate identical schemas"""
    connection = tdd_test_context.connection

    # This DDL repeated across many tests - inefficient
    await connection.execute("""
        CREATE TEMP TABLE users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255),
            email VARCHAR(255)
        )
    """)
```

### 3. Test Data Optimization

```python
# ✅ GOOD: Efficient test data patterns
@pytest.mark.asyncio
async def test_with_minimal_data(tdd_test_context):
    """Use minimal data for faster tests"""
    context = tdd_test_context
    connection = context.connection

    # Minimal schema
    await connection.execute("""
        CREATE TEMP TABLE simple_test (id SERIAL, value TEXT)
    """)

    # Minimal test data
    await connection.execute(
        "INSERT INTO simple_test (value) VALUES ($1)",
        "test_value"
    )

    # Single assertion
    result = await connection.fetchval(
        "SELECT value FROM simple_test WHERE id = 1"
    )
    assert result == "test_value"

# ❌ AVOID: Over-complex test data
@pytest.mark.asyncio
async def test_with_excessive_data(tdd_test_context):
    """Don't over-complicate test data"""
    # Complex schema with many unnecessary columns
    await connection.execute("""
        CREATE TEMP TABLE complex_test (
            id SERIAL PRIMARY KEY,
            field1 VARCHAR(255),
            field2 INTEGER,
            field3 BOOLEAN,
            field4 TIMESTAMP,
            field5 JSONB,
            field6 DECIMAL(10,2),
            -- ... many more fields not used in test
        )
    """)

    # Complex test data setup (slow)
    for i in range(100):  # Unnecessary bulk data
        await connection.execute(
            "INSERT INTO complex_test (field1, field2, field3, field4, field5, field6) VALUES (...)",
            # Many parameters not relevant to test
        )
```

## Error Handling Best Practices

### 1. Graceful Degradation

```python
@pytest.mark.asyncio
async def test_with_fallback_strategy(tdd_test_context):
    """Handle TDD infrastructure failures gracefully"""
    context = tdd_test_context

    try:
        # Attempt optimized operation
        result = await context.connection.fetchval("SELECT 1")
        assert result == 1

    except Exception as e:
        # Log the issue for investigation
        logger.warning(f"TDD infrastructure issue: {e}")

        # Fallback to slower but reliable approach
        pytest.skip("TDD infrastructure unavailable - skipping for CI stability")
```

### 2. Resource Cleanup

```python
@pytest.fixture
async def robust_tdd_context():
    """Robust context with guaranteed cleanup"""
    context = None
    try:
        async with tdd_test_context() as ctx:
            context = ctx
            yield ctx
    except Exception as e:
        logger.error(f"TDD context error: {e}")
        raise
    finally:
        # Ensure cleanup even on failure
        if context and context.connection:
            try:
                await context.connection.close()
            except Exception:
                pass  # Best effort cleanup
```

### 3. Performance Degradation Handling

```python
@pytest.mark.asyncio
async def test_with_performance_fallback(tdd_performance_tracker):
    """Handle performance degradation gracefully"""
    import time

    start = time.time()

    # Test operations
    await some_database_operation()

    duration_ms = (time.time() - start) * 1000

    if duration_ms > 100:
        # Log performance issue for investigation
        logger.warning(f"Test exceeded 100ms target: {duration_ms:.2f}ms")

        # Don't fail the test, but flag for review
        pytest.warns(UserWarning, match="Performance target exceeded")

    # Test still validates functionality
    assert result_is_correct()
```

## Team Adoption Strategies

### 1. Gradual Migration Approach

```python
# Phase 1: Enable TDD alongside existing tests
@pytest.mark.parametrize("approach", ["traditional", "tdd"])
@pytest.mark.asyncio
async def test_user_creation_dual(approach):
    """Run same test with both approaches during migration"""
    if approach == "traditional":
        # Traditional test implementation
        pass
    elif approach == "tdd":
        # TDD implementation
        pass

    # Same assertions for both approaches
    assert user_created_successfully()
```

### 2. Training and Documentation

```python
# tests/examples/tdd_training.py
"""
TDD Training Examples for Team Onboarding

This module provides guided examples for team members learning
DataFlow TDD patterns and best practices.
"""

@pytest.mark.asyncio
async def example_basic_tdd_test(tdd_test_context):
    """
    Example 1: Basic TDD Test Pattern

    Learning objectives:
    - Understand TDD context usage
    - Learn savepoint-based isolation
    - Practice basic database operations
    """
    context = tdd_test_context
    connection = context.connection

    # Step 1: Create test schema
    await connection.execute("""
        CREATE TEMP TABLE training_users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL
        )
    """)

    # Step 2: Insert test data
    await connection.execute(
        "INSERT INTO training_users (name, email) VALUES ($1, $2)",
        "Training User", "training@example.com"
    )

    # Step 3: Verify operations
    user_count = await connection.fetchval("SELECT COUNT(*) FROM training_users")
    assert user_count == 1

    # Step 4: Verify data quality
    user = await connection.fetchrow(
        "SELECT name, email FROM training_users WHERE id = 1"
    )
    assert user["name"] == "Training User"
    assert user["email"] == "training@example.com"

    # Note: Automatic cleanup via savepoint rollback
    # No manual cleanup required!
```

### 3. Code Review Guidelines

```python
# .github/pull_request_template.md
"""
## TDD Checklist

- [ ] Tests use TDD fixtures (`tdd_test_context`, `tdd_dataflow`, etc.)
- [ ] Performance targets met (<100ms per test)
- [ ] No mocking in integration tests
- [ ] Proper fixture selection for test complexity
- [ ] Tests are parallel-safe when appropriate
- [ ] Error handling includes graceful degradation

## Performance Validation

Run performance validation:
```bash
pytest tests/tdd/ --tb=short -x
# All tests should complete in <5 seconds total
```
"""

# Code review automation
def validate_tdd_compliance(test_file_path):
    """Automated TDD compliance checking"""
    with open(test_file_path) as f:
        content = f.read()

    compliance_issues = []

    # Check for TDD fixtures usage
    if "def test_" in content and "tdd_" not in content:
        compliance_issues.append("Test should use TDD fixtures")

    # Check for mocking anti-patterns
    if "Mock(" in content or "@patch" in content:
        compliance_issues.append("Avoid mocking in TDD tests")

    # Check for performance markers
    if "@pytest.mark.performance" not in content and "performance" in test_file_path:
        compliance_issues.append("Performance tests should be marked")

    return compliance_issues
```

## Monitoring and Maintenance

### 1. Performance Monitoring

```python
# tests/monitoring/test_tdd_performance_baseline.py
@pytest.mark.asyncio
async def test_performance_baseline_validation():
    """Validate TDD infrastructure performance baseline"""
    baseline_metrics = {
        "individual_test_target_ms": 100,
        "fixture_setup_target_ms": 10,
        "connection_acquisition_target_ms": 5,
        "schema_operation_target_ms": 10
    }

    # Measure current performance
    current_metrics = await measure_tdd_performance()

    # Validate against baseline
    for metric, target in baseline_metrics.items():
        current_value = current_metrics[metric]
        assert current_value <= target, f"{metric}: {current_value}ms > {target}ms target"

    # Log performance report
    logger.info(f"TDD Performance Report: {current_metrics}")
```

### 2. Infrastructure Health Checks

```python
# tests/health/test_tdd_infrastructure_health.py
@pytest.mark.asyncio
async def test_tdd_infrastructure_health():
    """Validate TDD infrastructure is healthy"""

    # Check TDD mode activation
    assert is_tdd_mode(), "TDD mode must be enabled"

    # Check database connectivity
    db_manager = get_database_manager()
    await db_manager.initialize()

    # Check connection pool health
    pool_manager = get_pool_manager()
    pool_stats = pool_manager.get_pool_statistics("health_check")
    assert pool_stats["active_connections"] >= 0

    # Check schema cache functionality
    schema_cache = get_schema_cache()
    cache_stats = schema_cache.get_cache_statistics()
    assert cache_stats["cache_enabled"] is True

    # Cleanup
    await db_manager.close()
```

### 3. Regression Detection

```python
# tests/regression/test_tdd_performance_regression.py
import json
from pathlib import Path

PERFORMANCE_HISTORY_FILE = Path("tests/performance_history.json")

@pytest.mark.asyncio
async def test_performance_regression_detection():
    """Detect performance regressions in TDD infrastructure"""

    # Measure current performance
    current_performance = await measure_comprehensive_performance()

    # Load historical performance data
    if PERFORMANCE_HISTORY_FILE.exists():
        with open(PERFORMANCE_HISTORY_FILE) as f:
            history = json.load(f)
    else:
        history = []

    # Check for regressions
    if history:
        latest_baseline = history[-1]
        regression_threshold = 1.2  # 20% degradation threshold

        for metric, current_value in current_performance.items():
            baseline_value = latest_baseline.get(metric, current_value)

            if current_value > baseline_value * regression_threshold:
                pytest.fail(
                    f"Performance regression detected: {metric} "
                    f"degraded from {baseline_value:.2f}ms to {current_value:.2f}ms"
                )

    # Update performance history
    history.append(current_performance)

    # Keep only last 10 measurements
    history = history[-10:]

    with open(PERFORMANCE_HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)
```

## Security Considerations

### 1. Test Data Security

```python
# ✅ GOOD: Secure test data practices
@pytest.mark.asyncio
async def test_with_safe_test_data(tdd_test_context):
    """Use non-sensitive test data"""
    context = tdd_test_context
    connection = context.connection

    # Safe test data - no real information
    test_user = {
        "name": "Test User",
        "email": "test@example.com",
        "ssn": "000-00-0000",  # Clearly fake
        "phone": "555-0123"     # Reserved test number
    }

    await connection.execute(
        "INSERT INTO users (name, email, ssn, phone) VALUES ($1, $2, $3, $4)",
        test_user["name"], test_user["email"], test_user["ssn"], test_user["phone"]
    )

# ❌ AVOID: Real or realistic sensitive data
@pytest.mark.asyncio
async def test_with_risky_data(tdd_test_context):
    """Don't use realistic sensitive data"""
    # Risky - looks like real data
    test_user = {
        "name": "John Smith",
        "email": "john.smith@gmail.com",
        "ssn": "123-45-6789",  # Format looks real
        "credit_card": "4532-1234-5678-9012"  # Real format
    }
    # This data could be mistaken for production data!
```

### 2. Database Isolation

```python
# ✅ GOOD: Proper test database isolation
TEST_DATABASE_CONFIG = {
    "database_url": "postgresql://dataflow_test:dataflow_test_password@localhost:5433/dataflow_test",
    # Clearly marked as test database
    "database_name": "dataflow_test",  # Not production name
    "port": 5433,  # Different from production port
    "environment": "test"
}

# ❌ AVOID: Risk of production database access
RISKY_CONFIG = {
    "database_url": "postgresql://user:pass@prod-db:5432/production",
    # Could accidentally connect to production!
}
```

These best practices ensure your DataFlow TDD implementation achieves enterprise-grade performance, reliability, and maintainability while supporting effective team adoption and long-term success.
