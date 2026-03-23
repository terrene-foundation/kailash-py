# L3 Autonomy Primitives — Brief Summary

## What This Is

Six specification briefs defining the L3 (Level 3) autonomy layer for the Kailash Kaizen agent framework. L3 enables agents that spawn child agents, allocate constrained budgets, communicate through typed channels, and execute dynamic task graphs — all under PACT governance.

## Brief Inventory

| Brief | Title                                                 | Scope                                                                | Priority        | Dependencies                      |
| ----- | ----------------------------------------------------- | -------------------------------------------------------------------- | --------------- | --------------------------------- |
| 00    | L0-L2 Remediation                                     | 5 blocking + 7 preparatory fixes                                     | BLOCKING prereq | None — must complete before L3    |
| 01    | EnvelopeTracker + EnvelopeSplitter + EnvelopeEnforcer | Runtime budget tracking, budget division, non-bypassable enforcement | Phase 1a        | 00 (blocking items)               |
| 02    | ScopedContext                                         | Hierarchical context scopes with projection-based access control     | Standalone      | None (can parallel with 01)       |
| 03    | Inter-Agent Messaging                                 | Typed, envelope-aware communication channels                         | Phase 1b        | 01 (EnvelopeEnforcer for routing) |
| 04    | AgentFactory + AgentInstanceRegistry                  | Runtime agent instantiation with lifecycle tracking                  | Phase 1c        | 01, 03                            |
| 05    | Plan DAG + PlanValidator + PlanExecutor               | Dynamic task graphs with verification gradient                       | Phase 2         | All of 01-04                      |

## Architectural Principles

1. **SDK boundary**: All L3 primitives are deterministic — no LLM calls. The orchestration layer (kaizen-agents) decides WHAT to do; the SDK validates and enforces.

2. **Monotonic tightening**: Children can never have more authority than their parents. This invariant pervades every primitive.

3. **Non-bypassable enforcement**: EnvelopeEnforcer cannot be disabled, paused, or bypassed at runtime.

4. **PACT integration**: Every governance event produces EATP records for audit traceability. The five PACT constraint dimensions (Financial, Operational, Temporal, Data Access, Communication) are enforced continuously.

5. **Cross-SDK alignment**: Both kailash-py and kailash-rs implement from the same specs independently. Semantics MUST match; idioms may differ.

## Scope Sizing

| Primitive                              | New types | New operations | Invariants | Test vectors | Estimated complexity |
| -------------------------------------- | --------- | -------------- | ---------- | ------------ | -------------------- |
| Remediation (00)                       | ~5        | ~12            | ~10        | ~5           | Medium               |
| EnvelopeTracker/Splitter/Enforcer (01) | 14        | 10             | 10         | 6            | High                 |
| ScopedContext (02)                     | 6         | 8              | 8          | 8+           | Medium-High          |
| Inter-Agent Messaging (03)             | 12+       | 7              | 9          | 7            | High                 |
| AgentFactory + Registry (04)           | 7         | 10             | 10         | 9+           | High                 |
| Plan DAG (05)                          | 10+       | 8+             | 15         | 12           | Very High            |
| **Total**                              | **~54**   | **~55**        | **~62**    | **~47**      | —                    |

## Key Decisions Already Made

| ID    | Decision                                                     | Rationale                                        |
| ----- | ------------------------------------------------------------ | ------------------------------------------------ |
| D-AC1 | Envelope on AgentConfig at SDK level, optional, None default | Single source of truth for agent constraints     |
| DP-1  | Harmonize checkpoint data model across languages BEFORE L3   | Plan-level checkpointing requires unified model  |
| DP-2  | ContextScope goes in SDK, both implementations               | Consistent scoping across delegation hierarchies |
| DP-3  | Extend existing MessageType enum (don't create parallel)     | Avoid type system fragmentation                  |
| DP-4  | Autonomy requirements folded into L3 specs (Rust builds own) | Python extends existing; Rust builds fresh       |
| DP-5  | Separate AgentInstance struct alongside AgentCard            | Static discovery vs. dynamic runtime lifecycle   |
