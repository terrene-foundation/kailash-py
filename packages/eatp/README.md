# EATP -- Enterprise Agent Trust Protocol

[![Build](https://img.shields.io/github/actions/workflow/status/terrene-foundation/eatp-python/ci.yml?branch=main)](https://github.com/terrene-foundation/eatp-python/actions)
[![Coverage](https://img.shields.io/codecov/c/github/terrene-foundation/eatp-python)](https://codecov.io/gh/terrene-foundation/eatp-python)
[![PyPI](https://img.shields.io/pypi/v/eatp)](https://pypi.org/project/eatp/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/pypi/pyversions/eatp)](https://pypi.org/project/eatp/)

**Cryptographic trust chains, delegation, and verification for AI agent systems.**

A public good by the [Terrene Foundation](https://terrenefoundation.org) -- open infrastructure for AI trust, released under the Apache 2.0 license.

## What is EATP?

As AI agents act on behalf of humans -- reading databases, calling APIs, delegating work to other agents -- there is no standard way to answer: *Who authorized this agent? What can it do? Who is responsible when things go wrong?*

EATP solves this with cryptographic trust chains. Every agent carries a signed, verifiable record of who authorized it, what capabilities it has, what constraints limit its behavior, and what actions it has taken. Trust is established once, delegated with constraint tightening, verified before every action, and audited immutably.

## Quick Start

```python
import asyncio
from eatp import TrustOperations, TrustKeyManager, CapabilityRequest
from eatp.chain import AuthorityType, CapabilityType
from eatp.crypto import generate_keypair
from eatp.store.memory import InMemoryTrustStore
from eatp.authority import OrganizationalAuthority, AuthorityPermission

async def main():
    # Setup
    store = InMemoryTrustStore()
    await store.initialize()
    key_mgr = TrustKeyManager()
    priv_key, pub_key = generate_keypair()
    key_mgr.register_key("key-org", priv_key)

    # Register authority
    authority = OrganizationalAuthority(
        id="org-acme", name="ACME Corp",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=pub_key, signing_key_id="key-org",
        permissions=[AuthorityPermission.CREATE_AGENTS],
    )

    # Simple in-memory registry
    class Registry:
        async def initialize(self): pass
        async def get_authority(self, aid, include_inactive=False):
            return authority

    # Create TrustOperations
    ops = TrustOperations(
        authority_registry=Registry(),
        key_manager=key_mgr,
        trust_store=store,
    )

    # ESTABLISH trust
    chain = await ops.establish(
        agent_id="agent-001",
        authority_id="org-acme",
        capabilities=[
            CapabilityRequest(capability="analyze_data", capability_type=CapabilityType.ACTION),
        ],
    )

    # VERIFY before acting
    result = await ops.verify(agent_id="agent-001", action="analyze_data")
    print(f"Verified: {result.valid}")  # True

asyncio.run(main())
```

## Four Operations

EATP defines four operations that form the complete lifecycle of agent trust:

### ESTABLISH -- Create initial trust

```python
chain = await ops.establish(
    agent_id="agent-001",
    authority_id="org-acme",
    capabilities=[
        CapabilityRequest(capability="analyze_data", capability_type=CapabilityType.ACTION),
        CapabilityRequest(capability="read_reports", capability_type=CapabilityType.ACCESS),
    ],
    constraints=["read_only", "business_hours_only"],
)
```

An organizational authority (company, department, individual) creates a signed genesis record for an agent, granting specific capabilities under specific constraints.

### DELEGATE -- Transfer trust with tightening

```python
delegation = await ops.delegate(
    delegator_id="agent-001",
    delegatee_id="agent-002",
    task_id="task-quarterly-report",
    capabilities=["analyze_data"],
    additional_constraints=["no_pii_export"],
)
```

An agent can delegate a subset of its capabilities to another agent. Constraints can only be *tightened*, never loosened -- the delegatee can never do more than the delegator.

### VERIFY -- Validate before every action

```python
result = await ops.verify(agent_id="agent-001", action="analyze_data")
if result.valid:
    # Proceed with action
    ...
```

Called before every agent action. Three verification levels trade off speed for thoroughness:
- **QUICK** (~1ms): Hash and expiration check
- **STANDARD** (~5ms): Capability and constraint validation
- **FULL** (~50ms): Cryptographic signature verification of the entire chain

### AUDIT -- Immutable action log

```python
from eatp.chain import ActionResult

anchor = await ops.audit(
    agent_id="agent-001",
    action="analyze_data",
    resource="finance_db",
    result=ActionResult.SUCCESS,
)
```

Every action is recorded in a signed, hash-linked audit trail. Each audit anchor includes the trust chain hash at time of action, enabling tamper detection.

## Features

### Core Trust

- **Ed25519 cryptography** via PyNaCl -- signing, verification, key generation
- **Trust Lineage Chains** -- 5-element structure (genesis, capabilities, delegations, constraints, audit anchors)
- **Trust postures** -- 5-level state machine (DELEGATED, CONTINUOUS_INSIGHT, SHARED_PLANNING, SUPERVISED, PSEUDO_AGENT)
- **Trust scoring** -- Composite 0-100 score across chain completeness, delegation depth, constraint coverage, posture, recency

### Constraint System

Five constraint dimensions with six built-in templates:

| Dimension | Controls |
|---|---|
| **Scope** | Allowed actions, visibility level |
| **Financial** | Spend limits, daily caps, commerce types |
| **Temporal** | Business hours, market hours, duration limits |
| **Communication** | Endpoint allowlists, rate limits, external access |
| **Data Access** | Classification ceiling, read-only mode, PII access |

Templates: `governance`, `finance`, `community`, `standards`, `audit`, `minimal`

```python
from eatp.templates import get_template, customize_template

# Load a built-in template
finance_constraints = get_template("finance")

# Customize it
custom = customize_template("finance", {"financial": {"max_amount": 50000}})
```

### Enforcement

- **StrictEnforcer** -- Production mode. Blocks unauthorized actions, holds for human review.
- **ShadowEnforcer** -- Observation mode. Logs what *would* be blocked without interrupting.
- **Decorators** -- 3-line integration for any async function.

```python
from eatp.enforce import verified, audited, shadow

@verified(agent_id="agent-001", action="read_data")
async def read_sensitive_data(query: str) -> dict:
    return await db.execute(query)
```

### Interoperability

EATP trust chains can be exported to and imported from industry standards:

| Format | Module | Use Case |
|---|---|---|
| **JWT** (RFC 7519) | `eatp.interop.jwt` | API authentication, bearer tokens |
| **W3C Verifiable Credentials** | `eatp.interop.w3c_vc` | Cross-organization trust |
| **DID** (Decentralized Identifiers) | `eatp.interop.did` | Agent identity |
| **UCAN** v0.10.0 | `eatp.interop.ucan` | Decentralized delegation |
| **SD-JWT** | `eatp.interop.sd_jwt` | Selective disclosure |
| **Biscuit** | `eatp.interop.biscuit` | Attenuation tokens |

### MCP Server

EATP ships an MCP server for direct integration with AI agent frameworks. Agents can establish trust, verify capabilities, and record audit entries through standard MCP tool calls.

### CLI

The `eatp` command provides full trust lifecycle management:

| Command | Description |
|---|---|
| `eatp init` | Create authority keypair and genesis record |
| `eatp establish` | Establish trust for a new agent |
| `eatp delegate` | Delegate capabilities to another agent |
| `eatp verify` | Verify an agent's trust for an action |
| `eatp revoke` | Revoke an agent's trust or delegation |
| `eatp status` | Show agent trust chain status |
| `eatp audit` | Query the audit trail |
| `eatp export` | Export trust chain (JSON, JWT) |
| `eatp verify-chain` | Cryptographically verify an entire chain |
| `eatp version` | Show SDK version |

```bash
# Initialize an authority
eatp init --name "Acme Corp" --type organization

# Establish trust for an agent
eatp establish --authority auth-abc123 --agent agent-001 --capabilities analyze_data,read_reports

# Verify before acting
eatp verify --agent agent-001 --action analyze_data
```

## Installation

```bash
pip install eatp
```

Optional extras:

```bash
pip install eatp[postgres]   # PostgreSQL-backed trust store
pip install eatp[dev]        # Development tools (pytest, mypy, ruff)
```

Requires Python 3.11+.

## Architecture

An EATP Trust Lineage Chain contains five elements:

```
TrustLineageChain
  |-- GenesisRecord          Who authorized this agent to exist?
  |-- CapabilityAttestation  What can this agent do?
  |-- DelegationRecord       Who delegated work to this agent?
  |-- ConstraintEnvelope     What limits apply?
  |-- AuditAnchor            What has this agent done?
```

Every element is cryptographically signed. The chain forms a tamper-evident structure: modifying any element invalidates the chain hash, and FULL verification checks every signature against the issuing authority's public key.

Delegation is monotonically constraining -- each delegation can only *tighten* constraints, never loosen them. This guarantees that delegated agents can never exceed the permissions of their delegators, no matter how deep the chain.

## Comparison with Alternatives

| | EATP | X.509 | SPIFFE | UCAN | Biscuit |
|---|---|---|---|---|---|
| Designed for AI agents | Yes | No | No | Partial | No |
| Delegation with constraint tightening | Yes | No | No | Yes | Yes |
| Action-level audit trail | Yes | No | No | No | No |
| Trust scoring and postures | Yes | No | No | No | No |
| Interop with existing standards | JWT, W3C VC, DID, UCAN, SD-JWT, Biscuit | N/A | X.509 | JWT | N/A |
| Human-origin traceability | Yes | No | No | No | No |
| Open source | Apache 2.0 | Various | Apache 2.0 | Various | Apache 2.0 |

EATP is not a replacement for transport-layer security (TLS/mTLS) or identity providers. It operates at the *authorization* and *accountability* layer, answering what an agent is allowed to do and recording what it actually did.

## Links

- [Terrene Foundation](https://terrenefoundation.org)
- [EATP Specification](https://docs.terrenefoundation.org/eatp)
- [API Documentation](https://docs.terrenefoundation.org/eatp/api)
- [Apache 2.0 License](LICENSE)

## Contributing

EATP is open infrastructure maintained by the Terrene Foundation. Contributions are welcome.

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/your-feature`)
3. Write tests for your changes
4. Ensure all tests pass (`pytest`)
5. Submit a pull request

Please follow [conventional commits](https://www.conventionalcommits.org/) for commit messages.

For bug reports and feature requests, open an issue on [GitHub](https://github.com/terrene-foundation/eatp-python/issues).
