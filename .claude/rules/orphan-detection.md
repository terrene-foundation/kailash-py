# Orphan Detection Rules

A class that no production code calls is a lie. Beautifully implemented orphans accumulate when a feature is built top-down — model + facade + accessor get checked in, the public API documents them, downstream consumers import them — but the wiring from the product's hot path to the new class never lands. The orphan keeps passing unit tests against itself, the product keeps shipping, and the security/audit/governance promise the orphan was supposed to deliver never executes once.

This is the failure mode kailash-py Phase 5.11 surfaced: 2,407 LOC of trust integration code (`TrustAwareQueryExecutor`, `DataFlowAuditStore`, `TenantTrustManager`) was instantiated and exposed as `db.trust_executor` / `db.audit_store` / `db.trust_manager`, four downstream workspaces imported the classes, and zero production code paths invoked any method on them. Operators believed the trust plane was running for an unknown period; it was not.

The rule below prevents this by requiring every facade-shaped class on a public API to have a verifiable consumer in the production hot path within a bounded number of commits.

## MUST Rules

### 1. Every `db.*` / `app.*` Facade Has a Production Call Site

Any attribute exposed on a public surface that returns a `*Manager`, `*Executor`, `*Store`, `*Registry`, `*Engine`, or `*Service` MUST have at least one call site inside the framework's production hot path within 5 commits of the facade landing. The call site MUST live in the same package as the framework, not just in tests or downstream consumers.

```python
# DO — facade + production call site land in the same PR
class DataFlow:
    @property
    def trust_executor(self) -> TrustAwareQueryExecutor:
        return self._trust_executor

# packages/kailash-dataflow/src/dataflow/features/express.py
class DataFlowExpress:
    async def list(self, model, ...):
        plan = await self._db.trust_executor.check_read_access(...)  # ← real call site
        ...

# DO NOT — facade ships, no call site, downstream consumers import the orphan
class DataFlow:
    @property
    def trust_executor(self) -> TrustAwareQueryExecutor:
        return self._trust_executor
# (no call site exists in any framework hot path; trust executor is dead code)
```

**Why:** Downstream consumers see the public attribute, build their security model around the class's documented behavior, and ship features that silently bypass the protection because the framework never invokes the class on the actual data path.

### 2. Every Wired Manager Has a Tier 2 Integration Test

Once a manager is wired into the production hot path, its end-to-end behavior MUST be exercised by at least one Tier 2 integration test (real database, real adapter — `rules/testing.md` § Tier 2). Unit tests against the manager class in isolation are NOT sufficient.

```python
# DO — Tier 2 test exercises the wired path against real infrastructure
@pytest.mark.integration
async def test_trust_executor_redacts_in_express_read(test_suite):
    db = DataFlow(test_suite.config.url)
    @db.model
    class Document:
        title: str
        body: str
    set_clearance(PUBLIC)
    rows = await db.express.list("Document")
    assert all(row["body"] == "[REDACTED]" for row in rows)

# DO NOT — Tier 1 test against the class in isolation
def test_trust_executor_returns_redacted_plan():
    executor = TrustAwareQueryExecutor(...)
    plan = executor.check_read_access(...)
    assert plan.redact_columns == {"body"}
# ↑ proves the executor can redact, NOT that the framework calls it
```

**Why:** Unit tests prove the orphan implements its API. Integration tests prove the framework actually calls the orphan.

### 3. Removed = Deleted, Not Deprecated

If a manager is found to be an orphan and the team decides not to wire it, it MUST be deleted from the public surface in the same PR — not marked deprecated, not left behind a feature flag, not commented out. Orphans-with-warnings still mislead downstream consumers about the framework's contract.

**Why:** Deprecation banners are easy to miss; consumers continue importing the symbol and silently shipping insecure code. Deletion is the only signal that survives a `pip install kailash --upgrade`.

### 4. API Removal MUST Sweep Tests In The Same PR

Any PR that removes a public symbol (module, class, function, attribute) MUST delete or port the tests that import it, in the same commit. Test files that reference the removed symbol become orphans — they fail at `pytest --collect-only` with `ModuleNotFoundError` / `ImportError`, which blocks every subsequent test run.

```python
# DO — remove the API and its tests in one commit
# git show <sha>:
# D  src/pkg/legacy_module.py
# D  tests/integration/test_legacy_module.py
# D  tests/e2e/test_legacy_module_e2e.py

# DO NOT — remove the API, leave the tests
# git show <sha>:
# D  src/pkg/legacy_module.py
# (test files still import pkg.legacy_module, collection fails on next run)
```

**BLOCKED rationalizations:**

- "The tests will be cleaned up in a follow-up PR"
- "CI doesn't run those tests anyway"
- "The tests are obsolete; they don't need to move"
- "Integration tier is separate scope"
- "`pytest --collect-only` isn't part of CI"

