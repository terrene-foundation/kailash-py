"""
Monitoring and alerting system for Kailash SDK.

Provides comprehensive monitoring for validation failures, security violations,
performance metrics, and alerting for critical events. Includes specialized
AsyncSQL lock contention monitoring.
"""

# Original monitoring imports
from .alerts import AlertManager, AlertRule, AlertSeverity

# AsyncSQL lock monitoring imports
from .asyncsql_metrics import (
    PROMETHEUS_AVAILABLE,
    AsyncSQLMetrics,
    disable_metrics,
    enable_metrics,
    get_global_metrics,
    integrate_with_async_sql,
    record_lock_acquisition,
    record_pool_operation,
    set_active_locks,
    set_global_metrics,
)
from .metrics import PerformanceMetrics, SecurityMetrics, ValidationMetrics

__all__ = [
    "ValidationMetrics",
    "SecurityMetrics",
    "PerformanceMetrics",
    "AlertManager",
    "AlertRule",
    "AlertSeverity",
    # AsyncSQL monitoring
    "AsyncSQLMetrics",
    "enable_metrics",
    "disable_metrics",
    "get_global_metrics",
    "set_global_metrics",
    "record_lock_acquisition",
    "record_pool_operation",
    "set_active_locks",
    "integrate_with_async_sql",
    "PROMETHEUS_AVAILABLE",
]
