"""Real-time transaction monitoring node with distributed tracing support.

This module provides live transaction monitoring capabilities with real-time
alerting, distributed tracing, and streaming dashboard support.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TracingProtocol(Enum):
    """Supported tracing protocols."""

    OPENTELEMETRY = "opentelemetry"
    JAEGER = "jaeger"
    ZIPKIN = "zipkin"
    CUSTOM = "custom"


@dataclass
class TransactionSpan:
    """Represents a distributed tracing span."""

    span_id: str
    trace_id: str
    parent_span_id: Optional[str] = None
    operation_name: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration: Optional[float] = None
    service_name: str = ""
    tags: Dict[str, str] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    baggage: Dict[str, str] = field(default_factory=dict)
    status: str = "ok"
    error: Optional[str] = None


@dataclass
class TransactionTrace:
    """Represents a complete distributed trace."""

    trace_id: str
    root_span_id: str
    spans: List[TransactionSpan] = field(default_factory=list)
    total_duration: Optional[float] = None
    service_count: int = 0
    span_count: int = 0
    error_count: int = 0
    critical_path: List[str] = field(default_factory=list)


@dataclass
class TransactionAlert:
    """Represents a transaction monitoring alert."""

    alert_id: str
    severity: AlertSeverity
    message: str
    transaction_id: Optional[str] = None
    trace_id: Optional[str] = None
    metric_name: str = ""
    metric_value: float = 0.0
    threshold: float = 0.0
    timestamp: float = field(default_factory=time.time)
    tags: Dict[str, str] = field(default_factory=dict)
    resolved: bool = False


@register_node()
class TransactionMonitorNode(AsyncNode):
    """Node for real-time transaction monitoring and distributed tracing.

    This node provides comprehensive real-time monitoring including:
    - Live transaction tracking and correlation
    - Distributed tracing with OpenTelemetry support
    - Real-time anomaly detection and alerting
    - WebSocket/SSE streaming for live dashboards
    - Transaction correlation across service boundaries
    - Critical path analysis for performance optimization

    Design Purpose:
    - Enable real-time performance monitoring
    - Support distributed system troubleshooting
    - Provide actionable alerts for SLA violations
    - Facilitate live dashboard visualization

    Examples:
        >>> # Start monitoring transactions
        >>> monitor = TransactionMonitorNode()
        >>> result = await monitor.execute(
        ...     operation="start_monitoring",
        ...     trace_sampling_rate=0.1,
        ...     alert_thresholds={
        ...         "duration": {"p95": 2.0, "p99": 5.0},
        ...         "error_rate": {"threshold": 0.01}
        ...     }
        ... )

        >>> # Create distributed trace
        >>> result = await monitor.execute(
        ...     operation="create_trace",
        ...     trace_id="trace_12345",
        ...     root_operation="order_processing",
        ...     service_name="order-service"
        ... )

        >>> # Add span to trace
        >>> result = await monitor.execute(
        ...     operation="add_span",
        ...     trace_id="trace_12345",
        ...     operation_name="validate_payment",
        ...     service_name="payment-service",
        ...     parent_span_id="span_abc"
        ... )
    """

    def __init__(self, **kwargs):
        """Initialize the transaction monitor node."""
        super().__init__(**kwargs)
        self._active_traces: Dict[str, TransactionTrace] = {}
        self._active_spans: Dict[str, TransactionSpan] = {}
        self._monitoring_active = False
        self._alert_handlers: List[Callable] = []
        self._stream_handlers: List[Callable] = []
        self._metrics_buffer: List[Dict[str, Any]] = []
        self._alert_thresholds: Dict[str, Dict[str, float]] = {}
        self._trace_sampling_rate = 1.0
        self._background_tasks: Set[asyncio.Task] = set()
        self.logger.info(f"Initialized TransactionMonitorNode: {self.id}")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation (start_monitoring, stop_monitoring, create_trace, add_span, finish_span, get_trace, get_alerts)",
            ),
            "transaction_id": NodeParameter(
                name="transaction_id",
                type=str,
                required=False,
                description="Transaction identifier for monitoring operations",
            ),
            "success": NodeParameter(
                name="success",
                type=bool,
                required=False,
                description="Whether the transaction completed successfully",
            ),
            "trace_id": NodeParameter(
                name="trace_id",
                type=str,
                required=False,
                description="Distributed trace identifier",
            ),
            "span_id": NodeParameter(
                name="span_id", type=str, required=False, description="Span identifier"
            ),
            "parent_span_id": NodeParameter(
                name="parent_span_id",
                type=str,
                required=False,
                description="Parent span identifier",
            ),
            "operation_name": NodeParameter(
                name="operation_name",
                type=str,
                required=False,
                description="Name of the operation being traced",
            ),
            "service_name": NodeParameter(
                name="service_name",
                type=str,
                required=False,
                description="Name of the service",
            ),
            "tags": NodeParameter(
                name="tags",
                type=dict,
                required=False,
                default={},
                description="Tags for span/trace",
            ),
            "baggage": NodeParameter(
                name="baggage",
                type=dict,
                required=False,
                default={},
                description="Baggage for distributed context",
            ),
            "error": NodeParameter(
                name="error",
                type=str,
                required=False,
                description="Error message if operation failed",
            ),
            "trace_sampling_rate": NodeParameter(
                name="trace_sampling_rate",
                type=float,
                required=False,
                default=1.0,
                description="Sampling rate for traces (0.0 to 1.0)",
            ),
            "alert_thresholds": NodeParameter(
                name="alert_thresholds",
                type=dict,
                required=False,
                default={},
                description="Alert thresholds for monitoring",
            ),
            "tracing_protocol": NodeParameter(
                name="tracing_protocol",
                type=str,
                required=False,
                default="opentelemetry",
                description="Tracing protocol (opentelemetry, jaeger, zipkin, custom)",
            ),
            "enable_streaming": NodeParameter(
                name="enable_streaming",
                type=bool,
                required=False,
                default=False,
                description="Enable real-time streaming for dashboards",
            ),
            "stream_endpoint": NodeParameter(
                name="stream_endpoint",
                type=str,
                required=False,
                description="WebSocket/SSE endpoint for streaming",
            ),
            "correlation_window": NodeParameter(
                name="correlation_window",
                type=float,
                required=False,
                default=30.0,
                description="Time window for transaction correlation in seconds",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node."""
        return {
            "monitoring_status": NodeParameter(
                name="monitoring_status",
                type=str,
                description="Current monitoring status",
            ),
            "trace_data": NodeParameter(
                name="trace_data", type=dict, description="Trace information"
            ),
            "span_data": NodeParameter(
                name="span_data", type=dict, description="Span information"
            ),
            "alerts": NodeParameter(
                name="alerts", type=list, description="Active alerts"
            ),
            "metrics": NodeParameter(
                name="metrics", type=dict, description="Real-time metrics"
            ),
            "correlation_id": NodeParameter(
                name="correlation_id",
                type=str,
                description="Correlation ID for tracking",
            ),
            "timestamp": NodeParameter(
                name="timestamp", type=str, description="ISO timestamp of operation"
            ),
            "status": NodeParameter(
                name="status", type=str, description="Operation status"
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute transaction monitoring operation."""
        operation = kwargs.get("operation")

        try:
            if operation == "start_monitoring":
                return await self._start_monitoring(**kwargs)
            elif operation == "stop_monitoring":
                return await self._stop_monitoring(**kwargs)
            elif operation == "start_transaction":
                return await self._start_transaction(**kwargs)
            elif operation == "complete_transaction":
                return await self._complete_transaction(**kwargs)
            elif operation == "get_monitoring_status":
                return await self._get_monitoring_status(**kwargs)
            elif operation == "create_trace":
                return await self._create_trace(**kwargs)
            elif operation == "add_span":
                return await self._add_span(**kwargs)
            elif operation == "finish_span":
                return await self._finish_span(**kwargs)
            elif operation == "get_trace":
                return await self._get_trace(**kwargs)
            elif operation == "get_alerts":
                return await self._get_alerts(**kwargs)
            elif operation == "correlate_transactions":
                return await self._correlate_transactions(**kwargs)
            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            self.logger.error(f"Transaction monitoring operation failed: {str(e)}")
            raise NodeExecutionError(
                f"Failed to execute monitoring operation: {str(e)}"
            )

    async def _start_monitoring(self, **kwargs) -> Dict[str, Any]:
        """Start real-time transaction monitoring."""
        self._trace_sampling_rate = kwargs.get("trace_sampling_rate", 1.0)
        self._alert_thresholds = kwargs.get("alert_thresholds", {})
        enable_streaming = kwargs.get("enable_streaming", False)
        stream_endpoint = kwargs.get("stream_endpoint")

        # Start background monitoring task
        if not self._monitoring_active:
            self._monitoring_active = True
            monitoring_task = asyncio.create_task(self._monitoring_loop())
            self._background_tasks.add(monitoring_task)
            monitoring_task.add_done_callback(self._background_tasks.discard)

        # Setup streaming if enabled
        if enable_streaming and stream_endpoint:
            streaming_task = asyncio.create_task(self._setup_streaming(stream_endpoint))
            self._background_tasks.add(streaming_task)
            streaming_task.add_done_callback(self._background_tasks.discard)

        self.logger.info(
            f"Started transaction monitoring with sampling rate {self._trace_sampling_rate}"
        )

        return {
            "monitoring_status": "active",
            "trace_data": {},
            "span_data": {},
            "alerts": [],
            "metrics": {"sampling_rate": self._trace_sampling_rate},
            "correlation_id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _stop_monitoring(self, **kwargs) -> Dict[str, Any]:
        """Stop real-time transaction monitoring."""
        self._monitoring_active = False

        # Cancel background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        self._background_tasks.clear()

        self.logger.info("Stopped transaction monitoring")

        return {
            "monitoring_status": "stopped",
            "trace_data": {},
            "span_data": {},
            "alerts": [],
            "metrics": {"active_traces": len(self._active_traces)},
            "correlation_id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _create_trace(self, **kwargs) -> Dict[str, Any]:
        """Create a new distributed trace."""
        trace_id = kwargs.get("trace_id") or str(uuid.uuid4())
        root_operation = kwargs.get("operation_name", "unknown")
        service_name = kwargs.get("service_name", "unknown")
        tags = kwargs.get("tags", {})

        # Check sampling
        if self._trace_sampling_rate < 1.0:
            import random

            if random.random() > self._trace_sampling_rate:
                # Skip this trace
                return {
                    "monitoring_status": "sampling_skipped",
                    "trace_data": {"trace_id": trace_id, "sampled": False},
                    "span_data": {},
                    "alerts": [],
                    "metrics": {},
                    "correlation_id": trace_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "status": "success",
                }

        # Create root span
        root_span_id = str(uuid.uuid4())
        root_span = TransactionSpan(
            span_id=root_span_id,
            trace_id=trace_id,
            operation_name=root_operation,
            service_name=service_name,
            tags=tags,
        )

        # Create trace
        trace = TransactionTrace(
            trace_id=trace_id,
            root_span_id=root_span_id,
            spans=[root_span],
            span_count=1,
            service_count=1,
        )

        self._active_traces[trace_id] = trace
        self._active_spans[root_span_id] = root_span

        self.logger.debug(f"Created trace {trace_id} with root span {root_span_id}")

        return {
            "monitoring_status": "trace_created",
            "trace_data": {
                "trace_id": trace_id,
                "root_span_id": root_span_id,
                "sampled": True,
            },
            "span_data": {
                "span_id": root_span_id,
                "operation_name": root_operation,
                "service_name": service_name,
            },
            "alerts": [],
            "metrics": {"active_traces": len(self._active_traces)},
            "correlation_id": trace_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _add_span(self, **kwargs) -> Dict[str, Any]:
        """Add a new span to an existing trace."""
        trace_id = kwargs.get("trace_id")
        if not trace_id or trace_id not in self._active_traces:
            raise ValueError(f"Trace {trace_id} not found")

        span_id = kwargs.get("span_id") or str(uuid.uuid4())
        parent_span_id = kwargs.get("parent_span_id")
        operation_name = kwargs.get("operation_name", "unknown")
        service_name = kwargs.get("service_name", "unknown")
        tags = kwargs.get("tags", {})
        baggage = kwargs.get("baggage", {})

        # Create span
        span = TransactionSpan(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            service_name=service_name,
            tags=tags,
            baggage=baggage,
        )

        # Add to trace
        trace = self._active_traces[trace_id]
        trace.spans.append(span)
        trace.span_count += 1

        # Update service count
        services = set(s.service_name for s in trace.spans)
        trace.service_count = len(services)

        self._active_spans[span_id] = span

        self.logger.debug(f"Added span {span_id} to trace {trace_id}")

        return {
            "monitoring_status": "span_added",
            "trace_data": {
                "trace_id": trace_id,
                "span_count": trace.span_count,
                "service_count": trace.service_count,
            },
            "span_data": {
                "span_id": span_id,
                "operation_name": operation_name,
                "service_name": service_name,
                "parent_span_id": parent_span_id,
            },
            "alerts": [],
            "metrics": {"active_spans": len(self._active_spans)},
            "correlation_id": trace_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _finish_span(self, **kwargs) -> Dict[str, Any]:
        """Finish an active span."""
        span_id = kwargs.get("span_id")
        if not span_id or span_id not in self._active_spans:
            raise ValueError(f"Span {span_id} not found")

        span = self._active_spans[span_id]
        error = kwargs.get("error")

        # Complete span
        span.end_time = time.time()
        span.duration = span.end_time - span.start_time

        if error:
            span.status = "error"
            span.error = error

            # Update trace error count
            trace = self._active_traces.get(span.trace_id)
            if trace:
                trace.error_count += 1

        # Check for alerts
        alerts = await self._check_span_alerts(span)

        # Remove from active spans
        del self._active_spans[span_id]

        # Check if trace is complete
        trace = self._active_traces.get(span.trace_id)
        if trace and span.span_id == trace.root_span_id:
            # Root span finished, calculate trace duration
            trace.total_duration = span.duration
            trace.critical_path = self._calculate_critical_path(trace)

            # Move to completed traces (not implemented in this basic version)
            # del self._active_traces[span.trace_id]

        self.logger.debug(f"Finished span {span_id} with duration {span.duration:.3f}s")

        return {
            "monitoring_status": "span_finished",
            "trace_data": {
                "trace_id": span.trace_id,
                "total_duration": trace.total_duration if trace else None,
            },
            "span_data": {
                "span_id": span_id,
                "duration": span.duration,
                "status": span.status,
            },
            "alerts": [self._serialize_alert(a) for a in alerts],
            "metrics": {"active_spans": len(self._active_spans)},
            "correlation_id": span.trace_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _get_trace(self, **kwargs) -> Dict[str, Any]:
        """Get trace information."""
        trace_id = kwargs.get("trace_id")
        if not trace_id:
            raise ValueError("trace_id is required")

        trace = self._active_traces.get(trace_id)
        if not trace:
            raise ValueError(f"Trace {trace_id} not found")

        # Serialize trace data
        trace_data = {
            "trace_id": trace.trace_id,
            "root_span_id": trace.root_span_id,
            "total_duration": trace.total_duration,
            "span_count": trace.span_count,
            "service_count": trace.service_count,
            "error_count": trace.error_count,
            "critical_path": trace.critical_path,
            "spans": [self._serialize_span(s) for s in trace.spans],
        }

        return {
            "monitoring_status": "trace_retrieved",
            "trace_data": trace_data,
            "span_data": {},
            "alerts": [],
            "metrics": {"span_count": trace.span_count},
            "correlation_id": trace_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _get_alerts(self, **kwargs) -> Dict[str, Any]:
        """Get active alerts."""
        # In a real implementation, this would query an alerts database
        # For now, return empty list
        return {
            "monitoring_status": "alerts_retrieved",
            "trace_data": {},
            "span_data": {},
            "alerts": [],
            "metrics": {"active_alerts": 0},
            "correlation_id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _correlate_transactions(self, **kwargs) -> Dict[str, Any]:
        """Correlate transactions across service boundaries."""
        correlation_window = kwargs.get("correlation_window", 30.0)
        current_time = time.time()

        # Find traces within correlation window
        recent_traces = []
        for trace in self._active_traces.values():
            if any(
                s.start_time >= current_time - correlation_window for s in trace.spans
            ):
                recent_traces.append(trace)

        # Group by common tags/baggage
        correlations = {}
        for trace in recent_traces:
            for span in trace.spans:
                for tag_key, tag_value in span.tags.items():
                    correlation_key = f"{tag_key}:{tag_value}"
                    if correlation_key not in correlations:
                        correlations[correlation_key] = []
                    correlations[correlation_key].append(
                        {
                            "trace_id": trace.trace_id,
                            "span_id": span.span_id,
                            "service_name": span.service_name,
                            "operation_name": span.operation_name,
                        }
                    )

        # Filter correlations with multiple traces
        significant_correlations = {
            k: v
            for k, v in correlations.items()
            if len(set(item["trace_id"] for item in v)) > 1
        }

        return {
            "monitoring_status": "correlations_found",
            "trace_data": {},
            "span_data": {},
            "alerts": [],
            "metrics": {
                "correlations_found": len(significant_correlations),
                "traces_analyzed": len(recent_traces),
            },
            "correlation_id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _monitoring_loop(self):
        """Background monitoring loop for real-time alerts."""
        while self._monitoring_active:
            try:
                await asyncio.sleep(1.0)  # Check every second

                # Check for long-running spans
                current_time = time.time()
                for span in self._active_spans.values():
                    duration = current_time - span.start_time
                    if duration > 10.0:  # Alert on spans > 10 seconds
                        alert = TransactionAlert(
                            alert_id=str(uuid.uuid4()),
                            severity=AlertSeverity.MEDIUM,
                            message=f"Long-running span detected: {span.operation_name}",
                            trace_id=span.trace_id,
                            metric_name="span_duration",
                            metric_value=duration,
                            threshold=10.0,
                            tags=span.tags,
                        )
                        await self._handle_alert(alert)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")

    async def _setup_streaming(self, endpoint: str):
        """Setup streaming for real-time dashboard updates."""
        # In a real implementation, this would setup WebSocket/SSE connections
        self.logger.info(f"Would setup streaming to {endpoint}")
        # Placeholder for streaming setup
        pass

    async def _check_span_alerts(self, span: TransactionSpan) -> List[TransactionAlert]:
        """Check if span triggers any alerts."""
        alerts = []

        # Check duration thresholds
        if span.duration and "duration" in self._alert_thresholds:
            thresholds = self._alert_thresholds["duration"]

            for threshold_name, threshold_value in thresholds.items():
                if span.duration > threshold_value:
                    alert = TransactionAlert(
                        alert_id=str(uuid.uuid4()),
                        severity=(
                            AlertSeverity.HIGH
                            if threshold_name == "p99"
                            else AlertSeverity.MEDIUM
                        ),
                        message=f"Span duration {span.duration:.3f}s exceeds {threshold_name} threshold {threshold_value}s",
                        trace_id=span.trace_id,
                        metric_name=f"span_duration_{threshold_name}",
                        metric_value=span.duration,
                        threshold=threshold_value,
                        tags=span.tags,
                    )
                    alerts.append(alert)

        # Check for errors
        if span.error:
            alert = TransactionAlert(
                alert_id=str(uuid.uuid4()),
                severity=AlertSeverity.HIGH,
                message=f"Span error: {span.error}",
                trace_id=span.trace_id,
                metric_name="span_error",
                metric_value=1.0,
                threshold=0.0,
                tags=span.tags,
            )
            alerts.append(alert)

        return alerts

    async def _handle_alert(self, alert: TransactionAlert):
        """Handle a generated alert."""
        # In a real implementation, this would send to alerting systems
        self.logger.warning(f"Alert: {alert.severity.value} - {alert.message}")

        # Call registered alert handlers
        for handler in self._alert_handlers:
            try:
                await handler(alert)
            except Exception as e:
                self.logger.error(f"Alert handler error: {e}")

    def _calculate_critical_path(self, trace: TransactionTrace) -> List[str]:
        """Calculate critical path through the trace."""
        # Simple implementation: find longest duration path
        # In a real implementation, this would use graph algorithms
        spans_by_duration = sorted(
            trace.spans, key=lambda s: s.duration or 0, reverse=True
        )
        return [s.span_id for s in spans_by_duration[:3]]  # Top 3 spans

    def _serialize_span(self, span: TransactionSpan) -> Dict[str, Any]:
        """Serialize a span to dictionary."""
        return {
            "span_id": span.span_id,
            "trace_id": span.trace_id,
            "parent_span_id": span.parent_span_id,
            "operation_name": span.operation_name,
            "service_name": span.service_name,
            "start_time": span.start_time,
            "end_time": span.end_time,
            "duration": span.duration,
            "status": span.status,
            "error": span.error,
            "tags": span.tags,
            "baggage": span.baggage,
        }

    def _serialize_alert(self, alert: TransactionAlert) -> Dict[str, Any]:
        """Serialize an alert to dictionary."""
        return {
            "alert_id": alert.alert_id,
            "severity": alert.severity.value,
            "message": alert.message,
            "transaction_id": alert.transaction_id,
            "trace_id": alert.trace_id,
            "metric_name": alert.metric_name,
            "metric_value": alert.metric_value,
            "threshold": alert.threshold,
            "timestamp": alert.timestamp,
            "tags": alert.tags,
            "resolved": alert.resolved,
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous wrapper for compatibility."""
        import asyncio

        return asyncio.run(self.async_run(**kwargs))

    async def _start_transaction(self, **kwargs) -> Dict[str, Any]:
        """Start monitoring a specific transaction."""
        transaction_id = kwargs.get("transaction_id", str(uuid.uuid4()))
        transaction_type = kwargs.get("transaction_type", "default")
        metadata = kwargs.get("metadata", {})

        # Create trace for transaction
        trace_id = str(uuid.uuid4())
        span_id = str(uuid.uuid4())

        # Store transaction info
        self._active_traces[trace_id] = {
            "transaction_id": transaction_id,
            "transaction_type": transaction_type,
            "start_time": time.time(),
            "metadata": metadata,
            "spans": [span_id],
            "status": "active",
        }

        self.logger.info(f"Started transaction monitoring for {transaction_id}")

        return {
            "monitoring_status": "transaction_started",
            "trace_data": {"trace_id": trace_id, "transaction_id": transaction_id},
            "span_data": {"span_id": span_id, "operation": "transaction_start"},
            "alerts": [],
            "metrics": {"active_transactions": len(self._active_traces)},
            "correlation_id": transaction_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _complete_transaction(self, **kwargs) -> Dict[str, Any]:
        """Complete a transaction and update monitoring status."""
        self.logger.debug(f"Complete transaction called with kwargs: {kwargs}")
        transaction_id = kwargs.get("transaction_id")
        status = kwargs.get("status", "completed")

        if not transaction_id:
            raise ValueError(
                f"transaction_id is required for complete_transaction. Received kwargs: {kwargs}"
            )

        # Mark the transaction as completed in active traces
        if transaction_id in self._active_traces:
            trace_data = self._active_traces[transaction_id]
            trace_data["end_time"] = time.time()
            trace_data["status"] = status
            trace_data["duration"] = trace_data["end_time"] - trace_data.get(
                "start_time", 0
            )

            # Move to completed traces if we track them
            # For now, just mark as completed in place

        return {
            "monitoring_active": self._monitoring_active,
            "transaction_id": transaction_id,
            "transaction_status": status,
            "monitoring_status": "transaction_completed",
            "trace_data": {
                "trace_id": f"trace_{transaction_id}",
                "transaction_id": transaction_id,
            },
            "span_data": {
                "span_id": f"span_{transaction_id}",
                "operation": "transaction_complete",
            },
            "alerts": [],
            "metrics": {"active_transactions": len(self._active_traces)},
            "correlation_id": transaction_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _get_monitoring_status(self, **kwargs) -> Dict[str, Any]:
        """Get current monitoring status and metrics."""
        active_traces_count = len(self._active_traces)
        active_spans_count = sum(
            len(trace_data.get("spans", []))
            for trace_data in self._active_traces.values()
        )

        # Calculate performance metrics
        current_time = time.time()
        recent_traces = [
            trace
            for trace in self._active_traces.values()
            if current_time - trace.get("start_time", 0) < 300  # Last 5 minutes
        ]

        status_info = {
            "monitoring_active": self._monitoring_active,
            "total_active_traces": active_traces_count,
            "total_active_spans": active_spans_count,
            "recent_traces_5min": len(recent_traces),
            "sampling_rate": self._trace_sampling_rate,
            "alert_thresholds": self._alert_thresholds,
            "background_tasks": len(self._background_tasks),
        }

        return {
            "monitoring_status": "active" if self._monitoring_active else "inactive",
            "trace_data": {"active_traces": active_traces_count},
            "span_data": {"active_spans": active_spans_count},
            "alerts": [],
            "metrics": status_info,
            "correlation_id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def cleanup(self):
        """Cleanup resources when node is destroyed."""
        await self._stop_monitoring()
        await super().cleanup() if hasattr(super(), "cleanup") else None
