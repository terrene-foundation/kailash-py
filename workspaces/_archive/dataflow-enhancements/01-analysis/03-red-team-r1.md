# Red Team Round 1 -- DataFlow Enhancements

## Challenge 1: EventBus Wildcard Subscription Gap

**Finding**: CRITICAL

The architecture doc proposes `db.on_model_change("Order", handler)` which subscribes to `"dataflow.Order.*"`. The `InMemoryEventBus.publish()` does an exact dict lookup on `event.event_type`. Wildcard patterns are not matched.

**Impact**: TSG-201 and TSG-101 architecture docs describe an API that cannot work with the current EventBus. If implemented as documented, `on_model_change()` would silently receive zero events.

**Resolution**: Subscribe to each specific event type rather than using wildcards:

```python
def on_model_change(self, model_name: str, handler: Callable) -> None:
    for op in ["create", "update", "delete", "upsert",
               "bulk_create", "bulk_update", "bulk_delete", "bulk_upsert"]:
        self._event_bus.subscribe(f"dataflow.{model_name}.{op}", handler)
```

This requires 8 subscriptions per model per listener. With bounded subscribers at 10,000 and 8 ops, this supports ~1,250 model-listener combinations before hitting the limit. Acceptable for production use.

## Challenge 2: Synchronous Event Handler Blocking

**Finding**: HIGH

`InMemoryEventBus` invokes handlers synchronously in the publish thread. If derived model recompute is triggered inside a write handler, it will:

1. Block the original write operation
2. Execute a potentially expensive full-table scan and recompute
3. Execute a bulk upsert on the derived model
4. Only then return control to the original write caller

For `on_source_change` with a large source table, this could add seconds of latency to every write.

**Resolution**: `DataFlowEventMixin._emit_write_event()` must fire-and-forget. The derived model recompute handler should schedule an `asyncio.create_task()` or use a background queue rather than executing inline. The architecture doc's `DerivedModelRefreshScheduler` pattern (for scheduled refresh) could be reused for event-driven refresh with a debounce mechanism.

## Challenge 3: CacheInvalidator / InMemoryCache Type Mismatch

**Finding**: MEDIUM

`CacheInvalidator.__init__` accepts `cache_manager: RedisCacheManager`. When Redis is not available, `CacheBackend.auto_detect()` returns `InMemoryCache`, which is NOT a `RedisCacheManager`. Direct wiring fails.

**Resolution**: Three options:

1. **Best**: Refactor `CacheInvalidator` to accept a protocol/ABC (`CacheBackendProtocol`) instead of `RedisCacheManager`. Both `RedisCacheManager` and `InMemoryCache` implement the needed methods (`delete`, `clear_pattern`).
2. Wrap `InMemoryCache` in an adapter matching `RedisCacheManager` interface.
3. Skip `CacheInvalidator` for InMemoryCache and implement model-scoped invalidation directly in Express (simpler but duplicates logic).

Option 1 is cleanest. Option 3 is fastest.

## Challenge 4: CacheKeyGenerator Input Format Mismatch

**Finding**: MEDIUM

`CacheKeyGenerator.generate_key()` takes `(model_name, sql, params)`. Express doesn't generate SQL -- it calls nodes directly with Python dicts. The key generator needs either:

1. A new `generate_key_from_express(model_name, operation, params)` method
2. Express to construct pseudo-SQL strings for key generation (wasteful)
3. Replace with a simpler key format: `"{prefix}:{model}:{operation}:{hash_of_params}"`

Option 3 is most pragmatic. The existing `ExpressQueryCache._generate_key()` already does something similar. Promote its approach to `CacheKeyGenerator`.

## Challenge 5: ReadReplica -- Single-Adapter Assumption

**Finding**: MEDIUM-HIGH

DataFlow's entire execution pipeline assumes a single database adapter. The `_connection_manager`, `_adapter`, all node execution paths, transaction management -- all assume one database. Adding `read_url` requires:

1. Two adapters with separate connection pools
2. A routing layer that intercepts every database operation
3. Transaction awareness (must force primary)
4. Schema migrations on both databases (or primary only?)
5. Health checks on both connections

The brief frames this as "wiring" but it's closer to "restructuring." The 1-session estimate is achievable if the implementation takes a pragmatic approach:

- Keep the existing single-adapter path as default
- When `read_url` is provided, create a read-only adapter that only handles ListNode/ReadNode/CountNode operations
- Route at the Express level (simpler than intercepting all node execution)

## Challenge 6: engine.py Size and Merge Conflicts

**Finding**: MEDIUM

At 6400 lines, engine.py is already the largest file. Six features all adding code to `__init__`, `model()`, and new properties will create significant merge pressure. Even with sequential development, the diff size increases review complexity.

