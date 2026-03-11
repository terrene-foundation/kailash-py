---
name: eatp-reference
description: Load EATP Framework technical reference. Use when explaining EATP concepts, trust lineage, attestation, verification gradient, trust postures, comparing to other identity standards, or working with the standalone EATP SDK (`pip install eatp`).
allowed-tools:
  - Read
  - Glob
  - Grep
---

# EATP Framework Reference

This skill provides the technical reference for the Enterprise Agent Trust Protocol (EATP) - the trust verification protocol for enterprise AI agents.

## SDK Skill Files

For standalone EATP SDK implementation knowledge, see these companion files:

- **[eatp-sdk-quickstart.md](eatp-sdk-quickstart.md)** — Getting started with `pip install eatp`, 4-operation lifecycle, store selection
- **[eatp-sdk-api-reference.md](eatp-sdk-api-reference.md)** — Complete API surface: all exports, module reference, type signatures
- **[eatp-sdk-patterns.md](eatp-sdk-patterns.md)** — Implementation patterns, critical gotchas, security findings, architecture patterns
- **[eatp-sdk-reasoning-traces.md](eatp-sdk-reasoning-traces.md)** — Reasoning trace extension: lifecycle, confidentiality, knowledge bridge integration

## Authoritative Sources

### PRIMARY: Standalone SDK

- `packages/eatp/src/eatp/` - Standalone EATP SDK source (Apache 2.0, Terrene Foundation)
- `packages/eatp/examples/` - Working examples
- `packages/eatp/tests/` - 1557 tests

## What is EATP?

EATP is an open standard for establishing and verifying trust in enterprise AI agent systems. It separates trust establishment (human judgment, once) from trust verification (machine speed, continuously). Every action traces back to human decisions through verifiable cryptographic chains.

EATP operationalizes the CARE framework's governance philosophy as a concrete, implementable protocol.

## The Core Insight

The problem conflates two distinct moments:

- **Trust establishment**: Should this agent be permitted to act within these boundaries? (Human judgment)
- **Trust verification**: Does this action fall within those boundaries? (Machine verification, milliseconds)

Traditional governance performs both together. EATP separates them.

## The Five EATP Elements (Trust Lineage Chain)

### 1. Genesis Record

The organizational root of trust. A human executive cryptographically commits: "I accept accountability for this AI governance framework." No AI creates its own genesis record.

### 2. Delegation Record

Authority transfer with constraint tightening. **Delegations can only reduce authority, never expand it.** A manager with $50K authority can delegate $10K to an agent, not $75K. Mirrors how healthy organizations work.

### 3. Constraint Envelope

Multi-dimensional operating boundaries across five dimensions:

| Dimension         | Examples                                                  |
| ----------------- | --------------------------------------------------------- |
| **Financial**     | Transaction limits, spending caps, cumulative budgets     |
| **Operational**   | Permitted/blocked actions                                 |
| **Temporal**      | Operating hours, blackout periods, time-bounded auth      |
| **Data Access**   | Read/write permissions, PII handling, data classification |
| **Communication** | Permitted channels, approved recipients, tone guidelines  |

### 4. Capability Attestation

Signed declaration of authorized capabilities. Prevents capability drift (agents gradually performing unauthorized tasks). Makes authorized scope explicit and verifiable.

### 5. Audit Anchor

Tamper-evident execution record. Each anchor hashes the previous; modifying any record invalidates the chain forward. Production should use Merkle trees or external checkpointing.

## Verification Gradient

Verification is not binary:

| Result            | Meaning                  | Action                           |
| ----------------- | ------------------------ | -------------------------------- |
| **Auto-approved** | Within all constraints   | Execute and log                  |
| **Flagged**       | Near constraint boundary | Execute and highlight for review |
| **Held**          | Soft limit exceeded      | Queue for human approval         |
| **Blocked**       | Hard limit violated      | Reject with explanation          |

Focuses human attention where it matters: near boundaries and at limits.

## Five Trust Postures

Graduated autonomy:

| Posture                | Autonomy | Human Role                                        |
| ---------------------- | -------- | ------------------------------------------------- |
| **Pseudo-Agent**       | None     | Human in-the-loop; agent is interface only        |
| **Supervised**         | Low      | Human in-the-loop; agent proposes, human approves |
| **Shared Planning**    | Medium   | Human on-the-loop; co-planning                    |
| **Continuous Insight** | High     | Human on-the-loop; agent executes, human monitors |
| **Delegated**          | Full     | Human on-the-loop; remote monitoring              |

