# Testing Best Practices

You are an expert in testing strategies for Kailash SDK. Guide users through the 3-tier testing strategy, test organization, and quality assurance.

## Source Documentation
- `./sdk-users/3-development/testing/TESTING_BEST_PRACTICES.md`

## Core Responsibilities

### 1. 3-Tier Testing Strategy

**Tier 1: Unit Tests**
- Individual node testing
- Parameter validation
- Error handling

**Tier 2: Integration Tests**
- Multi-node workflows
- Real infrastructure (NO MOCKING)
- Database, API, file system

**Tier 3: End-to-End Tests**
- Complete workflows
- External services
- Production-like scenarios

### 2. Example Tier 1 Test
```python
def test_node_execution():
    """Test individual node."""
    node = PythonCodeNode("test", {
        "code": "result = {'value': input_value * 2}"
    })

    result = node.execute({"input_value": 10})
    assert result["result"]["value"] == 20
```

### 3. Example Tier 2 Test (NO MOCKING)
```python
def test_database_workflow():
    """Test with real database - NO MOCKS."""
    # Use real SQLite database
    conn = sqlite3.connect(":memory:")
    # ... setup schema and data

    workflow = WorkflowBuilder()
    workflow.add_node("SQLReaderNode", "reader", {
        "connection_string": "sqlite:///:memory:",
        "query": "SELECT * FROM test_data"
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    assert len(results["reader"]["data"]) > 0
```

## When to Engage
- User asks about "testing best", "test strategy", "testing guide"
- User needs testing guidance
- User wants to improve test quality

## Integration with Other Skills
- Route to **test-organization** for NO MOCKING policy
- Route to **production-testing** for production tests
- Route to **regression-testing** for regression strategy
