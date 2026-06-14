---
type: DECISION
slug: cross-repo-authorized-read-eatp12-spec
created: 2026-06-14T02:49:16Z
---

# Cross-Repo Authorization — READ EATP-12 v1.0 spec from foundation

cross-repo-authorized: terrene-foundation/foundation

## Grant (repo-scope-discipline § User-Authorized Exception — all 5 conditions)

1. **User-initiated:** genuine user turn (2026-06-14) — verbatim: "approved read
   cross-repo", in direct response to the agent's proposal to read the EATP-12
   v1.0 spec from `terrene-foundation/foundation` to enable #1312 implementation.
2. **Explicit + specific:** target `terrene-foundation/foundation`; bounded
   action = READ-ONLY ingest of the EATP-12 v1.0 Trust Vault Key-Binding spec
   (`docs/02-standards/eatp/12-trust-vault-key-binding.md`) plus the normative
   material it references (Appendix B golden fixture, §7 conformance vectors
   V1–V8, per-subtype canonical payload schemas, the N12-\* normative-ID
   checklist). Purpose: bring the spec into kailash-py as a versioned brief so
   #1312 (EATP-12 conformance) can be implemented byte-identically.
3. **Confirmed:** restated here + in the session report before any cross-repo
   command runs. Matches the established eatp-gaps cross-repo pattern
   (workspaces/eatp-gaps/journal/0001-0004, all executed).
4. **Journaled before acting:** this entry lands BEFORE the first read of any
   foundation path.
5. **Scoped exactly:** ONLY read access to the EATP-12 spec + its appendix
   fixtures/vectors in `terrene-foundation/foundation`. NO write to foundation.
   NO incidental reads beyond the EATP-12 conformance surface. The implementation
   work itself happens entirely in the CWD repo (kailash-py). Foundation repo
   exists: local clone at /Users/esperie/repos/terrene/foundation (default
   branch `main`); confirmed via `gh repo view terrene-foundation/foundation`.

## Why this read is necessary

#1312 is a byte-identical conformance task. The authoritative spec — Appendix B
golden fixture, V1–V8 conformance vectors, per-subtype canonical payload
schemas — exists ONLY in foundation. The GitHub issue body summarizes the
requirements but does not carry the byte-level surface. Implementing the vault
KEK binding (the deployment's highest-value secret) against a summary rather
than the normative pre-images would be unsafe.

## Scope boundary going forward

The grant covers READING foundation's EATP-12 spec. It does NOT authorize:

- any write to foundation, mint, or kailash-rs;
- the cross-SDK byte-parity coordination with kailash-rs (separate, release-gated;
  needs its own grant when that step is reached);
- releasing the vault binding (release MUST coordinate cross-SDK per #1312).
