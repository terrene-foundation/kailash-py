# Trust Lineage Chain

The Trust Lineage Chain is EATP's core data structure — a cryptographically verifiable record of everything about an agent's trust status.

## Five Elements

### 1. Genesis Record

The root of trust. Proves **who authorized this agent to exist**.

- Created by an organizational authority
- Contains Ed25519 signature from the authority
- Optional expiration
- Metadata (department, owner, purpose)

### 2. Capability Attestation

Proves **what this agent can do**.

- Specific capability name (e.g., "analyze_data")
- Capability type: ACCESS, ACTION, or DELEGATION
- Constraints on the capability
- Scope restrictions

### 3. Delegation Record

Proves **who delegated work to this agent**.

- Delegator and delegatee IDs
- Task scoping
- Constraint tightening (delegations can only add restrictions, never remove them)
- Human origin tracing

### 4. Constraint Envelope

Defines **what limits apply**.

- Five constraint dimensions: scope, financial, temporal, communication, data access
- Aggregated from genesis, capabilities, and delegations
- Hash for quick comparison

### 5. Audit Anchor

Records **what the agent has done**.

- Immutable, hash-linked trail
- Trust chain hash at time of action
- Success/failure/denied result
- Causal chains (parent-child relationships)

## Chain Integrity

Every chain element is cryptographically signed. The chain hash changes when any component changes, enabling O(1) integrity verification.

```python
chain = await ops.establish(agent_id="agent-001", ...)
chain_hash = chain.hash()  # SHA-256 of entire chain state
```

## Linked Hash Chain

For tamper detection across multiple agents, EATP supports linked hash chains where each entry includes the previous entry's hash — similar to a blockchain but for trust state.

```python
from eatp.chain import LinkedHashChain

lhc = LinkedHashChain()
hash1 = lhc.add_hash("agent-1", chain1.hash())
hash2 = lhc.add_hash("agent-2", chain2.hash())
valid, break_idx = lhc.verify_chain_linkage([chain1.hash(), chain2.hash()])
```
