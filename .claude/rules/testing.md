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

See `.claude/guides/rule-extracts/testing.md` for full evidence, extended examples, and post-mortems.

## Test-Once Protocol (Implementation Mode)

During `/implement`, tests run ONCE per code change, not once per phase. Full suite per todo, pre-commit Tier 1 safety net, CI full matrix as final gate. Re-run only on commit-hash mismatch, infra change, or specific test suspected wrong.

**Why:** Running full suite every phase wastes 2-5 minutes per cycle.

## Audit Mode (/redteam)

### MUST: Re-derive coverage from scratch each round

```bash
# DO
pytest --collect-only -q tests/
# DO NOT
cat .test-results  # BLOCKED in audit mode
```

**Why:** Prior `.test-results` may claim "5950 tests pass" true for OLD code while new modules have zero tests.

### MUST: Verify NEW modules have NEW tests

For every new module, grep test directory for import of that module. Zero = HIGH.

```bash
grep -rln "from new_module\|import new_module" tests/   # empty → HIGH
```

**Why:** Suite-level count lets new functionality ship with zero coverage as long as legacy tests pass.

### MUST: Verify security mitigations have tests

For every § Security Threats subsection in any spec, grep for `test_<threat>`. Missing = HIGH.

**Why:** Documented threats without tests are unmitigated claims.

See `skills/spec-compliance/SKILL.md` for full protocol.

## Regression Testing

Every bug fix MUST include a regression test BEFORE merge. Place in `tests/regression/test_issue_*.py` with `@pytest.mark.regression`. NEVER deleted.

**Why:** Without it, same bug re-appears in future refactor, undetected until a user reports.

### MUST: Behavioral Regression Tests Over Source-Grep

Call the function; assert raise/return. Grepping source for literal substrings is BLOCKED as sole assertion.

```python
# DO — behavioral
@pytest.mark.regression
def test_null_byte_rejected():
    with pytest.raises(ValueError, match="null byte"):
        decode_userinfo_or_raise(urlparse("mysql://u:%00x@h/d"))

# DO NOT — source-grep pins implementation
assert "\\x00" in open("src/…/connection.py").read()  # breaks on refactor
```

**Why:** Source-grep breaks when logic moves to a shared helper (the right refactor). Behavioral tests survive refactors and module moves.

### MUST: Verified Numerical Claims In Session Notes

Numerical claims (test counts, file counts, coverage) in session notes MUST be produced by a verifying command at the moment of writing. Hand-typed is BLOCKED.

```bash
# DO
pytest tests/regression/ --collect-only -q 2>&1 | grep -c '::'
# DO NOT — hand-recalled round numbers
```

**Why:** "Claim a number, never verify" produces multi-test discrepancies; 2-second command converts memory bug into script.

## Test Resource Cleanup

Warnings during `pytest` are real bugs that will surface as production incidents in a different shape.

### MUST: Fixtures Yield + Cleanup, Never Return

```python
# DO
@pytest.fixture
def cli_channel(config):
    channel = CLIChannel(config=config); yield channel; channel.close()
# DO NOT — return without cleanup, resource leaks until GC
```

**BLOCKED rationalizations:** "class has `__del__`" / "unit test, process exits anyway" / "mock makes it fake".

**Why:** Resource classes emitting `ResourceWarning` from `__del__` flood the runner hiding real signals. See guide for PR #466 (36 unclosed channels).

### MUST: AsyncMock Replaced By Mock When side_effect Is `async def`

```python
# DO
with patch("asyncio.open_connection", new_callable=Mock) as mock_oc:
    mock_oc.side_effect = fake_open  # async def
# DO NOT — default AsyncMock double-wraps the coroutine
```

**Why:** Default `AsyncMock` wraps the side_effect coroutine again; the wrapper is never awaited; `RuntimeWarning` surfaces at GC, hours later.

### MUST: Helper Classes Use Stub/Helper/Fake Suffix, Not `Test` Prefix

```python
# DO — class NameStub: bypasses collection
# DO NOT — class TestName: with __init__ → PytestCollectionWarning
```

**Why:** pytest collects `Test*` classes; `__init__` triggers a warning AND the class is silently dropped.

### MUST: JWT Test Secrets ≥ 32 Bytes (RFC 7518 §3.2)

```python
# DO
JWT_TEST_SECRET = "test-secret-key-minimum-32-bytes!"
# DO NOT — short secret triggers InsecureKeyLengthWarning
```

**Why:** Short HMAC keys reduce brute-force resistance; a 10-byte test secret teaches contributors that 10 bytes is acceptable.

### MUST: Pytest Plugin + Marker Declaration Pair

Any test using `@pytest.mark.<X>` or `<X>` fixture from a plugin MUST declare the plugin in the owning sub-package's `[dev]` extras AND register the marker in pytest config SAME commit.

```toml
# DO
dev = ["pytest-benchmark>=4.0.0"]
[tool.pytest.ini_options]
markers = ["benchmark: Performance tests"]
# DO NOT — use plugin with either missing → collection fails, whole sub-package blocked
```

**BLOCKED rationalizations:** "plugin is in CI so local works" / "pytest accepts unknown markers" / "we'll register in follow-up" / "fixture imported lazily" / "sub-package venv is separate".

**Why:** Missing any layer breaks collection with an unhelpful error. See guide for 2026-04-20 11,917-test block.

## Env-Var Test Isolation

