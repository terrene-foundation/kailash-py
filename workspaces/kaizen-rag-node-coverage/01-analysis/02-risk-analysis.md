# 02 — Risk Analysis (ADR-style)

Status: Proposed
Date: 2026-05-19
Workstream: F8 — deep behavioral coverage for `kaizen.nodes.rag` (58 node classes / 17 modules)
Inputs: `briefs/00-brief.md`, `01-analysis/01-research/01-node-surface-inventory.md`,
direct read of all high-risk `kaizen/nodes/rag/*.py` modules + `kailash.nodes.base`.

---

## Context

`kaizen.nodes.rag` was dead code from the 2026-03-11 monorepo move until the
kaizen 2.23.0/2.23.1 resurrection PR. That PR did exactly three things: repointed
broken relative imports to `kailash.*`, renamed one collision
(`StreamingRAGNode` → `RealtimeStreamingRAGNode`), and added an import-smoke
test. "Resurrected" today means **"the module imports and the `@register_node`
decorator runs"** — it does NOT mean any node's `run()` / `execute()` has ever
been called. F8 adds the first behavioral coverage.

The core question this analysis answers: **what is systematically broken in
code that imported clean but has never run, and how do we cover it without
mocking (Tier 2/3) given `[rag]` ships no LLM/vector backend?**

I read the actual source. The findings below cite specific sites. The headline
is not speculative: there is a **mechanical, package-wide instantiation bug**
that the import-smoke test structurally cannot see.

---

## Brief corrections (gate before /todos)

The inventory baseline is accurate. Two refinements from direct source reading:

1. **Inventory says "58 class defs / 55 `@register_node` / 56 `__all__`".** The
   gap is now explained, not just flagged:
   - `RAGConfig` (`strategies.py:21`) is a `@dataclass`, not a node — correctly
     in `__all__` (56) but correctly NOT `@register_node`-decorated. This
     accounts for 1 of the 56-vs-55 gap.
   - `RAGPipelineWorkflowNode` (`workflows.py:452`) IS `@register_node`-decorated
     and IS imported by `registry.py:30`, but is **absent from
     `rag/__init__.py::__all__`** (the package `__init__` imports only
     `AdaptiveRAGWorkflowNode, AdvancedRAGWorkflowNode, SimpleRAGWorkflowNode`
     — 3 of the 4 workflow nodes). This is an `orphan-detection.md` Rule 6
     finding (eagerly reachable via `registry` import, advertised nowhere in
     `__all__`). F8 must reconcile this, not just cover it.
   - Remaining class-def-vs-registered delta is the set of helper/base classes
     and the dataclass; the deep-dive per shard must enumerate exactly which 3
     `class` defs are not `@register_node` and confirm each is intentional.

2. **Brief/inventory imply per-class coverage is uniform work.** It is not.
   Two structurally distinct node families exist (see Risk R1): `Node`
   subclasses with a real `run()` body (pure-compute, e.g. `similarity.py`) vs
   `WorkflowNode` subclasses that build a kailash workflow in `__init__` and
   delegate execution to the SDK runtime (e.g. `graph.py`, `agentic.py`,
   `strategies.py` factories). These have completely different breakage
   surfaces and completely different infra needs. Sharding MUST split on this
   axis, not just on module-cluster.

---

## Decision

Adopt the risk-tiered coverage architecture below. Cover the package in
**value-anchored shards split on (node-family × infra-class)**, fix every
defect surfaced in-shard (BUILD repo, `zero-tolerance.md` Rule 4), and gate
the workstream on a per-shard real-infra disposition decided HERE — not
re-litigated per shard.

---

## 1. Behavioral-breakage risk surface (core finding)

A node importing clean proves: the module parses, every `class` body executes,
every `@register_node` decorator runs (including kailash's constructor-time
collision guard). It proves **nothing** about `run()` / `execute()` /
`__init__(...)` with real arguments. Code dead since 2026-03-11 has had ~2
months of `kailash.*` API evolution flow past it with zero compile-time or
test signal. The breakage clusters into four systematic classes.

### R1 — `super().__init__(name)` positional call into a `**kwargs`-only base (CRITICAL, package-wide)

This is the headline finding.

`kailash.nodes.base.Node.__init__` is `def __init__(self, **kwargs)`
(`src/kailash/nodes/base.py:339`) — **keyword-only, no positional `name`
parameter**.

