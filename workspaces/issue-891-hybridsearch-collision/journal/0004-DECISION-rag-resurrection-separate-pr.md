# DECISION — kaizen.nodes.rag resurrection is a separate PR (this session)

Date: 2026-05-19
Phase: /implement (T3 re-disposition)

## Investigation result

User asked whether `kaizen.nodes.rag` is useful or replaced before deciding.
Findings:

- The package defines **53 RAG node classes** — GraphRAG, AgenticRAG,
  FederatedRAG, MultimodalRAG, privacy-preserving RAG, ColBERT retrieval,
  HyDE, cross-encoder rerank, query decomposition, RAG evaluation/benchmark,
  etc. A substantial, ambitious RAG toolkit.
- **Not replaced.** The only other retrieval code in kaizen is
  `kaizen/retrieval/` — a single `SimpleVectorStore`. No equivalent for the
  53 advanced RAG nodes exists anywhere else in kaizen.
- **Dead-on-arrival, not killed-by-us.** Un-importable since `b553104c`
  (2026-03-11 monorepo move) — the move relocated the package into kaizen but
  never repointed its `kailash.nodes.*` imports. Git history since: one commit,
  a bulk 819-file reformat. Zero functional work. Not imported, referenced, or
  documented anywhere. Zero bug reports in 2+ months.
- Full extent: 17 modules, 14 with broken relative imports (~40 import lines);
  `rag/__init__.py` eagerly imports all 17.

## Decision

User-gated 2026-05-19: **resurrect `kaizen.nodes.rag` as a separate PR in this
session**, AFTER the #891 collision PR merges.

- The #891 PR (this workstream) drops `StreamingRAGNode` / rag entirely —
  StreamingRAGNode is NOT a live collision (dead code never registers), so the
  core guard never sees it. The #891 PR ships the 3 LIVE collision fixes
  (HybridSearch, BulkUpsert, Aggregate) + the guard.
- The partial import-repair edits to `realtime.py` / `optimized.py` were
  reverted — they belong in the resurrection PR.
- The resurrection PR: repair ~40 broken imports across 14 modules, functionally
  validate the 53 node classes, add test coverage. Note: once the package is
  importable, `StreamingRAGNode` (realtime ↔ optimized, cross-module) becomes a
  LIVE collision and the #891 guard would crash on it — so the resurrection PR
  MUST also rename realtime's `StreamingRAGNode` → `RealtimeStreamingRAGNode`
  (the `rag/__init__.py:177` `as`-alias already anticipates the name).

## Sequencing

1. #891 PR: T4 guard + T5 test + T6 changelogs → merge.
2. Resurrection PR: rag import repair + StreamingRAGNode rename + functional
   validation + tests → merge.

T7 (was "draft issue for rag validation") is superseded — the user chose
execution over an issue.
