---
name: 29-pact
description: "PACT governance framework — D/T/R accountability grammar, operating envelopes, knowledge clearance, and verification gradient for AI agent organizations. Use when asking about 'governance', 'D/T/R', 'operating envelope', 'knowledge clearance', 'verification gradient', 'GovernanceEngine', 'PactGovernedAgent', 'access enforcement', 'organizational governance', 'PACT', 'governed agent', 'clearance', 'bridges', 'KSP', or 'monotonic tightening'."
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

| Skill                                                 | Use When                                    |
| ----------------------------------------------------- | ------------------------------------------- |
| [pact-quickstart](pact-quickstart.md)                 | Getting started, first GovernanceEngine     |
| [pact-governance-engine](pact-governance-engine.md)   | Engine API, verify_action, compute_envelope |
| [pact-dtr-addressing](pact-dtr-addressing.md)         | D/T/R grammar, Address parsing              |
| [pact-envelopes](pact-envelopes.md)                   | Three-layer model, monotonic tightening     |
| [pact-access-enforcement](pact-access-enforcement.md) | 5-step algorithm, clearance, bridges, KSPs  |
| [pact-governed-agents](pact-governed-agents.md)       | PactGovernedAgent, @governed_tool           |
| [pact-kaizen-integration](pact-kaizen-integration.md) | Wrapping Kaizen agents with governance      |

## Key Types

```python
from pact.governance import GovernanceEngine, GovernanceVerdict
from pact.governance.config import (
    ConstraintEnvelopeConfig, OrgDefinition,
    TrustPostureLevel, VerificationLevel,
    ConfidentialityLevel,
)
from pact.governance.agent import PactGovernedAgent
from pact.governance.audit import AuditChain
```

## Package Location

`packages/kailash-pact/src/pact/governance/`

## Rules

See `.claude/rules/pact-governance.md` for security invariants.
