# Wave 2.5 — Output-side wiring (L4): make every L3-fixed LLM stage's OUTPUT reach its consumer

User-greenlit 2026-06-09 (after Wave-2 L3 convergence). Value-anchor: brief "provably correct, not
merely importable" — a node whose LLM now CONSUMES context (Wave 2) but whose OUTPUT is dropped /
unparsed / mis-wired is STILL not provably correct end-to-end. BUILD repo: working-tree only.

## /analyze — output-side defect taxonomy (orchestrator audit, 2026-06-09)

`LLMAgentNode.run()` publishes its answer on the **`response`** port — a dict `{"content": "<text or
JSON string>", ...}` (+ `success`/`usage`/`metadata`). It does NOT auto-parse JSON into top-level
ports. So the CORRECT downstream pattern is: read `response` → `.get("content")` → `json.loads` if the
prompt asked for JSON → use the parsed fields. Two defect classes:

- **Class A — wrong port:** downstream reads a port the LLM never publishes (`result`, or a JSON-field
  name directly) → silently dropped.
- **Class B — parse-gap:** downstream reads `response` correctly but then `.get("<structured_field>")`
  on the response dict — but the field lives INSIDE `response.content` as a JSON string → resolves to
  the default (0 / empty) every time. Fabricated/zero output.

### Per-node disposition (audit receipts: `/tmp/outaudit.py` mechanical sweep + downstream-consumer grep)

