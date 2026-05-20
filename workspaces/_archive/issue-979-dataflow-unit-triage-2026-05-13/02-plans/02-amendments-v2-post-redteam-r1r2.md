# Plan Amendments v2 — Post Red-Team Rounds 1 + 2

Date: 2026-05-13
Supersedes: `01-amendments-post-redteam.md` for the items below.
Receipts: `journal/0001`, `journal/0002`, `journal/0003`, plus R1+R2
adversary reports (Round 1: 3 agents; Round 2: 2 agents).

## Reconciled Findings (FINAL — Round 2 verdicts applied)

### Confirmed CRIT (3)

- **CRIT-B** — Double-filter trap on `-m` (R1 verified).
- **CRIT-C** — `pyproject.toml [tool.pytest.ini_options]` dead config
  (R1 verified). Consolidation needed.
- **ATTACK-2** — DEFENSE-2 sanitizer test as drafted is unrunnable;
  `sanitize_sql_input` is a nested closure at `nodes.py:787` (not
  module-importable). The Rule-2 `ValueError` is raised at
  `nodes.py:923-928` + `:988-989` only via `DataFlowNode.execute()`
  through `validate_inputs`. (R2 verified empirically.)
- **ATTACK-6** — `test_saas_tenancy.py` move to integration enables
  silent cross-tenant regression because `unified-ci.yml:8-26` /
  `:137-145` excludes integration markers on ALL PR runs AND the
  `tests/integration/` tree fires neither on push nor PR. The file
  itself is 100% mocked (pure-Python, no infra) — meets tier-1
  contract today.

### CRIT-A (pytest-forked) — Disposition unchanged, framing corrected

- R1 verified: package is NOT archived (`pushed_at`: 2026-04-14).
  Release-specialist's "archived since 2021" claim is wrong.
- BUT: zero consumer in `packages/kailash-dataflow/` (no `--forked`
  flag, no `pytest_forked` import). Drop justified by
  no-consumer, not by archived.

### Confirmed HIGH (4)

- **HIGH-B** — Fabric S3 move loses tier-1 SSRF + integrity signals.
  Confirmed real assertions in `test_ssrf.py:23-48` and
  `test_fabric_integrity.py`.
- **HIGH-E** — `test_workflow_binding.py:109-115` is the only tier-1
  verification of the 11-node string API. Uses 73 `memory_dataflow`
  refs; imports `LocalRuntime` but `runtime.execute` is only ever
  asserted via mock. STAY in tier-1; importorskip on the runtime
  import (or refactor import to a function).
- **HIGH-G** — `db.express` async surface = ZERO tier-1 coverage
  after S3. Verified: 53 `db.express|express_sync` refs in
  tests/unit/, all in `test_derived_model.py` (sync) or
  `tests/unit/fabric/test_express_pagination.py` (async; moves with
  S3). New smoke file required.
- **HIGH-H** — Zero regression tests in plan (per `rules/testing.md`
  § Regression). Need behavioral grep-invariants under
  `tests/regression/test_issue_979_*.py`.

### Downgraded HIGH → MED

- **HIGH-C → MED** — Tier-2 sanitizer tests DO exist at
  `tests/integration/security/test_connection_sql_injection_protection.py:82-91,
356, 366`. Tier-1 gap remains but no longer catastrophic.

### Falsified findings (removed from scope)

- **HIGH-D** — Live `ssrf.py:73-110` calls `socket.getaddrinfo`
  and runs `_check_ip_blocked` on every resolved IP. The
  security-reviewer's "validator does not resolve DNS" claim is
  wrong against `main`. Strike.
- **HIGH-F** — `tests/unit/test_engine_validate_record_bp049.py:25`
  imports `DataFlowEngine`. Coverage is thin but non-zero. Strike
  the "ZERO matches" claim.
- **Gap-1 (`--strict-markers` race)** — `tests/unit/conftest.py:162-171`
  registers markers via `pytest_configure` (hook fires BEFORE
  collection-time strict-markers). No race.

### New from Round 2

- **Gap-2 (HIGH)** — Dual coverage-config drift:
  `pytest.ini [coverage:run] source = packages/kailash-dataflow`
  vs `pyproject.toml [tool.coverage.run] source = ["src/dataflow"]`.
  Paths conflict; pick one and delete the other in S1.
- **Gap-3 (HIGH)** — asyncio scope keys ONLY in `pytest.ini:43`
  (`asyncio_default_fixture_loop_scope = function` +
  `asyncio_default_test_loop_scope = function`). pyproject lacks
  them. CRIT-C consolidation MUST preserve these.

