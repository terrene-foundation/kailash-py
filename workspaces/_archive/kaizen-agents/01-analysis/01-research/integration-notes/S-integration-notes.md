# Integration Notes — Milestone S (SDK Prerequisites)

## Discoveries

1. **PlanExecutor was installed from standalone repo** — `pip show kaizen-agents` showed editable install from `/Users/esperie/repos/kailash/kaizen-agents/`, not monorepo. Always verify install location with `python -c "import kaizen_agents; print(kaizen_agents.__file__)"`.

2. **PlanNodeState transitions use `transition_to()` method** — not direct assignment. The method validates against `_NODE_TRANSITIONS` dict. Adding HELD required updating both the enum AND the transitions dict.

3. **FAILED→HELD transition needed** — The executor transitions RUNNING→FAILED first (emits NodeFailed), then needs FAILED→HELD. This two-step is important: the failure event is distinct from the hold decision.

4. **AsyncPlanExecutor semaphore pattern** — `max_concurrency` parameter creates an `asyncio.Semaphore`. Each node execution acquires the semaphore in `_execute_node_guarded()`. This limits concurrent SDK operations (AgentFactory.spawn, MessageRouter.route) without limiting event processing.

5. **L3 **init**.py needs explicit additions** — Adding AsyncPlanExecutor to `kaizen/l3/plan/__init__.py` was not enough; also needed in `kaizen/l3/__init__.py` for top-level export.
