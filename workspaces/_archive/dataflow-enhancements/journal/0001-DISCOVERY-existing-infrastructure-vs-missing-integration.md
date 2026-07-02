---
type: DISCOVERY
date: 2026-04-01
created_at: 2026-04-01T10:00:00+08:00
author: agent
session_id: analyze-phase
session_turn: 1
project: dataflow-enhancements
topic: Existing infrastructure is substantial but integration is zero
phase: analyze
tags: [cache, read-replica, eventbus, gap-analysis, architecture]
---

# DISCOVERY: Existing Infrastructure Is Substantial but Integration Is Zero

## Finding

The gap analysis and research reveal a consistent pattern across the 6 DataFlow enhancement features: the underlying infrastructure components already exist in the codebase, but none of them are wired into DataFlow's execution pipeline.

### Cache (TSG-104)

The `cache/` module contains 7 files with full implementations of `RedisCacheManager`, `InMemoryCache` (LRU + TTL), `CacheKeyGenerator`, and `CacheInvalidator` with model-scoped invalidation patterns. However, there are **zero imports** between `cache/` and Express. The `ExpressQueryCache` currently in Express uses a nuclear `self._cache.clear()` strategy that discards the entire cache on any write -- the sophisticated model-scoped invalidation infrastructure sits unused.

### Read Replica (TSG-105)

`DatabaseQueryRouter`, `DatabaseRegistry` with `is_read_replica`, `RoutingStrategy.READ_REPLICA`, and `QueryType.READ/WRITE` all exist and are functionally complete. But DataFlow's entire execution pipeline assumes a single database adapter. The brief claimed "80% built" -- routing logic is 100% built but integration with DataFlow is 0%.

### EventBus (TSG-201)

Core SDK provides `InMemoryEventBus` with `DomainEvent`, thread-safe bounded queues, and full publish/subscribe semantics. DataFlow has zero references to the EventBus. Furthermore, the EventBus does not support wildcard subscriptions (`dataflow.Order.*`), which the architecture docs assume -- it only does exact `event_type` matching.

### Validation (TSG-103)

Seven validator functions (email, url, uuid, length, range, pattern, phone) exist alongside a `@field_validator` decorator and `validate_model()` returning `ValidationResult`. No declarative dict syntax exists yet, but the primitives are solid.

## Implication

The implementation effort for these features is dominated by **integration plumbing**, not building new capability. The infrastructure teams (or prior sessions) built the components in isolation. The gap is that nobody wired them together through DataFlow's engine.py. This means the 6.25 session estimate is realistic -- most work is routing, adapter refactoring, and test coverage, not greenfield development.

The single most important architectural constraint is that **engine.py at 6,400 lines is the convergence point for all 6 features**. Every feature modifies `__init__`, `model()`, or adds properties there. Merge conflict management and modular extraction are critical success factors.

## For Discussion

1. The `CacheInvalidator` is typed to accept only `RedisCacheManager`, yet `CacheBackend.auto_detect()` returns `InMemoryCache` when Redis is unavailable. If the cache module had been designed with a `CacheBackendProtocol` from the start, would the TSG-104 estimate drop from 1.25 sessions to 0.5 -- and does this pattern of concrete-type coupling repeat elsewhere in the codebase?

2. If the EventBus had supported wildcard subscriptions natively, the TSG-201 architecture could use a single subscription per model instead of 8 (one per CRUD operation). Would that simplify the subscriber-count bound calculation (currently ~1,250 model-listener combinations before hitting the 10,000 limit), or is the explicit-subscription workaround actually more maintainable long-term?

3. Given that the routing infrastructure for read replicas exists at 100% completeness but has 0% integration, what does this tell us about the development process that produced these components -- were they built speculatively, or did a prior integration attempt stall?
