"""
Observability type definitions for metrics, logs, spans, and audit entries.

This module provides the core data structures used across the observability system:
- Metric: Counter, gauge, histogram observations
- LogEntry: Structured log entries with context
- Span: Distributed tracing spans (already handled by OpenTelemetry)
- AuditEntry: Immutable audit trail entries for compliance

Part of Phase 4: Observability & Performance Monitoring (ADR-017)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

# Metric types following Prometheus naming conventions
MetricType = Literal["counter", "gauge", "histogram", "summary"]

# Log levels following Python logging standard
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Audit result types
AuditResult = Literal["success", "failure", "denied"]


@dataclass
class Metric:
    """
    Single metric observation for monitoring agent performance.

    Supports Prometheus metric types:
    - counter: Monotonically increasing value (e.g., total API calls)
    - gauge: Point-in-time value (e.g., memory usage)
    - histogram: Distribution of values (e.g., request latency)
    - summary: Similar to histogram with calculated quantiles

    Example:
        >>> metric = Metric(
        ...     name="agent_loop_duration_ms",
        ...     value=125.5,
        ...     type="histogram",
        ...     timestamp=datetime.now(timezone.utc),
        ...     labels={"agent_id": "qa-agent", "status": "success"},
        ...     unit="milliseconds"
        ... )
    """

    name: str
    value: float
    type: MetricType
    timestamp: datetime
    labels: dict[str, str] = field(default_factory=dict)
    unit: str | None = None


@dataclass
class LogEntry:
    """
    Structured log entry with context propagation for distributed debugging.

    Supports correlation across distributed systems via trace_id and span_id.
    Context dict allows arbitrary key-value pairs for structured logging.

    Example:
        >>> entry = LogEntry(
        ...     timestamp=datetime.now(timezone.utc),
        ...     level="INFO",
        ...     message="Tool executed successfully",
        ...     context={"tool_name": "search", "duration_ms": 45.2},
        ...     agent_id="qa-agent",
        ...     trace_id="abc123",
        ...     span_id="def456"
        ... )
    """

    timestamp: datetime
    level: LogLevel
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    agent_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None


@dataclass
class AuditEntry:
    """
    Immutable audit trail entry for compliance and security logging.

    Records critical actions that require audit trails for enterprise compliance
    (SOC2, GDPR, HIPAA). Entries are append-only and never modified.

    Common actions:
    - "tool_execute": Tool invocation
    - "permission_grant": Permission approved
    - "permission_deny": Permission denied
    - "checkpoint_save": State checkpoint saved
    - "checkpoint_load": State checkpoint loaded
    - "interrupt_triggered": Interrupt mechanism activated

    Example:
        >>> entry = AuditEntry(
        ...     timestamp=datetime.now(timezone.utc),
        ...     agent_id="qa-agent",
        ...     user_id="user@example.com",
        ...     action="tool_execute",
        ...     details={"tool_name": "bash_command", "command": "ls -la"},
        ...     result="success",
        ...     metadata={"danger_level": "MODERATE", "approved_by": "user"}
        ... )
    """

    timestamp: datetime
    agent_id: str
    action: str  # Action identifier (e.g., "tool_execute", "permission_grant")
    details: dict[str, Any]  # Action-specific details
    result: AuditResult  # Outcome of the action
    user_id: str | None = None  # User who triggered the action (optional)
    metadata: dict[str, Any] = field(default_factory=dict)  # Additional context


# Note: Span type is handled by OpenTelemetry's trace.Span class
# We don't need a custom Span dataclass as OpenTelemetry provides a complete implementation
# See: opentelemetry.trace.Span for the trace span interface

__all__ = [
    "MetricType",
    "LogLevel",
    "AuditResult",
    "Metric",
    "LogEntry",
    "AuditEntry",
]
