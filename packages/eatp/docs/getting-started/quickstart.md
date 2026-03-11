# Quick Start

This guide walks through the four EATP operations in under 20 lines of code.

## Setup

```python
import asyncio
from eatp import TrustOperations, TrustKeyManager, InMemoryTrustStore
from eatp.authority import OrganizationalAuthority, AuthorityPermission
from eatp.chain import AuthorityType, CapabilityType
from eatp.crypto import generate_keypair
from eatp.operations import CapabilityRequest

async def main():
    # 1. Create infrastructure
    store = InMemoryTrustStore()
    await store.initialize()
    key_mgr = TrustKeyManager()
    priv_key, pub_key = generate_keypair()
    key_mgr.register_key("key-org", priv_key)
```

## Register an Authority

```python
    authority = OrganizationalAuthority(
        id="org-acme",
        name="ACME Corp",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=pub_key,
        signing_key_id="key-org",
        permissions=[AuthorityPermission.CREATE_AGENTS],
    )
```

## ESTABLISH — Create Trust

```python
    # Create a simple authority registry
    class Registry:
        async def get_authority(self, authority_id):
            if authority_id == "org-acme":
                return authority
            return None

    ops = TrustOperations(
        authority_registry=Registry(),
        key_manager=key_mgr,
        trust_store=store,
    )

    chain = await ops.establish(
        agent_id="agent-001",
        authority_id="org-acme",
        capabilities=[
            CapabilityRequest(
                capability="analyze_data",
                capability_type=CapabilityType.ACTION,
            )
        ],
    )
    print(f"Established: {chain.genesis.agent_id}")
```

## VERIFY — Check Trust

```python
    result = await ops.verify(agent_id="agent-001", action="analyze_data")
    print(f"Verified: {result.valid}")  # True
```

## DELEGATE — Transfer Trust

```python
    await ops.delegate(
        delegator_id="agent-001",
        delegatee_id="agent-002",
        task_id="task-001",
        capabilities=["analyze_data"],
        constraints=["read_only"],
    )
```

## AUDIT — Record Actions

```python
    await ops.audit(
        agent_id="agent-001",
        action="analyze_data",
        resource="transactions",
    )

asyncio.run(main())
```

## Next Steps

- [Constraint Templates](../examples/templates.md) — Pre-built constraint sets
- [Shadow Mode](../examples/shadow.md) — Gradual enforcement rollout
- [CLI Guide](cli.md) — Command-line interface
