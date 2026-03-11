"""
Observability & Performance Monitoring System.

This module provides comprehensive observability capabilities for Kaizen agents:

**System 3: Distributed Tracing** (TracingManager, TracingHook)
- OpenTelemetry-based distributed tracing
- Jaeger integration for trace visualization
- Automatic span creation and propagation

**System 4: Metrics Collection** (MetricsCollector)
- Counter, gauge, histogram metrics
- Prometheus export format
- Performance monitoring with <2% overhead

**System 5: Structured Logging** (StructuredLogger, LoggingManager)
- JSON-formatted logs with context propagation
- ELK Stack integration
- trace_id/span_id correlation

**System 6: Audit Trails** (AuditTrailManager, FileAuditStorage)
- Immutable audit logging for compliance (SOC2, GDPR, HIPAA)
- Append-only storage with querying
- Action tracking with timestamps

**System 7: Unified Manager** (ObservabilityManager)
- Single interface for all observability operations
- Selective component enabling/disabling
- Integrated metrics, logs, traces, audits

Part of Phase 4: Observability & Performance Monitoring (ADR-017)
"""

# System 6: Audit Trails
from kaizen.core.autonomy.observability.audit import (
    AuditStorage,
    AuditTrailManager,
    FileAuditStorage,
)

# System 5: Structured Logging
from kaizen.core.autonomy.observability.logging import LoggingManager, StructuredLogger

# System 7: Unified Manager
from kaizen.core.autonomy.observability.manager import ObservabilityManager

# System 4: Metrics Collection
from kaizen.core.autonomy.observability.metrics import MetricsCollector

# System 3: Distributed Tracing
from kaizen.core.autonomy.observability.tracing_manager import TracingManager

# Type definitions
from kaizen.core.autonomy.observability.types import (
    AuditEntry,
    AuditResult,
    LogEntry,
    LogLevel,
    Metric,
    MetricType,
)

__all__ = [
    # Types
    "Metric",
    "MetricType",
    "LogEntry",
    "LogLevel",
    "AuditEntry",
    "AuditResult",
    # System 3: Tracing
    "TracingManager",
    # System 4: Metrics
    "MetricsCollector",
    # System 5: Logging
    "StructuredLogger",
    "LoggingManager",
    # System 6: Audit
    "AuditStorage",
    "FileAuditStorage",
    "AuditTrailManager",
    # System 7: Unified Manager
    "ObservabilityManager",
]
