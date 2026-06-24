# DECISION — /implement cycle 1 merged; CLASS5 (MCP process/run) routed to A3

Date: 2026-05-19
Phase: 03 /implement — cycle 1 complete

## Merged to main (`e1dba643f`)

- **PR #1098** (A1) — 38 `kaizen.nodes.rag` `Node`-subclass constructors
  repaired to canonical keyword form across 13 modules; `strategies.py`
  `self.config`/`RAGConfig` collision fixed; `router.py` `llm_model` default
  env-sourced (LOW-1); import-smoke hardened to instantiate ≥1 node/module
  (34 passed / 2 skipped).
- **PR #1099** (A1-core) — `MCPToolNode`/`MCPResourceNode` constructors
  repaired; 2× `# type: ignore[call-arg]` removed; `MCPToolNode.get_parameters`
  reads the config bag (MED-1). MCP suite 11 passed / 1 xfailed.
- A0 — `01-analysis/04-A0-r4-table.md`: 30 code-template f-strings, 4 R4
  LEAKs (all `privacy.py` → B9a). No source edit.

Both PRs: reviewer + security-reviewer APPROVE-MERGE; 0 introduced
regressions (40 Pyright diagnostics all proven pre-existing via
`git show 0f906a1e0:`). Worktrees removed; branches deleted.

## CLASS5 — new defect class surfaced; routed to A3 (scope amendment)

A1-core's instantiation verification surfaced a 4th defect class beyond
R1/R2/R3/R4: `MCPToolNode` + `MCPResourceNode` implement `process()` but
`kailash.nodes.base.Node.run` is `@abstractmethod` — so the classes are
non-instantiable even with the constructor fixed (`TypeError: Can't
instantiate abstract class`). Proven pre-existing (`git show 0f906a1e0:`).

A1-core's constructor fix is correct and merged; the `xfail(strict=True)`
regression test in `test_server_enhanced.py` documents that MED-1's fixed
code path is unreachable until CLASS5 is resolved — `strict=True` forces the
A3 session to un-mark it.

**Plan amendment:** shard A3's charter is widened from "R3 + R4 disposition"
to also cover **CLASS5 — the `process()`/`run()` reconciliation for the 2 MCP
classes**. A3 must determine whether `process` is the stale name of `run`
(rename/alias) and verify both MCP classes instantiate + the xfail test
un-marks to a real pass. The rag package itself is NOT affected — rag
`Node`-subclasses implement `run()` (verified: similarity.py 7×`run`, 0×
`process`); CLASS5 is confined to the 2 kailash-core MCP classes.

## Cycle 1 status vs plan

- A0 ✅ · A1 ✅ · A1-core ✅ (constructor contract; CLASS5 → A3)
- Remaining Milestone A: A2 (13 WorkflowNode constructors), A3 (R3 + R4 +
  CLASS5 triage), A-S2 (advanced.py placeholder, folds into B6).
- Milestone B: B1–B10 behavioral coverage. Release: R1.

Next cycle: A2 (now unblocked — A1 is on main; A2 edits the same rag files,
the merge dependency is satisfied).

## Pre-existing Pyright surface (journal/0005)

~40 pre-existing latent type defects in rag modules remain (Workflow-vs-Node
return types, `self.name`/`self.workflow` attr-access, possibly-unbound
code-template vars). Confirmed pre-existing by the cycle-1 reviewer. Routed
to A3 triage + owning B-coverage shards per journal/0005 — not A1 regressions.
