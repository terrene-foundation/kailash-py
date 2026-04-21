"""
AgentLoop - Extracted execution loop logic for BaseAgent.

Encapsulates the TAOD (Think/Act/Observe/Decide) execution flow including:
- Hook triggering (sync and async bridge)
- Memory context loading and saving
- Shared memory integration
- Strategy execution delegation

Uses duck typing for the agent parameter to avoid circular imports --
the agent must provide: hook_manager, agent_id, memory, shared_memory,
signature, strategy, config, and the 7 extension point methods.

Copyright 2025 Terrene Foundation (Singapore CLG)
Licensed under Apache-2.0
"""

import asyncio
import concurrent.futures
import contextvars
import inspect
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _emit_trace_event(
    agent: Any,
    *,
    event_type: str,
    run_id: str,
    parent_event_id: Optional[str] = None,
    duration_ms: Optional[float] = None,
    status: Optional[str] = None,
) -> Optional[str]:
    """Emit a TraceEvent to the agent's trace exporter if one is attached.

    Fire-and-forget: any failure inside the exporter is logged at WARN
    and swallowed. Trace emission MUST NOT break the agent's hot path
    (rules/observability.md Rule 7 carve-out for observability side
    paths — the agent operation itself succeeded; the trace write is
    the degraded-path signal).

    Returns the emitted event's ``event_id`` so callers can thread it
    into ``parent_event_id`` of subsequent events, or ``None`` when no
    exporter is attached.
    """
    exporter = getattr(agent, "_trace_exporter", None)
    if exporter is None:
        return None

    try:
        # Lazy import to avoid kaizen.core → kaizen.observability circular.
        from kailash.diagnostics.protocols import (  # noqa: PLC0415
            TraceEvent,
            TraceEventStatus,
            TraceEventType,
        )

        event_id = f"evt-{uuid.uuid4().hex[:12]}"
        event = TraceEvent(
            event_id=event_id,
            event_type=TraceEventType(event_type),
            timestamp=datetime.now(timezone.utc),
            run_id=run_id,
            agent_id=str(getattr(agent, "agent_id", "unknown")),
            cost_microdollars=0,
            parent_event_id=parent_event_id,
            duration_ms=duration_ms,
            status=TraceEventStatus(status) if status is not None else None,
        )
        exporter.export(event)
        return event_id
    except Exception as exc:  # noqa: BLE001 — fire-and-forget trace
        logger.warning(
            "kaizen.agent_loop.trace_export_failed",
            extra={
                "trace_event_type": event_type,
                "trace_run_id": run_id,
                "trace_agent_id": str(getattr(agent, "agent_id", "unknown")),
                "trace_error": str(exc),
                "mode": "real",
            },
        )
        return None


@dataclass
class AgentLoopConfig:
    """Configuration for the agent execution loop."""

    max_cycles: int = 10
    temperature: float = 0.7
    max_tokens: int = 4096

    @classmethod
    def from_agent(cls, agent) -> "AgentLoopConfig":
        """Create loop config from an agent's BaseAgentConfig.

        Args:
            agent: Any object with a .config attribute exposing
                   max_cycles, temperature, max_tokens.
        """
        config = agent.config
        return cls(
            max_cycles=getattr(config, "max_cycles", 10),
            temperature=getattr(config, "temperature", 0.7) or 0.7,
            max_tokens=getattr(config, "max_tokens", 4096) or 4096,
        )


def run_async_hook(coro) -> None:
    """Run an async coroutine from sync context (hook bridge).

    Handles the async/sync boundary for hook triggers. Uses
    ThreadPoolExecutor when inside an existing event loop, or
    asyncio.run() when no loop is running.

    Copies the current contextvars context into the worker thread so
    that request-scoped state (active provider, active session, tracing
    IDs) set by the caller remains observable inside the coroutine. See
    issue #486 -- without ``copy_context().run`` every contextvar silently
    reverts to its default inside the worker.
    """
    try:
        asyncio.get_running_loop()
        # Inside an event loop -- run in a thread to avoid nesting
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            ctx = contextvars.copy_context()
            executor.submit(ctx.run, asyncio.run, coro).result(timeout=5.0)
    except RuntimeError:
        # No event loop -- safe to use asyncio.run() (runs on the caller's
        # thread, so contextvars propagate naturally).
        asyncio.run(coro)


