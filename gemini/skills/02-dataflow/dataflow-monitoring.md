---
name: dataflow-monitoring
description: "DataFlow pool monitoring, utilization tracking, leak detection, and health checks. Use when asking 'dataflow monitoring', 'pool stats', 'pool utilization', 'connection leak', 'health check', 'pool exhaustion', or 'dataflow metrics'."
---

# DataFlow Pool Monitoring

> **Skill Metadata**
> Category: `dataflow`
> Priority: `HIGH`
> Related Skills: [`dataflow-connection-config`](#) (pool sizing), [`dataflow-troubleshooting`](#)
> Related Rules: [`rules/dataflow-pool.md`](#) (single source of truth)

## Pool Stats API

```python
from dataflow import DataFlow

db = DataFlow("postgresql://localhost/app")

# Real-time pool utilization
stats = db.pool_stats()
# {
#     "active": 5,      # Connections currently in use
#     "idle": 12,        # Connections available in pool
#     "max": 17,         # Configured pool_size
#     "overflow": 0,     # Overflow connections beyond pool_size
#     "max_overflow": 8, # max(2, pool_size // 2)
#     "utilization": 0.19  # active / (max + max_overflow)
# }
```

## Health Check

```python
health = db.health_check()
# {
#     "status": "healthy",     # "healthy", "degraded", or "unhealthy"
#     "database": "connected",
#     "pool": {                # Present when pool monitor is running
#         "active": 5,
#         "utilization": 0.19
#     },
#     "components": {
#         "database": "ok",
#         "pool": "ok"         # "ok", "high_utilization", or "exhaustion_imminent"
#     }
# }

# Lightweight health check (dedicated 2-connection pool, doesn't compete with main pool)
result = await db.execute_raw_lightweight("SELECT 1")
```

## Automatic Monitoring

DataFlow runs a background daemon thread that monitors pool utilization:

| Utilization | Level   | Behavior                                 |
| ----------- | ------- | ---------------------------------------- |
| < 70%       | Silent  | No logging                               |
| 70-79%      | INFO    | Pool stats logged                        |
| 80-94%      | WARNING | "approaching pool exhaustion"            |
| >= 95%      | ERROR   | "EXHAUSTION IMMINENT" (checks 2x faster) |

### Enable/Disable

```python
# Monitor is enabled by default when connection_metrics=True (default)
db = DataFlow("postgresql://...", monitoring=True)

# Customize monitoring
# DATAFLOW_POOL_MONITOR_INTERVAL=10  (seconds between checks, default: 10)
```

## Connection Leak Detection

DataFlow tracks connection checkout time and logs warnings when connections are held too long:

```
# Default threshold: 30 seconds
# WARNING: Connection held for 45.2s (threshold: 30s)
#   Checked out at:
#     File "app/routes.py", line 42, in get_users
#       async with db.session() as session:

# After 3x threshold (90s):
# ERROR: Connection held for 95.1s — PROBABLE LEAK
```

### Configuration

| Variable                         | Purpose                                            | Default     |
| -------------------------------- | -------------------------------------------------- | ----------- |
| `DATAFLOW_POOL_MONITOR_INTERVAL` | Monitor check interval                             | `10` (secs) |
| Leak detection threshold         | Config: `monitoring.leak_detection_threshold_secs` | `30` (secs) |

## Startup Validation

DataFlow validates pool configuration at startup:

```
# If pool_size * workers > max_connections:
# ERROR: CONNECTION POOL WILL EXHAUST: pool_size=25 + max_overflow=12 x 4 workers = 148,
#        but max_connections=100. Set DATAFLOW_POOL_SIZE=15

# Disable with:
# DATAFLOW_STARTUP_VALIDATION=false
```

## Diagnostic Flow

1. **Check startup logs** — Look for `[DataFlow] Pool auto-scaled:` or `Pool configured:`
2. **Call `pool_stats()`** — Check utilization percentage
3. **Check health endpoint** — `health_check()["pool"]["utilization"]`
4. **Check leak logs** — Look for "Connection held for" warnings with tracebacks
5. **Use lightweight pool** — `execute_raw_lightweight("SELECT 1")` to verify DB connectivity without consuming main pool

## Common Issues

| Symptom                         | Cause                                       | Fix                                                                                 |
| ------------------------------- | ------------------------------------------- | ----------------------------------------------------------------------------------- |
| "EXHAUSTION IMMINENT" logs      | Pool too small for worker count             | Remove explicit pool_size (let auto-scaling handle it) or set DATAFLOW_WORKER_COUNT |
| "Connection held for Xs"        | Long-running query or leaked connection     | Check the traceback in the log message                                              |
| health_check returns "degraded" | Pool at 95%+ utilization                    | Scale down workers or increase max_connections                                      |
| pool_stats returns all zeros    | No pool monitor (pooling disabled or error) | Check if enable_connection_pooling=True                                             |

<!-- Trigger Keywords: dataflow monitoring, dataflow metrics, pool stats, pool utilization, connection leak, health check, pool exhaustion, pool monitor -->
