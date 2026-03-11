"""StreamingExecutor for event-based agent execution.

Provides the core execution bridge between Kaizen agents and Enterprise-App,
wrapping agent execution with typed event emission for progress tracking,
cost attribution, and UI integration.

See: TODO-204 Enterprise-App Streaming Integration
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

from .events import (
    CompletedEvent,
    CostUpdateEvent,
    ErrorEvent,
    EventType,
    ExecutionEvent,
    MessageEvent,
    ProgressEvent,
    StartedEvent,
    SubagentSpawnEvent,
    ThinkingEvent,
    ToolResultEvent,
    ToolUseEvent,
)


@dataclass
class ExecutionMetrics:
    """Metrics tracked during execution."""

    execution_id: str
    session_id: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    cycles_used: int = 0
    tools_used: int = 0
    subagents_spawned: int = 0
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    subagent_calls: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        """Calculate execution duration in milliseconds."""
        if self.end_time is None:
            return int((time.time() - self.start_time) * 1000)
        return int((self.end_time - self.start_time) * 1000)

    @property
    def total_cost_cents(self) -> int:
        """Convert USD to cents for API compatibility."""
        return int(self.total_cost_usd * 100)


class StreamingExecutor:
    """
    Event-based execution wrapper for Kaizen agents.

    Wraps agent execution with typed event emission for:
    - Progress visualization (TaskGraph in Enterprise-App)
    - Cost attribution and tracking
    - Tool invocation monitoring
    - Subagent spawning events
    - Session state management

    All 10 Enterprise-App event types are emitted at appropriate lifecycle points:
    - started: When execution begins
    - thinking: During agent reasoning
    - message: When agent produces response
    - tool_use: Before tool execution
    - tool_result: After tool execution
    - subagent_spawn: When Task tool spawns subagent
    - cost_update: After each LLM call
    - progress: During execution steps
    - completed: When execution ends successfully
    - error: On execution failure

    Example:
        >>> from kaizen.execution import StreamingExecutor
        >>> from kaizen.core import BaseAgent
        >>>
        >>> executor = StreamingExecutor()
        >>> agent = MyAgent(config)
        >>>
        >>> async for event in executor.execute_with_events(
        ...     agent=agent,
        ...     task="Analyze the codebase",
        ...     trust_chain_id="chain-123",
        ... ):
        ...     print(f"{event.event_type.value}: {event.to_dict()}")
    """

    def __init__(
        self,
        on_event: Optional[Callable[[ExecutionEvent], None]] = None,
        cost_per_1k_input_tokens: float = 0.01,
        cost_per_1k_output_tokens: float = 0.03,
    ):
        """
        Initialize StreamingExecutor.

        Args:
            on_event: Optional callback for each event (in addition to yield)
            cost_per_1k_input_tokens: Cost per 1000 input tokens (default: $0.01)
            cost_per_1k_output_tokens: Cost per 1000 output tokens (default: $0.03)
        """
        self._on_event = on_event
        self._cost_per_1k_input = cost_per_1k_input_tokens
        self._cost_per_1k_output = cost_per_1k_output_tokens

    async def execute_with_events(
        self,
        agent: Any,
        task: str,
        *,
        trust_chain_id: Optional[str] = None,
        session_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[ExecutionEvent]:
        """
        Execute agent task yielding typed events.

        This is the primary interface for Enterprise-App integration.

        Args:
            agent: The Kaizen agent to execute
            task: Task description/prompt for the agent
            trust_chain_id: Optional trust chain for delegation tracking
            session_id: Optional session ID for state correlation
            execution_id: Optional execution ID (auto-generated if None)
            metadata: Optional metadata to include in events

        Yields:
            ExecutionEvent: Typed events during execution

        Example:
            >>> async for event in executor.execute_with_events(agent, "Analyze code"):
            ...     if event.event_type == EventType.COMPLETED:
            ...         print(f"Done! Tokens: {event.total_tokens}")
        """
        # Generate IDs if not provided
        execution_id = execution_id or f"exec-{uuid.uuid4().hex[:12]}"
        session_id = session_id or f"session-{uuid.uuid4().hex[:12]}"
        trust_chain_id = trust_chain_id or ""

        # Extract agent info
        agent_id = getattr(agent, "agent_id", None) or f"agent-{uuid.uuid4().hex[:8]}"
        agent_name = getattr(agent, "name", None) or agent.__class__.__name__

        # Initialize metrics
        metrics = ExecutionMetrics(
            execution_id=execution_id,
            session_id=session_id,
        )

        try:
            # === STARTED Event ===
            started_event = StartedEvent(
                session_id=session_id,
                execution_id=execution_id,
                agent_id=agent_id,
                agent_name=agent_name,
                trust_chain_id=trust_chain_id,
                metadata=metadata or {},
            )
            yield self._emit(started_event)

            # === PROGRESS Event (0%) ===
            yield self._emit(
                ProgressEvent(
                    session_id=session_id,
                    execution_id=execution_id,
                    percentage=0,
                    step="Starting execution",
                    details=f"Executing task: {task[:100]}...",
                )
            )

            # === THINKING Event ===
            yield self._emit(
                ThinkingEvent(
                    session_id=session_id,
                    execution_id=execution_id,
                    content=f"Processing task: {task}",
                )
            )

            # === Execute Agent ===
            yield self._emit(
                ProgressEvent(
                    session_id=session_id,
                    execution_id=execution_id,
                    percentage=25,
                    step="Executing agent",
                    details="Agent is processing the task",
                )
            )

            # Check if agent has async method
            if hasattr(agent, "run_async") and asyncio.iscoroutinefunction(
                agent.run_async
            ):
                result = await self._execute_async_agent(
                    agent, task, session_id, execution_id, metrics
                )
            elif hasattr(agent, "run"):
                result = await self._execute_sync_agent(
                    agent, task, session_id, execution_id, metrics
                )
            else:
                raise AttributeError(
                    f"Agent {agent_name} has no run or run_async method"
                )

            # Emit events from execution result
            async for event in self._process_result(
                result, session_id, execution_id, agent_id, metrics
            ):
                yield event

            # === PROGRESS Event (90%) ===
            yield self._emit(
                ProgressEvent(
                    session_id=session_id,
                    execution_id=execution_id,
                    percentage=90,
                    step="Finalizing",
                    details="Processing complete, generating response",
                )
            )

            # === MESSAGE Event ===
            output_text = self._extract_output(result)
            yield self._emit(
                MessageEvent(
                    session_id=session_id,
                    execution_id=execution_id,
                    role="assistant",
                    content=output_text,
                )
            )
            metrics.messages.append({"role": "assistant", "content": output_text})

            # === COST_UPDATE Event (final) ===
            yield self._emit(
                CostUpdateEvent(
                    session_id=session_id,
                    agent_id=agent_id,
                    tokens_added=0,
                    cost_added_usd=0.0,
                    total_tokens=metrics.total_tokens,
                    total_cost_usd=metrics.total_cost_usd,
                )
            )

            # === COMPLETED Event ===
            metrics.end_time = time.time()
            yield self._emit(
                CompletedEvent(
                    session_id=session_id,
                    execution_id=execution_id,
                    total_tokens=metrics.total_tokens,
                    total_cost_cents=metrics.total_cost_cents,
                    total_cost_usd=metrics.total_cost_usd,
                    duration_ms=metrics.duration_ms,
                    cycles_used=metrics.cycles_used,
                    tools_used=metrics.tools_used,
                    subagents_spawned=metrics.subagents_spawned,
                )
            )

        except Exception as e:
            # === ERROR Event ===
            metrics.end_time = time.time()
            error_event = ErrorEvent(
                session_id=session_id,
                execution_id=execution_id,
                message=str(e),
                error_type=type(e).__name__,
                recoverable=self._is_recoverable(e),
            )
            yield self._emit(error_event)
            raise

    async def _execute_async_agent(
        self,
        agent: Any,
        task: str,
        session_id: str,
        execution_id: str,
        metrics: ExecutionMetrics,
    ) -> Dict[str, Any]:
        """Execute async agent and track metrics."""
        # Build inputs
        inputs = self._build_inputs(agent, task)

        # Execute
        result = await agent.run_async(**inputs)

        # Update metrics from result
        self._update_metrics_from_result(result, metrics)

        return result

    async def _execute_sync_agent(
        self,
        agent: Any,
        task: str,
        session_id: str,
        execution_id: str,
        metrics: ExecutionMetrics,
    ) -> Dict[str, Any]:
        """Execute sync agent in thread pool and track metrics."""
        # Build inputs
        inputs = self._build_inputs(agent, task)

        # Execute in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: agent.run(**inputs))

        # Update metrics from result
        self._update_metrics_from_result(result, metrics)

        return result

    def _build_inputs(self, agent: Any, task: str) -> Dict[str, Any]:
        """Build input dictionary for agent execution."""
        # Check agent signature for expected input field names
        signature = getattr(agent, "_signature", None) or getattr(
            agent, "signature", None
        )

        if signature:
            # Find the first InputField
            input_fields = []
            for name, field_value in signature.__class__.__dict__.items():
                if (
                    hasattr(field_value, "__class__")
                    and field_value.__class__.__name__ == "InputField"
                ):
                    input_fields.append(name)

            if input_fields:
                # Use first input field name
                return {input_fields[0]: task}

        # Default: use common input field names
        return {"question": task, "task": task, "prompt": task, "input": task}

    def _update_metrics_from_result(
        self, result: Dict[str, Any], metrics: ExecutionMetrics
    ) -> None:
        """Update metrics from agent result."""
        # Extract token usage if available
        if "tokens_used" in result:
            metrics.total_tokens = result["tokens_used"]
        elif "_metadata" in result and "tokens" in result["_metadata"]:
            metrics.total_tokens = result["_metadata"]["tokens"]

        # Extract cost if available
        if "cost_usd" in result:
            metrics.total_cost_usd = result["cost_usd"]
        elif "_metadata" in result and "cost" in result["_metadata"]:
            metrics.total_cost_usd = result["_metadata"]["cost"]

        # Calculate cost from tokens if not provided
        if metrics.total_cost_usd == 0.0 and metrics.total_tokens > 0:
            # Rough estimate assuming 50% input, 50% output
            input_tokens = metrics.total_tokens // 2
            output_tokens = metrics.total_tokens - input_tokens
            metrics.total_cost_usd = (input_tokens / 1000) * self._cost_per_1k_input + (
                output_tokens / 1000
            ) * self._cost_per_1k_output

        # Extract tool calls if available
        if "tool_calls" in result:
            metrics.tool_calls = result["tool_calls"]
            metrics.tools_used = len(result["tool_calls"])

        # Extract cycles if available
        if "cycles" in result:
            metrics.cycles_used = result["cycles"]

    async def _process_result(
        self,
        result: Dict[str, Any],
        session_id: str,
        execution_id: str,
        agent_id: str,
        metrics: ExecutionMetrics,
    ) -> AsyncIterator[ExecutionEvent]:
        """Process result and emit tool/subagent events."""
        # Emit tool events
        tool_calls = result.get("tool_calls", [])
        for i, tool_call in enumerate(tool_calls):
            tool_name = tool_call.get("tool", tool_call.get("name", "unknown"))
            tool_input = tool_call.get("input", tool_call.get("arguments", {}))
            tool_output = tool_call.get("output", tool_call.get("result", ""))
            tool_error = tool_call.get("error")
            tool_call_id = tool_call.get("id", f"tool-{uuid.uuid4().hex[:8]}")

            # TOOL_USE event
            yield self._emit(
                ToolUseEvent(
                    session_id=session_id,
                    execution_id=execution_id,
                    tool=tool_name,
                    input=tool_input,
                    tool_call_id=tool_call_id,
                )
            )

            # TOOL_RESULT event
            yield self._emit(
                ToolResultEvent(
                    session_id=session_id,
                    execution_id=execution_id,
                    tool=tool_name,
                    output=tool_output,
                    error=tool_error,
                    tool_call_id=tool_call_id,
                )
            )

            # PROGRESS event
            progress_pct = 25 + int((i + 1) / max(len(tool_calls), 1) * 50)
            yield self._emit(
                ProgressEvent(
                    session_id=session_id,
                    execution_id=execution_id,
                    percentage=progress_pct,
                    step=f"Tool execution ({i + 1}/{len(tool_calls)})",
                    details=f"Executed {tool_name}",
                )
            )

        # Emit subagent events
        subagent_calls = result.get("subagent_calls", [])
        for subagent_call in subagent_calls:
            metrics.subagents_spawned += 1

            yield self._emit(
                SubagentSpawnEvent(
                    session_id=session_id,
                    subagent_id=subagent_call.get(
                        "subagent_id", f"subagent-{uuid.uuid4().hex[:8]}"
                    ),
                    subagent_name=subagent_call.get("name", "unknown"),
                    task=subagent_call.get("task", ""),
                    parent_agent_id=agent_id,
                    trust_chain_id=subagent_call.get("trust_chain_id", ""),
                    capabilities=subagent_call.get("capabilities", []),
                    model=subagent_call.get("model"),
                    max_turns=subagent_call.get("max_turns"),
                    run_in_background=subagent_call.get("run_in_background", False),
                )
            )

            # COST_UPDATE for subagent
            subagent_tokens = subagent_call.get("tokens_used", 0)
            subagent_cost = subagent_call.get("cost_usd", 0.0)
            metrics.total_tokens += subagent_tokens
            metrics.total_cost_usd += subagent_cost

            yield self._emit(
                CostUpdateEvent(
                    session_id=session_id,
                    agent_id=agent_id,
                    tokens_added=subagent_tokens,
                    cost_added_usd=subagent_cost,
                    total_tokens=metrics.total_tokens,
                    total_cost_usd=metrics.total_cost_usd,
                )
            )

    def _extract_output(self, result: Dict[str, Any]) -> str:
        """Extract text output from agent result."""
        # Try common output field names
        for field_name in ["answer", "response", "output", "text", "content", "result"]:
            if field_name in result:
                value = result[field_name]
                if isinstance(value, str):
                    return value
                elif isinstance(value, dict):
                    return str(value)

        # Return string representation
        return str(result)

    def _is_recoverable(self, error: Exception) -> bool:
        """Determine if error is recoverable."""
        recoverable_types = (
            "RateLimitError",
            "Timeout",
            "ConnectionError",
            "TemporaryError",
        )
        return type(error).__name__ in recoverable_types

    def _emit(self, event: ExecutionEvent) -> ExecutionEvent:
        """Emit event and call callback if set."""
        if self._on_event:
            self._on_event(event)
        return event


# Convenience function for SSE formatting
def format_sse(event: ExecutionEvent) -> str:
    """
    Format ExecutionEvent for Server-Sent Events.

    Example:
        >>> from kaizen.execution import format_sse
        >>> event = StartedEvent(session_id="s1", execution_id="e1", ...)
        >>> sse_data = format_sse(event)
        >>> # Returns: "data: {...json...}\n\n"
    """
    import json

    data = event.to_dict()
    return f"data: {json.dumps(data)}\n\n"


__all__ = [
    "StreamingExecutor",
    "ExecutionMetrics",
    "format_sse",
]