def _trigger_hook_sync(hook_manager, event, agent_id: str, data: dict) -> None:
    """Trigger an async hook from a sync context. Swallows failures."""
    if hook_manager is None:
        return

    from kaizen.core.autonomy.hooks.types import HookEvent

    try:
        run_async_hook(hook_manager.trigger(event, agent_id=agent_id, data=data))
    except Exception as e:
        logger.error(f"{event} hook failed: {e}")


async def _trigger_hook_async(hook_manager, event, agent_id: str, data: dict) -> None:
    """Trigger an async hook from an async context. Swallows failures."""
    if hook_manager is None:
        return

    try:
        await hook_manager.trigger(event, agent_id=agent_id, data=data)
    except Exception as e:
        logger.error(f"{event} hook failed: {e}")


def _load_memory_context(agent, inputs: dict, session_id: Optional[str]) -> dict:
    """Load individual and shared memory context into inputs.

    Args:
        agent: Duck-typed agent with .memory, .shared_memory, .agent_id,
               .hook_manager attributes.
        inputs: Mutable dict of execution inputs (modified in-place).
        session_id: Optional session identifier for individual memory.

    Returns:
        The (possibly modified) inputs dict.
    """
    from kaizen.core.autonomy.hooks.types import HookEvent

    if agent.memory and session_id:
        _trigger_hook_sync(
            agent.hook_manager,
            HookEvent.PRE_MEMORY_LOAD,
            agent.agent_id,
            {"session_id": session_id},
        )
        memory_context = agent.memory.load_context(session_id)
        _trigger_hook_sync(
            agent.hook_manager,
            HookEvent.POST_MEMORY_LOAD,
            agent.agent_id,
            {"session_id": session_id, "context_size": len(str(memory_context))},
        )
        inputs["_memory_context"] = memory_context

    if agent.shared_memory:
        shared_insights = agent.shared_memory.read_relevant(
            agent_id=agent.agent_id,
            exclude_own=True,
            limit=10,
        )
        inputs["_shared_insights"] = shared_insights

    return inputs


def _save_memory_turn(
    agent,
    inputs: dict,
    processed_inputs: dict,
    final_result: dict,
    session_id: Optional[str],
) -> None:
    """Save turn to individual memory and write shared insights.

    Args:
        agent: Duck-typed agent.
        inputs: Original inputs.
        processed_inputs: Inputs after pre-execution hook.
        final_result: Final execution result.
        session_id: Session identifier.
    """
    from kaizen.core.autonomy.hooks.types import HookEvent

    if agent.memory and session_id:
        user_input = inputs.get("prompt", "")
        if not user_input and processed_inputs:
            user_input = (
                str(list(processed_inputs.values())[0]) if processed_inputs else ""
            )

        agent_response = final_result.get("response", "")
        if not agent_response and final_result:
            agent_response = str(list(final_result.values())[0]) if final_result else ""

        turn = {
            "user": user_input,
            "agent": agent_response,
            "timestamp": datetime.now().isoformat(),
        }

        _trigger_hook_sync(
            agent.hook_manager,
            HookEvent.PRE_MEMORY_SAVE,
            agent.agent_id,
            {"session_id": session_id, "turn_size": len(str(turn))},
        )
        agent.memory.save_turn(session_id, turn)
        _trigger_hook_sync(
            agent.hook_manager,
            HookEvent.POST_MEMORY_SAVE,
            agent.agent_id,
            {"session_id": session_id, "turn_saved": True},
        )

    if agent.shared_memory and final_result.get("_write_insight"):
        insight = {
            "agent_id": agent.agent_id,
            "content": final_result["_write_insight"],
            "tags": final_result.get("_insight_tags", []),
            "importance": final_result.get("_insight_importance", 0.5),
            "segment": final_result.get("_insight_segment", "execution"),
            "metadata": final_result.get("_insight_metadata", {}),
        }
        agent.shared_memory.write_insight(insight)


