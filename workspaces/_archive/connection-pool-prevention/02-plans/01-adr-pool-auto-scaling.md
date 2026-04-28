# ADR: Pool Size Auto-Scaling as Default Behavior

## Status

Proposed

## Context

DataFlow's current pool sizing uses a CPU-based formula (`min(50, cpu_count * 4)`) that has no awareness of PostgreSQL's `max_connections` limit or ASGI worker count. In practice, this formula is dead code — engine.py overrides it with a hardcoded `20`. Either way, the result is guaranteed pool exhaustion on standard production deployments:

- 4 Uvicorn workers x 20 pool_size x 3 (with max_overflow) = 240 connections
- PostgreSQL default max_connections = 100

Every project using DataFlow with PostgreSQL must manually tune pool_size. This is not a tuning problem — it is a design defect.

Two design philosophies are possible:

1. **Safe defaults with auto-detection** (proposed)
2. **Conservative static defaults** (pool_size=5, no detection)
3. **Keep current defaults and add validation warnings only**

## Decision

Make auto-detection the default behavior for `DatabaseConfig.get_pool_size()`. When pool_size is not explicitly set:

1. Probe the database server for `max_connections`
2. Detect worker count from environment variables
3. Compute `pool_size = max(2, int(db_max * 0.7) // workers)`
4. Fall back to `min(5, cpu_count)` if probe fails

Explicit `pool_size=N` always overrides auto-detection (backward compatible).

## Consequences

### Positive

- Pool exhaustion is impossible with default settings for standard deployments
- Users no longer need PostgreSQL expertise to deploy safely
- Falls back conservatively on probe failure — never makes things worse
- Backward compatible: explicit pool_size continues to work unchanged
- No new configuration surface needed — just removing the hardcoded overrides

### Negative

- Adds a probe connection at startup (~50ms latency increase on first connect)
- Worker count detection depends on environment variables that servers may not set (mitigated by falling back to workers=1 with conservative pool_size)
- Cannot know about OTHER applications sharing the same database (mitigated by the 30% reservation)

## Alternatives Considered

### Option A: Warning-only (PY-4 without PY-1)

Log a warning at startup when pool math exceeds max_connections, but do not change defaults.

**Rejected**: Treats a systemic SDK failure as a user education problem. Users still get exhaustion — they just get a warning 0.5 seconds before the TimeoutError.

### Option B: Conservative static defaults (pool_size=5)

Change the default pool_size to 5 across all environments.

**Rejected**: Severely underutilizes available connections on properly-configured servers. Users who CAN handle more connections would be penalized. Trades one bad default for another.

### Option C: Auto-scaling as opt-in (not default)

Implement auto mode but keep current defaults. Users opt in with `pool_mode="auto"`.

**Rejected**: Does not solve the problem for new users, who are the primary victims. Existing users who have already tuned pool_size are unaffected by auto-default anyway (their explicit setting overrides it).

## Design Decisions Requiring Documentation

### Why 70% reservation (not 80% or 60%)?

Production PostgreSQL servers share connections across:

- The application (DataFlow)
- Migration runners (1-2 connections)
- Monitoring tools (pg_stat_statements, pgAdmin, etc.)
- Admin connections (psql, database backups)
- AWS RDS internal connections (3-5 reserved on RDS)

30% reservation accommodates all of these. 20% would be too tight for RDS. 40% would waste capacity.

### Why workers=1 as fallback?

When no worker count env var is set, defaulting to 1 gives the single process the full 70% allocation. This is correct for:

- Development (single process)
- CLI tools (single process)
- Tests (single process)

For multi-worker production, users should set `DATAFLOW_WORKER_COUNT` or use a server that sets `UVICORN_WORKERS`/`WEB_CONCURRENCY`.

### Why advisory validation, not blocking?

Startup validation (PY-4) logs errors but does not prevent startup because:

- PgBouncer deployments intentionally overcommit (PgBouncer manages the actual PostgreSQL connection limit)
- Some users run connection poolers that make the pool math irrelevant
- Blocking on startup is a high-blast-radius change that can prevent production deployments

A future `strict_validation=True` mode could be added for security-conscious deployments.
