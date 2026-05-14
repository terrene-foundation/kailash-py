# 0003 DECISION — shard sequencing + build/wire split for Shard 4

Date: 2026-05-14
Phase: /todos

## Decision 1 — Strict sequential shard execution, NO parallelization

Shards 1 → 2 → 3 → 4a → 4b → release. Each depends on the prior merged to `main`.

**Rationale**: parallel worktree execution is BLOCKED here because every shard edits a shared file class (tests/unit/\*) and any leak missed in an earlier shard hides the regression in a later shard. The architecture-plan red-team's MED-1 finding (Shard 4 sequencing risk) makes the dependency chain load-bearing — running Shards 2 and 3 in parallel would mean Shard 3's AC#2 gate observes an artificial pass (the missing Shard-2 sites would still leak in CI when Shard 4b lands).

**Trade-off**: 5 sessions sequential vs ~2 wall-clock units if Shards 2+3 parallelized. The sequential path is the correct one — `value-prioritization.md` MUST-2 (each shard carries its own value-anchor surviving `/clear`) is preserved by the dependency chain.

## Decision 2 — Build/wire split for Shard 4

Split Shard 4 of the architecture plan into 4a (build regression test) + 4b (wire — remove setsid wrapper + CHANGELOG).

**Rationale**: per /todos skill contract, every component that produces or consumes data has TWO todos — build the component, wire it to real data. Shard 4a builds the regression test as a structural defense. Shard 4b removes the setsid wrapper (the production CI surface) and lands the CHANGELOG entry. They are NOT the same task: 4a is complete when the test runs locally with setsid still in CI; 4b is complete when CI runs plain pytest AND the 4a regression test guards against future regression.

Collapsing them would mean a single PR with both the workaround removal AND a fresh test — if CI hangs on that PR, we cannot tell whether the new test is broken or the workaround removal exposed a missed leak. Splitting lets 4a land green first (zero CI risk), then 4b's only variable is the workaround removal.

## Decision 3 — Entry gate codified as todo invariant, not implicit

Shard 4b's todo MUST run the local `time pytest tests/unit/ --timeout=120` repro AND record the wall-clock observation in the PR body. This converts the architecture-plan MED-1 risk into a structural invariant: the gate is not "the agent remembers to check"; it is "the PR body shows the timing."

**Rationale**: per `rules/verify-resource-existence.md` MUST-2 (cite the endpoint, not the documentation), trusting the architecture plan's "Shard 4 is safe to land after 1-3" is hearsay. Citing a live `time pytest` run in the PR body is the verifiable receipt.

## Decision 4 — Release-cut split into its own todo (06)

Per `rules/git.md` § Release-Prep PR convention, release-prep MUST go on a `release/v*` branch. Bundling Shard 4b's code-fix with the version bump on a `fix/` branch would trigger the full PR-gate matrix (~45 min × N) for what's effectively metadata. Splitting saves ~120 min of CI on the release-prep cycle.

**Trade-off**: 6 todos vs 5. The marginal todo is metadata-only; the time saving is real.

## Decision 5 — Sibling-package release sweep deferred to Shard 06 entry, not /todos

Per root `.session-notes` template, every release session should enumerate sibling-package PyPI vs `pyproject.toml` drift. Not run during /todos because the data would be stale by the time Shard 06 lands (3-4 sessions later). Captured as a Shard-06 pre-release checklist entry instead.

## Non-decisions (deferred to /implement)

- Specific fixture name for non-DataFlow adapter fixtures (Shard 2). The migration template gives the shape; the specialist picks the name during /implement based on each test file's existing patterns.
- Whether Shard 3's asyncio-mark fix at `test_performance_regression_suite.py:717` is "remove the mark" or "make the function async". Inspect-the-body decision during /implement.
- Cross-SDK kailash-rs investigation. Per `rules/repo-scope-discipline.md` — user-decision, not autonomous-pick.
