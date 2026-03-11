# EATP Architecture

## Data Model

```
TrustLineageChain
├── GenesisRecord          # Root of trust for an agent
│   ├── agent_id           # The agent being established
│   ├── authority_id       # Who authorized this agent
│   ├── authority_type     # ORGANIZATION | SYSTEM
│   ├── capabilities       # Initial capability list
│   ├── constraints        # Initial constraints
│   └── signature          # Ed25519 signature by authority
├── CapabilityAttestation[] # What the agent can do
│   ├── capability         # CapabilityType enum
│   ├── scope             # Action scope
│   └── constraints       # Per-capability constraints
├── DelegationRecord[]     # Trust delegated to sub-agents
│   ├── delegator_id      # Who delegates
│   ├── delegatee_id      # Who receives
│   ├── capabilities      # What's delegated
│   ├── constraints       # Tightened constraints (monotonic)
│   ├── reasoning_trace   # Optional ReasoningTrace (WHY)
│   ├── reasoning_trace_hash  # SHA-256 of trace (in signing payload)
│   └── reasoning_signature   # Ed25519 of trace (separate verification)
├── ConstraintEnvelope     # Aggregated constraints
│   └── constraints[]     # All applicable constraints
└── AuditAnchor[]         # Immutable audit trail
    ├── action            # What was done
    ├── result            # ActionResult enum
    ├── chain_hash        # Hash of chain at action time
    ├── reasoning_trace   # Optional ReasoningTrace (WHY)
    ├── reasoning_trace_hash  # SHA-256 of trace (in signing payload)
    └── reasoning_signature   # Ed25519 of trace (separate verification)
```

## Module Dependencies

```
eatp.chain (data structures)
    ↑
eatp.reasoning (ReasoningTrace, ConfidentialityLevel)
    ↗ standalone, imported by eatp.chain + eatp.crypto

eatp.crypto (Ed25519, hashing, reasoning hash/sign/verify)
    ↑
eatp.operations (ESTABLISH, DELEGATE, VERIFY, AUDIT)
    ↑               ↑
eatp.store.*    eatp.authority
(persistence)   (registry)
    ↑
eatp.enforce.* (StrictEnforcer, ShadowEnforcer, decorators)
    ↑
eatp.constraints.* (dimensions, templates, evaluator)
    ↑
eatp.postures (TrustPosture, PostureStateMachine)
    ↑
eatp.scoring (trust score 0-100, reports)

eatp.interop.* (JWT, W3C VC, DID, UCAN, SD-JWT, Biscuit)
    ↗ standalone, imports from eatp.chain + eatp.crypto

eatp.merkle (MerkleTree for audit proofs)
    ↗ standalone, imports from eatp.crypto

eatp.mcp (MCP server — 5 tools, 4 resources)
    ↗ imports from eatp.operations, eatp.store, eatp.enforce

eatp.cli (CLI — 10 commands + scan + quickstart)
    ↗ imports from eatp.operations, eatp.store, eatp.crypto
```

## Key Design Decisions

1. **PDP/PEP Separation**: SDK computes verdicts (Policy Decision Point), host framework enforces (Policy Enforcement Point)
2. **Monotonic Tightening**: Delegations can only add constraints, never remove them
3. **Ed25519 Only**: Single cryptographic primitive for simplicity and security
4. **Protocol-based Registry**: `AuthorityRegistryProtocol` decouples operations from concrete storage
5. **Append-Only Audit**: AuditAnchors are immutable once created
6. **No External Dependencies for Core**: Core chain/crypto uses only PyNaCl + stdlib
7. **Dual-Binding Reasoning (v2.2)**: `reasoning_trace_hash` bound into parent record's signing payload; `reasoning_signature` separately signs trace content. Prevents substitution attacks while preserving backward compatibility
8. **Graduated Reasoning Enforcement**: QUICK (no check), STANDARD (advisory warning), FULL (hard failure + crypto verification when REASONING_REQUIRED)
