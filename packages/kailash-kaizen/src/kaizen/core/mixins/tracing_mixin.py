"""
Tracing Mixin for BaseAgent.

Provides distributed tracing integration for agent operations including:
- Span creation for agent executions
- Trace context propagation
- Integration with existing TracingManager
- Support for nested agent calls
"""

import functools
import inspect
import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Generator, Optional

if TYPE_CHECKING:
    from kaizen.core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class Span:
    """A tracing span representing an operation."""

    name: str
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: str = "in_progress"
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: list = field(default_factory=list)

    def end(self, status: str = "success") -> None:
        """End the span with given status."""
        self.end_time = time.time()
        self.status = status

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """Add an event to the span."""
        self.events.append(
            {"name": name, "timestamp": time.time(), "attributes": attributes or {}}
        )

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a span attribute."""
        self.attributes[key] = value

    @property
    def duration_ms(self) -> Optional[float]:
        """Get span duration in milliseconds."""
        if self.end_time is not None:
            return (self.end_time - self.start_time) * 1000
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert span to dictionary."""
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "attributes": self.attributes,
            "events": self.events,
        }


class AgentTracer:
    """Simple tracer for agent operations."""

    def __init__(self, agent_name: str):
        """
        Initialize tracer.

        Args:
            agent_name: Name of the agent being traced
        """
        self.agent_name = agent_name
        self._current_trace_id: Optional[str] = None
        self._current_span_id: Optional[str] = None
        self._spans: list[Span] = []

    def _generate_id(self) -> str:
        """Generate a random ID."""
        return uuid.uuid4().hex[:16]

    @contextmanager
    def start_span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        parent_span_id: Optional[str] = None,
    ) -> Generator[Span, None, None]:
        """
        Start a new span.

        Args:
            name: Span name
            attributes: Initial attributes
            parent_span_id: Parent span ID (for nested spans)

        Yields:
            The created span
        """
        # Create or use existing trace
        if self._current_trace_id is None:
            self._current_trace_id = self._generate_id()

        span = Span(
            name=name,
            trace_id=self._current_trace_id,
            span_id=self._generate_id(),
            parent_span_id=parent_span_id or self._current_span_id,
            attributes=attributes or {},
        )

        # Set as current span
        old_span_id = self._current_span_id
        self._current_span_id = span.span_id

        try:
            yield span
            span.end("success")
        except Exception as e:
            span.add_event("error", {"error": str(e), "type": type(e).__name__})
            span.end("error")
            raise
        finally:
            self._spans.append(span)
            self._current_span_id = old_span_id

    def get_spans(self) -> list[Span]:
        """Get all recorded spans."""
        return list(self._spans)

    def clear(self) -> None:
        """Clear recorded spans."""
        self._spans.clear()
        self._current_trace_id = None
        self._current_span_id = None


class TracingMixin:
    """
    Mixin that adds distributed tracing to agents.

    Creates spans for agent executions with:
    - Automatic span creation/completion
    - Error recording with stack traces
    - Attribute propagation
    - Support for nested agent calls

    Example:
        config = BaseAgentConfig(tracing_enabled=True)
        agent = SimpleQAAgent(config)
        await agent.run(question="test")
        spans = agent._tracer.get_spans()
    """

    @classmethod
    def apply(cls, agent: "BaseAgent") -> None:
        """
        Apply tracing behavior to agent.

        Creates an AgentTracer instance and wraps the run method
        with span creation.

        Args:
            agent: The agent instance to apply tracing to
        """
        agent_name = agent.__class__.__name__
        agent._tracer = AgentTracer(agent_name)

        # Store original run method
        original_run = agent.run
        is_async = inspect.iscoroutinefunction(original_run)

        if is_async:

            @functools.wraps(original_run)
            async def traced_run_async(*args: Any, **kwargs: Any) -> Dict[str, Any]:
                """Wrapped async run method with tracing."""
                with agent._tracer.start_span(
                    f"{agent_name}.run",
                    attributes={
                        "agent.name": agent_name,
                        "agent.input_keys": list(kwargs.keys()) if kwargs else [],
                    },
                ) as span:
                    result = await original_run(*args, **kwargs)

                    # Record output keys
                    if isinstance(result, dict):
                        span.set_attribute("agent.output_keys", list(result.keys()))

                    return result

            agent.run = traced_run_async
        else:

            @functools.wraps(original_run)
            def traced_run_sync(*args: Any, **kwargs: Any) -> Dict[str, Any]:
                """Wrapped sync run method with tracing."""
                with agent._tracer.start_span(
                    f"{agent_name}.run",
                    attributes={
                        "agent.name": agent_name,
                        "agent.input_keys": list(kwargs.keys()) if kwargs else [],
                    },
                ) as span:
                    result = original_run(*args, **kwargs)

                    # Record output keys
                    if isinstance(result, dict):
                        span.set_attribute("agent.output_keys", list(result.keys()))

                    return result

            agent.run = traced_run_sync

    @classmethod
    def get_tracer(cls, agent: "BaseAgent") -> Optional[AgentTracer]:
        """
        Get the agent's tracer.

        Args:
            agent: The agent instance

        Returns:
            The agent's tracer or None
        """
        return getattr(agent, "_tracer", None)
