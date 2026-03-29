---
paths:
  - "tests/**"
  - "**/*test*"
  - "**/*spec*"
  - "conftest.py"
---

# Testing Rules

## Scope

These rules apply to all test files and test-related code.

## MUST Rules

### 0. Test-Once Protocol (MANDATORY)

Tests run ONCE per code change, not once per phase. This eliminates redundant test execution across `/implement`, `/redteam`, and pre-commit.

**The Protocol:**

1. `/implement` runs the full test suite ONCE per todo and writes `.test-results` to the workspace
2. `/redteam` READS `.test-results` — does NOT re-run existing tests
3. `/redteam` runs only NEW tests it creates (E2E user flows, Playwright, Marionette)
4. Pre-commit hook runs Tier 1 unit tests as a fast safety net
5. CI runs the full matrix as the final gate

**`.test-results` artifact:**

Written to `workspaces/<project>/.test-results` after each `/implement` todo completion. Contains commit hash, pass/fail counts, and regression count. Red team and deploy phases read this file instead of re-running.

**Re-run exceptions:**

- Code changed since `.test-results` was written (commit hash mismatch)
- Infrastructure-specific tests (e.g., ran against SQLite, need PostgreSQL verification)
- Red team suspects a specific test is wrong (re-run THAT test only)

**Enforced by**: `/implement` and `/redteam` command templates
**Violation**: Wasted compute, context window bloat, slower iteration

### 0b. Regression Testing (MANDATORY)

Every bug fix MUST include a regression test BEFORE the fix is merged.

**The Rule:**

1. When a bug is found, the FIRST step is writing a test that REPRODUCES the bug
2. The test MUST fail before the fix and pass after
3. Regression tests go in `tests/regression/test_issue_*.py`
4. Mark with `@pytest.mark.regression`
5. The test name includes the issue number (e.g., `test_issue_42_user_creation_drops_pk`)
6. Regression tests are NEVER deleted — they are permanent guards

**Why:** Without regression tests, the same bugs keep coming back. A fix verified only by code review is not verified at all.

**Pattern:**

```python
# tests/regression/test_issue_42.py
import pytest

@pytest.mark.regression
def test_issue_42_user_creation_preserves_explicit_id():
    """Regression: #42 — CreateUser silently drops explicit id.

    The bug: when auto_increment is enabled, passing an explicit id was silently ignored.
    Fixed in: commit abc1234
    """
    # Reproduce the exact bug from the issue
    # ...
    assert result["id"] == "custom-id-value"
```

**Enforcement:**

- Pre-commit: `pytest -m regression` must pass
- Pre-merge: reviewer verifies regression test exists for every bug fix
- Pre-release: regression suite is a mandatory checklist item

**Applies to**: All bug fixes
**Violation**: BLOCK merge — a fix without a regression test is not a fix

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

| Code Type         | Minimum Coverage |
| ----------------- | ---------------- |
| General           | 80%              |
| Financial         | 100%             |
| Authentication    | 100%             |
| Security-critical | 100%             |

**Enforced by**: CI coverage check
**Violation**: BLOCK merge

### 3. Real Infrastructure in Tiers 2-3

Integration and E2E tests MUST use real infrastructure.

**Tier 1 (Unit Tests)**:

- Mocking ALLOWED
- Test isolated functions
- Fast execution (<1s per test)

**Tier 2 (Integration Tests)**:

- Real infrastructure recommended - use real database
- Test component interactions
- Real API calls (use test server)

**Tier 3 (E2E Tests)**:

- Real infrastructure recommended - real everything
- Test full user journeys
- Real browser, real database
- **State persistence verification** — every write operation MUST be verified with a read-back (navigate away, reload, re-query). API 200 is NOT sufficient proof of persistence. See `rules/e2e-god-mode.md` Rule 6.

**Enforced by**: validate-workflow hook
**Violation**: Test invalid

## MUST NOT Rules (CRITICAL)

### 1. Real infrastructure recommended in Tier 2-3

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
├── regression/     # Tier 0: Permanent bug reproduction tests
├── unit/           # Tier 1: Mocking allowed
├── integration/    # Tier 2: Real infrastructure recommended
└── e2e/           # Tier 3: Real infrastructure recommended
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
    # Real infrastructure recommended - real database operations
    result = db.execute(CreateUser(name="test"))
    assert result.id is not None

    # STATE PERSISTENCE: Always read back after write
    # DataFlow silently ignores unknown params — verify the write actually wrote
    user = db.execute(ReadUser(filter={"id": result.id}))
    assert user is not None
    assert user.name == "test"
```

### State Persistence Verification (MANDATORY for Tiers 2-3)

Every test that writes data MUST verify persistence with a read-back:

```python
# ❌ BAD: Only checks API response
result = api.create_company(name="Acme")
assert result.status == 200  # DataFlow may have silently ignored params!

# ✅ GOOD: Verifies state persisted
result = api.create_company(name="Acme")
assert result.status == 200
# Read back to verify
company = api.get_company(result.id)
assert company.name == "Acme"
```

**Why**: DataFlow `UpdateNode` silently ignores unknown parameter names (`conditions`/`updates` instead of `filter`/`fields`). The API returns success but zero bytes are written. This is the #1 source of false-positive tests.

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
