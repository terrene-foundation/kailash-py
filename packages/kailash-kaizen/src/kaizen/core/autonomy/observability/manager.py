"""
Unified observability management for comprehensive agent monitoring.

This module provides the ObservabilityManager class which integrates:
- Metrics collection (System 4)
- Structured logging (System 5)
- Distributed tracing (System 3)
- Audit trails (System 6)

The manager provides a single interface for all observability operations,
with selective enabling/disabling of components as needed.

Part of Phase 4: Observability & Performance Monitoring (ADR-017)
"""

import logging
from typing import Any

from kaizen.core.autonomy.observability.audit import AuditTrailManager
from kaizen.core.autonomy.observability.logging import LoggingManager, StructuredLogger
from kaizen.core.autonomy.observability.metrics import MetricsCollector
from kaizen.core.autonomy.observability.tracing_manager import TracingManager
from kaizen.core.autonomy.observability.types import AuditResult, MetricType

logger = logging.getLogger(__name__)


class ObservabilityManager:
    """
    Unified observability management for agent monitoring.

    Integrates all observability subsystems:
    - **Metrics**: Counter, gauge, histogram collection with Prometheus export
    - **Logging**: Structured JSON logs with context propagation (ELK-ready)
    - **Tracing**: Distributed tracing with OpenTelemetry and Jaeger
    - **Audit**: Immutable audit trails for compliance (SOC2, GDPR, HIPAA)

    Components can be selectively enabled/disabled based on requirements.
    Performance overhead targets (ADR-017):
    - Metrics: <2% execution time
    - Logging: <5% execution time
    - Tracing: <1% execution time
    - Audit: <10ms per entry

    Example:
        >>> # Full observability (all components)
        >>> obs = ObservabilityManager(service_name="qa-agent")
        >>> logger = obs.get_logger("qa-agent")
        >>> logger.info("Agent started")
        >>>
        >>> # Selective observability (metrics + logging only)
        >>> obs = ObservabilityManager(
        ...     service_name="qa-agent",
        ...     enable_tracing=False,
        ...     enable_audit=False
        ... )
    """

    def __init__(
        self,
        service_name: str = "kaizen-agent",
        enable_metrics: bool = True,
        enable_logging: bool = True,
        enable_tracing: bool = True,
        enable_audit: bool = True,
    ):
        """
        Initialize observability manager.

        Args:
            service_name: Service name for identification (used by tracing)
            enable_metrics: Enable metrics collection
            enable_logging: Enable structured logging
            enable_tracing: Enable distributed tracing
            enable_audit: Enable audit trail recording

        Example:
            >>> # Full observability
            >>> obs = ObservabilityManager(service_name="qa-agent")
            >>>
            >>> # Metrics and logging only (lightweight)
            >>> obs = ObservabilityManager(
            ...     service_name="qa-agent",
            ...     enable_tracing=False,
            ...     enable_audit=False
            ... )
        """
        self.service_name = service_name

        # Initialize components based on flags
        self.metrics = MetricsCollector() if enable_metrics else None
        self.logging = LoggingManager() if enable_logging else None
        self.tracing = TracingManager(service_name) if enable_tracing else None
        self.audit = AuditTrailManager() if enable_audit else None

        # Track enabled components
        self._enabled_components = {
            "metrics": enable_metrics,
            "logging": enable_logging,
            "tracing": enable_tracing,
            "audit": enable_audit,
        }

        logger.info(
            f"ObservabilityManager initialized for {service_name}",
            extra={"enabled_components": self._enabled_components},
        )

    # ===== Logging Methods =====

    def get_logger(self, name: str) -> StructuredLogger | None:
        """
        Get logger for component.

        Args:
            name: Logger name (typically agent ID or component name)

        Returns:
            StructuredLogger instance (None if logging disabled)

        Example:
            >>> logger = obs.get_logger("qa-agent")
            >>> logger.info("Agent started", task_id="task-123")
        """
        if not self.logging:
            logger.warning("Logging not enabled")
            return None

        return self.logging.get_logger(name)

    # ===== Metrics Methods =====

    async def record_metric(
        self,
        name: str,
        value: float,
        type: MetricType = "counter",
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record a metric observation.

        Args:
            name: Metric name (e.g., "agent_loop_duration_ms")
            value: Metric value
            type: Metric type (counter, gauge, histogram, summary)
            labels: Key-value labels for dimensions

        Example:
            >>> await obs.record_metric(
            ...     "api_calls_total",
            ...     1.0,
            ...     type="counter",
            ...     labels={"provider": "openai"}
            ... )
            >>> await obs.record_metric(
            ...     "memory_bytes",
            ...     1024000,
            ...     type="gauge",
            ...     labels={"agent_id": "qa-agent"}
            ... )
        """
        if not self.metrics:
            return

        if type == "counter":
            self.metrics.counter(name, value, labels)
        elif type == "gauge":
            self.metrics.gauge(name, value, labels)
        elif type == "histogram":
            self.metrics.histogram(name, value, labels)
        else:
            logger.warning(f"Unsupported metric type: {type}")

    async def export_metrics(self) -> str:
        """
        Export metrics in Prometheus format.

        Returns:
            Prometheus-formatted metrics text (empty if metrics disabled)

        Example:
            >>> metrics_text = await obs.export_metrics()
            >>> print(metrics_text)
            # api_calls_total{provider="openai"} 150.0
            # memory_bytes{agent_id="qa-agent"} 1024000.0
        """
        if not self.metrics:
            return ""

        return await self.metrics.export()

    # ===== Tracing Methods =====

    def get_tracing_manager(self) -> TracingManager | None:
        """
        Get tracing manager for advanced tracing operations.

        Returns:
            TracingManager instance (None if tracing disabled)

        Example:
            >>> tracing = obs.get_tracing_manager()
            >>> if tracing:
            ...     async with tracing.span("operation", attributes={"key": "value"}):
            ...         await do_work()
        """
        if not self.tracing:
            logger.warning("Tracing not enabled")
            return None

        return self.tracing

    # ===== Audit Methods =====

    async def record_audit(
        self,
        agent_id: str,
        action: str,
        details: dict[str, Any],
        result: AuditResult,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Record audit trail entry.

        Args:
            agent_id: Agent performing the action
            action: Action identifier (e.g., "tool_execute", "permission_grant")
            details: Action-specific details (must be JSON-serializable)
            result: Action result (success, failure, denied)
            user_id: User who triggered the action (optional)
            metadata: Additional metadata (optional)

        Example:
            >>> await obs.record_audit(
            ...     agent_id="qa-agent",
            ...     action="tool_execute",
            ...     details={"tool_name": "bash", "command": "ls"},
            ...     result="success",
            ...     user_id="user@example.com"
            ... )
        """
        if not self.audit:
            return

        await self.audit.record(
            agent_id=agent_id,
            action=action,
            details=details,
            result=result,
            user_id=user_id,
            metadata=metadata,
        )

    async def query_audit_by_agent(self, agent_id: str):
        """
        Query audit entries for specific agent.

        Args:
            agent_id: Agent ID to query

        Returns:
            List of audit entries (empty if audit disabled)

        Example:
            >>> entries = await obs.query_audit_by_agent("qa-agent")
        """
        if not self.audit:
            return []

        return await self.audit.query_by_agent(agent_id)

    async def query_audit_by_action(self, action: str):
        """
        Query audit entries for specific action.

        Args:
            action: Action type to query

        Returns:
            List of audit entries (empty if audit disabled)

        Example:
            >>> entries = await obs.query_audit_by_action("tool_execute")
        """
        if not self.audit:
            return []

        return await self.audit.query_by_action(action)

    # ===== Status & Configuration =====

    def is_component_enabled(self, component: str) -> bool:
        """
        Check if component is enabled.

        Args:
            component: Component name (metrics, logging, tracing, audit)

        Returns:
            True if component is enabled

        Example:
            >>> if obs.is_component_enabled("tracing"):
            ...     # Use tracing features
        """
        return self._enabled_components.get(component, False)

    def get_enabled_components(self) -> list[str]:
        """
        Get list of enabled components.

        Returns:
            List of enabled component names

        Example:
            >>> enabled = obs.get_enabled_components()
            >>> print(f"Enabled: {enabled}")
            # Enabled: ['metrics', 'logging', 'tracing', 'audit']
        """
        return [name for name, enabled in self._enabled_components.items() if enabled]

    def get_service_name(self) -> str:
        """
        Get service name.

        Returns:
            Service name configured for this manager
        """
        return self.service_name

    # ===== Cleanup =====

    def shutdown(self) -> None:
        """
        Shutdown observability manager and cleanup resources.

        Call this when agent is done to ensure proper cleanup of:
        - Open file handles (audit log)
        - Tracing exporters
        - Metric collectors

        Example:
            >>> obs = ObservabilityManager()
            >>> try:
            ...     # Use obs...
            ... finally:
            ...     obs.shutdown()
        """
        # Shutdown tracing manager
        if self.tracing:
            try:
                self.tracing.shutdown()
                logger.debug("Tracing manager shutdown")
            except Exception as e:
                logger.warning(f"Error shutting down tracing: {e}")

        # Clear logging contexts
        if self.logging:
            try:
                self.logging.clear_all_context()
                logger.debug("Logging contexts cleared")
            except Exception as e:
                logger.warning(f"Error clearing logging contexts: {e}")

        logger.info(f"ObservabilityManager shutdown for {self.service_name}")


__all__ = [
    "ObservabilityManager",
]
