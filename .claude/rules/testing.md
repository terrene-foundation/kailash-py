# Testing Rules

## Scope
These rules apply to all test files and test-related code.

## MUST Rules

### 1. Test-First Development
Tests MUST be written before implementation for new features.

**Process**:
1. Write failing test that describes expected behavior
2. Implement minimum code to pass test
3. Refactor while keeping tests green

**Applies to**: New features, bug fixes
**Enforced by**: tdd-implementer agent
**Violation**: Code review flag

### 2. Coverage Requirements
Code changes MUST maintain or improve test coverage.

| Code Type | Minimum Coverage |
|-----------|------------------|
| General | 80% |
| Financial | 100% |
| Authentication | 100% |
| Security-critical | 100% |

**Enforced by**: CI coverage check
**Violation**: BLOCK merge

### 3. Real Infrastructure in Tiers 2-3
Integration and E2E tests MUST use real infrastructure.

**Tier 1 (Unit Tests)**:
- Mocking ALLOWED
- Test isolated functions
- Fast execution (<1s per test)

**Tier 2 (Integration Tests)**:
- NO MOCKING - use real database
- Test component interactions
- Real API calls (use test server)

**Tier 3 (E2E Tests)**:
- NO MOCKING - real everything
- Test full user journeys
- Real browser, real database

**Enforced by**: validate-workflow hook
**Violation**: Test invalid

## MUST NOT Rules (CRITICAL)

### 1. NO MOCKING in Tier 2-3
MUST NOT use mocking in integration or E2E tests.

**Detection Patterns**:
```python
❌ @patch('module.function')
❌ MagicMock()
❌ unittest.mock
❌ from mock import Mock
❌ mocker.patch()
```

**Why This Matters**:
- Mocks hide real integration issues
- Mocks don't catch API contract changes
- Mocks give false confidence
- Bugs slip through to production

**Enforced by**: validate-workflow hook
**Consequence**: Test invalid, must rewrite

### 2. No Test Pollution
Tests MUST NOT affect other tests.

**Required**:
- Clean setup/teardown
- Isolated test databases
- No shared mutable state

### 3. No Flaky Tests
Tests MUST be deterministic.

**Prohibited**:
- Random data without seeds
- Time-dependent assertions
- Network calls to external services (Tier 1)

## Test Organization

### Directory Structure
```
tests/
├── unit/           # Tier 1: Mocking allowed
├── integration/    # Tier 2: NO MOCKING
└── e2e/           # Tier 3: NO MOCKING
```

### Naming Convention
```
test_[feature]_[scenario]_[expected_result].py
```

Example: `test_user_login_with_valid_credentials_succeeds.py`

## Kailash-Specific Testing

### DataFlow Testing
```python
# Tier 2: Use real database
@pytest.fixture
def db():
    db = DataFlow("sqlite:///:memory:")  # Real SQLite
    yield db
    db.close()

def test_user_creation(db):
    # NO MOCKING - real database operations
    result = db.execute(CreateUser(name="test"))
    assert result.id is not None
```

### Workflow Testing
```python
# Tier 2: Use real runtime
def test_workflow_execution():
    runtime = LocalRuntime()
    workflow = build_workflow()
    results, run_id = runtime.execute(workflow.build())
    assert results is not None
```

## Exceptions
Testing exceptions require:
1. Written justification explaining why real infrastructure impossible
2. Approval from testing-specialist
3. Documentation in test file
4. Plan for removing exception