Postures upgrade through demonstrated performance. They downgrade instantly if conditions change.

## EATP Operations

- **ESTABLISH** - Create agent identity and initial trust
- **DELEGATE** - Transfer authority with constraints (accepts optional `reasoning_trace`)
- **VERIFY** - Validate trust chain and permissions (checks reasoning at STANDARD and FULL levels)
- **AUDIT** - Record and trace all trust operations (accepts optional `reasoning_trace`)

## Reasoning Trace Extension

Reasoning traces capture WHY a decision was made during delegation and audit operations. They are fully optional and backward compatible — existing trust chains continue to work without them.

### ReasoningTrace Dataclass (`eatp.reasoning`)

```python
from eatp.reasoning import ReasoningTrace, ConfidentialityLevel
from datetime import datetime, timezone

trace = ReasoningTrace(
    decision="Delegate data analysis to junior agent",
    rationale="Junior agent has demonstrated competence in Q3 reports",
    confidentiality=ConfidentialityLevel.RESTRICTED,
    timestamp=datetime.now(timezone.utc),
    alternatives_considered=["Senior agent (unavailable)", "Manual processing"],
    evidence=[{"type": "performance_review", "score": 0.92}],
    methodology="capability_matching",
    confidence=0.85,  # Must be 0.0 to 1.0 inclusive
)
```

| Field                     | Type                   | Required | Description                                   |
| ------------------------- | ---------------------- | -------- | --------------------------------------------- |
| `decision`                | `str`                  | Yes      | What was decided (human-readable)             |
| `rationale`               | `str`                  | Yes      | Why the decision was made                     |
| `confidentiality`         | `ConfidentialityLevel` | Yes      | Enterprise classification level               |
| `timestamp`               | `datetime`             | Yes      | When the reasoning occurred (UTC recommended) |
| `alternatives_considered` | `List[str]`            | No       | Other options evaluated (default: `[]`)       |
| `evidence`                | `List[Dict[str, Any]]` | No       | Supporting evidence (default: `[]`)           |
| `methodology`             | `Optional[str]`        | No       | Reasoning method (e.g., `"risk_assessment"`)  |
| `confidence`              | `Optional[float]`      | No       | Confidence score, 0.0-1.0 inclusive           |

Methods: `to_dict()`, `from_dict(data)`, `to_signing_payload()` (deterministic sorted keys for signing).

### ConfidentialityLevel Enum

Supports ordering comparisons for access control logic:

```
PUBLIC < RESTRICTED < CONFIDENTIAL < SECRET < TOP_SECRET
```

```python
from eatp.reasoning import ConfidentialityLevel

assert ConfidentialityLevel.PUBLIC < ConfidentialityLevel.SECRET  # True
assert ConfidentialityLevel.RESTRICTED <= ConfidentialityLevel.RESTRICTED  # True
```

`RESTRICTED` is the conventional default for most reasoning traces.

### REASONING_REQUIRED Constraint Type

A new value on `ConstraintType` (`eatp.chain`):

```python
from eatp.chain import ConstraintType

# Available constraint types:
# RESOURCE_LIMIT, TEMPORAL, DATA_SCOPE, ACTION_RESTRICTION,
# AUDIT_REQUIREMENT, REASONING_REQUIRED
```

When `REASONING_REQUIRED` is active on a chain's constraint envelope, the VERIFY operation checks for reasoning trace presence (at STANDARD level) and verifies reasoning integrity (at FULL level).

### Crypto Functions (`eatp.crypto`)

Three reasoning-specific functions:

```python
from eatp.crypto import (
    hash_reasoning_trace,       # SHA-256 of signing payload -> 64-char hex string
    sign_reasoning_trace,       # Ed25519 sign -> base64 signature
    verify_reasoning_signature, # Ed25519 verify -> bool
)

h = hash_reasoning_trace(trace)            # "a3f8..."  (64 chars)
sig = sign_reasoning_trace(trace, priv_key) # base64 string
ok = verify_reasoning_signature(trace, sig, pub_key)  # True/False
```

These operate on `ReasoningTrace.to_signing_payload()` — the same deterministic payload used for hashing and signing.

### Operations Reasoning Support

