# DECISION — Codify: cross-SDK signed-model field additions prune-when-unset

**Date:** 2026-07-10
**Phase:** 05-codify
**Type:** DECISION

## What was codified

One new MUST clause on branch `codify/signed-model-field-prune-2026-07-11`, distilled
from this session's BH5 redteam:

- **`rules/cross-sdk-inspection.md` Rule 4d — New Fields On A Cross-SDK Signed Model
  MUST Prune-When-Unset From The Signing Pre-Image.** A sibling of Rule 4b (byte-CHANGING
  encoder switches). When a commit ADDS a new optional field to a data model whose
  serialization feeds a cross-SDK signing/hash pre-image, `model_dump()` emits the
  `None`-default field as a `null` key — changing the signed bytes of EVERY existing
  instance, so a pre-existing or sibling-SDK-signed artifact fails verification even
  though nothing about it changed. The fix: prune the UNSET field from the signing
  pre-image so a not-configured instance signs byte-identically to the pre-addition
  form (backward-compatible); a configured value stays bound. Classify empirically
  (byte-diff, not reason); pin a byte-identity regression test. Only the configured
  case is a cross-SDK lockstep; the not-configured case is byte-neutral.

Path-scoped (`priority: 10`), so the rule-authoring Rule-10 proximity-band gate does
not fire; cross-sdk-inspection.md is not on the self-referential-codify allowlist, so
no mandatory multi-agent redteam. Canonical 8-field Trust Posture Wiring attached
(trigger key `cross_sdk_signed_field_addition`).

## Why (provenance)

BH5 (#1510) added `circuit_*` fields to `OperationalConstraintConfig`, nested in the
Ed25519-signed `ConstraintEnvelopeConfig`. A two-round `/redteam` (security-reviewer +
parity verifier) caught the HIGH: the addition changed the signed pre-image for every
envelope (breaker-less included), breaking backward-compat + cross-SDK verification.
Fixed via `_envelope_signing_dict` prune-when-unset — the BH3 unbound-form pattern
applied to field additions. The reusable generalization (any signed model gaining a
field) is what Rule 4d codifies so the next signed-model field addition, in either
SDK, is caught at `/implement` review rather than at a cross-version verify failure.

## Distribution

Appended to the BUILD→loom proposal (`.claude/.proposals/latest.yaml`, `pending_review`,
change 24) with `classification_suggestion: global` — the pattern is language-agnostic
(the Rust SDK mirror needs the same discipline). Anchor advanced
(`learning-codified.json::last_codified`).
