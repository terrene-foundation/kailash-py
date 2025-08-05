# DataFlow Troubleshooting Guide

Comprehensive guide to diagnosing and resolving common issues in DataFlow applications.

**🎉 Major Updates for v0.4.0**: Many common issues have been resolved in the latest release. Check if updating resolves your issue first.

## Common Issues

### Database Connection Issues

**Symptoms:**
- `AdapterError: Invalid connection string`
- `invalid literal for int() with base 10` errors
- Connection failures with special characters in passwords

**Common Causes (Fixed in v0.9.4+ and v0.4.0+):**
- Special characters in database passwords (#, $, @, ?) - FIXED in v0.9.4
- Incorrect URL encoding/decoding - IMPROVED in v0.9.4
- PostgreSQL parameter type casting issues - FIXED in v0.4.0
- Malformed connection strings

**Diagnosis:**
```python
from dataflow.adapters.connection_parser import ConnectionParser

# Test connection string parsing
connection_string = "postgresql://admin:MySecret#123$@localhost:5432/mydb"
try:
    components = ConnectionParser.parse_connection_string(connection_string)
    print(f"✅ Parsed successfully: {components}")
except Exception as e:
    print(f"❌ Parsing failed: {e}")
```

**Solutions:**
```python
# ✅ Since v0.9.4: Special characters work automatically
# ✅ Since v0.4.0: Enhanced parameter type casting
db = DataFlow(
    database_url="postgresql://admin:Complex#Pass$word@localhost:5432/mydb"
)

# ✅ Alternative: Manual URL encoding (for older versions)
from urllib.parse import quote
password = quote("Complex#Pass$word", safe="")
connection_string = f"postgresql://admin:{password}@localhost:5432/mydb"

# ✅ Environment variables (recommended for production)
import os
db = DataFlow(
    database_url=os.getenv("DATABASE_URL", "postgresql://admin:password@localhost:5432/mydb")
)
```

**Prevention Tips:**
- Use environment variables for connection strings
- Test connection parsing in development
- Validate connection strings before deployment

### Connection Pool Exhaustion

**Symptoms:**
- `PoolTimeoutError: Unable to acquire connection within timeout`
- Slow response times
- Application hangs

**Diagnosis:**
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
# Check pool statistics
workflow = WorkflowBuilder()
workflow.add_node("PoolDiagnosticsNode", "check_pool", {
    "include": ["active", "idle", "overflow", "wait_queue", "timeouts"]
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
print(f"Pool stats: {results['check_pool']}")
```

**Solutions:**
```python
# 1. Increase pool size
config = DataFlowConfig(
    pool_size=50,  # Increased from default
    pool_max_overflow=100,
    pool_timeout=30.0
)

# 2. Identify connection leaks
workflow.add_node("ConnectionLeakDetectorNode", "find_leaks", {
    "threshold": 300,  # Connections older than 5 minutes
    "action": "log_and_close"
})

# 3. Enable connection recycling
config.pool_recycle = 3600  # Recycle after 1 hour
```

### Slow Queries

**Symptoms:**
- High response times
- Database CPU spikes
- Query timeouts

**Diagnosis:**
```python
# Enable slow query logging
workflow.add_node("SlowQueryLoggerNode", "log_slow", {
    "threshold": 1.0,  # 1 second
    "log_explain": True,
    "capture_stack_trace": True
})

# Analyze query patterns
workflow.add_node("QueryPatternAnalyzerNode", "analyze", {
    "period": "1h",
    "group_by": ["query_type", "table", "filter_fields"],
    "identify": ["missing_indexes", "full_scans", "n_plus_one"]
})
```

**Solutions:**
```python
# 1. Add missing indexes
workflow.add_node("IndexAdvisorNode", "suggest_indexes", {
    "analyze_period": "24h",
    "min_impact": 0.1,  # 10% performance improvement
    "generate_sql": True
})

# 2. Optimize query
workflow.add_node("QueryOptimizerNode", "optimize", {
    "query": slow_query,
    "strategies": ["rewrite", "denormalize", "cache"],
    "test_performance": True
})
```

### Memory Issues

**Symptoms:**
- Out of memory errors
- Gradual memory increase
- Application crashes

**Diagnosis:**
```python
# Memory profiling
import tracemalloc

tracemalloc.start()

# Run workflow
workflow = create_workflow()
runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

# Get memory statistics
current, peak = tracemalloc.get_traced_memory()
print(f"Current memory usage: {current / 1024 / 1024:.2f} MB")
print(f"Peak memory usage: {peak / 1024 / 1024:.2f} MB")

# Top memory allocations
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
for stat in top_stats[:10]:
    print(stat)
```

**Solutions:**
```python
# 1. Use streaming for large datasets
workflow.add_node("StreamingQueryNode", "stream_data", {
    "query": "SELECT * FROM large_table",
    "chunk_size": 1000,
    "process_chunk": "chunk_processor"
})

# 2. Clear caches periodically
workflow.add_node("CacheClearNode", "clear_old_cache", {
    "strategy": "lru",  # Least recently used
    "max_memory": "1GB",
    "clear_interval": "1h"
})

# 3. Use weak references for large objects
from weakref import WeakValueDictionary
large_object_cache = WeakValueDictionary()
```

### Transaction Deadlocks

**Symptoms:**
- `OperationalError: deadlock detected`
- Transactions timing out
- Inconsistent data

**Diagnosis:**
```python
# Deadlock monitoring
workflow.add_node("DeadlockMonitorNode", "monitor", {
    "detect_patterns": True,
    "log_wait_graph": True,
    "alert_on_detection": True
})

# Transaction analysis
workflow.add_node("TransactionAnalyzerNode", "analyze_tx", {
    "identify": ["long_running", "blocking", "circular_waits"],
    "suggest_lock_ordering": True
})
```

**Solutions:**
```python
# 1. Consistent lock ordering
workflow.add_node("OrderedLockNode", "acquire_locks", {
    "resources": ["users", "accounts", "transactions"],
    "order": "alphabetical",  # Always same order
    "timeout": 5.0
})

# 2. Retry with exponential backoff
workflow.add_node("RetryableTransactionNode", "retry_tx", {
    "max_attempts": 3,
    "backoff": "exponential",
    "on_deadlock": "retry",
    "jitter": True
})

# 3. Use advisory locks
workflow.add_node("AdvisoryLockNode", "lock_resource", {
    "resource_id": "user_123_account_456",
    "timeout": 10.0,
    "skip_locked": True
})
```

### Data Corruption (Many Issues Fixed in v0.4.0)

**Symptoms:**
- Constraint violations - IMPROVED with better parameter type casting
- Inconsistent relationships - FIXED with corrected workflow connections
- Missing or duplicate data
- Content truncation at 255 characters - FIXED (now TEXT unlimited)
- DateTime serialization errors - FIXED in v0.4.0

**Diagnosis:**
```python
# Data integrity check
workflow.add_node("DataIntegrityCheckNode", "check_integrity", {
    "checks": [
        "foreign_key_consistency",
        "unique_constraints",
        "not_null_violations",
        "orphaned_records",
        "duplicate_detection"
    ],
    "generate_report": True
})

# Audit trail analysis
workflow.add_node("AuditTrailAnalyzerNode", "analyze_changes", {
    "period": "7d",
    "suspicious_patterns": [
        "bulk_deletes",
        "unauthorized_access",
        "timestamp_anomalies"
    ]
})
```

**Solutions:**
```python
# 1. Data repair workflow
workflow.add_node("DataRepairNode", "fix_orphans", {
    "strategy": "cascade_delete",  # or "reconnect"
    "dry_run": True,  # Test first
    "backup_before": True
})

# 2. Add validation
@db.model
class Order:
    id: int
    user_id: int
    total: float

    __dataflow__ = {
        'constraints': [
            {'type': 'check', 'condition': 'total >= 0'},
            {'type': 'foreign_key', 'field': 'user_id', 'references': 'users.id'}
        ],
        'triggers': [
            {
                'name': 'validate_order',
                'timing': 'BEFORE INSERT OR UPDATE',
                'function': 'validate_order_data()'
            }
        ]
    }
```

## Debugging Techniques

### Enable Debug Logging

```python
import logging

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dataflow_debug.log'),
        logging.StreamHandler()
    ]
)

# Enable SQL logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
logging.getLogger('sqlalchemy.pool').setLevel(logging.DEBUG)

# Enable workflow logging
logging.getLogger('kailash.workflow').setLevel(logging.DEBUG)
```

### Interactive Debugging

```python
# Use Python debugger
import pdb

workflow.add_node("PythonCodeNode", "debug_point", {
    "code": """
import pdb
pdb.set_trace()  # Breakpoint

# Inspect variables
data = get_input_data()
print(f"Input data: {data}")

# Step through execution
result = process_data(data)
"""
})

# Remote debugging with debugpy
import debugpy
debugpy.listen(5678)
debugpy.wait_for_client()  # Wait for debugger attachment
```

### Performance Profiling

```python
import cProfile
import pstats

# Profile workflow execution
profiler = cProfile.Profile()
profiler.enable()

workflow = create_complex_workflow()
runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

profiler.disable()

# Analyze results
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20 functions
```

### Database Query Analysis

```python
# PostgreSQL query analysis
workflow.add_node("PGStatStatementsNode", "analyze_queries", {
    "top_n": 20,
    "order_by": "total_time",
    "include_plans": True
})

# MySQL slow query log
workflow.add_node("MySQLSlowLogNode", "parse_slow_log", {
    "log_file": "/var/log/mysql/slow.log",
    "min_duration": 1.0,
    "analyze_patterns": True
})
```

## Error Recovery

### Automatic Recovery

```python
# Self-healing workflow
workflow.add_node("HealthCheckNode", "check_health", {
    "checks": ["database", "cache", "external_apis"],
    "interval": "30s"
})

workflow.add_node("AutoRecoveryNode", "auto_recover", {
    "strategies": {
        "database_down": "failover_to_replica",
        "cache_down": "bypass_cache",
        "api_down": "use_fallback"
    },
    "max_recovery_attempts": 3
})
```

### Manual Recovery Procedures

```python
# Database recovery
def recover_database():
    """Emergency database recovery procedure."""
    # 1. Check connection
    try:
        db.execute("SELECT 1")
    except Exception as e:
        logger.error(f"Database down: {e}")

        # 2. Reset connection pool
        db.dispose_pool()

        # 3. Try failover
        db.failover_to_replica()

        # 4. Verify recovery
        db.execute("SELECT 1")
        logger.info("Database recovered")

# Cache recovery
def recover_cache():
    """Cache recovery procedure."""
    try:
        # 1. Clear corrupted cache
        cache.flushall()

        # 2. Warm critical cache
        warm_critical_cache()

        # 3. Enable gradual warming
        enable_lazy_cache_warming()

    except Exception as e:
        logger.error(f"Cache recovery failed: {e}")
        # Bypass cache temporarily
        db.cache_enabled = False
```

## Monitoring and Alerts

### Set Up Alerts

```python
workflow.add_node("AlertConfigNode", "configure_alerts", {
    "rules": [
        {
            "name": "pool_exhaustion",
            "condition": "pool_wait_time > 5.0",
            "severity": "critical",
            "actions": ["page_oncall", "auto_scale"]
        },
        {
            "name": "high_error_rate",
            "condition": "error_rate > 0.05",  # 5%
            "severity": "high",
            "actions": ["email_team", "create_incident"]
        },
        {
            "name": "data_corruption",
            "condition": "integrity_check_failed",
            "severity": "critical",
            "actions": ["page_oncall", "stop_writes"]
        }
    ]
})
```

### Dashboard Setup

```python
# Grafana dashboard config
dashboard_config = {
    "panels": [
        {
            "title": "Query Performance",
            "metrics": ["query_duration_p95", "slow_queries_rate"],
            "threshold": {"warning": 1.0, "critical": 5.0}
        },
        {
            "title": "Connection Pool",
            "metrics": ["pool_utilization", "connection_wait_time"],
            "threshold": {"warning": 0.8, "critical": 0.95}
        },
        {
            "title": "Error Rates",
            "metrics": ["error_rate_by_type", "deadlock_rate"],
            "threshold": {"warning": 0.01, "critical": 0.05}
        }
    ]
}
```

## Emergency Procedures

### Database Failover

```python
# Manual failover procedure
def emergency_failover():
    """Emergency database failover."""
    # 1. Verify primary is down
    if not check_primary_health():
        # 2. Promote replica
        promote_replica_to_primary()

        # 3. Update connection strings
        update_app_config(new_primary_url)

        # 4. Restart connection pools
        restart_all_app_instances()

        # 5. Verify failover
        verify_failover_complete()
```

### Data Recovery

```python
# Point-in-time recovery
workflow.add_node("PointInTimeRecoveryNode", "recover_data", {
    "timestamp": "2024-01-15T10:30:00Z",
    "tables": ["orders", "payments"],
    "strategy": "restore_to_temp",
    "verify_before_swap": True
})
```

## Best Practices

1. **Always Have Backups**: Regular automated backups with tested restore procedures
2. **Monitor Proactively**: Set up alerts before issues become critical
3. **Document Everything**: Keep runbooks for common issues
4. **Test Recovery**: Regularly test disaster recovery procedures
5. **Use Circuit Breakers**: Prevent cascade failures
6. **Implement Retries**: With exponential backoff for transient errors
7. **Log Comprehensively**: But avoid logging sensitive data
8. **Version Everything**: Database schemas, configurations, and code
9. **Update Regularly**: v0.4.0+ includes 11+ critical bug fixes
10. **Test Migration Scenarios**: auto_migrate=False now works correctly
11. **Use TEXT Fields**: VARCHAR(255) limits removed in v0.4.0

## Next Steps

- **Performance**: [Performance Guide](performance.md)
- **Monitoring**: [Monitoring Guide](../advanced/monitoring.md)
- **Security**: [Security Guide](../advanced/security.md)

Effective troubleshooting requires preparation, monitoring, and well-documented procedures. Stay proactive!
