# AMENDMENT — cross-repo handoff receipts (executed under grant 0007)

relates_to: 0007-cross-repo-grant-rust-sdk-handoffs

**Date:** 2026-07-10
**Type:** AMENDMENT

Records the actual outcomes of the cross-repo actions authorized in 0007 (user-approved this session; each scrubbed body shown to the user before posting per `upstream-issue-hygiene.md` MUST-1).

## Executed against esperie-enterprise/kailash-rs

- **rs#1667** (subject_hash / RFC 8785 JCS) — comment posted with the byte-verified golden vectors from py #1590 (encoder executed this session; not carried-forward). `.../issues/1667#issuecomment-4935836967`.
- **rs#1729** (NEW) — soft_delete/versioned parity-verification brief created (paired with py #1601); no pre-existing rs issue existed, so `gh issue create` (matching the 0002 parity-issue precedent). `.../issues/1729`.
- **rs#1707** (BH3 origin-auth) — NOT yet posted. Finding: Python BH3 origin-auth is UNIMPLEMENTED (no signing pre-images to re-pin). Per user decision this session, BH3 is being IMPLEMENTED Python-side first (branch `feat/eatp-1510-bh3-origin-auth`); the rs#1707 reference handoff posts once the Python reference bytes are verified.

## Paired py-side back-links (CWD-repo writes, in-scope)

- py #1590 → rs#1667 back-link: `.../issues/1590#issuecomment-4935838863`.
- py #1601 → rs#1729 back-link: `.../issues/1601#issuecomment-4935839022`.

## Scope confirmation

Only the three named actions against only kailash-rs + the two paired py back-links. No incidental reads, no scope creep. All rs bodies SDK-public-API-only, no consumer/workspace/finding tokens.
