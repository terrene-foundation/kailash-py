# 04 — Red-Team Analysis of 03-reconciled-findings.md (F8 plan-input)

Adversarial empirical audit. Every claim falsified or confirmed with command
output against `.venv` (kaizen 2.23.1 editable + kailash 2.23.0) on `main`
`0f906a1e0`, 2026-05-19. Source of truth: instantiation of every class, not
re-reading the doc.

**VERDICT: BLOCK** — the three-class R1/R2/R3 split is empirically incomplete
(a 4th construction-failure class exists and is widespread-but-masked), one
load-bearing root-cause claim is false, and the R3 "unbounded" framing is
actually bounded at a small number this audit pins. Findings below MUST be
folded into the analysis before `/todos`.

Finding count: **2 CRIT, 4 HIGH, 3 MED, 2 LOW (confirmations)**.

---

## Mission 1 — R1/R2/R3 generalization across all modules (per-module table)

Representative class per module = first `Node`-subclass that is NOT a
`WorkflowNode` subclass; if none, first `WorkflowNode` subclass; if none, first
class. `WorkflowNode` lives at `kailash.nodes.logic.workflow` (the doc's
`src/kailash/nodes/base.py:1765` reference is stale — see Mission 6 MED-2).
Construction = no-arg `Cls()`.

| Module           | Representative class          | MRO base     | Construction result                                                               |
| ---------------- | ----------------------------- | ------------ | --------------------------------------------------------------------------------- |
| advanced         | `SelfCorrectingRAGNode`       | Node         | **TypeError-R1** `Node.__init__() takes 1 positional argument but 2 were given`   |
| agentic          | `ToolAugmentedRAGNode`        | Node         | **TypeError-R1**                                                                  |
| conversational   | `ConversationMemoryNode`      | Node         | **TypeError-R1**                                                                  |
| evaluation       | `RAGBenchmarkNode`            | Node         | **TypeError-R1**                                                                  |
| federated        | `EdgeRAGNode`                 | Node         | **TypeError-R1**                                                                  |
| graph            | `GraphBuilderNode`            | Node         | **TypeError-R1**                                                                  |
| multimodal       | `VisualQuestionAnsweringNode` | Node         | **TypeError-R1**                                                                  |
| optimized        | `CacheOptimizedRAGNode`       | WorkflowNode | **WorkflowValidationError-R3** `Node 'CacheNode' not found in registry`           |
| privacy          | `PrivacyPreservingRAGNode`\*  | WorkflowNode | **CLASS4** `NameError: name 'pii_type' is not defined` (4TH CLASS — see CRIT-1)   |
| query_processing | `QueryExpansionNode`          | Node         | **TypeError-R1**                                                                  |
| realtime         | `RealtimeStreamingRAGNode`    | Node         | **TypeError-R1**                                                                  |
| registry         | `RAGWorkflowRegistry`         | object       | **OK** (constructs no-arg)                                                        |
| router           | `RAGStrategyRouterNode`       | Node         | **TypeError-R1**                                                                  |
| similarity       | `DenseRetrievalNode`          | Node         | **TypeError-R1**                                                                  |
| strategies       | `SemanticRAGNode`             | Node         | **TypeError-R1**                                                                  |
| workflows        | `SimpleRAGWorkflowNode`       | WorkflowNode | **WorkflowValidationError-R3** `Node 'SemanticChunkerNode' not found in registry` |

(\*) privacy's first Node-subclass `SecureMultiPartyRAGNode` is R1; the module's
flagship `PrivacyPreservingRAGNode` is the CLASS4 case (shown because it is the
finding). 16 code modules (the doc says "17 modules"; the 17th is `__init__.py`
which is not a node module — minor count framing, see Mission 2).

**Full 58-class instantiation histogram** (every class, not representatives):

```
OK     (3):  advanced.RAGConfig, registry.RAGWorkflowRegistry, strategies.RAGConfig
R1    (39):  super().__init__(name) → Node.__init__() takes 1 positional but 2
R2    (10):  WorkflowNode.__init__() takes from 1 to 2 positional but 3
R3     (5):  WorkflowValidationError — Node '<X>' not found in registry
CLASS4 (1):  privacy.PrivacyPreservingRAGNode — NameError: name 'pii_type' is not defined
TOTAL  58
```

### CRIT-1 — A 4th construction-failure class exists AND is structurally widespread-but-masked

`privacy.PrivacyPreservingRAGNode()` does NOT raise R1/R2/R3. It raises
`NameError: name 'pii_type' is not defined` from **inside `_create_workflow()`,
before `super().__init__` is ever reached**:

