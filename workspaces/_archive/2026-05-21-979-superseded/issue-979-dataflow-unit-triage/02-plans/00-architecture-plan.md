# Architecture Plan — Issue #979 DataFlow Unit Suite Triage

Date: 2026-05-13
Phase output for `/analyze`; HUMAN GATE at `/todos` before any
shard executes.

## Goal (user-anchored)

Make `packages/kailash-dataflow/tests/unit/` tier-1-clean so the
PR #968 CI gate (issue #898) can re-land. Until then, every
DataFlow PR rediscovers the failure mode from PR #976. Value
source: issue #979 body (filed 2026-05-13).

## Brief corrections (gate per agents.md MUST)

These corrections to `briefs/00-brief.md` are recorded in
`journal/0001-DISCOVERY-brief-verification.md` and propagated
here for the plan:

1. **PR #976 was NEVER MERGED.** Its `_fresh_db_url()` helpers
   and `timeout = 120` are NOT on main. The plan starts from
   the pre-fix state, not the partial-fix state.
2. **AC#2 (`test_dataflow_events.py` 4+ failures) is likely a
   no-op.** Current state: pure-Python, collects clean. S5
   re-scoped to verification + documentation.
3. **Layer D (PG-requiring tests) is BROADER than #979 listed.**
   11+ files carry PG-shaped URLs; 2 use `IntegrationTestSuite`.
   The plan audits all, not just `TestImpactReporterIntegration`.
4. **Local dev venv hides Layer C.** `[fabric]` is installed
   locally; CI tier-1 is `[dev]`-only. Every shard's
   verification MUST use a clean venv per
   `01-analysis/01-research/04-history-reconciliation.md`.
5. **`migration/` and `migrations/` are different directories.**
   The plan uses full paths.

## Decomposition rationale (per autonomous-execution.md § Capacity)

This work has ~30-35 files and 5 distinct failure-mode classes.
LOC count is low (most edits are imports + path moves) but the
invariant count is high (every shard must hold "tier-1 contract"
plus "no regression in suite-level pass count" plus "CI parity"
across move boundaries). Decomposed into 6 shards:

- **S1** is a precondition (plugins + timeout config); ~50 LOC,
  3 invariants.
- **S2-S5** are independent cleanup shards; each ≤200 LOC and
  ≤5 invariants. They can run in parallel after S1 lands.
- **S6** is the gate re-application; depends on S1-S5 green.

## Value-anchors per shard

Each shard cites a primary user-anchored source (value-prioritization
MUST-2) so re-pickup across `/clear` works.

### S1 — Plugin & timeout preconditions

Files: `packages/kailash-dataflow/pyproject.toml`,
`packages/kailash-dataflow/pytest.ini`.

Changes:

- Add `pytest-timeout>=2.3.0` + `pytest-forked>=1.6.0` to
  `[project.optional-dependencies] dev`.
- Add `timeout = 120` and `timeout_method = thread` to
  `pytest.ini`.
- Add `addopts` marker exclusion default: `-m "not
(requires_postgres or requires_mysql or requires_redis or
requires_docker)"` (the unit-tier fallback strategy).

Invariants: plugins available in clean venv; per-test timeout
fires (not job-wide); marker filter does not affect existing
passing tests.

Verification: clean venv install + `pytest --collect-only`

- a deliberate `time.sleep(130)` test that times out at 120s
  (removed after verification).

Value-anchor: issue #979 says "the gate would convert every
PR touching DataFlow into a tier-2-environment-required run"
— S1 is the floor below which no other shard can land safely.

Capacity: ≤50 LOC. 3 invariants. 1 call-graph hop. One shard.

### S2 — Move `test_example_gallery.py` to integration

Files: move `packages/kailash-dataflow/tests/unit/examples/`
→ `packages/kailash-dataflow/tests/integration/examples/`.
Update any `tests/CLAUDE.md` references.

Changes:

