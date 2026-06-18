---
type: DECISION
date: 2026-06-18
author: co-authored
project: issue-1356-jwt-revocation
topic: MiddlewareAuthManager token revocation (F1 sibling of #1356) implemented
phase: implement
tags: [auth, jwt, revocation, security, cross-sdk, "1356-sibling"]
---

# DECISION — MiddlewareAuthManager token revocation implemented (F1)

Closes the F1 gap recorded in `0001-GAP-sibling-verifier-no-revocation.md`:
`MiddlewareAuthManager.verify_token` had no revocation capability (no `jti`, no
store consultation, no `revoke_token`). User directive this session: continue to
convergence under `/autonomize`.

## Approach chosen — Option 2 (own injectable store), NOT Option 1 (delegate)

The gap journal offered two fixes: (1) delegate verification to `JWTAuthManager`,
or (2) give `MiddlewareAuthManager` its own injectable `TokenRevocationStore` +
jti issuance. **Chose Option 2** because:

- It reuses the EXACT shared `TokenRevocationStore` ABC that #1356 shipped
  (`kailash/middleware/auth/revocation.py`), so ONE shared store can back BOTH
  managers in a deployment — the cross-worker propagation #1356 was about.
- Option 1 would force `MiddlewareAuthManager` to adopt `JWTAuthManager`'s token
  format/claims (different shape: `sub`/`tenant_id`/`token_type` vs
  `user_id`/`permissions`/`metadata`), a breaking change to its token contract.
  Option 2 is purely additive: it ADDS a `jti` claim, leaving existing claims
  intact.

## Changes (all in `src/kailash/middleware/auth/auth_manager.py`)

1. `__init__`: `enable_blacklist: bool = True` (matches `JWTConfig.enable_blacklist`
   default) + `revocation_store: Optional[TokenRevocationStore] = None`; wires
   `self._revocation_store = (revocation_store or InMemoryTokenRevocationStore())
if enable_blacklist else None` — mirrors `JWTAuthManager.__init__`.
2. `create_access_token`: adds `"jti": str(uuid.uuid4())` (the shared-store key).
3. `verify_token`: after decode, rejects `is_revoked(jti=, token=)` (BOTH passed
   per the #1356 invariant) with `HTTPException(401, "Token has been revoked")`;
   restructured the `except` so a deliberate 401 (revoked/expired) propagates
   with its real detail (`except HTTPException: raise` before the generic catch).
4. `revoke_token` (NEW, **async** per `patterns.md` paired-surface rule — create/
   verify/revoke must share async-ness): verify→extract jti+exp→revoke;
   decode-failure fallback revokes by raw token with TTL capped at
   `token_expiry_hours` (forged-future-exp defense, mirrors #1356).

## Pre-existing bug found + fixed (zero-tolerance Rule 1 — same file)

Three `security_logger.execute(severity="warning")` sites (1 new + 2 pre-existing
in `verify_token`/`verify_api_key`) passed an INVALID `SeverityLevel` — valid
values are `CRITICAL/HIGH/MEDIUM/LOW/INFO`. `SecurityEventNode` raised
`ValueError("'warning' is not a valid SeverityLevel")`, so before this change
EVERY invalid/expired token escaped `verify_token` as a raw `ValueError`, not a
clean 401. Fixed all three `"warning"→"MEDIUM"`. Regression-pinned by
`test_invalid_token_raises_clean_401_not_valueerror`.

## Tests

`tests/unit/middleware/test_middleware_auth_revocation.py` — 12 regression tests:
jti issuance, revoked-rejection-with-message, shared-store propagation,
process-local default, `enable_blacklist=False` no-op, decode-failure raw-token
record, forged-future-exp TTL cap, already-expired self-purge, backward-compat
(pre-jti token still verifies), custom-store protocol shape, clean-401 regression,
end-to-end FastAPI-dependency rejection. All 12 pass; #1356's 10 tests still pass.

## Cross-SDK (F2 — NOT acted on this session)

`cross-sdk-inspection.md` MUST-1: kailash-rs JWT middleware should be inspected
for the same MiddlewareAuthManager-equivalent revocation gap. That is cross-repo
(`esperie-enterprise/kailash-rs`, private) → human-gated per
`repo-scope-discipline.md`; needs its own kailash-rs session. Surfaced, not acted.

## For Discussion

1. Counterfactual: if a deployment runs `MiddlewareAuthManager` AND
   `JWTAuthManager` side by side but injects the shared store into only one,
   revocations made through the other won't propagate — is documenting "inject
   the same store into both" sufficient, or should a future Nexus auth facade
   construct one store and pass it to both managers?
2. The decode-failure fallback caps the TTL at `token_expiry_hours`; an operator
   who sets a very long `token_expiry_hours` (e.g. 720h) gives forged-exp entries
   a 30-day floor in the store. Is that acceptable, or should the cap be a
   separate, shorter bound?
3. `enable_blacklist=True` is the secure default and is backward-compatible
   (additive jti + empty-store no-op). Should any existing deployment expect a
   behavior change? (Analysis says no — confirm against any in-tree consumer.)
