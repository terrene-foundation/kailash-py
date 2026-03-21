# Connection Pool Prevention Brief: kailash-py

**Date**: 2026-03-20
**Priority**: CRITICAL (systemic — affects every project using DataFlow)
**Analysis source**: `/workspaces/connection-pool-prevention/01-analysis/00-pool-improvements.md`

---

## Executive Summary

Every project that deploys kailash-py with DataFlow hits connection pool exhaustion. This is not a user error — it is a systemic SDK failure. The current defaults are wrong, there is no monitoring, no auto-scaling, and no leak detection. Users discover the problem in production when their application starts throwing `TimeoutError` on database operations.

The root cause is a combination of three design failures:

1. **Wrong defaults**: `DatabaseConfig.get_pool_size()` returns up to `cpu_count * 4` (which can be 50 on a production server), but PostgreSQL's default `max_connections` is 100. With 4 Uvicorn workers, that is 200 connections requested against 100 available — guaranteed exhaustion.

2. **No visibility**: There is no pool utilization monitoring. The first signal users get is a hard failure — no warnings, no metrics, no gradual degradation signal. The `MonitoringConfig` has `alert_on_connection_exhaustion` and `connection_metrics` flags, but nothing reads them.

3. **No prevention**: The SDK never validates its pool configuration against the actual database server. It never checks `SHOW max_connections`. It does not know how many workers are running. It cannot detect connection leaks.

This workspace defines five improvements to make connection pool exhaustion preventable rather than inevitable.

---

## Problem Statement

### Observed Symptoms

- `sqlalchemy.exc.TimeoutError: QueuePool limit of N overflow M reached` in production
- Intermittent 503 errors under moderate load
- Dashboard pages failing to render (Aegis RT6 — pool exhaustion was the root cause)
- Users manually tuning `pool_size` and `max_overflow` by trial and error
- No warning before failure — the system goes from "working" to "broken" instantly

### Root Cause Chain

1. **DataFlowConfig** uses `DatabaseConfig.get_pool_size(environment)` which returns up to 50 connections per process
2. **ASGI servers** (Uvicorn, Gunicorn) spawn multiple workers (typically 2-4x CPU cores)
3. **Total connections** = `pool_size * workers` + `max_overflow * workers`
4. **PostgreSQL default** `max_connections = 100` — shared across ALL clients (app + migrations + monitoring + admin)
5. **Result**: Pool exhaustion is the default outcome for any production deployment

### Impact

- Every DataFlow project must manually tune pool sizes
- Users without PostgreSQL expertise get production outages
- No SDK-level protection or guidance
- The Aegis project alone has hit this 3 times (RT6, session 6, dashboard refactor)

---

## Objectives

- Pool exhaustion should be **impossible with default settings**
- Users should get **clear warnings** before exhaustion occurs
- The SDK should **auto-detect** the correct pool size for the deployment environment
- Connection leaks should be **detected and logged** automatically
- Frequently-read records should be cacheable to **reduce pool pressure**

## Tech Stack

- Backend: kailash-py DataFlow (`packages/kailash-dataflow/`)
- Database: PostgreSQL (primary target), SQLite (development)
- Config: `DataFlowConfig`, `DatabaseConfig` in `packages/kailash-dataflow/src/dataflow/core/config.py`

## Constraints

- Must be backward compatible — existing `pool_size=N` configurations must continue to work
- `"auto"` mode must be safe for all supported databases (PostgreSQL, SQLite, MySQL)
- Monitoring thread must not leak or prevent clean shutdown
- Cache invalidation must be correct — stale data is worse than no cache

## Users

- SDK consumers: Python developers using `DataFlowConfig` to configure database connections
- DevOps: Teams deploying DataFlow applications behind ASGI servers with multiple workers
- SDK maintainers: kailash-py team implementing and testing these improvements
