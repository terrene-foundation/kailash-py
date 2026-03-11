# EATP — Enterprise Agent Trust Protocol

Cryptographic trust chains, delegation, and verification for AI agent systems.

## What is EATP?

As AI agents become autonomous participants in enterprise workflows, a critical question emerges: **how do you verify what an agent is authorized to do?**

EATP answers this with cryptographic proof — not configuration files, not ACLs, not trust-on-first-use. Every agent carries a **Trust Lineage Chain** that cryptographically proves:

- **Who authorized it** (Genesis Record)
- **What it can do** (Capability Attestation)
- **Who delegated work to it** (Delegation Record)
- **What limits apply** (Constraint Envelope)
- **What it has done** (Audit Anchor)

## Four Operations

| Operation | Purpose | Latency |
|-----------|---------|---------|
| **ESTABLISH** | Create initial trust for an agent | ~10ms |
| **DELEGATE** | Transfer trust with constraint tightening | ~5ms |
| **VERIFY** | Validate trust chain before action | < 5ms |
| **AUDIT** | Record action in immutable trail | ~2ms |

## Quick Start

```python
from eatp import TrustOperations, TrustKeyManager, InMemoryTrustStore
from eatp.crypto import generate_keypair

store = InMemoryTrustStore()
await store.initialize()
key_mgr = TrustKeyManager()
priv_key, pub_key = generate_keypair()
key_mgr.register_key("key-org", priv_key)

# ... establish authority, create ops, verify agents
```

See [Quick Start Guide](getting-started/quickstart.md) for the full walkthrough.

## A Public Good

EATP is published by the **Terrene Foundation** under the **Apache 2.0** license. It is open infrastructure for AI trust — not a commercial product.

- [GitHub Repository](https://github.com/terrene-foundation/eatp-python)
- [EATP Specification](https://eatp.terrene.dev)
- [Terrene Foundation](https://terrenefoundation.org)
