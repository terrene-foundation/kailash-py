# Wave 3 — `from_function` migration of real-content RAG codegen — COMPLETE 2026-06-10

Value-anchor: brief _"provably correct, not merely importable"_ + `04-validate/13` DECISION (migrate brittle
f-string `"code"` codegen → `PythonCodeNode.from_function`; root-cause fix for #1117 publish-nothing /
#1123 brace-escape / #1118 import-trap). User-approved program greenlight (this session). BUILD repo —
**held UNCOMMITTED in the working tree; commit stays with the user.**

## Outcome — 42 real-content codegen blocks migrated across 9 files, ALL sub-waves converged

| Sub-wave | Files                                                      | Blocks | Gate                      | Receipt          |
| -------- | ---------------------------------------------------------- | ------ | ------------------------- | ---------------- |
| **3a**   | optimized.py                                               | 11     | R1→R2 converged           | `04-validate/17` |
| **3b**   | graph, evaluation, query_processing, workflows, strategies | 21     | R1→R2 converged           | `04-validate/18` |
| **3c**   | conversational, agentic, advanced                          | 10     | R1(+LOW fix)→R2 converged | this doc         |

`grep -c '"code":'` = **0** across all 9 real-content files; `from_function` uniformly **bare** (F33-forward-clean).
Full RAG suite (unit+integration): **1250 passed**, 0 failed; ruff clean; `src/kailash/base.py` untouched throughout.

## What the migration delivered (provably-correct value)

1. **Structural elimination of 3 bug classes** — every `"code": f"""..."""` PythonCodeNode block became a real
   typed module-level function: #1117 (publish-nothing — `return` IS the published `result`), #1123 (f-string
   brace-escape — gone), #1118 (import-trap — imports resolve in the function's namespace, e.g. networkx now works).
2. **12 latent #1117 phantom-port defects CLOSED** (downstream edges read ports the codegen never published →
   output silently dropped): 4 in optimized (3a), 2 in workflows AdvancedRAG (3b — the strategy router/validator
   never resolved the strategy), 6 in the agentic cyclic graph (3c). All proven via red-pre tests.
3. **Graph nodes UNLOCKED for end-to-end execution** — `graph_builder`/`graph_retriever` now run OUTSIDE the
   PythonCodeNode `exec()` sandbox, so `import networkx` works → the full graph workflow is now runnable under
   real LocalRuntime (impossible pre-Wave-3).
4. **Security improvement** — removed the runtime string-exec path + the #1123 brace-escape injection surface;
   closure factories bind typed objects (no source-string interpolation); the agentic `calculate` tool verified
   as a genuine AST-walked whitelisted safe-evaluator (no eval/exec/compile). CSPRNG session_id preserved.
5. **~19 orphaned tests rewritten** to exercise production from_function nodes / lifted fns (orphan-detection
   Rule 4a) — preserving + often strengthening assertion intent (source-grep → behavioral).
6. **type:ignore normalized bare** across all 9 files (no F33 unused-ignore debt when F33 lands).

## Convergence receipts (durable — verify-resource-existence MUST-4)

Posture **L5_DELEGATED** throughout. Each sub-wave gate ran reviewer + security-reviewer to 2-consecutive-clean.

- 3a: reviewer `af702a29c6fdc91fb` + security `a16e6cf90586cd3e2` (R1) → R2 `a4e54828ad530f574`. (`04-validate/17`)
- 3b: reviewer `a83c2179a9733bb6f` + security `a035ef5cdf5bb7a90` (R1) → R2 `aeffae4be4702d2e8`. (`04-validate/18`)
- 3c: reviewer `ae27623839064b59f` + security `a7ecce3b85e155709` (R1, security found 1 LOW = stale CSPRNG
  docstring, FIXED) → R2 `aa992ca899c223bdd` (clean). All R1 verdicts: APPROVE; the migration is a net
  security improvement per both security passes.
- Wave-process learnings (wave-loop G2): integration tests are NON-NEGOTIABLE per shard (S3 unit-green while
  integration was BROKEN — caught at the gate, would have shipped a regression); the systematic phantom-port
  enumeration is load-bearing every shard; session-limit mid-flight recovery via SendMessage-resume preserves
  migration context.

## Remaining (explicitly OUT of Wave 3 scope)

1. **F33 — `register_node` generic-typing erasure** (base.py:2719). `@register_node()` erases node subclasses to
   `type[Node]`, so `PythonCodeNode.from_function` emits a non-gating pyright `attr-defined` warning at every call
   site (now uniformly bare). NON-BLOCKING (pyright not gated). RECOMMEND: file as a standalone core-SDK typing
   fix (generic TypeVar `Callable[[type[T]], type[T]]`, typing-only) + cross-SDK kailash-rs check. Drafting the
   issue is ready on request; filing is human-gated.
2. **Wave 4 — simulated-content nodes** (multimodal/federated/similarity ColBERT/Dense/CrossEncoder/realtime —
   still retain `"code":` codegen BY DESIGN, out of this migration's scope). strip / experimental-flag / build-real
   is a **PRODUCT CALL (user)** per `04-validate/13`.
3. **F31-FU4 / F31-FU5** — non-RAG false-green-adapter audit; hybrid_search numpy eager-import. Forest items.

## Disposition

Wave 3 (the migration program the user approved this session) is at its **verified-done terminus**: all 42
real-content blocks migrated, all 3 sub-waves converged, 1250 tests green. Held uncommitted (BUILD repo) alongside
F31-FU2 (the 205 direct parser/composer unit tests, converged earlier this session). Commit/push stays with the user.
