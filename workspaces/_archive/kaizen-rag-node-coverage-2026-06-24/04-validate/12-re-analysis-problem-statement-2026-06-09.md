# RAG subsystem — re-analysis problem statement (input for a fresh /analyze)

User-directed 2026-06-09 (strategic checkpoint): PAUSE node-by-node patching, RE-ANALYZE the
architecture. This doc synthesizes the systemic evidence from the F8/F9/#1117 remediation so
the next `/analyze` starts from ground truth, not the (decayed) original brief. BUILD repo —
all remediation work is HELD uncommitted in the working tree pending the strategy decision.

## Root-cause HYPOTHESIS (to confirm/refute in /analyze)
**The codegen-into-`PythonCodeNode` workflow pattern is the systemic root cause.** Nearly every
`kaizen.nodes.rag` WorkflowNode builds its pipeline by embedding multi-line Python as f-string
`code=` blocks inside `PythonCodeNode`s wired with `add_connection`. This single pattern
generates the entire bug family observed:
- **#1117 publish-nothing** — codegen defines a fn but never calls it at module scope → the
  PythonCodeNode publishes no `result`. (6 of ~11 WorkflowNode classes affected.)
- **#1123 literal-brace crash** — a non-f-string `code=` containing `{self.x}` (or an f-string
  with unescaped `{...}`) → exec-time NameError / set-literal corruption.
- **#1118 separate-exec-namespace** — module-level imports invisible to the codegen exec; must
  self-import inside each fn body.
- **Wrong-port wiring** — `add_connection` reads ports the source never publishes (a
  PythonCodeNode publishes only `result`); silently drops data.
- **Contract mismatch** — codegen reads non-existent keys off a real Node's output (CacheNode
  `exact_hit` vs real `hit`/`value`).
- **Un-testable without AST helpers** — the bug class is invisible to unit tests that exec the
  inner fn directly; only end-to-end `LocalRuntime` runs catch it (no such tests existed).
- **Obscures real-content gaps** — because the pipelines never ran end-to-end, deeper gaps
  (LLMs ignoring context; simulated content) went undetected.

Implied architecture question: should RAG nodes be real typed `Node`/`WorkflowNode` classes
(or `PythonCodeNode.from_function`) with real Python — NOT f-string codegen strings?

## Evidence (this remediation)
- **3 #1117 shards, each broken at 3-5 layers:** privacy (publish-nothing + wrong-port; CRASHED
  pre-fix), conversational (#1117 + #1123 + input-copy session limit + L3), cache (#1117-partial
  + CacheNode contract-mismatch + 2 orthogonal blockers). All 3 FIXED + converged + end-to-end
  tested (fails-pre/passes-post) — held uncommitted.
- **Audit (`/tmp/audit_1117.py`):** 6/11 WorkflowNode rag classes publish nothing. CLEAN: eval
  (Wave-1-fixed), Graph, AsyncParallel/BatchOptimized/Streaming.
- **L3 (HIGH, systemic):** LLMAgentNode stages receive no `messages` — wired ports (history/
  context/retrieval) aren't valid LLMAgentNode params, silently dropped → the LLM answers from
  system-prompt alone, ignoring the RAG context. Confirmed in conversational; UNAUDITED but
  likely tree-wide (every node with an LLM stage).
- **Orthogonal blockers** (strategies.py): HybridRAGNode `config={"config":{...}}` shape bug →
  AttributeError on `.chunk_size`; non-functional `_skip_if_true` gate (SDK ignores it).
- **Simulated content** (07-ledger QUARANTINE/FIX, separate from #1117): Federated (federation
  network), Multimodal (CLIP/BLIP), ColBERT (BERT), RealtimeRAG, SecureMultiPartyRAG (deprecated
  this session). These cannot be "fixed" by wiring — they need real ML/crypto backends or strip.

## Node disposition map (current ground truth)
- **Real + fixed this session (held uncommitted):** RAGEvaluationNode, RAGBenchmarkNode (W1);
  PrivacyPreservingRAGNode (claim-strip + publish-fix); ConversationalRAGNode (publish-fix, but
  L3 LLM-no-context remains); CacheOptimizedRAGNode (publish-fix, but 2 orthogonal blockers remain).
- **Real + already clean:** GraphRAGNode, AsyncParallelRAGNode, BatchOptimizedRAGNode,
  StreamingRAGNode, the similarity/strategies/workflows SHIP-tier (per 07-ledger).
- **#1117-broken, fixable (keep candidates):** RealtimeRAGNode*, FederatedRAGNode*, MultimodalRAGNode*
  (*also simulated-content → fix-vs-strip).
- **Simulated content (strip-or-build-real candidates):** Federated, Multimodal, ColBERT,
  SecureMultiParty (deprecated).

## Questions /analyze MUST answer
1. Confirm/refute the codegen-PythonCodeNode root-cause hypothesis. Is the right pattern real
   typed nodes / `from_function` / a different composition primitive?
2. The LLMAgentNode context contract (L3): how SHOULD query/history/retrieved-docs reach the LLM
   (`messages`)? Audit which nodes are affected.
3. Keep-vs-strip per node: which RAG capabilities are genuinely valuable + buildable-real vs
   simulated-and-should-strip? (user product call, evidence above.)
4. Testing contract: mandate end-to-end `LocalRuntime` regression per node (the gap that hid all
   this) — not AST-helper unit tests.
5. The orthogonal blockers (HybridRAGNode config, skip-gate) — fix or design out.

## Carried context for the next session
- All converged work is HELD uncommitted (working tree, base `2f125ca4c`). DO NOT commit until
  strategy is set (user "hold"). Files: `packages/kailash-kaizen/src/kaizen/nodes/rag/{evaluation,
  privacy,conversational,optimized}.py` + CHANGELOG + rag test files.
- Receipts: 06-/07- (original audit), 08- (wave plan), 09-/10-/11- (Wave 1/2/#1117 redteam), this 12-.
- Landed (committed) this session: `auto-merge.yml` GHA-injection hardening, PR #1282, main `2f125ca4c`.