Every `Node`-subclass RAG node calls the base constructor **positionally**:

- `similarity.py:81` — `super().__init__(name)` (`DenseRetrievalNode`)
- `similarity.py:218` — `super().__init__(name)` (`SparseRetrievalNode`)
- `similarity.py:500, 758, 1061, 1302, 1588` — same pattern, all 7
  `similarity.py` nodes
- `strategies.py:385` — `super().__init__(name)` (`SemanticRAGNode`); `:432`
  (`StatisticalRAGNode`); same for `HybridRAGNode:465`, `HierarchicalRAGNode:524`

`Node(**kwargs)` called as `Node(name)` raises
`TypeError: __init__() takes 1 positional argument but 2 were given` **at
instantiation**. The `@register_node` decorator registers the class object; it
does NOT instantiate it. The import-smoke test imports modules and asserts
registry membership — it **never constructs a node**. Therefore this
TypeError is invisible to the entire existing test surface and fires the first
time any behavioral test does `DenseRetrievalNode()`.

This is not a per-node bug — it is a **single API-drift pattern replicated
across every `Node` subclass in the package** (~30+ classes). The risk is not
"some nodes broken" — it is "the canonical instantiation path is broken
package-wide and no test has ever exercised it." Highest probability, highest
blast radius. (Caveat: kailash `Node` MAY accept a positional first arg via a
compatibility shim not visible in the `__init__` signature; the deep-dive MUST
verify by _instantiating one node_, not by re-reading the signature — this is
exactly the `verify-resource-existence.md` "cite the endpoint not the doc"
discipline applied to an API contract.)

### R2 — `WorkflowNode` constructor-signature drift (CRITICAL, ~20 classes)

The `WorkflowNode`-subclass family builds a kailash workflow at construction
time and passes it to `super().__init__`. The call shapes are **already
inconsistent within the package**, which is the tell that the contract drifted
and the code was never run against current kailash:

- `graph.py:106` — `super().__init__(name, self._create_workflow())`
  (positional name + positional workflow)
- `strategies.py:92` — `WorkflowNode(workflow=workflow, name=..., description=...)`
  (keyword form)
- `workflows.py:45` — `super().__init__(workflow=workflow_node.workflow,
name=name, description=...)` AND `workflows.py:42` reads
  `create_semantic_rag_workflow(config).workflow` — an attribute-shape
  assumption on the kailash `WorkflowNode` return object.

Three different `WorkflowNode.__init__` call conventions in three modules of
the same package = the contract is not pinned and at least two of the three
forms are likely wrong against kailash 2.23.0. `WorkflowNode.__init__` is at
`src/kailash/nodes/base.py:1765` (`def __init__(self, **kwargs)`) — same
keyword-only shape as `Node`, so `graph.py:106`'s positional
`super().__init__(name, workflow)` is the same R1 bug class at the WorkflowNode
layer. Construction happens in `__init__`, and `@register_node` does not call
`__init__`, so again: invisible to import-smoke, fires on first instantiation.
`graph.py` is highest-risk in this family (positional 2-arg call).

### R3 — String-node-type references that may no longer resolve (HIGH, workflow-building family)

The `WorkflowNode` family builds workflows via `builder.add_node("NodeTypeString", ...)`.
Every string is a late-bound reference into the kailash node registry,
resolved at `builder.build()` / runtime — NOT at import. Strings referenced:

- `strategies.py`: `"SemanticChunkerNode"`, `"EmbeddingGeneratorNode"`,
  `"VectorDatabaseNode"`, `"HybridRetrieverNode"`, `"StatisticalChunkerNode"`,
  `"PythonCodeNode"`, `"WorkflowNode"`
- `similarity.py`: `"LLMAgentNode"`, `"PythonCodeNode"`, `"EmbeddingGeneratorNode"`
- `graph.py` / `agentic.py`: `"LLMAgentNode"` + the above

Any of these that kailash 2.23.0 renamed, moved, or removed produces a
runtime `NodeConfigurationError`/registry-miss the moment `build()` runs —
which only happens in a behavioral test, never at import. `"VectorDatabaseNode"`,
`"HybridRetrieverNode"`, `"SemanticChunkerNode"` are the highest-suspicion
strings: RAG-specific node types most likely to have drifted or to require the
vector/embedding backends `[rag]` does not ship. This risk is **coupled to the
infra gap (§2)** — a string that resolves but whose node needs a live
embedding provider fails the same way behaviorally.

