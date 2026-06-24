# RAG re-analysis — architecture decision + remediation program (2026-06-09)

Resolves the strategic checkpoint the prior session paused for (input: `12-re-analysis-problem-statement`).
Three parallel verification agents (read-only, current source) confirmed all claims. This doc is the
`/analyze` deliverable + the value-ranked program. BUILD repo — all work is working-tree only; commits
stay with the user.

## Verified findings (agent receipts: tasks aa4aa471c9cd8ddc4 / a16238488b6ea7828 / abacaa52194297050)

### Q1 — codegen root cause: CONFIRMED (scope = whole subsystem, not just WorkflowNode)

- `kaizen/nodes/rag/` mechanical counts: **80** `add_node("PythonCodeNode", ...)` codegen sites,
  **73** f-string `code=` blocks, **0** `PythonCodeNode.from_function`.
- Correct primitive exists: `src/kailash/nodes/code/python.py:1474` `PythonCodeNode.from_function(func)`.
  Wraps a live callable → real imports resolve in the function's own module namespace (#1118 trap gone),
  `return` value is published as `result` (#1117 gone), no f-string brace-escaping (#1123 gone),
  type-checkable.
- Exemplars already correct: `router.py` (RAGStrategyRouter/QualityAnalyzer/PerformanceMonitor — direct
  `run()` compute, 0 codegen), `similarity.py` Dense/Sparse (direct `run()`), `advanced.py`+`router.py`
  LLM stages (direct `.execute(messages=[...])`).
- 56 node classes across 15 files use the pattern (both `WorkflowNode` and `Node` tiers).

### Q2 — L3 LLMAgentNode context contract: CONFIRMED systemic

- `LLMAgentNode` (`kaizen/nodes/ai/llm_agent.py:52`) consumes context ONLY via `messages`
  (+ `system_prompt`); `run()` reads each param by explicit `kwargs.get` (`:755`), so any non-declared
  wired port is silently dropped.
- 27 builder-graph LLM stages across 8 files (agentic, conversational, evaluation, graph, multimodal,
  query_processing, similarity, workflows). **26 receive no `messages`**; the 1 that targets `messages`
  (`similarity.cross_encoder`) feeds the wrong shape. **0 of 27 deliver retrieved context to the LLM.**
- Correct pattern (in-tree template): build `result = {"messages":[{"role":"user","content": rendered}]}`
  in an upstream node and `add_connection(composer, "messages", llm_stage, "messages")`; feed
  query+docs+history INTO the composer, not into the LLM stage. `advanced.py`/`router.py` `.execute(
messages=[...])` is the reference.

### Q3 — keep-vs-strip (honesty / zero-tolerance Rule 2): verified

- ALREADY HANDLED: `SecureMultiPartyRAGNode` (DeprecationWarning `privacy.py:827`, "NON-FUNCTIONAL
  SIMULATION"); `PrivacyPreservingRAGNode` (DP-ε relabeled "NOT differential privacy", real regex PII).
- SIMULATED (advertise real capability, fabricate via random/sleep/hardcoded/keyword) — open Rule-2
  exposures: Multimodal trio (CLIP/BLIP, `multimodal.py:220+`), Federated pair (network,
  `federated.py:172+`), ColBERT (BERT, `similarity.py:700`), DenseRetrieval (keyword labeled "dense",
  `similarity.py:155`), CrossEncoderRerank `run()` (`similarity.py:1226`), Realtime monitor
  (`realtime.py:403`).
- REAL (content honest; many still carry the L3 bug): Graph, AsyncParallel/Batch/Streaming (optimized),
  Cache, Compliance, Edge, eval nodes, advanced/agentic/conversational/query_processing/router/
  strategies/workflows clusters.

## DECISION — root-cause remediation program

**Direction (technical, autonomize envelope): migrate each node's `code=f"""..."""` blocks to
`PythonCodeNode.from_function(real_func)`, and in the SAME pass (a) compose a real `messages` list and
wire it to the valid `messages` port (fixes L3), (b) ensure real `result` publishing (fixes #1117),
(c) for simulated nodes, strip/flag per the product call.** The WorkflowNode/builder architecture is
RETAINED — this is a per-block transformation (lift each code string into a real module-level function),
not a node-model redesign. Each node is a clean shard; the subsystem is a multi-session program.

Why from_function over more in-place patching: in-place patches on the f-string codegen (what the 4 held
shards did for #1117) are symptom fixes the migration re-touches → violates root-cause + long-term. One
migration pass per node fixes construction + L3 + publish together and is forward-stable.

### Value-ranked waves (anchor: brief "provably correct, not merely importable")

1. **Wave 1 (this session, in-envelope): ConversationalRAGNode** — complete the held shard to TRUE
   provably-correct by fixing its open HIGH L3 finding via the from_function pattern; establishes the
   migration reference template + per-node playbook. (Real content; already has an end-to-end test.)
2. **Wave 2: L3 across the remaining REAL nodes** (eval evaluators, graph, agentic, query_processing,
   workflows) — make every real LLM stage consume context. Highest aggregate "provably correct" value.
3. **Wave 3: from_function migration of the real-content codegen nodes** (mechanical transform; de-risks
   the whole family; supersedes the held in-place #1117 patches).
4. **Wave 4: simulated-content nodes** — strip OR experimental-flag OR build-real. PRODUCT CALL (user).

### Held interim work (4 shards: privacy/conversational/cache/eval — uncommitted, R1-converged)

Recommendation: KEEP as the working baseline (they make the nodes publish real output TODAY and pin the
runtime behavior the migration must preserve). They are superseded incrementally as each node migrates.
Do NOT discard. Commit disposition is the user's (BUILD repo).

## User-gated decisions (surfaced, non-blocking for Wave 1)

- **Program greenlight:** undertake the multi-session from_function migration program (Waves 2-3)? (rec: yes)
- **Strip-vs-build (Wave 4 product call):** for the simulated nodes — strip the advertised capability,
  experimental-flag it, or invest in real backends (vision ML/GPU for multimodal; network for federated;
  BERT for ColBERT)? (rec: strip/flag the un-buildable; build DenseRetrieval — cheapest, already has an
  `embedding_model` param.)
- **Held-shard commit:** commit the 4 interim shards now as a stepping stone, or hold until migration? (rec: hold)

## Wave 1 receipt + surfaced findings (2026-06-09)

**Wave 1 (ConversationalRAGNode L3) — implementation complete, redteam in flight.**
- Fix: 3 module-level composer fns (`compose_response_messages`/`compose_coreference_messages`/
  `compose_summary_messages` + `_render_history`/`_render_documents`/`_query_from_retrieval`) wrapped
  via `PythonCodeNode.from_function` and wired to the LLMAgentNode `messages` port; formerly-phantom
  ports (`retrieval_results`/`conversation_context`/`conversation_history`/`context`) now feed the
  composers. conversational.py:135-200 (fns) + ~848 (composer nodes) + re-wired connections.
- End-to-end test `TestConversationalRAGContextReachesLLM` (integration) — red-pre/green-post, asserts
  composed `messages` embed retrieved-doc + query. Held #1117 publish-fix + CSPRNG session_id preserved.
- Real gates GREEN: ruff clean; 54 conversational rag tests pass (2 pre-existing pytest-config warnings
  `timeout`/`env_files` — known test-infra dep-gap backlog, out of scope).
- Redteam R1 dispatched: reviewer (task a6ec4a88) + security-reviewer (task aea76160), parallel.

**SURFACED SDK FINDING (separate change — NOT in this shard's working tree):**
`register_node` (`src/kailash/nodes/base.py:2719`) inner `decorator(node_class: type[Node])` lacks a
return annotation → `@register_node()` erases the concrete subclass type to `type[Node]` for ALL ~140
nodes. This is the root cause of the `PythonCodeNode.from_function` "unknown attr" type diagnostic and
will recur at every `from_function` call site across the migration program. Verified fix (generic TypeVar
`Callable[[type[T]], type[T]]`, typing-only, zero runtime change) works, but REVERTED here because:
(a) it belongs in its own scoped change, not bundled into a kaizen-RAG working-tree set; (b) editing
base.py surfaces hundreds of pre-existing non-gating core-SDK pyright diagnostics across the import graph;
(c) warrants cross-SDK inspection (kailash-rs may have the same erasure). NOTE: project does NOT gate on
mypy/pyright (mypy pre-commit hook is commented out at `.pre-commit-config.yaml:217-223`) — real gates
are ruff + pytest. RECOMMEND: file as a standalone core-SDK typing fix + cross-SDK issue.

## Wave 1 CONVERGED — receipt (2026-06-09)

Convergence reached after 3 redteam rounds (the rounds caught real defects — redteam earned its keep):
- **R1**: security APPROVE (task aea76160) · reviewer found MED-1 (coreference composer got empty query) + LOW (test gap) (task a6ec4a88).
- **R2**: security APPROVE (task a25c90e2) · reviewer found MED-2 — the coreference test was FALSE-GREEN (node-keyed harness injection bypassed the production wiring; passed with the fix stripped) (task acde7db1).
- **R3 (clean)**: security APPROVE (task aeafc54a) · reviewer CONVERGED (task a0dcac63) — both MEDs independently re-proven closed (structural edge + behavioral param each red-pre/green-post); discovered `add_workflow_inputs` was DEAD CODE (query delivered via parameter-injector auto-distribute `parameter_injector.py:428-449` because the composer fn declares `current_query`) → removed per zero-tolerance Rule 2; 1 MINOR (stale comment) → FIXED this turn.
- **Final gates**: ruff clean; Tier-1 unit 36 passed; Tier-2 integration 19 passed; full kaizen RAG suite 871 passed (2 pre-existing httpserver collection errors out of scope); base.py diff EMPTY; held #1117 + CSPRNG preserved.

ConversationalRAGNode is now provably-correct at all 3 layers: L1 publishes real output, L2/#1117 module-scope result, **L3 the LLM now actually consumes retrieved docs + history + query via the `messages` port** (was system-prompt-only). The from_function messages-composer pattern is the established reference template for Waves 2-3.

**G2 learning delta (wave-loop):** the redteam's two real catches (empty-query on 1 of 3 stages; false-green test via harness-injection bypass) are the per-node migration playbook's two checklist items: (1) verify EVERY LLM stage of a node receives context (not just the primary path), (2) the L3 test MUST exercise the PRODUCTION delivery path (top-level workflow input / auto-distribute), never a node-keyed harness shortcut, and MUST go red when the load-bearing wiring is stripped.

**Status: Wave 1 done + held-uncommitted (BUILD repo; commit stays with user). Awaiting user steer on the 3 program/product gates before Wave 2.**
