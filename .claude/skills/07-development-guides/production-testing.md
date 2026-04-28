# Production Testing

3-tier testing strategy for Kailash SDK workflows. Real infrastructure in Tiers 2-3 -- no mocks.

## Tier 1: Unit Tests (Node-Level)

```python
import pytest
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.api import HTTPRequestNode

def test_node_execution():
    node = PythonCodeNode("test_node", {
        "code": "result = {'status': 'success', 'value': input_value * 2}"
    })
    result = node.execute({"input_value": 10})
    assert result["result"]["value"] == 20

def test_node_error_handling():
    node = PythonCodeNode("test_node", {"code": "result = 1 / 0"})
    with pytest.raises(ZeroDivisionError):
        node.execute({})

def test_parameter_validation():
    with pytest.raises(ValueError):
        HTTPRequestNode("test_node", {"method": "GET"})  # Missing URL
```

## Tier 2: Integration Tests (Real Infrastructure)

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

@pytest.fixture
def test_database():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO test_data VALUES (1, 'test')")
    conn.commit()
    yield conn
    conn.close()

def test_database_workflow(test_database):
    workflow = WorkflowBuilder()
    workflow.add_node("SQLReaderNode", "reader", {
        "connection_string": "sqlite:///:memory:",
        "query": "SELECT * FROM test_data"
    })
    workflow.add_node("PythonCodeNode", "processor", {
        "code": "result = {'count': len(data), 'values': [row['value'] for row in data]}"
    })
    workflow.add_connection("reader", "processor", "data", "data")

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build(), parameters={
        "reader": {"connection_string": "sqlite:///:memory:"}
    })
    assert results["processor"]["result"]["count"] > 0

def test_api_workflow():
    workflow = WorkflowBuilder()
    workflow.add_node("HTTPRequestNode", "api_call", {
        "url": "https://jsonplaceholder.typicode.com/posts/1", "method": "GET"
    })
    workflow.add_node("PythonCodeNode", "validator", {
        "code": "result = {'valid': isinstance(response, dict), 'has_title': 'title' in response}"
    })
    workflow.add_connection("api_call", "validator", "response", "response")

    results, _ = LocalRuntime().execute(workflow.build())
    assert results["validator"]["result"]["valid"]
```

## Tier 3: End-to-End Tests

```python
@pytest.mark.e2e
def test_complete_etl_pipeline():
    workflow = WorkflowBuilder()
    workflow.add_node("CSVReaderNode", "extract", {"file_path": "tests/data/test_input.csv"})
    workflow.add_node("PythonCodeNode", "transform", {
        "code": """
import pandas as pd
df = pd.DataFrame(data)
df['value'] = df['value'].fillna(0)
df['category'] = df['category'].str.upper()
result = {'transformed_data': df.to_dict('records')}
"""
    })
    workflow.add_node("CSVWriterNode", "load", {"file_path": "tests/output/test_output.csv"})
    workflow.add_connection("extract", "transform", "data", "data")
    workflow.add_connection("transform", "load", "result", "data")

    LocalRuntime().execute(workflow.build())

    import os, pandas as pd
    assert os.path.exists("tests/output/test_output.csv")
    output_df = pd.read_csv("tests/output/test_output.csv")
    assert len(output_df) > 0
    assert all(output_df['category'].str.isupper())
```

## Test Organization

Layout: `tests/unit/` (Tier 1) | `tests/integration/` (Tier 2) | `tests/e2e/` (Tier 3)

```python
# conftest.py
@pytest.fixture(scope="session")
def test_database():
    pass  # Real database setup

@pytest.fixture
def cleanup_files():
    yield
    import os, shutil
    if os.path.exists("tests/output"):
        shutil.rmtree("tests/output")
```

## Async Testing

```python
from kailash.runtime import AsyncLocalRuntime

@pytest.mark.asyncio
async def test_async_workflow():
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "proc", {
        "code": "import asyncio; await asyncio.sleep(0.1); result = {'processed': True}"
    })
    results = await AsyncLocalRuntime().execute_workflow_async(workflow.build(), inputs={})
    assert results["proc"]["result"]["processed"]