## Path Decision (the central user-gate question)

Three viable paths emerged from the red-team rounds:

### OPTION-A — Full integrated plan (~14 shards)

Land everything in this workspace: S1 → S2a/b/c/d → S3 → S4 → S5a/b
→ S6 + AC#2 sub-shard + DEFENSE-2/3 + regression tests + engine and
express smoke tests.

Pros:

- Single workspace owns the entire cleanup
- Full PR-gate security signal preserved on merge

Cons (real, not glossed):

- ~7-10 sessions of work
- Cross-finding coupling — a defect in DEFENSE-2 stalls everything
- Some findings (HIGH-C tier-1 sanitizer) genuinely outside #979's brief

### OPTION-B — Tier-1 floor only (~6 shards, brief-strict)

Land only S1 + S2a + S3 + S4 + S5a + S6 (the original draft); defer
S2b/c/d, smoke tests, security compensations, regression scaffolding.

Pros:

- Smallest scope; fastest to land (~3 sessions)
- Brief-strict per `value-prioritization.md` MUST-5

Cons (real):

- AC#2 (test_dataflow_events.py) has NO owner (per R2's OPTION-C′
  analysis) — the brief's AC isn't met
- AC#6 (≤2 min suite green) may fail with S2b/c/d files still
  carrying tier-1 contract violations
- HIGH-B fabric tier-1 security loss ships without compensation
- HIGH-E (test_workflow_binding STAY) has no shard to enforce it

### OPTION-C′ — Split with corrections (R2 revised)

**Workstream-A (this workspace, ~8 shards):**

