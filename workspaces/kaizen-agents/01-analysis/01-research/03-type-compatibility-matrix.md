# Type Compatibility Matrix: kaizen-agents Local → SDK

## Summary

| Category              | Count | Types                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| --------------------- | ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Direct Swap**       | 12    | DimensionGradient, WaitReason, TerminationReason, PlanNodeOutput, Priority, EscalationSeverity, SystemSubtype, ResourceSnapshot, StatusPayload, CompletionPayload, EscalationPayload, L3MessageType→MessageType                                                                                                                                                                                                                                                                     |
| **Needs Adapter**     | 17    | GradientZone (case), PlanGradient (timedelta→float), AgentSpec (envelope/memory dict), AgentState (enum→union), AgentInstance (state→union), EdgeType (case), PlanEdge (no default), PlanNode (spec→spec_id), PlanNodeState (case+HELD), PlanState (case), Plan (envelope/gradient→dict), PlanModification (enum→tag), PlanEvent (enum→tag), ClarificationPayload (blocking default), SystemPayload (None→""), L3Message→MessageEnvelope (structural), DelegationPayload (envelope) |
| **No SDK Equivalent** | 2     | ConstraintEnvelope, MemoryConfig — keep as orchestration-specific types                                                                                                                                                                                                                                                                                                                                                                                                             |

## Critical Differences

1. **Enum casing**: Local lowercase ("auto_approved") vs SDK UPPERCASE ("AUTO_APPROVED") — affects GradientZone, EdgeType, PlanNodeState, PlanState
2. **Time types**: Local `timedelta` vs SDK `float` (seconds) — PlanGradient.resolution_timeout, AgentSpec.max_lifetime, L3Message.ttl
3. **PlanNode.agent_spec vs agent_spec_id**: Local stores full AgentSpec, SDK stores only spec_id string
4. **Plan.gradient**: Local `PlanGradient` dataclass vs SDK `dict[str, Any]`
5. **AgentState**: Local simple enum vs SDK discriminated union with payload
6. **L3Message vs MessageEnvelope**: Local discriminated union with 6 payload fields vs SDK transport wrapper with single polymorphic payload

## Adapter Strategy

Given the extensive differences, the correct approach is NOT to delete types.py and import SDK types directly. Instead:

1. **Keep ConstraintEnvelope and MemoryConfig** as orchestration-specific types (no SDK equivalent)
2. **Create `_sdk_compat.py`** with bidirectional adapter functions
3. **Internal code continues using local types** for construction and manipulation
4. **Convert to SDK types at integration boundaries** (when calling SDK APIs)

This approach:

- Minimizes test rewrites (tests continue using local types)
- Isolates SDK coupling to adapter layer
- Allows gradual migration as SDK types evolve
- Follows the "orchestration layer adds structure" principle
