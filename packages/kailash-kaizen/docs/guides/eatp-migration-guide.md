# EATP Migration Guide

This guide helps you migrate existing Kaizen agents to use the Enterprise Agent Trust Protocol (EATP).

## Overview

EATP provides cryptographically verifiable trust chains for AI agents. Migrating to EATP adds:

- **Trust verification** before every action
- **Capability attestation** for what agents can do
- **Constraint enforcement** to limit agent behavior
- **Complete audit trails** for compliance

## Migration Steps

### Step 1: Assess Your Current Setup

Before migrating, identify:

1. **Agent count**: How many agents need trust chains?
2. **Authority structure**: Who authorizes agents (one org, multiple teams)?
3. **Capabilities needed**: What actions do agents perform?
4. **Constraints required**: What limits should apply?

### Step 2: Set Up EATP Infrastructure

#### Database Setup

EATP requires PostgreSQL for trust chain storage:

```bash
# Create database
createdb kaizen_trust

# Set environment variable
export POSTGRES_URL="postgresql://user:password@localhost:5432/kaizen_trust"
```

#### Initialize Trust Components

```python
from kaizen.trust import (
    PostgresTrustStore,
    OrganizationalAuthorityRegistry,
    TrustKeyManager,
    TrustOperations,
    generate_keypair,
)

# Create components
trust_store = PostgresTrustStore(
    database_url=os.getenv("POSTGRES_URL"),
    enable_cache=True,
)
authority_registry = OrganizationalAuthorityRegistry(
    database_url=os.getenv("POSTGRES_URL"),
)
key_manager = TrustKeyManager()

# Initialize (creates tables)
await trust_store.initialize()
await authority_registry.initialize()
```

### Step 3: Register Organizational Authority

Every trust chain needs an authority. Register your organization:

```python
from kaizen.trust import (
    OrganizationalAuthority,
    AuthorityType,
    AuthorityPermission,
    generate_keypair,
)

# Generate Ed25519 keypair
private_key, public_key = generate_keypair()

# Store private key securely
key_manager.register_key("key-my-org", private_key)

# Register authority
authority = OrganizationalAuthority(
    id="org-my-company",
    name="My Company",
    authority_type=AuthorityType.ORGANIZATION,
    public_key=public_key,
    signing_key_id="key-my-org",
    permissions=[
        AuthorityPermission.CREATE_AGENTS,
        AuthorityPermission.GRANT_CAPABILITIES,
    ],
    is_active=True,
)

await authority_registry.register_authority(authority)
```

### Step 4: Migrate BaseAgent to TrustedAgent

#### Before (BaseAgent)

```python
from kaizen import BaseAgent

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="my-agent",
            model="gpt-4",
            signature="Analyze data -> Report",
        )

    async def analyze(self, data: dict) -> dict:
        # No trust verification
        return await self.run(data)
```

#### After (TrustedAgent)

```python
from kaizen import BaseAgent
from kaizen.trust import (
    TrustedAgent,
    TrustedAgentConfig,
    TrustOperations,
    CapabilityRequest,
    CapabilityType,
    VerificationLevel,
)

class MyTrustedAgent(TrustedAgent):
    def __init__(self, trust_ops: TrustOperations):
        super().__init__(
            agent_id="agent-my-agent-001",
            trust_operations=trust_ops,
            config=TrustedAgentConfig(
                verification_level=VerificationLevel.STANDARD,
                audit_all_actions=True,
            ),
            # Original BaseAgent params
            name="my-agent",
            model="gpt-4",
            signature="Analyze data -> Report",
        )

    async def analyze(self, data: dict) -> dict:
        # Trust is automatically verified before run()
        return await self.run(data)


# Usage
trust_ops = TrustOperations(...)
await trust_ops.initialize()

# Establish trust ONCE
chain = await trust_ops.establish(
    agent_id="agent-my-agent-001",
    authority_id="org-my-company",
    capabilities=[
        CapabilityRequest(
            capability="analyze_data",
            capability_type=CapabilityType.ACTION,
        ),
    ],
)

# Create trusted agent
agent = MyTrustedAgent(trust_ops)
result = await agent.analyze(data)  # Trust verified automatically
```

