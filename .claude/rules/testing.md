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

## Test Resource Cleanup Discipline

The unit test suite is a leading indicator of production hygiene. Warnings emitted during `pytest` are not "noise" — every `ResourceWarning`, `RuntimeWarning`, or `DeprecationWarning` is a real bug in either the test or the code-under-test that will surface as a production incident in a different shape.

### MUST: Fixtures Yield + Cleanup, Never Return

Any fixture that constructs a resource (channel, runtime, server, connection, pool) MUST use `yield` and call the resource's cleanup method after `yield`. `return` in a fixture that creates a stateful resource is BLOCKED.

```python
# DO — yield + cleanup, resource closed when test exits
@pytest.fixture
def cli_channel(channel_config, mock_input_stream, mock_output_stream):
    channel = CLIChannel(
        config=channel_config,
        input_stream=mock_input_stream,
        output_stream=mock_output_stream,
    )
    yield channel
    channel.close()

# DO NOT — return without cleanup, resource leaks until GC
@pytest.fixture
def cli_channel(channel_config, mock_input_stream, mock_output_stream):
    return CLIChannel(
        config=channel_config,
        input_stream=mock_input_stream,
        output_stream=mock_output_stream,
    )
```

**BLOCKED rationalizations:**

- "The class has a `__del__` so the GC will clean it up"
- "It's a unit test, the process exits anyway"
- "The mock makes the resource fake, no real cleanup needed"

