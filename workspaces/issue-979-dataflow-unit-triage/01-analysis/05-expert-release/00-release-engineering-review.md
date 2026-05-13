# Release Engineering Review — issue-979 DataFlow Unit Triage

**Expert role:** CI/release-engineering
**Scope:** S1 (plugin pinning) and S6 (CI gate rebuild) in `02-plans/01-amendments-post-redteam.md`
**Source PRs:** #968 (gate, reverted), #977 (revert)
**Key reference:** `journal/0002-DISCOVERY-redteam-findings.md` HIGH-3

---

## Finding 1 — `pytest-forked` Is Unmaintained (CONFLICT)

**Classification:** CONFLICT
**Blocks:** S1 implementation

S1 calls for adding `pytest-forked>=1.6.0` to `packages/kailash-dataflow/pyproject.toml [dev]` (amended plan §S1, plugin pinning). `pytest-forked` was archived upstream. The last release was in 2021 and the GitHub repo is read-only. This is an unmaintained dependency with no active maintainer.

`rules/dependencies.md` "Own the Stack" principle requires re-implementation or removal when a dependency goes unmaintained. Pinning to an archived package converts every future Python upgrade into a potential silent break with no upstream fix available.

**S1 must either:**

- Remove `pytest-forked` from the pin list entirely, OR
- Replace it with the functional equivalent: `pytest-xdist` (active, maintained, handles process isolation via `-n` workers, supports forked test isolation via `--dist=no --forked` on compatible runners)

The brief's actual requirement (brief §Acceptance Criteria) is process isolation for `test_example_gallery` due to asyncio event loop contamination — not `forked` specifically. `pytest-xdist` with `--dist=no` achieves that on `ubuntu-latest` without a dead dependency. If the isolation mechanism is kept in-house via `subprocess.run` per test, `pytest-forked` can be dropped entirely from the pin list.

**Action required before S1 can land:** remove `pytest-forked>=1.6.0` from the S1 pin list. Re-evaluate whether `pytest-xdist` is needed or whether the `test_example_gallery` move to integration (per brief acceptance criteria) makes the isolation requirement moot.

---

## Finding 2 — Marker Exclusion Double-Filter Is a CONFLICT-Class Risk (CONFLICT)

**Classification:** CONFLICT
**Blocks:** S6 implementation if not resolved before PR creation
**Source:** `journal/0002-DISCOVERY-redteam-findings.md` HIGH-3

S1 adds `addopts = -m "not (requires_postgres or requires_mysql or requires_redis or requires_docker)"` to `packages/kailash-dataflow/pyproject.toml [tool.pytest.ini_options]`.

PR #968 (reverted by #977) used a workflow-level `-m` flag in the `run:` command of the `test-dataflow` job.

If S6 rebuilds the job from PR #968 as a reference AND carries over the workflow `-m` flag without removing it, both layers are active simultaneously. pytest applies both filters as an intersection — tests must pass BOTH expressions to be selected. For unit tests this is redundant but harmless. The real risk is in integration-tier CI: any job that passes `--m requires_postgres` to select integration tests would have its selection silently suppressed by the `not (requires_postgres ...)` from pytest.ini's `addopts`.

**The rule:** ONE canonical location for marker exclusion. The amended plan correctly designates pytest.ini as the canonical location. S6 MUST NOT include a `-m` flag in the workflow `run:` command for `test-dataflow`. The workflow `run:` command must use no `-m` at all, or only an additive (non-conflicting) expression.

**Enforcement check for S6 PR:**

```yaml
# MUST NOT appear in the test-dataflow run: block
.venv/bin/python -m pytest tests/ \
  -m "not (requires_postgres or ...)"   # BLOCKED — duplicates pytest.ini addopts
  --timeout=60 -m ...                   # BLOCKED — any -m flag

# CORRECT — no -m, pytest.ini addopts fires automatically
.venv/bin/python -m pytest tests/ \
  --maxfail=10 -q --timeout=60
```

Verify by grepping PR #968's diff at `unified-ci.yml` to confirm whether `-m` appears in the `test-dataflow` run command before treating it as a reference.

---

## Finding 3 — S1 Plugin Pins Are Correctly Scoped (CLARIFICATION)

**Classification:** CLARIFICATION

`pytest-timeout>=2.3.0` added to `packages/kailash-dataflow/pyproject.toml [dev]` is the correct location. `pytest-asyncio>=0.23.0` is already present in the DataFlow dev extras (confirmed in `packages/kailash-dataflow/pyproject.toml` current state). No duplication risk.

