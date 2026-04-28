# 0003 CONNECTION — JourneyMate Incident As Canary For Azure-Class Deployments

**Date:** 2026-04-28
**Session:** dataflow-prod-incident /analyze
**Type:** CONNECTION

## Finding

The JourneyMate incident has the structural fingerprint of "Azure Container Apps + FastAPI + DataFlow with multiple instances" — a deployment shape that is increasingly common across kailash-dataflow's downstream consumers. The connection-leak + DDL-retry pair surfaces fastest in this shape because:

1. **Azure PG defaults to 100–200 max_connections** (vs AWS RDS's typically larger pools), making the saturation point closer.
2. **gunicorn worker pre-fork creates new event loops per worker** — `_generate_pool_key` includes `id(get_running_loop())` so each worker gets its own pool keyspace; 8 workers × 13 DataFlow instances = 104 distinct pool keys before any user traffic.
3. **Azure Container Apps' default 30 s health-check interval** matches the DDL retry cadence — every health-probe touches a model, which fires the failed DDL, which creates a new pool.
4. **FastAPI lifespan + DataFlow `auto_migrate=True`** is the documented pattern in DataFlow's quickstart. Anyone copying the docs verbatim into a multi-instance Azure deployment hits this.

## Connection to other workstreams

This is the THIRD time in 2026-04 that a downstream Azure deployment has surfaced a kailash bug class:

- 2026-04-12: arbor-upstream-fixes (multi-tenant DataFlow + Azure)
- 2026-04-19: issue #525 (cross-SDK execute_raw + Postgres bind layer)
- 2026-04-28: this incident (JourneyMate)

The pattern: **Azure-class deployments are running ahead of the SDK's test-tier coverage.** Tier-2 tests target real PG via Docker — which runs single-process, single-event-loop, with `max_connections=100` defaults. The compound failure modes only appear under multi-process + multi-event-loop + Azure ceiling.

## What this implies

The Tier-2 regression tests for Shards A + B should NOT use docker-compose-PG with default settings. They should:

- Set `max_connections` low (50?) to surface saturation faster
- Spawn multiple event loops via `asyncio.new_event_loop()` to exercise the per-loop pool keying
- Run for 30 s+ wall clock to catch idle-timeout eviction

This is more expensive than current Tier-2 tests (which assume <1 s per test). But the alternative is the next JourneyMate-class incident.

Codification candidate (for future cycle):

> SDK regression tests for shared-architecture concerns (DataFlow connection lifecycle, Nexus session lifecycle, Kaizen agent budget) MUST include at least one test that runs against a constrained-resource real-infrastructure setup (low max_connections, low memory, multi-event-loop) — not just docker-default. The test names this constraint explicitly so future runners know it's load-bearing.

This deserves codification but only with a 2nd occurrence pattern (per `learning-codified.json` deferral discipline). This is the 3rd Azure-incident in 16 days, so 2nd occurrence is met.

## Action this workstream

The Tier-2 regression tests in `02-plans/01-implementation-plan.md` Shards A + B EXPLICITLY include constrained-resource setup:

- Shard A: `auto_migrate=True` with FK-misordered model (forces real DDL failure)
- Shard B: `max_pool_count_per_process=10` + `lock_timeout=0.1` (forces real saturation)

These mirror JourneyMate's failure conditions, run against real PG, and would catch a regression that re-introduces either bug.

## Related

- arbor-upstream-fixes session 2026-04-12
- Issue #525 / PR #528 (cross-SDK execute_raw)
- This workstream (#696/#697/#698/#685/#686)
- `rules/testing.md` § "End-to-End Pipeline Regression"
