# DISCOVERY — Fabric product cache is a 4-layer ghost feature

**Date**: 2026-04-08
**Phase**: 01-analyze
**Context**: /analyze 354
**Severity**: CRITICAL

## What I found

`PipelineExecutor` in `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py` accepts a `redis_url` parameter, stores it on `self._redis_url`, and then **never reads it**. The cache is a per-process `collections.OrderedDict` regardless of whether Redis is configured. Four docstrings promise Redis; zero lines instantiate a Redis client for the cache.

The surprise was the multiplier. The reporter found one stub. I found **eight in the same file** plus two additional wiring bugs:

1. `self._redis_url` dead (pipeline.py:152)
2. `self._dev_mode` dead (pipeline.py:154)
3. `self._queue` completely unused (pipeline.py:173)
4. `InMemoryDebouncer` class defined but zero instantiations anywhere in fabric (pipeline.py:581)
5. Module docstring lie (pipeline.py:8)
6. Class docstring lie (pipeline.py:137)
7. `dev_mode` vacuous docstring (pipeline.py:140)
8. "Redis is a future extension" comment (pipeline.py:227) — honest but contradicts #1-#7 ninety lines up in the same file

Plus two wiring bugs the reporter didn't find:

9. `DataFlow(redis_url=...)` kwarg never reaches fabric — `engine.py:2018` reads `self._redis_url` but no line ever writes it. Dead `hasattr` branch.
10. `WebhookReceiver` never gets the Redis client. `_RedisNonceBackend` exists and works, but `FabricRuntime.start()` at `runtime.py:211-214` calls `WebhookReceiver(sources=..., on_webhook_event=...)` without `redis_client=`. Webhook nonce deduplication has been silently in-memory in every current deployment.

## The data-leak risk

`products.py:52,111` documents `multi_tenant: Whether cache is partitioned per tenant`. Implementation: `_cache_key(product_name, params)` at `pipeline.py:119-124` has no tenant dimension. Today this is low-impact because each process has its own in-memory cache. **The moment a naive Redis fix lands, this becomes a cross-tenant data-leak primitive.** Shipping Redis without tenant partitioning is strictly worse than the current bug.

## The impact-verse crash loop mechanism

Prewarming 26 products serially against 6K participants × 3K orgs × 14 clusters took 4-5 minutes per replica. Container Apps startup probe defaults to ~4 minutes. Every new replica entered a crash loop because serving 202 "warming" for the full prewarm window exceeded the probe timeout. Follower replicas had no way to read from another replica's cache because there is no shared cache. Redis alone does NOT fix this — **followers need a lazy-prewarm code path that reads Redis instead of re-executing pipelines**.

## The pre-existing abstraction nobody used

`dataflow/cache/auto_detection.py` already ships `CacheBackend.auto_detect()` returning `AsyncRedisCacheAdapter | InMemoryCache` with a unified async surface. Fabric re-implemented its own OrderedDict cache instead of reusing it. Framework-first violation inside the framework. But: `AsyncRedisCacheAdapter` uses a ThreadPoolExecutor wrapping a sync Redis client (adds 1-2ms per op per its own docstring). For the fabric hot path we reject reuse and implement direct `redis.asyncio` matching `leader.py:55-105`. The correct lesson is "reuse the pattern, not necessarily the code".

## How this survived review

The honest comment `# Cache operations (in-memory; Redis is a future extension)` at `pipeline.py:227` and the dishonest class docstring `redis_url: Optional Redis URL for production caching` at `pipeline.py:137` are **ninety lines apart in the same file**. The author documented the stub correctly in one place and incorrectly in another. The reviewer either did not grep for "future extension" or accepted "will add later". `.claude/rules/dataflow-pool.md` Rule 3 ("No Deceptive Configuration") already forbids exactly this pattern: "A flag set to True with no consumer is a stub."

## Links

- Issue: terrene-foundation/kailash-py#354
- Executive summary: `workspaces/issue-354/01-analysis/00-executive-summary.md`
- Specialist report: `workspaces/issue-354/01-analysis/01-research/01-dataflow-specialist-report.md` (830 lines, 15 sections)
- Blast radius report: `workspaces/issue-354/01-analysis/01-research/02-blast-radius-report.md`
- Fix plan: `workspaces/issue-354/02-plans/01-fix-plan.md`
- Follow-ups: `workspaces/issue-354/02-plans/02-followup-issues.md`
- Cross-SDK Rust parallel: `kailash-rs/crates/kailash-dataflow/src/executor.rs:32-149`
