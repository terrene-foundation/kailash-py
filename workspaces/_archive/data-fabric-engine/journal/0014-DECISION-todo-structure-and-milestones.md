---
type: DECISION
date: 2026-04-03
created_at: 2026-04-03T11:30:00+08:00
author: co-authored
session_turn: 21
project: data-fabric-engine
topic: Todo structure — 6 milestones, 39 todos, dependency-ordered
phase: todos
tags: [planning, milestones, todos, implementation-order]
---

# Decision: Todo Structure — 6 Milestones, 39 Todos

## Structure

| Milestone | Name                  | Todos | What It Delivers                                                                                                   |
| --------- | --------------------- | ----- | ------------------------------------------------------------------------------------------------------------------ |
| 1         | Foundation            | 01-08 | BaseSourceAdapter, configs, 5 source adapters, DataFlow core wiring                                                |
| 2         | Products & Pipeline   | 09-13 | Product decorator, FabricContext, PipelineExecutor, ChangeDetector, LeaderElector                                  |
| 3         | Serving & Runtime     | 14-18 | Endpoints, write pass-through, webhooks, FabricRuntime, event bus wiring                                           |
| 4         | Observability         | 19-25 | Health, traces, metrics, logging, SSE, batch reads, programmatic API                                               |
| 5         | Integration & Testing | 26-33 | Builder wire, MockSource, cron, multi-tenancy, packaging, integration tests, reference app, docs                   |
| 6         | Security & Gaps       | 34-39 | Product dependency graph, filter allowlist, OAuth2 lifecycle, webhook nonces, db.start() params, dev-mode debounce |

## Key Ordering Decisions

1. **Adapters before engine**: Milestones 1-2 build bottom-up. Adapters and configs first, then the engine that uses them.
2. **Pipeline before serving**: Serving reads from cache that pipeline writes. Pipeline must exist first.
3. **Security as final milestone**: Not because it's less important — because security features (filter allowlist, OAuth2 lifecycle, nonce tracking) extend components built in earlier milestones. They cannot be built before their targets exist.
4. **Red team additions**: TODO-34 through TODO-39 were added by the todo red team. They close gaps from the analysis red team findings that had no implementation path.

## For Discussion

1. 39 todos across 6 milestones — at autonomous execution speed, this is estimated at 4-5 sessions. Does this match your expectations?
2. Milestone 7 (Aether migration) is intentionally NOT included in these todos. It is a separate workspace after fabric ships. Should it be?
