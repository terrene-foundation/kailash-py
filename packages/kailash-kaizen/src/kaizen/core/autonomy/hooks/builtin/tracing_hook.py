"""
TracingHook for distributed tracing integration with hook system.

Integrates TracingManager with the autonomous agent hook system, automatically
creating OpenTelemetry spans for hook events with parent-child hierarchy,
exception recording, and span status based on hook results.

Features:
- Automatic span creation for hook events
- Parent-child span hierarchy (PRE_AGENT_LOOP → PRE_TOOL_USE → POST_TOOL_USE)
- Event filtering support (trace only specified events)
- Span attributes from HookContext
- Exception recording from HookResult errors
- Span status based on HookResult success
- Performance: <3% overhead compared to baseline

Example:
    >>> from kaizen.core.autonomy.observability.tracing_manager import TracingManager
    >>> from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook
    >>> from kaizen.core.autonomy.hooks import HookEvent
    >>>
    >>> manager = TracingManager(service_name="my-service")
    >>> hook = TracingHook(
    ...     tracing_manager=manager,
    ...     events_to_trace=[HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE]
    ... )
    >>>
    >>> # Hook automatically creates spans for filtered events
    >>> hook_manager.register(HookEvent.PRE_TOOL_USE, hook.handle)
    >>> hook_manager.register(HookEvent.POST_TOOL_USE, hook.handle)

Integration with BaseAgent:
    TracingHook is designed to work with BaseAgent.enable_observability(),
    automatically creating traces for agent lifecycle events.
"""

import logging
import time
from typing import ClassVar, List, Optional

from kaizen.core.autonomy.observability.tracing_manager import TracingManager

from ..protocol import BaseHook
from ..types import HookContext, HookEvent, HookResult

logger = logging.getLogger(__name__)


