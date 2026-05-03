---
type: CONNECTION
date: 2026-03-31
created_at: 2026-03-31T12:01:00+08:00
author: agent
session_id: session-10
session_turn: 1
project: kailash
topic: PACT and EATP trust chain are adjacent but never connected
phase: analyze
tags: [pact, eatp, trust-chain, architecture, integration-gap]
---

# PACT and EATP Trust Chain Are Adjacent But Never Connected

## Connection

The PACT governance module (`src/kailash/trust/pact/`) and the EATP trust chain module (`src/kailash/trust/chain.py` + `src/kailash/trust/operations/`) live in the same `trust/` package tree but have zero integration:

- PACT's `engine.py`: 0 imports from `kailash.trust.chain`
- PACT's `audit.py`: Defines its own `AuditAnchor` class (different from EATP's `AuditAnchor` in `chain.py`)
- EATP's `TrustOperations`: Has `establish()`, `delegate()`, `verify()`, `audit()` — none called by PACT
- EATP's `TrustStore` (filesystem/sqlite/memory): Never instantiated by PACT

**The modules are structurally adjacent but functionally isolated.** PACT manages organizational governance (D/T/R, envelopes, bridges) and emits its own audit trail. EATP manages trust lineage (genesis, capabilities, delegations) with cryptographic verification. They solve complementary problems but don't talk to each other.

## Why This Matters

Issue #199 (EATP record emission) is the bridge. It connects organizational governance decisions to cryptographic trust lineage. When a role gets an envelope, that's a `DelegationRecord`. When a clearance is granted, that's a `CapabilityAttestation`. When the org is created, that's a `GenesisRecord`.

The design is dual emission: PACT keeps its own audit chain for tamper-evident governance trail, AND emits EATP types for cross-system interop. Both run in parallel.

## Architectural Implication

The integration point is `GovernanceEngine.__init__()` gaining an optional `trust_chain_store: TrustStore | None` parameter. When provided, EATP records are emitted alongside PACT anchors. When `None`, PACT runs standalone (backward-compatible). This is the minimum-coupling approach — PACT depends on EATP types but not vice versa.

## For Discussion

1. Should the dual audit trail (PACT anchors + EATP records) be the permanent design, or should PACT eventually migrate entirely to EATP record types and deprecate its custom `AuditAnchor`?
2. The `AuditAnchor` name collision between PACT (`audit.py:111`) and EATP (`chain.py:503`) — is this a problem for users who import both, or does the package namespace prevent confusion?
3. If `trust_chain_store` is `None` (standalone mode), should PACT still produce the EATP record _objects_ (for local inspection) even if it doesn't persist them?
