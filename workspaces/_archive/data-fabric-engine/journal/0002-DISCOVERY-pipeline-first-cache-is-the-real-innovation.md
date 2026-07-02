---
type: DISCOVERY
date: 2026-04-02
created_at: 2026-04-02T14:35:00+08:00
author: co-authored
session_turn: 3
project: data-fabric-engine
topic: Pipeline-driven cache is the only genuinely novel architectural insight
phase: analyze
tags: [caching, invalidation, architecture, differentiation]
---

# Discovery: Pipeline-First Cache Is the Real Innovation

## Finding

After competitive analysis of 10+ competitors and red team scrutiny of 4 value propositions, only ONE architectural insight is genuinely novel and defensible:

**Cache is updated ONLY when the full data pipeline succeeds. Pipelines drive cache freshness, not TTL.**

Every other feature (heterogeneous sources, pre-warming, endpoint generation, cache-first reads) either exists in competitors or is a straightforward engineering exercise. The pipeline-first cache model is an architectural inversion that competitors would need to fundamentally rearchitect to replicate.

## Evidence

| Competitor         | Caching Model                  | Why Pipeline-First Is Different                |
| ------------------ | ------------------------------ | ---------------------------------------------- |
| **Hasura**         | TTL-based response cache       | Cache expires on time, not on data change      |
| **Supabase**       | No caching (hits PG directly)  | No cache at all                                |
| **Denodo**         | TTL + optional event listeners | Events are OPTIONAL, TTL is primary            |
| **RisingWave**     | Streaming materialized views   | Similar concept but ONLY for streaming sources |
| **Redis**          | TTL-based key expiration       | Cache expires on time, not on pipeline success |
| **TanStack Query** | TTL stale time                 | 30s stale time = 30s of potentially stale data |

RisingWave is closest but only works for sources with CDC/streaming capabilities. Our innovation: apply the pipeline-first pattern to ALL source types (databases via cheap change detection, APIs via ETag/polling, files via watch).

## Implications

- VP4 should be promoted to the LEAD value proposition
- VP1 (zero-wait) and VP2 (single contract) are CONSEQUENCES of pipeline-first, not standalone pitches
- Marketing should explain the architectural inversion, not just the UX benefit
- The 6-month competitive moat is architectural (requires rearchitecting), not feature-level

## For Discussion

1. RisingWave applies this pattern to streaming sources. If RisingWave adds REST API polling or file sources, does our moat disappear? What is our response to RisingWave expanding scope?
2. If the pipeline-first model is the primary differentiator, should we consider open-publishing a design paper or blog post to establish thought leadership before competitors claim the concept?
3. Denodo's "smart cache" uses event listeners that ARE pipeline-driven in practice. Is the difference between "events are primary" vs "events are optional" enough for a customer to perceive?
