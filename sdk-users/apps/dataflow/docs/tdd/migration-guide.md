# DataFlow TDD Migration Guide

Migrate your existing DataFlow test suite from traditional testing (DROP SCHEMA CASCADE) to TDD (<100ms execution) with this comprehensive guide.

## Migration Overview

Transform your test suite from 2000ms+ per test to <100ms with savepoint-based isolation and connection pooling.

### Time Investment
- **Total time**: 4-6 hours for typical test suite
- **ROI**: 20-50x speed improvement, 95% less maintenance

### Migration Phases
1. **Assessment** (30 minutes): Analyze current test suite
2. **Infrastructure Setup** (45 minutes): Configure TDD infrastructure
3. **Test Migration** (2-3 hours): Progressive migration approach
4. **Performance Validation** (30 minutes): Verify improvements
5. **CI/CD Integration** (45 minutes): Update pipelines

## Phase 1: Assessment (30 minutes)

### Analyze Current Test Suite

```python
# assessment_script.py
"""Assess current test suite for TDD migration."""

import os
import time
import subprocess
from pathlib import Path


def assess_test_suite(test_directory="tests/"):
    """Analyze test suite characteristics."""

    metrics = {
        "total_tests": 0,
        "database_tests": 0,
        "uses_drop_schema": 0,
        "avg_execution_time": 0,
        "cleanup_patterns": []
    }

    # Count test files
    test_files = list(Path(test_directory).rglob("test_*.py"))
    metrics["total_tests"] = len(test_files)

    # Analyze for database patterns
    for test_file in test_files:
        content = test_file.read_text()

        # Check for database usage
        if "DataFlow" in content or "postgresql://" in content:
            metrics["database_tests"] += 1

        # Check for DROP SCHEMA patterns
        if "DROP SCHEMA" in content or "CASCADE" in content:
            metrics["uses_drop_schema"] += 1

        # Check for cleanup patterns
        if "teardown" in content or "cleanup" in content:
            metrics["cleanup_patterns"].append(str(test_file))

    # Measure current execution time
    start = time.time()
    subprocess.run(["pytest", test_directory, "-q"], capture_output=True)
    metrics["avg_execution_time"] = (time.time() - start) / max(metrics["total_tests"], 1)

    return metrics


# Run assessment
metrics = assess_test_suite()
print(f"""
Test Suite Assessment Results:
==============================
Total tests: {metrics['total_tests']}
Database tests: {metrics['database_tests']}
Using DROP SCHEMA: {metrics['uses_drop_schema']}
Average execution time: {metrics['avg_execution_time']:.2f}s
Cleanup patterns found: {len(metrics['cleanup_patterns'])}

Migration potential: {metrics['uses_drop_schema'] * 2000}ms savings
Expected speedup: {metrics['avg_execution_time'] / 0.1:.1f}x
""")
```

## Phase 2: Infrastructure Setup (45 minutes)

### Install TDD Dependencies

```bash
# Install with TDD support
pip install kailash-dataflow[tdd]

# Or add to requirements
echo "kailash-dataflow[tdd]>=0.9.0" >> requirements-test.txt
```

### Configure Test Database

```python
# conftest.py - Shared test configuration
import os
import pytest
import asyncio
from dataflow import DataFlow
from dataflow.testing.tdd_support import (
    TDDTestContext,
    TDDDatabaseManager,
    get_database_manager
)

# Configure test database
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test"
)

# Enable TDD mode globally
os.environ["DATAFLOW_TDD_MODE"] = "true"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def tdd_database_manager():
    """Session-scoped database manager with connection pooling."""
    manager = get_database_manager()
    await manager.initialize(database_url=TEST_DATABASE_URL)
    yield manager
    await manager.close()


@pytest.fixture
async def tdd_dataflow(tdd_database_manager):
    """Test-scoped DataFlow with automatic isolation."""
    context = TDDTestContext(test_id=f"test_{id(asyncio.current_task())}")

    # Get pooled connection
    connection = await tdd_database_manager.get_test_connection(context)

    # Create DataFlow with TDD optimizations
    db = DataFlow(
        database_url=TEST_DATABASE_URL,
        tdd_mode=True,
        test_context=context,
        connection=connection,  # Reuse pooled connection
        auto_migrate=False,
        existing_schema_mode=True
    )

    # Begin savepoint for isolation
    await context.begin_test_transaction(connection)

    yield db

    # Automatic rollback - no cleanup needed!
    await context.rollback_test_transaction(connection)
    await tdd_database_manager.release_connection(context)
```

