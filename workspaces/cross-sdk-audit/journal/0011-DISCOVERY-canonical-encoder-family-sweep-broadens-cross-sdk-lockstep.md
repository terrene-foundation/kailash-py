---
type: DISCOVERY
date: 2026-06-20
author: agent
project: cross-sdk-audit
topic: Canonical-encoder family sweep broadens the cross-SDK lockstep beyond the audit chain
phase: redteam
tags:
  [
    cross-sdk,
    canonical-encoder,
    selective-disclosure,
    envelope,
    kailash-rs-1448,
    byte-parity,
  ]
relates_to: 0009-DECISION-cross-repo-authorized-kailash-rs-audit-chain-canonical-read
---

# DISCOVERY — The canonical-encoder cross-SDK lockstep is broader than the audit chain

## What was found

After the audit-chain canonical-hash fix (PR #1411, blocked on `kailash-rs#1448`),
an empirical byte-diff sweep classified **every** `json.dumps(..., default=str)`
site in the trust plane against the conformant `canonical_scalars` whitelist —
97 occurrences across 54 files; 8 candidate signing/hash sites, 89 local
persistence/display/dedup sites (where `default=str` is correct). Each candidate
was byte-diffed by running production code with fixed inputs (not reasoned about).

The decisive result: **the cross-SDK canonical migration is broader than the
audit chain.** Two additional signing/hash surfaces are byte-CHANGING under
`canonical_scalars` and carry the SAME `kailash-rs#449` byte-for-byte contract as
the audit chain, so they cannot be switched py-only:

| Surface                                                                                                                        | Why byte-changing                                                                                                                                                                                                                                                        | Disposition       |
| ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------- |
| selective-disclosure witness family — `_hash_value` (47) / `_compute_chain_hash` (274) / export+verify sign-payloads (332/376) | `AuditRecord.anchor` is a nested `chain.AuditAnchor` dataclass that `_audit_record_to_dict` does NOT pre-normalize; it reaches the witness encoders by default. `default=str` stringifies the dataclass repr; `canonical_scalars` asdict-expands it → different SHA-256. | CROSS_SDK_BLOCKED |
| `ConstraintEnvelope.to_canonical_json` (1039) — the HMAC sign/verify pre-image                                                 | includes the free-form unvalidated `metadata: dict[str, Any]`; a `datetime`/`set`/`bytes` there renders differently under `canonical_scalars` AND a switch invalidates every on-disk HMAC-signed envelope.                                                               | CROSS_SDK_BLOCKED |

By analogy to the audit chain (journal/0009: kailash-rs mirrors py's CURRENT
`default=str` bytes), switching either py-only would diverge the two SDKs — the
same class as the `#1400` timestamp change. They were therefore NOT switched.

Two surfaces were resolved py-side:

- **`ConstraintEnvelope.envelope_hash` (817) → `canonical_scalars` (SHIPPED).**
  Byte-NEUTRAL: the constraint `to_dict()` layer pre-normalizes every divergent
  type and `_hashable_dict` excludes `metadata`, so the swap changes zero
  currently-emitted bytes (the #1403/#1405 latent-divergence-closure pattern).
  Empirically confirmed identical (`698342bb…`).
- **`decorators._hash_result` (305) + `dataflow/trust/audit.py::compute_query_hash`
  (680): NO_CHANGE.** Local fingerprints with no cross-SDK byte contract
  (`_hash_result`'s contract is downstream at the conformant `serialize_for_signing`;
  `compute_query_hash` is a DataFlow-local privacy-truncated dedup hash).

## What landed this session (py-side, unblocked)

- `envelope.py:817` byte-neutral switch to `canonical_scalars`.
- `tests/regression/test_canonical_encoder_family_conformance.py` — pins the
  envelope_hash byte-neutrality AND the CURRENT (`default=str`) bytes of every
  cross-SDK-blocked site, so a silent py-only canonical switch fails loudly
  (`cross-sdk-inspection.md` Rule 4). These are `selective_disclosure.py`'s
  first-ever tests, including an intra-SDK lockstep round-trip (export↔verify
  sign-payloads must use the same encoder as each other regardless of the
  cross-SDK decision).
- `specs/trust-canonical-encoders.md` — the full encoder-family map + dispositions.
- Audit-chain convergence (PR #1411) independently re-verified from scratch:
  1503 tests pass (1244+35+32+192), canonical vectors reproduce byte-for-byte.

## Recommended cross-SDK action (human-gated — user manages both teams)

`kailash-rs#1448` is currently scoped to the audit-chain timestamp lockstep. The
canonical-conformance lockstep should be **expanded** to cover the two additional
surfaces above (the selective-disclosure witness family + the envelope HMAC
pre-image), OR two sibling `cross-sdk` issues filed against `kailash-rs`. Filing
against `kailash-rs` is a cross-repo write requiring explicit user authorization

- a receipt-before-acting entry per `repo-scope-discipline.md` — NOT taken in
  this session. The py-side byte pins are the loud tripwire until that lockstep.

## For Discussion

1. Should the broadened conformance ride a SINGLE expanded `kailash-rs#1448`
   lockstep wave (one coordinated migration for audit-chain + witness-family +
   envelope HMAC pre-image), or be split into separate issues so the audit chain
   can land independently if the witness-family migration takes longer? The
   single-wave option minimizes the number of "re-pin both SDKs" events; the
   split option de-risks the audit chain's timeline.
2. `compute_query_hash` (DataFlow-local) is byte-changing on `datetime` query
   params but has no cross-SDK contract today — counterfactually, if a future
   requirement adds cross-SDK audit-correlation for DataFlow, would the local
   dedup hash need to become canonical, and is pinning its current bytes now
   (vs. leaving it unpinned) worth the maintenance?
3. The envelope HMAC pre-image switch would invalidate every on-disk
   HMAC-signed envelope (a data-migration concern beyond byte parity). Does that
   raise the bar for ever migrating it — i.e., is `to_canonical_json` effectively
   frozen on `default=str` unless a versioned envelope format is introduced?
