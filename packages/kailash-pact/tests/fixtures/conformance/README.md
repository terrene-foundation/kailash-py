# PACT N4/N5 Conformance Vectors (Vendored from kailash-rs)

This directory holds the vendored copy of the PACT N4/N5 cross-SDK
conformance vectors. The Python conformance runner
(`pact.conformance.ConformanceRunner`) drives every JSON file here
through its canonical-JSON path and asserts byte-for-byte equality
against `expected.canonical_json`.

## Source of truth

The cross-SDK contract source of truth lives in the Rust SDK:

- Vectors: `~/repos/loom/kailash-rs/crates/kailash-pact/tests/conformance/vectors/*.json`
- Runner: `~/repos/loom/kailash-rs/crates/kailash-pact/tests/conformance_vectors.rs`

These vectors are vendored (byte-identical copies) into this Python
repository so:

1. Tier 2 integration tests run without a sibling `kailash-rs`
   checkout (CI matrix jobs, downstream consumers, fresh clones).
2. The cross-SDK byte-equality contract is exercised against a
   pinned snapshot — drift between the Rust source and the Python
   vendored copy surfaces as a vector mismatch in CI rather than
   silently passing because the local tree happens to be in sync.

**Vendored from kailash-rs commit:** `95916caa66d698d2d7c2755a4b5f3e61019af74e`
(snapshot taken 2026-04-25).

## Refresh procedure

When kailash-rs lands new vectors or modifies existing ones, refresh
this directory by re-copying byte-for-byte:

```bash
cp ~/repos/loom/kailash-rs/crates/kailash-pact/tests/conformance/vectors/n4_*.json \
   packages/kailash-pact/tests/fixtures/conformance/n4/
cp ~/repos/loom/kailash-rs/crates/kailash-pact/tests/conformance/vectors/n5_*.json \
   packages/kailash-pact/tests/fixtures/conformance/n5/
```

Then update the "Vendored from kailash-rs commit" SHA above so the
audit trail tracks which Rust SHA the Python tests are pinned to.

**Do NOT modify the JSON files directly.** Vectors are the canonical
source of truth — modifying them in this repo means the Python SDK
asserts a contract that diverges from the Rust SDK. If a vector needs
fixing, fix it in kailash-rs first and re-vendor.

## Cross-SDK contract

Each vector defines:

- `id`: stable identifier (used for grep / forensic correlation across
  Python + Rust runner output).
- `contract`: `"N4"` (TieredAuditEvent canonicalisation) or `"N5"`
  (Evidence canonicalisation).
- `input`: the runtime inputs (`verdict`, `posture`, `fixed_event_id`,
  `fixed_timestamp`, etc.) that the SDK's domain types are constructed
  from.
- `expected.canonical_json`: the byte string both SDKs MUST emit when
  the domain type is serialised through `canonical_json()`.
- `expected.tier` / `durable` / `requires_signature` /
  `requires_replication` (N4 only): optional invariants the runner
  asserts before the canonical-JSON diff.

The byte-equality contract pins serde struct-field declaration order,
snake_case enum variant names, and absence of whitespace between
tokens. See `pact.conformance.vectors.canonical_json_dumps` for the
encoder contract.

## Inventory

- `n4/n4_audit_zone1_pseudo.json` — PseudoAgent posture maps to Zone 1
  (ephemeral, in-memory durability tier).
- `n4/n4_audit_zone2_guardian.json` — Guardian posture maps to Zone 2
  (durable single-region).
- `n4/n4_audit_zone3_cognate.json` — Cognate posture maps to Zone 3.
- `n4/n4_audit_zone3_continuous_insight.json` — ContinuousInsight
  posture maps to Zone 3.
- `n4/n4_audit_zone4_delegated.json` — Delegated posture maps to
  Zone 4 (durable + signed + replicated).
- `n5/n5_evidence_blocked.json` — Evidence record from a Blocked
  verdict (custom `evidence_source` override).
- `n5/n5_evidence_verdict_v1.json` — Evidence record from a verdict
  with `evidence_source = role_address` fallback.
