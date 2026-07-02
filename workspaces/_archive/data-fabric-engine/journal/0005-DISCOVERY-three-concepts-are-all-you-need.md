---
type: DISCOVERY
date: 2026-04-02
created_at: 2026-04-02T16:30:00+08:00
author: co-authored
session_turn: 7
project: data-fabric-engine
topic: The entire fabric is three new concepts on top of existing DataFlow
phase: analyze
tags: [developer-experience, api-design, simplicity]
---

# Discovery: Three Concepts Are All You Need

## Finding

After two rounds of red-teaming (architecture + DX), the fabric API reduces to exactly three new concepts added to existing DataFlow. Everything else is unchanged.

### 1. `db.source("name", Config)` — "I have data elsewhere"

Register an external source. DataFlow manages connection, polling, health, circuit breaking. Five source types (REST, File, Cloud, Database, Stream) with typed auth objects.

### 2. `@db.product("name", depends_on=[...])` — "FE needs this data"

Define a materialized view over sources. Three modes (materialized, parameterized, virtual). Static dependency declaration. Staleness policy per product.

### 3. `await db.start()` — "Go"

Pre-warm cache, start watchers, register endpoints. After this returns, FE gets instant data.

## Why This Matters

- Developer learns three new things. Express API, @db.model, caching — all unchanged
- 100% backward compatible. Existing DataFlow projects add fabric incrementally
- The mental model shift is from imperative ("fetch, cache, serve") to declarative ("I need this data, this fresh")
- FabricContext is fully specified: `.express` (database), `.source()` (external), `.product()` (other products)

## Key Decisions Made During DX Red Team

| Decision            | Resolution                                                                   |
| ------------------- | ---------------------------------------------------------------------------- |
| Express API scope   | Database-only. Sources via `ctx.source()`. No ambiguity.                     |
| Dependency tracking | Static `depends_on=[]`. Runtime warns on undeclared access.                  |
| Auth config         | Typed objects only (BearerAuth, OAuth2Auth, etc.). No dicts.                 |
| Error timing        | Env vars at `db.source()`. Connectivity at `db.start()`. Format at runtime.  |
| Testing             | `FabricContext.for_testing()` with pre-loaded data. MockSource for Tier 1/2. |

## For Discussion

1. Should `depends_on` be optional with a warning ("Product 'dashboard' has no depends_on — it will never auto-refresh")? Or required to force developers to think about dependencies?
2. `ctx.product("other_product")` allows product-to-product composition. This creates a dependency DAG. Should circular product dependencies be detected at registration time or at runtime?
3. For the parameterized product `GET /fabric/users?filter={"active":true}`, parsing JSON from query strings is fragile. Should we use a custom query syntax (e.g., `?active=true`) or require POST for complex filters?
