# Production Testing

You are an expert in production-quality testing for Kailash SDK. Guide users through comprehensive testing strategies, test organization, and quality assurance.

## Core Responsibilities

### 1. 3-Tier Testing Strategy

- **Tier 1**: Unit tests - Individual node testing
- **Tier 2**: Integration tests - Multi-node workflows with real infrastructure
- **Tier 3**: End-to-end tests - Complete workflows with external services

### 2. Tier 1: Unit Tests (Node-Level)

```python
import pytest
from kailash.nodes.code import PythonCodeNode

def test_python_code_node_execution():
    """Test individual node execution."""
    node = PythonCodeNode("test_node", {
        "code": "result = {'status': 'success', 'value': input_value * 2}"
    })

    result = node.execute({"input_value": 10})

    assert result["result"]["status"] == "success"
    assert result["result"]["value"] == 20

def test_python_code_node_error_handling():
    """Test node error handling."""
    node = PythonCodeNode("test_node", {
        "code": "result = 1 / 0"  # Division by zero
    })

    with pytest.raises(ZeroDivisionError):
        node.execute({})

def test_parameter_validation():
    """Test parameter validation."""
    from kailash.nodes.api import HTTPRequestNode

    node = HTTPRequestNode("test_node", {
        "url": "https://api.example.com",
        "method": "GET"
    })

    # Valid execution
    result = node.execute({})
    assert "response" in result

    # Test with missing URL
    with pytest.raises(ValueError):
        invalid_node = HTTPRequestNode("test_node", {
            "method": "GET"  # Missing required URL
        })
```

### 3. Tier 2: Integration Tests (Real Infrastructure)

```python
import pytest
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

@pytest.fixture
def test_database():
    """Setup test database - Real infrastructure recommended."""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE test_data (
            id INTEGER PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.execute("INSERT INTO test_data VALUES (1, 'test')")
    conn.commit()
    yield conn
    conn.close()

def test_database_workflow_integration(test_database):
    """Test workflow with real database - NO MOCKS."""
    workflow = WorkflowBuilder()

    workflow.add_node("SQLReaderNode", "reader", {
        "connection_string": "sqlite:///:memory:",
        "query": "SELECT * FROM test_data"
    })

    workflow.add_node("PythonCodeNode", "processor", {
        "code": """
result = {
    'count': len(data),
    'values': [row['value'] for row in data]
}
"""
    })

    workflow.add_connection("reader", "processor", "data", "data")

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build(), parameters={
        "reader": {"connection_string": "sqlite:///:memory:"}
    })

    assert results["processor"]["result"]["count"] > 0
    assert "test" in results["processor"]["result"]["values"]

def test_api_workflow_integration():
    """Test workflow with real API - NO MOCKS."""
    workflow = WorkflowBuilder()

    # Use real test API (jsonplaceholder)
    workflow.add_node("HTTPRequestNode", "api_call", {
        "url": "https://jsonplaceholder.typicode.com/posts/1",
        "method": "GET"
    })

    workflow.add_node("PythonCodeNode", "validator", {
        "code": """
result = {
    'valid': isinstance(response, dict),
    'has_title': 'title' in response,
    'title': response.get('title')
}
"""
    })

    workflow.add_connection("api_call", "validator", "response", "response")

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    assert results["validator"]["result"]["valid"]
    assert results["validator"]["result"]["has_title"]
```

### 4. Tier 3: End-to-End Tests

```python
@pytest.mark.e2e
def test_complete_etl_pipeline():
    """Test complete ETL pipeline end-to-end."""
    workflow = WorkflowBuilder()

    # Extract
    workflow.add_node("CSVReaderNode", "extract", {
        "file_path": "tests/data/test_input.csv"
    })

    # Transform
    workflow.add_node("PythonCodeNode", "transform", {
        "code": """
import pandas as pd  # requires: pip install pandas
df = pd.DataFrame(data)

# Clean and transform
df['value'] = df['value'].fillna(0)
df['category'] = df['category'].str.upper()

result = {'transformed_data': df.to_dict('records')}
"""
    })

    # Load
    workflow.add_node("CSVWriterNode", "load", {
        "file_path": "tests/output/test_output.csv"
    })

    # Connections
    workflow.add_connection("extract", "transform", "data", "data")
    workflow.add_connection("transform", "load", "result", "data")

    # Execute
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    # Verify output file exists and has correct data
    import os
    assert os.path.exists("tests/output/test_output.csv")

    # Verify data integrity
    output_df = pd.read_csv("tests/output/test_output.csv")
    assert len(output_df) > 0
    assert 'category' in output_df.columns
    assert all(output_df['category'].str.isupper())
```

### 5. Test Organization (Real infrastructure recommended Policy)

```python
# tests/unit/test_nodes.py
"""Unit tests for individual nodes."""

# tests/integration/test_workflows.py
"""Integration tests with real infrastructure."""

# tests/e2e/test_complete_flows.py
"""End-to-end tests of complete workflows."""

# conftest.py
import pytest

@pytest.fixture(scope="session")
def test_database():
    """Real test database - Real infrastructure recommended."""
    # Setup real database
    pass

@pytest.fixture
def cleanup_files():
    """Clean up test files after tests."""
    yield
    # Cleanup logic
    import os
    import shutil
    if os.path.exists("tests/output"):
        shutil.rmtree("tests/output")
```

