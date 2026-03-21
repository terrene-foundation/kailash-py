# Reasoning Traces (EATP Extension)

This guide explains how to use reasoning traces in the EATP SDK to capture WHY decisions are made during trust delegation and audit operations.

## What Are Reasoning Traces?

Reasoning traces are structured records that document the rationale behind agent decisions. They complement the existing EATP trust chain (which tracks WHAT happened and WHO authorized it) by adding the WHY dimension.

Every delegation and audit record can optionally carry a `ReasoningTrace` that includes:

- **Decision**: What was decided (human-readable summary)
- **Rationale**: Why the decision was made
- **Confidentiality**: Enterprise classification level controlling disclosure
- **Evidence**: Supporting data that informed the decision
- **Alternatives**: Other options that were evaluated and rejected

Reasoning traces are cryptographically signed independently from the parent record, preserving backward compatibility with existing trust chains.

## Quick Start

```python
from kailash.trust import TrustOperations, ReasoningTrace, ConfidentialityLevel
from datetime import datetime, timezone

# Create a reasoning trace
trace = ReasoningTrace(
    decision="Delegate data analysis to agent-junior",
    rationale="Junior agent completed 15 similar tasks with 98% accuracy",
    confidentiality=ConfidentialityLevel.RESTRICTED,
    timestamp=datetime.now(timezone.utc),
    alternatives_considered=[
        "Agent-senior (unavailable until next week)",
        "Manual processing (too slow for deadline)",
    ],
    evidence=[
        {"type": "performance_history", "tasks_completed": 15, "accuracy": 0.98},
        {"type": "availability_check", "agent": "agent-junior", "status": "idle"},
    ],
    methodology="capability_matching",
    confidence=0.92,
)

# Attach to delegation
delegation = await ops.delegate(
    delegator_id="agent-senior",
    delegatee_id="agent-junior",
    task_id="task-q4-analysis",
    capabilities=["analyze_data"],
    reasoning_trace=trace,
)

# The SDK automatically computes:
# - delegation.reasoning_trace_hash (SHA-256)
# - delegation.reasoning_signature (Ed25519, separate from record signature)
```

Reasoning traces work the same way on audit operations:

```python
audit_trace = ReasoningTrace(
    decision="Approve quarterly report",
    rationale="All data validated, within tolerance thresholds",
    confidentiality=ConfidentialityLevel.PUBLIC,
    timestamp=datetime.now(timezone.utc),
)

anchor = await ops.audit(
    agent_id="agent-analyst",
    action="approve_report",
    resource="finance_db.q4_revenue",
    reasoning_trace=audit_trace,
)
```

## Confidentiality Classification

Every reasoning trace carries a `ConfidentialityLevel` that controls how the trace is disclosed across interop formats and selective disclosure mechanisms.

| Level          | Ordering | Behavior                                                              |
| -------------- | -------- | --------------------------------------------------------------------- |
| `PUBLIC`       | 0        | Always visible in all formats                                         |
| `RESTRICTED`   | 1        | Visible by default; hidden in SD-JWT unless `disclose_reasoning=True` |
| `CONFIDENTIAL` | 2        | Hidden by default; when disclosed, `alternatives_considered` stripped |
| `SECRET`       | 3        | Never disclosed; only `reasoning_trace_hash` survives                 |
| `TOP_SECRET`   | 4        | Never disclosed; only `reasoning_trace_hash` survives                 |

Levels support ordering comparisons:

```python
from kailash.trust.reasoning.traces import ConfidentialityLevel

assert ConfidentialityLevel.PUBLIC < ConfidentialityLevel.SECRET
assert ConfidentialityLevel.RESTRICTED <= ConfidentialityLevel.RESTRICTED

# Use in access control logic
agent_clearance = ConfidentialityLevel.CONFIDENTIAL
trace_level = ConfidentialityLevel.SECRET
if agent_clearance < trace_level:
    print("Agent lacks clearance to view this reasoning")
```

## Requiring Reasoning Traces

Add the `REASONING_REQUIRED` constraint to a chain's constraint envelope to enforce that all delegations and audit anchors must include reasoning traces:

```python
from kailash.trust.chain import ConstraintType, Constraint

# When establishing trust, include REASONING_REQUIRED
chain = await ops.establish(
    agent_id="agent-auditor",
    authority_id="org-acme",
    capabilities=[...],
    constraints=["reasoning_required"],
)
```

When `REASONING_REQUIRED` is active:

- **STANDARD verification** checks that reasoning traces are present on all delegation and audit records. Missing traces produce a non-blocking violation (severity: `"warning"`).
- **FULL verification** additionally verifies `reasoning_trace_hash` (SHA-256 integrity) and `reasoning_signature` (Ed25519 cryptographic verification) for every record.
- **QUICK verification** does not check reasoning (expiration only).

```python
from kailash.trust.chain import VerificationLevel

# STANDARD: checks presence
result = await ops.verify(
    agent_id="agent-auditor",
    action="analyze_data",
    level=VerificationLevel.STANDARD,
)
# result.reasoning_present: True/False/None
# result.violations: [{constraint_type: "reasoning_required", severity: "warning", ...}]

# FULL: checks presence + hash + signature
result = await ops.verify(
    agent_id="agent-auditor",
    action="analyze_data",
    level=VerificationLevel.FULL,
)
# result.reasoning_present: True/False/None
# result.reasoning_verified: True/False/None
```