- `git mv tests/unit/examples tests/integration/examples`
- Update test docstrings noting tier-2 classification
- Add a brief `tests/integration/examples/__init__.py` if needed

Invariants: tests still collect after move; tests still pass
when run from integration tier (with real workflows OK there);
no orphan import path remains in unit tier.

Verification: `pytest tests/integration/examples -x` passes in
its tier (integration env has real PG/Redis/Docker available);
`pytest tests/unit -x` no longer collects the gallery file.

Value-anchor: PR #977 step 4 — refactor was the recovery plan's
named target; we MOVE instead of refactor because the tests
genuinely exercise `AsyncLocalRuntime` and `WorkflowBuilder`
(per `02-failure-layers.md` Layer B).

Capacity: ≤30 LOC change (mostly path moves). 3 invariants.

### S3 — Move `tests/unit/fabric/` to integration

Files: `git mv tests/unit/fabric → tests/integration/fabric`.
Update `tests/CLAUDE.md` (integration tier section) to
document `[fabric]` extra requirement for that directory.

Invariants: all 21 test files still collect post-move (when
integration env has `[fabric]`); no orphan path remains in
unit tier; `tests/integration/__init__.py` aware of new subdir.

Verification: `pytest tests/integration/fabric --collect-only`
in env with `[fabric]` returns 21 files; `pytest tests/unit
--collect-only` does not list any `fabric/`.

Value-anchor: #979 AC#3 — explicit "fabric/\* either moved OR
gated"; MOVE picked per `05-recovery-plan-mapping.md` strategy
table (intent is integration-shape).

Capacity: ≤50 LOC of doc + path changes. 3 invariants.

### S4 — Move PG/IntegrationTestSuite users + audit URLs

Files:

- MOVE `tests/unit/cache/test_cache_invalidation.py`
  → `tests/integration/cache/test_cache_invalidation.py`
- MOVE `tests/unit/migration/test_impact_reporter_unit.py`
  → `tests/integration/migration/test_impact_reporter_unit.py`
  (note: `tests/integration/migration/` may need to be created;
  there is also `tests/integration/migrations/` plural — check
  before commit)
- For each file in V4 inventory: open, verify whether PG URL is
  real-connecting or parse-only; MOVE if real, refactor to
  SQLite sentinel URL if parse-only.
- For `tests/unit/testing/test_tdd_support.py`: replace bare
  `import asyncpg` (line 16) with
  `asyncpg = pytest.importorskip("asyncpg")` at module top.

Invariants: every moved file passes in integration tier;
every gated import behaves identically when driver is absent
(skip) and present (full run); no unit-tier file imports
`IntegrationTestSuite` post-shard.

Verification: clean-venv `pytest tests/unit -x` collects with
zero ImportError on Layer C/D; integration-venv `pytest
tests/integration -x` (cache + migration subdirs) passes.

Value-anchor: #979 AC#4 + AC#5; also addresses the BROADER
PG-URL inventory surfaced in `03-violations-inventory.md` V4.

Capacity: ≤200 LOC (mostly imports + path moves, per-file audit
on 9 V4 files); 5 invariants; 2 call-graph hops.

### S5 — Refactor `tempfile`/ad-hoc DataFlow to fixtures

Files: 7 files from V5 + ~8 net new from V6 (`03-violations-inventory.md`).

Changes: per file, replace ad-hoc `DataFlow(f"sqlite:///{tmp.name}")`
patterns with `memory_dataflow` or `file_dataflow` fixture. Where
a test genuinely needs file-based DB (rare), use `file_dataflow`
or `file_test_suite` from conftest.

Invariants: each refactored test still asserts the same
behavior; fixture yield+close pattern in place; no
`tempfile.mktemp()` or `tempfile.NamedTemporaryFile` for DB
paths remains under `tests/unit/`.

