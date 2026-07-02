---
type: DISCOVERY
date: 2026-04-03
created_at: 2026-04-03T10:00:00+08:00
author: co-authored
session_turn: 19
project: data-fabric-engine
topic: Fabric maps precisely onto DataFlow's 10-layer stack with one new layer
phase: analyze
tags: [architecture, layers, integration, dataflow]
---

# Discovery: Fabric Adds One Layer and Extends Three — Everything Else Unchanged

## Finding

After mapping fabric concepts onto DataFlow's exact 10-layer architecture and red-teaming the mapping, the integration is surgical:

- **Layer 1** (BaseAdapter): Unchanged. Both DatabaseAdapter and new BaseSourceAdapter inherit from it.
- **Layer 2** (Adapters): Extended with 5 new source adapters parallel to existing DB adapters.
- **Layer 3** (Config): Extended with source config types parallel to DatabaseConfig.
- **Layer 5** (Nodes): Unchanged. Products are NOT nodes — they are a different abstraction. But a thin `ProductInvokeNode` wrapper gives workflow composability.
- **Layer 6** (Core Engine): Extended with `_sources`, `_products` registries and `source()`, `product()`, `start()`, `stop()` methods.
- **Layer 7** (Express): Unchanged. Products USE Express for DB access via `ctx.express`.
- **Layer 10** (NEW): FabricRuntime — the background system (poll loops, pipelines, scheduler, SSE, health).

7 of 10 existing layers are completely unchanged. The 3 extended layers gain additive-only changes — no existing API modified.

## Key Red Team Findings Resolved

1. **Pipeline snapshot consistency**: Product functions now execute within a `PipelineScopedExpress` that deduplicates reads within a single pipeline run.
2. **Pool exhaustion from background pipelines**: Pipeline executor uses a dedicated semaphore (20% of total pool) to avoid starving user requests.
3. **Products are not nodes but can compose**: `ProductInvokeNode` auto-generated wrapper gives workflow composability without forcing products into node constraints.

## For Discussion

1. The `PipelineScopedExpress` caches reads within a pipeline run but does NOT provide transaction-level isolation. Two concurrent product refreshes can still see different database states. Should pipeline executions use `READ COMMITTED` or `REPEATABLE READ` isolation?
2. The 80/20 pool split (requests/pipelines) is a soft partition. Should it be configurable per-deployment, or is 80/20 a good default for all cases?
