# A3 — R3 + R4 + CLASS5 triage & disposition (F8 Milestone A)

Phase: 03 `/implement`, shard A3 (investigation + 2 core fixes).
Branch base: `main` `208bcf166`. Core fixes branch: `feat/f8-a3-core-fixes`.
Consumes: `04-A0-r4-table.md` (R4 LEAK set), `03-reconciled-findings.md`
(R3 framing), journal 0005 (Pyright surface), journal 0006 (CLASS5 charter).
Produces: this disposition table + amended B-shard sizing. Per
`specs-authority.md` 5c the orchestrator amends B todos at `/implement`
launch from this doc.

Every verdict below is empirically reproduced against the project `.venv`
(Python 3.13) on `main` `208bcf166` + the `feat/f8-a3-core-fixes` branch.

---

## Summary of dispositions

| Class      | Finding                                                                                              | Disposition                             | Owner                          |
| ---------- | ---------------------------------------------------------------------------------------------------- | --------------------------------------- | ------------------------------ |
| R3-L1      | `WorkflowNode` exposes no public `.workflow` property                                                | **FIXED in A3** (core)                  | A3 — done                      |
| R3-L2      | 4 chunker/cache node-types referenced by string but unregistered                                     | registering import per owning module    | B7 (chunkers), B9c (CacheNode) |
| R3-L3      | `workflows.py` calls `add_connection(from, to, route=…)` — stale 3-arg form                          | rewrite 9 sites to canonical 4-arg form | B7                             |
| R4         | 4 single-brace f-string LEAKs, all `privacy.py`                                                      | 4× `{x}`→`{{x}}` escapes                | B9a                            |
| CLASS5     | `MCPToolNode`/`MCPResourceNode` abstract — no `run()`                                                | **FIXED in A3** (core)                  | A3 — done                      |
| Pyright    | ~40 pre-existing latent type defects in rag modules                                                  | per-module cleanup                      | per-module B-shard             |
| (surfaced) | `test_error_workflow_execution_failure` pre-existing fail; `enhanced_server.py` Pyright import-noise | recorded — NOT F8 scope                 | separate disposition           |

---

## R3 — sub-workflow node references: THREE layers

`03-reconciled-findings.md` framed R3 as "sub-workflow registry references …
NOT MECHANICAL, UNBOUNDED-UNTIL-INVESTIGATED". The investigation **collapses
the uncertainty**: R3 is bounded and mechanical, but it is a **3-layer stack**
— each layer masks the next until fixed.

### R3 finding — the 4 named node-types ALL EXIST and register correctly

The plan named 4 R3 node-types as `stale-rename` vs `genuinely-absent`
unknowns: `CacheNode`, `SemanticChunkerNode`, `HierarchicalChunkerNode`,
`StatisticalChunkerNode`. **Verdict: all 4 EXIST in kailash core and are
`@register_node()`-decorated** — none is absent, none is a stale rename:

| Node type                 | Defined at                                    | `@register_node()` |
| ------------------------- | --------------------------------------------- | ------------------ |
| `SemanticChunkerNode`     | `src/kailash/nodes/transform/chunkers.py:85`  | line 84            |
| `HierarchicalChunkerNode` | `src/kailash/nodes/transform/chunkers.py:12`  | line 11            |
| `StatisticalChunkerNode`  | `src/kailash/nodes/transform/chunkers.py:390` | line 389           |
| `CacheNode`               | `src/kailash/nodes/cache/cache.py:72`         | line 71            |

The rag string-references are CORRECT (`strategies.py:43/109/273`,
`optimized.py:147/213`). The plan's "stale string" / "genuinely absent"
options are both **rejected** — committed disposition is the third option
below (R3-L2).

### R3-L1 — `WorkflowNode.workflow` public-property gap → FIXED in A3

Before any registry error is reached, every `workflows.py` / `strategies.py`
class fails earlier. `kailash.nodes.logic.workflow.WorkflowNode` stores the
wrapped workflow as `self._workflow` (private) and exposes **no public
`.workflow` property and no `get_workflow()`**. The rag code accesses
`workflow_node.workflow` (e.g. `workflows.py:46`, `:536`, plus
`semantic_workflow.workflow` etc. inside `_create_advanced_workflow` /
`_create_adaptive_workflow`) → `AttributeError: 'WorkflowNode' object has no
attribute 'workflow'`.

