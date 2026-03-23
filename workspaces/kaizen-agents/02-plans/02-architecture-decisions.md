# Architecture Decisions — kaizen-agents

## AD-ORC-01: Package Placement — Separate Package in Monorepo

**Decision**: kaizen-agents is a separate package at `packages/kaizen-agents/` within the kailash-py monorepo.

**Rationale**: Follows the existing three-layer architecture defined in the brief. The SDK (kailash-kaizen) provides deterministic L3 primitives. kaizen-agents adds LLM-driven orchestration. Separate PyPI package allows independent versioning.

## AD-ORC-02: Type Strategy — Adapter Layer

**Decision**: Local types.py stays for internal use. SDK types accessed through `_sdk_compat.py` adapter at integration boundaries.

**Rationale**: The compatibility matrix (P0-01) found 17 types need adapters (enum casing, timedelta→float, structural differences). Full replacement would require 379 test rewrites. Adapter layer isolates coupling.

## AD-ORC-03: Execution Model — PlanMonitor Keeps Own Async Loop

**Decision**: PlanMonitor keeps its own async execution loop. Uses SDK PlanValidator and SDK types (via adapters) but does NOT delegate to SDK PlanExecutor.

**Rationale**: PlanMonitor has LLM-driven recovery (FailureDiagnoser + Recomposer) that the SDK PlanExecutor doesn't know about. The SDK PlanExecutor is for conformance testing; the orchestration layer adds intelligence.

## AD-ORC-04: Protocol Pattern — Stateful Protocol Objects

**Decision**: Communication protocols (Delegation, Clarification, Escalation) are stateful objects with LLM composition + SDK MessageRouter transport.

**Rationale**: Protocols have lifecycle state, correlation tracking, and need to compose content (LLM) and deliver it (SDK MessageRouter). Stateful objects naturally encapsulate both concerns.

## AD-ORC-05: Testing Strategy — Three Tiers

| Tier            | What                                           | Mocking            |
| --------------- | ---------------------------------------------- | ------------------ |
| 1 (Unit)        | Individual signatures, protocol state machines | Allowed (LLM only) |
| 2 (Integration) | Cross-component flows with real SDK primitives | NO mocking of SDK  |
| 3 (E2E)         | Full plan lifecycle                            | NO mocking         |

## AD-ORC-06: Concurrency Model — asyncio.Lock

**Decision**: All orchestration components sharing state with L3 primitives use `asyncio.Lock` (not `threading.Lock`).

**Rationale**: Per AD-L3-04-AMENDED, L3 primitives use asyncio.Lock because they are exclusively called from async code paths. The orchestration layer follows the same convention for consistency.

## AD-ORC-07: PlanExecutor Integration — SDK Validation, Local Execution

**Decision**: SDK AsyncPlanExecutor is available for direct use. PlanMonitor uses SDK PlanValidator for structural validation but runs its own execution loop for LLM recovery support.

**Rationale**: The SDK AsyncPlanExecutor (S-01) was built for consumers who want deterministic gradient handling without LLM recovery. PlanMonitor adds recovery intelligence. Both paths are valid.

## AD-ORC-08: Structured Output — kaizen-agents Keeps complete_structured()

**Decision**: kaizen-agents keeps its own `LLMClient.complete_structured()` with JSON schema enforcement. The SDK signature system is NOT modified.

**Rationale**: The existing `llm.py` already has working structured output. Modifying the SDK signature system (OutputField, \_flatten_outputs) is a cross-cutting change affecting all kailash-kaizen consumers — high risk, low immediate value.

## AD-ORC-09: Naming — GovernedSupervisor

**Decision**: The high-level API class is named `GovernedSupervisor` (not `AutonomousSupervisor`).

**Rationale**: "Governed" is the distinguishing characteristic. "Autonomous" collides with existing `kaizen/agents/autonomous/` module semantics.
