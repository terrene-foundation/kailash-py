# Architecture Decision Records — Platform Convergence

This directory contains the ADRs that define the platform-architecture-convergence decisions. Each ADR is a load-bearing decision that shapes the implementation plan.

## Index

| ADR                                                     | Title                               | Status   | Scope                 |
| ------------------------------------------------------- | ----------------------------------- | -------- | --------------------- |
| [ADR-001](01-adr-composition-over-extension-points.md)  | Composition over extension points   | ACCEPTED | Kaizen                |
| [ADR-002](02-adr-baseagent-keeps-node-inheritance.md)   | BaseAgent keeps Node inheritance    | ACCEPTED | Kaizen                |
| [ADR-003](03-adr-streaming-as-wrapper-primitive.md)     | Streaming as wrapper primitive      | ACCEPTED | Kaizen                |
| [ADR-004](04-adr-kailash-mcp-package-boundary.md)       | kailash-mcp package boundary        | ACCEPTED | MCP, Cross-SDK        |
| [ADR-005](05-adr-provider-capability-protocol-split.md) | Provider capability protocol split  | ACCEPTED | LLM providers         |
| [ADR-006](06-adr-single-constraint-envelope-type.md)    | Single canonical ConstraintEnvelope | ACCEPTED | Trust/PACT, Cross-SDK |
| [ADR-007](07-adr-delegate-as-composition-facade.md)     | Delegate as composition facade      | ACCEPTED | Kaizen                |
| [ADR-008](08-adr-cross-sdk-lockstep.md)                 | Cross-SDK lockstep convergence      | ACCEPTED | Governance process    |
| [ADR-009](09-adr-backward-compatibility-strategy.md)    | Backward compatibility strategy     | ACCEPTED | Release process       |
| [ADR-010](10-adr-co-five-layers-agent-mapping.md)       | CO Five Layers → Agent runtime map  | ACCEPTED | Cross-cutting (all)   |

## Decision Chain

```
ADR-002 (BaseAgent keeps Node)
   ↓
ADR-001 (Composition over extension points)
   ↓
ADR-003 (Streaming as wrapper)        ADR-007 (Delegate as facade)
         ↓                                    ↓
         └───────→ ADR-004 (kailash-mcp)  ←──┘
                        ↓
                  ADR-005 (Provider split)
                        ↓
                  ADR-006 (ConstraintEnvelope)
                        ↓
                  ADR-008 (Cross-SDK lockstep)
                        ↓
                  ADR-009 (Backward compat strategy)
```

## How to Read

Each ADR follows the format:

- **Status**: ACCEPTED / PROPOSED / SUPERSEDED
- **Context**: What problem are we solving
- **Decision**: What we decided
- **Rationale**: Why this over alternatives
- **Consequences**: What this enables and what it costs
- **Alternatives considered**: What we rejected and why

## Related Documents

- [Master architecture analysis](../00-master-architecture-analysis.md)
- [Red team round 1](../02-red-team-r1.md)
- [Research files — Python](../01-research/)
- [Research files — Rust](../02-rs-research/)
- [Specs](../03-specs/)