### MUST: Serialize Env-Var-Mutating Tests Via Module Lock

Any two tests mutating SAME env var MUST serialize through a module-scope lock held across read-then-mutate.

```python
_ENV_LOCK = threading.Lock()
@pytest.fixture
def _env_serialized():
    with _ENV_LOCK: yield
# tests take (monkeypatch, _env_serialized)
```

**BLOCKED rationalizations:** "passes locally, CI scheduling is the bug" / "lock is overkill" / "pytest one-per-worker default" / "`@pytest.mark.serial`" (only with `--dist=loadgroup`) / "monkeypatch auto-restores".

**Why:** `monkeypatch.setenv` restores at fixture teardown — AFTER the test body — so sibling tests observe either value depending on xdist scheduling. Classic "passes locally, fails CI".

## 3-Tier Testing

- **Tier 1 (Unit)**: Mocking allowed, <1s per test
- **Tier 2 (Integration)**: Real infrastructure. NO mocking (`@patch`, `MagicMock`, `unittest.mock` — BLOCKED)
- **Tier 3 (E2E)**: Real everything; every write verified with read-back

**Why:** Mocks in Tier 2/3 hide real failures (connection handling, schema mismatches, transactions) that only surface against real infra.

**Exception — Protocol-Satisfying Deterministic Adapters:** A class satisfying a `typing.Protocol` at runtime with deterministic output is NOT a mock. See guide § "Protocol Adapters" for full example.

## Coverage Requirements

| Code Type                            | Minimum |
| ------------------------------------ | ------- |
| General                              | 80%     |
| Financial / Auth / Security-critical | 100%    |

## MUST: End-to-End Pipeline Regression Above Unit + Integration

Every canonical pipeline the docs teach (README Quick Start, tutorial, 3-line example) MUST have a Tier-2+ regression test executing DOCS-EXACT code against real infra, asserting the final user-visible outcome. Lives in `tests/regression/` with `@pytest.mark.regression`; name includes "quickstart"/"readme"/tutorial-name (grep-able).

```python
@pytest.mark.regression
@pytest.mark.asyncio
async def test_readme_quickstart_executes_end_to_end():
    import kailash_ml as km
    result = await km.train(df, target="churned")
    assert result.trainable is not None  # handoff field MUST survive
    registered = await km.register(result, name="demo")
    assert "onnx" in registered.artifact_uris
```

**BLOCKED rationalizations:** "primitives have unit+integration, pipeline is composition" / "README is illustrative" / "Tier 2 per primitive proves interfaces" / "user will file issue" / "E2E is slow and flaky" / "pipeline is demo's concern, not SDK".

**Why:** Unit tests per primitive construct fixtures with exactly the fields THAT primitive needs — they cannot observe a field MISSING from the A→B handoff. Only DOCS-EXACT chain exercises the handoff contract. When docs teach a pipeline, the pipeline IS the public API. Evidence: kailash-ml W33b (2026-04-23) — `km.train → km.register` broken via missing `TrainingResult.trainable`; every unit test passed; canonical Quick Start raised `ValueError` on every fresh install. See `zero-tolerance.md` §2 "Fake integration via missing field".

## State Persistence Verification (Tiers 2-3)

Every write MUST be verified with a read-back:

```python
# DO — verify persistence
result = api.create_company(name="Acme")
company = api.get_company(result.id)
assert company.name == "Acme"
# DO NOT — only check status
assert result.status == 200   # DataFlow may silently ignore params
```

**Why:** DataFlow `UpdateNode` silently ignores unknown parameter names — API returns success but zero bytes written.

## Kailash-Specific

```python
@pytest.fixture
def db():
    db = DataFlow("sqlite:///:memory:"); yield db; db.close()

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## MUST: One Direct Test Per Variant In Every Delegating Pair

When a module exposes paired variants delegating to a shared core (`get`/`get_raw`, `post`/`post_raw`, `insert`/`insert_batch`, `read`/`read_typed`), each variant MUST have a direct-call test — not reaching the other by delegation.

```python
# DO — direct per-variant tests
def test_get_typed_success(client): user = client.get("/u/42"); assert user["name"] == "Alice"
def test_get_raw_success(client):   resp = client.get_raw("/u/42"); assert resp["status"] == 200
# DO NOT — only typed variant; refactor of get_raw error-mapping ships silent regression
```

**BLOCKED rationalizations:** "typed calls raw internally, one test covers both" / "shared core" / "integration catches this" / "raw is just less-useful typed".

**Why:** Convergent delegation paths look like one path until they diverge under refactor pressure — the divergent moment is when the test you didn't write would have failed.

`/redteam` MUST mechanically grep each variant pair; any pair with zero direct call site is a finding.

## Rules

- Test-first development for new features
- Deterministic: no random data without seeds, no time-dependent assertions
- Isolated: clean setup/teardown, isolated DBs, tests MUST NOT affect each other
- Naming: `test_[feature]_[scenario]_[expected_result].py`

**Why (deterministic):** Intermittent failures erode trust; developers start ignoring real failures.
**Why (isolated):** Shared state → order-dependent results; passes individually, fails in CI where order differs.

Origin: PR #466 (warnings sweep, 2026-04-14), #518 (test-skip triage, 2026-04-19), BP-046 (paired-variant coverage, 2026-04-14), kailash-rs #435 (env-var race, 2026-04-20), kailash-ml W33b (E2E regression, 2026-04-23). See guide for full session evidence.