async def _save_memory_turn_async(
    agent,
    inputs: dict,
    processed_inputs: dict,
    final_result: dict,
    session_id: Optional[str],
) -> None:
    """Async version of _save_memory_turn."""
    from kaizen.core.autonomy.hooks.types import HookEvent

    if agent.memory and session_id:
        user_input = inputs.get("prompt", "")
        if not user_input and processed_inputs:
            user_input = (
                str(list(processed_inputs.values())[0]) if processed_inputs else ""
            )

        agent_response = final_result.get("response", "")
        if not agent_response and final_result:
            agent_response = str(list(final_result.values())[0]) if final_result else ""

        turn = {
            "user": user_input,
            "agent": agent_response,
            "timestamp": datetime.now().isoformat(),
        }

        # In async context, the memory hooks still use sync bridge
        # because the hook trigger API is async
        _trigger_hook_sync(
            agent.hook_manager,
            HookEvent.PRE_MEMORY_SAVE,
            agent.agent_id,
            {"session_id": session_id, "turn_size": len(str(turn))},
        )
        agent.memory.save_turn(session_id, turn)
        _trigger_hook_sync(
            agent.hook_manager,
            HookEvent.POST_MEMORY_SAVE,
            agent.agent_id,
            {"session_id": session_id, "turn_saved": True},
        )

    if agent.shared_memory and final_result.get("_write_insight"):
        insight = {
            "agent_id": agent.agent_id,
            "content": final_result["_write_insight"],
            "tags": final_result.get("_insight_tags", []),
            "importance": final_result.get("_insight_importance", 0.5),
            "segment": final_result.get("_insight_segment", "execution"),
            "metadata": final_result.get("_insight_metadata", {}),
        }
        agent.shared_memory.write_insight(insight)


def _execute_strategy(agent, processed_inputs: dict) -> dict:
    """Execute the agent strategy (sync), handling async strategies.

    Args:
        agent: Duck-typed agent with .strategy attribute.
        processed_inputs: Pre-processed inputs.

    Returns:
        Execution result dict.

    Note:
        When the caller is already inside a running event loop we hand
        the coroutine to a worker thread. ``ThreadPoolExecutor`` does
        NOT propagate :mod:`contextvars` into its workers, so we copy
        the caller's context explicitly and run the coroutine inside
        that context (issue #486). Without this, request-scoped state
        used by custom provider routing (active provider, active
        session, tracing IDs) silently resets to defaults inside the
        strategy's LLM dispatch and tool invocations.
    """
    if hasattr(agent.strategy, "execute"):
        if inspect.iscoroutinefunction(agent.strategy.execute):
            # Async strategy -- run in event loop
            try:
                asyncio.get_running_loop()
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    ctx = contextvars.copy_context()
                    future = executor.submit(
                        ctx.run,
                        asyncio.run,
                        agent.strategy.execute(agent, processed_inputs),
                    )
                    return future.result()
            except RuntimeError:
                return asyncio.run(agent.strategy.execute(agent, processed_inputs))
        else:
            return agent.strategy.execute(agent, processed_inputs)
    else:
        return agent._simple_execute(processed_inputs)


async def _execute_strategy_async(agent, processed_inputs: dict) -> dict:
    """Execute the agent strategy (async).

    Args:
        agent: Duck-typed agent with .strategy attribute.
        processed_inputs: Pre-processed inputs.

    Returns:
        Execution result dict.
    """
    if hasattr(agent.strategy, "execute_async"):
        return await agent.strategy.execute_async(agent, processed_inputs)
    elif hasattr(agent.strategy, "execute"):
        if inspect.iscoroutinefunction(agent.strategy.execute):
            return await agent.strategy.execute(agent, processed_inputs)
        else:
            return await asyncio.to_thread(
                agent.strategy.execute, agent, processed_inputs
            )
    else:
        return await agent._simple_execute_async(processed_inputs)


