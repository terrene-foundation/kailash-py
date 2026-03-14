# ADR-004: Optional HMAC Overlay (DualSignature)

**Status**: Accepted
**Date**: 2026-03-14

## Context

Ed25519 provides strong external verification. Some deployments also need fast internal verification (e.g., service-to-service within a trust boundary) without the cost of asymmetric crypto.

## Decision

HMAC-SHA256 is an optional overlay on top of mandatory Ed25519. `DualSignature` carries both. HMAC alone is never sufficient for external verification.

## Rationale

- **Ed25519-first**: Asymmetric signatures are the foundation. HMAC is a convenience for internal fast-path.
- **Never HMAC-only**: External verifiers don't share the HMAC key. Ed25519 must always be present.
- **Backward compatible**: Ed25519-only path is unchanged. HMAC is only added when `hmac_key` is provided.
- **Constant-time**: HMAC verification uses `hmac.compare_digest()`, never `==`.

## Consequences

- `DualSignature.has_hmac` indicates whether HMAC is present.
- `dual_verify()` checks Ed25519 first (mandatory), then HMAC if present and key available.
- AWS KMS uses ECDSA P-256 (Ed25519 not available in KMS). The algorithm mismatch is documented.
