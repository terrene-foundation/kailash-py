---
type: DISCOVERY
date: 2026-04-02
created_at: 2026-04-02T20:00:00+08:00
author: agent
session_turn: 15
project: data-fabric-engine
topic: The fundamental transformation is request-driven → event-driven execution model
phase: analyze
tags: [architecture, runtime, event-driven, transformation]
---

# Discovery: The Fundamental Transformation Is Execution Model, Not Features

## Finding

DataFlow today has ZERO background tasks (except one pool monitor thread). After `db.start()`, there are N background tasks running continuously — poll loops, file watchers, pipeline executors, cron schedulers, leader election heartbeats.

This is not "adding fabric features." This is changing DataFlow's execution model from **request-driven** (nothing runs until called) to **event-driven** (things run continuously in response to source changes).

## Why This Matters for Implementation

1. **Concurrency model**: DataFlow has never managed long-running asyncio tasks. The fabric introduces structured background task management with supervised restart on failure.

2. **Failure isolation**: A crash in one poll loop must NOT kill other poll loops. The `asyncio.TaskGroup` pattern (initially proposed) would cascade failures. Supervised individual tasks are required.

3. **Resource lifecycle**: `db.start()` acquires resources (connections, threads, locks). `db.stop()` must release ALL of them in the correct order. DataFlow has never had this — its resources are lazy-initialized and never explicitly released.

4. **Multi-process coordination**: Request-driven systems don't need coordination — each request is independent. Event-driven systems need leader election to prevent duplicate background work.

## The Key Runtime Components After Transformation

```
FabricRuntime
├── LeaderElector         — only leader runs background tasks
├── SourceManager         — connection lifecycle for all sources
├── ChangeDetector        — poll loops and file watchers (leader only)
├── WebhookReceiver       — HTTP endpoints (all workers, queue to leader)
├── PipelineExecutor      — semaphore-guarded, debounced product refresh
├── CacheManager          — atomic Lua-based cache writes
├── Scheduler             — cron-based product refresh (leader only)
└── HealthReporter        — extends existing HealthMonitor
```

## For Discussion

1. Should DataFlow expose a generic "background task" API for extensions beyond fabric? If other subsystems need background work in the future, the supervised task pattern should be reusable.
2. The event-driven model means DataFlow processes consume more CPU at idle (poll loops, heartbeats). Is this acceptable for all deployment environments? Should there be a "passive mode" where fabric only responds to webhooks, never polls?