### R4 — Intra-kaizen import coupling beyond `kailash.*` (MEDIUM, narrows the "clean import" claim)

`graph.py:24` and `agentic.py:26` import `from ..ai.llm_agent import
LLMAgentNode` — an **intra-kaizen** import, not `kailash.*`. The resurrection
brief's "all imports repointed to `kailash.*`" is therefore incomplete: these
two modules' clean import also depends on `kaizen.nodes.ai.llm_agent` staying
stable. The import-smoke test does exercise this (it imports the modules), so
import-level this is GREEN today — but it means the rag package's behavioral
correctness is coupled to `kaizen.nodes.ai` evolution, a surface the brief
does not acknowledge. Lower probability (smoke test covers import), real
blast radius (an `LLMAgentNode` API change breaks graph/agentic behavior
silently).

### Highest-risk module clusters (ranked)

1. **`strategies.py` + `workflows.py` + `registry.py`** — R1 + R2 + R3 all
   present; `registry.py` instantiates strategy/workflow classes via
   `create_strategy()`/`create_workflow()` (`registry.py:361-407`), so the
   global `rag_registry = RAGWorkflowRegistry()` at module scope (`:547`) is
   one factory-call away from triggering R1/R2. Plus the
   `RAGPipelineWorkflowNode` `__all__` orphan.
2. **`graph.py`, `agentic.py`** — R2 (worst form: positional 2-arg
   `super().__init__`) + R3 + R4. `WorkflowNode` subclasses that build
   LLM-dependent workflows in `__init__`.
3. **`similarity.py`** — R1 across all 7 classes, but `run()` bodies are
   pure-compute (numpy/keyword overlap, no LLM/vector dep) — once R1 is fixed,
   these are the **cheapest to cover with real assertions** and the natural
   first shard.
4. **`realtime.py`** — R1 + async surface: `start_monitoring()` (`:373`),
   `_monitor_loop()` (`:383`, `asyncio.create_task`), `stream()` (`:465`,
   `AsyncIterator`). `patterns.md` § "Paired Public Surface — Consistent
   Async-ness" risk: a sync `run()` (`:528`, `:628`) coexisting with async
   `start_monitoring`/`stream` on the same class is exactly the
   event-loop-collision failure mode.

---

## 2. Infra-availability gap (per infra class — committed disposition)

`[rag]` = numpy, Pillow, networkx, requests, aiosqlite. **No LLM provider
client, no vector store.** Per `rules/testing.md` Tier 2/3 mocking is BLOCKED
and per `verify-resource-existence.md` "the disposition for an absent resource
is not 'mock it' and not 'silently skip'." Per `value-prioritization.md`
MUST-4 / the brief's "no OR-escape-hatch": each infra class gets ONE committed
disposition, decided here.

| Infra class                                                 | Nodes (examples)                                                                                                                                          | Disposition (committed)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Pure-compute** (numpy / keyword / networkx / Pillow only) | `similarity.py` (all 7), `graph.py` graph-traversal internals, multimodal image-matching that is pixel/Pillow-only                                        | **Tier 2 with real in-process execution, no backend.** These nodes' `run()` is deterministic Python over in-memory dicts. Real inputs, real outputs, real assertions. No infra needed beyond `[rag]`. This is the bulk of coverable behavior and the first shards.                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| **Embedding / vector-store-dependent**                      | anything routing through `"EmbeddingGeneratorNode"`, `"VectorDatabaseNode"`, `"HybridRetrieverNode"` (most of `strategies.py`, `workflows.py`)            | **Real lightweight backend via `aiosqlite` (already in `[rag]`) as the vector store + a deterministic local embedding.** kailash's embedding/vector nodes are configurable by provider; a real sqlite-backed vector path with a deterministic hash-embedding is a **real backend, not a mock** (it satisfies the protocol with deterministic output — explicitly the `testing.md` Protocol-Adapter carve-out). If kailash's `VectorDatabaseNode` cannot target sqlite, that is an SDK gap to fix in-shard (BUILD repo, Rule 4), not a reason to mock.                                                                                                                                                |
| **LLM-provider-dependent**                                  | `agentic.py` (ReAct loops), `graph.py` entity-extraction, `router.py` LLM routing, `query_processing.py` LLM rewrites, anything building `"LLMAgentNode"` | **Tier-1 contract-boundary test with a documented limitation, NOT a mock.** The behavioral contract that is _node-owned_ (workflow graph is built correctly: right nodes, right connections, right config) is verified by asserting the **built workflow structure** (`.build()` then inspect the graph) — a real structural assertion that needs no LLM. The LLM-output-dependent portion is explicitly out of behavioral scope and documented as such per `spec-accuracy.md` (state what ships, no split-state hand-waving — the limitation is a bounded `## Out of scope`, not a gap tracker). `.env` real-key LLM tests, if the user wants them, are a separately-anchored shard, not a default. |