This is a core gap with **no rag B-shard owner** — the same class as CLASS5
(core fix, no rag B-shard). Per the journal-0006 precedent (A3 owns core
fixes that unblock rag), **A3 fixes it**: a read-only `@property def
workflow(self) -> Workflow | None` added to `WorkflowNode`. Fixed on
`feat/f8-a3-core-fixes` commit `2eacf5a20`.

### R3-L2 — chunker/cache node-types not registered (lazy module cache)

`import kailash.nodes` does NOT populate the registry with the chunker/cache
node-types — `kailash/nodes/__init__.py` uses a **lazy module cache**
(`cache`, `transform` listed but lazily loaded). The `@register_node()`
decorators in `transform/chunkers.py` and `cache/cache.py` fire only when
those modules are actually imported. Empirically verified: after `import
kailash.nodes.transform.chunkers` the 3 chunker types resolve in
`NodeRegistry`; after `import kailash.nodes.cache.cache` so does `CacheNode`.

**Committed disposition (no OR-escape):** the owning rag module adds an
explicit registering import so the `@register_node()` decorator fires before
its `_create_workflow()` builds a workflow referencing the string.

- `strategies.py` (3 chunker refs) → **B7**: add
  `from kailash.nodes.transform import chunkers  # noqa: F401 — registers *ChunkerNode`.
- `optimized.py` (2 `CacheNode` refs) → **B9c**: add
  `from kailash.nodes.cache import cache  # noqa: F401 — registers CacheNode`.
- Dead commented-out imports `# from ..data.cache import CacheNode  # TODO`
  (`conversational.py:26`, `optimized.py:21`) — the `..data.cache` path never
  existed; **delete** both dead comments (conversational → B9b, optimized →
  B9c). `conversational.py` references no `CacheNode` string — comment only.

### R3-L3 — `workflows.py` stale `add_connection(route=…)` form

Once R3-L1 + R3-L2 are applied, `SimpleRAGWorkflowNode` and
`CacheOptimizedRAGNode` construct fully (verified). The other 3 workflows.py
classes — `AdvancedRAGWorkflowNode`, `AdaptiveRAGWorkflowNode`,
`RAGPipelineWorkflowNode` — hit a NEW error:
`TypeError: WorkflowBuilder.add_connection() got an unexpected keyword
argument 'route'`.

`WorkflowBuilder.add_connection(self, from_node, from_output, to_node,
to_input)` (`src/kailash/workflow/builder.py:565`) is a strict 4-positional
signature. `workflows.py` mixes two forms: the correct 4-arg form
(`workflows.py:189`) and a **stale `add_connection(from, to, route="…")`
3-arg form** (`workflows.py:192-195`, `:421`, `:425`, +; 9 `route=`
occurrences total). The `route=` form is a pre-monorepo-move API that
expressed conditional/switch routing.

**Committed disposition (no OR-escape):** → **B7**. Rewrite the 9
`route=`-form `add_connection` calls in `workflows.py` to the canonical
4-arg form `add_connection(router_id, <route-name>, target_id, "input")` —
the router/switch node's per-route output port IS the `from_output`. This is
behavioral-coverage work (fix the wiring AND assert the workflow runs); it
pairs naturally with B7's coverage of the workflow nodes.

### R3 layer → owning B-shard map

| Layer | Sites                                           | Owner         | Fix                                    |
| ----- | ----------------------------------------------- | ------------- | -------------------------------------- |
| L1    | `WorkflowNode.workflow` (core)                  | **A3 — DONE** | read-only property, commit `2eacf5a20` |
| L2    | `strategies.py` ×3 chunker refs                 | **B7**        | registering import                     |
| L2    | `optimized.py` ×2 `CacheNode` refs              | **B9c**       | registering import                     |
| L2    | dead `CacheNode` comment `conversational.py:26` | **B9b**       | delete dead comment                    |
| L2    | dead `CacheNode` comment `optimized.py:21`      | **B9c**       | delete dead comment                    |
| L3    | `workflows.py` ×9 `add_connection(route=)`      | **B7**        | rewrite to 4-arg form                  |

Post-L1+L2+L3, every workflows.py + optimized WorkflowNode constructs; deeper
per-node execution correctness is the owning B-shard's behavioral coverage.

---

## R4 — code-template f-string LEAKs (consume A0 verbatim)

`04-A0-r4-table.md` is the deterministic enumeration. **4 LEAKs, all
`privacy.py`** — A3 adds no new R4 investigation, only the owning-shard
assignment:

