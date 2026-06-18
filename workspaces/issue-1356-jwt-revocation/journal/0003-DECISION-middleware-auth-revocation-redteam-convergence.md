---
type: DECISION
date: 2026-06-18
author: agent
project: issue-1356-jwt-revocation
topic: MiddlewareAuthManager revocation (F1) — redteam convergence + R1/R2 hardening
phase: redteam
tags: [auth, jwt, revocation, security, redteam, convergence, "1356-sibling"]
relates_to: 0002-DECISION-middleware-auth-revocation-implemented
---

# DECISION — F1 redteam converged (R1 + R2), two LOW findings fixed

Extends `0002` (which described the implement-phase 12-test state). Records the
adversarial redteam-to-convergence on PR #1365 and the fixes it produced.

## Redteam method

4-lens adversarial review per round (concurrency capped at 3 per
`worktree-isolation.md` Rule 4 after a 4-wide launch hit the synchronized
server throttle), each lens producing schema'd findings, then adversarial
verify of every MED+ finding:

- **reviewer** (code correctness + mechanical sweeps)
- **security-reviewer** (threat model: bypass / accept-on-error / DoS / leakage)
- **closure-parity** (gap actually closed by delivered+tested code; #1356 parity)
- **bypass-attacker** (ran a 9-vector Python probe attempting real bypasses)

## Round receipts (durable, per `verify-resource-existence.md` MUST-4)

- **R1** (workflow task `wxc08pd6a`): 4/4 lenses returned. reviewer APPROVE;
  security + closure APPROVE_WITH_FIXES; bypass APPROVE (no bypass reproduced
  across 9 vectors; fail-closed-on-store-down confirmed). 1 MED raised
  (revocation-vs-expiration ordering) → **adversarially REFUTED** (jwt.decode
  validates exp first; both paths reject). 0 confirmed-actionable MED+.
- **R2** (workflow task `wfyx8e1j2`, after the R1 LOW fix): **all 4 lenses
  APPROVE; 0 confirmed-actionable MED+.** Two consecutive clean rounds on the
  security-critical surface = converged.

## Fixes applied during convergence

1. **R1 LOW (closure)** — `revoke_token`'s audit-log path (`enable_audit=True`,
   the production default) had no test coverage; every test used
   `enable_audit=False`. Added `test_revoke_token_audit_path_does_not_raise`
   (commit 07ad10741). Same kwarg/severity-mismatch bug class as the severity
   fix two lines away.
2. **R2 LOW (bypass)** — a `SecurityEventNode.execute` failure inside the
   revoked / verification-failed branch escaped `verify_token` as a raw
   exception (HTTP 500) instead of a clean 401 (fail-closed availability defect,
   NOT a bypass — the token was still rejected). Added a best-effort
   `_emit_security_event` helper that swallows logging-backend failures (records
   a fallback line via the module logger) and rewired all 3 security-event sites
   (`token_revoked`, `token_verification_failed`, `api_key_verification_failed`)
   through it. A logging failure can no longer convert a 401 into a 500. Pinned
   by `test_logging_failure_does_not_break_revocation_401`.

## Test count

14 regression tests in `tests/unit/middleware/test_middleware_auth_revocation.py`
(12 at implement-time per `0002`, +1 audit-path R1, +1 best-effort-logging R2).
All 14 pass; #1356's 10 tests still pass (24 total). Count produced by
`pytest --collect-only -q | grep -c '::'`.

## Dispositioned, NOT changed (with rationale)

- Decode-failure fallback re-decodes the token twice — **intentional parity**
  with #1356's `jwt_auth.py`; changing it would diverge from the proven reference.
- `details=` payload dropped by `SecurityEventNode` — **pre-existing node
  behavior**; `event_type` already conveys the reason; changing the node is
  out of scope for this PR.
- Revocation-before-expiration ordering / manual exp check dead code — **INFO,
  pre-existing**; jwt.decode validates exp first, so it is unreachable for
  tokens carrying an exp claim. Not introduced by this PR.
- Two tests inspect the store's private `_revoked` dict — **parity** with the
  #1356 test pattern (no public API exposes the stored TTL to assert the cap).

## For Discussion

1. Counterfactual: the best-effort `_emit_security_event` now swallows ALL
   SecurityEventNode failures — does silently dropping a security-event log
   (with only a module-logger fallback) ever hide a signal an operator needs,
   or is fail-closed-on-auth strictly the right trade for an auth hot path?
2. The R2 bypass finding was availability-only (500 vs 401). Should the
   #1356 `JWTAuthManager` reference adopt the same best-effort pattern for
   cross-manager consistency, or is its non-raising stdlib logger already safe?
3. Two consecutive clean rounds (R1 refuted-MED+R2 all-APPROVE) plus a post-fix
   confirmation round is the convergence bar applied here — is that the right
   rigor for a security-critical auth change, or is a single clean round after
   the last fix sufficient given the fix is a defensive try/except?
