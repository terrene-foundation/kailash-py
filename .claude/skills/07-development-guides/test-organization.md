# Test Organization (NO MOCKING)

You are an expert in test organization and the NO MOCKING policy for Kailash SDK. This is a CRITICAL skill for maintaining test quality.

## Source Documentation
- `./sdk-users/3-development/testing/test-organization-policy.md`

## Core Responsibilities

### 1. NO MOCKING Policy (CRITICAL)

**Why NO MOCKING?**
- Mocks hide real integration issues
- Real infrastructure catches actual bugs
- Production-like testing prevents surprises
- Type mismatches discovered early

**What to Use Instead:**
- **Tier 1**: Test actual node implementation
- **Tier 2**: Use real databases (SQLite :memory:, test DBs)
- **Tier 3**: Use real APIs (test endpoints, staging environments)

### 2. Test Directory Structure
```
tests/
├── unit/              # Tier 1: Individual nodes
│   ├── test_nodes.py
│   └── test_validators.py
├── integration/       # Tier 2: Real infrastructure
│   ├── test_database_workflows.py
│   ├── test_api_workflows.py
│   └── test_file_workflows.py
├── e2e/              # Tier 3: Complete flows
│   ├── test_etl_pipeline.py
│   └── test_production_scenarios.py
└── conftest.py       # Shared fixtures
```

### 3. NO MOCKING Example

**WRONG** (Using mocks):
```python
@patch('requests.get')  # DON'T DO THIS
def test_api_call(mock_get):
    mock_get.return_value = Mock(status_code=200, json=lambda: {"data": "test"})
    # Test code...
```

**CORRECT** (Real infrastructure):
```python
def test_api_call():
    """Use real test API endpoint."""
    workflow = WorkflowBuilder()
    workflow.add_node("HTTPRequestNode", "api", {
        "url": "https://jsonplaceholder.typicode.com/posts/1",  # Real API
        "method": "GET"
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    assert results["api"]["status_code"] == 200
    assert "title" in results["api"]["response"]
```

### 4. Real Database Testing
```python
@pytest.fixture
def test_database():
    """Real SQLite database - NO MOCKING."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE users (id INTEGER, name TEXT)")
    cursor.execute("INSERT INTO users VALUES (1, 'Alice')")
    conn.commit()
    yield conn
    conn.close()

def test_database_workflow(test_database):
    """Test with real database."""
    workflow = WorkflowBuilder()
    workflow.add_node("SQLReaderNode", "reader", {
        "connection_string": "sqlite:///:memory:",
        "query": "SELECT * FROM users"
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    assert len(results["reader"]["data"]) == 1
    assert results["reader"]["data"][0]["name"] == "Alice"
```

### 5. Fixtures for Real Infrastructure
```python
# conftest.py
import pytest

@pytest.fixture(scope="session")
def postgres_test_db():
    """Real PostgreSQL test database."""
    # Create test database
    import psycopg2
    conn = psycopg2.connect("postgresql://localhost/test_db")
    yield conn
    conn.close()

@pytest.fixture
def cleanup_files():
    """Clean up test files after tests."""
    yield
    import shutil
    shutil.rmtree("tests/output", ignore_errors=True)
```

## When to Engage (CRITICAL)
- User asks about "test organization", "NO MOCKING", "3-tier testing"
- User attempts to use mocks (REDIRECT to real infrastructure)
- User needs test structure guidance
- User wants to improve test quality

## Critical Rules
1. **NO MOCKING in Tiers 2-3** - Use real infrastructure
2. **Use test databases** - SQLite :memory:, test instances
3. **Use real test APIs** - jsonplaceholder, staging endpoints
4. **Clean up after tests** - Use fixtures for cleanup

## Integration with Other Skills
- Route to **testing-best-practices** for overall strategy
- Route to **production-testing** for production tests
- Route to **regression-testing** for regression testing
