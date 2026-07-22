# rs#2063 cross-SDK handoff — DRAFT issue body (NOT yet filed)

Status: DRAFT. Filing is a cross-repo write requiring (a) `/cross-repo-authorize <rust-sdk-repo> "file the #1912-equivalent subject-binding + chain-state issue"` receipt AND (b) user yes/no per repo-scope-discipline User-Authorized-Exception + upstream-issue-hygiene MUST-1. Do NOT imply-done (handoff-completion).

Scrubbed per upstream-issue-hygiene MUST-2 (SDK-API-surface only; no workspace paths, finding tags, session context, or consumer identifiers). Five-section minimal-repro shape.

---

**Title:** security(trust): bind holder subject into capability signing pre-image + sign the capability-set / chain-state envelope (store-tamper hardening)

**Labels:** `cross-sdk`, `security`

## Affected API

The trust-plane capability-signing + chain-verification path — the equivalent of the Python SDK's `verify()` / capability-signing pre-image + chain-state envelope signature.

## Summary

The trust plane's persisted capability signatures do not bind the holder's `agent_id` into the signed pre-image, and the capability-set / chain-state envelope is unsigned. Under the bounded-trust store-writer threat model (a party with write access to the persisted trust store), this permits:

1. **Cross-chain capability transplant** — a capability signed by authority A for holder/chain X verifies identically for a different holder/chain Y, because the subject is not in the signed bytes.
2. **Silent constraint / envelope tamper** — the capability set and its constraint envelope carry no signature, so a store-writer can strip a constraint (or an entire capability's constraints) and verification still accepts the weakened set.

## Expected vs actual

- **Expected:** the signed capability pre-image binds the holder subject (so a capability cannot be transplanted to a different holder/chain), and the capability-set / chain-state envelope carries a signature that fails closed when absent, stripped, or invalid.
- **Actual:** subject is not bound in the pre-image; the envelope is unsigned; a store-writer can transplant capabilities across chains and strip constraints undetected.

## Severity

HIGH (store-tamper) + two MEDIUM (constraint-strip variants) — affects every trust-plane deployment that persists chains a store-writer can reach.

## Acceptance criteria

- [ ] Capability signing pre-image binds the holder subject id; a capability signed for one holder/chain fails verification for a different holder/chain.
- [ ] Capability-set / chain-state envelope is signed; an absent / stripped / invalid signature fails closed (denies) by default.
- [ ] A migration path re-signs the installed base (subject-bind existing capabilities + add the envelope signature), verifying each existing signature against the genesis authority BEFORE re-signing (no laundering of a forged/transplanted capability), gated on an explicit trust-the-store-snapshot acknowledgment for every write surface.
- [ ] Fail-closed enforcement of the new posture by default, with a loud, documented, migration-window opt-out.
- [ ] Cross-SDK: the capability pre-image byte layout (including the bound subject) matches the Python SDK's, verified by a shared byte-pin vector.

## Cross-SDK alignment

This is the Rust-SDK equivalent of the Python SDK's subject-binding + chain-state-signing hardening (originating issue: kailash-py #1912). The capability pre-image + envelope byte layout is a cross-SDK signed contract, so the subject-binding + envelope-signature shapes MUST match for cross-SDK trust-plane interop on these artifacts (per cross-sdk-inspection Rule 4 — pin shared byte vectors).
