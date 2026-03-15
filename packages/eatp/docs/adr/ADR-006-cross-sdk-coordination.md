# ADR-006: Cross-SDK Coordination Model

**Status**: Accepted
**Date**: 2026-03-15

## Context

The EATP protocol has two independent SDK implementations: Python (`eatp` package) and Rust (`eatp-rs` crate). The spec (D6 decision) states that both SDKs implement the protocol independently with convention-level alignment. This ADR documents the coordination model.

## Decision

Python and Rust SDKs implement the EATP spec independently. Coordination happens at the **convention level**, not the code level:

1. **Wire format compatibility**: Both SDKs produce and consume the same JSON wire format for trust chains, verification verdicts, audit anchors, and constraint envelopes. Wire format fixtures in `tests/fixtures/wire_format/` are the source of truth.

2. **Convention alignment**: Both SDKs follow the same conventions (e.g., `maxlen=10000` for bounded collections, Ed25519 as mandatory signing algorithm, fail-closed error handling), but naming follows each language's idiom (Python `snake_case` vs Rust `snake_case` with different module structure).

3. **Semantic equivalence**: The same input must produce the same output in both SDKs. New spec-level concepts require Rust team coordination before implementation.

4. **Independent release cycles**: Each SDK has its own version, changelog, and release process. Breaking changes to the wire format require coordinated releases.

## Rationale

- **Language-idiomatic code**: Forcing identical structure across Python and Rust would produce unidiomatic code in both. Convention alignment preserves quality.
- **Independent velocity**: Teams can ship fixes and improvements without blocking on the other SDK, as long as wire format compatibility is maintained.
- **Wire format as contract**: The JSON wire format is the interop boundary. As long as both SDKs produce and consume it correctly, internal implementation details can diverge.
- **Spec gating for new concepts**: New protocol concepts (e.g., new posture levels, new constraint types) must be coordinated to prevent divergence in the wire format.

## Consequences

- Wire format fixture tests must pass in both SDKs before a release that touches the wire format.
- Convention names may differ (Python `TrustPosture` vs potential Rust `TrustPosture`) but enum values and semantics must match exactly.
- New EATP spec features require a coordination ticket with the Rust team before implementation begins.
- The `tests/fixtures/wire_format/manifest.json` lists all canonical fixture files that both SDKs must validate against.