```

## Path Coverage and Best Practices

```python
def test_all_execution_paths():
    """Test every branch through SwitchNode -- high, low, boundary."""
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "input", {"code": "result = {'value': input_value}"})
    workflow.add_node("SwitchNode", "router", {
        "cases": [{"condition": "value > 50", "target": "high"}, {"condition": "value <= 50", "target": "low"}]
    })
    workflow.add_node("PythonCodeNode", "high", {"code": "result = {'cat': 'high'}"})
    workflow.add_node("PythonCodeNode", "low", {"code": "result = {'cat': 'low'}"})
    rt = LocalRuntime()
    assert rt.execute(workflow.build(), parameters={"input": {"input_value": 75}})[0]["high"]["result"]["cat"] == "high"
    assert rt.execute(workflow.build(), parameters={"input": {"input_value": 25}})[0]["low"]["result"]["cat"] == "low"
    assert rt.execute(workflow.build(), parameters={"input": {"input_value": 50}})[0]["low"]["result"]["cat"] == "low"

def test_error_recovery():
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "op", {
        "code": "try:\n    result = {'value': 1 / divisor}\nexcept ZeroDivisionError:\n    result = {'value': 0, 'error': 'division_by_zero'}"
    })
    results, _ = LocalRuntime().execute(workflow.build(), parameters={"op": {"divisor": 0}})
    assert results["op"]["result"]["error"] == "division_by_zero"

def test_workflow_performance():
    import time
    start = time.time()
    LocalRuntime().execute(create_complex_workflow().build())
    assert time.time() - start < 5.0
```

## Infrastructure Testing Patterns

Async fixtures, singleton cleanup, and transaction atomicity. All tests run against real databases.

```python
from kailash.db.connection import ConnectionManager
from kailash.infrastructure.factory import StoreFactory

# --- Fixtures ---
@pytest.fixture
async def conn():
    cm = ConnectionManager("sqlite:///:memory:")
    await cm.initialize()
    yield cm
    await cm.close()

@pytest.fixture(autouse=True)
async def reset_store_factory():
    yield
    old = StoreFactory._instance
    if old is not None and old._conn is not None:
        await old.close()
    StoreFactory.reset()

# --- CRUD ---
@pytest.mark.asyncio
async def test_insert_and_fetch(conn):
    await conn.execute("CREATE TABLE t (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
    await conn.execute("INSERT INTO t (id, data) VALUES (?, ?)", "r1", '{"k":"v"}')
    row = await conn.fetchone("SELECT * FROM t WHERE id = ?", "r1")
    assert row["data"] == '{"k":"v"}'

# --- StoreFactory levels ---
@pytest.mark.asyncio
async def test_store_factory_levels():
    f0 = StoreFactory(database_url=None)
    await f0.initialize()
    assert type(await f0.create_event_store()).__name__ == "SqliteEventStoreBackend"
    await f0.close(); StoreFactory.reset()

    f1 = StoreFactory(database_url="sqlite:///:memory:")
    await f1.initialize()
    assert type(await f1.create_event_store()).__name__ == "DBEventStoreBackend"

# --- Transaction rollback ---
@pytest.mark.asyncio
async def test_transaction_rollback(conn):
    await conn.execute("CREATE TABLE atomic (id TEXT PRIMARY KEY, val INTEGER)")
    await conn.execute("INSERT INTO atomic VALUES (?, ?)", "existing", 1)
    with pytest.raises(Exception):
        async with conn.transaction() as tx:
            await tx.execute("INSERT INTO atomic VALUES (?, ?)", "new", 2)
            await tx.execute("INSERT INTO atomic VALUES (?, ?)", "existing", 3)  # dup PK
    assert await conn.fetchone("SELECT * FROM atomic WHERE id = ?", "new") is None

# --- Task queue atomicity ---
@pytest.mark.asyncio
async def test_dequeue_atomicity(conn):
    from kailash.infrastructure.task_queue import SQLTaskQueue
    queue = SQLTaskQueue(conn)
    await queue.initialize()
    tid = await queue.enqueue({"job": "test"})
    assert (await queue.dequeue(worker_id="w1")).task_id == tid
    assert await queue.dequeue(worker_id="w2") is None
```

### Infrastructure Red Team Checklist

- [ ] Table/column names through `_validate_identifier()`
- [ ] Multi-statement ops use `conn.transaction()`
- [ ] `?` placeholders only (no `$1`/`%s`), `dialect.blob_type()` (no `BLOB`)
- [ ] `dialect.upsert()` (no check-then-act), no `AUTOINCREMENT`
- [ ] In-memory stores bounded with LRU, drivers imported lazily
- [ ] `FOR UPDATE SKIP LOCKED` only inside transactions
- [ ] StoreFactory singleton reset in fixtures

See `rules/infrastructure-sql.md` and `skills/15-enterprise-infrastructure/`
