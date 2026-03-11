"""TaskTool - Subagent spawning for autonomous execution.

Implements the Task tool that spawns specialized subagents dynamically,
similar to Claude Code's Task tool. Enables multi-agent coordination
and autonomous execution patterns.

See: TODO-203 Task/Skill Tools, ADR-013 Specialist System

Example:
    >>> from kaizen.tools.native import TaskTool, KaizenToolRegistry
    >>> from kaizen.runtime.adapters import LocalKaizenAdapter
    >>>
    >>> adapter = LocalKaizenAdapter(kaizen_options=options)
    >>> task_tool = TaskTool(adapter=adapter)
    >>> registry = KaizenToolRegistry()
    >>> registry.register(task_tool)
    >>>
    >>> result = await registry.execute("task", {
    ...     "subagent_type": "code-reviewer",
    ...     "prompt": "Review the authentication module",
    ...     "description": "Review auth module",
    ... })
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from kaizen.execution.events import (
    CostUpdateEvent,
    SubagentCompleteEvent,
    SubagentSpawnEvent,
)
from kaizen.execution.subagent_result import SubagentResult
from kaizen.tools.native.base import BaseTool, NativeToolResult
from kaizen.tools.types import DangerLevel, ToolCategory

if TYPE_CHECKING:
    from kaizen.runtime.adapters.kaizen_local import LocalKaizenAdapter

logger = logging.getLogger(__name__)

# Type alias for event callback
EventCallback = Callable[[Any], None]


class TaskTool(BaseTool):
    """Spawn and execute specialized subagents.

    The Task tool enables multi-agent coordination by spawning subagents
    that execute autonomously and return results. This is the core tool
    for agent decomposition and delegation patterns.

    Features:
    - Spawn specialists by name from registry
    - Propagate trust chain from parent
    - Track cost and token usage
    - Support background execution
    - Emit events for progress tracking

    Parameters:
        subagent_type: Type/name of specialist to spawn (from registry)
        prompt: Task description for subagent
        description: Short (3-5 word) description for progress display
        model: Optional model override
        max_turns: Optional max execution turns
        run_in_background: Run async and return output file path

    Example:
        >>> result = await task_tool.execute(
        ...     subagent_type="code-reviewer",
        ...     prompt="Review the authentication module for security issues",
        ...     description="Review auth module",
        ... )
        >>> print(result.output)
    """

    name = "task"
    description = (
        "Spawn a specialized subagent to handle a complex task. "
        "Use this when you need to delegate work to a specialist agent."
    )
    danger_level = DangerLevel.MEDIUM  # Creates new agent execution
    category = ToolCategory.AI

    def __init__(
        self,
        adapter: Optional["LocalKaizenAdapter"] = None,
        parent_agent_id: Optional[str] = None,
        trust_chain_id: Optional[str] = None,
        on_event: Optional[EventCallback] = None,
        session_id: Optional[str] = None,
    ):
        """Initialize TaskTool.

        Args:
            adapter: LocalKaizenAdapter with specialist registry
            parent_agent_id: ID of the parent agent (for trust chain)
            trust_chain_id: Trust chain ID to propagate to subagents
            on_event: Callback for emitting execution events
            session_id: Session ID for event correlation
        """
        super().__init__()
        self._adapter = adapter
        self._parent_agent_id = parent_agent_id or f"agent_{uuid.uuid4().hex[:8]}"
        self._trust_chain_id = trust_chain_id or f"chain_{uuid.uuid4().hex[:8]}"
        self._on_event = on_event
        self._session_id = session_id or f"session_{uuid.uuid4().hex[:8]}"

        # Background task tracking
        self._background_tasks: Dict[str, asyncio.Task] = {}

    async def execute(
        self,
        subagent_type: str,
        prompt: str,
        description: str = "",
        model: Optional[str] = None,
        max_turns: Optional[int] = None,
        run_in_background: bool = False,
        resume: Optional[str] = None,
    ) -> NativeToolResult:
        """Spawn and execute a subagent.

        Args:
            subagent_type: Name of specialist to spawn (from registry)
            prompt: Task description for subagent
            description: Short description for progress display
            model: Optional model override
            max_turns: Optional max execution turns
            run_in_background: Run async and return output file path
            resume: Optional subagent_id to resume from checkpoint

        Returns:
            NativeToolResult with SubagentResult in output
        """
        start_time = time.time()
        subagent_id = resume or f"subagent_{uuid.uuid4().hex[:12]}"

        # Validate adapter
        if self._adapter is None:
            return NativeToolResult.from_error(
                "TaskTool requires an adapter with specialist registry"
            )

        # Validate subagent_type
        specialist = self._adapter.get_specialist(subagent_type)
        if specialist is None:
            available = self._adapter.list_specialists()
            return NativeToolResult.from_error(
                f"Specialist '{subagent_type}' not found. "
                f"Available specialists: {', '.join(available) if available else 'none'}"
            )

        # Get capabilities from specialist
        capabilities = specialist.available_tools or []

        # Emit subagent_spawn event
        spawn_event = SubagentSpawnEvent(
            session_id=self._session_id,
            subagent_id=subagent_id,
            subagent_name=subagent_type,
            task=prompt[:200],  # Truncate for event
            parent_agent_id=self._parent_agent_id,
            trust_chain_id=self._trust_chain_id,
            capabilities=capabilities,
            model=model or specialist.model,
            max_turns=max_turns,
            run_in_background=run_in_background,
        )
        await self._emit_event(spawn_event)

        # Handle background execution
        if run_in_background:
            return await self._execute_background(
                subagent_id=subagent_id,
                subagent_type=subagent_type,
                prompt=prompt,
                description=description,
                model=model,
                max_turns=max_turns,
            )

        # Execute subagent synchronously
        try:
            result = await self._execute_subagent(
                subagent_id=subagent_id,
                subagent_type=subagent_type,
                prompt=prompt,
                model=model,
                max_turns=max_turns,
                start_time=start_time,
            )

            # Emit completion event
            duration_ms = int((time.time() - start_time) * 1000)
            complete_event = SubagentCompleteEvent(
                session_id=self._session_id,
                subagent_id=subagent_id,
                parent_agent_id=self._parent_agent_id,
                status=result.status,
                output=result.output[:500],  # Truncate for event
                tokens_used=result.tokens_used,
                cost_usd=result.cost_usd,
                cycles_used=result.cycles_used,
                duration_ms=duration_ms,
                error_message=result.error_message,
            )
            await self._emit_event(complete_event)

            # Emit cost update event
            if result.tokens_used > 0:
                cost_event = CostUpdateEvent(
                    session_id=self._session_id,
                    agent_id=subagent_id,
                    tokens_added=result.tokens_used,
                    cost_added_usd=result.cost_usd,
                    total_tokens=result.tokens_used,
                    total_cost_usd=result.cost_usd,
                )
                await self._emit_event(cost_event)

            return NativeToolResult.from_success(
                result,
                subagent_id=subagent_id,
                specialist_name=subagent_type,
                duration_ms=duration_ms,
            )

        except asyncio.CancelledError:
            # Handle cancellation (interrupt)
            result = SubagentResult.from_error(
                subagent_id=subagent_id,
                error_message="Execution was interrupted",
                error_type="InterruptedError",
                specialist_name=subagent_type,
            )
            return NativeToolResult.from_error(
                "Subagent execution was interrupted",
                subagent_result=result.to_dict(),
            )

        except Exception as e:
            logger.exception(f"Subagent execution failed: {e}")
            result = SubagentResult.from_error(
                subagent_id=subagent_id,
                error_message=str(e),
                error_type=type(e).__name__,
                specialist_name=subagent_type,
            )
            return NativeToolResult.from_error(
                f"Subagent execution failed: {e}",
                subagent_result=result.to_dict(),
            )

    async def _execute_subagent(
        self,
        subagent_id: str,
        subagent_type: str,
        prompt: str,
        model: Optional[str],
        max_turns: Optional[int],
        start_time: float,
    ) -> SubagentResult:
        """Execute a subagent synchronously.

        Args:
            subagent_id: Unique ID for this subagent instance
            subagent_type: Name of specialist to spawn
            prompt: Task description
            model: Optional model override
            max_turns: Optional max execution turns
            start_time: Start time for duration tracking

        Returns:
            SubagentResult with execution output and metrics
        """
        # Get specialist-configured adapter
        specialist_adapter = self._adapter.for_specialist(subagent_type)
        if specialist_adapter is None:
            return SubagentResult.from_error(
                subagent_id=subagent_id,
                error_message=f"Could not create adapter for specialist: {subagent_type}",
            )

        # Override model if specified
        if model:
            specialist_adapter.config.model = model

        # Override max_cycles if specified
        if max_turns:
            specialist_adapter.config.max_cycles = max_turns

        # Create execution context
        from kaizen.runtime.context import ExecutionContext

        context = ExecutionContext(
            task=prompt,
            session_id=subagent_id,
        )

        # Execute
        execution_result = await specialist_adapter.execute(context)

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Map execution result to SubagentResult
        if execution_result.status.value in ("complete", "completed"):
            return SubagentResult.from_success(
                subagent_id=subagent_id,
                output=execution_result.output,
                tokens_used=execution_result.tokens_used or 0,
                cost_usd=execution_result.cost_usd or 0.0,
                cycles_used=execution_result.cycles_used or 0,
                duration_ms=duration_ms,
                specialist_name=subagent_type,
                model_used=specialist_adapter.config.model,
                parent_agent_id=self._parent_agent_id,
                trust_chain_id=self._trust_chain_id,
            )
        else:
            return SubagentResult.from_error(
                subagent_id=subagent_id,
                error_message=execution_result.error_message or "Execution failed",
                error_type=execution_result.error_type or "ExecutionError",
                tokens_used=execution_result.tokens_used or 0,
                cost_usd=execution_result.cost_usd or 0.0,
                cycles_used=execution_result.cycles_used or 0,
                duration_ms=duration_ms,
                specialist_name=subagent_type,
            )

    async def _execute_background(
        self,
        subagent_id: str,
        subagent_type: str,
        prompt: str,
        description: str,
        model: Optional[str],
        max_turns: Optional[int],
    ) -> NativeToolResult:
        """Execute a subagent in the background.

        Args:
            subagent_id: Unique ID for this subagent instance
            subagent_type: Name of specialist to spawn
            prompt: Task description
            description: Short description for progress display
            model: Optional model override
            max_turns: Optional max execution turns

        Returns:
            NativeToolResult with output file path
        """
        import os
        import tempfile

        # Create output file
        output_dir = tempfile.gettempdir()
        output_file = os.path.join(output_dir, f"kaizen_subagent_{subagent_id}.output")

        # Write initial status
        with open(output_file, "w") as f:
            f.write(f"Subagent {subagent_id} started\n")
            f.write(f"Specialist: {subagent_type}\n")
            f.write(f"Task: {prompt[:200]}\n")
            f.write("Status: running\n")

        async def background_task():
            """Background execution coroutine."""
            start_time = time.time()
            try:
                result = await self._execute_subagent(
                    subagent_id=subagent_id,
                    subagent_type=subagent_type,
                    prompt=prompt,
                    model=model,
                    max_turns=max_turns,
                    start_time=start_time,
                )

                # Write result to file
                with open(output_file, "w") as f:
                    f.write(f"Subagent {subagent_id} completed\n")
                    f.write(f"Status: {result.status}\n")
                    f.write(f"Tokens: {result.tokens_used}\n")
                    f.write(f"Cost: ${result.cost_usd:.6f}\n")
                    f.write("---\n")
                    f.write(result.output)

            except Exception as e:
                with open(output_file, "w") as f:
                    f.write(f"Subagent {subagent_id} failed\n")
                    f.write(f"Error: {e}\n")

            finally:
                # Clean up tracking
                if subagent_id in self._background_tasks:
                    del self._background_tasks[subagent_id]

        # Start background task
        task = asyncio.create_task(background_task())
        self._background_tasks[subagent_id] = task

        # Return immediately with output file path
        result = SubagentResult.from_background(
            subagent_id=subagent_id,
            output_file=output_file,
            specialist_name=subagent_type,
            parent_agent_id=self._parent_agent_id,
            trust_chain_id=self._trust_chain_id,
        )

        return NativeToolResult.from_success(
            result,
            subagent_id=subagent_id,
            output_file=output_file,
            is_background=True,
        )

    async def get_background_status(self, subagent_id: str) -> Optional[SubagentResult]:
        """Get status of a background execution.

        Args:
            subagent_id: ID of the subagent to check

        Returns:
            SubagentResult with current status, or None if not found
        """
        task = self._background_tasks.get(subagent_id)
        if task is None:
            return None

        if task.done():
            # Task completed, try to get result
            try:
                return task.result()
            except Exception as e:
                return SubagentResult.from_error(
                    subagent_id=subagent_id,
                    error_message=str(e),
                )
        else:
            # Task still running
            return SubagentResult(
                subagent_id=subagent_id,
                output="",
                status="running",
                is_background=True,
            )

    async def _emit_event(self, event: Any) -> None:
        """Emit an execution event.

        Args:
            event: Event to emit
        """
        if self._on_event:
            try:
                if asyncio.iscoroutinefunction(self._on_event):
                    await self._on_event(event)
                else:
                    self._on_event(event)
            except Exception as e:
                logger.warning(f"Failed to emit event: {e}")

    def get_schema(self) -> Dict[str, Any]:
        """Return JSON Schema for LLM function calling."""
        return {
            "type": "object",
            "properties": {
                "subagent_type": {
                    "type": "string",
                    "description": (
                        "The type/name of specialist to spawn from the registry. "
                        "Use list_specialists() to see available specialists."
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": (
                        "The task description for the subagent. "
                        "Be specific about what you want the subagent to do."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": (
                        "A short (3-5 word) description for progress display. "
                        "Example: 'Review auth module'"
                    ),
                },
                "model": {
                    "type": "string",
                    "description": "Optional model override for this subagent.",
                },
                "max_turns": {
                    "type": "integer",
                    "description": "Optional maximum execution turns/cycles.",
                    "minimum": 1,
                },
                "run_in_background": {
                    "type": "boolean",
                    "description": (
                        "Run the subagent asynchronously. "
                        "Returns an output_file path to check progress."
                    ),
                    "default": False,
                },
                "resume": {
                    "type": "string",
                    "description": (
                        "Optional subagent_id to resume from checkpoint. "
                        "Use this to continue a previous execution."
                    ),
                },
            },
            "required": ["subagent_type", "prompt"],
        }


__all__ = ["TaskTool"]
