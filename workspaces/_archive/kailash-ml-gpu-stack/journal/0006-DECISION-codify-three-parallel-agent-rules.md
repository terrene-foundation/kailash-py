---
type: DECISION
date: 2026-04-19
created_at: 2026-04-19T23:10:00.000Z
author: agent
session_id: continue-session-2026-04-19
project: kailash-ml-gpu-stack
topic: Codify three rule additions to rules/agents.md from this session's parallel-shard failure modes
phase: codify
tags:
  [
    codify,
    parallel-agents,
    worktree-isolation,
    reviewer-discipline,
    rules-update,
  ]
related_journal:
  [
    0004-RISK-torch-lightning-deviceReport-orphan.md,
    0005-GAP-predictions-device-field-missing.md,
  ]
---

# Codify — three rule additions for parallel-shard agent discipline

## Decision

Three rule additions land in `rules/agents.md`, all phrased per the
`rules/rule-authoring.md` meta-rule (MUST clause + BLOCKED rationalizations

- DO/DO NOT example + `**Why:**` + `Origin:` line):

1. **§ "MUST: Worktree Prompts Use Relative Paths Only"** — agent prompts
   referencing absolute paths bypass `isolation: "worktree"` and write to
   the parent checkout.
2. **§ "MUST: Worktree Agents Commit Incremental Progress"** — agents that
   don't commit before exit lose 100% of work to worktree auto-cleanup.
3. **§ "MUST: Reviewer Prompts Include Mechanical AST/Grep Sweep"** — gate
   reviewers given only the diff miss orphans in OLD untouched lines that
   the new public surface implicitly required.

All 3 are classification_suggestion: global (cross-SDK-applicable to
kailash-rs's parallel agent patterns) and live in `.claude/.proposals/latest.yaml`
for loom/ Gate-1 review.

## Alternatives considered

**Alternative A — Extract worktree rules into a new `rules/worktree-isolation.md` file.**
Pro: rules/agents.md goes from 244 lines back under the 200-line cap. Con: splits
agent-orchestration discipline across two files; the existing `rules/agents.md`
already references `rules/worktree-isolation.md` as a sibling at line 95, so
the file split is a partial migration that future-codify cycles would need to
finish. Decision: keep in agents.md; mark file-length as a LOW follow-up.

**Alternative B — Codify only Pattern 3 (reviewer mechanical sweep) and leave
the two worktree patterns implicit.** Pro: smaller surface change. Con: the
worktree failure modes cost ~300 LOC of lost work this session; without rule-
level enforcement they recur every parallel-shard cycle. Decision: codify all
three.

**Alternative C — Update the `reviewer` agent's knowledge instead of adding
to `rules/agents.md`.** Pro: agent-level updates are more targeted. Con:
agent-level guidance loads only when the reviewer agent is invoked; rule-level
enforcement loads in every session that touches `rules/agents.md` paths. Per
the rule-authoring meta-rule § "Layered" — the failure mode applies to ALL
gate reviewers (reviewer, security-reviewer, gold-standards-validator),
so rule-level is the right layer. Decision: rule-level.

## Why this matters

These 3 patterns are the institutional residue of three concrete dollar-cost
failures this session:

- ~300 LOC of Shard A's SklearnTrainable Array-API rewrite was lost.
  Recovery happened serendipitously because Shard B scope-crept and
  re-implemented it; without that, a 4th sequential agent run would have
  been needed.
- Shard C's UMAP/HDBSCAN work needed orchestrator-side WIP rescue commit
  to survive notification arrival.
- The reviewer's APPROVE verdict on a 940-LOC diff missed a HIGH spec-
  compliance orphan that the `/redteam` mechanical sweep caught in
  4 seconds. The 0.12.0 wheel would have shipped with TorchTrainable +
  LightningTrainable returning `TrainingResult.device = None` for the
  two DL-spine families.

Each of these is now a one-line linguistic tripwire in the rule file.

## Consequences

- Future parallel-shard sessions in either kailash-py or kailash-rs will
  receive worktree + reviewer discipline as part of session-start rule
  loading.
- Cross-SDK distribution via loom/ Gate-2 is gated on human classification.
  The proposal explicitly tags all 3 rules as `classification_suggestion: global`.

## Outstanding follow-ups (not blocking codify)

- 0005-GAP: `Predictions.device` field missing — 0.12.1 work.
- LOW: `rules/agents.md` is now 244 lines (over the 200-line cap from
  `rules/cc-artifacts.md`). Future codify may extract the worktree sections
  into `rules/worktree-isolation.md`.

## For Discussion

1. **Counterfactual**: If these 3 rules had been in `rules/agents.md` at
   the start of this session, would Shard A's work have survived? Almost
   certainly yes — the prompt would have included the relative-path
   directive and the commit-before-exit directive. Net session cost would
   have dropped by ~1 hour of recovery work.

2. **Data-referenced**: This session ran 5 parallel ml-specialist agents
   total (Shards A/B/C round 1, plus 2 background reviewers). 3 of 3 round-1
   shards truncated at 250-370k tokens — a 100% truncation rate. The
   `rules/autonomous-execution.md` capacity bands say ≤500 LOC load-bearing,
   but each shard was ~300-400 LOC. The token budget exhausted before the
   LOC budget. Question for next codify: should `autonomous-execution.md`
   add a "context-token budget separate from LOC budget" clause? Filed as
   open question; not part of this codify because the evidence base is one
   session.

3. **What would a 4th rule look like?** Spec-completeness in plan
   decomposition — the punch list named items 3/4/5/7/8 covering 5 of 7
   Trainable families; Torch + Lightning weren't called out but the spec
   mandate "every fit returns one" applied to them too. Could become a
   `rules/specs-authority.md` MUST: "Plans MUST enumerate EVERY existing
   call site of each public surface the spec touches, not only the
   sites in the explicit todo list." Decision: defer to next codify;
   evidence base is one occurrence and the failure was caught by /redteam.
