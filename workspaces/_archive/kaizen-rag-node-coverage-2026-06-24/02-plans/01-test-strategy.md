# 02 — Test Strategy: `kaizen.nodes.rag` behavioral coverage (F8)

Phase-01 plan. Pairs with `02-shard-decomposition.md`. Authoritative
counts from `01-analysis/01-research/01-node-surface-inventory.md` +
this session's own infra read of `packages/kailash-kaizen/src/kaizen/
nodes/rag/*.py` (the parallel contract deep-dive `02-node-contracts.md`
was NOT present at strategy-authoring time; the orchestrator reconciles
if/when it lands).

Value-anchor (this whole strategy) — `workspaces/kaizen-rag-resurrection/
briefs/00-brief.md` § "Out of scope", quoted verbatim in this
workstream's brief lines 12-18: _"the RAG capability the user chose to
preserve is provably correct, not merely importable."_ A test strategy
that mocked the retrieval/generation path would re-create exactly the
"importable but unproven" floor the user rejected — so the no-mocking
constraint is not just a rule here, it is the point.

---

## 1. The central testability finding (resolves the no-mocking problem)

The brief's "central testability question" — _how do RAG nodes take
their backends, given `[rag]` ships NO LLM client and NO vector store?_
— is **answered by reading the code, and the answer is favorable.**

Every one of the 55 registered node classes falls into one of three
runtime-backend shapes. Crucially, **none hard-requires an LLM API key
or a vector store to produce a real, assertable output**:

1. **Pure-compute nodes** — `run()` executes deterministic Python over
   the inputs (keyword overlap, numpy vector math, `networkx` graph
   algorithms, regex PII redaction, Laplace-noise differential privacy,
   in-memory dict session stores, simulated federated aggregation). No
   network, no model. Example proven this session: `DenseRetrievalNode.
run()` does keyword-overlap scoring with `numpy`, explicitly
   commented "Simple keyword-based scoring as fallback". The `[rag]`
   extra (numpy, Pillow, networkx, requests, aiosqlite) is the COMPLETE
   real backend for this class.

2. **LLM-with-rule-fallback nodes** — `run()` constructs an
   `LLMAgentNode` and calls `.execute(...)` inside a
   `try/except Exception → self._fallback_*()` block. The fallback is a
   real rule-based implementation (e.g. `router.py`
   `_fallback_strategy_selection`, lines 99-100). Verified this session
   across `router/advanced/evaluation/graph/agentic/conversational/
query_processing` — **zero** of them `raise` on missing key; all
   degrade to the deterministic branch. So with NO key configured, the
   node still returns a real, contract-shaped, assertable output (the
   fallback output) — that IS a behavioral contract worth locking.

3. **Workflow-composing nodes** (`workflows.py` 4 classes,
   `strategies.py` 4 classes via `WorkflowNode`) — `run()` builds and
   executes a sub-workflow graph through the Kailash runtime. These need
   a `LocalRuntime` (real, in-process, no external infra) and exercise
   the real Core SDK execution path.

**Consequence for the no-mocking rule (`rules/testing.md` Tier 2/3):**
the no-mocking constraint is honored WITHOUT containerized LLM/vector
infra for the overwhelming majority of nodes, because the real,
shipped, default code path of these nodes IS deterministic compute or a
real rule-based fallback — there is no mock to remove. We test the
behavior the user actually gets when they `pip install kailash-kaizen
[rag]` and run a node with no OpenAI key, which is the realistic
deployment for the resurrected toolkit (it has no LLM dep declared).

This is the single most important strategic decision in the plan and it
is grounded in code, not convenience.

---

## 2. Per-tier policy

Tiers follow `rules/testing.md` § 3-Tier Testing. All new tests live
under `packages/kailash-kaizen/tests/`.

### Tier 1 — Unit (`tests/unit/rag/`, `--timeout=1`, mocking allowed)

- **Scope:** Every registered node's `run()` golden path on the
  **deterministic / fallback code path** (no key in env → real fallback
  fires), plus documented edge cases (empty `documents`, empty `query`,
  malformed doc dicts, `k` larger than corpus, unicode, the typed-error
  paths).
- **Mocking position:** Tier 1 permits mocking, BUT we deliberately do
  NOT mock the retrieval/generation core — there is nothing to mock,
  the fallback is real. The ONLY Tier-1 stub permitted is the canonical
  `tests/unit/conftest.py` autouse fixture from `rules/testing.md`
  § "Tier-1 Conftest Stub" IF a node's fallback still attempts a network
  call before catching (none observed this session, but the fixture is
  the sanctioned escape hatch if the contract deep-dive finds one). It
  MUST NOT leak to Tier 2/3 (pytest conftest scoping guarantees this).
- **Why Tier 1 carries the bulk:** these nodes are deterministic given
  inputs; Tier 1 is where the contract (input shape → output shape +
  values) is locked fast and cheaply, one test per documented behavior.

### Tier 2 — Integration (`tests/integration/rag/`, `--timeout=5`, NO mocking)

- **Scope, two sub-classes:**
  - **2a. Real-infra-light** — nodes whose real backend IS the `[rag]`
    extra (numpy / networkx / Pillow / aiosqlite / requests-to-loopback).
    `GraphRAGNode` against real `networkx`; `realtime`/`conversational`
    against real `aiosqlite` on a tmp file; multimodal against a real
    Pillow-generated PNG. No container needed — the dep IS the infra.
  - **2b. Real-runtime** — `workflows.py` + `strategies.py` WorkflowNode
    classes executed end-to-end through a real `LocalRuntime`
    (`runtime.execute(workflow.build())` per `rules/patterns.md`). The
    runtime is real, in-process, zero external infra. State-persistence
    read-back applies where a node writes to aiosqlite (`rules/testing.md`
    § State Persistence Verification).
- **No-mocking honored by real lightweight backend** — this is the
  `rules/testing.md` Tier-2 contract met via "real lightweight backend",
  the FIRST of the three sanctioned options the brief requires the
  strategy to name.

### Tier 3 — E2E (`tests/e2e/rag/`, `--timeout=10`, NO mocking)

- **Scope:** The two canonical multi-node RAG pipelines the package
  docstring teaches (`__init__.py` Quick Start: router → strategy node;
  and Simple/Advanced/Adaptive `*WorkflowNode` chunk→embed→store→
  retrieve). Executed through a real `LocalRuntime`, asserting the final
  user-visible outcome (retrieved results for a known corpus+query),
  per `rules/testing.md` § "End-to-End Pipeline Regression". Filename
  contains `quickstart` for grep-ability.
- **One optional real-LLM E2E (env-gated, NOT in default CI):** a single
  test for the LLM-success path of `RAGStrategyRouterNode` /
  `RAGEvaluationNode`, `@pytest.mark.skipif(not os.environ.get(
"OPENAI_API_KEY"))`, model+key strictly from `.env` per
  `rules/env-models.md` (NEVER hardcoded). This is the documented
  boundary (the THIRD sanctioned option) for the LLM-success path that
  cannot be exercised with no key — it is a real-infra test, just
  env-gated, never a mock.

---

## 3. Real-infra plan per infra class

The brief asks for a real-infra plan per infra class
(embedding/LLM/vector/graph/network/storage/multimodal). Mapped to the
ACTUAL code shapes found this session:

| Infra class                     | Nodes (modules)                                                                                                                | Real backend                                                                                                                                                                                           | Tier                                      | No-mocking honored by                                                                                            |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **Embedding / dense retrieval** | `similarity.py` (7): Dense/Sparse/ColBERT/MultiVector/CrossEncoderRerank/HybridFusion/PropositionBased                         | numpy + inline keyword/vector fallback (the shipped default path — no embedding service in `[rag]`)                                                                                                    | T1 + T2a                                  | Real fallback IS the code path; numpy is real                                                                    |
| **LLM-driven reasoning**        | `router.py`(3), `advanced.py`(4), `query_processing.py`(6), `agentic.py`(3), `evaluation.py` `RAGEvaluationNode`               | rule-based fallback (no key → fallback fires, asserted); real OpenAI only in 1 env-gated E2E                                                                                                           | T1 (fallback) + T3 (1 env-gated real-LLM) | Fallback path real (T1); real LLM via `.env` key, env-gated (documented boundary)                                |
| **Vector store**                | none — no node imports chromadb/pinecone/faiss; "vector_db" is a string param threaded into workflow config, not a live client | n/a (the `[rag]` extra correctly carries no vector dep because no node opens a vector connection)                                                                                                      | —                                         | No vector client exists to mock; nothing to honor                                                                |
| **Graph**                       | `graph.py` (3): GraphRAG/GraphBuilder/GraphQuery                                                                               | real `networkx` (in `[rag]`)                                                                                                                                                                           | T1 + T2a                                  | networkx is the real, declared backend                                                                           |
| **Network / federated**         | `federated.py` (3): Federated/Edge/CrossSilo; `agentic.py` ToolAugmented (RESTClientNode)                                      | code path is "simulated federated aggregation" (federated.py:166 "simulated - would use actual network calls") — real deterministic compute; any genuine REST goes to a loopback `http.server` fixture | T1 + T2a                                  | Simulated-aggregation IS the shipped code path (real compute); real REST → loopback server (real infra, no mock) |
| **Storage**                     | `realtime.py`(3), `conversational.py`(2)                                                                                       | real `aiosqlite` (in `[rag]`) on a tmp DB file; in-memory dict store for the default path                                                                                                              | T1 + T2a                                  | aiosqlite is the real declared backend; read-back asserted                                                       |
| **Multimodal**                  | `multimodal.py` (3): Multimodal/VQA/ImageTextMatching                                                                          | real `Pillow` (in `[rag]`) — generate a real small PNG in the fixture; numpy for embeddings-fallback                                                                                                   | T1 + T2a                                  | Pillow is the real declared backend; real image bytes, not a mock                                                |
| **Workflow composition**        | `workflows.py`(4), `strategies.py`(4)                                                                                          | real `LocalRuntime` (Core SDK, in-process)                                                                                                                                                             | T2b + T3                                  | Real runtime, real graph execution; zero external infra                                                          |

### The hardest infra-availability problem (called out per brief)

**It is NOT the LLM/vector gap** — that dissolves once you read the code
(every node degrades to a real deterministic path; nothing to mock).
**The hardest problem is the workflow-composing nodes
(`workflows.py` + `strategies.py`, 8 classes via `WorkflowNode`).**
Their `run()` builds a sub-workflow and executes it through the Kailash
runtime. Behavioral coverage of these is only meaningful end-to-end
through a real `LocalRuntime`, and the sub-workflow internally wires
`LLMAgentNode` / `EmbeddingGeneratorNode` instances. Whether those
inner nodes also degrade gracefully with no key (like the top-level
nodes do) is the one open question the contract deep-dive
(`02-node-contracts.md`) MUST resolve before Shard 7 (workflow tier)
runs. Mitigation in the shard plan: Shard 7 is sequenced LAST, after the
deep-dive lands, and its value-anchor explicitly notes the dependency.
If an inner node DOES hard-require a key, the documented boundary is a
Tier-1 contract test asserting the WorkflowNode builds the correct graph
shape (`get_parameters` / `to_dict` / node-count invariant) + an
env-gated E2E for the live path — never a mock of the runtime.

---

## 4. How "no mocking in Tier 2/3" is honored where infra is hard

Per the brief's hard constraint, for every infra class the strategy
states the mechanism (real lightweight backend / containerized / Tier-1
contract test with documented boundary) — NEVER "mock it":

- **Embedding / LLM-reasoning:** real lightweight backend = the node's
  own shipped rule-based fallback path (it is real code, not a stub;
  exercised by simply not setting a key). The LLM-success path: Tier-1
  contract test of the request-construction + an **env-gated real-LLM
  E2E** keyed from `.env` (documented boundary; real infra, gated).
- **Graph / storage / multimodal:** real lightweight backend = the
  `[rag]` extra's own deps (networkx / aiosqlite / Pillow), which ARE
  the production backends — no container, no mock.
- **Network / federated:** real lightweight backend = a loopback
  `http.server` fixture for any genuine REST; the federated-aggregation
  path is simulated IN THE SHIPPED CODE (we test that real code, not a
  mock of it).
- **Vector store:** N/A — no node holds a vector client; nothing to mock
  or containerize. (If the contract deep-dive contradicts this, the
  fallback is a containerized real store via `tests/utils/test-env`,
  NOT a mock — recorded here as the contingency.)
- **Workflow runtime:** real in-process `LocalRuntime` — already real,
  no infra to procure.

No node's behavioral test uses `@patch` / `MagicMock` / `unittest.mock`
on the retrieval/generation path. Tier-1 may use the single sanctioned
autouse conftest stub ONLY if the contract deep-dive surfaces a fallback
that still touches the network before catching (none found this session).

---

## 5. Log-assertion + zero-tolerance posture

- Per `rules/observability.md` § Mandatory Log Points, Tier-2/3 tests
  for any node that logs a fallback (`router.py:99` `logger.warning(
"LLM strategy selection failed... using fallback")`) MUST assert the
  WARN log line — the fallback IS an observable contract; a test that
  asserts the fallback output but not the fallback log lets the
  observability contract silently break.
- Per `rules/zero-tolerance.md` Rule 4 (BUILD repo): any defect a
  behavioral test surfaces in a resurrected node is fixed in the SAME
  shard + a `tests/regression/` test + kaizen version bump, never
  deferred (brief success criterion).
- Per `rules/probe-driven-verification.md`: nodes whose contract is a
  SEMANTIC property of generated text (the env-gated real-LLM E2E only)
  use a probe (LLM-as-judge + JSON schema), not regex on the output.
  All other assertions are structural (output keys, score ranges, list
  lengths, typed-error raises) and use direct assertions.

## 6. Existing-suite non-duplication

The new suite complements `tests/regression/
test_rag_resurrection_import_smoke.py` (import + registration only — the
structural floor). New tests assert BEHAVIOR (`run()` outputs), never
re-test "imports clean" / "registers". The import-smoke suite MUST stay
green (brief success criterion) and is the regression baseline.
