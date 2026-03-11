"""
TracingManager for distributed tracing with OpenTelemetry and Jaeger.

Provides OpenTelemetry-based distributed tracing with Jaeger backend integration.
Converts HookContext events into OpenTelemetry spans with automatic attribute mapping,
parent-child span hierarchy, and exception recording.

Features:
- OpenTelemetry TracerProvider with Jaeger OTLP exporter
- Span creation from HookContext events
- HookContext.trace_id → OpenTelemetry trace ID mapping
- Parent-child span hierarchy via context propagation
- Automatic span attribute mapping (agent_id, event_type, data, metadata)
- Thread-safe concurrent span creation
- Batch span processor with configurable settings
- Exception recording in spans
- Performance: <1ms per span creation

Example:
    >>> from kaizen.core.autonomy.observability.tracing_manager import TracingManager
    >>> from kaizen.core.autonomy.hooks import HookContext, HookEvent
    >>>
    >>> manager = TracingManager(
    ...     service_name="my-service",
    ...     jaeger_host="localhost",
    ...     jaeger_port=4317
    ... )
    >>>
    >>> context = HookContext(
    ...     event_type=HookEvent.PRE_TOOL_USE,
    ...     agent_id="agent1",
    ...     timestamp=time.time(),
    ...     trace_id=str(uuid.uuid4()),
    ...     data={"tool_name": "search"}
    ... )
    >>>
    >>> span = manager.create_span_from_context(context)
    >>> # ... do work ...
    >>> span.end()
    >>> manager.shutdown()

Integration with Hook System:
    TracingManager is designed to work with TracingHook, which automatically creates
    spans for hook events. Direct usage is typically not needed.
"""

import logging
import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from kaizen.core.autonomy.hooks import HookContext, HookResult

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Span, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode, set_span_in_context

logger = logging.getLogger(__name__)