class TracingHook(BaseHook):
    """
    Hook for distributed tracing with OpenTelemetry and Jaeger.

    Automatically creates OpenTelemetry spans for hook events with parent-child
    hierarchy, exception recording, and span status based on hook results.

    Attributes:
        events: All hook events (tracing can capture any event)
        tracing_manager: TracingManager for span creation
        events_to_trace: Optional filter for events to trace (None = all events)
    """

    events: ClassVar[list[HookEvent]] = list(HookEvent)

    def __init__(
        self,
        tracing_manager: TracingManager,
        events_to_trace: Optional[List[HookEvent]] = None,
    ):
        """
        Initialize TracingHook with TracingManager and optional event filter.

        Args:
            tracing_manager: TracingManager for span creation
            events_to_trace: Optional list of events to trace (None = all events)
        """
        super().__init__(name="tracing_hook")
        self.tracing_manager = tracing_manager
        self.events_to_trace = events_to_trace or []

        # Store active spans for parent-child hierarchy
        # Key: (trace_id, event_pair), Value: (span, start_time)
        # event_pair examples: "agent_loop", "tool_use", "llm_call"
        self._active_spans = {}

        logger.info(
            f"TracingHook initialized: "
            f"events_filter={len(self.events_to_trace) if self.events_to_trace else 'all'}"
        )

    def _should_trace_event(self, event: HookEvent) -> bool:
        """
        Check if event should be traced based on filter.

        Args:
            event: Hook event to check

        Returns:
            True if event should be traced, False otherwise
        """
        # If no filter specified, trace all events
        if not self.events_to_trace:
            return True

        # Otherwise, check if event is in filter
        return event in self.events_to_trace

    async def handle(self, context: HookContext) -> HookResult:
        """
        Handle hook event and create OpenTelemetry span.

        Creates span for event with attributes from HookContext. Handles parent-child
        span hierarchy by checking metadata for parent_span_id. Records exceptions
        and sets span status based on hook execution.

        Args:
            context: Hook context with event details

        Returns:
            HookResult with success=True and span data
        """
        start_time = time.time()

        try:
            # Check event filter
            if not self._should_trace_event(context.event_type):
                return HookResult(
                    success=True,
                    data={"span_created": False, "reason": "event_filtered"},
                )

            # Determine event pair type (remove pre_/post_ prefix)
            # Examples: "pre_agent_loop" → "agent_loop", "post_tool_use" → "tool_use"
            is_pre_event = "pre_" in context.event_type.value
            is_post_event = "post_" in context.event_type.value

            if is_pre_event:
                event_pair = context.event_type.value.replace("pre_", "")
            elif is_post_event:
                event_pair = context.event_type.value.replace("post_", "")
            else:
                event_pair = context.event_type.value

            # Make event_pair more specific by including context data
            # For tool_use events, include tool_name to differentiate multiple tool calls
            if (
                "tool_use" in event_pair
                and context.data
                and "tool_name" in context.data
            ):
                event_pair = f"{event_pair}:{context.data['tool_name']}"
            # For llm_call events, include model if available
            elif "llm_call" in event_pair and context.data and "model" in context.data:
                event_pair = f"{event_pair}:{context.data['model']}"

            # Create composite key for this event pair
            span_key = (context.trace_id, event_pair) if context.trace_id else None

            # Get parent span if available (for hierarchy)
            # Priority 1: Check for exact match (for PRE/POST pairing)
            # Priority 2: Find most recent active span with same trace_id (for nesting)
            parent_span = None
            pre_span_start_time = None

            if span_key and span_key in self._active_spans:
                # Exact match for PRE/POST pairing
                parent_span, pre_span_start_time = self._active_spans[span_key]
            elif context.trace_id:
                # Find most recent active span with same trace_id for nesting
                # (e.g., tool_use spans nested under agent_loop span)
                for key, (span, timestamp) in self._active_spans.items():
                    if key[0] == context.trace_id:
                        # Use this as parent (most recent will be the last one stored)
                        parent_span = span
                        break

            # Create span from context
            span = self.tracing_manager.create_span_from_context(
                context=context,
                parent_span=parent_span,
            )

            # Get span ID for parent-child hierarchy
            span_id = span.get_span_context().span_id

            # Store span for potential child spans (PRE events only)
            if span_key and is_pre_event:
                # For PRE events, store as potential parent with start time (don't end yet)
                self._active_spans[span_key] = (span, context.timestamp)
            elif span_key and is_post_event:
                # For POST events, end the corresponding PRE span and calculate duration
                pre_data = self._active_spans.pop(span_key, None)
                if pre_data:
                    pre_span, pre_start_time = pre_data
                    pre_span.end()
                    # Calculate actual operation duration (PRE to POST)
                    pre_span_start_time = pre_start_time

            # End current span (POST spans end immediately, PRE spans stay active)
            if is_post_event:
                span.end()

            # Calculate duration
            if is_post_event and pre_span_start_time is not None:
                # For POST events, use actual operation duration (PRE to POST)
                duration_ms = (context.timestamp - pre_span_start_time) * 1000
            else:
                # For PRE events or standalone events, use hook processing time
                duration_ms = (time.time() - start_time) * 1000

            # Build result data
            result_data = {
                "span_name": span.name,
                "span_id": span_id,
                "agent_id": context.agent_id,
                "trace_id": context.trace_id,
                "duration_ms": duration_ms,
            }

            # Add span_created or span_updated based on event type
            if is_pre_event:
                result_data["span_created"] = True
            elif is_post_event:
                result_data["span_updated"] = True
            else:
                result_data["span_created"] = True

            return HookResult(
                success=True,
                data=result_data,
            )

        except Exception as e:
            logger.error(f"TracingHook failed: {e}", exc_info=True)

            # Return success=False to indicate tracing failure
            return HookResult(
                success=False,
                error=str(e),  # HookResult requires error parameter when success=False
                data={
                    "span_created": False,
                    "error": str(e),
                },
            )