The root `pyproject.toml` must NOT re-declare these as root dev deps per `rules/python-environment.md` MUST Rule 4: sub-package test deps must not be duplicated at root. `pytest-timeout` in particular does not register as a pytest plugin at collection time (it hooks into the test runner differently), so the root-venv injection risk from `hypothesis` does not apply here — but the rule still prohibits root-level duplication categorically.

`timeout = 120` and `timeout_method = thread` in `pytest.ini` (`[tool.pytest.ini_options]`) apply per-test. This is distinct from the job-level `timeout-minutes` in the workflow (see Finding 5). Both are needed; they operate at different layers and do not conflict.

---

## Finding 4 — `ubuntu-latest` RAM Ceiling Is the Rebuild Condition, Not a Blocker (COST-CONCERN)

**Classification:** COST-CONCERN

PR #977's revert cites OOM on `ubuntu-latest` at approximately 22 seconds, estimated ~7 GB RAM at peak. GitHub-hosted `ubuntu-latest` provides approximately 7 GB usable RAM.

After S1-S5 remediation:

- `test_example_gallery` moves to integration tier (no longer in unit suite)
- Fabric tests move out of the unit path
- `TestImpactReporterIntegration` moves out
- DB-driver imports gate behind `importorskip`

These four removals account for the majority of the OOM vector. The residual unit suite on `ubuntu-latest` should comfortably fit within budget after remediation.

The job-level `timeout-minutes` in S6 serves as a RAM-exhaustion circuit breaker: if the process OOMs, pytest hangs rather than exits cleanly, and `timeout-minutes` terminates the runner. Recommend `timeout-minutes: 15` for the `test-dataflow` job — aggressive enough to surface a hung process within one CI cycle, generous enough for a clean unit run.

**Cost projection:** `test-dataflow` job on `ubuntu-latest` (GitHub-hosted, billed per minute). At `timeout-minutes: 15`, worst-case cost per run is 15 min × 1 runner. For a PR with typical push frequency (3-5 pushes), that is at most 75 minutes. With `concurrency: cancel-in-progress: true` (already set at `.github/workflows/unified-ci.yml` lines 5-8), earlier runs are cancelled but prior wall-clock minutes are still billed. Run the suite green locally before the first push to avoid triggering the cancellation-billing cycle — per `rules/git.md` Pre-FIRST-Push CI Parity Discipline.

---

## Finding 5 — Path Filter Must Cover Transitive Dep Graph (CLARIFICATION)

**Classification:** CLARIFICATION
**Applies to:** S6 — the `test-dataflow` job's `on.pull_request.paths` filter

Per `rules/ci-runners.md` Rule 5: paths filter must cover the transitive dependency graph of the package, not just its own directory.

The recommended filter for `test-dataflow`:

```yaml
on:
  pull_request:
    paths:
      - "packages/kailash-dataflow/**"
      - "src/kailash/**"
      - "pyproject.toml"
      - "uv.lock"
      - ".github/workflows/unified-ci.yml"
```

Omitting `src/kailash/**` is the failure mode `ci-runners.md` Rule 5 documents: a fix to a shared core module triggers the core CI but silently skips `test-dataflow`. The `pyproject.toml` + `uv.lock` entries ensure dep-pin changes trigger the suite. The workflow file entry ensures CI config changes re-trigger the job.

If `test-dataflow` is embedded in `unified-ci.yml` (same file as other jobs), the workflow file entry on the paths filter covers this automatically for that workflow.

---

## Finding 6 — PR #968 Cherry-Pick Is Blocked; Rebuild Required (ROLLBACK-RISK)

**Classification:** ROLLBACK-RISK
**Applies to:** S6 approach

PR #968 cannot be cherry-picked back into main without introducing Finding 2's double-filter conflict. PR #968's diff contains marker exclusion in the workflow `run:` block (the original design before S1 moved it to pytest.ini). Cherry-picking #968 and then removing the `-m` flag as a patch is risky because the canonical source of truth for `-m` placement was established by S1, not S6 — two parallel edits to the same logical contract.

**Required approach:** S6 rebuilds `test-dataflow` from scratch in `unified-ci.yml`, using `test-pact` as the structural template (already in `unified-ci.yml` at lines 121-167), and PR #968 as a behavioral reference only (what the job should do, not what code to copy).

