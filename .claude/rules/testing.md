---
paths:
  - "tests/**"
  - "**/*test*"
  - "**/*spec*"
  - "conftest.py"
  - "**/.spec-coverage*"
  - "**/.test-results*"
  - "**/02-plans/**"
  - "**/04-validate/**"
---

# Testing Rules

## Test-Once Protocol (Implementation Mode)

During `/implement`, tests run ONCE per code change, not once per phase.

**Why:** Running the full test suite in every implementation phase wastes 2-5 minutes per cycle, compounding to significant delays across a multi-phase session.

1. `/implement` runs full suite ONCE per todo, writes `.test-results` to workspace
2. Pre-commit runs Tier 1 unit tests as fast safety net
3. CI runs the full matrix as final gate

**Re-run during /implement only when:** commit hash mismatch, infrastructure change, or specific test suspected wrong.

## Audit Mode Rules (Red Team / /redteam)

When auditing test coverage, the rules invert: do NOT trust prior round outputs. Re-derive everything.

### MUST: Re-derive coverage from scratch each audit round

```bash
# DO: re-derive
pytest --collect-only -q tests/

# DO NOT: trust the file
cat .test-results  # BLOCKED in audit mode
```

**Why:** A previous round may have written `.test-results` claiming "5950 tests pass" — true, but those tests covered the OLD code, while new spec modules have zero tests. Without re-derivation, the audit certifies test counts that don't correspond to the new functionality.

### MUST: Verify NEW modules have NEW tests

For every new module a spec creates, grep the test directory for an import of that module. Zero importing tests = HIGH finding regardless of "tests pass".

```bash
# DO
grep -rln "from kaizen_agents.wrapper_base\|import wrapper_base" tests/
# Empty → HIGH: new module has zero test coverage

# DO NOT
cat .test-results | grep -c PASSED  # Suite-level count tells you nothing about new modules
```

**Why:** Counting passing tests at the suite level lets new functionality ship with zero coverage as long as legacy tests still pass. Per-module test verification catches this.

### MUST: Verify security mitigations have tests

For every § Security Threats subsection in any spec, grep for a corresponding `test_<threat>` function. Missing = HIGH.

```bash
# Spec § Threat: prompt injection via tool description
grep -rln "test.*prompt.*injection\|test.*tool.*description.*injection" tests/
# Empty → HIGH: documented threat has no test
```

**Why:** Documented threats with no test become "we said we'd handle it" claims that nothing actually verifies. Threats without tests are unmitigated.

See `skills/spec-compliance/SKILL.md` for the full spec compliance verification protocol.

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

### MUST: Behavioral Regression Tests Over Source-Grep

Regression tests MUST exercise the actual code path (call the function, assert the raise/return). Grepping source files for literal substrings is BLOCKED as the sole assertion.

```python
# DO — behavioral: call the function, assert the contract
@pytest.mark.regression
def test_null_byte_rejected_in_credential_decode():
    """Regression: DATABASE_URL with null byte after percent-decode."""
    from kailash.utils.url_credentials import decode_userinfo_or_raise
    parsed = urlparse("mysql://user:%00bypass@host/db")
    with pytest.raises(ValueError, match="null byte"):
        decode_userinfo_or_raise(parsed)

# DO NOT — source-grep: pins implementation, breaks on refactor
@pytest.mark.regression
def test_null_byte_check_exists():
    src = open("src/kailash/db/connection.py").read()
    assert "\\x00" in src  # breaks when logic moves to shared helper
```

**Why:** Source-grep tests pin the implementation, not the contract; refactoring to a shared helper (the right move) breaks them. Behavioral tests survive refactors and survive being moved between modules.

Origin: `workspaces/arbor-upstream-fixes/.session-notes` (2026-04-12)

### MUST: Verified Numerical Claims In Session Notes

Any numerical claim about test counts, file counts, or coverage in session notes / wrapup MUST be produced by a verifying command (`pytest --collect-only -q | wc -l`, `git diff --stat`) at the moment of writing. Hand-typed numbers are BLOCKED.

```bash
# DO — verified: run the command, paste the output
# "62 regression tests pass" — verified via:
.venv/bin/python -m pytest tests/regression/ --collect-only -q 2>&1 | grep -c '::'
# Output: 62

# DO NOT — hand-recall: author guesses a round number
# "86 regression tests pass" — author's recall; actual was 46.
```

**Why:** The "claim a number, never verify" pattern bypassed the audit-mode rule and produced a 40-test discrepancy in this session. A verifying command costs 2 seconds and converts a memory bug into a script.

Origin: `workspaces/arbor-upstream-fixes/.session-notes` (2026-04-12)

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
