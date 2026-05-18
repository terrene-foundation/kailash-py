# 09 — Parallel Agent Bundles for Non-Shard Follow-Ups

When a session contains many small, independent fixes — use-feedback triage, codify follow-ups, post-redteam corrections, README/skill polish, scattered config nudges — the right shape is a single dispatch round of parallel non-shard agents, not a sequenced list of todos. This guide names the pattern and the decision matrix.

The pattern is judgment-driven, not rule-bound. The decision is "shard vs non-shard bundle," and the wrong choice has different costs in each direction. Sharding trivial work fragments attention into context-switches that buy nothing. Bundling load-bearing work overflows the per-shard invariant budget defined in `rules/autonomous-execution.md` § Per-Session Capacity Budget and reproduces the Phase 5.11 orphan failure mode at smaller scale.

## When To Use The Bundle Pattern

Use the parallel non-shard bundle when ALL of the following hold:

1. **N items, each describable in 1–2 sentences.** If any single item needs three sentences to scope, that item is a shard, not a bundle entry.
2. **Items are independent.** Item B's correctness does not depend on item A's output. Each agent reads only the files relevant to its item.
3. **Each item is ≤ ~150 LOC of changes.** Above that, the per-item LOC starts approaching the per-shard load-bearing-logic budget; size up.
4. **Each item touches ≤ 2 files of correctness-relevant surface.** A 5-file refactor is not a bundle entry, even if the LOC is small.
5. **No cross-item invariants.** If item A and item B both have to preserve the same tenant-isolation contract or the same audit-row shape, they belong in one shard, not two parallel agents.
6. **Feedback loops fire per agent.** Each agent has its own `cargo check` / `pytest -k` / type-check pass that runs to ground-truth the change before exiting.

The canonical session that motivates this guide bundled 8 follow-up items as 6 parallel agents (two were done inline / serialized for dependency reasons). Implementation wall-clock: ~5 minutes to dispatch + ~5 minutes for the longest agent. Sequential todos would have taken ~45 minutes minimum.

## When NOT To Use The Bundle Pattern

Drop back to a sharded plan (see `rules/autonomous-execution.md` § Per-Session Capacity Budget) when ANY of the following hold:

- The work has cross-shard invariants that all shards must preserve simultaneously (tenant isolation, audit, redaction, classification, error taxonomy).
- The work involves load-bearing logic ≥ 500 LOC in a single conceptual change.
- The call-graph reasoning crosses 3+ files for any single item.
- The items are sequenced by dependency (item B reads item A's output) — these are todos, not a bundle.
- Any single item takes more than 3 sentences to describe.

The shard budget exists because beyond it the model stops tracking invariants and pattern-matches instead. The bundle pattern is _not_ a way around the shard budget — it is a way to handle work that was never shard-shaped in the first place.

## Decision Matrix

| Trigger                                                  | Shape        | Why                                                              |
| -------------------------------------------------------- | ------------ | ---------------------------------------------------------------- |
| 8 small independent fixes, each 1–2 sentences            | Bundle       | Independence + small size makes parallel dispatch the right move |
| 1 conceptual change, 800 LOC, 5 invariants               | Single shard | Load-bearing logic — invariant budget governs                    |
| 1 conceptual change, 2000 LOC, 8 invariants              | Multi-shard  | Exceeds invariant budget; partition by call-graph                |
| 14 CRUD repositories generated from one pattern          | Single shard | Boilerplate stamps from one pattern; no per-item invariants      |
| 6 service migrations of one scheduler refactor           | 6 shards     | Each service has its own invariants to preserve                  |
| 4 dependent fixes (B reads A, C reads B)                 | Sequential   | Dependency forbids parallelism; not a bundle                     |
| 5 use-feedback items, mostly skill rewrites + 1 rule fix | Bundle       | Independent + small + 1–2 files each                             |
| Crypto-pair test (encrypt + decrypt round-trip)          | Single shard | Cross-test invariant (round-trip identity) lives in one place    |

## Dispatch Mechanics

For the bundle pattern, dispatch all agents in a single message — multiple `Task` tool calls in one response. Sequential dispatch defeats the purpose; parallel is the entire point.

```
# Dispatch round (all in one message):
Agent({subagent_type: "...", isolation: "worktree", prompt: "fix item T14..."})
Agent({subagent_type: "...", isolation: "worktree", prompt: "fix item T16..."})
Agent({subagent_type: "...", isolation: "worktree", prompt: "fix item T17..."})
Agent({subagent_type: "...", isolation: "worktree", prompt: "fix item T18..."})
Agent({subagent_type: "...", isolation: "worktree", prompt: "fix item T19..."})
Agent({subagent_type: "...", isolation: "worktree", prompt: "fix item T20..."})
# Items T13 + T15 done inline / serialized (T15 depended on T14's PR number)
```

### Worktree Isolation For Compiling Agents

Per `rules/agents.md` § "Worktree Isolation for Compiling Agents," any bundle agent that will run `cargo check` / `cargo test` MUST receive `isolation: "worktree"`. Cargo's exclusive `target/` lock turns shared-tree parallel agents into sequential execution.

Python-only / docs-only / config-only agents do not need worktree isolation — but giving it to them costs nothing and removes the "wait, was that one compiling?" check.

### Dependency Serialization

When one bundle item legitimately depends on another (e.g. item T15 needed the PR number created by item T14), serialize that pair while keeping the rest parallel. Don't serialize the whole bundle to handle one dependency.

## Red Team Round Pattern (Same Shape, Different Source)

After a sharded `/implement` cycle finishes, the red team round typically surfaces 5–10 small independent corrections. This is the same bundle shape — dispatch the corrections as parallel agents, not as a new round of sharded todos. The red-team-round bundle is the most common application of this pattern.

## Cross-References

- `rules/autonomous-execution.md` § Per-Session Capacity Budget — the shard sizing contract that governs when work cannot be bundled.
- `rules/agents.md` § "Worktree Isolation for Compiling Agents" — required for any bundle agent that compiles.
- `rules/agents.md` § "Parallel Execution" — the underlying MUST that bundles operationalize.
- `guides/deterministic-quality/02-session-architecture.md` — the broader session-shape decision space.

Origin: Codified from a use-feedback-triage session (2026-04-19) that dispatched 8 follow-up items as 6 parallel agents (T13–T20 bundle), with red-team round 1 dispatching 5 agents in parallel for round-1 corrections. The dispatch-vs-shard decision was judgment-driven each time; this guide names the pattern so future sessions reach for it reliably.
