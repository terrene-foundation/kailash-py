# L3 Plan DAG — Dynamic Task Graph Execution

## What It Is

Replaces rigid orchestration strategies with a dynamic, modifiable DAG. PlanValidator checks structure and envelope feasibility. PlanExecutor schedules nodes using PACT's verification gradient for failure handling.

## Key Components

- **Plan**: DAG of PlanNodes connected by PlanEdges
- **PlanValidator**: Structural + envelope validation (deterministic, no LLM)
- **PlanExecutor**: Gradient-driven scheduling with retry/hold/block
- **PlanModification**: 7 typed mutations for runtime plan changes

## Edge Types

| Type                 | Semantics                                                         |
| -------------------- | ----------------------------------------------------------------- |
| DataDependency       | `to` requires `from`'s output. Failure blocks downstream.         |
| CompletionDependency | `to` waits for `from` to finish (any outcome). For cleanup nodes. |
| CoStart              | Advisory co-start. Does not block.                                |

## Usage

```python
from kaizen.l3.plan import Plan, PlanNode, PlanEdge, PlanValidator, PlanExecutor, EdgeType

# Create plan
plan = Plan(name="code-review", envelope={"financial": {"max_cost": 1000}})
plan.add_node(PlanNode(node_id="analyze", agent_spec_id="analyzer", envelope={"financial": {"max_cost": 400}}))
plan.add_node(PlanNode(node_id="review", agent_spec_id="reviewer", envelope={"financial": {"max_cost": 400}}))
plan.add_node(PlanNode(node_id="report", agent_spec_id="reporter", envelope={"financial": {"max_cost": 200}}))
plan.add_edge(PlanEdge(from_node="analyze", to_node="review", edge_type=EdgeType.DATA_DEPENDENCY))
plan.add_edge(PlanEdge(from_node="review", to_node="report", edge_type=EdgeType.DATA_DEPENDENCY))

# Validate
errors = PlanValidator.validate(plan)  # [] if valid, Draft → Validated

# Execute with callback
def execute_node(node_id, spec_id):
    return {"result": f"done by {spec_id}"}

executor = PlanExecutor()
events = executor.execute(plan, node_callback=execute_node)
```

## Gradient Rules (G1-G8)

| Rule | Condition                       | Zone                                   |
| ---- | ------------------------------- | -------------------------------------- |
| G1   | Node completed                  | AutoApproved                           |
| G2   | Retryable failure, retries left | AutoApproved (retry)                   |
| G3   | Retries exhausted               | Held                                   |
| G4   | Non-retryable, optional         | Flagged (skip)                         |
| G5   | Non-retryable, required         | Held                                   |
| G6   | Budget at flag threshold (80%)  | Flagged                                |
| G7   | Budget at hold threshold (95%)  | Held                                   |
| G8   | Envelope violation              | **Blocked** (always, non-configurable) |

## Modifications (7 Types)

AddNode, RemoveNode, ReplaceNode, AddEdge, RemoveEdge, UpdateSpec, SkipNode

Batch atomic: `apply_modifications(plan, [mod1, mod2])` — all or nothing.

## Reference

- Spec: `workspaces/kaizen-l3/briefs/05-plan-dag.md`
- Source: `kaizen/l3/plan/`