**Recommendation per infra class, in one sentence each:**

- **Pure-compute:** real execution, full behavioral assertions, no infra — do
  these first (highest value/effort ratio, unblocks the R1 fix verification).
- **Embedding/vector:** real `aiosqlite` backend + deterministic local
  embedding (a Protocol adapter, not a mock); fix kailash if it can't target
  sqlite.
- **LLM-dependent:** assert the _built workflow structure_ (real, infra-free,
  node-owned contract) + bounded out-of-scope note for LLM-output behavior;
  real-key E2E only as a user-anchored separate shard.

This commits a disposition for every node. No node is "skipped." No node is
"mocked." Nodes whose only untested surface is third-party LLM output have
their _node-owned_ contract (graph construction) fully tested and their
non-node-owned surface explicitly bounded.

---

## 3. Workstream risks

### W1 — Scope exceeds many shards (HIGH)

58 classes × (R1 fix + R2 fix where applicable + behavioral test + edge cases)
≫ single-shard budget (`autonomous-execution.md`: ≤500 LOC load-bearing,
≤5–10 invariants, ≤3–4 call-graph hops). MUST decompose at `/todos`. Shard
axis = **(node-family × infra-class)**, not module alone:

- Shard A: `similarity.py` pure-compute (7 nodes, R1 fix + real assertions) —
  smallest, unblocks the R1-fix pattern for every later shard.
- Shard B: `strategies.py` + `registry.py` (R1 + R2 + factory instantiation +
  `RAGPipelineWorkflowNode` `__all__` reconciliation) — vector/sqlite infra.
- Shard C: `graph.py` + `agentic.py` (R2 worst-form + R4) — workflow-structure
  assertions.
- Shard D: `realtime.py` + `conversational.py` (async-surface risk).
- Shard E: `multimodal.py` + `federated.py` (Pillow / requests infra).
- Shard F: `privacy.py` + `evaluation.py` + `query_processing.py` + `router.py`
  - `optimized.py` + `advanced.py` (remaining).

Each shard carries its own value-anchor (per `value-prioritization.md` MUST-2)
deriving from the brief's success criterion "the RAG capability the user chose
to preserve is provably correct, not merely importable."

### W2 — "Add a test" silently becomes "fix the node" mid-shard (HIGH — flag for sharding)

This is correct behavior in a BUILD repo (`zero-tolerance.md` Rule 4 — fix the
defect, don't work around it; the brief's success criterion mandates it). But
R1 alone means **every shard's first action is a package-wide-pattern fix**,
not a test. The first behavioral test in Shard A will hit the R1 TypeError;
fixing it touches every `Node` subclass (~30 sites). That fix is itself a
shard-sized unit. **Sharding MUST budget the fix explicitly:** Shard A is
"fix R1 across the package + cover `similarity.py`", NOT "cover
`similarity.py`" — the R1 fix is the load-bearing logic, the tests are the
verification harness. Treating the R1 fix as incidental to a "just add tests"
shard overflows the invariant budget and produces the Phase-5.11 failure mode
(errors poison everything after, surface at /redteam). Per
`autonomous-execution.md` MUST Rule 4: R1 is one bug class, fits one shard,
fix it immediately and package-wide in Shard A — do NOT file 30 per-node
follow-ups.

### W3 — Regression risk to the existing import-smoke test (MEDIUM)

