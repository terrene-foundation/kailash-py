# Brief — kailash.trust.chain crypto-expansion for Delegate substrate parity

**Date:** 2026-05-21
**Authorized by:** user — yes-gate via AskUserQuestion 2026-05-21 in `workspaces/issue-1035-delegate-py/` redteam Round 2 disposition.
**Originating evidence:** `workspaces/issue-1035-delegate-py/01-analysis/02-kailash-rs-reference-extraction.md` (kailash-rs `GenesisBlock` field set) + Round 2 analyst HIGH-1 finding.

## Why this workspace exists

The kailash-py Delegate composition primitive (#1035, shipping via Wave 1 PRs #1132 + #1133) composes the existing canonical `kailash.trust.chain.GenesisRecord` (`src/kailash/trust/chain.py:121`) as its substrate per `composition.rs:1-19` "compose, don't re-derive" discipline. The composition works for Wave 1 substrate semantics — `chain.hash()` round-trips, `Ed25519` sign/verify is in place, Tier 1 wiring proven.

**The structural gap:** the kailash-rs sibling `kailash-delegate-types::GenesisBlock` (in `kailash-rs/crates/kailash-delegate-types/src/composition.rs:36-37`) carries cryptographic-linkage fields that kailash-py's `chain.GenesisRecord` does not yet expose:

- `principal_directory_anchor` — SHA-256 hex of the principal directory at genesis time. Required for the cryptographic anchor that ties a Delegate to the principal set in effect when it was instantiated.
- `initial_envelope_hash` — SHA-256 hex of the genesis-seeded `ConstraintEnvelope`. Required for the load-bearing F5 anchor (envelope monotonic-tightening proof per Wave 1 PR #1133 S2.5).
- `delegation_proof` — opaque proof bytes (hex). Required for the substrate's signed-delegation contract.

Wave 1 works around the absence by carrying these fields on the `DelegateGenesisRecord` wrapper layer (`src/kailash/delegate/types.py::DelegateGenesisRecord`), but cross-SDK byte-canonical conformance at Delegate S7 (`receipts_agree(rs, py)` against vendored `delegate_spec_vectors()`) will fail the first Genesis-exercising vector because the rs side emits these fields nested inside `block: GenesisBlock` while py emits them at the Delegate-wrapper level.

## Scope

Extend `kailash.trust.chain.GenesisRecord` with the three crypto-linkage fields **per a deprecation cycle** (the type is exported public API; per `zero-tolerance.md` Rule 6a, public-API extension that breaks downstream call shapes MUST land with a `DeprecationWarning` shim covering ≥1 minor release + CHANGELOG migration).

Phased plan (proposed; subject to /analyze):

1. Add the three fields as `Optional[str] = None` with hex-format + length validation (matching the `_validate_hex` pattern S2.5b landed at `src/kailash/delegate/types.py`).
2. `to_signing_payload()` / `to_dict()` MUST handle backward-compat (Wave 1 callers passing the old shape continue to work; serialized payloads MUST include the new fields when set).
3. Cross-SDK fixture parity: emit byte-canonical JSON matching `kailash-rs/crates/kailash-delegate-types/src/composition.rs::GenesisBlock` serialization shape.
4. Migrate `DelegateGenesisRecord` (in `src/kailash/delegate/types.py`) to delegate these fields to `chain.GenesisRecord` rather than carrying them at the wrapper layer.
5. Update `tools/lint-delegate-fences.py` to enforce the contract on cross-SDK fixtures.

## Related issues / known constraints

- **`kailash.trust._locking.validate_id` regex `^[a-zA-Z0-9_-]+$`** is too strict for PACT D/T/R `org:foo:bar`-style identifiers. Already flagged in S2.5b PR #1133 comment (Wave 1) as a S3 known limitation; revisit here if the substrate-expansion work needs to validate `sovereign_ref`/`role_binding_ref`/`genesis_ref` against the PACT identifier grammar.
- **Coordination with #1035 (Delegate Wave 2+):** Delegate S6 runtime spine + S7 conformance vectors depend on this workspace. Surface dependency at S6 launch gate.

## Authorization receipt

cross-repo-authorized: terrene-foundation/kailash-rs (READ-ONLY, journaled at `workspaces/issue-1035-delegate-py/journal/0001-cross-repo-authorization-kailash-rs-check.md`; extends to this workspace's reference reads of `composition.rs::GenesisBlock`).
