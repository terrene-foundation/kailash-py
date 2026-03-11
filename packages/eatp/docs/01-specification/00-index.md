# EATP Specification Index

**Enterprise Agent Trust Protocol -- Version 2.0**

| Field      | Value                                               |
| ---------- | --------------------------------------------------- |
| Version    | EATP v2.0                                           |
| Status     | Draft (Public Review)                               |
| License    | Apache 2.0                                          |
| Maintainer | Terrene Foundation                                  |
| Repository | `github.com/terrene-foundation/eatp-python`         |
| Rust SDK   | `github.com/terrene-foundation/eatp-rust` (planned) |

---

## Overview

EATP is a cryptographic trust protocol for AI agent systems. It answers five
questions about every agent action:

1. **Who authorized this agent to exist?** (Genesis Record)
2. **What can this agent do?** (Capability Attestation)
3. **Who delegated work to this agent?** (Delegation Record)
4. **What limits apply?** (Constraint Envelope)
5. **What has this agent done?** (Audit Anchor)

These five chain elements form a **Trust Lineage Chain** -- an immutable,
hash-linked data structure that is cryptographically signed at every level.

Four operations manipulate and query trust chains:

| Operation     | Purpose                                               | Section                                |
| ------------- | ----------------------------------------------------- | -------------------------------------- |
| **ESTABLISH** | Create initial trust for an agent (genesis + keys)    | [operations.md](../spec/operations.md) |
| **DELEGATE**  | Transfer a subset of trust to another agent           | [operations.md](../spec/operations.md) |
| **VERIFY**    | Validate an agent's trust chain for a specific action | [operations.md](../spec/operations.md) |
| **AUDIT**     | Record an action in the immutable audit trail         | [operations.md](../spec/operations.md) |

---

## Specification Sections

### Core Protocol

| #   | Section                     | File                                                         | Summary                                                                                                    |
| --- | --------------------------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| 1   | Trust Chain Data Structures | [trust-chain.md](../spec/trust-chain.md)                     | GenesisRecord, CapabilityAttestation, DelegationRecord, ConstraintEnvelope, AuditAnchor, TrustLineageChain |
| 2   | Operations                  | [operations.md](../spec/operations.md)                       | ESTABLISH, DELEGATE, VERIFY, AUDIT lifecycle and semantics                                                 |
| 3   | Constraints                 | [constraints.md](../spec/constraints.md)                     | Tightening invariant, constraint types, ConstraintValidator                                                |
| 4   | Enforcement Modes           | [enforcement.md](../spec/enforcement.md)                     | StrictEnforcer, ShadowEnforcer, ChallengeProtocol, decorators                                              |
| 5   | Trust Postures              | [postures.md](../spec/postures.md)                           | FULL_AUTONOMY, ASSISTED, SUPERVISED, HUMAN_DECIDES, BLOCKED                                                |
| 6   | Wire Format & Schemas       | [wire-format.md](../spec/wire-format.md)                     | JSON serialization, canonical form for signing                                                             |
| 7   | JSON Schemas                | [schemas.md](../spec/schemas.md)                             | JSON Schema definitions for all chain element types                                                        |
| 8   | Responsibility Matrix       | [responsibility-matrix.md](../spec/responsibility-matrix.md) | RACI matrix for trust operations across roles                                                              |

### Extended Features

| #   | Feature                        | Module Path                                 | Summary                                                                          |
| --- | ------------------------------ | ------------------------------------------- | -------------------------------------------------------------------------------- |
| 9   | Constraint Dimensions          | `eatp.constraints`                          | Pluggable constraint evaluation: cost, time, resource, rate, data, communication |
| 10  | Trust Scoring                  | `eatp.scoring`                              | Deterministic 0-100 trust score based on chain completeness, depth, posture      |
| 11  | Challenge-Response Protocol    | `eatp.enforce.challenge`                    | Live key possession proof with nonce, replay protection, rate limiting           |
| 12  | W3C Verifiable Credentials     | `eatp.interop.w3c_vc`                       | Export/import trust chains as W3C VC Data Model 2.0 credentials                  |
| 13  | SD-JWT Interop                 | `eatp.interop.sd_jwt`                       | Selective disclosure JWT tokens for capability proof                             |
| 14  | DID Interop                    | `eatp.interop.did`                          | Decentralized Identifier resolution and mapping                                  |
| 15  | UCAN / Biscuit Interop         | `eatp.interop.ucan`, `eatp.interop.biscuit` | Token format bridges for UCAN and Biscuit ecosystems                             |
| 16  | Enterprise System Agents (ESA) | `eatp.esa`                                  | Trust-aware proxy agents for legacy enterprise systems                           |
| 17  | Agent Registry                 | `eatp.registry`                             | Trust-verified agent registration, discovery, heartbeats                         |
| 18  | Secure Messaging               | `eatp.messaging`                            | Signed envelopes, replay protection, channel management                          |
| 19  | Multi-Signature                | `eatp.multi_sig`                            | M-of-N signature schemes for high-value operations                               |
| 20  | Key Rotation                   | `eatp.rotation`                             | Atomic key rotation with chain re-signing                                        |
| 21  | Certificate Revocation         | `eatp.crl`                                  | Revocation list management and broadcast                                         |
| 22  | Governance Policies            | `eatp.governance`                           | Policy engine, cost estimation, rate limiting                                    |
| 23  | Knowledge Provenance           | `eatp.knowledge`                            | Trust-annotated knowledge entries with provenance tracking                       |
| 24  | A2A Communication              | `eatp.a2a`                                  | Agent-to-agent service discovery and authenticated RPC                           |
| 25  | Orchestration Runtime          | `eatp.orchestration`                        | Trust-aware workflow execution with policy enforcement                           |
| 26  | MCP Server                     | `eatp.mcp`                                  | Model Context Protocol server exposing EATP as tools                             |