- S1 (preconditions, with CRIT-A/B/C/Gap-2/Gap-3 baked in)
- S2a (gallery → integration)
- S-EV (NEW — diagnose `test_dataflow_events.py` per AC#2)
- S3 (fabric → integration) **with DEFENSE-3 compensation in S6**
- S4 (Layer D PG audit + move, ~12 files, ATTACK-6 keeps tenancy)
- S5a (V5 tempfile refactor)
- S6 (gate + DEFENSE-3 sanitizer/SSRF tier-1 placeholder + CLAUDE.md alignment)
- HIGH-E inline in S2-shape audit (test_workflow_binding stays;
  no separate shard, just a documented "no-touch" entry)

**Workstream-B (new workspace `issue-979-followup-platform-gaps`, ~5 shards):**

- S2b (inspector files — heterogeneous, 4 files)
- S2c (SaaS template files — 6 files INCLUDING tenancy KEEPS in tier-1)
- S2d (other workflow-importers — 10 files)
- HIGH-G express async smoke
- HIGH-H regression scaffolding

**Workstream-C (separate platform issue, NOT this workspace):**

- HIGH-C tier-1 sanitizer contract tests (pre-existing scope)

Pros:

- A delivers all 7 ACs (per R2 verification)
- A's PR diff stays small; reviewer can audit in one session
- B's value-anchors cited from `briefs/00-brief.md:48-53` for each
- A re-lands #968 gate cleanly; B compounds value after

Cons (real):

- Two workspace administrative overhead
- B can decay if not picked up within 2 sessions (per
  `value-prioritization.md` MUST-3); mitigation: file as GH
  issues with explicit value-anchors at A-merge
- HIGH-B fabric move depends on DEFENSE-3 placeholder in S6,
  which is not trivial — but the placeholder can be a simple
  smoke test, not a full pentest harness

## Concrete shard amendments (apply to OPTION-A and OPTION-C′)

### S1 — Preconditions, expanded

Replace amendments-v1 S1 with:

Files: `packages/kailash-dataflow/pyproject.toml`,
`packages/kailash-dataflow/pytest.ini`.

Changes:

- Add `pytest-timeout>=2.3.0` to `[project.optional-dependencies] dev`.
- **DO NOT** add `pytest-forked` (zero consumer in dataflow).
- Add `timeout = 120` and `timeout_method = thread` to `pytest.ini`.
- Add `addopts` marker exclusion: `-m "not (requires_postgres or
requires_mysql or requires_redis or requires_docker)"` (this is
  the SOLE marker filter location — see S6).
- **Consolidate**: delete `[tool.pytest.ini_options]` from
  `pyproject.toml`. pytest.ini is canonical. (Per CRIT-C.)
- **Coverage consolidation**: delete `[tool.coverage.run]` from
  `pyproject.toml`. `[coverage:run]` in `pytest.ini` is canonical.
  (Per Gap-2.)
- **Preserve asyncio scope**: `asyncio_default_fixture_loop_scope`
  and `asyncio_default_test_loop_scope` keys stay in pytest.ini.
  (Per Gap-3 — relevant only if CRIT-C was inverted to consolidate
  to pyproject; here we go the other way.)

Verification: clean venv install + `pytest --collect-only` + a
deliberate `time.sleep(130)` test deselected after timeout fires.

Invariants: 5 (plugins available; per-test timeout fires; marker
filter applies in unit tier; coverage config single source; asyncio
scope unchanged).

Capacity: ≤80 LOC, 5 invariants — within budget.

### S6 — Gate + DEFENSE-3 placeholder + alignment

Replace amendments-v1 S6 with:

Files (in addition to v1):

- **NEW**: `packages/kailash-dataflow/tests/unit/security/test_fabric_smoke_invariants.py`
  — minimal tier-1 placeholder asserting SSRF validator rejects
  10.0.0.0/8 and `::ffff:127.0.0.1`, AND fabric-integrity middleware
  raises on tampered route. ~30 LOC. Closes COVERAGE-LOSS-1 + 2 in
  the pentest artifact. **Mandatory in BOTH OPTION-A and OPTION-C′**
  — fabric moves in both, HIGH-B applies to both. (R3 LOW-N1 fix.)
- **NEW**: `packages/kailash-dataflow/tests/unit/security/test_sanitizer_public_api.py`
  — DEFENSE-2 rewrite per ATTACK-2: invokes type-confusion guard
  through `db.express.create("User", {"name": {"$injection": "..."}})`
  with `User.name: str`, asserts `ValueError("parameter type
mismatch")` raised. ~40 LOC.
- `.github/workflows/unified-ci.yml`: new `test-dataflow` job —
  workflow has ZERO `-m` flag (S1's pytest.ini owns the filter).
  `paths:` includes both `packages/kailash-dataflow/**` AND
  `src/kailash/**` (per ci-runners.md Rule 5).
- `packages/kailash-dataflow/tests/unit/CLAUDE.md` updated.
- `packages/kailash-dataflow/tests/CLAUDE.md` documents `[fabric]`
  integration extra requirement.
- `specs/testing-tiers.md` adds `unit_test_suite` to fixture table
  (drift-2 from journal 0002).

Invariants: 6 — gate fires; gate fails on canary; pytest.ini sole
filter; sanitizer test exercises public API; fabric smoke covers
two threat classes; docs aligned.

Capacity: ≤350 LOC (workflow + 2 small test files + doc edits) —
within budget.

### S-EV — NEW shard (AC#2 owner) [OPTION-A and OPTION-C′]

Files: `packages/kailash-dataflow/tests/unit/features/test_dataflow_events.py`.

Per R1 dataflow-specialist + brief Scope boundaries (production code
fix permitted "if a failing test reveals a real bug"):

- Run `pytest tests/unit/features/test_dataflow_events.py -v -x` in
  a clean `[dev]`-only venv. Verify whether PR #976's "4+ failures"
  reproduce.
- If they reproduce: diagnose root cause; fix in production code if
  required (per zero-tolerance Rule 4).
- If they don't reproduce: document the dispostion + journal entry
  citing the clean-venv command output as receipt.

Capacity: ≤200 LOC, 3 invariants (file collects clean; all 11 tests
pass; no fixture-scope leakage between tests).

### S4 — Layer D scope correction (ATTACK-6)

Remove `test_saas_tenancy.py` from any move list. The file:

- is 100% mocked (verified lines 81-100, 404-419, 457-500)
- has 2 cross-tenant tests that are pure-Python
- collects fine without infra
- already MEETS tier-1 contract

S4's PG audit doesn't touch it. S2c (in Workstream-B if OPTION-C′)
keeps it in tier-1, not the move list. If OPTION-A: S2c excludes
tenancy from MOVE; keeps it in tier-1.

## Round 3 verification target

Round 3 confirms amendments-v2 resolves R2's open items:

1. ATTACK-2 fix uses public-API path (verify by reading the new
   `test_sanitizer_public_api.py` design)
2. ATTACK-6 fix keeps `test_saas_tenancy.py` in tier-1 (verify by
   reading S4 + S2c shard prompts)
3. Coverage consolidation choice is documented (verify by reading
   S1 amendment)
4. Asyncio scope preservation explicit (verify same)
5. AC#2 has an owner shard (verify S-EV exists for both OPTION-A and OPTION-C′)
6. HIGH-B fabric compensation present in OPTION-C′'s S6
   (verify the new test file design)

If Round 3 surfaces zero new CRIT/HIGH AND all 6 verifications
pass, CONVERGED.