**Why:** Resource classes that emit `ResourceWarning` from `__del__` (CLIChannel, LocalRuntime, AsyncLocalRuntime, AsyncSQLDatabaseNode) flood the test runner with warnings that hide real signals. Fixtures using `return` accumulate orphan resources across the test session — 36 unclosed channels in `test_cli_channel_comprehensive.py` produced 36 warnings before this rule landed (PR #466).

### MUST: AsyncMock Replaced By Mock When side_effect Is `async def`

When patching an awaitable function (e.g. `asyncio.open_connection`, `asyncio.wait_for`) with a side_effect that is itself an `async def`, MUST use `Mock(new_callable=Mock)` not the default `AsyncMock`. The `async def` side_effect already returns the coroutine — `AsyncMock` wraps it again and the inner wrapper is never awaited.

```python
# DO — Mock with async side_effect, no double-wrap
async def fake_open(*args, **kwargs):
    return (mock_reader, mock_writer)

with patch("asyncio.open_connection", new_callable=Mock) as mock_oc:
    mock_oc.side_effect = fake_open
    # production code awaits mock_oc(...) → fake_open() → coroutine awaited
    await production_code()

# DO NOT — AsyncMock + async side_effect, leaks _execute_mock_call coroutine
async def fake_open(*args, **kwargs):
    return (mock_reader, mock_writer)

with patch("asyncio.open_connection") as mock_oc:  # default = AsyncMock for awaitables
    mock_oc.side_effect = fake_open
    # AsyncMock._execute_mock_call wraps fake_open() into another coroutine that's never awaited
    # → RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited
```

**Why:** `AsyncMock` introspects the patched target; if it's a coroutine function, every `__call__` creates an internal `_execute_mock_call` coroutine that wraps the side_effect. When the side_effect itself is `async def`, the wrapper coroutine is created but never awaited — the warning surfaces during garbage collection, hours after the test passed. Source: PR #466 fix in `tests/unit/mcp_server/test_discovery.py`.

### MUST: Test Helper Classes Without `__init__` Use Stub Naming

Classes in test files that act as helper implementations (subclasses of production base classes) MUST NOT use the `Test` prefix. pytest collects every class matching `python_classes = Test*`, and a helper class with `__init__(self, **kwargs)` raises `PytestCollectionWarning: cannot collect test class because it has a __init__ constructor`.

```python
# DO — Stub naming bypasses pytest collection
class ConditionalRuntimeStub(BaseRuntime, ConditionalExecutionMixin):
    """Helper runtime for testing the mixin in isolation."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.executed_nodes = []

# DO NOT — Test prefix triggers collection warning + skipped tests
class TestConditionalRuntime(BaseRuntime, ConditionalExecutionMixin):
    """Helper runtime — but pytest tries to collect it as a test class."""

    def __init__(self, **kwargs):  # <-- triggers PytestCollectionWarning
        super().__init__(**kwargs)
```

**Why:** A `Test*` class with `__init__` is silently dropped from collection AND pollutes the warning summary. The `Stub` / `Helper` / `Fake` suffix signals intent and stays out of pytest's collection path. Source: PR #466 fix in `tests/unit/runtime/mixins/test_conditional_execution_mixin.py`.

### MUST: JWT Test Secrets ≥ 32 Bytes (RFC 7518 §3.2)

JWT test fixtures using HS256 / HS384 / HS512 MUST use a secret of at least 32 bytes. Short test secrets trigger `InsecureKeyLengthWarning` from PyJWT and produce false-positive security signals in CI logs.

```python
# DO — 32-byte test secret per RFC 7518
class TestJWTAuth:
    JWT_TEST_SECRET = "test-secret-key-minimum-32-bytes!"

    def test_create_token(self):
        auth = JWTAuth(self.JWT_TEST_SECRET, algorithm="HS256")
        # ...

# DO NOT — short test secret
def test_create_token():
    auth = JWTAuth("secret_key", algorithm="HS256")  # 10 bytes → InsecureKeyLengthWarning
```

**Why:** Short HMAC keys reduce brute-force resistance and are the same code path as production. A test that ships with a 10-byte key teaches the next contributor that 10 bytes is acceptable. Source: PR #466 fix in `tests/unit/mcp_server/test_auth.py`.

Origin: PR #466 (2026-04-14) — eliminated 63 unit test warnings across 10 categories. Each pattern above resolves a category that recurred until the rule was added.

### MUST: Pytest Plugin + Marker Declaration Pair

Any test file that uses `@pytest.mark.<X>` or the `<X>` fixture from a pytest plugin MUST declare the plugin in the owning sub-package's `[dev]` extras AND register the marker in that sub-package's pytest `markers` config in the SAME commit. Using a plugin without declaring it OR using a marker without registering it is BLOCKED — collection fails with `"'<X>' not found in markers configuration option"` or `ModuleNotFoundError` and no test in that sub-package can run.

```toml
# DO — plugin declared in [dev] extras AND marker registered in same pyproject
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-benchmark>=4.0.0",  # declared
]

[tool.pytest.ini_options]
markers = [
    "benchmark: Performance benchmark tests (pytest-benchmark)",  # registered
]
```

```python
# DO — test uses the plugin AFTER declaration + registration landed
@pytest.mark.benchmark
def test_write_performance(benchmark):
    benchmark(lambda: do_work())

# DO NOT — test uses plugin with neither declaration nor marker registration
@pytest.mark.benchmark   # marker unregistered → collection fails
def test_write_performance(benchmark):   # benchmark fixture unavailable → ModuleNotFoundError
    ...
```

**BLOCKED rationalizations:**

- "The plugin is in CI so local works fine"
- "pytest accepts unknown markers by default"
- "We'll register the marker in a follow-up commit"
- "The fixture is imported lazily so it doesn't matter"
- "It works in the sub-package venv, root venv is a separate concern"

**Why:** Pytest plugins form a hidden middle layer: declared in sub-package `[dev]` extras, registered in pytest `markers` config, invoked via decorator or fixture. Any one layer missing breaks collection with an unhelpful error and blocks the entire sub-package's test suite. The declared-imported discipline from `dependencies.md` applies 1:1 to pytest plugins; this rule is the pytest-specific binding.

Origin: Session 2026-04-20 /redteam collection-gate sweep — `packages/kailash-kaizen/tests/e2e/memory/test_persistent_buffer_e2e.py` used `@pytest.mark.benchmark` + `benchmark` fixture without declaring `pytest-benchmark`; blocked 11,917 kaizen tests from collection. Fixed commit `1313ae56`. See `workspaces/kailash-ml-gpu-stack/journal/0008-GAP-full-specs-redteam-2026-04-20-findings.md`.

## 3-Tier Testing

### Tier 1 (Unit): Mocking allowed, <1s per test

### Tier 2 (Integration): Real infrastructure recommended

- Real database, real API calls (test server)
- NO mocking (`@patch`, `MagicMock`, `unittest.mock` — BLOCKED)

**Why:** Mocks in integration tests hide real failures (connection handling, schema mismatches, transaction behavior) that only surface with real infrastructure.

#### Exception: Protocol-Satisfying Deterministic Adapters Are Not Mocks

A class that satisfies a `typing.Protocol` at runtime (`isinstance(x, TheProtocol) is True`) and produces deterministic output from its inputs is NOT a mock — it is a real implementation of the Protocol whose output happens to be deterministic. Tier 2 integration tests MAY use such adapters for Protocol-typed dependencies where real production implementations require API keys, network, or GPU that CI cannot provide.

```python
# DO — real Protocol implementation, isinstance holds, deterministic output
class DeterministicJudge:
    """Real JudgeCallable implementation for Tier 2 tests."""
    judge_model: str = "deterministic-test-judge"

    def __init__(self) -> None:
        self.calls: list[JudgeInput] = []

    async def __call__(self, judge_input: JudgeInput) -> JudgeResult:
        self.calls.append(judge_input)
        raw = min(len(judge_input.candidate_a) / 200.0, 1.0)
        return JudgeResult(
            score=raw, winner=None,
            reasoning=f"Deterministic score={raw:.2f}",
            judge_model=self.judge_model,
            cost_microdollars=150,
            prompt_tokens=10, completion_tokens=15,
        )

@pytest.mark.integration
def test_facade_satisfies_protocol() -> None:
    judge = DeterministicJudge()
    assert isinstance(judge, JudgeCallable)  # Protocol check holds at runtime

# DO NOT — MagicMock with spec=JudgeCallable
judge = MagicMock(spec=JudgeCallable)  # methods are auto-generated stubs, still mock-based
```

**BLOCKED rationalizations:**

- "MagicMock with `spec=` passes isinstance — same thing"
- "It's the same as a mock if the output is scripted"
- "`side_effect` on an AsyncMock is functionally equivalent"
- "Protocol adapter is over-engineering; just use `patch`"

**Why:** The Protocol contract is the scripting surface, not a mock framework's `side_effect` or `return_value`. A real class declaring the Protocol-required methods with correct signatures + returning real values of the Protocol-required types is a valid Tier 2 test double even when its output is deterministic. The rule distinguishes Tier 2 test-doubles from mocks by Protocol-conformance, not by whether the backing store is real — a real PostgreSQL + a `DeterministicJudge` are both Tier 2-legal; a mocked PostgreSQL + a real OpenAI call is Tier 2 illegal.

Origin: Session 2026-04-20 (issue #567 PR#5, PR#580). `DeterministicJudge` in `packages/kailash-kaizen/tests/integration/judges/test_judges_wiring.py` exercises 7 Tier 2 tests through the `kaizen.judges` facade without API keys; satisfies `kailash.diagnostics.protocols.JudgeCallable` at runtime.

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

## Delegating Primitives Need Direct Coverage

When a module exposes paired variants that delegate to a shared core (e.g. `get` / `get_raw`, `post` / `post_raw`, `insert` / `insert_batch`, `read` / `read_typed`), each variant MUST have at least one test that calls it directly — not a test that calls only one variant and reaches the other by delegation.

This is a narrow rule about delegating primitive pairs. It is NOT a universal "every public function has a direct test" mandate.

### MUST: One Direct Test Per Variant In Every Delegating Pair

```python
# DO — one test per variant, each asserting the externally observable behaviour
# of THAT specific variant
def test_get_typed_success(client):
    """Direct exercise of the typed get() variant."""
    user = client.get("/users/42")
    assert user["name"] == "Alice"

def test_get_raw_success(client):
    """Direct exercise of the raw get_raw() variant."""
    resp = client.get_raw("/users/42")
    assert resp["status"] == 200
    assert "Alice" in resp["body"]

# DO NOT — exercise only the typed variant and trust delegation
def test_get_works(client):
    """Only calls client.get(); never touches client.get_raw()."""
    user = client.get("/users/42")
    assert user["name"] == "Alice"
# A refactor that touches get_raw's error mapping ships a silent regression
# because no test exercises that path directly.
```

**Why:** A refactor that changes the typed variant while leaving the raw variant in place ships a silent regression — the raw variant has no guard. Convergent delegation paths look like one path until they diverge under refactor pressure, and the divergent moment is exactly when the test you didn't write would have failed.

**BLOCKED rationalizations:**

- "The typed variant calls the raw variant internally, so testing typed covers raw"
- "Both variants share the same execute() core, so one test is enough"
- "We can rely on integration tests to catch this"
- "The raw variant is just a less-useful version of the typed one"

### MUST: Mechanical Enforcement Via Grep

`/redteam` MUST run a grep for paired variants and report any pair where one side has no direct call site in `tests/`. The check is mechanical — no judgment required.

```bash
# DO — grep each known variant pair for direct test coverage
for variant in get_raw post_raw put_raw delete_raw; do
  count=$(grep -rln "client.$variant\(" tests/ | wc -l)
  if [ "$count" -eq 0 ]; then
    echo "MISSING: no test calls client.$variant() directly"
  fi
done
```

**Why:** Mechanical grep catches the regression at the audit gate, not at the next production incident. Manual "I'm pretty sure I covered both variants" is not auditable.

Origin: BP-046 (kailash-rs ServiceClient, 2026-04-14, commit `d3a14a73`). The `put_raw` and `delete_raw` variants were transitively exercised through delegation only — no direct call sites in the test suite. Fixed by adding four direct wiremock tests, one per raw variant. The pattern generalises to any module with paired typed/raw, single/batch, or sync/async variants that delegate to a shared core.

## Rules

- Test-first development for new features
- Tests MUST be deterministic (no random data without seeds, no time-dependent assertions)
  **Why:** Non-deterministic tests produce intermittent failures that erode trust in the test suite, causing developers to ignore real failures.
- Tests MUST NOT affect other tests (clean setup/teardown, isolated DBs)
  **Why:** Shared state between tests creates order-dependent results — tests pass individually but fail in CI where execution order differs.
- Naming: `test_[feature]_[scenario]_[expected_result].py`