---

## The Five Chain Elements

```
 GenesisRecord          Who authorized this agent to exist?
      |                    - authority_id, agent_id, public_key
      |                    - Ed25519 signature from authority
      v
 CapabilityAttestation   What can this agent do?
      |                    - capability name + type (ACCESS, ACTION, DELEGATION)
      |                    - constraints, scope, expiration
      v
 DelegationRecord        Who delegated work to this agent?
      |                    - delegator_id -> delegatee_id
      |                    - capability subset, constraint subset
      |                    - tightening invariant enforced
      v
 ConstraintEnvelope      What limits apply?
      |                    - cost_limit, rate_limit, time_window
      |                    - resources (glob matching), geo_restrictions
      |                    - nested and custom constraint dimensions
      v
 AuditAnchor             What has this agent done?
                           - action, resource, result (success/failure/denied)
                           - trust_chain_hash at time of action
                           - Ed25519 signature for immutability
```

These five elements are linked by SHA-256 hashes into a **TrustLineageChain**.

---

## The Four Operations

### ESTABLISH

Creates initial trust for an agent. Produces a GenesisRecord signed by the
authority's Ed25519 key, one or more CapabilityAttestations, and a
ConstraintEnvelope. The resulting TrustLineageChain is stored and becomes the
agent's identity.

### DELEGATE

Transfers a **subset** of an agent's trust to another agent. The tightening
invariant guarantees that the delegatee can never have more permissions than the
delegator. Produces a DelegationRecord and a new TrustLineageChain for the
delegatee.

### VERIFY

Validates an agent's trust chain for a specific action. Checks chain
integrity (signatures and hashes), capability existence, constraint
satisfaction, and delegation depth. Returns a `VerificationResult` with
a validity flag, level (BASIC, STANDARD, FULL), and detailed reason.

### AUDIT

Records an agent action in the immutable audit trail. Produces an
AuditAnchor containing the action, resource, result, trust chain hash at
the time of the action, and an Ed25519 signature. The audit trail is
hash-linked for tamper detection.

---

## The Tightening Invariant

The central security property of EATP:

> **Trust can only be reduced as it flows through the delegation chain.**

Formally: for every constraint dimension `d`, if parent has value `P(d)` and
child has value `C(d)`, then `C(d)` must be a subset of or less than or equal
to `P(d)`. The `ConstraintValidator` enforces this for all supported
dimensions including cost limits, time windows, resource scopes, rate limits,
geo restrictions, delegation depth, and custom nested constraints.

---

## Verification Gradient

EATP supports three verification levels with increasing cost and assurance:

| Level        | Checks                                                      |
| ------------ | ----------------------------------------------------------- |
| **BASIC**    | Chain exists, genesis signature valid                       |
| **STANDARD** | BASIC + capability exists + constraints satisfied           |
| **FULL**     | STANDARD + delegation depth + all signatures + chain hashes |

The `StrictEnforcer` maps verification results to four verdicts:
AUTO_APPROVED, FLAGGED, HELD, BLOCKED.

---

## SDK Extraction Note

EATP v2.0 is extracted from the Kailash Kaizen framework as a standalone,
independently versioned Python package (`pip install eatp`). The protocol
and SDK are open source under the Apache 2.0 license, maintained by the
Terrene Foundation as a public good.

A Rust SDK (`eatp-rust`) is planned for environments requiring native
performance and WASM compilation.

The extraction preserves all cryptographic guarantees while removing
dependencies on the Kailash Core SDK runtime, making EATP usable in any
Python 3.11+ project regardless of orchestration framework.

---

## References

- **Source Code**: `packages/eatp/src/eatp/`
- **License**: [Apache 2.0](../../LICENSE)
- **Terrene Foundation**: [terrenefoundation.org](https://terrenefoundation.org)
- **API Documentation**: [docs/api/](../api/)
- **Getting Started**: [docs/getting-started/](../getting-started/)
- **Examples**: [examples/](../../examples/)
