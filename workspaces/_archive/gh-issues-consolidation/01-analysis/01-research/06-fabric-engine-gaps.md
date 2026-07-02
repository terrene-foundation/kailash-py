# Fabric Engine Gaps — Issues #245-#252

## Source

All 8 issues filed from integration testing of Treasury Fabric migration against real data (42 loans / 22 active / 7 currencies). This confirms the Fabric Engine IS operational for basic materialized products but has critical gaps.

## Critical Bugs

### #245: Virtual Products Return data:None (CRITICAL)

**Root Cause**: `fabric/serving.py` lines 227-234 — handler calls `get_cached(name)` and if no cache exists, returns `data: None`. Virtual products should never be cached — they should execute inline on every request.

**Impact**: Virtual products (mode="virtual") are completely broken in the serving layer.

**Fix**: Add virtual product detection before the cache check. Execute product function inline for virtual mode. Estimated ~20 lines.

### #248: dev_mode Skips Pre-Warming (BUG)

**Root Cause**: `fabric/runtime.py` lines 162-163 — `if self._leader.is_leader and not self._dev_mode:` condition skips pre-warming entirely in dev mode.

**Impact**: First request to any materialized product returns 202 (warming) with no data. Products appear broken on startup in development.

**Fix**: Pre-warm in dev_mode too, but serially (reduced resource usage). Estimated ~15 lines.

## Core Enhancements

### #246: Cache Invalidation API (HIGH)

**Gap**: PipelineExecutor has `set_cached()` and `get_cached()` but no `invalidate()` or `invalidate_all()`. Users reach into private internals to clear caches.

**Fix**: Add `invalidate(product_name, params)` and `invalidate_all()` to PipelineExecutor + expose via `db.fabric.invalidate()`. Estimated ~30 lines.

### #247: ?refresh=true Cache Bypass (HIGH)

**Gap**: Serving layer has no mechanism for per-request cache bypass. No `?refresh=true` query parameter support.

**Fix**: Parse `refresh` param in handler, skip cache lookup, execute product fresh. Estimated ~25 lines.

### #249: FileSourceAdapter Directory Scanning (MEDIUM)

**Gap**: FileSourceAdapter reads a single file only. No directory scanning, pattern matching, or latest-file selection.

**Fix**: Extend FileSourceConfig with `directory`, `pattern`, `selection` fields. Add directory scanning and mtime-based change detection to adapter. Estimated ~80 lines.

### #250: MCP Tool Generation from Products (MEDIUM)

**Gap**: Products auto-generate REST endpoints but not MCP tools. Users must manually duplicate product logic in MCP tool definitions.

**Fix**: Add `db.fabric.get_mcp_tools()` that generates MCP tool definitions from product registrations. Optional `db.fabric.register_with_mcp(mcp_server)` for auto-registration. Estimated ~120 lines. Requires kailash-mcp integration.

### #251: Fabric-Only Mode (MEDIUM)

**Gap**: DataFlow requires database URL even when only fabric features are used (sources + products). Users create throwaway SQLite databases.

**Fix**: Allow `DataFlow(database_url=None)` when no models registered. Skip DB initialization in fabric-only mode. Estimated ~40 lines.

### #252: BaseAdapter.database_type → source_type (LOW)

**Gap**: `database_type` property name misleading for non-DB adapters (file, cache, REST).

**Fix**: Rename to `source_type` with deprecation shim. Estimated ~20 lines across adapter hierarchy.

## Dependency Analysis

```
#245 (virtual products fix) — BLOCKS all virtual product usage
#248 (dev_mode pre-warm) — BLOCKS development workflow
#246 (invalidation API) — independent
#247 (refresh bypass) — independent, but complementary to #246
#249 (file scanning) — independent
#250 (MCP tools) — depends on fabric serving layer being correct (#245)
#251 (fabric-only mode) — independent
#252 (rename) — independent, low priority
```

**Critical path**: #245 must land first — virtual products are broken.

## Relationship to Existing Plan

- **Resolves M1** (red team finding): Fabric Engine IS operational for materialized products. Virtual products broken.
- **#244** (consumer adapters) can proceed — it only needs the serving layer and materialized products, which work.
- **#250** (MCP tools) is a natural companion to #244 (consumer adapters) — both extend how products are consumed.