**Mitigation**: The brief's approach of creating separate modules (`features/derived.py`, `features/retention.py`, `core/events.py`) is correct. Minimize engine.py additions to:

- Parameter forwarding in `__init__`
- Property definitions
- 1-2 line hooks in `model()` decorator

Delegate all logic to the feature modules.

## Challenge 7: DerivedModel Compute on Large Tables

**Finding**: MEDIUM

The architecture proposes: `source_data[src] = await db.express.list(src, limit=None)`. For a source table with millions of records, this loads all records into memory. The brief mentions "paginated for large datasets" but the compute function signature `compute(sources: Dict[str, List[Dict]]) -> List[Dict]` implies all data in memory at once.

**Resolution**: Two approaches:

1. **Streaming compute** -- page through source data, pass batches to compute. Requires changing the compute signature to support incremental computation.
2. **Accept memory constraint** -- document that DerivedModel is for tables that fit in memory. For large-table aggregation, recommend SQL materialized views directly.

Option 2 is pragmatic for the initial release. Document the limitation and add streaming compute in a future iteration.

## Challenge 8: Effort Estimates

**Review**:

| Feature | Estimated    | Revised       | Rationale                                                     |
| ------- | ------------ | ------------- | ------------------------------------------------------------- |
| TSG-100 | 1 session    | 1 session     | Accurate. Scheduled + manual is well-scoped                   |
| TSG-101 | 0.5 sessions | 0.75 sessions | EventBus wildcard workaround + async dispatch adds complexity |
| TSG-102 | 1 session    | 0.75 sessions | Simpler than estimated -- stdlib handles most formats         |
| TSG-103 | 0.5 sessions | 0.5 sessions  | Accurate                                                      |
| TSG-104 | 1 session    | 1.25 sessions | CacheInvalidator type mismatch, CacheKeyGenerator adaptation  |
| TSG-105 | 1 session    | 1.25 sessions | Single-adapter assumption makes this harder than described    |
| TSG-106 | 1 session    | 1 session     | Accurate                                                      |
| TSG-201 | 0.5 sessions | 0.75 sessions | Wildcard workaround + async handler dispatch                  |

**Total revised**: ~6.25 sessions (was 5.5 + 1 for Phase 2 = 6.5 in plan). The plan's 6.5 estimate is actually close. Individual items shift but the total is similar.

## Challenge 9: Circular Dependency in DerivedModel

**Finding**: LOW

If DerivedModel A sources from Model X, and DerivedModel B sources from Model A, a write to X triggers A recompute, which emits events, which triggers B recompute. If B also depends on X (directly or transitively), this could cause infinite recompute loops.

The architecture mentions "circular dependency detection at db.initialize() time" but doesn't detail the algorithm.

**Resolution**: Build a directed graph of source -> derived relationships at initialize time. Run cycle detection (DFS with coloring). Reject cycles with a clear error. This is straightforward graph theory -- low effort to implement.

## Challenge 10: Cross-SDK Alignment Claims

**Finding**: LOW-MEDIUM

The brief's cross-SDK alignment table describes Rust features (`#[dataflow::derived_model]`, `FileSourceNode` Node impl) that could not be verified in the kailash-rs codebase. These may be planned features rather than implemented features. The alignment table should distinguish "exists" from "planned."

Verified Rust features:

- QueryCache with DashMap + TTL: EXISTS and wired
- RetentionPolicy + DataRetentionEnforcer: EXISTS in Python bindings
- DerivedModel proc macro: NOT FOUND
- FileSourceNode: NOT FOUND
- read_url in DataFlowConfig: NOT FOUND

## Summary

| #   | Finding                            | Severity      | Status                                     |
| --- | ---------------------------------- | ------------- | ------------------------------------------ |
| 1   | EventBus wildcard gap              | CRITICAL      | Resolved: use specific subscriptions       |
| 2   | Synchronous handler blocking       | HIGH          | Resolved: async dispatch / fire-and-forget |
| 3   | CacheInvalidator type mismatch     | MEDIUM        | Needs resolution during TSG-104            |
| 4   | CacheKeyGenerator input mismatch   | MEDIUM        | Needs resolution during TSG-104            |
| 5   | Single-adapter assumption          | MEDIUM-HIGH   | Needs careful design in TSG-105            |
| 6   | engine.py merge pressure           | MEDIUM        | Mitigated by modular design                |
| 7   | Large-table memory in DerivedModel | MEDIUM        | Accept + document for v1                   |
| 8   | Effort estimates                   | INFORMATIONAL | Total is close, individual items shift     |
| 9   | Circular dependency detection      | LOW           | Standard graph algorithm                   |
| 10  | Cross-SDK claims unverified        | LOW-MEDIUM    | Distinguish planned vs implemented         |
