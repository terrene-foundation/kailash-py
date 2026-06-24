# Wave 3 — Sub-wave 3a (optimized.py from_function migration) — CONVERGED 2026-06-10

Value-anchor: brief _"provably correct, not merely importable"_ + `04-validate/13` DECISION (migrate
brittle f-string `"code"` codegen → `PythonCodeNode.from_function`; root-cause fix for #1117 publish-nothing
/ #1123 brace-escape / #1118 import-trap). BUILD repo — working-tree only; commit stays with the user.

## Delivered (S1 + S2)

All 11 `"code"` codegen blocks across the 4 real-content optimized node classes migrated to
`PythonCodeNode.from_function`:

- **S1** — CacheOptimizedRAGNode (3) + AsyncParallelRAGNode (2). `_generate_cache_keys`, `_decide_cache_use`,
  `_aggregate_cache_result`, `_build_execution_plan`, `_combine_strategy_results` (+ `_make_result_combiner`
  synthetic-signature factory for dynamic per-strategy inputs).
- **S2** — StreamingRAGNode (3) + BatchOptimizedRAGNode (3). `_build_streaming_plan`, `_progressive_retrieve`,
  `_format_stream_chunks`, `_organize_batches`, `_process_batches`, `_format_batch_results`.

`grep -c '"code":' optimized.py` = **0**. Direct Tier-1 unit tests per new fn + Tier-2 end-to-end tests on
the production path (real LocalRuntime, top-level input) with red-pre proofs. optimized suite: **84 passed**;
full RAG suite **1180 passed**; ruff clean; `src/kailash/` untouched (base.py not edited).

## KEY LEARNING (G2 — wave-loop) — the latent #1117 defect is SYSTEMATIC

Every one of the 4 optimized classes carried the SAME latent #1117 phantom-port bug: downstream edges read
a top-level port (`execution_plan`, `streaming_plan`, `progressive_results`, `batch_plan` ×2, `batch_results`)
that the codegen NEVER published — it only ever published the flat `result` port → the value was **silently
dropped** at runtime. The held in-place #1117 patches (Waves 1-2) only covered the nodes those waves touched;
**the un-migrated compute nodes ALL carried the phantom-port bug**. Re-wired 6 edges to `result.<key>`,
proven RED via phantom-port red-pre tests (runtime logs `Source output 'X' not found … Available: ['result']`

- honest default).

**Implication for 3b/3c:** the phantom-port-check (playbook step 3) is LOAD-BEARING for every remaining shard
— expect the same latent #1117 defect in the other un-migrated real-content files (graph/eval/query_processing
compute stages, workflows, strategies, conversational/agentic compute, advanced). Each shard MUST enumerate
every `add_connection` source-port and confirm it resolves to a real returned key or a real node port.

## Redteam convergence receipts (durable — verify-resource-existence MUST-4)

Posture: **L5_DELEGATED**. G1 ran to convergence (R1 substantive + LOW-1 fix + R2 clean).

- **R1 security-reviewer** — task `a16e6cf90586cd3e2` — **APPROVE**, 0 CRIT/HIGH/MED/LOW (migration is a net
  security improvement: removes runtime string-exec sink + #1123 brace-escape class; all lifted fns pure,
  offline, honest-default; no new sinks/secrets/egress; the two `exec()` sites are test-controlled SDK-codegen
  execution with literal namespaces).
- **R1 reviewer** — task `af702a29c6fdc91fb` — **APPROVE**, 0 CRIT/0 HIGH/0 MED, 1 LOW (exhaustive 11-block
  behavior-equivalence — all EQUIVALENT, several HARDENED against latent crashes; 14/14 edges resolve to real
  ports; no vestigial params; red-pre load-bearing). LOW-1 = `metadata.strategies_used` semantics drift
  (metadata-only, no consumer).
- **LOW-1 fix** — restored `strategies_used` to behavior-equivalent all-wired semantics
  (`[s for s in strategies if s in strategy_results]` ≡ original `list(strategy_results.keys())`); fusion still
  driven by truthy `collected` so fused output byte-identical. 84 passed, ruff clean.
- **R2 reviewer** — task `a4e54828ad530f574` — **APPROVE (clean)** — LOW-1 confirmed closed behavior-equivalently,
  no new finding, suite green, 0 codegen, phantom-port closures resolve to real returned keys. **R1→R2 converged.**

## G4 — re-rank of remaining Wave 3 sub-waves (unchanged; REINFORCED by the G2 learning)

The systematic-phantom-port learning REINFORCES the existing value-rank (latent-#1117 files first):

- **3b — S3 graph(4) + evaluation(3)** [both flagged latent-#1117 in-pass `14:329` — HIGHEST] → **S4 query_processing(6)** → **S5 workflows(6) + strategies(3)**.
- **3c — S6 conversational(5) + agentic(3) + advanced(2)**.
  Each shard behind its own inter-wave gate (G1-G4). F33 (`register_node` typing erasure) remains non-blocking
  (pyright non-gating; the 11 `from_function unknown attr` warnings are expected), to be filed separately.
