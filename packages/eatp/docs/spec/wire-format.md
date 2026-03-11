# Wire Format

EATP defines a JSON wire format for cross-language compatibility. All records are serialized as JSON objects conforming to JSON Schema definitions.

## Namespace

All schemas use the namespace `https://eatp.terrene.dev/schemas/`.

## Record Types

| Record | Schema ID | Required Fields |
|--------|-----------|-----------------|
| Genesis Record | `genesis-record.schema.json` | id, agent_id, authority_id, authority_type, created_at, signature, signature_algorithm |
| Capability Attestation | `capability-attestation.schema.json` | id, agent_id, capability, capability_type, granted_at, signature |
| Delegation Record | `delegation-record.schema.json` | id, delegator_id, delegatee_id, task_id, capabilities, created_at, signature |
| Audit Anchor | `audit-anchor.schema.json` | id, agent_id, action, timestamp, trust_chain_hash, result, signature |
| Constraint Envelope | `constraint-envelope.schema.json` | id, agent_id, constraints, constraint_type, effective_from, signature |
| Verification Verdict | `verification-verdict.schema.json` | valid, level |
| Signed Envelope | `signed-envelope.schema.json` | id, sender_id, recipient_id, payload, timestamp, signature, nonce |

## Signatures

All signatures are Ed25519, base64-encoded. The signing payload is computed using deterministic JSON serialization (sorted keys, no whitespace).

## Timestamps

All timestamps use ISO 8601 format with timezone: `2025-01-15T10:30:00+00:00`.

## Cross-Language Compatibility

The wire format ensures Python and Rust SDKs produce interoperable records. Test fixtures in `tests/fixtures/wire_format/` verify this.