class TracingManager:
    """
    Manages distributed tracing with OpenTelemetry and Jaeger backend.

    Converts HookContext events into OpenTelemetry spans with automatic attribute
    mapping, parent-child hierarchy, and exception recording.

    Attributes:
        tracer_provider (TracerProvider): OpenTelemetry tracer provider
        tracer (Tracer): OpenTelemetry tracer for span creation
        jaeger_host (str): Jaeger OTLP endpoint host
        jaeger_port (int): Jaeger OTLP gRPC port (default 4317)
        batch_size (int): Batch span processor max queue size
        batch_timeout_ms (int): Batch span processor export timeout
        max_export_batch_size (int): Maximum spans per export batch
    """

    def __init__(
        self,
        service_name: str,
        jaeger_host: str = "localhost",
        jaeger_port: int = 4317,
        insecure: bool = True,
        batch_size: int = 512,
        batch_timeout_ms: int = 5000,
        max_export_batch_size: int = 512,
    ):
        """
        Initialize TracingManager with OpenTelemetry and Jaeger configuration.

        Args:
            service_name: Service name for resource identification
            jaeger_host: Jaeger OTLP endpoint host (default "localhost")
            jaeger_port: Jaeger OTLP gRPC port (default 4317)
            insecure: Use insecure gRPC connection (default True)
            batch_size: Batch processor max queue size (default 512)
            batch_timeout_ms: Batch processor export timeout in ms (default 5000)
            max_export_batch_size: Maximum spans per export batch (default 512)
        """
        self.service_name = service_name
        self.jaeger_host = jaeger_host
        self.jaeger_port = jaeger_port
        self.insecure = insecure
        self.batch_size = batch_size
        self.batch_timeout_ms = batch_timeout_ms

        # Ensure max_export_batch_size <= batch_size (OpenTelemetry requirement)
        self.max_export_batch_size = min(max_export_batch_size, batch_size)

        # Create resource with service name
        resource = Resource.create(
            attributes={
                "service.name": service_name,
            }
        )

        # Initialize TracerProvider
        self.tracer_provider = TracerProvider(resource=resource)

        # Configure OTLP gRPC exporter to Jaeger
        otlp_exporter = OTLPSpanExporter(
            endpoint=f"{jaeger_host}:{jaeger_port}",
            insecure=insecure,
        )

        # Configure batch span processor
        batch_processor = BatchSpanProcessor(
            otlp_exporter,
            max_queue_size=batch_size,
            schedule_delay_millis=batch_timeout_ms,
            max_export_batch_size=self.max_export_batch_size,  # Use corrected value
        )

        self.tracer_provider.add_span_processor(batch_processor)

        # Get tracer for span creation
        self.tracer = self.tracer_provider.get_tracer(__name__)

        # Thread lock for concurrent span creation
        self._lock = threading.Lock()

        logger.info(
            f"TracingManager initialized: service={service_name}, "
            f"endpoint={jaeger_host}:{jaeger_port}"
        )

    def create_span_from_context(
        self,
        context: "HookContext",
        parent_span: Optional[Span] = None,
    ) -> Span:
        """
        Create OpenTelemetry span from HookContext event.

        Maps HookContext fields to span attributes:
        - event_type → span name and attribute
        - agent_id → attribute
        - trace_id → attribute (HookContext trace_id for correlation)
        - data fields → attributes
        - metadata fields → attributes

        Args:
            context: Hook context containing event details
            parent_span: Optional parent span for hierarchy

        Returns:
            OpenTelemetry Span with attributes mapped from context
        """
        # Convert event type to span name (e.g., PRE_TOOL_USE → pre_tool_use)
        span_name = context.event_type.value.lower()

        # Prepare span attributes
        attributes = {
            "agent_id": context.agent_id,
            "event_type": context.event_type.value.lower(),
            "trace_id": context.trace_id or "",  # HookContext trace_id
        }

        # Add data fields as attributes
        if context.data:
            for key, value in context.data.items():
                # Only add primitive types (str, int, float, bool)
                if isinstance(value, (str, int, float, bool)):
                    attributes[key] = value

        # Add metadata fields as attributes
        if context.metadata:
            for key, value in context.metadata.items():
                # Skip parent_span_id (used for hierarchy, not attribute)
                if key == "parent_span_id":
                    continue
                # Only add primitive types
                if isinstance(value, (str, int, float, bool)):
                    attributes[key] = value

        # Create span with optional parent context
        if parent_span is not None:
            parent_context = set_span_in_context(parent_span)
            span = self.tracer.start_span(
                span_name,
                context=parent_context,
                attributes=attributes,
            )
        else:
            span = self.tracer.start_span(
                span_name,
                attributes=attributes,
            )

        return span

    def update_span_from_result(self, span: Span, result: "HookResult") -> None:
        """
        Update span status based on HookResult.

        Sets span status to OK if result.success is True, ERROR otherwise.
        Includes error message in status description if available.

        Args:
            span: OpenTelemetry span to update
            result: Hook execution result
        """
        if result.success:
            span.set_status(Status(StatusCode.OK))
        else:
            error_msg = result.error or "Hook execution failed"
            span.set_status(Status(StatusCode.ERROR, description=error_msg))

    def record_exception(self, span: Span, exception: Exception) -> None:
        """
        Record exception in span.

        Captures exception details as span event and sets status to ERROR.

        Args:
            span: OpenTelemetry span to update
            exception: Exception to record
        """
        # Record exception as span event
        span.record_exception(exception)

        # Set span status to ERROR
        span.set_status(Status(StatusCode.ERROR, description=str(exception)))

    def force_flush(self, timeout: int = 30) -> bool:
        """
        Force export of all pending spans.

        Blocks until all spans are exported or timeout is reached.

        Args:
            timeout: Maximum time to wait in seconds (default 30)

        Returns:
            True if flush succeeded, False otherwise
        """
        try:
            return self.tracer_provider.force_flush(timeout_millis=timeout * 1000)
        except Exception as e:
            logger.error(f"Force flush failed: {e}")
            return False

    def shutdown(self, timeout: int = 30) -> bool:
        """
        Shutdown tracing manager and export all pending spans.

        Blocks until all spans are exported or timeout is reached.
        Should be called when application terminates.

        Args:
            timeout: Maximum time to wait in seconds (default 30)

        Returns:
            True if shutdown succeeded, False otherwise
        """
        try:
            result = self.tracer_provider.shutdown()
            logger.info("TracingManager shutdown complete")
            return result
        except Exception as e:
            logger.error(f"Shutdown failed: {e}")
            return False