### Step 5: Add Capabilities

Define what your agent can do:

```python
from kaizen.trust import CapabilityRequest, CapabilityType

capabilities = [
    # Read access
    CapabilityRequest(
        capability="read_database",
        capability_type=CapabilityType.ACCESS,
        constraints=["read_only"],
    ),
    # Action capability
    CapabilityRequest(
        capability="generate_report",
        capability_type=CapabilityType.ACTION,
    ),
    # Delegation capability (for supervisors)
    CapabilityRequest(
        capability="delegate_tasks",
        capability_type=CapabilityType.DELEGATION,
    ),
]

chain = await trust_ops.establish(
    agent_id="agent-001",
    authority_id="org-my-company",
    capabilities=capabilities,
)
```

### Step 6: Add Constraints

Limit agent behavior with constraints:

```python
from kaizen.trust import Constraint, ConstraintType

constraints = [
    # Resource limit
    Constraint(
        constraint_type=ConstraintType.RESOURCE_LIMIT,
        name="max_api_calls",
        value=1000,
    ),
    # Time window
    Constraint(
        constraint_type=ConstraintType.TIME_WINDOW,
        name="business_hours",
        value={"start": "09:00", "end": "18:00"},
    ),
    # Data scope
    Constraint(
        constraint_type=ConstraintType.DATA_SCOPE,
        name="allowed_departments",
        value=["sales", "marketing"],
    ),
    # Action restriction
    Constraint(
        constraint_type=ConstraintType.ACTION_RESTRICTION,
        name="no_delete",
        value=True,
    ),
]

chain = await trust_ops.establish(
    agent_id="agent-001",
    authority_id="org-my-company",
    capabilities=capabilities,
    constraints=constraints,
)
```

### Step 7: Enable Trust Verification

Explicit verification (optional, automatic for TrustedAgent):

```python
from kaizen.trust import VerificationLevel

# Before sensitive action
result = await trust_ops.verify(
    agent_id="agent-001",
    action="read_database",
    level=VerificationLevel.FULL,  # Cryptographic verification
)

if not result.valid:
    raise PermissionError(f"Trust verification failed: {result.errors}")

# Proceed with action
```

### Step 8: Add Audit Logging

Record all actions (automatic for TrustedAgent):

```python
from kaizen.trust import ActionResult

# After action completes
await trust_ops.audit(
    agent_id="agent-001",
    action_type="generate_report",
    resource_uri="report://sales/q4-2024",
    result=ActionResult.SUCCESS,
    metadata={
        "duration_seconds": 15,
        "pages_generated": 20,
    },
)
```

## Migration Patterns

### Pattern 1: Gradual Migration

Migrate agents one at a time:

```python
# Phase 1: Establish trust for critical agents
for agent_id in critical_agents:
    await trust_ops.establish(agent_id=agent_id, ...)

# Phase 2: Convert to TrustedAgent
class CriticalAgent(TrustedAgent):  # Was BaseAgent
    ...

# Phase 3: Migrate remaining agents
for agent_id in remaining_agents:
    await trust_ops.establish(agent_id=agent_id, ...)
```

### Pattern 2: Parallel Running

Run both versions during migration:

```python
class HybridAgent(BaseAgent):
    def __init__(self, trust_ops: Optional[TrustOperations] = None):
        self.trust_ops = trust_ops
        self.use_trust = trust_ops is not None

    async def run(self, input_data):
        if self.use_trust:
            # New trust-verified path
            result = await self.trust_ops.verify(...)
            if not result.valid:
                raise PermissionError(result.errors)

        # Existing logic
        return await super().run(input_data)
```

### Pattern 3: Feature Flag Migration

Use feature flags to control trust:

```python
import os

USE_EATP = os.getenv("ENABLE_EATP", "false").lower() == "true"

class MyAgent(TrustedAgent if USE_EATP else BaseAgent):
    ...
```

## Multi-Agent Migration

### Migrating Supervisor-Worker Patterns

