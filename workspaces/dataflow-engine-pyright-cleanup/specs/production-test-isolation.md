# Production / Test Isolation Contract — engine.py Imports

**Domain:** Import discipline (production code MUST NOT import test fixtures)
**Authority:** Promoted from `02-plans/` to `specs/` on T1 (S1) merge (2026-05-04). The invariant holds on `main` as of the T1 PR merge: `engine.py:3427` now imports `MockConnectionPool` from `dataflow.testing.mock_helpers` (a real package path), not from `tests.fixtures.mock_helpers`. Sister spec to `static-analysis-baseline.md`.

## Invariant

Production source under `packages/*/src/**/*.py` MUST NOT contain `import` or `from` statements that target a path matching `tests.*` or `tests.fixtures.*`.

## Verifying command

```bash
grep -rn 'from tests\.\|import tests\.' packages/*/src/ src/
# Expected output (post-S1): empty (exit code 1 from grep = no matches)
```

## Why

Test fixtures are not part of any installed-package import path. On a clean PyPI install of `kailash-dataflow`:

- `tests/` directory is excluded from the wheel build (`pyproject.toml::[tool.setuptools.packages.find]` does not enumerate `tests`).
- Production code that imports from `tests.*` ALWAYS hits an `ImportError` on real installs.
- The only environment where `tests.*` is importable is the BUILD-repo working tree where `tests/` happens to be on `sys.path` because pytest added it.

Per `rules/dependencies.md` § "Declared = Imported", every production import MUST resolve to a declared package. `tests` is not a declared package; it's a directory present only in the source tree.

## Acceptable patterns

The following ARE permitted (do NOT violate this contract):

1. **Test code imports test fixtures** — `tests/integration/test_X.py` doing `from tests.fixtures.mock_helpers import MockX` is fine (test code lives in `tests/`).
2. **Production code imports a non-test sibling module** — `dataflow.testing.mock_helpers` (under `src/dataflow/testing/`) is a real package path; production code may import from it under the optional-extras pattern (loud failure at call site if the test sibling isn't installed, per `dependencies.md` § "BLOCKED Anti-Patterns" exception).
3. **Production code accepts test doubles via dependency injection** — `def __init__(self, pool: ConnectionPool | None = None)` lets test code inject a mock without the production module knowing about test fixtures.

## BLOCKED patterns

- `from tests.fixtures.X import Y` in any `src/` path
- `import tests.fixtures.X` in any `src/` path
- `try: from tests.X import Y; except ImportError: pass` in any `src/` path (the try/except form is the L3437 site — disguising the violation behind a fallback does not make it a non-violation; per `dependencies.md` MUST § "Declared = Imported" this is BLOCKED)

## §X Change log

- **2026-05-04** — Promoted from `02-plans/03-production-test-isolation-contract.md` to `specs/production-test-isolation.md` on T1 (S1) merge. T1 relocated `MockConnectionPool` from `tests/fixtures/mock_helpers.py` to `src/dataflow/testing/mock_helpers.py`, updated `engine.py:3427` to import from the real package path, and deleted the old test-fixture file. The verifying grep `grep -rnE "^(from|import) tests(\.|$|\s)" packages/*/src/ src/` returns empty.