### 6. Async Testing

```python
import pytest
from kailash.runtime import AsyncLocalRuntime

@pytest.mark.asyncio
async def test_async_workflow():
    """Test async workflow execution."""
    workflow = WorkflowBuilder()

    workflow.add_node("PythonCodeNode", "async_processor", {
        "code": """
import asyncio
await asyncio.sleep(0.1)
result = {'processed': True}
"""
    })

    runtime = AsyncLocalRuntime()
    results = await runtime.execute_workflow_async(workflow.build(), inputs={})

    assert results["async_processor"]["result"]["processed"]

@pytest.mark.asyncio
async def test_async_api_calls():
    """Test async API calls."""
    workflow = WorkflowBuilder()

    workflow.add_node("HTTPRequestNode", "api_call", {
        "url": "https://jsonplaceholder.typicode.com/posts/1",
        "method": "GET"
    })

    runtime = AsyncLocalRuntime()
    results = await runtime.execute_workflow_async(workflow.build(), inputs={})

    assert "api_call" in results
    assert results["api_call"]["status_code"] == 200
```

### 7. Test Coverage and Assertions

```python
def test_comprehensive_workflow_coverage():
    """Test all execution paths in workflow."""
    workflow = WorkflowBuilder()

    workflow.add_node("PythonCodeNode", "input", {
        "code": "result = {'value': input_value}"
    })

    workflow.add_node("SwitchNode", "router", {
        "cases": [
            {"condition": "value > 50", "target": "high_path"},
            {"condition": "value <= 50", "target": "low_path"}
        ]
    })

    workflow.add_node("PythonCodeNode", "high_path", {
        "code": "result = {'category': 'high', 'value': value}"
    })

    workflow.add_node("PythonCodeNode", "low_path", {
        "code": "result = {'category': 'low', 'value': value}"
    })

    runtime = LocalRuntime()

    # Test high path
    results_high, _ = runtime.execute(workflow.build(), parameters={
        "input": {"input_value": 75}
    })
    assert results_high["high_path"]["result"]["category"] == "high"

    # Test low path
    results_low, _ = runtime.execute(workflow.build(), parameters={
        "input": {"input_value": 25}
    })
    assert results_low["low_path"]["result"]["category"] == "low"

    # Test boundary
    results_boundary, _ = runtime.execute(workflow.build(), parameters={
        "input": {"input_value": 50}
    })
    assert results_boundary["low_path"]["result"]["category"] == "low"
```

### 8. Production Test Best Practices

```python
# 1. Use fixtures for setup/teardown
@pytest.fixture(scope="module")
def production_config():
    """Production-like configuration."""
    return {
        "database_url": "sqlite:///:memory:",
        "api_timeout": 30,
        "retry_attempts": 3
    }

# 2. Test error scenarios
def test_error_recovery():
    """Test workflow error recovery."""
    workflow = WorkflowBuilder()

    workflow.add_node("PythonCodeNode", "risky_op", {
        "code": """
try:
    result = {'value': 1 / divisor}
except ZeroDivisionError:
    result = {'value': 0, 'error': 'division_by_zero'}
"""
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build(), parameters={
        "risky_op": {"divisor": 0}
    })

    assert results["risky_op"]["result"]["error"] == "division_by_zero"

# 3. Test performance
import time

def test_workflow_performance():
    """Test workflow execution performance."""
    workflow = create_complex_workflow()

    start_time = time.time()
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
    execution_time = time.time() - start_time

    assert execution_time < 5.0  # Should complete in under 5 seconds
```

## Critical Testing Rules

1. **Real infrastructure recommended in Tiers 2-3**: Use real infrastructure
2. **Test All Paths**: Ensure complete code coverage
3. **Real Data**: Use realistic test data
4. **Error Scenarios**: Test failures, not just successes
5. **Async Testing**: Use pytest-asyncio for async workflows
6. **Cleanup**: Always clean up test artifacts

## When to Engage

- User asks about "production testing", "quality assurance", "testing strategy"
- User needs testing guidance
- User wants to improve test coverage
- User has questions about test organization

## 9. Infrastructure Testing Patterns

Testing infrastructure stores (ConnectionManager, StoreFactory, task queues, idempotency) requires async fixtures, singleton cleanup, and transaction atomicity verification. All infrastructure tests run against real databases -- Real infrastructure recommended.

### Async Test Fixtures with ConnectionManager