## Crypto Operations

Three dedicated functions handle reasoning trace cryptography:

```python
from kailash.trust.signing.crypto import (
    hash_reasoning_trace,
    sign_reasoning_trace,
    verify_reasoning_signature,
)

# Hash: SHA-256 of deterministic signing payload
trace_hash = hash_reasoning_trace(trace)  # 64-char hex string

# Sign: Ed25519 signature (separate from record signature)
signature = sign_reasoning_trace(trace, private_key)  # base64 string

# Verify: check signature against public key
is_valid = verify_reasoning_signature(trace, signature, public_key)  # bool
```

These functions use `ReasoningTrace.to_signing_payload()` internally, which produces a deterministic dict with sorted keys for canonical serialization.

## Enforcement

### StrictEnforcer

Propagates reasoning metadata into enforcement records:

```python
from kailash.trust.enforce.strict import StrictEnforcer

enforcer = StrictEnforcer()
result = await ops.verify(agent_id="agent-001", action="do_thing")
verdict = enforcer.enforce(agent_id="agent-001", action="do_thing", result=result)

# Enforcement record metadata includes:
# - reasoning_present: True/False (when set)
# - reasoning_verified: True/False (when set)
```

Reasoning-specific violations are logged at WARNING level with details.

### ShadowEnforcer

Tracks reasoning metrics without blocking:

```python
from kailash.trust.enforce.shadow import ShadowEnforcer

shadow = ShadowEnforcer()
# ... process verifications ...

metrics = shadow.metrics
print(f"Reasoning present: {metrics.reasoning_present_count}")
print(f"Reasoning absent: {metrics.reasoning_absent_count}")
print(f"Verification failures: {metrics.reasoning_verification_failed_count}")
```

### Selective Disclosure

Redacts reasoning traces based on confidentiality:

- PUBLIC/RESTRICTED traces are kept visible
- CONFIDENTIAL and above are redacted to SHA-256 hash

## Trust Scoring

When `REASONING_REQUIRED` is active, a `reasoning_coverage` factor is added to the trust score at approximately 5% weight. This factor measures the percentage of delegations and audit anchors that have reasoning traces attached.

The base 5 scoring factors are scaled down proportionally so the total remains 100. An empty chain (no delegations or anchors) scores full coverage (vacuous truth).

Risk analysis flags incomplete reasoning coverage with actionable recommendations.

## Interop Formats

### W3C Verifiable Credentials

```python
from kailash.trust.interop.w3c_vc import chain_to_w3c_vc

vc = chain_to_w3c_vc(chain, signing_key=priv_key)
# PUBLIC/RESTRICTED: full reasoning in "reasoning" key
# CONFIDENTIAL+: reasoning withheld, only hash included
# reasoningTraceHash and reasoningSignature always present (integrity proofs)
```

### SD-JWT

```python
from kailash.trust.interop.sd_jwt import create_reasoning_sd_jwt

# Without disclosure (default): RESTRICTED+ traces hidden
token = create_reasoning_sd_jwt(
    chain, signing_key=priv_key,
    disclosed_claims=["genesis", "delegations"],
)

# With disclosure: RESTRICTED/CONFIDENTIAL traces included
token = create_reasoning_sd_jwt(
    chain, signing_key=priv_key,
    disclosed_claims=["genesis", "delegations"],
    disclose_reasoning=True,
)
# SECRET/TOP_SECRET traces are never included regardless of this flag
```

### JWT and UCAN

Reasoning traces are serialized as `eatp_reasoning_trace`, `eatp_reasoning_trace_hash`, and `eatp_reasoning_signature` within the token claims/facts.

## Knowledge Bridge

Convert reasoning traces into searchable knowledge entries:

```python
from kailash.trust.knowledge.bridge import KnowledgeBridge

bridge = KnowledgeBridge(
    knowledge_store=store,
    trust_operations=ops,
)

entry = await bridge.reasoning_trace_to_knowledge(
    trace=trace,
    agent_id="agent-senior",
    derived_from=["entry-123"],  # Optional provenance chain
)
# entry.content_type == KnowledgeType.DECISION_RATIONALE
# entry.metadata includes: confidentiality, methodology, evidence, alternatives
```

## Backward Compatibility

Reasoning traces are fully backward compatible:

- `reasoning_trace`, `reasoning_trace_hash`, and `reasoning_signature` fields default to `None` on `DelegationRecord` and `AuditAnchor`
- Reasoning fields are **excluded** from the record's `to_signing_payload()` — existing signatures remain valid when reasoning traces are added later
- `VerificationResult.reasoning_present` and `reasoning_verified` default to `None` — existing verification consumers see no change
- All `from_dict()` deserialization methods handle missing reasoning fields gracefully
- The `REASONING_REQUIRED` constraint is opt-in — reasoning checks only activate when the constraint is present in the chain's constraint envelope