**Structural template from `test-pact`** (`.github/workflows/unified-ci.yml` lines 121-167):

```yaml
test-dataflow:
  name: Test DataFlow (Python 3.11)
  needs: check-duplicate
  if: needs.check-duplicate.outputs.should-skip != 'true' && !startsWith(github.head_ref, 'release/')
  runs-on: ubuntu-latest
  timeout-minutes: 15 # job-level ceiling
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"
    - uses: astral-sh/setup-uv@v5
    - name: Install dependencies
      run: |
        uv venv .venv
        uv pip install -e "." --python .venv/bin/python    # root editable FIRST
        uv pip install -e "packages/kailash-dataflow[dev]" --python .venv/bin/python
    - name: Test kailash-dataflow
      timeout-minutes: 10 # step-level ceiling
      run: |
        cd packages/kailash-dataflow
        ../../.venv/bin/python -m pytest tests/ \
          --maxfail=10 -q --timeout=120
          # NO -m flag — marker exclusion lives in pytest.ini addopts
```

The root editable install (`uv pip install -e "."`) MUST precede the sub-package install per `rules/deployment.md` MUST: Sibling-Package CI Installs Root SDK Editable For Unreleased Core Modules. This was correct in PR #968 and must be preserved in the rebuild.

---

## Finding 7 — Rollback Plan Is Narrow and Clean (ROLLBACK-RISK)

**Classification:** ROLLBACK-RISK (mitigated)

S6 touches exactly one file: `.github/workflows/unified-ci.yml`. S1-S5 touch:

- `packages/kailash-dataflow/pyproject.toml` (plugin pins, timeout config, marker exclusion)
- Test file relocations (move tests from `tests/unit/` to `tests/integration/` or delete)

**If S6 gate produces unexpected failures post-merge:**

- Revert vector: `git revert <S6-merge-commit>` — removes the `test-dataflow` job from `unified-ci.yml`; the suite keeps running in the existing `test` matrix
- Test file moves from S1-S5 are permanent and do NOT revert; they are independent improvements that don't depend on S6's gate
- Plugin additions from S1 are permanent; no harm in keeping `pytest-timeout` in dev extras even without the gate job

**If S6 gate fires unexpectedly on a legitimate integration PR:**

- Root cause is almost certainly Finding 2 (double-filter) — diagnose by checking whether the failing test is tagged `requires_postgres` or similar
- Fix: remove the `-m` flag from the workflow `run:` block if it was inadvertently included; pytest.ini addopts remain canonical
- Timeline: one PR fix to `unified-ci.yml` restores correct behavior; no PyPI publish needed (gate is CI-only, not a release artifact)

Per `rules/build-repo-release-discipline.md` Rule 1a: test-only PRs (S1-S6) do not require a PyPI release. The DataFlow package version is unchanged. No release cycle implications unless the team chooses to cut a new DataFlow patch for the pyproject.toml dev-dependency changes — which is not required.

---

## Summary Matrix

| #   | Finding                                                        | Classification | S1/S6 Impact                     | Blocking? |
| --- | -------------------------------------------------------------- | -------------- | -------------------------------- | --------- |
| 1   | `pytest-forked` archived, unmaintained                         | CONFLICT       | S1 pin list must change          | Yes — S1  |
| 2   | Double marker filter (pytest.ini + workflow `-m`)              | CONFLICT       | S6 run command must omit `-m`    | Yes — S6  |
| 3   | S1 plugin pins correctly scoped to DataFlow dev                | CLARIFICATION  | No change needed                 | No        |
| 4   | `ubuntu-latest` RAM ceiling resolved by S1-S5 suite cleanup    | COST-CONCERN   | Set `timeout-minutes: 15` in S6  | Advisory  |
| 5   | Path filter must include `src/kailash/**`                      | CLARIFICATION  | S6 `on.pull_request.paths`       | Advisory  |
| 6   | PR #968 cherry-pick blocked; rebuild from `test-pact` template | ROLLBACK-RISK  | S6 must rebuild, not cherry-pick | Yes — S6  |
| 7   | Rollback scope is narrow (one workflow file)                   | ROLLBACK-RISK  | No PyPI release needed           | Mitigated |

**Hard blockers before S6 can open a PR:**

1. S1 must remove `pytest-forked>=1.6.0` (Finding 1)
2. S6 run command must have zero `-m` flags (Finding 2)
3. S6 must be a fresh rebuild using `test-pact` as template, not a cherry-pick of #968 (Finding 6)
