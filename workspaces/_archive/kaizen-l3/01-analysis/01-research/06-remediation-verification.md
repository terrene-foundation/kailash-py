# Remediation Verification — Python-Specific Findings

## Blocking Items (B1-B5): All Verified as Blocking

| Item | Status                 | Python-Specific Notes                                                                                                                                                          |
| ---- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| B1   | **Confirmed blocking** | `AgentConfig` at `kaizen/agent_config.py` has no envelope field. Adding `envelope: Optional[ConstraintEnvelopeConfig] = None` is non-breaking.                                 |
| B2   | **Confirmed blocking** | Python has checkpoint config in `AgentConfig` but needs harmonized data model. `parent_checkpoint_id`, `pending_actions`, `completed_actions`, `workflow_state` fields needed. |
| B3   | **Confirmed blocking** | No `ContextScope` exists in Python. Must build from scratch. `SharedMemoryPool` (tag-based filtering) is conceptual ancestor but not code-reusable.                            |
| B4   | **Confirmed blocking** | Python does not have a formal `MessageType` enum. L3 message types need to be defined as part of the A2A messaging module.                                                     |
| B5   | **Confirmed blocking** | No `AgentInstance` exists. Python has `AgentState` in autonomy subsystem but not the formal 6-state machine with transition validation.                                        |

## Preparatory Items: Python Applicability

| Item | Python Applicable? | Finding                                                                                                                                                                                                                                   |
| ---- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1   | **Partially**      | Python enums are inherently extensible. No `#[non_exhaustive]` equivalent needed. Document the contract that consumers should handle unknown variants.                                                                                    |
| P2   | **N/A**            | `RoutingCondition` does not exist in the Python codebase. This is a Rust-only issue. Skip for kailash-py.                                                                                                                                 |
| P3   | **N/A (likely)**   | `LlmDecision` does not appear as a routing strategy in Python. Only reference is in RAG workflows (different context). The Python orchestration module may not have this variant. Verify deeper during implementation.                    |
| P4   | **Verify**         | Python has `SupervisorAgent` in `orchestration/patterns/supervisor_worker.py`. Need to check if depth tracking uses shared state vulnerable to concurrent access. Python's GIL mitigates some races but async code may still be affected. |
| P5   | **Already done**   | `validate_dag()` in `composition/dag_validator.py` is already public (`__all__ = ["validate_dag"]`). Returns topological order. Uses DFS 3-color marking (not Kahn's — different algorithm, same result). Can be reused by PlanValidator. |
| P6   | **Applicable**     | Python A2A message types likely need metadata field. Verify during B4 implementation.                                                                                                                                                     |
| P7   | **N/A**            | Python classes are inherently extensible. No struct-level forward-compatibility annotation needed. Document construction contract.                                                                                                        |

## Python-Specific Implementation Notes

### DAG Validator Reuse

The existing `validate_dag()` function takes `List[Dict[str, Any]]` with `"name"` and `"inputs_from"` keys. For PlanValidator, we need to either:

1. Adapt PlanNode/PlanEdge to this input format, or
2. Extract the DFS cycle detection logic into a generic function that takes adjacency lists

Option 2 is cleaner — extract the algorithm, keep the existing function as a wrapper.

### Autonomy Subsystem Integration

Python has a rich autonomy subsystem (`core/autonomy/`) with control protocol, hooks, state management, permissions, interrupts, and observability. L3 should integrate with this rather than building parallel infrastructure:

- Use existing hooks for EATP record emission
- Use existing control protocol for agent lifecycle (pause/resume/terminate)
- Extend existing state management for the 6-state machine

### Supervisor Depth Tracking

The Python `SupervisorAgent` (`orchestration/patterns/supervisor_worker.py`) needs investigation for the same depth race condition described in P4. If depth is tracked per-instance (shared across concurrent calls), the same issue exists. Fix during remediation phase.
