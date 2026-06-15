---
type: AMENDMENT
date: 2026-06-15
author: agent
project: issue-1316-eatp08-marker-regime-py
topic: Cross-repo re-read of mint EATP-08 spec §5/§6 to lock exact V1-V9 vector table for Shard 2 coverage map (H1)
phase: implement
tags: [eatp-08, cross-repo, shard-2, coverage-map, v-table]
relates_to: 0002-DECISION-cross-repo-authorized-mint-spec-read
---

# 0005 — AMENDMENT: mint spec §5/§6 re-read for exact V1-V9 table

cross-repo-authorized: terrene-foundation/mint

Extends the standing grant in journal 0002 (verbatim user instruction "check
~/repos/terrene/mint"; scope: "read only the EATP-08 algorithm-identifier spec
(+ adjacent conformance refs if cited)").

- **Why now**: Wave-2 Shard 2e (the H1 red-team coverage-map gate) requires the
  EXACT V1-V9 → behavior table. The in-repo distillation
  (`01-analysis/02-spec-locked-facts.md` §6) pins V6/V7/V9 precisely but does NOT
  individually define V1-V5. Assigning V-ids to vector entries without the spec
  table would be an unverifiable factual claim landing in a durable cross-SDK
  conformance file (`verify-claims-before-write.md` MUST-1). The exact table
  cannot be derived from in-repo sources.
- **Action (bounded, in standing-grant scope)**: READ-ONLY re-read of
  `~/repos/terrene/mint/workspaces/envoy-parity/03-drafts/finalized/eatp-08-v1.1.md`
  §5 (resolver dispatch + §5.3 error codes) and §6 (conformance vectors V1-V9 +
  levels). These are "adjacent conformance refs" of the EATP-08 algorithm-identifier
  spec already cited in the /analyze distillation (`:259-268`, `:272`, `:302-311`).
- **Scope**: read only; no writes / no `gh` / no edits to the mint repo.
- **Disposition of findings**: the exact V-table is recorded into
  `01-analysis/02-spec-locked-facts.md` (in-repo durable record) so future sessions
  do not need a fresh cross-repo read.
