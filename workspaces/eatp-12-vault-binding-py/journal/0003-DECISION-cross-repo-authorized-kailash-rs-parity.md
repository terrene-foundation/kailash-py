---
type: DECISION
slug: cross-repo-authorized-kailash-rs-parity
created: 2026-06-14T03:45:00Z
---

# Cross-Repo Authorization — kailash-rs EATP-12 parity (READ + DRAFT issue)

cross-repo-authorized: esperie-enterprise/kailash-rs

## Grant (repo-scope-discipline § User-Authorized Exception — all 5 conditions)

1. **User-initiated:** genuine user turn (2026-06-14) — verbatim: "ensure
   kailash-rs is on parity with this as well".
2. **Explicit + specific:** target `esperie-enterprise/kailash-rs` (local clone
   `/Users/esperie/repos/loom/kailash-rs`, default branch `main`); bounded
   action = (a) READ-ONLY assessment of kailash-rs's parity on BOTH threads of
   the user's "ensure kailash-rs is on parity with this as well" directive —
   (i) EATP-08 ISS-32 (the kailash-py #1315 fix just merged here, whose sibling
   mint identifies as kailash-rs#1315) and (ii) EATP-12 Trust Vault Key-Binding
   (the #1312 plan) — across open issues/PRs + the trust/vault + signing/alg-id
   source surface, AND (b) DRAFT (not file) a sibling cross-SDK
   conformance-tracker issue. Filing the drafted issue is GATED on a
   separate same-session user y/n per `upstream-issue-hygiene.md` MUST-1
   (drafting permitted; submission needs explicit per-issue approval).
3. **Confirmed:** restated in the session report + here before any cross-repo
   command runs.
4. **Journaled before acting:** this entry lands BEFORE the first read of any
   kailash-rs path or `gh ... --repo esperie-enterprise/kailash-rs` call.
5. **Scoped exactly:** ONLY the EATP-12 parity read + an issue draft against
   `esperie-enterprise/kailash-rs`. NO code write to kailash-rs (its binding
   work happens in its own session). NO incidental reads beyond the EATP-12
   surface. The cross-SDK byte-parity reconciliation itself (V6 commitment / KCV
   / audit pre-image, the non-ASCII sentinel) is a later release-coordination
   step needing its own grant when reached.

## Why

The EATP-12 spec mandates cross-SDK byte-parity (V6) and forbids either SDK
releasing vault binding before parity is reconciled. The user directed kailash-rs
parity explicitly. This grant covers the READ to assess current rs state +
DRAFTING a sibling tracker; the actual byte-parity reconciliation + any rs code
is rs-session work.

## Disclosure note (upstream-issue-hygiene MUST-2)

Any drafted issue body references SDK/standards surfaces only (EATP-12 spec,
foundation §, the N12-\* IDs, public API). No consumer/operator identifiers, no
workspace paths, no finding tags.
