# RISK: Stacking order resolution gates 50+ tasks

**Date**: 2026-04-08
**Phase**: 02 (todos)
**Trigger**: Red team RT-002 — no dependency edge from TASK-R2-003 to Phase 3

## Risk

TASK-R2-003 (resolve whether governance wraps cost, or cost wraps governance) is the single highest-leverage spec decision remaining. It cascades through:
- SPEC-03 §3.1 (wrapper stacking order) — 61 tasks
- SPEC-05 §3 (Delegate internal stack construction) — 44 tasks
- SPEC-10 (multi-agent patterns with wrapped agents) — 48 tasks
- All integration tests that verify wrapper composition

If an implementer starts Phase 3 before the order is decided, the wrong stacking means re-implementing MonitoredAgent, L3GovernedAgent, and the Delegate facade.

## Mitigation

TASK-R2-003 is now a **critical gate** blocking all Phase 3 and Phase 4 wrapper tasks. It must be resolved BEFORE `/implement` begins Phase 3.

The resolution is a spec-level decision (not code) — takes minutes, not sessions. The two options are clear:
- **Option A** (`BaseAgent → L3GovernedAgent → MonitoredAgent → StreamingAgent`): governance first, cost second. Rejected requests incur zero LLM cost.
- **Option B** (`BaseAgent → MonitoredAgent → L3GovernedAgent → StreamingAgent`): cost first, governance second. All requests are cost-tracked even if governance rejects them. Useful for cost auditing of governance overhead.

Recommend resolving this during the human approval gate of `/todos`.

## Impact if unmitigated

Full re-implementation of 3 wrapper classes + Delegate facade + all stacking tests. Estimated waste: 3-5 autonomous execution cycles.