## Phase 3: Test Migration (Progressive Approach)

### Pattern 1: Simple CRUD Tests

**Before (Traditional):**
```python
def test_user_creation_traditional(database):
    """Traditional test with manual cleanup."""
    # Setup (expensive)
    database.execute("DROP SCHEMA public CASCADE")  # 2000ms
    database.execute("CREATE SCHEMA public")        # 500ms
    create_tables()                                 # 1000ms

    # Test
    user = create_user("test@example.com")
    assert user.id is not None

    # Teardown (manual)
    database.execute("DELETE FROM users")           # 100ms
    # Total: >3600ms
```

**After (TDD):**
```python
@pytest.mark.asyncio
async def test_user_creation_tdd(tdd_dataflow):
    """TDD test with automatic isolation."""
    # No setup needed - reuses connection

    @tdd_dataflow.model
    class User:
        email: str

    # Use generated nodes
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "email": "test@example.com"
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    assert results["create"]["id"] is not None

    # No teardown - automatic rollback!
    # Total: <100ms (20-50x faster!)
```

### Pattern 2: Complex Integration Tests

**Before:**
```python
def test_order_workflow_traditional():
    """Complex workflow with multiple cleanups."""
    # Setup
    cleanup_all_tables()  # 3000ms
    seed_test_data()      # 2000ms

    # Test workflow
    customer = create_customer()
    order = create_order(customer)
    items = add_order_items(order)
    invoice = generate_invoice(order)

    # Complex assertions
    assert invoice.total == sum(item.price for item in items)

    # Cleanup
    delete_invoices()     # 500ms
    delete_orders()       # 500ms
    delete_customers()    # 500ms
    # Total: >7000ms
```

**After:**
```python
@pytest.mark.asyncio
async def test_order_workflow_tdd(tdd_dataflow):
    """Complex workflow with automatic isolation."""
    # Define models
    @tdd_dataflow.model
    class Customer:
        name: str

    @tdd_dataflow.model
    class Order:
        customer_id: int
        total: float = 0.0

    # Build workflow
    workflow = WorkflowBuilder()

    # All operations in single transaction
    workflow.add_node("CustomerCreateNode", "customer", {"name": "Test"})
    workflow.add_node("OrderCreateNode", "order", {"total": 100.00})
    workflow.add_connection("customer", "id", "order", "customer_id")

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    # Assertions
    assert results["order"]["total"] == 100.00

    # Automatic rollback - all changes reverted!
    # Total: <100ms (70x faster!)
```

### Pattern 3: Parallel Test Execution

**Before:**
```python
# Sequential only - database conflicts prevent parallelization
@pytest.mark.sequential
def test_parallel_unsafe():
    """Can't run in parallel - table conflicts."""
    # Each test needs exclusive schema access
    pass
```

**After:**
```python
@pytest.mark.asyncio
@pytest.mark.parallel  # Safe for parallel execution!
async def test_parallel_safe(tdd_dataflow):
    """Isolated via savepoints - parallel safe."""
    # Each test has isolated transaction
    # Can run N tests simultaneously!
    pass
```

## Phase 4: Performance Validation (30 minutes)

### Benchmark Script

