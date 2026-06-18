---
type: DISCOVERY
date: 2026-05-19
created_at: 2026-05-19T00:00:00Z
author: agent
session_id: f8-a3-implement
session_turn: 1
project: kaizen-rag-node-coverage
topic: A3 triage — R3 is a 3-layer stack (all 4 node-types exist); CLASS5 + a 2nd core gap fixed
phase: implement
tags: [f8, a3, r3, r4, class5, workflownode, mcp, triage, plan-amendment]
---

# DISCOVERY — A3 triage: R3 is a 3-layer stack, not a node-type-absence problem

## Context

`/implement` cycle 3, shard A3 — the R3/R4/CLASS5 triage shard. The approved
plan framed R3 (sub-workflow node references) as "NOT MECHANICAL,
UNBOUNDED-UNTIL-INVESTIGATED" and posed each of the 4 named node-types
(`CacheNode`, `SemanticChunkerNode`, `HierarchicalChunkerNode`,
`StatisticalChunkerNode`) as a `stale-rename` vs `genuinely-absent` unknown.

## What the investigation found

### R3 is bounded — and a 3-layer stack

The investigation collapses the uncertainty. **All 4 named node-types EXIST
in kailash core and are `@register_node()`-decorated** (chunkers in
`transform/chunkers.py`, `CacheNode` in `cache/cache.py`). Neither "stale
rename" nor "genuinely absent" — both plan options rejected.

R3 is instead a **3-layer stack**, each layer masking the next:

- **L1 — `WorkflowNode.workflow` gap.** `kailash.nodes.logic.workflow.
WorkflowNode` stores `self._workflow` but exposes no public `.workflow`
  property; rag code reads `workflow_node.workflow` → `AttributeError`. This
  is the FIRST failure — it precedes any registry error. Core gap, no rag
  B-shard owner.
- **L2 — lazy module cache.** `import kailash.nodes` does NOT fire the
  chunker/cache `@register_node()` decorators (lazy module cache); the rag
  string-references are correct, the registering modules are simply never
  imported. Fix = a registering import in the owning rag module.
- **L3 — stale `add_connection(route=…)`.** Once L1+L2 are applied, 3
  `workflows.py` classes hit `TypeError: add_connection() got an unexpected
keyword argument 'route'` — a pre-monorepo-move 3-arg API form; the current
  `WorkflowBuilder.add_connection` is strict 4-positional. 9 sites.

### CLASS5 — `process` is NOT a rename of `run`

Journal 0006 asked whether MCP `process()` is a stale alias of `run()`.
**It is not.** `process(inputs: dict)` is the MCP server's own per-tool
execution convention — `enhanced_server.py` reads and overrides `.process`.
The 2 MCP classes simply never implemented the abstract `Node.run`, leaving
them uninstantiable. CLASS5 is confined to those 2 core classes; rag is
unaffected.

## Decisions taken

1. **A3 fixes the 2 core gaps** (L1 `WorkflowNode.workflow` + CLASS5
   `MCPToolNode`/`MCPResourceNode.run`). Rationale: both are kailash-core
   gaps with no rag B-shard owner — the same class journal 0006 used to put
   CLASS5 in A3 scope. Branch `feat/f8-a3-core-fixes`, commits `9cc2eac55`
   (CLASS5) + `2eacf5a20` (`.workflow`). A3 owning both keeps the B-shards
   purely rag-coverage and avoids a cross-B-shard ordering dependency on a
   shared core fix.
2. **R3-L2 + R3-L3 + R4 + Pyright route to owning B-shards** — A3 produces
   the disposition (`01-analysis/04-A3-triage.md`), the B-shards apply the
   fix paired with behavioral coverage, per the approved plan's per-module
   shard structure. No OR-escape: each layer has one committed disposition.
3. **A3 does NOT un-mark the 6 rag `xfail(strict=True)` markers.** The plan
   scopes A3 as triage; the rag-side `_create_workflow()` fixes (L2/L3, R4)
   land in B-shards, so the **owning B-shard** un-marks its xfail. The
   smoke-test docstring (A2-authored) claimed "A3 removes the marks" — that
   prediction is corrected on `feat/f8-a3-core-fixes`.

## Consequences

- B7 (workflows+strategies) absorbs the most A3 amendment: R3-L2 (chunker
  import) + R3-L3 (9 `add_connection` rewrites) + strategies Pyright. Still
  one shard — L2/L3 are mechanical once the router-output→route mapping is
  read.
- Two pre-existing non-F8 surfaces became visible and are recorded in the
  triage doc (not silently dismissed):
  `test_workflow_node.py::test_error_workflow_execution_failure` (fails on
  `main` `208bcf166`, verified; workflow-error-propagation bug, separate
  shard) and `enhanced_server.py` Pyright import-noise (pre-existing
  MCP-middleware cleanup). Neither is an A3 regression.

## For Discussion

1. Counterfactual — had A3 only produced a disposition doc and routed CLASS5
   - L1 to B-shards, the first B-shard to run would have silently owned 2
     core fixes the others depend on. Does "A3 owns core fixes, B-shards own
     rag coverage" generalize as the rule for every triage shard that uncovers
     a core gap, or is it specific to F8's B-shard structure?
2. R3-L3's 9 `add_connection(route=…)` sites encode conditional routing from
   a router node. The current 4-arg `add_connection` expresses output→input
   wiring — does the router node already emit a per-route output port, or
   does B7 also need to confirm the router node's output schema before the
   rewrite is mechanical?
3. `test_error_workflow_execution_failure` has been red on `main` while
   #1100/#1101 merged green — confirming it is outside the blocking PR-gate.
   How many other integration tests are red-but-ungated, and should that set
   be swept independently of F8?