```
File ".../rag/privacy.py", line 96, in __init__
    super().__init__(name, self._create_workflow())
File ".../rag/privacy.py", line 152, in _create_workflow
    replacement = f"[{pii_type.upper()}_{hash_value}]"
                      ^^^^^^^^
NameError: name 'pii_type' is not defined
```

Root cause (read of `privacy.py:107-153`): the node builds a `PythonCodeNode`
whose `code=` is an **outer f-string** (`"code": f"""..."""` at :107). Every
brace meant to be literal Python-in-the-generated-code is correctly doubled
(`{{`, `}}` at :117, :120, :127, :145). Line 152 — `f"[{pii_type.upper()}_{hash_value}]"`
— was left **single-braced**, so Python interpolates `pii_type` / `hash_value`
at workflow-construction time (the builder's scope, where they do not exist)
instead of emitting them as literal text into the generated PythonCodeNode body.
This is a deterministic construction-time bug, NOT "needs infra", NOT R1/R2/R3.

Why this is CRIT, not a one-off: `code=f"""..."""`-templated PythonCodeNode
blocks exist in **conversational, evaluation, federated, multimodal, optimized,
privacy, realtime, similarity, strategies, workflows** (grep: every Shape-W
module has ≥1 `f"""` code block). `PrivacyPreservingRAGNode` is merely the
**first node to surface CLASS4**, because its `super().__init__(name,
self._create_workflow())` evaluates `_create_workflow()` as a super() argument
— so the f-string leak fires before the R2 signature error. For every other
Shape-W node, R1/R2 fires FIRST and **masks** any latent same-class
f-string-template bug. The reconciled doc's own §02-risk W2 cites the
Phase-5.11 failure mode ("errors poison everything after, surface at
/redteam"); CLASS4 IS that failure mode pre-loaded into this workstream: the
Shard-A1/A2 R1/R2 fix will **unmask an unknown count of CLASS4 bugs** the doc
does not budget for. The three-class split is not just incomplete — it hides
the highest-risk Shard-A surprise.

Disposition required in the analysis: add R4 = "f-string code-template
interpolation leak (single-brace `{var}` inside `code=f\"\"\"...\"\"\"`)"; state
that R1/R2 fixes UNMASK R4; mandate a mechanical grep audit
(`code=f"""` blocks with single-brace `{...}` that is not `{{`/`}}`) as a
Shard-A0 pre-flight, not a /redteam afterthought.

---

## Mission 2 — Count integrity

| Claim (doc)                | Verified                         | Method                                     | Verdict         |
| -------------------------- | -------------------------------- | ------------------------------------------ | --------------- |
| 58 `class X` defs          | **58**                           | `grep -hcE '^class ' *.py` summed          | ✅ CONFIRMED    |
| 55 `@register_node`        | **55**                           | `grep -hcE '^@register_node'` summed       | ✅ CONFIRMED    |
| 56 `__all__`               | **56**                           | `ast.parse` `len(__all__.elts)`            | ✅ CONFIRMED    |
| ~38 R1 sites               | **38** `super().__init__(name)`  | grep; **39** classify as R1 on instantiate | ✅ (see MED-1)  |
| 17 WorkflowNode subclasses | not separately reverified here   | —                                          | ⚠️ (see HIGH-3) |
| 3 non-node (`object`)      | **3** (2× RAGConfig + Registry)  | instantiation: OK bucket = exactly 3       | ✅ CONFIRMED    |
| "17 modules"               | **16 code modules** + `__init__` | `pkgutil.iter_modules`                     | ⚠️ MED-3        |

### MED-1 — "~38 R1" is grep-count 38 but instantiation-classified 39

`grep -c 'super().__init__(name)'` = 38. But classifying every one of the 58
classes by its actual construction exception gives **R1 = 39**. The doc's "~38"
hedge technically covers it, but the exact number is 39 and the doc should pin
it (the grep undercounts by one because one R1-classified class reaches the
`Node.__init__() takes 1 positional but 2` error via a call shape the
`super().__init__(name)` literal grep misses). Not blocking on its own;
folded into the BLOCK because the doc presents 38 as authoritative for Shard-A1
sizing.

### MED-3 — "17 modules" vs 16 code modules

`pkgutil.iter_modules(kaizen.nodes.rag)` enumerates exactly **16** non-`__init__`
modules (advanced, agentic, conversational, evaluation, federated, graph,
multimodal, optimized, privacy, query_processing, realtime, registry, router,
similarity, strategies, workflows). The doc and both contract docs say "17
modules" — the 17th is `__init__.py`, which registers no node. The S5
import-smoke-expansion shard ("assert ALL 17 modules import") will assert 16
node modules; the off-by-one is harmless to the smoke gate but the plan text
should say 16.

---

## Mission 3 — Is R1 really mechanical / single-uniform-pattern?

**Falsified — the doc's "One pattern, ~38 sites" is two patterns, ~38 + ~13
sites.** `super().__init__` call-shape census across `rag/*.py`:

```
38×  super().__init__(name)                       ← the doc's R1
13×  super().__init__(name, self._create_workflow())   ← NOT modelled as a distinct shape
```

The 13 `name, self._create_workflow()` sites span 9 modules (agentic 2,
conversational 1, evaluation 1, federated 1, graph 1, multimodal 1, optimized 4,
privacy 1, realtime 1). The fix shapes are structurally DIFFERENT:

- R1 `super().__init__(name)` → `Node.__init__(**kwargs)`: route `name` through
  the kwargs contract. ~mechanical.
- `super().__init__(name, workflow)` → `WorkflowNode.__init__(workflow=None, **kwargs)`:
  the **second positional arg is a workflow OBJECT** that has no home in a
  `name`→kwargs rewrite. The fix is `super().__init__(workflow=<wf>, name=name, ...)`
  — a different edit, and it only works if `_create_workflow()` itself succeeds
  (which for privacy it does NOT — CLASS4; for the R3 set it raises
  WorkflowValidationError).

Read of 4 `__init__` bodies confirms divergence beyond the two super-shapes:

- `similarity.DenseRetrievalNode:72-81` — stash 3 attrs, `super().__init__(name)`,
  overrides `get_parameters()`. Uniform.
- `strategies.SemanticRAGNode:382-385` — `self.config`, `self.workflow_node=None`,
  `super().__init__(name)`. Uniform-ish.
- `advanced.SelfCorrectingRAGNode:59-71` — 5 attrs incl `self.base_rag_workflow=None`,
  `super().__init__(name)`. Note: `advanced.RAGConfig:32` is **already
  `def **init**(self, **kwargs)`\*\* — a third shape (kwargs-native, in the OK bucket).
- `evaluation.RAGBenchmarkNode:90-105` — `super().__init__(name, self._create_workflow())`
  on a class the contract doc labels `Node`/`CONSTRUCTION=PURE_COMPUTE`. It is
  the name+workflow shape, NOT bare-name.

`kailash.nodes.base.Node.__init__` has a `__init_with_capture` wrapper
(`src/kailash/nodes/base.py:282-304`) that **post-hoc captures subclass
`__init__` bound-args into `self.config` AFTER `original_init` returns**. So the
R1 fix is not merely "pass name as kwarg" — the chosen rewrite MUST keep the
capture wrapper's `self.config` population intact (the wrapper reads `hasattr(self,
"config")` and back-fills). A naive `super().__init__(name=name)` may interact
with the capture wrapper differently than the contract doc assumes; the analysis
calls R1 "MECHANICAL, BOUNDED" without acknowledging the capture-wrapper
contract or the 38-vs-13 shape split.

### HIGH-1 — Shard A1 is under-scoped: two fix shapes + capture-wrapper contract, not "one pattern, ~38 sites"

The analysis sizes Shard A1 as "R1 (≈38 Node subclasses) — MECHANICAL,
BOUNDED ... One pattern, ~38 sites." Empirically it is: 38 bare-name sites +
13 name+workflow sites (the doc's "R2" but the doc never enumerates them and
calls the count "subset of 17 — enumerate before fixing"), with a
`__init_with_capture` config-population contract neither contract doc cites.
Under-estimating Shard A1 is exactly the "highest-impact error to catch" the
mission flagged. The analysis MUST: (a) state the 38 + 13 split with the
9-module distribution, (b) cite the `__init_with_capture` wrapper as the real
post-fix invariant, (c) re-classify which "R1" classes are actually the
name+workflow shape (RAGBenchmarkNode, etc. — the contract docs' Node-vs-WFN
labels are unreliable here).

---

## Mission 4 — R3 unboundedness (sizing Shard A3, a number not "unbounded")

**The doc's R3 framing "NOT MECHANICAL, UNBOUNDED-UNTIL-INVESTIGATED" is
falsified — R3 is bounded.** Distinct node-type strings referenced via
`.add_node("...Node", ...)` in the Shape-W builder files:

```
15 distinct *Node-typed strings; 11 resolve in registry, 4 ABSENT
PRESENT (11): EmbeddingGeneratorNode HybridRAGNode HybridRetrieverNode
              LLMAgentNode PythonCodeNode QueryIntentClassifierNode
              SemanticRAGNode SparseRetrievalNode SwitchNode
              VectorDatabaseNode WorkflowNode
ABSENT  (4):  CacheNode  HierarchicalChunkerNode  SemanticChunkerNode
              StatisticalChunkerNode
```

**Shard-A3 distinct-missing-node-type number = 4.** Not "unbounded" — four
named strings. Of these, the brief acknowledges `CacheNode` (and the contract
docs cite `SemanticChunkerNode`); **`HierarchicalChunkerNode` and
`StatisticalChunkerNode` are NOT mentioned anywhere in the reconciled doc or
either contract doc — two NEW R3 findings** this audit surfaces.

### HIGH-2 — The 11 "PRESENT" R3 refs are mostly rag's OWN R1-broken nodes (circular dependency the doc misses)

Splitting "PRESENT" by registration source (kailash core registry snapshot
BEFORE importing kaizen.rag, vs. after):

```
CORE-kailash (3):       PythonCodeNode  SwitchNode  WorkflowNode
rag-self R1-broken (8):  EmbeddingGeneratorNode HybridRAGNode HybridRetrieverNode
                         LLMAgentNode QueryIntentClassifierNode SemanticRAGNode
                         SparseRetrievalNode  (+ HybridRAGNode)
```

Only **3 of 15** sub-workflow node-type strings resolve to genuinely-working
kailash-core nodes. 8 "resolve" only because rag registered them itself — and
those classes are R1-broken, so at sub-workflow execute time they fail to
instantiate. This is a **third R3 sub-case the doc's two-way "stale string vs
genuinely absent" split misses**: "string resolves to rag's OWN broken node."
It also means R3 cannot even be enumerated/triaged until R1 is fixed (the
registry entries are R1-broken classes) — so Shard A3's investigation is
**gated on Shard A1**, a sequencing constraint the analysis does not state
(it lists A1/A2/A3 as if independently shardable).

Net Shard-A3 sizing the analysis should adopt: 15 distinct strings; 4 genuinely
absent (2 brief/contract-acknowledged + 2 NEW: HierarchicalChunkerNode,
StatisticalChunkerNode); 8 resolve-to-self-broken (auto-fixed by Shard A1);
3 resolve-to-core (OK). Bounded, A1-gated. NOT "unbounded judgement call."

---

## Mission 5 — specs/ disposition soundness (spec-accuracy.md Rule 5)

**Confirmed sound — the deferral is rule-aligned, not a violation dressed as
compliance.** Verified: `specs/` exists at project root; `specs/_index.md` has
a Kaizen section with 14 `kaizen-*.md` files; **no `kaizen-rag.md` and no rag
row in the Kaizen section** (grep `rag` in `_index.md` Kaizen rows = empty).

`spec-accuracy.md` Rule 5 ("Incremental Spec Extension Is The Workflow"):
_"Spec content describes ONLY behavior already shipped on `main`. A PR that
adds spec content without corresponding code on `main` is BLOCKED."_ RAG
behavior on `main` provably raises `TypeError`/`NameError`/`WorkflowValidationError`
at construction (Missions 1, 3). Authoring `specs/kaizen-rag.md` now would
describe behavior that does not execute — a phantom spec, exactly Rule 5's
BLOCKED case and Rule 1's "every citation resolves against working code."

The doc's disposition — "authored INCREMENTALLY, code-first — each fix+coverage
shard appends the spec section for the nodes it makes provably-correct, in the
SAME shard" — is the textbook Rule 5 + `specs-authority.md` Rule 5 workflow
("code first, spec describes what landed"). Adversarial check for the
disguised-violation pattern: the doc does NOT create a gap-tracker, does NOT
use a Phase-1/Phase-2 split-state framing, does NOT add a `## Out of scope (for
now)` tracker — it defers spec _origination_ to post-code, which is precisely
what Rule 5 mandates. **No finding. The disposition is correctly rule-aligned.**
One nit (LOW-1): the doc should name the eventual file `specs/kaizen-rag.md`
AND add the `_index.md` Kaizen-section row in the SAME shard that authors the
first section (per `specs-authority.md` Rule 1, every spec file in `_index.md`).

---

## Mission 6 — What else the analysis missed

### CRIT-2 — The doc's root-cause claim "0 super().**init**(name) sites outside /rag/" is FALSE

The doc's "dominant fact" section asserts the root cause is rag-local: _"NOT a
kailash regression (0 `super().__init__(name)` sites outside `/rag/`)."_
Empirically:

```
$ grep -rn 'super().__init__(name)' src/kailash/
src/kailash/middleware/mcp/enhanced_server.py:72:   super().__init__(name)  # type: ignore[call-arg]
src/kailash/middleware/mcp/enhanced_server.py:125:  super().__init__(name)  # type: ignore[call-arg]
```

`MCPToolNode(Node)` (:62) and `MCPResourceNode(Node)` (:115) in
`src/kailash/middleware/mcp/enhanced_server.py` carry the **identical R1 bug
pattern** — `super().__init__(name)` into the kwargs-only `Node.__init__` —
PLUS a `# type: ignore[call-arg]` comment that proves an author already knew the
call was type-incorrect and suppressed the checker rather than fixing it. This
does not change the rag fix work, but it **falsifies a load-bearing framing
claim**: R1 is NOT rag-local; it is a kailash-core bug class with ≥2 live sites
in `src/kailash/`. The analysis builds its "rag-local code frozen since
2026-03-11; NOT a kailash regression" narrative on this false premise. Per
`cross-sdk-inspection.md` and `zero-tolerance.md` Rule 1 ("if you found it, you
own it"), the 2 enhanced_server.py sites are in-scope same-bug-class fixes the
analysis must acknowledge, not a separate concern. BLOCKING because the
inaccurate root-cause framing propagates into the plan's "this is purely a
rag-resurrection-debt problem" scoping.

### HIGH-3 — Construction-failure surfaces FIRST; R3 is masked behind R1/R2 for most WorkflowNodes (sequencing the analysis treats as parallel)

Only **5 classes** reach R3 (`WorkflowValidationError`) at construction:
`optimized.CacheOptimizedRAGNode`, `workflows.{Simple,Advanced,Adaptive,RAGPipeline}*`.
All build their sub-workflow as a `super().__init__(name, self._create_workflow())`
argument, so the sub-workflow build runs before the super signature check. The
OTHER ~17 Shape-W nodes raise R2 (`WorkflowNode.__init__() takes 1 to 2
positional but 3`) FIRST — their R3 sub-workflow defects (stale strings,
absent node-types) are **invisible until R2 is fixed**. The analysis lists
Shard A1, A2, A3 as if independently plannable; empirically **A3 (R3 triage)
is strictly gated on A1+A2** because R3 only becomes observable once
construction succeeds. The plan must encode this dependency edge or A3 will be
re-derived mid-`/implement` (the exact `autonomous-execution.md` "defer
sharding to /implement is BLOCKED" anti-pattern).

### HIGH-4 — `advanced.create_hybrid_rag_workflow` is provably broken with certainty, not "may not exist" (S2 escalation)

The contract doc (02 §S2) and reconciled doc say `from ...workflow.graph import
Workflow` "resolves to `kaizen.workflow.graph.Workflow`" and "may not exist."
Empirically it is **certain**:

```
$ .venv/bin/python -c "from kaizen.workflow.graph import Workflow"
ModuleNotFoundError: No module named 'kaizen.workflow'
```

`advanced.py:38-45` `create_hybrid_rag_workflow()` body imports a module that
does not exist; its docstring says verbatim _"return a simple mock workflow"_
(a `zero-tolerance.md` Rule 2 shipped-placeholder — the reconciled doc DOES
flag this, correctly). The 4 advanced nodes (`SelfCorrectingRAGNode`,
`RAGFusionNode`, `HyDENode`, `StepBackRAGNode`) have a 100%-certain
`ModuleNotFoundError` on `run()`, not a "may." The analysis should state it as
certain (it currently inherits the contract doc's "may not exist" hedge), which
upgrades these 4 from "investigate" to "known in-shard SDK fix" and tightens
the broken-fix shard estimate.

### Mission 6 negative results (clean — no finding, recorded for completeness)

- **All 16 code modules import cleanly** (`importlib.import_module` each → OK).
  S5's "import-breakage risk on untested modules" is empirically NOT present
  today; the doc hedges S5 as "unverified" but it is verifiable-now and clean.
  The S5 import-smoke-expansion shard remains valuable as a regression guard
  but its framing should change from "may be broken" to "currently clean, pin
  it."
- **All 55 `@register_node` classes ARE Node subclasses** — zero decorated
  non-Node classes. (Mission 6 hypothesis negative.)
- **`kaizen.nodes.rag.__init__` imports cleanly; all 56 `__all__` names
  attribute-resolve.** No circular intra-rag import. (Mission 6 hypotheses
  negative.)
- `RAGPipelineWorkflowNode` `__all__`-orphan **confirmed**: decorated +
  in `NodeRegistry` + `RAGPipelineWorkflowNode in __all__ == False`. The doc's
  `orphan-detection.md` Rule 6 finding is accurate.
- `registry.py:547 rag_registry = RAGWorkflowRegistry()` module-scope
  singleton **confirmed** — the doc's import-smoke claim is accurate.

### MED-2 — Stale citation: `WorkflowNode.__init__` is NOT at `src/kailash/nodes/base.py:1765`

The 02-risk doc R2 cites `WorkflowNode.__init__` at
`src/kailash/nodes/base.py:1765`. `WorkflowNode` is defined at
`src/kailash/nodes/logic/workflow.py:32` (`class WorkflowNode(Node)`).
`src/kailash/nodes/base.py` has no `WorkflowNode`. Per `spec-accuracy.md` Rule 1
("every cited file:line resolves against working code") this is a phantom
citation in the plan-input chain. Not independently blocking (the conclusion —
positional-vs-kwargs drift — still holds via the real `WorkflowNode`), but the
analysis inherits the wrong path and any Shard-A2 agent following the citation
edits the wrong file.

---

## Verdict

**BLOCK.** The analysis is directionally correct on the headline (RAG package
is non-functional; not one node constructs as-is — confirmed: 55/58
node classes fail construction, only RAGConfig×2 + RAGWorkflowRegistry are OK)
and its specs/ disposition is rule-sound. But it ships to `/todos` with:

- **CRIT-1**: an empirically-missing 4th construction-failure class (R4
  f-string-template leak) that is widespread-but-masked and that the
  Shard-A1/A2 fixes will UNMASK — the single highest-impact omission.
- **CRIT-2**: a false load-bearing root-cause claim ("0 sites outside /rag/";
  there are 2 in `src/kailash/middleware/mcp/enhanced_server.py`, same bug
  class, with a tell-tale `# type: ignore[call-arg]`).
- **HIGH-1**: Shard A1 under-scoped — 38+13 two-shape split + capture-wrapper
  contract, not "one pattern ~38 sites."
- **HIGH-2**: R3 "PRESENT" set is mostly rag's own R1-broken nodes; only 3/15
  resolve to core — A3 is A1-gated.
- **HIGH-3**: A3 is strictly gated on A1+A2 (R3 masked behind R1/R2); the plan
  treats the shards as parallelizable.
- **HIGH-4**: S2 is certain (`ModuleNotFoundError`), not "may not exist."

**Gaps that MUST be fixed in the analysis before `/todos`:**

1. Add **R4** (f-string code-template single-brace interpolation leak) as a
   distinct class; state that R1/R2 fixes UNMASK R4; add a Shard-A0 mechanical
   grep pre-flight (`code=f"""` blocks containing single-brace `{ident...}`
   that are not `{{`/`}}`).
2. Correct the root-cause framing: R1 is a kailash-core bug class, NOT
   rag-local; the 2 `enhanced_server.py` sites are in-scope same-bug-class
   fixes (`zero-tolerance.md` Rule 1).
3. Re-size Shard A1 with the empirical **38 bare-name + 13 name+workflow**
   split (9-module distribution) and cite the `__init_with_capture`
   `self.config` population contract as the post-fix invariant.
4. Re-size Shard A3 with the pinned number: **15 distinct sub-workflow
   node-type strings; 4 absent** (`CacheNode`, `SemanticChunkerNode`,
   `HierarchicalChunkerNode`_, `StatisticalChunkerNode`_ — \*=NEW, not in any
   prior doc); 8 resolve-to-self-broken (auto-closed by A1); 3 core-OK.
   Encode the **A3-gated-on-A1+A2** dependency edge.
5. Fix the `WorkflowNode.__init__` citation: `src/kailash/nodes/logic/workflow.py:32`,
   not `src/kailash/nodes/base.py:1765`. Correct "17 modules" → "16 code
   modules". Pin R1 = 39 (not ~38).
6. Re-state S2 as certain `ModuleNotFoundError: No module named 'kaizen.workflow'`.

The specs/ deferral (Mission 5) is sound and needs no change beyond LOW-1
(name the file + add `_index.md` row in the first authoring shard).

```

```
