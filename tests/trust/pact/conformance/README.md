# PACT N6 Cross-Implementation Conformance Suite

Validates that PACT governance types produce **deterministic, byte-identical
serialization** across SDK implementations (Python and Rust). Both SDKs
validate against the same committed JSON vector files.

## Conformance Requirements Coverage

| Requirement | Description | Status |
|------------|-------------|--------|
| **N1** | Pre-retrieval filtering (FilterDecision, KnowledgeQuery) | Platform-contract: vector + roundtrip tests |
| **N2** | Verification gradient (VerificationLevel enum) | Platform-contract: wire format test |
| **N3** | Plan re-entry guarantee (PlanSuspension, ResumeCondition) | Platform-contract: vector + roundtrip tests |
| **N4** | Tamper-evident audit (AuditAnchor, hash determinism) | Platform-contract: vector + hash + roundtrip tests |
| **N5** | Structured observation (Observation) | Platform-contract: vector + roundtrip tests |
| **N6** | Cross-implementation conformance | **This suite**: all vector + wire format tests |

## Serialization Convention

All PACT types follow the same canonical serialization path:

```python
canonical_json = json.dumps(obj.to_dict(), sort_keys=True)
```

- `to_dict()` serializes enums as `.value`, datetimes as `.isoformat()`,
  frozensets as `sorted(list)`.
- `json.dumps(sort_keys=True)` produces deterministic key ordering.
- The result is a UTF-8 string that can be compared byte-for-byte across
  implementations.

## Test Vectors

Each vector file in `vectors/` contains:

| File | PACT Type | What it verifies |
|------|-----------|-----------------|
| `constraint_envelope.json` | ConstraintEnvelopeConfig | Five CARE dimensions + clearance + delegation depth |
| `governance_verdict.json` | GovernanceVerdict | Decision output with timestamp, envelope snapshot |
| `role_clearance.json` | RoleClearance | Clearance assignment with compartments, vetting status |
| `access_decision.json` | AccessDecision | Allow/deny with step_failed, audit_details (2 vectors) |
| `filter_decision.json` | FilterDecision (N1) | Pre-retrieval filter with narrowed KnowledgeQuery (2 vectors) |
| `plan_suspension.json` | PlanSuspension (N3) | Budget suspension with resume conditions, snapshot |
| `audit_anchor.json` | AuditAnchor (N4) | Tamper-evident record with deterministic SHA-256 hash |
| `observation.json` | Observation (N5) | Structured monitoring event with correlation ID |

## Wire Format Tests

In addition to vector tests, the suite validates enum wire formats:

- **TrustPosture**: pseudo, tool, supervised, delegating, autonomous (5 members)
- **VerificationLevel**: AUTO_APPROVED, FLAGGED, HELD, BLOCKED (4 members)
- **ConfidentialityLevel**: public, restricted, confidential, secret, top_secret (5 members)

Exhaustiveness checks ensure no enum member is added or removed without
updating the conformance suite.

## Adding New Vectors

1. Create the vector JSON file in `vectors/` with `input` and `expected_canonical_json`.
2. Add a test class in `test_n6_conformance.py` that constructs the type from `input`
   and asserts the canonical JSON matches `expected_canonical_json`.
3. Add a roundtrip test (`to_dict` -> `from_dict` -> assert fields equal).
4. Add the filename to `TestVectorIntegrity.EXPECTED_VECTORS`.
5. Copy the vector file to the Rust SDK's conformance test directory.
