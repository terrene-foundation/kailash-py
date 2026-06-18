# Brief Red-Team — 2026-05-28

Target: `workspaces/kaizen-rag-node-coverage/briefs/00-brief.md`
Triggered by: user-approved /redteam at session start (re-validation passed).
Method: 3 parallel deep-dive verification agents per `rules/agents.md` § Parallel
Brief-Claim Verification (≥3-issue brief). Each agent independently re-grepped /
re-read every factual claim in its cluster against the source tree.

## Severity ledger (15 claims across 3 clusters)

| Sev      | Claim | Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| -------- | ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CRITICAL | L1    | Value-anchor source path `workspaces/kaizen-rag-resurrection/briefs/00-brief.md` does NOT exist; archived to `workspaces/_archive/kaizen-rag-resurrection-superseded-2026-05-26/...`. Verbatim quote IS correct at the archived path. Phantom file-path citation per `rules/spec-accuracy.md` MUST-1.                                                                                                                                                                                                                                        |
| CRITICAL | L2    | Lineage citation `workspaces/issue-891-hybridsearch-collision/journal/0004` does NOT exist; archived to `workspaces/_archive/issue-891-hybridsearch-collision-2026-05-18/journal/0004-DECISION-rag-resurrection-separate-pr.md`. Phantom file-path citation.                                                                                                                                                                                                                                                                                 |
| HIGH     | S5    | "These ~53 classes have been dead since the 2026-03-11 monorepo move; none has a behavioral test" is FALSE as a present-tense claim. 14 unit test files + 14 integration test files exist under `packages/kailash-kaizen/tests/{unit,integration}/rag/` exercising `.run()`. Earliest behavioral commit `ba989f23f` (2026-05-19), continued through F8 B4-B10 (≈10+ commits, e.g. `fc0c46b4a`, `e88bba27a`, `7efb58c3e`, `762d37ee5`). Workstream is mid-execution, NOT pending.                                                             |
| HIGH     | L4    | "RAG nodes whose modules are still commented-out TODOs (`CacheNode`, `ImageReaderNode`)" is FALSE for CacheNode: live registering import at `packages/kailash-kaizen/src/kaizen/nodes/rag/optimized.py:20` (`from kailash.nodes.cache import cache  # noqa: F401 — registers CacheNode`) + string refs at `:147, :213`. Recent commit `29645dbc7` titled "fix(rag): remove dead CacheNode comment + add registering import in optimized (F8 B9c A3 R3-L2)" confirms resurrection shipped. ImageReaderNode IS genuinely absent (0 grep hits). |
| MEDIUM   | S1    | "17 modules" is FALSE; actual is 16 + `__init__.py`. Even the smoke test's own docstring is self-contradictory: `tests/regression/test_rag_resurrection_import_smoke.py:3` says "The 17-module …" then the next line says "all 16 submodules".                                                                                                                                                                                                                                                                                               |
| MEDIUM   | C1    | "~53 classes" is an under-count by 3. Actual: 56 node-derived classes (38 inherit `Node`, 18 inherit `WorkflowNode`). 2 non-node helpers (`RAGConfig`, `RAGWorkflowRegistry`) bring total to 58 classes.                                                                                                                                                                                                                                                                                                                                     |
| MEDIUM   | C3    | Brief's "behavioral coverage = exercise documented public contract" framing is looser than `rules/testing.md:141-145`: rule mandates "every write verified with read-back" for Tier 3 (brief omits read-back) AND includes a "Protocol-Satisfying Deterministic Adapter" carve-out (brief omits the exception).                                                                                                                                                                                                                              |
| MEDIUM   | L5    | Brief line 7 reads "Re-validated and picked up by the user this session (2026-05-19)" — but `git log --since=2026-05-19 -- packages/kailash-kaizen/src/kaizen/nodes/rag/` shows extensive F8 B4-B10 multi-session execution. Brief framing is internally inconsistent with shipped commits. Today's re-affirmation IS genuine, but the workstream has been in flight for 9 days.                                                                                                                                                             |
| MEDIUM   | C5    | Cluster decomposition pattern in scope §: "by module cluster: retrieval-core, graph/agentic, multimodal/federated, privacy/eval, …" — the "…" elides ~13 classes across 4 modules (`optimized`, `realtime`, `workflows`, `conversational`). `registry` has 0 node classes (helper-only) and should be flagged. /todos needs explicit 5-cluster enumeration.                                                                                                                                                                                  |
| TRUE     | S2    | `RealtimeStreamingRAGNode` rename verified at `realtime.py:434-435`; original `StreamingRAGNode` (WorkflowNode subclass) still distinct at `optimized.py:495`. Cross-module collision resolved.                                                                                                                                                                                                                                                                                                                                              |
| TRUE     | S3    | Import-smoke test at `packages/kailash-kaizen/tests/regression/test_rag_resurrection_import_smoke.py` with 5 functions; 8 "representative" nodes named at lines 96-103.                                                                                                                                                                                                                                                                                                                                                                      |
| TRUE     | S4    | PR #1096 (MERGED 2026-05-18 21:39, commit `f0ea4ccf`, "fix(kaizen): resurrect kaizen.nodes.rag (#891 follow-up)") + PR #1097 (MERGED 2026-05-18 22:04, commit `0f906a1e`, "release(kaizen): complete the [rag] extra (2.23.1)") confirmed.                                                                                                                                                                                                                                                                                                   |
| TRUE     | C2    | All 17 module names (16 submodules + `__init__`) verified present, no extras, no missing. (Despite S1's "17 modules" miscount — that was about submodule count, not name list.)                                                                                                                                                                                                                                                                                                                                                              |
| TRUE     | C4    | Shard-budget overflow confirmed. Production code = 17,195 LOC across 16 modules — exceeds the ≤15k surface-area threshold AND will multiply with test code (~2,800+ LOC test orchestration for 56 classes × ~50 LOC each). Decomposition mandatory.                                                                                                                                                                                                                                                                                          |
| TRUE     | L3    | `deploy/deployments/2026-05-19-kaizen-v2.23.0-v2.23.1-rag-resurrection.md` exists; documents both 2.22.0→2.23.0 and 2.23.0→2.23.1 publish runs (success).                                                                                                                                                                                                                                                                                                                                                                                    |
| TRUE     | L6    | F8 scope-out rationale verified in archived resurrection brief (lines 39-57): "Deep per-node behavioral test coverage of the ~53 RAG node classes" explicitly scoped out as recommended follow-up. kaizen-rag-node-coverage faithfully picks it up.                                                                                                                                                                                                                                                                                          |

## Reconciliation

The two CRITICAL phantom citations (L1, L2) violate `rules/spec-accuracy.md`
MUST-1 — every cited file:line MUST resolve against working code. Both source
paths were archived during the 2026-05-26 sweep (per ls of `_archive/`); the
brief was not updated to follow.

The HIGH-severity S5 + L4 findings together signal **the brief is substantially
stale**: the work it describes ("none has a behavioral test", "CacheNode is
commented-out") was true at the 2026-05-18 PR-merge instant but has been
actively executing since 2026-05-19 in the F8 B4-B10 batches. The workstream
is not "ready to pick up" — it is "mid-execution, picking up needs an
audit-gap pass."

The MEDIUM-severity count errors (S1, C1) are minor but should land in the
amended brief for accuracy.

## Recommended next steps (no work executed yet — user gate per `rules/value-prioritization.md` MUST-4)

The brief is stale enough that picking up `/todos`/`/implement` against it as
written would burn shard budget on work already shipped. The disposition
that respects the materialized value-anchor (still valid: "the RAG capability
the user chose to preserve is provably correct, not merely importable") is to
**run an audit-gap pass first, then re-plan against the actual remaining
surface**.

Two paths forward — both preserve the value-anchor:

**Path A — Audit-gap first, then plan against the real gap (recommended)**

- One-shard audit: enumerate the 56 node classes; cross-reference against the
  14+14 existing test files; for each class, classify as
  `behavioral-covered-Tier-2` / `behavioral-covered-Tier-3` /
  `import-only` / `uncovered`. Report coverage matrix.
- For each `uncovered` / `import-only` class, decide: shard into new tests OR
  flag as out-of-scope with rationale (e.g. abstract base class, deprecated).
- Amend brief to reflect actual state: drop the L1/L2/L4 phantom citations,
  fix the S1/C1 counts, replace the "none has a behavioral test" framing
  with the coverage-matrix output.
- Then `/todos` against the actual remaining gap (likely much smaller than
  53 classes × 2 tiers).

  Pros: respects work already shipped; avoids duplicating F8 B4-B10 effort;
  delivers an honest current-state brief as the next session's anchor.

  Cons: one extra audit-shard (~one session) before any new test code lands;
  user sees no "new feature value" from the audit pass — but the audit
  closes the staleness gap that would otherwise burn 5–10 sessions of
  re-discovery.

**Path B — Patch the brief in-place, re-validate, then /todos against amended scope**

- Apply the 5 brief corrections (L1, L2 repoint to `_archive/`; S5 → "covered
  in F8 B4-B10, audit remainder"; L4 → drop CacheNode from out-of-scope;
  S1/C1 number fixes).
- Re-run the re-validation gate on the amended brief.
- /todos against the amended scope.

  Pros: keeps the workspace's existing 4-stage analysis/plans/validate scaffolding;
  no separate audit shard.

  Cons: the amendments are non-trivial (5 corrections including 2 CRITICAL)
  and Path B assumes the orchestrator already knows the coverage matrix —
  which it doesn't without the Path A audit. Path B without the audit is
  guess-and-amend; Path B with the audit IS Path A.

Recommend **Path A**. The audit pass is the structural defense against the
"brief stale + workspace mid-flight" failure mode — it converts an unknowable
"what's left?" into a coverage matrix the next /todos can shard against.

Implications of Path A:

- One audit-shard session (~500-1000 LOC of analysis output, no production code)
- The brief gets amended at audit-pass conclusion with the actual coverage
  matrix as the new factual anchor
- The 5 lower-severity corrections (L4 CacheNode out-of-scope basis, S1/C1
  counts, C3 testing.md interpretation, C5 cluster decomp, L5 "this session"
  framing) fold into the same brief-amendment commit
- L1 + L2 phantom citations get repointed to `_archive/` paths in the
  amendment (no archive un-doing needed)

Open question for the user: Path A audit-first, OR something else?
