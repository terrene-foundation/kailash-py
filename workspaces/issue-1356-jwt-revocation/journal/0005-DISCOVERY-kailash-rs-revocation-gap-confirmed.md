---
type: DISCOVERY
date: 2026-06-18
author: agent
project: issue-1356-jwt-revocation
topic: kailash-rs Nexus JWT middleware has the same revocation gap (F2 confirmed)
phase: redteam
tags: [cross-sdk, kailash-rs, jwt, revocation, "F2", eatp-d6]
relates_to: 0004-AUTHORIZATION-cross-repo-kailash-rs-revocation-parity
---

# DISCOVERY — kailash-rs Nexus JWT middleware has the same revocation gap (F2)

Authorized read-only cross-SDK inspection (receipt: `0004`). Read-only; no writes
to kailash-rs. Repo confirmed `git@github.com:esperie-enterprise/kailash-rs.git`
at `/Users/esperie/repos/loom/kailash-rs` (branch `main`).

## Finding: SAME GAP CONFIRMED

The kailash-rs Nexus JWT middleware verifier has the SAME no-revocation gap that
kailash-py `MiddlewareAuthManager` had pre-2.38.3.

**Evidence (quoted):**

- `crates/kailash-nexus/src/auth/jwt.rs:177` — the `JwtAuthLayer` middleware
  delegates verification to `kailash_auth::jwt::decode_jwt` and just injects the
  decoded claims into request extensions. No revocation step.
- `crates/kailash-auth/src/jwt/mod.rs:334-353` — the canonical `decode_jwt`:
  ```rust
  pub fn decode_jwt(token, config) -> Result<JwtClaims, AuthError> {
      config.validate()?;
      let token_data = jsonwebtoken::decode::<JwtClaims>(token, &key, &validation)?;
      if let Some(max_age) = config.max_age_secs { /* absolute age check */ }
      Ok(token_data.claims)
  }
  ```
  Signature + exp (via `build_validation`) + absolute-age only. NO revocation
  consultation, NO `jti`, NO revoke method.
- `grep -rnE "jti|revoc|is_revoked|revoke" crates/kailash-auth/src/` → EMPTY.
  `kailash-auth` (the crate the Nexus middleware verifies through) has no
  revocation concept and `JwtClaims` carries no `jti`.
- `grep -rnE "is_revoked|revoke|RevocationStore|TokenManager|revocation"
crates/kailash-nexus/src/` → EMPTY. The Nexus auth path does NOT wire the
  enterprise revocation in.

**The revocation-aware manager EXISTS but is unwired (the `JWTAuthManager`
analog):** `crates/kailash-enterprise/src/token/{store,manager}.rs` ships a
`TokenStore` trait (`revoke()` + `is_revoked()`) + `InMemoryTokenStore` default +
a `TokenManager` whose `validate()` "checks revocation first" and whose tokens
carry a `jti` (uuid4). This is the structural analog of kailash-py's
`JWTAuthManager` (revocation-aware, #1356). But the Nexus _middleware_ verify
path uses `kailash-auth::decode_jwt`, not the enterprise `TokenManager` — so the
middleware-authenticated path silently bypasses revocation.

## Cross-SDK parity (EATP D6)

This is the Rust equivalent of the kailash-py F1 gap (closed in 2.38.3). The
kailash-py fix wired the existing `TokenRevocationStore` into the legacy
middleware verifier (`MiddlewareAuthManager`). The kailash-rs equivalent fix
would wire `kailash-enterprise`'s `TokenStore`/`TokenManager` revocation into the
Nexus `JwtAuthLayer` verify path (or give `kailash-auth::decode_jwt` an optional
injectable revocation check) so a revoked token presented through the Nexus
middleware is rejected.

## Disposition — HUMAN-GATED, NOT acted on this session

- A cross-SDK issue against `esperie-enterprise/kailash-rs` is the correct next
  step (`cross-sdk-inspection.md` MUST-1/2). Filing it is a cross-repo WRITE and
  is **human-gated** (`upstream-issue-hygiene.md` MUST-1) — NOT covered by the
  READ-only authorization in `0004`. A scrubbed draft is presented in the session
  report for the user's filing decision; this session did NOT file it.
- A FIX is a kailash-rs session's work (cross-repo write; separate authorization).

## For Discussion

1. Should the kailash-rs fix wire revocation at the Nexus `JwtAuthLayer` (narrow,
   middleware-only) or push it into `kailash-auth::decode_jwt` via an optional
   injectable revocation checker (broader, covers every `decode_jwt` caller)?
2. kailash-py shipped `MiddlewareAuthManager` revocation as a patch (2.38.3); the
   kailash-rs equivalent adds a `jti` claim + an injectable check — additive, so
   likely also a patch on the affected crate(s). Confirm at fix time.
