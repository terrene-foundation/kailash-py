# 0026 — DECISION: #1695 trust-plane fix + kailash 2.48.1 security release

**Date:** 2026-07-12 · **Type:** DECISION · **Phase:** 05-codify · **Posture:** L5_DELEGATED

## Decision

Fixed, reviewed-to-convergence, shipped, and verified a trust-plane **privilege-escalation** fix
(#1695), then cut security release **kailash 2.48.1** (live on PyPI, clean-venv verified).

## The vulnerability (#1695)

At the default `VerificationLevel.STANDARD`, `TrustOperations.verify()` matched a capability by
name + expiry only; the per-`CapabilityAttestation` Ed25519 signature covering the grant CONTENT ran
only at `FULL`. An actor able to tamper the persisted chain could mutate a stored grant's content
(`read`→`delete`, or loosen constraints) while preserving its `id` (id-only chain-state hash
unaffected). All 12 enforcement surfaces default to STANDARD → the tamper was authorized.

## Fix (PR #1697, merged) — evidence

- STANDARD now verifies the matched capability's content signature via a shared
  `_verify_capability_signature` helper (FULL's `_verify_signatures` refactored to reuse it,
  byte-identical); fails closed + WARN on unresolved authority / malformed signature.
- **Gate-review HIGH (enforcement-surface parity):** the ops-less `EATPMCPServer._verify_from_store`
  path matched capabilities with NO signature check (default construction) → now **fails closed**.
- MEDIUM: malformed/empty signature raises `InvalidSignatureError` → caught, fail-closed.
- LOW: documented QUICK is not an enforcement level over untrusted chains.
- **RED→GREEN proven** (source-fix stashed → tests FAIL with `valid=True`; restored → DENY).
- 4 regression tests (`tests/regression/test_issue_1695_tampered_grant_default_verify.py`).
- **6535 trust tests pass, 0 regressions.**
- Reviews: security-reviewer APPROVE-WITH-FIXES → all applied → **CONVERGED (0 CRIT/0 HIGH)**;
  reviewer APPROVE.

## Release (PR #1698 → tag v2.48.1)

- Version 2.48.0→2.48.1 atomic (`pyproject.toml` + `__init__.py`); CHANGELOG security entry.
- `release/v2.48.1` branch auto-skipped the PR-gate matrix (a stale `build` duplicate was
  `cancelled` by concurrency, superseded by a `success` — admin-merged on the verified-green head).
- Tag pushed → `publish-pypi.yml` **success** → PyPI + GitHub Release.
- **Done gate:** clean-venv `pip install kailash==2.48.1` → `_verify_capability_signature` present.
- Patch release; TestPyPI skipped with human approval (per `deployment.md`).

## Cross-SDK (rs#1765)

Per `cross-sdk-inspection.md` Rule 1 + both reviewers' parity note, filed **rs#1765** on the Rust SDK
(user-authorized, grant `journal/0025`) — the same two-surface shape (STANDARD verify + ops-less
lightweight path) inspection. Scrubbed SDK-contract-level; back-linked on public py#1695 by role.

## Disposition

#1695 CLOSED; 2.48.1 shipped + verified; rs#1765 tracking the sibling. Consumers on 2.48.0 now have
the fix. Nothing further outstanding on this workstream.
