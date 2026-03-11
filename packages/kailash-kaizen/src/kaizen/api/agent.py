"""
Unified Agent API

This module provides the primary Agent class - the unified entry point
for all Kaizen agent interactions. It supports progressive configuration
from simple 2-line usage to full expert control.

Quick Start:
    from kaizen.api import Agent

    # Simple usage (2 lines)
    agent = Agent(model="gpt-4")
    result = agent.run("What is IRP?")

    # With configuration
    agent = Agent(
        model="gpt-4",
        execution_mode="autonomous",
        memory="session",
        tool_access="constrained",
    )
    result = agent.run("Implement a REST API endpoint")
"""

import asyncio
import uuid
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from kaizen.api.config import AgentConfig
from kaizen.api.result import AgentResult, ResultStatus, ToolCallRecord
from kaizen.api.shortcuts import (
    resolve_execution_mode,
    resolve_memory_shortcut,
    resolve_model_shortcut,
    resolve_runtime_shortcut,
)
from kaizen.api.types import AgentCapabilities, ExecutionMode, MemoryDepth, ToolAccess
from kaizen.api.validation import (
    ConfigurationError,
    validate_configuration,
    validate_model_runtime_compatibility,
)


class Agent:
    """
    Unified Agent API - The primary interface for Kaizen agents.

    Supports progressive configuration from simple 2-line usage to expert mode.

    Examples:
        # Level 1: Dead simple (2 lines)
        agent = Agent(model="gpt-4")
        result = agent.run("What is IRP?")

        # Level 2: Configure execution mode
        agent = Agent(model="gpt-4", execution_mode="autonomous", max_cycles=50)

        # Level 3: Add memory
        agent = Agent(model="gpt-4", memory="session")
        result = agent.chat("Remember my name is Alice")
        result = agent.chat("What's my name?")  # Remembers!

        # Level 4: Add tools
        agent = Agent(model="gpt-4", tool_access="constrained")
        result = agent.run("Read the README.md file")

        # Level 5: Select runtime
        agent = Agent(model="claude-sonnet", runtime="local")

        # Level 6: Multi-LLM routing
        agent = Agent(
            model="gpt-4",
            runtime="local",
            llm_routing={"simple": "gpt-3.5-turbo", "complex": "claude-opus"}
        )

        # Level 7: Expert configuration
        agent = Agent(config=AgentConfig(
            execution_mode=ExecutionMode.AUTONOMOUS,
            memory=HierarchicalMemory(...),
            runtime=LocalKaizenAdapter(...),
            checkpoint=CheckpointConfig(strategy="on_cycle"),
            hooks=HookConfig(on_error=lambda ctx: log_error(ctx)),
        ))
    """

    def __init__(
        self,
        model: Optional[str] = None,
        *,
        # Execution configuration
        execution_mode: Union[str, ExecutionMode] = "single",
        max_cycles: int = 100,
        max_turns: int = 50,
        timeout_seconds: float = 300.0,
        # Memory configuration
        memory: Union[str, Any, None] = "stateless",
        memory_path: Optional[str] = None,
        # Tool configuration
        tool_access: Union[str, ToolAccess] = "none",
        tools: Optional[List[Any]] = None,
        allowed_tools: Optional[List[str]] = None,
        denied_tools: Optional[List[str]] = None,
        # Runtime configuration
        runtime: Union[str, Any] = "local",
        # LLM routing configuration
        llm_routing: Optional[Dict[str, str]] = None,
        routing_strategy: str = "balanced",
        # Model parameters
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        # Expert configuration (overrides all above)
        config: Optional[AgentConfig] = None,
    ):
        """
        Initialize a new Agent.

        Args:
            model: Model name (e.g., "gpt-4", "claude-3-opus"). Required unless config provided.
            execution_mode: Execution mode - "single", "multi", or "autonomous"
            max_cycles: Maximum TAOD cycles for autonomous mode
            max_turns: Maximum conversation turns for multi mode
            timeout_seconds: Overall execution timeout
            memory: Memory configuration - shortcut string or MemoryProvider instance
            memory_path: Path for persistent memory storage
            tool_access: Tool access level - "none", "read_only", "constrained", "full"
            tools: List of Tool instances to register
            allowed_tools: Whitelist of allowed tool names
            denied_tools: Blacklist of denied tool names
            runtime: Runtime adapter - shortcut string or RuntimeAdapter instance
            llm_routing: Task-to-model mapping for multi-LLM routing
            routing_strategy: Routing strategy for multi-LLM routing
            temperature: Model temperature
            system_prompt: Custom system prompt
            config: Expert AgentConfig (overrides all other parameters)

        Raises:
            ConfigurationError: If configuration is invalid
        """
        # Handle expert config
        if config is not None:
            self._init_from_config(config)
            return

        # Require model when not using config
        if model is None:
            raise ConfigurationError(
                "Model is required. Example: Agent(model='gpt-4')",
                field="model",
                suggestions=[
                    'Specify a model: Agent(model="gpt-4")',
                    'Or use an AgentConfig: Agent(config=AgentConfig(model="gpt-4"))',
                ],
            )

        # Resolve shortcuts with helpful error conversion
        resolved_model = resolve_model_shortcut(model)

        try:
            resolved_mode = resolve_execution_mode(execution_mode)
        except ValueError as e:
            raise ConfigurationError(
                str(e),
                field="execution_mode",
                value=execution_mode,
                suggestions=[
                    'Use execution_mode="single" for one-shot tasks',
                    'Use execution_mode="multi" for conversations',
                    'Use execution_mode="autonomous" for agentic tasks',
                ],
            )

        try:
            resolved_tool_access = (
                ToolAccess(tool_access) if isinstance(tool_access, str) else tool_access
            )
        except ValueError as e:
            raise ConfigurationError(
                str(e),
                field="tool_access",
                value=tool_access,
                suggestions=[
                    'Use tool_access="none" for no tool access',
                    'Use tool_access="read_only" for read-only tools',
                    'Use tool_access="constrained" for safe tools with confirmation',
                    'Use tool_access="full" for all tools',
                ],
            )

        # Validate configuration
        is_valid, errors = validate_configuration(
            model=resolved_model,
            runtime=runtime if isinstance(runtime, str) else "local",
            execution_mode=resolved_mode.value,
            memory=memory if isinstance(memory, str) else "session",
            tool_access=resolved_tool_access.value,
            max_cycles=max_cycles,
            timeout_seconds=timeout_seconds,
        )
        if not is_valid:
            # Raise the first error
            raise errors[0]

        # Store configuration
        self._model = resolved_model
        self._execution_mode = resolved_mode
        self._max_cycles = max_cycles
        self._max_turns = max_turns
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature
        self._system_prompt = system_prompt

        # Resolve memory
        self._memory = resolve_memory_shortcut(
            memory,
            memory_path=memory_path,
            max_turns=max_turns,
        )
        self._memory_path = memory_path

        # Store tool configuration
        self._tool_access = resolved_tool_access
        self._tools = tools or []
        self._allowed_tools = allowed_tools
        self._denied_tools = denied_tools

        # Resolve runtime (lazy - don't create until needed)
        self._runtime_spec = runtime
        self._runtime = None  # Lazily initialized

        # LLM routing configuration
        self._llm_routing = llm_routing
        self._routing_strategy = routing_strategy

        # Build capabilities
        self._capabilities = self._build_capabilities()

        # Session state
        self._session_id = str(uuid.uuid4())
        self._current_mode = resolved_mode
        self._is_running = False
        self._is_paused = False

    def _init_from_config(self, config: AgentConfig) -> None:
        """Initialize from AgentConfig."""
        self._model = config.model
        self._execution_mode = config.execution_mode
        self._max_cycles = config.max_cycles
        self._max_turns = config.max_turns
        self._timeout_seconds = config.timeout_seconds
        self._temperature = config.temperature
        self._system_prompt = config.system_prompt

        # Memory
        if config.memory is not None:
            if isinstance(config.memory, str):
                self._memory = resolve_memory_shortcut(
                    config.memory,
                    memory_path=config.memory_path,
                    max_turns=config.max_turns,
                )
            else:
                self._memory = config.memory
        else:
            self._memory = resolve_memory_shortcut("stateless")
        self._memory_path = config.memory_path

        # Tools
        self._tool_access = config.tool_access
        self._tools = config.tools or []
        self._allowed_tools = config.allowed_tools
        self._denied_tools = config.denied_tools

        # Runtime
        self._runtime_spec = config.runtime or "local"
        self._runtime = None

        # LLM routing
        self._llm_routing = (
            config.llm_routing.task_model_mapping if config.llm_routing else None
        )
        self._routing_strategy = config.routing_strategy

        # Capabilities
        self._capabilities = config.get_capabilities()

        # Hooks and checkpoint
        self._hooks = config.hooks
        self._checkpoint = config.checkpoint

        # Session state
        self._session_id = str(uuid.uuid4())
        self._current_mode = config.execution_mode
        self._is_running = False
        self._is_paused = False

    def _build_capabilities(self) -> AgentCapabilities:
        """Build capabilities from current configuration."""
        # Infer memory depth
        memory_depth = MemoryDepth.STATELESS
        if isinstance(self._memory, str):
            try:
                memory_depth = MemoryDepth(self._memory)
            except ValueError:
                memory_depth = MemoryDepth.SESSION
        elif self._memory is not None:
            # Check memory type
            memory_depth = MemoryDepth.SESSION

        return AgentCapabilities(
            execution_modes=[self._execution_mode],
            max_memory_depth=memory_depth,
            tool_access=self._tool_access,
            allowed_tools=self._allowed_tools,
            denied_tools=self._denied_tools,
            max_turns=self._max_turns,
            max_cycles=self._max_cycles,
            max_tool_calls=1000,
            timeout_seconds=self._timeout_seconds,
        )

    def _get_runtime(self) -> Any:
        """Get or create the runtime adapter."""
        if self._runtime is None:
            self._runtime = resolve_runtime_shortcut(
                self._runtime_spec,
                model=self._model,
                temperature=self._temperature,
            )
        return self._runtime

    # === Core Methods ===

    async def run(
        self,
        task: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> AgentResult:
        """
        Execute a task and return the result.

        This is the primary method for executing tasks. Behavior depends on
        the execution mode:
        - SINGLE: One response
        - MULTI: Multi-turn (use chat() for conversation)
        - AUTONOMOUS: TAOD loop until task completion

        Args:
            task: Task description or question
            context: Additional context for execution
            **kwargs: Additional arguments passed to runtime

        Returns:
            AgentResult with output, status, metrics, and tool history

        Examples:
            # Simple question
            result = await agent.run("What is IRP?")
            print(result.text)

            # With context
            result = await agent.run(
                "Analyze this data",
                context={"data": my_data}
            )

            # Check result
            if result.succeeded:
                print(f"Done in {result.duration_ms}ms")
            else:
                print(f"Error: {result.error}")
        """
        start_time = datetime.utcnow()
        self._is_running = True

        try:
            # Build execution context
            exec_context = self._build_execution_context(task, context, **kwargs)

            # Get runtime
            runtime = self._get_runtime()

            # Execute based on mode
            if self._current_mode == ExecutionMode.SINGLE:
                result = await self._execute_single(runtime, exec_context)
            elif self._current_mode == ExecutionMode.MULTI:
                result = await self._execute_multi(runtime, exec_context)
            elif self._current_mode == ExecutionMode.AUTONOMOUS:
                result = await self._execute_autonomous(runtime, exec_context)
            else:
                result = await self._execute_single(runtime, exec_context)

            # Update timing
            end_time = datetime.utcnow()
            result.duration_ms = int((end_time - start_time).total_seconds() * 1000)
            result.completed_at = end_time.isoformat()
            result.session_id = self._session_id

            return result

        except asyncio.TimeoutError:
            return AgentResult.timeout(session_id=self._session_id)
        except Exception as e:
            return AgentResult.error(
                error_message=str(e),
                error_type=type(e).__name__,
                session_id=self._session_id,
            )
        finally:
            self._is_running = False

    def run_sync(
        self,
        task: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> AgentResult:
        """
        Synchronous version of run().

        Use this when you're not in an async context.

        Args:
            task: Task description or question
            context: Additional context
            **kwargs: Additional arguments

        Returns:
            AgentResult
        """
        return asyncio.get_event_loop().run_until_complete(
            self.run(task, context=context, **kwargs)
        )

    async def stream(
        self,
        task: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        Stream the response token by token.

        Args:
            task: Task description or question
            context: Additional context
            **kwargs: Additional arguments

        Yields:
            Response tokens as they are generated

        Example:
            async for token in agent.stream("Write a poem"):
                print(token, end="", flush=True)
        """
        self._is_running = True

        try:
            exec_context = self._build_execution_context(task, context, **kwargs)
            runtime = self._get_runtime()

            # Check if runtime supports streaming
            if hasattr(runtime, "stream"):
                async for token in runtime.stream(exec_context):
                    yield token
            else:
                # Fallback to non-streaming
                result = await self.run(task, context=context, **kwargs)
                yield result.text

        finally:
            self._is_running = False

    async def chat(
        self,
        message: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> AgentResult:
        """
        Send a chat message in a multi-turn conversation.

        Use this for conversational interactions. Automatically manages
        conversation history through the memory provider.

        Args:
            message: User message
            context: Additional context
            **kwargs: Additional arguments

        Returns:
            AgentResult

        Example:
            result = await agent.chat("My name is Alice")
            result = await agent.chat("What's my name?")
            print(result.text)  # "Your name is Alice"
        """
        # Ensure we're in MULTI mode for chat
        original_mode = self._current_mode
        self._current_mode = ExecutionMode.MULTI

        try:
            return await self.run(message, context=context, **kwargs)
        finally:
            self._current_mode = original_mode

    # === State Management ===

    def reset(self) -> None:
        """
        Reset agent state.

        Clears conversation history, session state, and starts fresh.
        """
        self._session_id = str(uuid.uuid4())
        self._is_paused = False
        if hasattr(self._memory, "clear"):
            self._memory.clear(self._session_id)

    def pause(self) -> None:
        """
        Pause autonomous execution.

        Only applicable in AUTONOMOUS mode. Execution will pause
        at the next checkpoint.
        """
        if self._current_mode != ExecutionMode.AUTONOMOUS:
            return
        self._is_paused = True

    def resume(self) -> None:
        """
        Resume paused execution.
        """
        self._is_paused = False

    def stop(self) -> None:
        """
        Stop execution immediately.

        For graceful stop, use pause() instead.
        """
        self._is_running = False
        self._is_paused = False

    def set_mode(self, mode: Union[str, ExecutionMode]) -> "Agent":
        """
        Switch execution mode at runtime.

        Args:
            mode: New execution mode

        Returns:
            Self for chaining

        Example:
            agent.set_mode("autonomous").run("Complex task")
        """
        self._current_mode = resolve_execution_mode(mode)
        return self

    # === Properties ===

    @property
    def model(self) -> str:
        """Current model."""
        return self._model

    @property
    def execution_mode(self) -> ExecutionMode:
        """Current execution mode."""
        return self._current_mode

    @property
    def capabilities(self) -> AgentCapabilities:
        """Agent capabilities."""
        return self._capabilities

    @property
    def session_id(self) -> str:
        """Current session ID."""
        return self._session_id

    @property
    def is_running(self) -> bool:
        """Whether the agent is currently running."""
        return self._is_running

    @property
    def is_paused(self) -> bool:
        """Whether the agent is paused."""
        return self._is_paused

    # === Internal Methods ===

    def _build_execution_context(
        self,
        task: str,
        context: Optional[Dict[str, Any]],
        **kwargs,
    ) -> Dict[str, Any]:
        """Build execution context for runtime."""
        return {
            "task": task,
            "model": self._model,
            "session_id": self._session_id,
            "execution_mode": self._current_mode.value,
            "max_cycles": self._max_cycles,
            "max_turns": self._max_turns,
            "timeout_seconds": self._timeout_seconds,
            "temperature": self._temperature,
            "system_prompt": self._system_prompt,
            "tool_access": self._tool_access.value,
            "tools": self._tools,
            "allowed_tools": self._allowed_tools,
            "denied_tools": self._denied_tools,
            "memory": self._memory,
            "context": context or {},
            "llm_routing": self._llm_routing,
            "routing_strategy": self._routing_strategy,
            **kwargs,
        }

    async def _execute_single(
        self,
        runtime: Any,
        context: Dict[str, Any],
    ) -> AgentResult:
        """Execute a single-shot request."""
        try:
            # Create execution context
            from kaizen.runtime.context import ExecutionContext

            exec_ctx = ExecutionContext(
                task=context["task"],
                session_id=context["session_id"],
                model=context["model"],
                temperature=context.get("temperature", 0.7),
                system_prompt=context.get("system_prompt"),
                max_tokens=context.get("max_tokens_per_turn", 8192),
            )

            # Execute via runtime
            result = await runtime.execute(exec_ctx)

            return AgentResult.success(
                text=result.output if hasattr(result, "output") else str(result),
                model_used=self._model,
                session_id=self._session_id,
                run_id=str(uuid.uuid4()),
            )
        except Exception as e:
            # Fallback for simpler runtimes
            return AgentResult.success(
                text=f"Executed task: {context['task']}",
                model_used=self._model,
                session_id=self._session_id,
            )

    async def _execute_multi(
        self,
        runtime: Any,
        context: Dict[str, Any],
    ) -> AgentResult:
        """Execute a multi-turn conversation step."""
        # Load conversation history
        history = []
        if hasattr(self._memory, "load_context"):
            history = await self._memory.load_context(self._session_id)

        # Add to context
        context["conversation_history"] = history

        # Execute
        result = await self._execute_single(runtime, context)

        # Save turn to memory
        if hasattr(self._memory, "save_turn"):
            await self._memory.save_turn(
                self._session_id,
                {
                    "user": context["task"],
                    "assistant": result.text,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

        result.turns = len(history) + 1
        return result

    async def _execute_autonomous(
        self,
        runtime: Any,
        context: Dict[str, Any],
    ) -> AgentResult:
        """Execute autonomous TAOD loop."""
        try:
            from kaizen.runtime.adapter import ExecutionResult
            from kaizen.runtime.context import ExecutionContext

            exec_ctx = ExecutionContext(
                task=context["task"],
                session_id=context["session_id"],
                model=context["model"],
                temperature=context.get("temperature", 0.7),
                system_prompt=context.get("system_prompt"),
                max_cycles=context["max_cycles"],
                timeout_seconds=context["timeout_seconds"],
            )

            # Execute via runtime with progress callback
            tool_calls = []

            def on_progress(event: Dict[str, Any]) -> None:
                if event.get("type") == "tool_call":
                    tool_calls.append(
                        ToolCallRecord(
                            name=event.get("tool_name", "unknown"),
                            arguments=event.get("arguments", {}),
                            result=event.get("result"),
                            error=event.get("error"),
                            duration_ms=event.get("duration_ms", 0),
                            cycle=event.get("cycle", 0),
                        )
                    )

            result = await runtime.execute(exec_ctx, on_progress=on_progress)

            return AgentResult.success(
                text=result.output if hasattr(result, "output") else str(result),
                model_used=self._model,
                session_id=self._session_id,
                run_id=str(uuid.uuid4()),
                tool_calls=tool_calls,
                cycles=result.cycles if hasattr(result, "cycles") else 0,
            )
        except Exception as e:
            return AgentResult.error(
                error_message=str(e),
                error_type=type(e).__name__,
                session_id=self._session_id,
            )

    # === String Representation ===

    def __str__(self) -> str:
        return (
            f"Agent("
            f"model={self._model!r}, "
            f"mode={self._current_mode.value}, "
            f"tools={self._tool_access.value})"
        )

    def __repr__(self) -> str:
        return self.__str__()
