# External Agent ABAC Policies

## Overview

The External Agent Policy Engine provides attribute-based access control (ABAC) for external agents in Kaizen Framework. This enables fine-grained access control based on:

- **Time windows** (business hours, maintenance windows, blackout periods)
- **Geographic location** (country/region allowlists/blocklists)
- **Deployment environment** (development, staging, production)
- **Data classification** (public, internal, confidential, restricted)
- **Agent provider** (copilot_studio, custom_rest_api, etc.)
- **Agent tags** (approval status, department, capabilities)

## Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                  ExternalAgentPolicyEngine                   │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Policy Evaluation Flow                                 │ │
│  │                                                          │ │
│  │  1. Find applicable policies (pattern matching)         │ │
│  │  2. Evaluate conditions for each policy                 │ │
│  │  3. Apply conflict resolution strategy                  │ │
│  │  4. Return PolicyDecision (ALLOW/DENY + reason)         │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  Conflict Resolution Strategies:                            │
│  • DENY_OVERRIDES: Any DENY → final DENY (most secure)     │
│  • ALLOW_OVERRIDES: Any ALLOW → final ALLOW (permissive)   │
│  • FIRST_APPLICABLE: First matching policy wins (priority) │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Policy Components

```python
ExternalAgentPolicy:
  - policy_id: Unique identifier
  - name: Human-readable name
  - effect: ALLOW or DENY
  - conditions: List[PolicyCondition]
  - priority: int (for conflict resolution)
  - principal_pattern: Optional regex for principal matching
  - action_pattern: Optional regex for action matching
```

### Condition Types

1. **TimeWindowCondition**: Time-based restrictions
   - Business hours (e.g., "mon-fri 09:00-17:00")
   - Maintenance windows (blackout periods)
   - Allowed days of week

2. **LocationCondition**: Geographic restrictions
   - Allowed countries (e.g., ["US", "CA"])
   - Blocked countries (e.g., ["RU", "CN"])
   - Allowed/blocked regions (e.g., ["us-east-1"])

3. **EnvironmentCondition**: Deployment environment restrictions
   - Allowed environments (e.g., [PRODUCTION])
   - Blocked environments (e.g., [DEVELOPMENT])

4. **ProviderCondition**: Agent provider restrictions
   - Allowed providers (e.g., ["copilot_studio", "custom_rest_api"])
   - Blocked providers (e.g., ["untrusted_provider"])

5. **TagCondition**: Tag-based restrictions
   - Required tags (all must be present)
   - Blocked tags (none can be present)
   - Any-of tags (at least one must be present)

6. **DataClassificationCondition**: Data sensitivity restrictions
   - Allowed classifications (e.g., [PUBLIC, INTERNAL])
   - Encryption requirements (bool)

## Usage Examples

### Example 1: Business Hours Policy

Only allow agent invocations during business hours:

```python
from kaizen.governance import (
    ExternalAgentPolicy,
    PolicyEffect,
    TimeWindowCondition,
    ExternalAgentPolicyEngine,
    ConflictResolutionStrategy,
)

# Define business hours policy
business_hours_policy = ExternalAgentPolicy(
    policy_id="policy-business-hours",
    name="Allow only during business hours",
    effect=PolicyEffect.ALLOW,
    conditions=[
        TimeWindowCondition(
            business_hours={
                "mon-fri": "09:00-17:00",
                "timezone": "America/New_York"
            }
        )
    ],
    priority=10,
)

# Create policy engine
engine = ExternalAgentPolicyEngine(
    policies=[business_hours_policy],
    conflict_resolution=ConflictResolutionStrategy.DENY_OVERRIDES,
)

# Evaluate policy
from kaizen.governance import ExternalAgentPolicyContext, ExternalAgentPrincipal
from datetime import datetime

context = ExternalAgentPolicyContext(
    principal=ExternalAgentPrincipal(
        external_agent_id="agent-001",
        provider="copilot_studio",
    ),
    action="invoke",
    resource="agent-001",
    time=datetime(2025, 12, 22, 10, 0, 0),  # Monday 10:00 AM
)

decision = engine.evaluate_policies(context)
print(f"Decision: {decision.effect.value}")  # Output: ALLOW
print(f"Reason: {decision.reason}")
```

### Example 2: Production Environment + Location Policy

Restrict production deployments to US/CA only:

```python
from kaizen.governance import (
    Environment,
    EnvironmentCondition,
    LocationCondition,
)

# Policy: ALLOW production invocations from US/CA only
production_policy = ExternalAgentPolicy(
    policy_id="policy-production-location",
    name="Production restricted to US/CA",
    effect=PolicyEffect.ALLOW,
    conditions=[
        EnvironmentCondition(
            allowed_environments=[Environment.PRODUCTION]
        ),
        LocationCondition(
            allowed_countries=["US", "CA"]
        )
    ],
    priority=20,
)

# Create context with location
context = ExternalAgentPolicyContext(
    principal=ExternalAgentPrincipal(
        external_agent_id="agent-prod-001",
        provider="copilot_studio",
        environment=Environment.PRODUCTION,
        location={"country": "US", "region": "us-east-1"},
    ),
    action="invoke",
    resource="agent-prod-001",
    time=datetime.now(),
)

decision = engine.evaluate_policies(context)
# Result: ALLOW (production + US location)
```

### Example 3: Tag-Based Approval Policy

Require "approved" and "finance" tags for sensitive operations:

```python
from kaizen.governance import TagCondition

# Policy: ALLOW only agents with "approved" and "finance" tags
approval_policy = ExternalAgentPolicy(
    policy_id="policy-finance-approved",
    name="Require finance approval tags",
    effect=PolicyEffect.ALLOW,
    conditions=[
        TagCondition(
            required_tags={"approved", "finance"}
        )
    ],
    priority=30,
)

# Agent with required tags
context = ExternalAgentPolicyContext(
    principal=ExternalAgentPrincipal(
        external_agent_id="agent-finance-001",
        provider="custom_rest_api",
        tags=["approved", "finance", "production"],
    ),
    action="invoke",
    resource="agent-finance-001",
    time=datetime.now(),
)

decision = engine.evaluate_policies(context)
# Result: ALLOW (has both required tags)
```

### Example 4: Conflict Resolution - Deny Overrides

When multiple policies match, DENY wins:

```python
# Policy 1: ALLOW copilot_studio provider
allow_copilot = ExternalAgentPolicy(
    policy_id="policy-allow-copilot",
    name="Allow Copilot Studio",
    effect=PolicyEffect.ALLOW,
    conditions=[
        ProviderCondition(allowed_providers=["copilot_studio"])
    ],
    priority=10,
)

# Policy 2: DENY production environment
deny_production = ExternalAgentPolicy(
    policy_id="policy-deny-production",
    name="Deny production",
    effect=PolicyEffect.DENY,
    conditions=[
        EnvironmentCondition(blocked_environments=[Environment.PRODUCTION])
    ],
    priority=20,
)

# Engine with DENY_OVERRIDES strategy
engine = ExternalAgentPolicyEngine(
    policies=[allow_copilot, deny_production],
    conflict_resolution=ConflictResolutionStrategy.DENY_OVERRIDES,
)

# Context matching BOTH policies
context = ExternalAgentPolicyContext(
    principal=ExternalAgentPrincipal(
        external_agent_id="agent-001",
        provider="copilot_studio",  # Matches allow_copilot
        environment=Environment.PRODUCTION,  # Matches deny_production
    ),
    action="invoke",
    resource="agent-001",
    time=datetime.now(),
)

decision = engine.evaluate_policies(context)
# Result: DENY (deny_production wins with DENY_OVERRIDES)
print(f"Decision: {decision.effect.value}")  # DENY
print(f"Matched policies: {decision.matched_policies}")  # Both policies
```

### Example 5: Data Classification + Encryption

Require encryption for confidential data:

```python
from kaizen.governance import DataClassification, DataClassificationCondition

# Policy: ALLOW confidential data only with encryption
encryption_policy = ExternalAgentPolicy(
    policy_id="policy-confidential-encrypted",
    name="Confidential data requires encryption",
    effect=PolicyEffect.ALLOW,
    conditions=[
        DataClassificationCondition(
            allowed_classifications=[DataClassification.CONFIDENTIAL],
            requires_encryption=True,
        )
    ],
    priority=40,
)

# Context with encrypted confidential data
context = ExternalAgentPolicyContext(
    principal=ExternalAgentPrincipal(
        external_agent_id="agent-data-001",
        provider="custom_rest_api",
    ),
    action="read",
    resource="confidential-customer-data",
    time=datetime.now(),
    data_classification=DataClassification.CONFIDENTIAL,
    attributes={"encryption_enabled": True},
)

decision = engine.evaluate_policies(context)
# Result: ALLOW (confidential + encryption enabled)
```

## Performance

The policy engine is optimized for <5ms p95 latency:

- **Policy caching** with TTL (60s default)
- **Pattern pre-compilation** for regex matching
- **Early exit** for first_applicable strategy
- **Short-circuit evaluation** for conditions

Benchmarks with 100 policies show <1ms average evaluation time.

## Best Practices

### 1. Use Deny-Overrides for Security

```python
# Most secure: Any DENY wins
engine = ExternalAgentPolicyEngine(
    policies=policies,
    conflict_resolution=ConflictResolutionStrategy.DENY_OVERRIDES,
)
```

### 2. Set Appropriate Priorities

```python
# Higher priority policies evaluated first
critical_deny = ExternalAgentPolicy(
    policy_id="critical",
    effect=PolicyEffect.DENY,
    priority=100,  # Evaluated first
    ...
)

general_allow = ExternalAgentPolicy(
    policy_id="general",
    effect=PolicyEffect.ALLOW,
    priority=1,  # Evaluated last
    ...
)
```

### 3. Use Pattern Matching for Scalability

```python
# Match all production agents
production_policy = ExternalAgentPolicy(
    policy_id="all-production",
    principal_pattern=r"agent-prod-.*",  # Matches agent-prod-001, agent-prod-002, etc.
    action_pattern=r"invoke|configure",  # Matches invoke OR configure
    ...
)
```

### 4. Combine Multiple Conditions

```python
# All conditions must be TRUE for policy to apply
strict_policy = ExternalAgentPolicy(
    policy_id="strict",
    effect=PolicyEffect.ALLOW,
    conditions=[
        TimeWindowCondition(business_hours={...}),  # AND
        LocationCondition(allowed_countries=["US"]),  # AND
        TagCondition(required_tags={"approved"}),  # AND
    ],
)
```

### 5. Use Default Deny

The engine defaults to DENY when no policies match (fail-safe):

```python
# No matching policies → DENY
decision = engine.evaluate_policies(context)
# decision.reason = "No applicable policies found (default deny)"
```

## Integration with Kaizen Studio

The policy engine is designed for Kaizen Studio integration:

```python
# TODO-025: Kaizen Studio will use this engine for:
# 1. Pre-execution governance checks
# 2. Real-time policy evaluation (<5ms)
# 3. Audit logging of policy decisions
# 4. Policy management UI
```

## See Also

- [Policy Configuration Guide](./policy-configuration.md)
- [Conflict Resolution Strategies](./policy-conflict-resolution.md)
- [Time-Based Policies](./time-based-policies.md)
- [Location-Based Policies](./location-based-policies.md)