class AgentLoop:
    """Extracted execution loop for BaseAgent.

    Orchestrates the full run cycle: memory load, pre-hook, strategy
    execution, validation, post-hook, memory save. All methods accept
    a duck-typed agent to avoid importing BaseAgent.
    """

    @staticmethod
    def run_sync(agent, **inputs) -> Dict[str, Any]:
        """Execute agent synchronously with full lifecycle.

        This replaces the inline run() body in BaseAgent. The agent
        parameter is duck-typed -- it must expose the attributes and
        methods documented in this module's docstring.
        """
        from kaizen.core.autonomy.hooks.types import HookEvent

        # Auto-discover MCP tools on first run
        if (
            agent.has_mcp_support()
            and not agent._discovered_mcp_tools
            and agent._mcp_client is not None
        ):
            try:
                run_async_hook(agent.discover_mcp_tools())
            except Exception as e:
                logger.warning("MCP auto-discovery failed: %s", e)

        session_id = inputs.pop("session_id", None)

        # Trace correlation — issue #567 PR#6 hot-path wiring of kaizen.observability.
        # run_id is stable across start/end events per rules/observability.md Rule 2.
        trace_run_id = f"run-{uuid.uuid4().hex[:12]}"
        trace_t0 = time.monotonic()
        start_event_id = _emit_trace_event(
            agent, event_type="agent.run.start", run_id=trace_run_id
        )

        try:
            # Load memory context
            _load_memory_context(agent, inputs, session_id)

            processed_inputs = agent._pre_execution_hook(inputs)

            # Trigger PRE_AGENT_LOOP hook
            _trigger_hook_sync(
                agent.hook_manager,
                HookEvent.PRE_AGENT_LOOP,
                agent.agent_id,
                {
                    "inputs": processed_inputs,
                    "signature": agent.signature.__class__.__name__,
                },
            )

            # Execute strategy
            result = _execute_strategy(agent, processed_inputs)

            # Validate output
            agent._validate_signature_output(result)

            # Post-execution hook
            final_result = agent._post_execution_hook(result)

            # Trigger POST_AGENT_LOOP hook
            _trigger_hook_sync(
                agent.hook_manager,
                HookEvent.POST_AGENT_LOOP,
                agent.agent_id,
                {
                    "result": final_result,
                    "signature": agent.signature.__class__.__name__,
                },
            )

            # Save memory turn
            _save_memory_turn(agent, inputs, processed_inputs, final_result, session_id)

            _emit_trace_event(
                agent,
                event_type="agent.run.end",
                run_id=trace_run_id,
                parent_event_id=start_event_id,
                duration_ms=(time.monotonic() - trace_t0) * 1000.0,
                status="ok",
            )
            return final_result

        except Exception as error:
            import gc

            _emit_trace_event(
                agent,
                event_type="agent.run.end",
                run_id=trace_run_id,
                parent_event_id=start_event_id,
                duration_ms=(time.monotonic() - trace_t0) * 1000.0,
                status="error",
            )
            gc.collect()
            return agent._handle_error(error, {"inputs": inputs})

    @staticmethod
    async def run_async(agent, **inputs) -> Dict[str, Any]:
        """Execute agent asynchronously with full lifecycle.

        This replaces the inline run_async() body in BaseAgent.
        """
        from kaizen.core.autonomy.hooks.types import HookEvent

        if not agent.config.use_async_llm:
            raise ValueError(
                "Agent not configured for async mode. "
                "Set use_async_llm=True in BaseAgentConfig:\n\n"
                "config = BaseAgentConfig(\n"
                "    llm_provider='openai',\n"
                "    model='gpt-4',\n"
                "    use_async_llm=True  # Enable async mode\n"
                ")\n"
            )

        session_id = inputs.pop("session_id", None)

        trace_run_id = f"run-{uuid.uuid4().hex[:12]}"
        trace_t0 = time.monotonic()
        start_event_id = _emit_trace_event(
            agent, event_type="agent.run.start", run_id=trace_run_id
        )

        try:
            # Load memory context (sync -- memory is sync API)
            _load_memory_context(agent, inputs, session_id)

            processed_inputs = agent._pre_execution_hook(inputs)

            # Trigger PRE_AGENT_LOOP hook (async)
            await _trigger_hook_async(
                agent.hook_manager,
                HookEvent.PRE_AGENT_LOOP,
                agent.agent_id,
                {
                    "inputs": processed_inputs,
                    "signature": agent.signature.__class__.__name__,
                },
            )

            # Execute strategy (async)
            result = await _execute_strategy_async(agent, processed_inputs)

            # Validate output
            agent._validate_signature_output(result)

            # Post-execution hook
            final_result = agent._post_execution_hook(result)

            # Trigger POST_AGENT_LOOP hook (async)
            await _trigger_hook_async(
                agent.hook_manager,
                HookEvent.POST_AGENT_LOOP,
                agent.agent_id,
                {
                    "result": final_result,
                    "signature": agent.signature.__class__.__name__,
                },
            )

            # Save memory turn
            await _save_memory_turn_async(
                agent, inputs, processed_inputs, final_result, session_id
            )

            _emit_trace_event(
                agent,
                event_type="agent.run.end",
                run_id=trace_run_id,
                parent_event_id=start_event_id,
                duration_ms=(time.monotonic() - trace_t0) * 1000.0,
                status="ok",
            )
            return final_result

        except Exception as error:
            _emit_trace_event(
                agent,
                event_type="agent.run.end",
                run_id=trace_run_id,
                parent_event_id=start_event_id,
                duration_ms=(time.monotonic() - trace_t0) * 1000.0,
                status="error",
            )
            return agent._handle_error(error, {"inputs": inputs})
