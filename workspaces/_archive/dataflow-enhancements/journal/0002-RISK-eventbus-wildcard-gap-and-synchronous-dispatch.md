---
type: RISK
date: 2026-04-01
created_at: 2026-04-01T10:01:00+08:00
author: agent
session_id: analyze-phase
session_turn: 1
project: dataflow-enhancements
topic: EventBus wildcard gap and synchronous dispatch threaten DerivedModel viability
phase: analyze
tags: [eventbus, derived-model, performance, red-team, critical]
---

# RISK: EventBus Wildcard Gap and Synchronous Dispatch Threaten DerivedModel Viability

## Risk Statement

The red team identified two compounding issues (Challenge 1: CRITICAL, Challenge 2: HIGH) that together threaten the viability of the event-driven DerivedModel architecture (TSG-101) and the DataFlowEventMixin (TSG-201).

### Issue 1: Silent Event Loss (CRITICAL)

The architecture docs propose `db.on_model_change("Order", handler)` which subscribes to `"dataflow.Order.*"`. The `InMemoryEventBus.publish()` performs an exact dictionary lookup on `event.event_type`. Wildcard patterns are not matched. If implemented as documented, `on_model_change()` would **silently receive zero events** -- no error, no warning, just silent failure.

The red team resolution -- subscribing to each of the 8 specific event types (`create`, `update`, `delete`, `upsert`, `bulk_create`, `bulk_update`, `bulk_delete`, `bulk_upsert`) per model per listener -- works but creates a multiplicative subscription burden. With the EventBus bounded at 10,000 subscribers, this supports approximately 1,250 model-listener combinations.

### Issue 2: Write-Path Blocking (HIGH)

`InMemoryEventBus` invokes handlers synchronously in the publishing thread. If DerivedModel recompute is triggered inside a write handler, the sequence becomes:

1. User writes to source model
2. Write triggers event publish
3. Event handler fires synchronously
4. Handler executes a full-table scan of source model
5. Handler executes bulk upsert on derived model
6. Only then does control return to the original write caller

For large source tables, this could add **seconds of latency** to every write. The architecture's `DerivedModelRefreshScheduler` (designed for scheduled refresh) could be repurposed for event-driven refresh with a debounce mechanism, but this was not part of the original design.

### Compounding Effect

These issues compound: the workaround for Issue 1 (8 subscriptions per model) means each model write fires through 8 subscription checks. If each of those triggers synchronous recompute (Issue 2), a single write to a model with derived dependents could trigger multiple synchronous recomputes before returning.

## Likelihood

HIGH -- both issues are structural. They will manifest the moment TSG-201 and TSG-101 are integrated. They cannot be avoided through careful coding; they require architectural changes (async dispatch, explicit multi-subscription).

## Impact

- **Correctness**: Without the wildcard fix, event-driven derived models silently do nothing. Users would see stale derived data with no error indicating why.
- **Performance**: Without async dispatch, write latency degrades proportionally to derived model complexity. This is particularly damaging for OLTP workloads where write latency matters.
- **Cascading recompute**: DerivedModel A sourcing from Model X, and DerivedModel B sourcing from A, could create cascading synchronous recomputes. The red team noted this as Challenge 9 (circular dependency), rated LOW because cycle detection is straightforward graph theory -- but the synchronous dispatch makes even acyclic chains expensive.

## Mitigation

1. Implement the 8-specific-subscription pattern in TSG-201 (resolved by red team).
2. Use `asyncio.create_task()` or a background queue for event handlers in `DataFlowEventMixin._emit_write_event()` -- fire-and-forget with debounce.
3. Add cycle detection at `db.initialize()` time using DFS with coloring on the source-to-derived dependency graph.
4. Document the subscriber-count bound (1,250 model-listener combinations) in the API reference.

## For Discussion

1. The 10,000 subscriber bound on `InMemoryEventBus` with 8 subscriptions per model-listener yields ~1,250 combinations. For a typical DataFlow application with 10-20 models and 2-3 derived models each, this is well within limits. But if a future feature (like TSG-104 cache invalidation via events) adds another 8 subscriptions per model, does the bound become a practical constraint -- and should the EventBus bound be configurable?

2. If the `InMemoryEventBus` had been designed with async-first dispatch (using `asyncio.create_task` internally), would the DerivedModel architecture have been simpler -- or would async dispatch introduce harder-to-debug ordering issues where derived models see inconsistent source data during concurrent writes?

3. The red team rated circular dependency detection as LOW severity. But given that synchronous dispatch makes even linear dependency chains expensive, should cycle detection be elevated to a blocking requirement for TSG-101 rather than a nice-to-have?
