# GAP — MiddlewareAuthManager has no token revocation (sibling of #1356)

**Type:** GAP · **Surfaced by:** /redteam Round 1 security-reviewer (#1356) · **Date:** 2026-06-17

## Finding

`src/kailash/middleware/auth/auth_manager.py::MiddlewareAuthManager.verify_token`
(lines ~193-223) is a SECOND, independent JWT verifier in the same package
(exported, gated behind `_has_access_control`). It does `jwt.decode` + a manual
exp check with **no revocation consultation, no jti claim, and no `revoke_token`
method**. It is the legacy nodes-based ("was SDKAuthManager") auth system.

This is NOT the #1356 bug (process-local revocation in `JWTAuthManager`). The two
managers share **no** revocation state. `MiddlewareAuthManager` simply has no
revocation capability at all.

## Why deferred (not fixed in the #1356 PR)

Per `autonomous-execution.md` Rule 4: a same-class gap is fixed in-shard only if
it fits the shard budget. Retrofitting revocation onto `MiddlewareAuthManager` is
a NEW FEATURE, not a call-site sweep:

- its tokens carry no `jti` → either change the token format (breaking) or
  revoke by raw-token-string only;
- it needs a new `revoke_token` API + store wiring;
- it requires deciding which manager is the canonical production auth path.

This exceeds one shard and is a distinct design decision → tracked follow-up.
R2 + R3 security-reviewer confirmed the disposition sound: #1356 is fully closed
for `JWTAuthManager`.

## Disposition

- File a follow-up GH issue (HUMAN-GATED per `upstream-issue-hygiene.md` — drafted,
  awaiting user approval to file).
- Recommended fix when picked up: wire `MiddlewareAuthManager` to delegate
  verification to `JWTAuthManager`, OR give it its own injectable
  `TokenRevocationStore` + jti issuance.

## Cross-SDK (cross-sdk-inspection.md)

kailash-rs JWT middleware should be inspected for the same revocation-propagation
gap. Cross-repo (`esperie-enterprise/kailash-rs`, private) → human-gated; not
acted on from this session per `repo-scope-discipline.md`.
