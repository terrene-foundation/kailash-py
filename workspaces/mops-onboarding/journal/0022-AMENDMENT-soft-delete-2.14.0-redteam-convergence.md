---
type: AMENDMENT
date: 2026-07-07
author: agent
project: kailash-py / kailash-dataflow
topic: /redteam convergence of the released soft_delete completion (2.14.0) — 2 HIGH found, fixed, verified; 2.14.1 patch pending
phase: redteam
tags: [dataflow, soft_delete, redteam, observability, security, changelog-accuracy, 2.14.1]
relates_to: 0021-AMENDMENT-issue-1585-bulk-transaction-awareness-shipped
---

# 0022 — AMENDMENT: soft_delete 2.14.0 /redteam → convergence (2 HIGH fixed)

**What:** Audit-mode `/redteam` of the ALREADY-MERGED-AND-RELEASED soft_delete
completion (kailash-dataflow **2.14.0**, PR #1598, feat commit `beb5307bd`). The
shipping session had no formal redteam convergence receipt; this closes that gap.
Posture **L5_DELEGATED**. Converged on **2 consecutive clean rounds**.

## Method

Round 1 = 3 parallel adversarial agents scoped to the #1598 diff (curated
governance slices per `governed-throughput.md`) + orchestrator mechanical floor:
- **dataflow-specialist** (behavioral, live PG+SQLite): **0 CRIT / 0 HIGH**. All 7
  soft_delete invariants verified with live probes. Notably: the #1600 strict-xfail
  pins a GENUINE generic auto-migrate-ALTER gap (not soft_delete-specific), and when
  auto-migrate cannot ALTER-ADD, the tombstone UPDATE **raises loudly and preserves
  the row** — no silent hard-delete fallback. Cross-tenant un-delete attack BLOCKED
  (live probe: `records_processed=0`).
- **security-reviewer** (static): **0 CRIT / 1 HIGH**. SQL-injection, classification
  redaction, and tenant isolation all PASS with cited evidence.
- **reviewer** (code-quality): **1 HIGH**.

## Findings (both HIGH — fixed this session; released as pending 2.14.1)

### HIGH-1 — `versioned` model-flag removal was incomplete; released CHANGELOG over-claimed
2.14.0 removed the advertised-but-unimplemented `versioned` flag from five docs
files and its CHANGELOG asserted "the docs no longer advertise it" — but three
UNTOUCHED files still shipped it with zero backing code: `examples/03_enterprise_integration.py`
(3 model blocks), `examples/enterprise/README.md`, and `docs/advanced/database-optimization.md`
(the last documenting a fictional `OptimisticUpdateNode` / `optimistic_lock` /
`retry_on_conflict` API — `grep src/` → empty). A user copying `versioned: True` gets a
silent no-op. `zero-tolerance.md` Rule 2 (fake feature in shipped examples) +
`verify-claims-before-write` (false released CHANGELOG claim).
**Fix:** dropped every `versioned` flag (inventory example switched to real `soft_delete`),
deleted the fictional Optimistic-Locking section, corrected the CHANGELOG. Residue now 0.

### HIGH-2 — bulk PII/schema logging: instrumentation emitted raw row values at WARN
2.14.0 downgraded the bulk_update/bulk_delete query+params EXECUTION logs to DEBUG but
left sibling instrumentation at WARN across all four bulk verbs — including the four
`BULK_* ENTRY` traces (raw `data`/`update_values`/`kwargs`) and the four `*_success`
traces (raw `filter`/`update` row values). `observability.md` Rule 8 + `security.md`
§ "No secrets in logs". **Fix:** full sweep — every pure-instrumentation and
success-metadata trace → DEBUG (15 sites); only 4 `logger.warning` remain (2
`Empty filter detected` dangerous-path signals + 2 per-record skip signals now logging
only `keys=sorted(...)` / `id=...`, never raw values). Genuine error paths keep
`logger.error` (12, unchanged); no partial-failure signal downgraded (Rule 7).
Also: `_model_has_tenant_field`'s bare `except: return False` now logs a WARN
before returning (`zero-tolerance.md` Rule 3), + `import logging` at module scope.

## Institutional lesson — the refutation cycle (why independent verify is load-bearing)

My FIRST fix of HIGH-2 was itself **incomplete** (I worked the logging sweep from
memory, missed the entire `bulk_upsert` path + the `*_success` PII traces) AND I wrote
a CHANGELOG bullet that **over-claimed** ("UPSERT ENTRY … now DEBUG" when it wasn't) —
committing a `verify-claims-before-write` violation *while fixing one*. An independent
adversarial verify pass REFUTED the "clean" claim and enumerated every miss. Second
fix: enumerated EVERY `logger.warning` first, classified each, swept completely, then
grep-verified only-4-remain BEFORE rewriting the CHANGELOG to match reality. **Takeaway:
a sweep claim ("all sites downgraded") is a code-claim — enumerate-then-verify before
asserting it, never sweep from memory. The self-attested "clean" round was wrong;
the independent verify caught it.** This is the `verify-resource-existence.md` MUST-4
receipt discipline in action.

## Convergence receipt (posture-invariant, L5)

- Contract `test_soft_delete_lifecycle.py`: **17 passed + 1 strict-xfail** (#1600) — stable across R1→R4.
- `bulk_operations/` suite: **46 passed, 0 failed** (exercises all 4 edited verbs).
- Collection merge-gate: **6743 tests collected**, no ModuleNotFoundError.
- Mechanical: versioned/optimistic residue **0**; bulk.py `logger.warning` **4** (all legit); added stub markers **0**.
- Round history: R1 (2 HIGH) → fix → **R2-verify REFUTED** (incomplete sweep + over-claim) → complete fix → **R3-verify reviewer CLEAN (close-parity, all findings resolved)** → **R4 mechanical CLEAN** = 2 consecutive clean rounds.

## Fix diff (working tree — NOT yet committed; 2.14.1 release is user-gated, BUILD repo)

`bulk.py` (logging sweep + fail-open log + import), `examples/03_enterprise_integration.py`,
`examples/enterprise/README.md`, `docs/advanced/database-optimization.md`, `CHANGELOG.md`
(`[Unreleased]`). Src changed → NOT a release carve-out → **2.14.1 patch required**.

## Out-of-scope follow-ups (surfaced, NOT fixed — separate class/shard)

- **LOW (security, pre-existing):** general `bulk_update` SET/WHERE clause interpolates the
  column *identifier* without `dialect.quote_identifier()` (values ARE bound = currently safe;
  keys are trusted model field names). Defense-in-depth gap; the soft_delete surfaces
  (`deleted_at` literal, registry table_name) are safe. Recommend a follow-up issue to quote
  identifiers in `features/bulk.py` matching `core/nodes.py`/`engine.py`.
- **LOW (behavioral):** `express.find_one` has no `include_deleted` escape hatch (API-completeness, not a bug).
- **LOW (envelope):** `bulk_update(include_deleted=True, {"deleted_at": None})` un-delete is ordinary
  update authorization (tenant-scoped, documented) — deployment PACT/Nexus policy should scope who may call it.
- **Pre-existing (#1594):** `test_bulk_upsert_comprehensive::test_bulk_upsert_large_mixed_batch` hang +
  `test_v052` failures — proven pre-existing on main, separate tracked issue, did NOT manifest in R1-R4 runs.

## Next

Present 2.14.1 release decision to the user (BUILD-repo structural gate). On authorization:
branch → PR → merge → bump 2.14.0→2.14.1 → `/release` kailash-dataflow → PyPI installable verify.
