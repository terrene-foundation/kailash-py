# DISCOVERY — #1050 protection orphan confirmed by independent 2-agent verification

**Date:** 2026-05-17
**Phase:** /analyze

## Finding

`WriteProtectionEngine.check_operation()` has exactly 2 production call
sites, BOTH synchronous (`protection_middleware.py:367` in
`ProtectedNode.run()`; `:422` in `AsyncSQLProtectionWrapper`'s sync `def`
closure). Every real user path (`db.express.*`, `runtime.execute(
workflow.build())`) dispatches through `AsyncNode.execute_async` →
`async_run`, which `ProtectedNode` does NOT override. The security feature
is unreachable on the documented default path — facade orphan,
`orphan-detection.md` §1, same shape as Phase-5.11
`TrustAwareQueryExecutor`.

## Why journal-worthy

Confirms the issue's root cause is accurate (not a misframed brief) BEFORE
fix design — the verification gate per `rules/agents.md`. Two independent
`general-purpose` agents (agentId a700bd897512aa8fe cluster A, agentId
ad8a3f8202d0121da cluster B), parallel, fresh re-grep of `main`, both
CONFIRMED. Line numbers in the issue body had drifted; actuals recorded in
`01-analysis/01-rootcause-verification.md`. The issue's structural
analysis was exact.

## Consequence

Fix is engine-wiring on the async path, not a logic bug in the engine.
Candidate insertion points P1 (`ProtectedNode.async_run` override) / P2
(express-layer hook ×13) / P3 (async SQL wrapper) — P1 covers both
user paths at one site. Specialist evaluation is task #2.