`test_rag_resurrection_import_smoke.py` asserts registry membership by class
name (`"GraphRAGNode" in NodeRegistry._nodes`, etc.) and the
`RealtimeStreamingRAGNode`/`StreamingRAGNode` collision split. The R1/R2 fixes
change `__init__` call sites but not class names or registration, so the smoke
test SHOULD stay green. **Risk:** if the R1 fix involves renaming or
re-decorating any class, or if reconciling `RAGPipelineWorkflowNode` into
`__all__` changes import order, the cross-module collision guard
(`test_rag_coexists_with_broader_kaizen_node_surface`) could re-fire. Mitigation:
the smoke test is the regression guard for the fix — run it after every shard's
R1/R2 changes, treat any smoke-test red as a blocking in-shard failure
(`zero-tolerance.md` Rule 1). NEVER weaken the smoke test to accommodate a fix.

### W4 — Version / CHANGELOG implications (MEDIUM — likely a minor bump, not patch)

The brief says "kaizen version bump + CHANGELOG if any node behavior is
corrected." Given R1 is package-wide, **node behavior WILL be corrected** (every
`Node` subclass currently cannot be instantiated; after the fix it can). This
is a behavior change from "raises TypeError" to "works" — that is a **feature-
level fix making the package functional**, paralleling the resurrection's own
2.22→2.23 minor-bump reasoning. Recommend planning for a **minor bump**
(2.23.x → 2.24.0) not a patch, with a CHANGELOG entry documenting "RAG nodes
are now instantiable and behaviorally covered." Per
`build-repo-release-discipline.md`: this is a BUILD repo; "done" = released to
PyPI + clean-venv import verified, NOT merged. The release obligation is part
of F8's definition of done and must be in the plan, not deferred.

### W5 — Missing end-to-end pipeline regression (HIGH — release gate)

Per `testing.md` § "End-to-End Pipeline Regression Above Unit + Integration"
and the analyst release-gate discipline: `rag/__init__.py` ships a "Quick
Start" docstring (lines 9-41) AND `registry.py:411` ships a
`get_quick_start_guide()` with copy-paste examples
(`registry.create_workflow("simple")`, `registry.create_strategy("semantic")`,
`semantic_rag.execute(documents=docs, operation="index")`). These ARE the
documented user journey. Unit + integration green per node is NOT the release
gate — a `tests/regression/test_rag_quickstart_*.py` that executes the
docstring/guide examples VERBATIM end-to-end is. **Absence of that regression
at /redteam is a HIGH finding regardless of per-node test counts** — it is the
only test that exercises the `registry → factory → WorkflowNode.__init__ →
build() → execute()` handoff chain where R1/R2/R3 compound. F8 owes this test;
the plan must name it as a discrete shard deliverable, not an afterthought.

---

## 4. Recommended risk-mitigations (each actionable)

| #   | Mitigation                                                                              | Actionable form                                                                                                                                                                                                                                                                                                       |
| --- | --------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M1  | **Verify R1 empirically before planning the fix**                                       | Shard A step 0: instantiate ONE node (`DenseRetrievalNode()`) in a throwaway test and capture the actual exception. Do NOT design the fix from re-reading `Node.__init__` — `verify-resource-existence.md` discipline: the runtime is the evidence, the signature is hearsay (a compat shim may exist).               |
| M2  | **Make R1 fix package-wide in Shard A, not per-node**                                   | One pattern, ~30 sites, one bug class, one shard (`autonomous-execution.md` MUST-4). Either fix every `super().__init__(name)` → `super().__init__(name=name)` (if base accepts kw `name`) OR fix the base if it should accept positional. Decide by M1's evidence. Land R1 fix + `similarity.py` coverage in one PR. |
| M3  | **Pin the `WorkflowNode` contract with a structural invariant test**                    | One Tier-2 test that builds a representative `WorkflowNode` subclass and asserts `.build()` produces the expected node set + connections. This is the R3 + R2 guard and is infra-free (`cross-sdk-inspection.md` § structural-invariant pattern).                                                                     |
| M4  | **Commit the per-infra-class disposition table (§2) into `02-plans/` before /todos**    | The disposition is decided HERE; shards execute it, they do not re-litigate "should we mock this." Prevents per-shard OR-escape-hatch drift (`value-prioritization.md` MUST-4).                                                                                                                                       |
| M5  | **Reconcile `RAGPipelineWorkflowNode` into `__all__` in the strategies/registry shard** | `orphan-detection.md` Rule 6 — eagerly reachable, advertised nowhere. Add to `rag/__init__.py` import + `__all__` in the same shard that covers it; update any `len(__all__)` assertion in the same commit.                                                                                                           |
| M6  | **Author the Quick Start end-to-end regression as a named shard deliverable**           | `tests/regression/test_rag_quickstart_executes_end_to_end.py` running the `__init__.py` docstring + `registry.get_quick_start_guide()` examples verbatim against the real sqlite/local-embedding backend. Release-gate per `testing.md`.                                                                              |
| M7  | **Treat the import-smoke test as the fix's regression guard, never weaken it**          | Run `test_rag_resurrection_import_smoke.py` after every shard's R1/R2 edits; smoke red = blocking in-shard failure (`zero-tolerance.md` Rule 1).                                                                                                                                                                      |
| M8  | **Plan the release into F8's definition of done**                                       | Minor bump (recommend 2.24.0), CHANGELOG entry "RAG nodes instantiable + behaviorally covered", PyPI publish + clean-venv import verify (`build-repo-release-discipline.md`). Not "merged = done."                                                                                                                    |
| M9  | **Audit the async surface in `realtime.py`/`conversational.py`**                        | `patterns.md` § Paired Public Surface — assert sync `run()` and async `start_monitoring`/`stream` don't collide under an active event loop; if they do, it is an in-shard fix (Rule 4).                                                                                                                               |

