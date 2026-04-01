# Express API Current State

## Source

`packages/kailash-dataflow/src/dataflow/features/express.py` (~800 lines)

## API Surface

`DataFlowExpress` provides the following methods:

| Method                | Signature                                                         | Caching                           | Notes                                   |
| --------------------- | ----------------------------------------------------------------- | --------------------------------- | --------------------------------------- |
| `create()`            | `(model, data) -> Dict`                                           | Invalidates model cache           | Read-back for SQLite missing timestamps |
| `read()`              | `(model, id, cache_ttl?) -> Dict?`                                | Reads from cache, writes to cache | Returns None on not-found               |
| `update()`            | `(model, id, fields) -> Dict`                                     | Invalidates model cache           |                                         |
| `delete()`            | `(model, id) -> bool`                                             | Invalidates model cache           |                                         |
| `list()`              | `(model, filter?, limit=100, offset=0, cache_ttl?) -> List[Dict]` | Reads from cache, writes to cache |                                         |
| `find_one()`          | `(model, filter, cache_ttl?) -> Dict?`                            | Reads from cache, writes to cache | Validates non-empty filter              |
| `count()`             | `(model, filter?, cache_ttl?) -> int`                             | Reads from cache, writes to cache |                                         |
| `upsert()`            | `(model, data, conflict_on?) -> Dict`                             | Invalidates model cache           | Simple upsert on id field               |
| `upsert_advanced()`   | `(model, where, create, update?, conflict_on?) -> Dict`           | Invalidates model cache           | Separate where/create/update            |
| `warm_schema_cache()` | `() -> Dict[str, bool]`                                           | Schema pre-warm                   |                                         |
| `get_stats()`         | Not explicitly checked but `_operation_times` tracked             |                                   |                                         |

Also: `SyncExpress` wraps the async methods for non-async contexts. Available via `db.express_sync`.

## ExpressQueryCache Implementation

`ExpressQueryCache` is a hand-rolled, in-process LRU cache. Key findings:

1. **Thread-safe**: Uses `threading.RLock` for all operations.
2. **LRU eviction**: `OrderedDict` with `popitem(last=False)` on capacity.
3. **TTL support**: Per-entry TTL checked on read.
4. **Key generation**: SHA-256 hash of `"{model}:{operation}:{json.dumps(params)}"` truncated to 32 chars.
5. **Statistics**: Tracks hits, misses, evictions, invalidations.

### The Nuclear-Option Invalidation Bug

The `invalidate_model()` method is the critical weakness. It attempts model-scoped invalidation but falls back to clearing everything:

```python
def invalidate_model(self, model: str) -> int:
    # ...attempts to find model-associated keys...
    # "For now, since we don't track model associations, invalidate all"
    count = len(self._cache)
    self._cache.clear()
    self._invalidations += count
    return count
```

This means every `create()`, `update()`, `delete()`, or `upsert()` call on ANY model clears the ENTIRE cache. On a system with 10 models, writing to model A destroys cached queries for models B through J.

### Cache Integration with Express Methods

Read methods (`read`, `list`, `find_one`, `count`) accept an optional `cache_ttl` parameter that overrides the default TTL. Write methods (`create`, `update`, `delete`, `upsert`) call `invalidate_model()` after the write operation.

### What Is NOT Present

- No Redis backend support (in-memory only)
- No model-scoped invalidation (despite the method name suggesting it)
- No `cache_stats()` public method on Express (stats are on `ExpressQueryCache` via `get_stats()`)
- No `import_file()` method
- No `use_primary` parameter on any read method
- No validation-on-write integration
- No event emission

## DataFlow Constructor Parameters (Cache-Related)

From `DataFlow.__init__`:

- `cache_enabled: bool = True` -- enables Express query cache
- `cache_ttl: int = 3600` -- default TTL (1 hour)
- `enable_caching: Optional[bool] = None` -- alias for `cache_enabled`

No `redis_url` parameter exists. No connection to the `cache/` module.