`delegate()` and `audit()` accept an optional `reasoning_trace` parameter:

```python
from eatp.reasoning import ReasoningTrace, ConfidentialityLevel
from datetime import datetime, timezone

trace = ReasoningTrace(
    decision="Delegate analysis task",
    rationale="Agent has required clearance and availability",
    confidentiality=ConfidentialityLevel.RESTRICTED,
    timestamp=datetime.now(timezone.utc),
)

# Delegation with reasoning
delegation = await ops.delegate(
    delegator_id="agent-senior",
    delegatee_id="agent-junior",
    task_id="task-q4",
    capabilities=["analyze_data"],
    reasoning_trace=trace,  # Optional
)
# delegation.reasoning_trace_hash and delegation.reasoning_signature
# are automatically computed and set

# Audit with reasoning
anchor = await ops.audit(
    agent_id="agent-senior",
    action="approve_report",
    reasoning_trace=trace,  # Optional
)
```

When a `reasoning_trace` is provided, the SDK automatically:

1. Stores the trace on the record (`DelegationRecord.reasoning_trace` / `AuditAnchor.reasoning_trace`)
2. Computes and stores `reasoning_trace_hash` (SHA-256)
3. Computes and stores `reasoning_signature` (Ed25519, separate from record signature)

### Verification Gradient with Reasoning

| Level        | Reasoning Check                                                                    |
| ------------ | ---------------------------------------------------------------------------------- |
| **QUICK**    | No reasoning check                                                                 |
| **STANDARD** | If `REASONING_REQUIRED` constraint active: checks presence, records warning violation (valid=True) |
| **FULL**     | If `REASONING_REQUIRED` + no trace: **hard failure** (valid=False). If trace present: verifies `reasoning_trace_hash` and `reasoning_signature` cryptographically |

`VerificationResult` includes two new optional fields:

- `reasoning_present: Optional[bool]` — `True` if all records have traces, `False` if any missing, `None` if no records to check or no `REASONING_REQUIRED` constraint
- `reasoning_verified: Optional[bool]` — `True` if hash + signature verified (FULL only), `False` on crypto failure, `None` if not checked

Missing reasoning when `REASONING_REQUIRED` is active: at STANDARD level, produces a non-blocking violation (severity: `"warning"`, valid=True). At FULL level, produces a **hard failure** (valid=False).

### Interop with Reasoning

**W3C Verifiable Credentials** (`eatp.interop.w3c_vc`): Confidentiality-driven selective disclosure. PUBLIC/RESTRICTED traces are included in the `reasoning` key. CONFIDENTIAL/SECRET/TOP_SECRET traces are withheld (only hash included). `reasoningTraceHash` and `reasoningSignature` are always included (they are integrity proofs, not confidential).

**SD-JWT** (`eatp.interop.sd_jwt`): `create_reasoning_sd_jwt()` accepts `disclose_reasoning=True/False`. Per-delegation confidentiality rules apply:

- PUBLIC: always included
- RESTRICTED: included when `disclose_reasoning=True`
- CONFIDENTIAL: included when `disclose_reasoning=True`, but `alternatives_considered` stripped
- SECRET/TOP_SECRET: never included, only hash survives

**JWT** (`eatp.interop.jwt`): Reasoning trace serialized as `eatp_reasoning_trace`, hash as `eatp_reasoning_trace_hash`, signature as `eatp_reasoning_signature`.

**UCAN** (`eatp.interop.ucan`): Same field mapping as JWT within UCAN facts.

### Enforcement with Reasoning

**StrictEnforcer** (`eatp.enforce.strict`): Propagates `reasoning_present` and `reasoning_verified` into enforcement record metadata. Logs reasoning violations separately at WARNING level.

**ShadowEnforcer** (`eatp.enforce.shadow`): Tracks three reasoning metrics:

- `reasoning_present_count` — traces found on records
- `reasoning_absent_count` — traces missing from records
- `reasoning_verification_failed_count` — crypto verification failures

**Selective Disclosure** (`eatp.enforce.selective_disclosure`): Redacts `reasoning_trace` based on confidentiality level — PUBLIC/RESTRICTED traces are kept visible, CONFIDENTIAL+ traces are redacted to SHA-256 hash.

### Trust Scoring with Reasoning

