# Wave 3 — Sub-wave 3b (graph + evaluation + query_processing + workflows + strategies) — CONVERGED 2026-06-10

Value-anchor: brief _"provably correct, not merely importable"_ + `04-validate/13` DECISION (migrate brittle
f-string `"code"` codegen → `PythonCodeNode.from_function`; root-cause fix for #1117/#1123/#1118). BUILD repo —
working-tree only; commit stays with the user.

## Delivered — 21 compute-codegen blocks migrated across 5 files

- **S3** graph.py GraphRAGNode (3) + evaluation.py RAGEvaluationNode (3). Tasks `acf662f162121fbef` (recovered
  from a mid-flight session-limit cutoff — integration tests were left broken; fixed: 2 orphaned eval tests +
  3 graph tests rewritten to exercise production from_function nodes per orphan-detection Rule 4a). **ROOT-CAUSE
  WIN:** `graph_builder`/`graph_retriever` now run OUTSIDE the PythonCodeNode `exec()` sandbox → `import networkx`
  works → the graph nodes are NOW executable end-to-end under real LocalRuntime (impossible pre-Wave-3).
- **S4** query_processing.py 6 processor blocks. Task `a5df64b758d4b5cf4`. Fixed 2 orphaned regression tests;
  dropped a vestigial `domain` param.
- **S5a** workflows.py 6 blocks (Advanced/Adaptive/Pipeline). Task `addc3efd1303432e7`. **CLOSED 2 more latent
  #1117 phantom-port defects** (AdvancedRAGWorkflowNode `quality_analyzer → result.analysis` ×2 — the strategy
  router + validator were reading the wrong nesting level; the strategy never resolved). Rewrote 1 orphaned test.
- **S5b** strategies.py 3 blocks. Task `a21a00cbeb2c99832`. Rewrote 2 orphaned tests; phantom-ports already-correct.

**type:ignore normalization (orchestrator):** S5a had added `# type: ignore[attr-defined]` to its from_function
calls; graph/eval/query_processing also carried them (Wave-2.5/shard-added). Normalized ALL from_function calls
to **bare** across all 6 RAG files (the F33 `register_node` erasure warning is non-gating; bare is F33-forward-clean
— no unused-ignore debt when F33 lands). Pre-existing `.workflow`-property ignores kept.

`grep -c '"code":'` = **0** across all 5 files. Full RAG suite (unit+integration): **1240 passed**, 0 failed;
ruff clean; base.py untouched.

## KEY LEARNING (G2 — wave-loop)

1. **The systematic latent-#1117 defect held** — S5a found+closed 2 MORE phantom-port defects (4 optimized in 3a +
   2 workflows here = 6 total). The phantom-port enumeration is load-bearing; do it for every shard in 3c too.
2. **Integration tests are NON-NEGOTIABLE per shard** — S3's unit tests passed (156) while integration was BROKEN
   (5 failures: orphaned tests + a graph synthesizer disabled-path issue). Unit-green ≠ shard-done; the orchestrator
   MUST run integration before accepting any shard (caught here, would have shipped a regression otherwise).
3. **Session-limit mid-flight recovery** — S3 hit an account/session limit mid-work; resuming the same agent (SendMessage,
   fresh account) with the precise broken-test list was more efficient than relaunch (preserved migration context).
4. **from_function = capability unlock, not just de-risk** — lifting out of the `exec()` sandbox makes
   import-dependent nodes (networkx) actually runnable end-to-end. Real correctness gain, not cosmetic.

## Redteam convergence receipts (durable — verify-resource-existence MUST-4)

Posture: **L5_DELEGATED**. G1 ran to convergence (R1 fully clean → R2 additive-coverage clean = 2 consecutive).

- **R1 security-reviewer** — task `a035ef5cdf5bb7a90` — **APPROVE**, 0 CRIT/HIGH/MED/LOW (full-file review of all 5
  src; no new exec/sink; honest defaults no-fabrication; closure-bound factories bind typed objects → injection
  surface removed; net security improvement). + durable secret-sweep grep receipt: CLEAN.
- **R1 reviewer** — task `a83c2179a9733bb6f` — **APPROVE**, 0 CRIT/HIGH/MED/LOW (all 7 mechanical sweeps PASS;
  the 2 workflows.py #1117 closures VERIFIED REAL; graph disabled-synthesizer path safe; orphaned tests correctly
  rewritten not weakened; 1240 passed).
- **R2 reviewer (additive)** — task `aeffae4be4702d2e8` — **APPROVE (clean)** — deep behavior-equivalence on the
  remainder blocks (graph build/retrieve, eval collect/precision, all 6 query_processing processors, workflows
  aggregator/formatter/config-processor) — all EQUIVALENT, zero silent computation change; re-confirms hold.
  **R1→R2 converged.**

## G4 — re-rank remaining Wave 3 (unchanged)

- **3c — S6 conversational(5) + agentic(3) + advanced(2)** = ~10 compute blocks, the FINAL real-content sub-wave.
  agentic.py was the O5 false-green file (Wave 2.5 found 5 broken output stages there); its from_function parsers
  are already landed — S6 migrates only the remaining COMPUTE blocks. Apply the phantom-port + integration-test +
  orphaned-test discipline from 3a/3b.
- After 3c converges: Wave 3 COMPLETE (all real-content codegen migrated). Then F33 (filed separately) + Wave 4
  (simulated nodes, product call) remain — both out of Wave 3 scope.

## Wave 3 cumulative (3a + 3b)

**32 codegen blocks** migrated to from_function across 6 files (optimized 11 + graph/eval/qp/workflows/strategies 21);
**6 latent #1117 phantom-port defects** closed; graph nodes unlocked for end-to-end execution; ~11 orphaned tests
rewritten; type:ignore normalized bare; 3 redteam convergences (3a, 3b — each R1→R2). Held UNCOMMITTED (BUILD repo).