| LEAK row                              | Fix                             | Owner   |
| ------------------------------------- | ------------------------------- | ------- |
| `privacy.py:152` `{hash_value}`       | escape → `{{hash_value}}`       | **B9a** |
| `privacy.py:152` `{pii_type.upper()}` | escape → `{{pii_type.upper()}}` | **B9a** |
| `privacy.py:221` `{pattern}`          | escape → `{{pattern}}`          | **B9a** |
| `privacy.py:221` `{replacement}`      | escape → `{{replacement}}`      | **B9a** |

Two templates: `pii_detector` (`privacy.py:107`) and `query_anonymizer`
(`privacy.py:178`). Fixing the 4 escapes lets `PrivacyPreservingRAGNode`
construct past the `_create_workflow()` `NameError`. `strategies.py:240`
(`{fusion_method}`) is BENIGN per A0 (a function parameter, resolves at
build time) — NOT an R4 fix; A0 §"Adjudication" left a non-blocking
semantic note for B7 to consider, no LEAK count.

All 4 R4 LEAKs → **B9a**; no other module carries an R4 LEAK.

---

## CLASS5 — MCP `process()`/`run()` reconciliation → FIXED in A3

Per journal 0006, A3's charter was widened to resolve CLASS5. **Verdict:
`process` is NOT a stale rename of `run`.** `process(self, inputs: dict)` is
the MCP server's own per-tool/per-resource execution convention —
`enhanced_server.py` itself reads and overrides `.process`
(`enhanced_server.py:352-364`, `:394-404`: `tool_node.process =
custom_process`). `kailash.nodes.base.Node.run` is an `@abstractmethod`
(`def run(self, **kwargs)`), so `MCPToolNode`/`MCPResourceNode` — which
implement `process` but not `run` — were **abstract and uninstantiable**
(`MCPToolNode.__abstractmethods__ == frozenset({'run'})`).

**Disposition: A3 fixes it.** A `run(self, **kwargs) -> Dict` adapter added
to both classes bridges the Node-graph keyword contract to the MCP
`process(inputs)` convention (`return self.process(kwargs)`), preserving
`process` as the override point. Both classes now construct AND run. Fixed
on `feat/f8-a3-core-fixes` commit `9cc2eac55`. The
`xfail(strict=True)` test `test_mcp_tool_node_get_parameters_reads_config_bag`
(`tests/unit/mcp/test_server_enhanced.py`) is un-marked → real pass; a new
behavioral regression test asserts `run()` returns the `process` payload.

The rag package is unaffected — rag `Node`-subclasses implement `run()`
(confirmed: 0 `process`-only rag nodes); CLASS5 was confined to the 2
kailash-core MCP classes.

---

## Pyright — ~40 pre-existing latent defects (journal 0005)

Journal 0005 catalogued ~40 pre-existing latent Pyright defects across rag
modules, reviewer-confirmed pre-existing (cycle-1 gate, `git show
208bcf166:`). A3 routes them per-module to the owning B-shard's cleanup pass
(journal 0005 disposition item 2 — each B-shard cleans + covers its module):

| Module group            | Defect class (journal 0005)                                          | Owner               |
| ----------------------- | -------------------------------------------------------------------- | ------------------- |
| `similarity.py`         | `_create_workflow() -> Node` typed but returns `Workflow` (×6)       | B1                  |
| `query_processing.py`   | same return-type mismatch (`:231/429/665/941/1204/1385`)             | B8                  |
| `router.py`             | `self.name` attr-access (`:102` — base `Node` has no public `.name`) | B10                 |
| `strategies.py`         | `self.workflow` attr-access on a `Node` (`:193/199`)                 | B7                  |
| `realtime.py`           | return-type (`:371`); possibly-unbound `chunk_idx` (`:550`)          | B9c                 |
| `advanced.py`           | return-type (`:43`); possibly-unbound `content` (`:1556`)            | B6                  |
| `agentic.py`            | latent type noise                                                    | B3                  |
| unused-import (★) noise | per-module                                                           | each owning B-shard |

Each B-shard fixes its module's Pyright defects in-shard; none is an A1/A2
regression (all proven pre-existing). Note: the `similarity.py` /
`query_processing.py` `_create_workflow() -> Node` return annotations are
mis-typed — those methods return `Workflow`/`WorkflowNode`; the owning
B-shard corrects the annotation.

---

## Surfaced during A3 — pre-existing, NOT F8 scope (recorded, not dismissed)

