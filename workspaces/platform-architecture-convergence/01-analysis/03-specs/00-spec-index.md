# Specifications — Platform Convergence

This directory contains the detailed specifications for each architectural change in the platform convergence. Each SPEC is the canonical source of truth that both Python and Rust SDKs implement against (per ADR-008 lockstep protocol).

## Index

| SPEC                                                  | Title                                                                                                | Status | Implements                    |
| ----------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------ | ----------------------------- |
| [SPEC-01](01-spec-kailash-mcp-package.md)             | kailash-mcp package                                                                                  | DRAFT  | ADR-004                       |
| [SPEC-02](02-spec-provider-layer.md)                  | Provider layer (per-provider modules + capability protocols)                                         | DRAFT  | ADR-005                       |
| [SPEC-03](03-spec-composition-wrappers.md)            | Composition wrappers (StreamingAgent, MonitoredAgent, L3GovernedAgent, SupervisorAgent, WorkerAgent) | DRAFT  | ADR-001, ADR-003              |
| [SPEC-04](04-spec-baseagent-slimming.md)              | BaseAgent slimming + extension point deprecation                                                     | DRAFT  | ADR-001, ADR-002              |
| [SPEC-05](05-spec-delegate-engine.md)                 | Delegate engine facade                                                                               | DRAFT  | ADR-007                       |
| [SPEC-06](06-spec-nexus-migration.md)                 | Nexus auth/audit migration + PACTMiddleware                                                          | DRAFT  | (Nexus audit recommendations) |
| [SPEC-07](07-spec-constraint-envelope-unification.md) | ConstraintEnvelope unification                                                                       | DRAFT  | ADR-006                       |
| [SPEC-08](08-spec-core-sdk-consolidation.md)          | Core SDK audit/registry consolidation                                                                | DRAFT  | (Core synergy audit)          |
| [SPEC-09](09-spec-cross-sdk-parity.md)                | Cross-SDK parity specification                                                                       | DRAFT  | ADR-008                       |
| [SPEC-10](10-spec-multi-agent-patterns.md)            | Multi-agent patterns migration                                                                       | DRAFT  | ADR-001                       |

## Spec Template

Every SPEC follows this structure:

```markdown
# SPEC-XX: <Name>

**Status**: DRAFT | ACCEPTED | IN_PROGRESS | COMPLETED | SUPERSEDED
**Implements**: <ADR references>
**Cross-SDK issues**:

- Python: terrene-foundation/kailash-py#NNN
- Rust: esperie-enterprise/kailash-rs#NNN

## §1 Overview

## §2 Wire Types / API Contracts

## §3 Semantics

## §4 Backward Compatibility

## §5 Security Considerations

## §6 Examples

## §7 Interop Test Vectors

## §8 Implementation Notes

## §9 Migration Order

## §10 Test Migration

## §11 Related Specs
```

## Implementation Order

Per the master analysis convergence phases:

### Phase 1: Foundation extraction

1. **SPEC-01** — Extract `kailash-mcp` package (unblocks everything else)

### Phase 2: Shared primitives

2. **SPEC-02** — Provider layer (feeds BaseAgent and Delegate)
3. **SPEC-07** — ConstraintEnvelope unification (unblocks Trust/PACT convergence)

### Phase 3: BaseAgent + wrappers

4. **SPEC-03** — Composition wrappers (StreamingAgent, MonitoredAgent, etc.)
5. **SPEC-04** — BaseAgent slimming (consumes providers + MCP + composition wrappers)

### Phase 4: Engine facade + patterns

6. **SPEC-05** — Delegate engine facade (composes slimmed BaseAgent + wrappers)
7. **SPEC-10** — Multi-agent patterns migration (built on BaseAgent wrappers)

### Phase 5: Nexus + Core SDK cleanup

8. **SPEC-06** — Nexus auth migration + PACTMiddleware
9. **SPEC-08** — Core SDK audit/registry consolidation

### Phase 6: Cross-SDK lockstep

10. **SPEC-09** — Cross-SDK parity (validates everything)

## Related Documents

- [Master architecture analysis](../00-master-architecture-analysis.md)
- [ADR Index](../04-adrs/00-adr-index.md)
- [Red team round 1](../02-red-team-r1.md)
- [Python research](../01-research/)
- [Rust research](../02-rs-research/)
