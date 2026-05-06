# Regression Gate Contract — engine.py Pyright Invariant

**Domain:** Test infrastructure (regression gate for static-analysis cleanliness)
**Authority:** Promoted from `02-plans/02-regression-gate-contract.md` to `specs/regression-gate-contract.md` on T8 (S8) merge (2026-05-04). The regression test exists at `packages/kailash-dataflow/tests/regression/test_engine_pyright_invariant.py` and enforces the contract below.

## Test placement + collection

| Property       | Value                                                                                                             |
| -------------- | ----------------------------------------------------------------------------------------------------------------- |
| Path           | `packages/kailash-dataflow/tests/regression/test_engine_pyright_invariant.py`                                     |
| Pytest marker  | `@pytest.mark.regression`                                                                                         |
| Collection     | Default `pytest` collection (per `rules/refactor-invariants.md` MUST Rule 2 — invariant tests in CI default path) |
| Sub-package    | `kailash-dataflow` (test belongs to the package whose source it audits)                                           |
| Skip condition | None — gate runs on every test invocation                                                                         |

## Pass condition

The test passes iff ALL of:

1. `uv run pyright packages/kailash-dataflow/src/dataflow/core/engine.py` exits status 0 for the **error count** (exit code from pyright's "errors" tally is 0).
2. The total error count parsed from pyright's summary line equals **0**.
3. The total warning count parsed from pyright's summary line is **≤ 10**.
4. Every surviving warning corresponds to an in-source `# pyright: ignore[<rule>]` comment WITH an adjacent `# Reason: <X>` justification line. (The justification grep is BLOCKING — undocumented suppressions fail the gate.)

## Drift detection

The test's threshold values (errors=0, warnings≤10) are pinned in the test source. A future PR that re-introduces an error OR pushes warnings >10 fails the gate. A future PR that LEGITIMATELY justifies relaxing the threshold MUST update the threshold AND document the rationale in the test docstring + commit body — silent threshold relaxation is a `rules/zero-tolerance.md` Rule 1 violation.

## Pyright version pinning

The pyright version under which the gate's thresholds were calibrated MUST be pinned to an EXACT version (`==X.Y.Z`, not `>=X.Y.Z`) in `packages/kailash-dataflow/pyproject.toml::[project.optional-dependencies].dev`. The test asserts running pyright matches the pinned value AND reports the version on every assertion failure:

```python
import subprocess
PINNED_PYRIGHT_VERSION = "1.1.371"  # MUST match pyproject.toml [dev] pyright pin
result = subprocess.run(["uv", "run", "pyright", "--version"], capture_output=True, text=True)
running_version = result.stdout.strip()  # e.g. "pyright 1.1.371"
assert PINNED_PYRIGHT_VERSION in running_version, (
    f"pyright version mismatch: running {running_version}, "
    f"gate calibrated for {PINNED_PYRIGHT_VERSION}. "
    f"Update both `pyproject.toml::[dev]` AND PINNED_PYRIGHT_VERSION + re-baseline."
)
assert <error_count> == 0, f"pyright {running_version} reports N errors (expected 0)"
```

This converts a "thresholds drifted because pyright bumped a rule" diagnosis from "git bisect across the dataflow tree" to "compare pyright versions in CI logs." The exact-pin discipline is the structural defense: a `>=X.Y.Z` pin lets contributor envs and CI containers run different pyright versions silently, producing "passes locally, fails CI" as a recurring fingerprint.

**Current calibration baseline:** pyright `1.1.371` (the version under which the 5-errors / 56-warnings baseline in `static-analysis-baseline.md` was measured). Latest pyright is `1.1.409`. Bump strategy: a future PR may relax the pin to a newer version, BUT MUST re-run the audit + re-baseline thresholds + document the rule-set delta in the test docstring + commit body.

## CLI invocation portability

The gate test invokes `uv run pyright` via `subprocess.run`. CI containers MUST have `uv` installed. Verified pre-deploy as part of CI image inventory; if a container ships without `uv`, the gate fails at the `subprocess.run` level (FileNotFoundError) — loud failure preferred over silent skip.

## Failure-mode signals

| Failure signal                          | Likely root cause                                                                        |
| --------------------------------------- | ---------------------------------------------------------------------------------------- |
| `errors == N (expected 0)`, N ≥ 1       | A new PR re-introduced one of E1-E5 OR introduced a different error                      |
| `warnings == M (expected ≤ 10)`, M > 10 | A new PR widened the typing surface OR pyright version bumped a rule                     |
| `Undocumented suppression at L<N>`      | A `# pyright: ignore` was added without a `# Reason:` line — fails Rule 4                |
| `pyright not installed`                 | `dev` extras not synced — install via `uv pip install -e packages/kailash-dataflow[dev]` |

## Bypass policy

The gate is structural; bypass is BLOCKED. Per `rules/test-skip-discipline.md` (mandatory bypass discipline):

- `pytest --skip-regression` is BLOCKED (would skip every regression test, defeating the gate).
- `@pytest.mark.skipif` per-platform is BLOCKED (pyright is platform-independent).
- `git commit --no-verify` (which bypasses pre-commit, not pytest) does NOT bypass the gate; the gate runs in CI per `rules/refactor-invariants.md` Rule 2.

The only legitimate path to disable the gate is to delete the test file via a PR that documents WHY the cleanup contract is being abandoned — and that PR is itself subject to red-team review.

## Out of scope

- Other DataFlow files (`pool_lightweight.py`, `adapters/postgresql.py`, etc.) — each gets its own regression gate when its cleanup workspace runs.
- Pyright `strict=true` mode — out of this workspace's scope.
- Cross-file pyright analysis (whole-package run) — gate audits engine.py only, matching the workspace's scope.
