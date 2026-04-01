---
type: RISK
date: 2026-04-01
created_at: 2026-04-01T15:45:00+08:00
author: agent
session_turn: 1
project: kailash-align
topic: ModelRegistry extension contract is not covered by kailash-ml-protocols
phase: analyze
tags: [model-registry, protocols, dependency, cross-workspace, adapter-registry]
---

# ModelRegistry Extension Contract Not Covered by Protocols Package

## Risk Description

Red Team R1 (RT3-03, CRITICAL) identified the kailash-ml dependency as the hardest blocker and recommended freezing the ModelRegistry interface in `kailash-ml-protocols` before implementation begins.

R2 analysis reveals that `kailash-ml-protocols` solves a different problem: it resolves the circular dependency between kailash-ml and kailash-kaizen by defining `AgentInfusionProtocol` and `MLToolProtocol`. It does NOT define a ModelRegistry interface.

AdapterRegistry uses concrete class inheritance (`class AdapterRegistry(ModelRegistry)`), not protocol-based composition. The extension depends on:

1. ModelRegistry's constructor signature: `__init__(db: DataFlow, artifact_store: ArtifactStore | None)`
2. Method signatures: `register()`, `promote()`, `load()`, `compare()`
3. DataFlow model schemas: `MLModel`, `MLModelVersion` field definitions
4. `Stage` enum values
5. `ArtifactStore` protocol
6. `ModelArtifact` dataclass

If any of these change during kailash-ml implementation (TSG-302), AdapterRegistry breaks.

## Why This Matters

The R1 finding assumed that `kailash-ml-protocols` would serve as the interface contract. It does not. The actual contract is implicit -- documented in the kailash-ml architecture doc and TSG-302 acceptance criteria, but not enforced by any code artifact.

This means parallel development of kailash-ml and kailash-align is safe only if TSG-302 implementation does not deviate from the architecture doc. Given that implementation routinely discovers design issues that force API changes, this is a real risk.

## Likelihood and Impact

- **Likelihood**: MEDIUM -- TSG-302 has detailed acceptance criteria listing the exact methods and DataFlow models. The design is thorough. But implementation surprises happen.
- **Impact**: HIGH if triggered -- AdapterRegistry's DataFlow model extension means a schema change in MLModelVersion cascades to AlignAdapterVersion, potentially requiring migration logic.

## Severity Revision

R1 rated this CRITICAL. R2 downgrades to MEDIUM because:

1. The architecture doc specifies the API in detail (unlike a vague "we'll figure it out")
2. TSG-302 acceptance criteria are specific enough to be a de facto contract
3. The risk is implementation drift, not design ambiguity

## Mitigation

Create an explicit "ModelRegistry Extension Contract" that lists:

- Frozen method signatures (name, parameters, return types)
- Frozen DataFlow model schemas (field names, types)
- Frozen enum values (Stage)
- Frozen protocol (ArtifactStore)

This document lives in the kailash-align workspace and is referenced by both kailash-ml and kailash-align workspaces. Any change to a frozen element requires a coordination ticket.

## For Discussion

1. Should AdapterRegistry be refactored from concrete inheritance to composition? `AdapterRegistry` could hold a `ModelRegistry` instance and delegate to it, rather than extending it. This would decouple the implementation dependency -- AdapterRegistry would depend on the interface, not the class. The trade-off: more boilerplate code, but resilience to ModelRegistry internal changes.
2. If TSG-302 implementation discovers that `register()` needs an additional parameter (e.g., `tags: list[str]`), how should that be communicated to kailash-align? Should the contract document live in a shared location (e.g., kailash-ml-protocols repo), or is a workspace-level document sufficient?
3. The DataFlow model extension (`AlignAdapterVersion extends MLModelVersion`) is the highest-risk coupling point. If kailash-ml changes MLModelVersion's primary key strategy or adds a required field, the cascade is severe. Should AlignAdapterVersion use a foreign-key reference to MLModelVersion instead of extending it?
