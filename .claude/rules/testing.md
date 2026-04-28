---
priority: 10
scope: path-scoped
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

See `.claude/guides/rule-extracts/testing.md` for full evidence, the kailash-ml W33b post-mortem, the test-skip triage decision tree, the test-resource-cleanup post-mortems (PR #466 63-warning sweep, 11,917-test block, env-var race), and protocol blocks.

<!-- slot:neutral-body -->

## Test-Once Protocol (Implementation Mode)

During `/implement`, tests run ONCE per code change, not once per phase. Full suite per todo, pre-commit Tier 1 safety net, CI full matrix as final gate. Re-run only on commit-hash mismatch, infra change, or specific test suspected wrong.

**Why:** Running full suite every phase wastes 2-5 minutes per cycle.

## Audit Mode (/redteam)

In audit mode, MUST (1) re-derive coverage from scratch via `pytest --collect-only -q tests/` (NOT `cat .test-results` — BLOCKED); (2) for every NEW module, grep test directory for import — empty = HIGH; (3) for every spec § Security Threats subsection, grep `test_<threat>` — missing = HIGH.

**Why:** Prior `.test-results` may claim "5950 tests pass" true for OLD code while new modules ship with zero coverage. Documented threats without tests are unmitigated claims. See `skills/spec-compliance/SKILL.md` for full protocol.

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
# DO     pytest tests/regression/ --collect-only -q 2>&1 | grep -c '::'
# DO NOT hand-recalled round numbers
```

**Why:** "Claim a number, never verify" produces multi-test discrepancies; 2-second command converts memory bug into script.

### MUST: `__all__` / Re-export Symbol Counts Use Structural Enumeration, Not Grep

Counts of `__all__` entries (Python) or re-exports (Rust `pub use ...`) used in spec authority, docstrings, audit findings, or CHANGELOG claims MUST be produced by structural enumeration of the language's parser AST — NOT `grep -c` / `wc -l`. See guide for canonical Python (`ast.parse()`) and Rust (`syn::parse_file` / `cargo doc --document-private-items`) snippets.

```python
# DO — Python: walk ast.Assign for __all__, len(value.elts)
# DO NOT — grep '^\s*"' (counts comments + blank lines + line continuations as entries)
```

**BLOCKED rationalizations:** "Grep is faster" / "I'll subtract the comment lines manually" / "The count is approximate anyway" / "AST is overkill for a docstring number".

**Why:** Grep cannot distinguish `# Group N — comment` from `"Group_N",` when both contain quotes; it cannot follow line continuations across an `__all__ = [...]` block. Structural parsing is canonical because it parses the language, not text. See guide for Wave 6 evidence (three incompatible counts: docstring 41, grep 48, AST 49).

## Test Resource Cleanup

Warnings during `pytest` are real bugs that will surface as production incidents. See guide § "PR #466 — 63-Warning Sweep" for full evidence per category below.

### MUST: Fixtures Yield + Cleanup, Never Return

```python
# DO    yield channel; channel.close()
# DO NOT return without cleanup → resource leaks until GC
```

**BLOCKED rationalizations:** "class has `__del__`" / "unit test, process exits anyway" / "mock makes it fake".

**Why:** Resource classes emitting `ResourceWarning` from `__del__` flood the runner hiding real signals. See guide for PR #466 (36 unclosed channels).

### MUST: AsyncMock Replaced By Mock When `side_effect` Is `async def`

```python
# DO    patch(..., new_callable=Mock); m.side_effect = fake_open  # async def
# DO NOT default AsyncMock double-wraps the coroutine; never awaited; RuntimeWarning at GC
```

**Why:** Default `AsyncMock` wraps the side_effect coroutine again; the wrapper is never awaited; `RuntimeWarning` surfaces at GC, hours later.

### MUST: Helper Classes Use Stub/Helper/Fake Suffix; JWT Test Secrets ≥ 32 Bytes

`class NameStub:` (NOT `class TestName:` with `__init__` — pytest collects `Test*`, triggers `PytestCollectionWarning`, class silently dropped). `JWT_TEST_SECRET = "test-secret-key-minimum-32-bytes!"` (NOT short — `InsecureKeyLengthWarning` per RFC 7518 §3.2).

**Why:** Pytest's `Test*` collection silently drops `__init__`-bearing helper classes, hiding real test logic. Short HMAC keys teach contributors that 10 bytes is acceptable when 32 is the floor.

### MUST: Pytest Plugin + Marker Declaration Pair

Any test using `@pytest.mark.<X>` or `<X>` fixture from a plugin MUST declare the plugin in the owning sub-package's `[dev]` extras AND register the marker in pytest config SAME commit.

```toml
# DO    dev = ["pytest-benchmark>=4.0.0"]
#       [tool.pytest.ini_options]
#       markers = ["benchmark: Performance tests"]
# DO NOT either layer missing → collection fails, whole sub-package blocked
```

**BLOCKED rationalizations:** "plugin is in CI so local works" / "pytest accepts unknown markers" / "we'll register in follow-up" / "fixture imported lazily" / "sub-package venv is separate".

**Why:** Missing any layer breaks collection with an unhelpful error. See guide for 2026-04-20 11,917-test block.

## MUST: Serialize Env-Var-Mutating Tests Via Module Lock

Any two tests mutating SAME env var MUST serialize through a module-scope `threading.Lock` held across read-then-mutate; tests take `(monkeypatch, _env_serialized)`. See guide for full fixture pattern + kailash-rs PR #435 cross-language origin.

**BLOCKED rationalizations:** "passes locally, CI scheduling is the bug" / "lock is overkill" / "pytest one-per-worker default" / "`@pytest.mark.serial`" (only with `--dist=loadgroup`) / "monkeypatch auto-restores".

**Why:** `monkeypatch.setenv` restores at fixture teardown — AFTER the test body — so sibling tests observe either value depending on xdist scheduling. Classic "passes locally, fails CI".

## 3-Tier Testing

- **Tier 1 (Unit)**: Mocking allowed, <1s per test
- **Tier 2 (Integration)**: Real infrastructure. NO mocking (`@patch`, `MagicMock`, `unittest.mock` — BLOCKED)
- **Tier 3 (E2E)**: Real everything; every write verified with read-back

**Why:** Mocks in Tier 2/3 hide real failures (connection handling, schema mismatches, transactions) that only surface against real infra. Exception — Protocol-Satisfying Deterministic Adapters: a class satisfying a `typing.Protocol` at runtime with deterministic output is NOT a mock. See guide § "Protocol Adapters" for full example.

## Coverage Requirements

| Code Type                            | Minimum |
| ------------------------------------ | ------- |
| General                              | 80%     |
| Financial / Auth / Security-critical | 100%    |

## MUST: End-to-End Pipeline Regression Above Unit + Integration

Every canonical pipeline the docs teach (README Quick Start, tutorial, 3-line example) MUST have a Tier-2+ regression test executing DOCS-EXACT code against real infra, asserting the final user-visible outcome. Lives in `tests/regression/` with `@pytest.mark.regression`; name includes "quickstart"/"readme"/tutorial-name (grep-able). See guide for full example.

```python
@pytest.mark.regression
async def test_readme_quickstart_executes_end_to_end():
    result = await km.train(df, target="churned")
    assert result.trainable is not None  # handoff field MUST survive
```

**BLOCKED rationalizations:** "primitives have unit+integration, pipeline is composition" / "README is illustrative" / "Tier 2 per primitive proves interfaces" / "user will file issue" / "E2E is slow and flaky" / "pipeline is demo's concern, not SDK".

**Why:** Unit tests per primitive construct fixtures with exactly the fields THAT primitive needs — they cannot observe a field MISSING from the A→B handoff. Only DOCS-EXACT chain exercises the handoff contract. See guide for kailash-ml W33b evidence + `zero-tolerance.md` §2 "Fake integration via missing field".

## State Persistence Verification (Tiers 2-3)

Every write MUST be verified with a read-back: call create/update, then call get/list, assert the value.

```python
# DO    result = api.create_company(name="Acme"); assert api.get_company(result.id).name == "Acme"
# DO NOT assert result.status == 200  # DataFlow may silently ignore params
```

**Why:** DataFlow `UpdateNode` silently ignores unknown parameter names — API returns success but zero bytes written.

## MUST: One Direct Test Per Variant In Every Delegating Pair

When a module exposes paired variants delegating to a shared core (`get`/`get_raw`, `post`/`post_raw`, `insert`/`insert_batch`, `read`/`read_typed`), each variant MUST have a direct-call test — not reaching the other by delegation.

```python
# DO — direct per-variant tests
def test_get_typed_success(client): user = client.get("/u/42"); assert user["name"] == "Alice"
def test_get_raw_success(client):   resp = client.get_raw("/u/42"); assert resp["status"] == 200
# DO NOT — only typed variant; refactor of get_raw error-mapping ships silent regression
```

**BLOCKED rationalizations:** "typed calls raw internally, one test covers both" / "shared core" / "integration catches this" / "raw is just less-useful typed".

**Why:** Convergent delegation paths look like one path until they diverge under refactor pressure. `/redteam` MUST mechanically grep each variant pair; any pair with zero direct call site is a finding.

## Rules

- Test-first development for new features
- Deterministic: no random data without seeds, no time-dependent assertions
- Isolated: clean setup/teardown, isolated DBs, tests MUST NOT affect each other
- Naming: `test_[feature]_[scenario]_[expected_result].py`

**Why:** Intermittent failures erode trust; shared state → order-dependent results that pass individually but fail in CI where order differs.

Origin: PR #466 (warnings sweep), #518 (test-skip triage), BP-046 (paired-variant coverage), kailash-rs #435 (env-var race), kailash-ml W33b (E2E regression), 2026-04-27 W6 (AST counts). See guide for full session evidence.

<!-- /slot:neutral-body -->