```python
# 1. Establish supervisor with delegation capability
supervisor_chain = await trust_ops.establish(
    agent_id="supervisor-001",
    authority_id="org-my-company",
    capabilities=[
        CapabilityRequest(
            capability="coordinate_tasks",
            capability_type=CapabilityType.ACTION,
        ),
        CapabilityRequest(
            capability="delegate_work",
            capability_type=CapabilityType.DELEGATION,
        ),
    ],
)

# 2. Establish workers with basic trust
for i in range(3):
    await trust_ops.establish(
        agent_id=f"worker-{i:03d}",
        authority_id="org-my-company",
        capabilities=[
            CapabilityRequest(
                capability="process_data",
                capability_type=CapabilityType.ACTION,
            ),
        ],
    )

# 3. Supervisor delegates to workers at runtime
delegation = await trust_ops.delegate(
    delegator_agent_id="supervisor-001",
    delegatee_agent_id="worker-001",
    task_id="task-batch-001",
    capabilities=["process_data"],
    constraints=[
        Constraint(
            constraint_type=ConstraintType.RESOURCE_LIMIT,
            name="max_records",
            value=1000,  # Tightened from supervisor's limit
        ),
    ],
)
```

## Performance Considerations

### Enable Caching

```python
trust_store = PostgresTrustStore(
    database_url=os.getenv("POSTGRES_URL"),
    enable_cache=True,
    cache_ttl_seconds=300,  # 5 minutes
)
```

### Use Appropriate Verification Levels

```python
# High-frequency, low-risk: QUICK (<1ms)
await trust_ops.verify(agent_id, level=VerificationLevel.QUICK)

# Most operations: STANDARD (<5ms)
await trust_ops.verify(agent_id, action="read", level=VerificationLevel.STANDARD)

# Sensitive operations: FULL (<50ms)
await trust_ops.verify(agent_id, action="admin", level=VerificationLevel.FULL)
```

## Troubleshooting

### Common Issues

#### "AgentAlreadyEstablishedError"

Agent already has trust chain:

```python
# Check if already established
existing = await trust_store.get_chain(agent_id)
if existing:
    print(f"Agent {agent_id} already established")
else:
    await trust_ops.establish(agent_id=agent_id, ...)
```

#### "AuthorityNotFoundError"

Authority not registered:

```python
# Ensure authority exists
try:
    authority = await authority_registry.get_authority(authority_id)
except AuthorityNotFoundError:
    # Register authority first
    await authority_registry.register_authority(...)
```

#### "CapabilityNotFoundError"

Action not in capabilities:

```python
# Add capability during establish
await trust_ops.establish(
    agent_id=agent_id,
    capabilities=[
        CapabilityRequest(
            capability="missing_action",  # Add the missing capability
            capability_type=CapabilityType.ACTION,
        ),
    ],
)
```

#### "ConstraintViolationError" in Delegation

Trying to loosen constraints:

```python
# Constraints can only be TIGHTENED
# If parent has max_records=10000, child cannot have max_records=20000

# Correct: Tighten to smaller value
constraints=[
    Constraint(
        constraint_type=ConstraintType.RESOURCE_LIMIT,
        name="max_records",
        value=5000,  # Tighter than parent's 10000
    ),
]
```

## Rollback Plan

If issues occur, you can run without trust verification:

```python
# Emergency bypass (use sparingly!)
class MyAgent(BaseAgent):  # Revert to BaseAgent
    async def run(self, input_data):
        # Trust verification bypassed
        return await super().run(input_data)
```

Keep trust chains in database for re-enabling:

```python
# Re-enable later
class MyAgent(TrustedAgent):  # Restore TrustedAgent
    ...
```

## Checklist

Before going to production:

- [ ] PostgreSQL database provisioned
- [ ] Authority registered with secure key storage
- [ ] All agents have trust chains established
- [ ] Capabilities defined for each agent
- [ ] Constraints configured appropriately
- [ ] Caching enabled for performance
- [ ] Audit logging configured
- [ ] Monitoring set up for trust failures
- [ ] Rollback plan documented

## Next Steps

- Read the [API Reference](../api/trust.md)
- Review [Security Best Practices](./eatp-security-best-practices.md)
- Explore [Examples](../../examples/trust/)

## Support

For migration assistance:
- GitHub Issues: https://github.com/terrene-foundation/kailash-py/issues
- Documentation: https://docs.kailash.dev/kaizen/trust
