---
type: DECISION
date: 2026-04-01
created_at: 2026-04-01T15:10:00+08:00
author: human
session_turn: 105
project: kailash-align
topic: kailash-rl is a separate package, not kailash-ml[rl]
phase: todos
tags: [architecture, rl, package-boundary, decision-reversal]
---

# kailash-rl: Separate Package (Decision Reversal)

## Decision

`kailash-rl` is a first-class Kailash framework package, NOT `kailash-ml[rl]`. Same reasoning as kailash-align: different primitives, different users, different dependencies.

Previous decision (journal 0011) reversed. "Start as extra, extract later" is a false economy — the extraction cost is real, the architectural clarity of separation is immediate, and COC autonomous execution makes the implementation cost irrelevant.

## Rationale (from user)

"Don't waste time separating later. Always go for the best optimal outcome regardless of costs."

## Implications

1. New package: `packages/kailash-rl/` in kailash-py monorepo
2. New workspace: `workspaces/kailash-rl/` with own brief, analysis, todos
3. ALN-500-503 move out of kailash-align workspace → become RL-001 through RL-004
4. `pip install kailash-rl` (not `pip install kailash-ml[rl]`)
5. kailash-ml `[rl]` extra becomes a redirect: `kailash-ml[rl]` depends on `kailash-rl` (backward compat)
6. PyPI OIDC trusted publisher needed for `kailash-rl`
7. Publish workflow needs `rl-v*` tag pattern

## For Discussion

1. Does kailash-rl depend on kailash-ml (for ModelRegistry, ExperimentTracker)? Yes — same as kailash-align depends on kailash-ml.
2. Should the Kailash platform table in CLAUDE.md be updated? Yes — kailash-rl becomes the 9th framework.
