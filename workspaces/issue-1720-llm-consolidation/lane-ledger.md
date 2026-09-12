# Lane Ledger — cont-33

Lane-keyed per `orchestration-launch-ledger.md` MUST-1. The row unit is the LANE
(the ceiling-bound worktree+branch), NOT the agent and NOT the task. Ceilings bind
lanes; agents are unbounded (MUST-6).

| lane | branch | tasks (issues) | agents (status) | lane status |
| --- | --- | --- | --- | --- |
| L1-rest | fix/rest-pagination | #2230, #2231 | (mini-orchestrator: fans out internally) | in-flight |
| L2-df | fix/dataflow-warns | #1971, emit-forensics | (mini-orchestrator: fans out internally) | in-flight |

## Packing rationale (MUST-6)

4 dispatchable tasks → 2 ceiling slots, NOT 4. Two lanes, each a mini-orchestrator.

- **#2230 + #2231 are CO-LOCATED, not merely packed.** Both touch
  `src/kailash/nodes/api/rest.py`. Splitting them across lanes would guarantee a
  merge conflict on the same file — so bound (c) (joint revert-safety on one
  branch) forces them together rather than merely permitting it.
- **#1971 + emit-forensics are packed by disjointness.** `packages/kailash-dataflow/**`
  and `.claude/bin/**` share no file with each other or with L1, so one ceiling
  slot carries both safely.

## Ordering constraint carried into L1 (do NOT reorder)

#2230's shape fix ARMS a latent credential-exfiltration path: `_handle_async_pagination`
follows a response-body-supplied link with the caller's headers and no origin
validation, unreachable today only because the shape bug keeps the link out of
metadata. The guard lands BEFORE or WITH the shape fix, never after.
