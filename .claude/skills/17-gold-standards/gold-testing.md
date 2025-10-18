---
name: gold-testing
description: "Gold standard for testing. Use when asking 'testing standard', 'testing best practices', or 'how to test'."
---

# Gold Standard: Testing

> **Skill Metadata**
> Category: `gold-standards`
> Priority: `HIGH`
> SDK Version: `0.9.25+`

## Testing Principles

### 1. Test-First Development
```python
# ✅ Write test FIRST
def test_user_creation():
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "email": "test@example.com"
    })
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())
    assert results["create"]["email"] == "test@example.com"

# Then implement the workflow
```

### 2. 3-Tier Testing
```python
# Tier 1: Unit (fast, in-memory)
def test_workflow_build():
    workflow = WorkflowBuilder()
    workflow.add_node("LLMNode", "llm", {"prompt": "test"})
    assert workflow.build() is not None

# Tier 2: Integration (real infrastructure)
def test_llm_real_api():
    # Real OpenAI API call
    # Real database
    pass

# Tier 3: E2E (full system)
@pytest.mark.e2e
def test_full_flow():
    # Complete user journey
    pass
```

### 3. NO MOCKING (Tiers 2-3)
```python
# ✅ GOOD: Real infrastructure
def test_database_operations():
    db = DataFlow("sqlite:///test.db")
    # Test with real database

# ❌ BAD: Mocking in integration tests
# @patch("database.query")
# def test_database(mock_query):
#     mock_query.return_value = {...}
```

### 4. Clear Test Names
```python
# ✅ GOOD: Descriptive names
def test_user_creation_with_valid_email_succeeds():
    pass

def test_user_creation_with_invalid_email_fails():
    pass

# ❌ BAD: Generic names
def test_user_1():
    pass
```

### 5. Test Isolation
```python
@pytest.fixture
def test_db():
    """Each test gets clean database"""
    db = DataFlow("sqlite:///:memory:")
    db.initialize_schema()
    yield db
    db.close()

def test_one(test_db):
    # Isolated data
    pass

def test_two(test_db):
    # Clean slate
    pass
```

## Testing Checklist

- [ ] Test written before implementation
- [ ] All 3 tiers covered (unit, integration, E2E)
- [ ] No mocking in Tiers 2-3
- [ ] Clear, descriptive test names
- [ ] Test isolation with fixtures
- [ ] Tests run in CI/CD
- [ ] 80%+ code coverage
- [ ] Error cases tested
- [ ] Edge cases tested
- [ ] Performance tests for critical paths

<!-- Trigger Keywords: testing standard, testing best practices, how to test, testing gold standard -->
