---
name: 29-pact
description: "PACT governance framework -- D/T/R accountability grammar, operating envelopes, knowledge clearance, and verification gradient for AI agent organizations. Use when asking about 'governance', 'D/T/R', 'operating envelope', 'knowledge clearance', 'verification gradient', 'GovernanceEngine', 'PactGovernedAgent', 'access enforcement', 'organizational governance', 'PACT', 'governed agent', 'clearance', 'bridges', 'KSP', 'monotonic tightening', 'MCP governance', 'McpGovernanceEnforcer', 'McpGovernanceMiddleware', 'McpAuditTrail', 'McpToolPolicy', 'MCP tool policy', 'default-deny MCP', or 'governed MCP tools'."
---

# PACT Governance Skills

Quick reference for PACT organizational governance patterns.

## Install

```bash
pip install kailash-pact          # Governance framework
pip install kailash>=2.0.0        # Core SDK with trust subsystem
pip install kailash-kaizen>=2.0.0 # For governed Kaizen agents
```

## Skill Files

| Skill                                                 | Use When                                                                        |
| ----------------------------------------------------- | ------------------------------------------------------------------------------- |
| [pact-quickstart](pact-quickstart.md)                 | Getting started, first GovernanceEngine                                         |
| [pact-governance-engine](pact-governance-engine.md)   | Engine API, verify_action, compute_envelope                                     |
| [pact-dtr-addressing](pact-dtr-addressing.md)         | D/T/R grammar, Address parsing                                                  |
| [pact-envelopes](pact-envelopes.md)                   | Three-layer model, monotonic tightening, gradient thresholds, interim envelopes |
| [pact-access-enforcement](pact-access-enforcement.md) | 5-step algorithm, clearance, bridges, KSPs                                      |
| [pact-governed-agents](pact-governed-agents.md)       | PactGovernedAgent, @governed_tool                                               |
| [pact-kaizen-integration](pact-kaizen-integration.md) | Wrapping Kaizen agents with governance                                          |
| [pact-mcp-governance](pact-mcp-governance.md)         | MCP tool governance: enforce, audit, middleware                                 |

## Key Types

```python
# Flat imports via pact package (recommended)
from pact import (
    GovernanceEngine, GovernanceVerdict,
    ConstraintEnvelopeConfig, OrgDefinition,
    TrustPostureLevel, VerificationLevel,
    PactGovernedAgent,
    AuditChain,
    Address, PactError,
)
from kailash.trust import ConfidentialityLevel

# Or canonical imports from kailash.trust.pact
from kailash.trust.pact import GovernanceEngine, GovernanceVerdict, Address
from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig, OrgDefinition,
    TrustPostureLevel, VerificationLevel,
)

# MCP governance
from pact.mcp import (
    McpGovernanceEnforcer, McpGovernanceMiddleware, McpAuditTrail,
    McpToolPolicy, McpGovernanceConfig, McpActionContext,
)

# Shadow enforcement storage
from kailash.trust.enforce.shadow_store import (
    ShadowStore,          # Protocol
    MemoryShadowStore,    # In-memory bounded deque
    SqliteShadowStore,    # SQLite persistence
)

# Signed envelopes
from kailash.trust.pact.envelopes import SignedEnvelope
```

## New Features (v2.0)

### GovernanceEngine Pure Python

The engine is now a pure Python implementation with `store_backend="memory"|"sqlite"`:

```python
engine = GovernanceEngine(
    org,
    store_backend="sqlite",
    store_url="governance.db",
    eatp_emitter=emitter,                  # Optional EATP record emission
    vacancy_deadline_hours=24,             # Interim envelope window
    require_bilateral_consent=True,        # Bridge bilateral consent
)
```

### ShadowStore Persistent Storage

`ShadowStore` protocol enables persistent enforcement records:

```python
store = SqliteShadowStore("shadow.db")   # 0o600 perms, parameterized SQL
shadow = ShadowEnforcer(store=store)

# Time-windowed metrics
metrics = store.get_metrics(since=one_hour_ago)
records = store.get_records(limit=100, agent_id="agent-001")
```

### SignedEnvelope (Ed25519)

Cryptographic envelope signing with 90-day expiry:

```python
signed = sign_envelope(envelope, private_key, signed_by="D1-R1")
valid = signed.verify(public_key)   # Checks signature + expiry, fail-closed
# frozen=True -- immutable after creation
```

## Rules

See `.claude/rules/pact-governance.md` for security invariants.