**Why:** Test files that fail at collection block the ENTIRE suite from running, not just themselves. One orphan test import takes down the 100 tests collected after it. Evidence: kailash-py commits `d3e7e0ef` + `5edc941f` deleted 9 orphan test files left behind by the DataFlow 2.0 refactor (`53dab715`) — integration collection had been failing since that refactor landed, but nobody noticed because the collection error was buried in the middle of a log.

### 5. Collect-Only Is A Merge Gate

`pytest --collect-only` across every test directory MUST return exit 0 before any PR merges. A collection error is a blocker in the same class as a test failure, regardless of which test file contains the error.

```bash
# DO — gate in CI, pre-commit, or /redteam
.venv/bin/python -m pytest --collect-only tests/ packages/*/tests/
# exit 0 required

# DO NOT — "we only run unit tests in CI, integration is manual"
# (unit tests pass, integration collection is silently red for months)
```

**Why:** Collection failures are invisible in "unit-only CI" setups yet become merge-blocking the moment someone runs the full suite locally. The only way to keep the full suite runnable is to gate every PR on collect-only-green.

### 6. Module-Scope Public Imports Appear In `__all__`

When a symbol is imported at module-scope into a package's `__init__.py` (not behind `_` / not lazy via `__getattr__`), it MUST appear in that module's `__all__` list unless the symbol itself is private (leading underscore). New `__all__` entries MUST land in the same PR as the import. Eagerly-imported-but-absent-from-`__all__` is BLOCKED.

```python
# DO — every public module-scope import appears in __all__
# packages/kailash-ml/src/kailash_ml/__init__.py
from kailash_ml._device_report import (
    DeviceReport,
    device_report_from_backend_info,
)

__all__ = [
    "__version__",
    "DeviceReport",
    "device_report_from_backend_info",
    ...
]

# DO NOT — public symbol imported but missing from __all__
from kailash_ml._device_report import DeviceReport, device_report_from_backend_info

__all__ = [
    "__version__",
    # DeviceReport, device_report_from_backend_info → absent
    # Result: `from kailash_ml import *` drops the advertised public API
]
```

**BLOCKED rationalizations:**

- "The symbol is reachable via `kailash_ml.DeviceReport`, that's enough"
- "Nobody uses `from pkg import *`"
- "`__all__` is a convention, not a contract"
- "We'll clean up `__all__` in a follow-up"
- "The symbol is eagerly imported; the package re-exports it implicitly"

**Why:** `__all__` is the package's public-API contract: documentation generators (Sphinx autodoc), linters, typing tools (`mypy --strict`), and `from pkg import *` consumers all read it as the canonical export list. A symbol that the agent "eagerly imports" but never lists is both advertised (via the import) AND hidden (via `__all__`) — that inconsistency is the exact failure shape the orphan pattern produces on the consumer side. The fix is a one-line addition in the same PR; deferring it means the advertised feature ships broken for every tool that respects `__all__`. Evidence: PR #523 (kailash-ml 0.11.0) eagerly imported `DeviceReport` / `device_report_from_backend_info` / `device` / `use_device` but omitted all four from `__all__`; caught by post-release reviewer; patched in PR #529 (kailash-ml 0.11.1).

Origin: PR #523 / PR #529 (2026-04-19) — GPU-first Phase 1 public API symbols missed from `__all__`.

## MUST NOT

- Land a `db.X` / `app.X` facade without the production call site in the same PR

**Why:** The PR review is the only structural gate that catches orphans before they ship; allowing the gate to bypass means the orphan is in production by the next release.

- Skip the consumer check on the grounds that "downstream consumers will use it"

**Why:** Downstream consumers using a class is not the same as the framework using it. The framework's hot path is the security boundary; downstream consumers are clients of that boundary, not enforcers of it.

- Mark a wired manager as "fully tested" based on Tier 1 unit tests alone

**Why:** Tier 1 mocks the framework's call into the manager. The orphan failure mode is precisely "the framework never calls the manager in production" — Tier 1 cannot detect that.

## Detection Protocol

When auditing for orphans, run this protocol against every class exposed on the public surface:

1. **Surface scan** — list every property, method, and attribute on the framework's top-level class that returns a `*Manager` / `*Executor` / `*Store` / `*Registry` / `*Engine` / `*Service`.
2. **Hot-path grep** — for each candidate, grep the framework's source (NOT tests, NOT downstream consumers) for calls into the class's methods. Zero matches in the hot path = orphan.
3. **Tier 2 grep** — for each non-orphan, grep `tests/integration/` and `tests/e2e/` for the class name. Zero matches = unverified wiring.
4. **Collect-only sweep** — run `.venv/bin/python -m pytest --collect-only tests/ packages/*/tests/`. Every `ERROR <path>` / `ModuleNotFoundError` / `ImportError` at collection is a test-orphan. Disposition: delete the orphan test file (if the API is gone) or port its imports (if the API moved).
5. **Disposition** — every orphan and every unverified wiring MUST be either fixed (wire + test) or deleted (remove from public surface).

This protocol runs as part of `/redteam` and `/codify`.
