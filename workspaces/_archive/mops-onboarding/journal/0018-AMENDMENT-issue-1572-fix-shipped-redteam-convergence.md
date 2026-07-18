# 0018 — AMENDMENT: #1572 bridge-loop pool drain shipped + redteam converged

**Date:** 2026-07-05
**Type:** AMENDMENT (of 0017 DISCOVERY/DECISION)
**Author:** agent
**Issue:** kailash-py #1572 → PR #1574 (fix) + #1575 (follow-up)
**relates_to:** 0017-DISCOVERY-issue-1572-bridge-loop-pool-leak-root-cause

## Outcome

Option A (approved in 0017) implemented, redteamed to convergence, committed on
`fix/dataflow-1572-bridge-loop-pool-drain` (commit `3ab9e0e4a`), pushed as **PR #1574**.

Fix shape (as approved): per-loop drain registry `kailash.utils.loop_pool_registry`
(core kailash, so both a DataFlow adapter pool AND a core `EnterpriseConnectionPool`
pool — covered transitively via its inner adapter `connect()` — register through one
path). The bridge `dataflow.core.async_utils._run_on_new_loop` marks its transient
loop and drains registered pools BEFORE `close()`. Applied to BOTH bridge branches
(thread-pool + the no-running-loop `asyncio.run` branch — same bug class). Registration
sites: core `async_sql.py` PG/MySQL `connect()`; dataflow `adapters/{mysql,postgresql}.py`
`create_connection_pool`. Marker-gated so persistent app loops (FastAPI/Jupyter) are
never registered/drained.

## Verification (first-hand)

Deterministic Tier-2 regression on real PG:5434 + MySQL:3307: `adapter._pool is None`
after `async_safe_run` returns. **Stash-flip proved the guard genuine** — with the fix
stashed, the test reproduced the EXACT #1572 symptom (`RuntimeError: Event loop is closed`
from `aiomysql/connection.py:1131 Connection.__del__`); with the fix applied, 10/10 green.
No regression across the existing async-bridge suite (66) + core adapters (5); collection
clean (6660).

## Redteam — 3 rounds to convergence

- **R1** (reviewer + security-reviewer + correctness adversary, parallel): no CRIT/HIGH.
  1 MED regression — the drain had no timeout; a hung `disconnect()` would block the
  bridge forever (pre-fix bare `asyncio.run` never awaited pool close, so this was a NEW
  hang surface). + several LOW. All folded: bounded each drain at 5s (`asyncio.wait_for`),
  `shutdown_default_executor` parity, removed unused `discard_loop` (orphan), regression
  markers + infra-skip guards, narrowed drain-error logs to `type(exc).__name__` (never
  `str(exc)` — no DSN can surface).
- **R2** (reviewer + adversary): CONVERGED — all R1 items confirmed closed first-hand;
  the `wait_for`-cancel-mid-`close()` bounded-leak is the intended tradeoff (strictly
  better than pre-fix leak AND better than infinite hang). All 5 correctness probes refuted.
- **R3** (fresh-eyes holistic): safe to commit; surfaced MED-1 (sibling non-bridge loops)
  - LOW-1 (in-scope log consistency). LOW-1 fixed; MED-1 deferred (below).

## Deferred (out of this shard's budget)

- **#1575 (filed):** sibling non-bridge transient loops (schema discovery `asyncio.run`
  in `engine._inspect_database_schema_real`, not in try/finally → leaks on exception;
  `new_event_loop()` in engine/model_registry; **owned/long-lived** `self._loop` in
  express/transactions which must NOT be drained via the transient registry). Heterogeneous,
  multi-subsystem, needs per-site transient-vs-owned analysis → a distinct shard, not a
  continuation (autonomous-execution Rule 4 bounded-by-budget carve-out).
- **ECP captured-ref (R1 Probe 1):** `EnterpriseConnectionPool._pool` keeps a ref to the
  drained pool; only bites on ECP-reuse-after-loop-death, which was already broken and the
  pools are one-shot. Pre-existing, not a regression. Folded into #1575's audit scope.
- **Cross-SDK:** the Rust SDK bridge may share this transient-loop pool-leak class
  (cross-sdk-inspection MUST-1). Needs a user-authorized cross-repo action per
  repo-scope-discipline — NOT self-initiated.

## Status

PR #1574 open; CI running at time of writing. Next: merge on green (admin), then /release
(BUILD-repo discipline — tag-triggered OIDC `dataflow-v<ver>`, no manual twine).
