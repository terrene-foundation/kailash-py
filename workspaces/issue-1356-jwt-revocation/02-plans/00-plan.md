# Issue #1356 — JWTAuthManager token revocation is process-local

## Problem (verified against src/kailash/middleware/auth/jwt_auth.py @ 9f68ec637)

- `verify_token` (line 377) checks `self._blacklisted_tokens` — an in-memory `set`
  scoped to ONE manager instance.
- `revoke_token` (line 473) adds to that same in-memory set.
- In any multi-worker / multi-pod deployment (the default production topology),
  a token revoked on worker A stays valid on worker B until natural expiry.
- The class docstring lists "Token blacklisting" as a security best practice with
  NO caveat that it is process-local.

## Decision: pluggable shared revocation store (acceptance option 1, root-cause)

Per `/autonomize` (optimal/root-cause) + user memory `project_optimal_outcome`
("always choose optimal architecture"), fix the control rather than document the gap.

### Constraint that shapes the design

`verify_token()` / `revoke_token()` are **synchronous** public API on the
per-request hot path. Making them async to fit an async store (the
infrastructure/\*\_store.py idiom) is a breaking API change to a widely-used
surface. → The revocation-store contract is **synchronous**.

### Design (matches the established Protocol-backend-+-facade idiom, sync variant)

New file `src/kailash/middleware/auth/revocation.py`:

- `TokenRevocationStore(ABC)` — sync contract:
  - `revoke(*, jti, token=None, expires_at=None) -> None`
  - `is_revoked(*, jti=None, token=None) -> bool`
  - `count() -> int | None` (None = unknown for external stores; used by get_stats)
- `InMemoryTokenRevocationStore(TokenRevocationStore)` — DEFAULT, preserves exact
  current single-process behavior; keys by jti AND raw token (fallback for
  tokens that fail to decode at revoke time); TTL-aware lazy purge via expires_at.

Wiring into `JWTAuthManager`:

- `__init__(..., revocation_store: Optional[TokenRevocationStore] = None)`.
  - `enable_blacklist=False` → `self._revocation_store = None` (current no-op).
  - else → injected store, or `InMemoryTokenRevocationStore()` default.
- `verify_token`: decode first, then ONE `is_revoked(jti=jti, token=token)` check
  before returning payload; keep raising `jwt.InvalidTokenError("Token has been
revoked")` (NO exception-class change → no caller breakage).
- `revoke_token`: decode → jti + exp → `store.revoke(jti, token, expires_at)`;
  on decode failure → `store.revoke(jti=None, token=token)` (preserves "revoke
  even if verification fails").
- `get_stats`: `self._revocation_store.count()` (was `len(self._blacklisted_tokens)`).
- `_blacklisted_tokens` removed (private attr; zero src/test callers besides this file).

A SHARED backend (Redis/DB) is supplied by the user implementing the Protocol;
the SDK ships the contract + the in-memory default. This is the "injectable
revocation backend" the acceptance criteria names.

### Scope boundary (one shard, one invariant: revocation propagation)

- IN scope: access-token revocation blacklist (the filed issue).
- Documented as known process-local (NOT silently): refresh-token tracking
  (`_refresh_tokens`) and rate-limit (`_failed_attempts`) — same bug class, but
  expanding the store to cover them exceeds one shard + the issue. Surfaced to
  user as a follow-up, not silently dropped.

## Tests (regression)

1. `test_revocation_propagates_via_shared_store` — two managers sharing ONE
   `InMemoryTokenRevocationStore` instance (models a shared backend): revoke on
   A → B rejects. The fix's core contract.
2. `test_default_store_is_process_local` — two managers, default (separate)
   stores: documents the in-memory default is process-local by design.
3. `test_revoke_token_when_verification_fails_still_revokes` — preserves the
   line-484 "revoke even if decode fails" behavior.
4. `test_revocation_store_protocol_shape` — structural: contract methods present.
5. `test_get_stats_reports_revocation_count`.

## Cross-SDK (rules/cross-sdk-inspection.md)

kailash-rs JWT middleware is a SIBLING repo (`esperie-enterprise/kailash-rs`,
private). `rules/repo-scope-discipline.md` blocks reading it from this session.
→ Surface to user as a human-gated cross-SDK filing (upstream-issue-hygiene),
do NOT act cross-repo autonomously.
