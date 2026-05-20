# #1050 — Decomposition / Shard Plan (revised post-red-team)

Per `autonomous-execution.md` § Per-Session Capacity Budget. Each shard
carries a value-anchor citing a user-anchored source (user's
session-start approval of #1050 as the CRITICAL workstream + issue #1050
acceptance criteria + `briefs/00-brief.md`). Design source:
`01-analysis/02-fix-design.md` (revised — Option (a)). Contract:
`specs/dataflow-protection.md` §1–3 (invariants I1–I9). Red-team status:
CRITICAL (execute_async wraps ProtectionViolation) found + resolved;
Option-(a) blast-radius + I9-existing-behavior independently re-verified
TRUE (journal 0003).

## Shard 1a — ProtectionViolation exception-taxonomy re-base

**Value-anchor:** Without this, a blocked write on the workflow path
surfaces as a generic execution error, not a protection violation —
operators' protection-aware error handling and the issue's AC#3
("enforced via `runtime.execute(workflow.build())`") silently fail. This
is the load-bearing half of making the opt-in security feature actually
observable as a protection block (issue #1050 AC#3 + I5; user approved
#1050 as the CRITICAL security workstream).

**Scope:** `protection.py` — `class ProtectionViolation(NodeExecutionError)`
(import `NodeExecutionError` from `kailash.sdk_exceptions`; dataflow→core,
correct direction). CHANGELOG entry: public exception-taxonomy change
(downstream `except NodeExecutionError` now also catches
`ProtectionViolation` — R7). NO code behavior change beyond the base
class; the propagation correctness is what this delivers.

**Budget:** ~5 LOC + CHANGELOG. Invariants: I5 + taxonomy-compat (≤4).
Call-graph: ProtectionViolation → execute_async re-raise allowlist (2
hops). Blast-radius audit already done (journal 0003: 9 `except
NodeExecutionError` sites, zero class-(iii); no ordering hazard). **One
shard. Lands first.**

**Specialist:** dataflow-specialist.

## Shard 1b — async_run override + delete dead sync override + restore gap-tests

**Value-anchor:** This is the enforcement wiring itself — it makes
`ProtectedDataFlow` actually block writes on `db.express.*` (the
documented default) and the workflow path. Without it the opt-in safety
feature is a no-op (issue #1050 CRITICAL core defect; `briefs/00-brief.md`).

**Scope:** `protection_middleware.py` `protect_dataflow_node()`: add
`async def async_run(self, **kwargs)` invoking `check_operation` (args
from `self.operation` / `self.model_name` / `self.dataflow_instance`;
routes blocks through `_handle_violation` → satisfies I9 automatically),
then `return await super().async_run(**kwargs)`; DELETE the dead sync
`run()` override (closes I1). Same commit: restore the 2 intent-changed
tests in `tests/unit/test_protection_system_critical_gaps.py`
(`# KNOWN COVERAGE GAP — tracked: issue #1050`) to assert end-to-end
runtime-path enforcement (`orphan-detection.md` §4a — same commit or
release CI flips them red).

**Budget:** ~40–60 LOC + ~40 LOC test restore. Invariants: I1, I2, I3,
I6, I9 (5 — at budget edge, acceptable: live feedback loop via the
restored unit tests + Shard 3). Hops: async_run → check_operation →
\_handle_violation (3). **One shard. Depends on 1a.**

**Specialist:** dataflow-specialist.

## Shard 2 — Workflow-runtime path Tier-2 (regression guard for the red-team finding)

**Value-anchor:** Issue #1050 AC#3 — protection MUST enforce via
`runtime.execute(workflow.build())`, not only Express. This shard is the
permanent regression guard for the CRITICAL the red-team caught: it pins
both that a block raises AND that the type survives the runtime's
exception re-wrap.

**Scope:** Tier-2 — `WorkflowBuilder` with a generated `*CreateNode`,
executed via plain `LocalRuntime` AND `AsyncLocalRuntime` against a
protected `db` (NOT only `ProtectedDataFlowRuntime` — the plain runtimes
are where the re-wrap bug lived). Assert `pytest.raises(ProtectionViolation)`
PLUS `isinstance(exc, NodeExecutionError)` (pins the Option-(a)
taxonomy). Real Postgres + file-backed SQLite (NOT `:memory:` — that
isolation masked the orphan).

**Budget:** ~35 LOC. Invariants I2, I5. **One shard. Depends on 1a+1b.
Parallels Shard 3.**

**Specialist:** testing-specialist.

## Shard 3 — Per-mutation-surface Tier-2 matrix

**Value-anchor:** Issue #1050 AC#1+2 — protection MUST enforce on EVERY
mutation surface and MUST NOT block read/list/count. Bulk + upsert were
_never_ enforced (worse orphan than single-record); this matrix is the
proof the promise holds for the operations users actually run.

**Scope:** One Tier-2 test per protected mutation surface
(create/update/delete/upsert/bulk_create/bulk_update/bulk_delete/
bulk_upsert) asserting BLOCK; explicit NOT-blocked assertions for
read/list/count under read-only (pins I7; prevents the latent
`count`-over-block regressing — `02-fix-design.md` R2); one model-level +
one field-level test (pins I4); one assertion that a blocked op leaves an
audit record via `get_protection_audit_log()` (pins I9 — R8). Real
Postgres + file-backed SQLite.

**Budget:** ~9–12 methods, ~280–380 LOC boilerplate stamped from one
pattern → one shard per boilerplate-scales clause. If PG+SQLite
duplication exceeds budget, split 3a {write-block} / 3b {read-allow} / 3c
{model+field+audit}.

**Specialist:** testing-specialist.

## Shard 4 — Cross-SDK inspection (read-only)

**Value-anchor:** Issue #1050 AC#6 (`cross-sdk` label) — the same
sync-vs-async dispatch bypass may exist in kailash-rs; user flagged
#1050 cross-sdk.

**Scope:** Read-only inspection of whether kailash-rs has an equivalent
sync-only protection override bypassed by an async dispatch path. Record
the finding in this workspace's journal. **MUST NOT edit kailash-rs from
this session** (`repo-scope-discipline.md`). If a defect is confirmed,
draft (do NOT file) an upstream issue body per `upstream-issue-hygiene.md`;
filing is a separate human-gated action.

**Budget:** read-only + journal entry. **One shard. Parallels 2/3.**

**Specialist:** general-purpose (read-only; no kailash-rs writes).

## Follow-up (NOT bundled — distinct bug class)

`AsyncSQLProtectionWrapper` + the global `node_class.execute =
protected_execute` monkeypatch (`protection_middleware.py:394-451`)
become provably dead after Shard 1b (`02-fix-design.md` WU-5, R6).
Deleting them is a different bug class (orphan cleanup, not the security
fix) and exceeds the same-bug-class shard test
(`autonomous-execution.md` Rule 4). **File as a separate GH issue at
/redteam or /codify** — do NOT bundle. Value-anchor: removes a dead,
instance-contaminating monkeypatch surface (`orphan-detection.md` §3);
NOT user-brief-anchored, so filed as a tracked issue, not carried
silently.

## Sequencing

```
Shard 1a (taxonomy) ──▶ Shard 1b (wiring + gap-tests) ──┐
                                                        ├─▶ Shard 2 (runtime Tier-2) ┐
                                                        ├─▶ Shard 3 (mutation matrix)├─ parallel
                                                        └─▶ Shard 4 (cross-SDK)      ┘
```

- 1a → 1b are sequential (1b's wiring relies on 1a's taxonomy so Shard-2
  assertions hold).
- 1a+1b ship together as the security PR; **security-reviewer gate is
  MANDATORY before merge** (`security` label + `agents.md` MUST gate at
  `/implement`). reviewer + security-reviewer in parallel.
- Shards 2/3/4 parallel after the security PR merges.

## Risks carried into /todos (from revised 02-fix-design.md)

- **R1** behavior change — writes that "worked" only because protection
  was a no-op now correctly raise. CHANGELOG MUST call this out as a
  security behavior change; no deprecation shim (a fake gate made real is
  not a removal, `zero-tolerance.md` Rule 2).
- **R2** read/list/count MUST NOT block — Shard 3 pins.
- **R4** `dataflow_instance`-not-bound fail-open is pre-existing
  (inherited from sync override), NOT introduced here; flag to reviewer
  for a possible fail-closed follow-up — out of scope for the orphan fix.
- **R7** public exception-taxonomy change (Shard 1a) — `except
NodeExecutionError` downstream now also catches `ProtectionViolation`;
  blast-radius audited clean (journal 0003), CHANGELOG-documented.
- **R8** I9 audit-on-block is existing behavior; Shard 3 adds the
  behavioral regression assertion (LOW).
