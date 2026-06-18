# RAG "Provably Correct" Red-Team — 2026-06-08

**Mission:** Honor `/redteam to convergence` against the real target — are the 55
landed `kaizen.nodes.rag` nodes *provably correct*, not merely *importable*?
Read-only gap-audit (no commits). Answers whether F8 Milestone B has residual value.

**Method note:** Round-1 parallel-agent fan-out (5 cluster auditors) aborted on a
transient platform rate-limit (`Server is temporarily limiting requests`, ~0 tokens
each). Substituted main-thread **mechanical + targeted-deep-read** audit, which
yields harder evidence than LLM judgment (grep counts, AST profile, live test run,
direct code reads). Findings below are mechanically grounded.

---

## Verdict

| Milestone | Brief value | Status |
| --------- | ----------- | ------ |
| **A — make-functional / importable** | "55 nodes construct" | ✅ **DONE** (delivered by F25/#1198) |
| **B — provably correct, not merely importable** | brief §"Out of scope" verbatim | ❌ **NOT met** for a material node subset |

**F8 Milestone A is superseded** (F25/#1198 wired constructors + redteam-round-1).
**F8 Milestone B carries genuine, HIGH residual value:** a material subset of nodes
returns **simulated / templated output in their production run-paths**, with the
passing test suite asserting the simulated output.

---

## Evidence — Milestone A is solid

- **Construct:** 55/55 `Node` subclasses instantiate, 0 fail (target module
  `packages/kailash-kaizen/src/kaizen/nodes/rag/__init__.py`).
- **Tests run:** `tests/unit/rag/` = **590 passed, 0 failed, 0 skipped, 17.2s**
  (`.venv/bin/python -m pytest tests/unit/rag/ -q`). Slowest are real executions
  (6.5s workflow run, 4.5s benchmark), not no-op constructs.
- **Assertion quality (AST profile, 14 files, 1174 unit assertions):** **60%
  behavioral** (`==` / magnitude / quantifier), **~0 mocks** (1 patch in entire tree)
  → coverage is unhollowed by mocks; not assertion-theatre.

## Evidence — Milestone B gap (the finding)

**36 inline-`#` placeholder comments in executable run-path logic** (not docstrings),
across 10 of 15 node files. The simulations are capability-defining:

| Node cluster | Run-path evidence | What is simulated |
| ------------ | ----------------- | ----------------- |
| **FederatedRAG** | `federated.py:172` "Federated query executor (simulated — would use actual network calls)"; `:207` "Generate simulated response" | the entire cross-silo federation |
| **MultimodalRAG / VQA / ImageTextMatching** | `multimodal.py:220` "Simulated encoding (would use CLIP/BLIP in production)"; `:555` "Simulated VQA (would use real model)" | embeddings + visual-QA (no real model) |
| **RAGEvaluation / RAGBenchmark** | `evaluation.py:145-146` "Execute RAG (simplified — would call actual system)"; `:262` "Simulate relevance judgment (would use LLM)" | doesn't run the system it benchmarks; metrics fabricated |
| **ToolAugmentedRAG / ReasoningRAG** | `agentic.py:721` "In production, would use LLM for synthesis"; `:703` keyword tool-routing; `:862` "simplified — would use loop" | LLM synthesis templated; `LLMAgentNode` imported `# noqa: F401` but unused in run() |
| **QueryProcessing** (6 nodes) | 22 keyword-routing hits (`in query_lower`) for intent classification | `agent-reasoning.md` MUST-1 surface (keyword classification where LLM reasoning belongs) |
| **PrivacyPreservingRAG** | docstring advertises "ε-differential privacy" + "Homomorphic encryption support" (`privacy.py:8,45`); impl is regex PII redaction (`:147-169`) | formal DP / HE guarantees not implemented (regex redaction is real but a weaker guarantee than advertised) |

**Rule mapping:**
- `zero-tolerance.md` Rule 2 — "No simulated/fake data … `simulate`, placeholder …
  fake classification / fake encryption" — the run-path `simulated` branches ship
  fabricated output as if real.
- `agent-reasoning.md` MUST-1 / MUST-NOT — keyword/regex routing in agent decision
  paths (query-intent classification, tool detection).
- The brief's verbatim value — *"the RAG capability the user chose to preserve is
  provably correct, not merely importable"* — is precisely the gap.

**Confidence:** HIGH for the cited file:line run-path comments (direct reads).
Per-node real-vs-stub branch confirmation across all 55 (does any sim have a real
fallback branch?) is the natural Round-2 deep-dive; the inline "would use X in
production" phrasing indicates the simulations are unconditional.

## Caveat / fairness

Not every placeholder is a defect. Deterministic tool dispatch (calculator) and
regex PII redaction as a defense-in-depth layer are legitimate. The finding is
scoped to nodes that **advertise a capability** (LLM agency, model-based multimodal,
formal privacy guarantees, real federation, real benchmarking) **but simulate it in
the run path** — that is the `zero-tolerance` Rule 2 surface.

## Disposition (user-gated per value-prioritization MUST-3/MUST-4)

F8 Milestone B has real residual value. Options are the user's call:
1. **Scope + implement** real backends for the simulated clusters (multi-session;
   federated network, CLIP/BLIP multimodal, real eval harness, LLM synthesis, DP noise).
2. **Right-size the surface** — remove/quarantine over-claimed nodes & guarantees
   (e.g. drop "homomorphic encryption" from PrivacyRAG docs; mark simulated nodes
   experimental) so the public API stops advertising what it doesn't perform.
3. **Hybrid** — implement the high-value real backends, deprecate the rest.

**Receipt:** this file. Audit commands + counts reproduced inline above.