```python
# benchmark_migration.py
"""Compare traditional vs TDD performance."""

import time
import asyncio
import statistics


async def benchmark_test_suite():
    """Benchmark before and after migration."""

    traditional_times = []
    tdd_times = []

    # Benchmark traditional tests
    for _ in range(10):
        start = time.time()
        # Run traditional test
        await run_traditional_test()
        traditional_times.append(time.time() - start)

    # Benchmark TDD tests
    for _ in range(10):
        start = time.time()
        # Run TDD test
        await run_tdd_test()
        tdd_times.append(time.time() - start)

    # Calculate improvements
    traditional_avg = statistics.mean(traditional_times) * 1000  # ms
    tdd_avg = statistics.mean(tdd_times) * 1000  # ms
    improvement = traditional_avg / tdd_avg

    print(f"""
Performance Comparison:
======================
Traditional: {traditional_avg:.2f}ms average
TDD:        {tdd_avg:.2f}ms average
Improvement: {improvement:.1f}x faster
Time saved:  {traditional_avg - tdd_avg:.2f}ms per test

For 100 tests:
Traditional: {traditional_avg * 100 / 1000:.1f} seconds
TDD:        {tdd_avg * 100 / 1000:.1f} seconds
Time saved:  {(traditional_avg - tdd_avg) * 100 / 1000:.1f} seconds
""")


asyncio.run(benchmark_test_suite())
```

## Phase 5: CI/CD Integration (45 minutes)

### Update GitHub Actions

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_password
          POSTGRES_DB: kailash_test
        ports:
          - 5434:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e .[tdd]
          pip install pytest pytest-asyncio pytest-xdist

      - name: Run TDD tests (parallel)
        env:
          DATAFLOW_TDD_MODE: true
          TEST_DATABASE_URL: postgresql://test_user:test_password@localhost:5434/kailash_test
        run: |
          # Run tests in parallel with xdist
          pytest tests/ -n auto --dist loadscope

      - name: Performance validation
        run: |
          python scripts/validate_performance.py
```

### Update Local Development

```bash
# Makefile or scripts/test.sh
test-tdd:
	@echo "Running TDD tests with <100ms target..."
	DATAFLOW_TDD_MODE=true pytest tests/ -v --tb=short

test-parallel:
	@echo "Running tests in parallel..."
	DATAFLOW_TDD_MODE=true pytest tests/ -n auto

test-benchmark:
	@echo "Benchmarking test performance..."
	python scripts/benchmark_migration.py
```

## Migration Checklist

### Pre-Migration
- [ ] Backup existing test suite
- [ ] Document current test execution times
- [ ] Identify database-dependent tests
- [ ] Review cleanup patterns

### Infrastructure
- [ ] Install TDD dependencies
- [ ] Configure test database
- [ ] Setup connection pooling
- [ ] Create base fixtures

### Test Migration
- [ ] Migrate simple CRUD tests
- [ ] Migrate integration tests
- [ ] Migrate complex workflows
- [ ] Remove manual cleanup code
- [ ] Enable parallel execution

### Validation
- [ ] All tests passing
- [ ] <100ms average execution
- [ ] Parallel execution working
- [ ] No test pollution/conflicts

### CI/CD
- [ ] Update GitHub Actions
- [ ] Configure parallel execution
- [ ] Add performance gates
- [ ] Update documentation

## Troubleshooting

### Issue: Tests still slow after migration
```python
# Check TDD mode is active
assert os.environ.get("DATAFLOW_TDD_MODE") == "true"
assert tdd_dataflow._tdd_mode == True

# Verify connection pooling
assert tdd_dataflow._connection_pooled == True
```

### Issue: Test isolation failures
```python
# Ensure savepoint isolation
async def test_with_explicit_isolation(tdd_dataflow):
    # Explicit transaction boundary
    async with tdd_dataflow.transaction():
        # Your test code
        pass
    # Automatic rollback here
```

### Issue: Parallel execution conflicts
```python
# Use unique identifiers
context = TDDTestContext(test_id=f"test_{uuid.uuid4()}")
```

## Success Metrics

After migration, you should see:
- ✅ 20-50x faster test execution
- ✅ <100ms per test average
- ✅ Parallel execution capability
- ✅ Zero manual cleanup code
- ✅ Reduced CI/CD time by 90%+

## Support

- [TDD API Reference](api-reference.md)
- [Performance Guide](performance-guide.md)
- [Best Practices](best-practices.md)
- [Troubleshooting](troubleshooting.md)

**Ready to migrate? Start with Phase 1 assessment and see your potential improvements!**