Verification: `grep -rn 'tempfile\.\(mktemp\|NamedTemporaryFile\)'
packages/kailash-dataflow/tests/unit/` returns ≤2 hits (the
`test_performance_regression_suite.py` JSON-file cases, which
are out of scope); `pytest tests/unit -x` passes in clean venv.

Value-anchor: tier-1 contract clause #2
(`01-tier1-contract.md`) — fixture mandate is explicit in the
canonical CLAUDE.md. Closing this violation closes the deadlock
class PR #976 kept rediscovering.

Capacity: ~15 files × ~10-20 LOC each = ~150-300 LOC; 5
invariants per file (yield+close, no state-bleed, same assertion
shape, fixture availability, marker propagation); 3 call-graph
hops max. Single shard since each file is independent and the
fixture surface is shared.

Note: this is the largest shard. If S5 exceeds capacity during
implementation, split by sub-directory (V5 first, V6 second).

### S6 — Re-apply PR #968 CI gate + CLAUDE.md update

Files:

- `.github/workflows/unified-ci.yml`: re-add `test-dataflow`
  job from PR #968 (cherry-pick the diff, sans the issues
  S1-S5 fixed).
- `packages/kailash-dataflow/tests/unit/CLAUDE.md`: document
  the marker-exclusion strategy + importorskip pattern + the
  S2-S4 move rationale.
- `packages/kailash-dataflow/tests/CLAUDE.md`: document
  `[fabric]` extra requirement for integration tier.

Invariants: CI gate fires on this PR and passes; gate ALSO
fires on a deliberate `feat/canary` PR with a planted unit-tier
violation and CORRECTLY fails; CLAUDE.md reflects what was
actually enforced.

Verification: PR opens, full CI green; the canary PR's
intentional violation is caught by the gate.

Value-anchor: #979 AC#6 + AC#7 — the entire workstream's
purpose is enabling this shard. Without S6 the value
("re-enable the gate") is undelivered.

Capacity: ≤200 LOC (workflow + docs). 4 invariants. 1 call-graph
hop. One shard.

## Dependency graph

```
S1 (preconditions) ──┐
                     ├──→ S2 (gallery move)        ──┐
                     ├──→ S3 (fabric move)          ──┤
                     ├──→ S4 (PG audit + move/gate) ──┼──→ S6 (gate re-apply)
                     └──→ S5 (fixture refactor)     ──┘
```

S2-S5 can be launched as a parallel worktree wave (3 at a time
per worktree-isolation Rule 4) once S1 lands. S6 strictly
follows all four.

## Risk register

| Risk                                        | Mitigation                                                              |
| ------------------------------------------- | ----------------------------------------------------------------------- |
| Moving files breaks transitive imports      | Each MOVE shard runs `grep -rn 'from tests.unit.<sub>' packages/` first |
| `IntegrationTestSuite` import surface leaks | S4 closes; S6 documents to prevent recurrence                           |
| Clean-venv verification omitted in haste    | Every shard's verification section explicitly says "clean venv"         |
| Marker exclusion hides legitimate tests     | S1 adds the markers; subsequent shards explicitly add markers per file  |
| S5 exceeds capacity                         | Pre-authorized split into V5-only + V6-only sub-shards                  |
| PR #968 cherry-pick conflicts with new HEAD | S6 builds the workflow diff from scratch using PR #968 as reference     |

## Out of scope (explicit non-goals)

- Refactoring `tests/integration/` (it has its own contract drift; not this issue)
- Adding new tests
- Changing production code under `packages/kailash-dataflow/src/` (unless a failing test reveals a real bug; then per `rules/zero-tolerance.md` Rule 4 — fix, do not work around)
- Touching sibling packages (`kailash-nexus`, `kailash-kaizen`, etc.)
- Resurrecting PR #976 — those fixes never landed and the strategy here supersedes them

## Spec authority

This plan extends `specs/tier1-test-contract.md` (created by
this `/analyze` per Task #5). Every shard's invariants trace
to a clause in that spec.
