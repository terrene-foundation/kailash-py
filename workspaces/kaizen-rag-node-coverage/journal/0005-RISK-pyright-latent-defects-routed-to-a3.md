# RISK — Pyright surfaced latent rag defects during A1; routed to reviewer + A3

Date: 2026-05-19
Phase: 03 /implement — cycle 1 (Wave 1: A0 + A1 + A1-core)

## Wave-1 landing state

- **A0** complete — `01-analysis/04-A0-r4-table.md`: 30 code-template
  f-strings, 4 R4 LEAKs (all `privacy.py` → B9a). strategies.py:240
  re-classified BENIGN by AST (corrected the round-1 + plan-draft estimates).
- **A1** complete — branch `feat/f8-a1-rag-node-constructors`, 14 commits.
  All 40 `Node`-subclass `super().__init__(name)` sites fixed (`grep` = 0 in
  every rag module; realtime held 2 not 1 — brief undercount caught).
  Latent `self.config` vs `RAGConfig` collision fixed in strategies
  (renamed `self.rag_config`; zero-tolerance Rule 4). Smoke test hardened
  (`test_representative_rag_node_constructs`): 34 passed / 2 skipped
  (WorkflowNode modules → A2 un-skips) / 0 failed. All commits through
  pre-commit (Black/isort/Ruff/Tier-1) — no `--no-verify`.
- **A1-core** complete — branch `feat/f8-a1core-mcp-constructors`, 1 commit
  `16ec633de`. 2 MCP constructors fixed, `# type: ignore[call-arg]` removed,
  11 MCP middleware tests pass.

## RISK — Pyright latent-defect surface (NOT yet dispositioned)

Pyright flagged ~25 issues across realtime/query_processing/router/
strategies/similarity/advanced/agentic. Provisional classification (to be
PROVEN by the cycle-1 reviewer gate via `git show 0f906a1e0:<file>`, per
`zero-tolerance.md` Rule 1c — "pre-existing" requires a pre-session SHA):

- **Likely pre-existing (2-month-dead code; A1 never touched these lines):**
  `_create_workflow()` methods typed `-> Node` but returning `Workflow`
  (realtime:371, query_processing:231/429/665/941/1204/1385, similarity ×6,
  advanced:43 unresolved `...workflow.graph` = the S2 stub); `self.name`
  attr-access (router:102 — base `Node` exposes `_node_metadata.name`, never
  public `.name`); `self.workflow` attr-access on a `Node` (strategies:
  193/199 — `.workflow` is a `WorkflowNode` attr); possibly-unbound vars
  (realtime:550 `chunk_idx`, advanced:1556 `content`, similarity:506
  `expander_id`).
- **MUST be checked for A1-regression:** any diagnostic on a line A1's
  constructor rewrite touched — the reviewer gate adjudicates.

## Disposition (zero-tolerance-compliant — tracked, not deferred)

1. The cycle-1 **reviewer gate** triages each diagnostic A1-INTRODUCED vs
   PRE-EXISTING with a `git show 0f906a1e0:` proof. A1-introduced → fixed in
   A1's commits BEFORE merge. Pre-existing → item 2.
2. Pre-existing latent defects are routed to **A3 triage** (which already
   owns "failures unmasked once construction works" per the approved plan)
   and fixed in the **owning B-coverage shard** for that module (each B shard
   cleans + covers its module). This is routing to an approved-plan shard
   with a disposition obligation — NOT silent deferral.
3. The unused-import (★) noise is fixed per-module by the owning B-shard's
   cleanup pass.

Rationale: fixing ~25 latent type errors NOW, outside their B-coverage
shards, would be un-sharded B-work in the A1 cycle — exceeding cycle scope
and violating the approved plan's per-module shard structure. The analysis
predicted exactly this latent surface (≥13 HIGH-breakage-risk nodes); the
plan's A3 + per-module B-shards are the structural owner.