---

## Cross-reference audit

- **Documents affected:** `02-plans/` (must encode §2 disposition table + the
  6-shard split + R1-as-Shard-A-load-bearing); `01-research/01-node-surface-inventory.md`
  (the 58/55/56 gap is now explained — `RAGConfig` dataclass + `RAGPipelineWorkflowNode`
  `__all__` orphan; inventory should be annotated, not contradicted).
- **Inconsistencies found:** brief/inventory treat per-class coverage as
  uniform; it is bimodal (`Node` pure-compute vs `WorkflowNode` graph-builder)
  — corrected in "Brief corrections" §. Resurrection brief's "all imports
  repointed to `kailash.*`" is incomplete (intra-kaizen `..ai.llm_agent` in
  graph/agentic) — R4; not a defect (smoke covers it) but a scope correction.
- **No spec drift:** there is no `specs/` entry for `kaizen.nodes.rag` behavior
  yet; per `spec-accuracy.md` the spec is written AFTER code behavior is
  proven, so F8's coverage shards produce the domain truth a future
  `specs/rag-nodes.md` would describe — out of scope for this analysis, noted
  for the /codify phase.

## Implementation roadmap

Phase 1 (`/todos`): encode §2 disposition table + 6-shard split; Shard A =
"R1 package-wide fix + similarity.py coverage" (load-bearing fix, NOT just
tests). Human approval gate.
Phase 2 (`/implement`): Shard A → B → C in parallel waves of ≤3 worktrees
(`worktree-isolation.md` Rule 4); each shard fixes in-surfaced defects (Rule 4);
M3 structural-invariant + M6 quickstart-regression land as named deliverables.
Phase 3 (`/redteam`): re-derive coverage from scratch (`testing.md` audit
mode); the Quick Start end-to-end regression is the release gate; smoke test
must be green.
Phase 4 (release): minor bump + CHANGELOG + PyPI + clean-venv verify
(`build-repo-release-discipline.md`).

## Success criteria

- [ ] R1 empirically confirmed (M1) and fixed package-wide in one shard (M2);
      every `Node`/`WorkflowNode` subclass instantiable.
- [ ] Every one of the 58 classes has ≥1 behavioral test exercising its
      node-owned contract with real infra (no Tier-2/3 mocks).
- [ ] Per-infra-class disposition (§2) executed exactly as committed — zero
      mocks, zero silent skips, LLM-dependent nodes' graph-construction
      contract fully tested.
- [ ] `RAGPipelineWorkflowNode` reconciled into `__all__` (M5).
- [ ] Quick Start end-to-end regression green against real sqlite/local-embedding
      backend (M6).
- [ ] Existing import-smoke test still green after all fixes (M7).
- [ ] kaizen minor bump + CHANGELOG + PyPI publish + clean-venv import verified
      (M8).
- [ ] Coverage delta reported per shard (per brief success criteria).