A3's core-fix PR touches `tests/integration/nodes/test_workflow_node.py`
(added the `.workflow` regression test) and `enhanced_server.py`. Two
pre-existing surfaces became visible; both are recorded here so they are not
silently dismissed (`zero-tolerance.md` Rule 1a) — neither is an A3
regression and neither is F8/rag scope:

1. **`test_workflow_node.py::test_error_workflow_execution_failure`** fails
   on `main` `208bcf166` (verified: `git show 208bcf166:` of the test file
   reproduces the identical failure with all A3 changes absent). It is a
   workflow-error-propagation bug (`asyncio.get_running_loop()` "no running
   event loop" + result-shape mismatch) — a distinct bug class, not in the
   blocking PR-gate (`main` merged #1100/#1101 with it failing). **Disposition:
   surface to the user for a tracking issue; out of A3's shard budget
   (separate workflow-runtime shard).**
2. **`enhanced_server.py` Pyright import-noise** (`asyncio`, `json`, `List`,
   `PythonCodeNode`, `JSONReaderNode`, `SwitchNode`, `CacheManager`,
   `ConfigManager`, `MetricsCollector` unused; `__init__.py`
   `kailash.events` unresolved). All verified identical on `main` (A3's diff
   is +24 lines of `run` methods only). MCP-middleware Pyright surface, same
   class as the journal-0005 rag noise but no rag B-shard owns
   `enhanced_server.py`. **Disposition: pre-existing MCP-middleware cleanup;
   pre-commit/ruff (the enforced gate) is green; recommend folding into the
   next MCP-touching session — NOT F8/rag scope.**

---

## Amended B-shard sizing (per `specs-authority.md` 5c)

The orchestrator amends these B todos at `/implement` launch:

| B-shard                   | Plan scope            | A3 amendment                                                                                                                                                                                                      |
| ------------------------- | --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| B1 (similarity)           | 7 nodes, numpy T1+T2a | + fix 6 `_create_workflow() -> Node` return annotations                                                                                                                                                           |
| B6 (advanced)             | 4 nodes + A-S2        | + advanced.py return-type + possibly-unbound `content:1556`                                                                                                                                                       |
| B7 (workflows+strategies) | 8 nodes, T2b+T3       | **+ R3-L2 chunker registering import; + R3-L3 rewrite 9 `add_connection(route=)` sites; + strategies.py `self.workflow` Pyright (:193/199)** — largest A3 amendment; still one shard (8 nodes + mechanical L2/L3) |
| B8 (query_processing)     | 6 nodes               | + 6 `_create_workflow() -> Node` return annotations                                                                                                                                                               |
| B9a (privacy)             | 3 nodes               | + R4: 4 `{x}`→`{{x}}` escapes (A0 table)                                                                                                                                                                          |
| B9b (eval+conversational) | 5 nodes               | + delete dead `CacheNode` comment `conversational.py:26`                                                                                                                                                          |
| B9c (realtime+optimized)  | 7 nodes               | + R3-L2 `CacheNode` registering import; + delete dead comment `optimized.py:21`; + realtime return-type/`chunk_idx` Pyright                                                                                       |
| B10 (router)              | 4 nodes               | + router.py `self.name` attr-access Pyright (:102)                                                                                                                                                                |
| B2/B3/B4/B5               | unchanged             | per-module ★ unused-import noise only                                                                                                                                                                             |

B-shards B1–B10 remain within `autonomous-execution.md` per-session capacity
(≤7 classes, one infra class). B7 absorbs the most A3 work (L2 + L3 + Pyright)
but L2/L3 are mechanical once the router-output→route mapping is read; B7
stays a single shard.

---

## Done-criterion check (plan §A3)

- [x] Every R3 missing-node-type has a committed disposition mapped to an
      owning B-shard (L1 fixed in A3; L2/L3 → B7/B9b/B9c; no OR-escape).
- [x] Every A0 LEAK row has a committed disposition mapped to B9a.
- [x] CLASS5 resolved + verified (2 MCP classes instantiate; xfail un-marked
      to real pass).
- [x] B-shard sizes amended (table above).
- [x] Pyright surface routed per-module.

A3's 6 rag `xfail(strict=True)` markers in
`test_rag_resurrection_import_smoke.py` remain xfail — A3 routes the rag-side
fixes to B-shards; the **owning B-shard** un-marks each as it lands the fix
(smoke-test docstring corrected on `feat/f8-a3-core-fixes`).