```python
import pytest
from kailash.db.connection import ConnectionManager

@pytest.fixture
async def conn():
    """Provide an initialized in-memory SQLite ConnectionManager."""
    cm = ConnectionManager("sqlite:///:memory:")
    await cm.initialize()
    yield cm
    await cm.close()

@pytest.fixture
async def conn_with_table(conn):
    """ConnectionManager with a pre-created test table."""
    await conn.execute(
        "CREATE TABLE test_store ("
        "id TEXT PRIMARY KEY, "
        "data TEXT NOT NULL, "
        "status TEXT NOT NULL DEFAULT 'active'"
        ")"
    )
    yield conn

@pytest.mark.asyncio
async def test_insert_and_fetch(conn_with_table):
    """Test basic CRUD against real database."""
    await conn_with_table.execute(
        "INSERT INTO test_store (id, data) VALUES (?, ?)",
        "record-1", '{"key": "value"}'
    )
    row = await conn_with_table.fetchone(
        "SELECT * FROM test_store WHERE id = ?", "record-1"
    )
    assert row is not None
    assert row["data"] == '{"key": "value"}'
```

### StoreFactory.reset() for Singleton Cleanup

The `StoreFactory` is a singleton. Tests MUST reset it between test cases to prevent state leakage:

```python
import pytest
from kailash.infrastructure.factory import StoreFactory

@pytest.fixture(autouse=True)
async def reset_store_factory():
    """Reset the StoreFactory singleton between every test."""
    yield
    # Cleanup: close the old instance before resetting
    old = StoreFactory._instance
    if old is not None:
        if old._conn is not None:
            await old.close()
    StoreFactory.reset()

@pytest.mark.asyncio
async def test_level0_returns_sqlite_event_store():
    """StoreFactory with no URL returns Level 0 defaults."""
    factory = StoreFactory(database_url=None)
    await factory.initialize()
    assert factory.is_level0
    event_store = await factory.create_event_store()
    # Level 0: SqliteEventStoreBackend (not DBEventStoreBackend)
    assert type(event_store).__name__ == "SqliteEventStoreBackend"

@pytest.mark.asyncio
async def test_level1_returns_db_event_store():
    """StoreFactory with SQLite URL returns Level 1 DB backends."""
    factory = StoreFactory(database_url="sqlite:///:memory:")
    await factory.initialize()
    assert not factory.is_level0
    event_store = await factory.create_event_store()
    assert type(event_store).__name__ == "DBEventStoreBackend"
```

### Transaction Atomicity Verification

Test that multi-statement operations are truly atomic:

```python
@pytest.mark.asyncio
async def test_transaction_rollback_on_error(conn):
    """Verify transaction rolls back ALL statements on failure."""
    await conn.execute(
        "CREATE TABLE atomic_test (id TEXT PRIMARY KEY, val INTEGER)"
    )
    await conn.execute(
        "INSERT INTO atomic_test VALUES (?, ?)", "existing", 1
    )

    # Attempt a transaction that fails partway through
    with pytest.raises(Exception):
        async with conn.transaction() as tx:
            await tx.execute(
                "INSERT INTO atomic_test VALUES (?, ?)", "new-row", 2
            )
            # This will fail (duplicate primary key)
            await tx.execute(
                "INSERT INTO atomic_test VALUES (?, ?)", "existing", 3
            )

    # Verify 'new-row' was NOT persisted (transaction rolled back)
    row = await conn.fetchone(
        "SELECT * FROM atomic_test WHERE id = ?", "new-row"
    )
    assert row is None, "Transaction should have rolled back the first INSERT"

@pytest.mark.asyncio
async def test_dequeue_atomicity(conn):
    """Verify task queue dequeue is atomic -- no double-processing."""
    from kailash.infrastructure.task_queue import SQLTaskQueue

    queue = SQLTaskQueue(conn)
    await queue.initialize()

    # Enqueue one task
    task_id = await queue.enqueue({"job": "test"})

    # Dequeue it
    task = await queue.dequeue(worker_id="worker-1")
    assert task is not None
    assert task.task_id == task_id

    # Second dequeue should return None (task already claimed)
    task2 = await queue.dequeue(worker_id="worker-2")
    assert task2 is None, "Task should not be dequeued twice"
```

### Infrastructure Red Team Checklist

When reviewing SQL infrastructure code, verify:

- [ ] All table/column names pass through `_validate_identifier()`
- [ ] All multi-statement operations use `conn.transaction()`
- [ ] All SQL uses `?` canonical placeholders (no `$1` or `%s`)
- [ ] DDL uses `dialect.blob_type()` not hardcoded `BLOB`
- [ ] Upserts use `dialect.upsert()` not check-then-act
- [ ] In-memory stores have bounded size with LRU eviction
- [ ] No `AUTOINCREMENT` in shared DDL
- [ ] Database drivers imported lazily (inside methods)
- [ ] `FOR UPDATE SKIP LOCKED` only used inside transactions
- [ ] StoreFactory singleton is reset in test fixtures

> For the full set of infrastructure SQL rules, see `.claude/rules/infrastructure-sql.md`.
> For the complete enterprise infrastructure skills, see `.claude/skills/15-enterprise-infrastructure/`.

## Integration with Other Skills

- Route to **testing-best-practices** for testing strategies
- Route to **test-organization** for Real infrastructure recommended policy
- Route to **regression-testing** for regression testing
- Route to **tdd-implementer** for test-first development
- Route to **infrastructure-specialist** for infrastructure store testing patterns
