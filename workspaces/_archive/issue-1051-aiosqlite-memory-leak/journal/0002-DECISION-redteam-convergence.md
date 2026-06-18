# 0002 — DECISION: #1051 /redteam convergence (Round 1)

**Date:** 2026-05-18
**Issue:** #1051 — aiosqlite :memory: Connection leak
**Commits:** `3093c5e41` (fix A-E) + `4d90221fb` (redteam hardening)
**Phase:** /redteam → release

## Verdict: CONVERGED Round 1

Both gate agents (parallel background, `rules/agents.md` MUST gate) returned
zero CRIT/HIGH. No Round 2 (zero blockers; the same-class in-budget findings
were fixed in `4d90221fb`).

## Durable receipts (per `rules/verify-resource-existence.md` MUST-4)

| Gate agent        | Task ID             | Verdict                                                                                                                                                                                                                                                                                           |
| ----------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| reviewer          | `a936c8a6dfd2af5f0` | CONVERGED — non-vacuity DEFINITIVELY proven (pre-fix via `git checkout 3093c5e41~1 -- <src>`: DataFlow=4, ProtectedDataFlow=8 survivors → post-fix 0); #1002/#1010/#1045 = 15 passed; collection clean single-path; patterns.md `__del__` unchanged; scope = exactly 3 files; 3 LOW informational |
| security-reviewer | `a1f8d90293821e352` | CLEAN — no blockers; no cross-tenant/instance widening; no use-after-close; no secrets; no cross-repo; 2 MEDIUM + 4 LOW                                                                                                                                                                           |

## Factual discrepancy resolved (security LOW-3 was a reviewer misread)

security-reviewer claimed shipped `engine.py` "still reads `hasattr(node,
"close")`" and "the node has a close() method". Independently verified:
shipped `engine.py` has `getattr(node,"cleanup",None) or getattr(node,
"close",None)` at ALL 3 sites (`:5919`, `:10056`, `:10204`); `python -c`
proves `AsyncSQLDatabaseNode` has `cleanup:True, close:False`. The
dataflow-specialist's keystone diagnosis was correct; the reviewer
grep'd the explanatory comment at `:10044` (which quotes the OLD
`hasattr(node,"close")` while describing the bug), not the code. The
1→0 regression result independently confirms Change E is live. **No code
defect; reviewer LOW-3 is a misread — no action.**

## Findings disposition (per `rules/autonomous-execution.md` MUST-4)

**Fixed in `4d90221fb` (same-class, in-shard-budget, my Change-C/D code):**

- Security MEDIUM-1 / reviewer LOW-1: `_owned_adapters` unbounded growth →
  dedupe + cap-32 + evict-disconnect.
- Security LOW-1: `cleanup()` swallow → `logger.debug` parity.
- Security LOW-4: regression gc probe → before/after delta.

**Follow-up (user-gated — pre-existing, DIFFERENT bug class, out of shard):**

- **Security MEDIUM-2**: transaction-abort path does not reset
  `_transaction_depth` / `_savepoint_counter` when `begin_transaction()`
  is cancelled/errors before commit/rollback — next `begin_transaction()`
  on the same adapter takes the SAVEPOINT branch against an
  unknown-outer-transaction connection. security-reviewer explicitly
  flagged this **PRE-EXISTING, not introduced by #1051**, per-adapter-
  instance (not cross-tenant), transaction-state-machine class (NOT the
  connection-leak class). Per MUST-4 bounded-by-shard + zero-tolerance
  Rule 1c (pre-existing, provable provenance — begin/commit/rollback
  untouched by this fix), the correct disposition is a tracked
  follow-up issue, NOT fix-immediately. **Surfaced to user for the
  filing decision** (consistent with the #1068 user-gated pattern).

**No-action LOWs:** security LOW-2 (`id(self)` cache-name, pre-existing
benign); security LOW-3 (reviewer misread, resolved above); reviewer
LOW-2 (stash-vs-parent-checkout process note); reviewer LOW-3 (cross-SDK
defer — compliant, surface-only per repo-scope-discipline).

## Next

- Release: core `kailash` (`async_sql.py`) + `kailash-dataflow`
  (`engine.py`) source change → real production fix shipping in BOTH
  package wheels → a `kailash` + `kailash-dataflow` PyPI release IS
  warranted. **Surface release scope to user** (do NOT auto-publish).
- Cross-SDK: kailash-rs SQLite-teardown name-mismatch audit — user
  files from a kailash-rs session (repo-scope-discipline).
