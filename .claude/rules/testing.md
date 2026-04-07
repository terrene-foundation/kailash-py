# Testing Rules

## Test-Once Protocol

Tests run ONCE per code change, not once per phase.

**Why:** Running the full test suite in every phase wastes 2-5 minutes per cycle, compounding to significant delays across a multi-phase session.

1. `/implement` runs full suite ONCE per todo, writes `.test-results` to workspace
2. `/redteam` READS `.test-results` — does NOT re-run existing tests
3. `/redteam` runs only NEW tests it creates (E2E, Playwright, Marionette)
4. Pre-commit runs Tier 1 unit tests as fast safety net
5. CI runs the full matrix as final gate

**Re-run only when:** commit hash mismatch, infrastructure change, or specific test suspected wrong.

## Regression Testing

Every bug fix MUST include a regression test BEFORE the fix is merged.

**Why:** Without a regression test, the same bug silently re-appears in a future refactor with no signal until a user reports it again.

1. Write test that REPRODUCES the bug (must fail before fix, pass after)
2. Place in `tests/regression/test_issue_*.py` with `@pytest.mark.regression`
3. Regression tests are NEVER deleted

```python
@pytest.mark.regression
def test_issue_42_user_creation_preserves_explicit_id():
    """Regression: #42 — CreateUser silently drops explicit id."""
    # Reproduce the exact bug
    assert result["id"] == "custom-id-value"
```

## 3-Tier Testing

### Tier 1 (Unit): Mocking allowed, <1s per test

### Tier 2 (Integration): Real infrastructure recommended

- Real database, real API calls (test server)
- NO mocking (`@patch`, `MagicMock`, `unittest.mock` — BLOCKED)

**Why:** Mocks in integration tests hide real failures (connection handling, schema mismatches, transaction behavior) that only surface with real infrastructure.

### Tier 3 (E2E): Real everything

- Real browser, real database
- State persistence verification — every write MUST be verified with a read-back

**Why:** E2E tests are the last gate before users — any abstraction here means the test validates something other than what users actually experience.

```
tests/
├── regression/     # Permanent bug reproduction
├── unit/           # Tier 1: Mocking allowed
├── integration/    # Tier 2: Real infrastructure
└── e2e/           # Tier 3: Real everything
```

## Coverage Requirements

| Code Type                            | Minimum |
| ------------------------------------ | ------- |
| General                              | 80%     |
| Financial / Auth / Security-critical | 100%    |

## State Persistence Verification (Tiers 2-3)

Every write MUST be verified with a read-back:

```python
# ❌ Only checks API response
result = api.create_company(name="Acme")
assert result.status == 200  # DataFlow may silently ignore params!

# ✅ Verifies state persisted
result = api.create_company(name="Acme")
company = api.get_company(result.id)
assert company.name == "Acme"
```

**Why:** DataFlow `UpdateNode` silently ignores unknown parameter names. The API returns success but zero bytes are written.

## Kailash-Specific

```python
# DataFlow: Use real database
@pytest.fixture
def db():
    db = DataFlow("sqlite:///:memory:")
    yield db
    db.close()

# Workflow: Use real runtime
def test_workflow_execution():
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())
    assert results is not None
```

## Rules

- Test-first development for new features
- Tests MUST be deterministic (no random data without seeds, no time-dependent assertions)
  **Why:** Non-deterministic tests produce intermittent failures that erode trust in the test suite, causing developers to ignore real failures.
- Tests MUST NOT affect other tests (clean setup/teardown, isolated DBs)
  **Why:** Shared state between tests creates order-dependent results — tests pass individually but fail in CI where execution order differs.
- Naming: `test_[feature]_[scenario]_[expected_result].py`
