---
type: DISCOVERY
date: 2026-04-02
created_at: 2026-04-02T17:30:00+08:00
author: co-authored
session_turn: 9
project: data-fabric-engine
topic: The fabric solves exactly four needs — previous analysis was tech-forward, not needs-forward
phase: analyze
tags: [needs-analysis, first-principles, product-design]
---

# Discovery: The Fabric Solves Four Needs

## Finding

Three rounds of red-teaming kept finding gaps because the analysis was technology-forward ("here are the components") instead of needs-forward ("here are the needs"). When reframed around needs, the fabric becomes clear:

### Need 1: "Where is my data?" → Sources

Register any data source — database, API, file, cloud, stream. One abstraction for all of them. Push (webhooks) or pull (polling). The developer declares WHERE, the fabric handles HOW.

### Need 2: "What should the frontend see?" → Products

Define the data shape the frontend needs. The product function IS the business logic — fetch, normalize, enrich, aggregate, compose. The developer writes WHAT the FE sees, the fabric handles WHEN to refresh and WHERE to cache.

### Need 3: "Is everything working?" → Observability

Health endpoint, structured logs, Prometheus metrics, pipeline traces. The developer and operator can see which sources are healthy, which products are fresh, what went wrong and when.

### Need 4: "How do I change data?" → Writes

Pass-through writes that trigger automatic product refresh. The developer writes ONCE, the fabric handles cache invalidation across all affected products.

## What Changed After This Reframing

| Previous Design Gap    | Root Cause                                                                             | Resolution                                    |
| ---------------------- | -------------------------------------------------------------------------------------- | --------------------------------------------- |
| No auth on endpoints   | Tech focus — "auto-generated endpoints" without asking "who should see this?"          | Products inherit app auth. Per-product roles. |
| No rate limiting       | Tech focus — "serve from cache, it's fast" without asking "what if someone abuses it?" | Per-product limits, cache cardinality bounds. |
| \_fabric body envelope | Tech focus — "we need metadata" without asking "does the FE want an envelope?"         | Headers. Clean body. Standard HTTP.           |
| No multi-tenancy       | Tech focus — "cache the product" without asking "whose product?"                       | Tenant-aware cache keys and context.          |
| No scheduled products  | Tech focus — "refresh on source change" without asking "what about daily summaries?"   | Cron schedule per product.                    |

## For Discussion

1. Are there needs beyond these four? Or does every fabric feature trace back to Sources, Products, Observability, or Writes?
2. The four needs map cleanly to four API surfaces: `db.source()`, `@db.product()`, `/fabric/_health`, `db.fabric.write()`. Is there a fifth surface missing?
3. The previous analysis had 8 research documents. After this reframing, is a single end-to-end document (09-fabric-end-to-end.md) plus the convergence (04-final-convergence.md) sufficient? Or do the component documents still have value?