When `REASONING_REQUIRED` constraint is active, a sixth scoring factor `reasoning_coverage` is added at ~5% weight (`_REASONING_COVERAGE_WEIGHT = 5`). The base 5 weights are scaled down proportionally so the total remains 100. Coverage is the percentage of delegations and audit anchors that have a non-None `reasoning_trace`. Risk analysis flags incomplete coverage with a recommendation.

### Knowledge Bridge

`KnowledgeBridge.reasoning_trace_to_knowledge()` converts a `ReasoningTrace` into a `DECISION_RATIONALE` knowledge entry:

```python
entry = await bridge.reasoning_trace_to_knowledge(
    trace=trace,
    agent_id="agent-senior",
    derived_from=["entry-123"],  # Optional provenance chain
)
# entry.content_type == KnowledgeType.DECISION_RATIONALE
```

Preserves decision, rationale, methodology, evidence, and alternatives as structured metadata. Confidence maps from trace (default 0.8 if not set).

### Backward Compatibility

- `reasoning_trace`, `reasoning_trace_hash`, and `reasoning_signature` are `Optional` (default `None`) on `DelegationRecord` and `AuditAnchor`
- `reasoning_trace_hash` IS included in `to_signing_payload()` (v2.2) — binds reasoning to parent signature, preventing substitution attacks. Only `reasoning_trace` (full object) and `reasoning_signature` are excluded — they have their own separate verification path
- `VerificationResult.reasoning_present` and `reasoning_verified` default to `None` — legacy code sees no change
- All `from_dict()` methods handle missing reasoning fields gracefully

## The Traceability Distinction (Critical)

**EATP provides traceability, not accountability.**

- **Traceability**: Trace any AI action back to human authority. EATP delivers this.
- **Accountability**: Humans understand, evaluate, and bear consequences. No protocol can deliver this.
- Traceability is necessary for accountability but not sufficient.

## How EATP Differs from Existing Standards

| Standard         | Handles               | EATP Adds                           |
| ---------------- | --------------------- | ----------------------------------- |
| **OAuth/OIDC**   | User authentication   | Agent trust delegation              |
| **SPIFFE/SPIRE** | Service identity      | Agent autonomy governance           |
| **Zero-Trust**   | Network security      | Agent governance with trust lineage |
| **PKI**          | Hierarchical identity | Action-to-human traceability        |

Existing standards verify identity and access. EATP verifies that actions are within human-established trust boundaries with unbroken chains to human authority.

## Cascade Revocation

Trust revocation at any level automatically revokes all downstream delegations. No orphaned agents. Mitigations for propagation latency: short-lived credentials (5-minute validity), push-based revocation, action idempotency.

## Quick Reference

```
Human Authority
      |
      v [Genesis Record + Capability Attestation]
   Agent A
      |
      v [Delegation Record + Constraint Envelope]
   Agent B
      |
      v [Action + Audit Anchor]
   System Action
      |
      v [Trust Lineage Chain]
   Traceable to Human

Verification: Auto-approved → Flagged → Held → Blocked
Postures: Pseudo-Agent → Supervised → Shared Planning → Continuous Insight → Delegated
Operations: ESTABLISH → DELEGATE → VERIFY → AUDIT
```

## Relationship to Companion Frameworks

| Framework   | Relationship                                      |
| ----------- | ------------------------------------------------- |
| **CARE**    | EATP operationalizes CARE's governance philosophy |
| **COC**     | COC maps EATP concepts to development guardrails  |
| **Kailash** | Reference implementation (Apache 2.0)             |

## Standalone SDK (v0.1.0)

The EATP specification is implemented as a standalone Python SDK:

- **Install**: `pip install eatp`
- **Source**: `packages/eatp/src/eatp/`
- **License**: Apache 2.0 (Terrene Foundation)
- **Tests**: 1557 passed (+ Kaizen shim tests)

Kaizen's `kaizen.trust` module is now a shim layer that re-exports from the standalone SDK. Canonical code lives in `packages/eatp/`.

For SDK implementation details, see the companion skill files linked above.

## For Detailed Information

- `packages/eatp/src/eatp/__init__.py` - SDK API surface
- `packages/eatp/src/eatp/operations/__init__.py` - 4 core operations
- `packages/eatp/src/eatp/chain.py` - 5 EATP elements
- `packages/eatp/examples/quickstart.py` - Working example

For comprehensive analysis, invoke the **eatp-expert** agent.