| Node                    | Output-side state              | Defect                                                                                                                                                                                                                                                                                                                                                                                                |
| ----------------------- | ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **evaluation.py**       | **BROKEN (Class B)**           | `metric_aggregator` reads `faithfulness_scores[i].get("response",{}).get("faithfulness_score",0)` (`:599-609`) — the score is in `response.content` JSON, never parsed → **scores always 0**. Compounds the already-xfail'd batch-vs-per-test limitation.                                                                                                                                             |
| **workflows.py**        | **BROKEN (Class A+B)**         | `rag_strategy_analyzer.result → strategy_executor.input_data`/`results_aggregator.llm_decision` (`:717/:747`) reads `result` (LLM publishes `response`) AND the SwitchNode needs a parsed `{recommended_strategy}` → strategy decision never drives the executor. (= F31-FU3)                                                                                                                         |
| **graph.py**            | **BROKEN (Class B)** + F31-FU1 | `graph_builder` does `for doc_extraction in extraction_results` (`:373`) on `entity_extractor.response` — iterates the response DICT KEYS, not the parsed entity JSON in `response.content` → knowledge graph built from garbage (masked: full graph can't run under the networkx sandbox). PLUS `summary_generator.response → result_synthesizer.global_summaries` is accepted-but-unread (F31-FU1). |
| **query_processing.py** | **LIKELY BROKEN (Class B)**    | processors assign the raw response (`expansion_result = expansion_response` `:385`; same for decomposition/rewrite/intent/hop_plan) — need per-processor confirmation of whether they parse `response.content` before using structured fields.                                                                                                                                                        |
| **agentic.py**          | **CORRECT**                    | downstream uses `.get("response")` + `json.loads(verification_data)` (`:636-637,:718-723`) — the right unwrap+parse pattern. Verify-only at its shard.                                                                                                                                                                                                                                                |
| **conversational.py**   | **CORRECT**                    | unwraps `response.get("content")` everywhere (`:582,:692,:701`) — the Wave-1 fix. Verify-only.                                                                                                                                                                                                                                                                                                        |

### Value-ranked shards (anchor: "provably correct")

1. **eval (BROKEN, scores=0) — HIGHEST.** Sharpest failure (fabricated zeros); fix retires the held
   batch-vs-per-test xfail by adding a response-parser + real per-test scoring.
2. **workflows (BROKEN, F31-FU3).** Strategy decision never drives execution.
3. **graph (BROKEN + F31-FU1).** Entity parse + summary-output wiring (interacts with the networkx
   non-runnability — composer/parse proven via structural+standalone-probe per the L3 precedent).
4. **query_processing (verify → fix if broken).** 6 processors.
5. **agentic + conversational — VERIFY-ONLY** (audit says correct; confirm at a light verification pass).

Fix shape per stage: insert a from_function response-parser (read `response` → `.content` → `json.loads`
with a typed fallback) between the LLM stage and its structured-field consumer; re-wire the consumer to
read the parsed fields; end-to-end test asserts REAL parsed values reach the consumer (red-pre: raw
response → consumer gets defaults). Same shard+redteam discipline as the L3 wave.

---

## Shard O1 — evaluation.py output-side — CONVERGED 2026-06-09/10

**Fix (kaizen-specialist, task ab067abcbec8970e3):**

- **Parse-gap closed:** 3 `from_function` response-parsers (`parse_faithfulness/relevance/answer_quality_response`
  - `_unwrap_response_content` / `_parse_score_array`) read each judge's `response → .content → json.loads`
    → per-test score list; the aggregator now indexes REAL parsed scores (was `.get("<score>", 0)` off the raw
    response dict → always 0 = fabricated zeros).
- **Malformed-output honesty (zero-tolerance Rule 2):** non-JSON / missing-field judge output → typed sentinel
  `{"<score_key>": None, "parse_error": "<reason>"}`, EXCLUDED from the numeric mean, surfaced as a
  `parse_gaps` counter — NOT a fabricated 0. (security + reviewer garbage-input probe verified.)
- **Batch-vs-per-test resolved (xfail RETIRED):** Option (b) judge-returns-array — judge `system_prompt` +
  messages-composer number the tests (Test 1..N), each judge returns a JSON array one-object-per-test, the
  parser splits, the aggregator indexes per-test. Misalignment handled honestly (short → flagged gap, NOT
  zero-padded; long → extra ignored). The `@pytest.mark.xfail(strict=True)` deferral test was DELETED +
  replaced with a real passing test (orphan Rule 4a).

**MED-1 (R1 reviewer) — fixed in-session (autonomous-execution Rule 4):** the headline `overall_score`
scalar still did `.get("mean", 0)` per component → a fully parse-gapped metric averaged in a fabricated 0
(re-introducing the zero this shard removes). Fixed to roll up ONLY present (non-None) component means
(mirrors the per-test `present`-filter), `None` when none present. Regression test
`test_overall_score_excludes_parse_gapped_metric_not_fabricated_zero` + `_GarbageFaithfulnessJudge` adapter;
R2-verified load-bearing (revert → RED at 0.2 vs honest 0.6).

**End-to-end test:** `TestEvaluationScoresFlowEndToEnd` (4 tests, real LocalRuntime, `_DeterministicJsonJudge`
Protocol adapter publishing the production `response.content` JSON-string shape). Asserts real mean=0.7
(NOT 0), per-test `[0.8,0.6]` flow in order, answer_quality 0.65, overall_score excludes gaps. Red-pre
verified (revert parser wiring → KeyError / fabricated 0).

**Gates:** ruff clean; RAG suite **908 passed, 0 xfailed** (was 903 + 1xfail — xfail retired + 4 new tests +
the MED-1 test); 2 pre-existing `test_agentic_nodes.py` httpserver errors OUT OF SCOPE. base.py NOT edited.

**Redteam convergence receipts:**

- R1 security — task `a1d4c75133c678ba8` — **APPROVE**, zero findings (`json.loads` safe; parse-failure →
  typed sentinel not fabricated 0; aggregator excludes flagged from mean + `parse_gaps`; no logging leak).
- R1 reviewer — task `a29f6763e63187c93` — CHANGES-REQUESTED (MED-1). All else PASS — parse-gap closed,
  malformed-honesty verified via garbage-input probe, batch resolved, xfail retired, red-pre confirmed.
- R2 reviewer — task `aab9cff919196b84c` — **APPROVE (convergence)**. MED-1 closed + load-bearing
  (revert→RED); honesty consistent; 908 passed/0 xfailed; no scope creep; R1 PASSED items intact.

**Files (working-tree only, held uncommitted):** `src/kaizen/nodes/rag/evaluation.py`,
`tests/integration/rag/test_evaluation_nodes.py`, `tests/unit/rag/test_evaluation_nodes.py`.

**Outcome:** the evaluation node is now provably-correct end-to-end — judges CONSUME context (L3) AND
produce REAL parsed per-test scores (output-side) AND honestly exclude parse-gaps from every mean +
the headline score. The held batch-vs-per-test xfail is retired by a real fix.

Status: **Shard O1 DONE + held-uncommitted.**

## Remaining output-side shards (scoped, queued for continuation)

- **O2 — workflows.py (BROKEN, Class A+B / F31-FU3):** `rag_strategy_analyzer.result → ...` reads the wrong
  port (`response`) + needs a JSON parse so `{recommended_strategy}` drives the SwitchNode executor.
- **O3 — graph.py (BROKEN, Class B + F31-FU1):** `graph_builder` iterates the unparsed `response` dict
  instead of the entity JSON in `response.content`; PLUS `summary_generator.response → result_synthesizer.
global_summaries` is accepted-but-unread (F31-FU1). (Interacts with the networkx non-runnability →
  structural+standalone-probe proof per the L3 precedent.)
- **O4 — query_processing.py (verify → fix):** 6 processors assign the raw `response` (`expansion_result =
expansion_response` etc.) — confirm per-processor whether they parse `response.content` before using
  structured fields; fix the ones that don't.
- **O5 — agentic.py + conversational.py — VERIFY-ONLY** (audit says CORRECT: `.get("response")`+`json.loads`
  / `response.content` unwrap). A light verification pass to confirm, then close.

---

## Shards O2–O5 — IMPLEMENTED + held-uncommitted (2026-06-10)

Execution: SERIAL in the main working tree, one node-file = one shard, kaizen-specialist delegation
(worktree isolation infeasible — the root venv's editable `kaizen` resolves to the MAIN checkout, so a
worktree agent's edits would not be exercised by pytest). Fix shape identical across all four: a module-level
`from_function` response-parser (`response → _unwrap_response_content → .content → json.loads`) inserted between
each LLMAgentNode stage and its consumer, typed parse-error sentinel on malformed (NEVER fabricated output),
consumer re-wired to read the parsed dict, real-LocalRuntime end-to-end test with a verified red-pre proof +
malformed-honesty test, stale graph-shape unit tests swept (orphan Rule 4). Baseline at HEAD `638ed691d`: **910
passed**. Cumulative after O2–O5: **945 passed, 0 failed/errored**; ruff clean on all 4 node files; base.py
untouched; BUILD repo — all four shards held UNCOMMITTED in the working tree (commit stays with the user).

### O2 — workflows.py (F31-FU3) — DONE (kaizen-specialist `a420bb0c5195c6b6d`)

`AdaptiveRAGWorkflowNode`: `rag_strategy_analyzer` published `response` but two edges read the wrong `result`
port (Class A) AND the SwitchNode `condition_field: recommended_strategy` + `results_aggregator.llm_decision`
needed a PARSED dict (Class B). Fix: `parse_strategy_decision` (5 typed sentinels: empty/non-json/unexpected-
content-type/non-object-json/missing-strategy) → `strategy_decision_parser` node; removed 2 phantom `result`
edges; wired `analyzer.response → parser.response`, `parser.result → executor.input_data` + `→ aggregator.
llm_decision`. Malformed → SwitchNode fails-closed (no case matches None), NOT a fabricated `"semantic"`.
Red-pre: `condition_result != "hybrid"` + no `case_*` fires under raw-`result` topology. **915 passed (+5).**

### O3 — graph.py (Class B + F31-FU1) — DONE (kaizen-specialist `aa90f3ba34598892f`)

GraphRAGNode, two defects. (1) Class B: `entity_extractor.response` (a `{entities,relationships}` JSON in
`.content`) was fed RAW to `graph_builder`, whose `build_knowledge_graph` iterates `extraction_results` as a
per-doc list → iterated the response dict's KEYS → would `AttributeError` if it ran (latent: networkx sandbox
makes the full graph non-runnable, pre-existing). Fix: `parse_entity_extraction` publishes the parsed object
WRAPPED IN A ONE-ELEMENT LIST; malformed → `[{"entities":[],"relationships":[],"parse_error":...}]` → EMPTY
graph honestly. (2) F31-FU1: `result_synthesizer` accepted `global_summaries` but its `code=` body never read
it → `summary_generator` output DROPPED (Rule 3c). Fix: `parse_global_summary` (prose, no json.loads) +
synthesizer body now emits `graph_rag_results["global_summary"]`. Conditional-wiring: Option (i) — the
`global_summaries`-reading lines are emitted in the synthesizer `code=` ONLY on the `use_global_summary=True`
path (PythonCodeNode injects inputs as locals; an unwired name → NameError), adding zero new topology on the
disabled path. Node counts 9→11 (enabled) / 7→8 (disabled). Both parsers proven via structural-wiring +
standalone-probe under real LocalRuntime (full graph non-runnable = networkx, honestly surfaced). Red-pre
proven for both defects. **924 passed (+9).**

### O4 — query_processing.py (Class B ×6) — DONE (kaizen-specialist `a24e82e69d21f0ff8`)

ALL 6 LLM stages were BROKEN (not "likely" — verified): every consumer `code=` body assigned the raw
`response` dict then `.get("<structured_field>")` on it → structured fields live inside `response.content` as
JSON → every field silently defaulted. Fix: shared `_unwrap_response_content`/`_loads_response_object` + 6
parsers (`parse_expansion/decomposition/analysis/rewrite/intent/hop_plan_response`), 7 parser nodes (rewriting
has 2), 6 direct `response→consumer` edges removed + parser edges added; consumer bodies unchanged (they
already `.get` the structured fields, now receive the parsed dict). `AdaptiveQueryProcessorNode` confirmed
out of scope (no direct LLM stage). In-pass same-class fix (Rule 4): the existing `_DeterministicLLMAgent`
integration substitute modelled the WRONG wire shape (structured fields at top-level of `response`, no
`content` key) — green only because it matched the pre-fix bug; corrected to the production
`response={"content": json.dumps(payload)}` shape so the existing 32 integration tests now exercise the real
parsed path. Red-pre per stage. **939 passed (+15).**

### O5 — agentic.py + conversational.py — VERIFIED; AUDIT WAS WRONG (kaizen-specialist `a82e3904e4af46093`)

The "audit says CORRECT" verdict for **agentic.py was FALSE** — empirically all 5 consuming LLM stages were
BROKEN (Class B): the `response` port delivers the inner `{"content":...}` dict, so the consumers' `.get
("response")` read a non-existent key → `planner`/`verifier` verdicts dropped (confidence never adjusted:
red-pre 0.8 vs honest 0.4), `react`/`step_reasoner` prose `None.strip()` CRASH. The test adapter
(`_MessageCapturingLLMAgent`) had the SAME wrong shape O4 found — a systematic false-green. Fix: 5 parsers
(`parse_plan/reasoning/verification/decomposition/reasoning_chain_response`) across AgenticRAGNode (+3 nodes,
9→12) + ReasoningRAGNode (+2 nodes, 7→9; unit 6→8); adapter corrected to production shape → the 2 ReasoningRAG
end-to-end tests went RED until parsers wired (load-bearing). AgenticRAGNode cyclic-graph + ReasoningRAGNode
acyclic honest dispositions preserved. **conversational.py GENUINELY CORRECT** (proven: all 3 consumers read
`.get("content")`; `test_workflow_publishes_conversational_response` × 4 cfgs, full graph, real LocalRuntime,
`provider:"mock"` production shape, read-back assert) — untouched. **945 passed (+6).**

### Wave-level learning (G2, pre-redteam)

**The test-adapter wrong-shape (`response`-top-level instead of `{"content":...}`) was a SYSTEMATIC false-green
source for output-side correctness across the RAG node family.** It masked real output-side bugs in BOTH
agentic AND query_processing despite the L3 input-side tests being green (input-side tests only need the adapter
to CAPTURE messages, not publish a correct response — so the wrong shape was invisible to them). O1 (eval,
committed) + conversational (Wave-1) used the correct `{"content":...}` shape and were genuinely correct; O2/O3
introduced correct-shape adapters; O4/O5 corrected the two wrong-shape adapters. **The "audit says correct"
output-side verdict is UNRELIABLE without a production-shape read-back probe** (O5 disproved it for agentic).
Forest item: audit non-RAG kaizen tests for the same wrong-shape adapter pattern (out of this wave's scope).

---

## Wave-boundary /redteam — CONVERGED 2026-06-10 (G1 gate)

Scope: the full output-side wave (O2 workflows + O3 graph + O4 query_processing + O5 agentic) vs HEAD
`638ed691d`, held uncommitted. reviewer + security-reviewer dispatched in parallel each round.

**Round 1:**

- security-reviewer (`a6554116d6d545c17`) — **APPROVE**, zero CRIT/HIGH/MED/LOW (6 surfaces: `json.loads`
  safe; no untrusted content reaches a `code=`/SQL/shell exec surface — only dev-set constants interpolated;
  typed `parse_error` sentinels are static strings that neither leak nor fabricate; no unbounded parse/DoS;
  type-confusion rejected to sentinel before reaching consumers; test adapters secret-free).
- reviewer (`af6a87c10801938c1`) — **CHANGES-REQUESTED**, **CRIT-1**: GraphRAGNode has THREE LLM stages and
  O3 fixed only two — `query_processor.response → graph_retriever.query_analysis` was left wired RAW (Class-B
  parse gap), so `graph_retriever` returned an EMPTY subgraph regardless of the LLM's query analysis (the
  query-driven retrieval path was dead). The graph.py unit node-set test was self-consistent but pinned the
  buggy topology. LOW-1 (pre-existing agentic `tool_executor` demo stubs at agentic.py:696-724) noted
  out-of-scope → forest item.

**CRIT-1 fix (in-wave per autonomous-execution Rule 4; kaizen-specialist `aa90f3ba34598892f`):** added
`parse_query_analysis` (unwrap `.content → json.loads → {entities, relationship_types, requires_multi_hop,
reasoning_type}`, typed sentinel with EMPTY defaults on malformed → honest empty subgraph, never fabricated)

- `query_analysis_parser` node; removed the raw edge; wired `query_processor.response → parser.response`,
  `parser.result → graph_retriever.query_analysis`; node counts 11→12 / 8→9 (parser present on both paths);
  corrected the node-set unit tests; added `test_red_pre_proof_raw_response_to_retriever_yields_empty_subgraph`
  (load-bearing: raw topology → `set()` despite real entities in `_ANALYSIS_JSON`; parsed → `{transformer,
attention}`). **948 passed (+3).**

**Round 2 (post-fix):**

- security-reviewer (`a9da9cc182fd4f21e`) — **APPROVE**, focused delta on the CRIT-1 fix (all 5 surfaces
  clean; parse-then-coerce closes type-confusion before the retriever's data-only `.get`/iteration; sentinel
  leaks nothing; adapter secret-free; no new unbounded loop).
- reviewer (`abb0c1b6097e70f61`) — **APPROVE (convergence)**. Exhaustive re-enumeration of ALL 16 LLMAgentNode
  stages across the 4 files: every stage routes through a `parse_*`/`*_parser` node OR is correctly terminal
  (agentic `logic_verifier` receives only `messages`, never a connection source); every `<id>,"result"` read
  confirmed to be a genuine PythonCodeNode (workflows `quality_analyzer` etc.), never an LLMAgentNode. Verdict:
  **"No remaining unparsed LLMAgentNode output stage across the 4 files."** CRIT-1 closed; red-pre load-bearing;
  948 passed; collect-only exit 0; ruff clean; base.py not in diff.

**Convergence:** R1 reviewer CHANGES → CRIT-1 fixed → R2 both-reviewers-APPROVE (the post-fix clean round),
matching the L3/O1 convergence pattern. One transient server throttle hit the R2 reviewer mid-run (single
agent, `not your usage limit`) — NOT the synchronized ≥2-in-30-48s concurrency signal (worktree-isolation
Rule 4), resumed after account swap, no back-off warranted.

## WAVE 2.5 (output-side wiring) — CONVERGED — 2026-06-10

**Delivered:** every LLM stage across the 5 RAG node files that CONSUMES context (Wave-2 L3) now also has its
OUTPUT reach the real downstream consumer PARSED — workflows (1 stage), graph (3), query_processing (6),
agentic (5 + 1 terminal); conversational (3) verified already-correct. 15 `from_function` response-parsers
(workflows 1, graph 3, query_processing 6, agentic 5), all with typed parse-error sentinels (never fabricated). Each fix ships a real-LocalRuntime end-to-end test
with a verified red-pre proof; the wave converged via parallel reviewer + security-reviewer (R1 security
APPROVE + reviewer CRIT-1 → fix → R2 both APPROVE). **Cumulative gate: 948 passed, 0 failed/errored; ruff
clean; base.py untouched.** F31-FU1 (graph summary orphan) + F31-FU3 (workflows analyzer mis-wire) CLOSED by
O3/O2. **BUILD repo — held UNCOMMITTED in the working tree; commit/push stays with the user.**

### G4 — re-value-rank of the remaining F31 program (value-anchor: brief "provably correct, not merely importable")

With the input-side (L3) AND output-side (Wave 2.5) now both provably-correct end-to-end across the real RAG
node family, the remaining F31 candidates re-rank:

1. **F31-FU2 — composer/parser DIRECT unit tests (MED, hardening).** The 13 parsers + the L3 composers are
   proven via integration capture / standalone probes, not direct unit tests asserting `{"messages":[...]}` /
   parsed-dict shape + the empty/None-input branch (testing.md "one direct test per variant"). Best as a codify
   /hardening pass.
2. **from_function migration (orig Wave 3) — large, mechanical de-risk.** Supersedes the held in-place #1117
   nested-port patches; closes the latent nested-port class systematically. High value, large scope → shard.
3. **Wave 4 simulated nodes (strip/flag/build) — PRODUCT CALL (user).**
4. **Forest items:** audit non-RAG kaizen tests for the wrong-shape adapter false-green class (surfaced this
   wave); LOW-1 agentic `tool_executor` demo stubs (pre-existing, separate issue against the ReAct tool layer);
   pre-existing `env_files` pytest-config warning (vestigial `pytest-env` key, test-infra, orthogonal).
