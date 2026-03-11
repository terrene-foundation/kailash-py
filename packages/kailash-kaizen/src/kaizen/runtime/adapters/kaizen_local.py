"""
LocalKaizenAdapter - Native Autonomous Agent Implementation

Implements Kaizen's native autonomous agent runtime that provides
Claude Code-like capabilities while working with ANY LLM provider.

This is the core autonomous execution engine implementing the
Think-Act-Observe-Decide (TAOD) loop with full state management,
checkpointing, and integration with Kaizen's existing infrastructure.

Supports the Specialist System (ADR-013) for user-defined specialists,
skills, and context files loaded from .kaizen/ directories.

Example:
    >>> from kaizen.runtime.adapters import LocalKaizenAdapter
    >>> from kaizen.runtime import ExecutionContext
    >>> from kaizen.core import KaizenOptions
    >>>
    >>> # Basic usage
    >>> adapter = LocalKaizenAdapter()
    >>> context = ExecutionContext(task="List files in /tmp")
    >>> result = await adapter.execute(context)
    >>>
    >>> # With Specialist System
    >>> options = KaizenOptions(setting_sources=["project"])
    >>> adapter = LocalKaizenAdapter(kaizen_options=options)
    >>> specialists = adapter.list_specialists()
"""

import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from kaizen.core.kaizen_options import KaizenOptions
from kaizen.core.specialist_types import (
    ContextFile,
    SkillDefinition,
    SpecialistDefinition,
)
from kaizen.runtime.adapter import BaseRuntimeAdapter, ProgressCallback
from kaizen.runtime.adapters.types import (
    AutonomousConfig,
    AutonomousPhase,
    ExecutionState,
    PermissionMode,
    PlanningStrategy,
)
from kaizen.runtime.capabilities import KAIZEN_LOCAL_CAPABILITIES, RuntimeCapabilities
from kaizen.runtime.context import ExecutionContext, ExecutionResult, ExecutionStatus
from kaizen.runtime.specialist_loader import SpecialistLoader
from kaizen.runtime.specialist_registry import SkillRegistry, SpecialistRegistry

logger = logging.getLogger(__name__)


class LocalKaizenAdapter(BaseRuntimeAdapter):
    """Native autonomous agent adapter for Kaizen.

    Implements the RuntimeAdapter interface to provide a fully-featured
    autonomous agent that:
    - Works with any LLM provider (OpenAI, Anthropic, Ollama, etc.)
    - Implements Think-Act-Observe-Decide loop
    - Supports checkpointing and resume via StateManager
    - Fires hooks at execution boundaries via HookManager
    - Handles graceful interruption via InterruptManager
    - Uses native Kaizen tools via KaizenToolRegistry

    The adapter can be used standalone or through the RuntimeSelector
    for automatic runtime selection based on task requirements.

    Example:
        >>> adapter = LocalKaizenAdapter(
        ...     config=AutonomousConfig(
        ...         model="gpt-4o",
        ...         max_cycles=100,
        ...         planning_strategy=PlanningStrategy.PEV,
        ...     )
        ... )
        >>>
        >>> context = ExecutionContext(task="Analyze the codebase")
        >>> result = await adapter.execute(context)
    """

    def __init__(
        self,
        config: Optional[AutonomousConfig] = None,
        state_manager: Optional[Any] = None,
        hook_manager: Optional[Any] = None,
        interrupt_manager: Optional[Any] = None,
        tool_registry: Optional[Any] = None,
        llm_provider: Optional[Any] = None,
        kaizen_options: Optional[KaizenOptions] = None,
    ):
        """Initialize the LocalKaizenAdapter.

        Args:
            config: Configuration for autonomous execution.
                    Uses defaults if not provided.
            state_manager: StateManager instance for checkpointing.
                          Creates default if not provided.
            hook_manager: HookManager instance for event hooks.
                         Creates default if not provided.
            interrupt_manager: InterruptManager for handling interrupts.
                              Creates default if not provided.
            tool_registry: KaizenToolRegistry with available tools.
                          Creates default with standard tools if not provided.
            llm_provider: LLM provider instance for calling models.
                         Auto-detects based on config if not provided.
            kaizen_options: KaizenOptions for specialist system configuration.
                           Enables loading specialists, skills, and context
                           from .kaizen/ directories.
        """
        super().__init__()

        # Configuration
        self.config = config or AutonomousConfig()

        # Specialist System (ADR-013)
        self._kaizen_options = kaizen_options
        self._specialist_registry: Optional[SpecialistRegistry] = None
        self._skill_registry: Optional[SkillRegistry] = None
        self._context_file: Optional[ContextFile] = None
        self._specialist_loader: Optional[SpecialistLoader] = None

        # Load specialists if options provided
        if kaizen_options is not None:
            self._load_specialist_system()

        # Infrastructure dependencies (lazily initialized)
        self._state_manager = state_manager
        self._hook_manager = hook_manager
        self._interrupt_manager = interrupt_manager
        self._tool_registry = tool_registry
        self._llm_provider = llm_provider

        # Execution state
        self._current_state: Optional[ExecutionState] = None
        self._on_progress: Optional[ProgressCallback] = None

        # For specialist-specific adapters
        self._available_tools: Optional[List[str]] = None
        self._specialist_system_prompt: Optional[str] = None

        # Capabilities (cached)
        self._capabilities = self._build_capabilities()

    # -------------------------------------------------------------------------
    # Specialist System (ADR-013)
    # -------------------------------------------------------------------------

    def _load_specialist_system(self) -> None:
        """Load specialists, skills, and context from KaizenOptions.

        Called during initialization when kaizen_options is provided.
        """
        if self._kaizen_options is None:
            return

        self._specialist_loader = SpecialistLoader(self._kaizen_options)

        # Load all resources
        specialists, skills, context = self._specialist_loader.load_all()

        self._specialist_registry = specialists
        self._skill_registry = skills
        self._context_file = context

        logger.debug(
            f"Loaded {len(specialists)} specialists, "
            f"{len(skills)} skills, "
            f"context: {context is not None}"
        )

    @property
    def kaizen_options(self) -> Optional[KaizenOptions]:
        """Get the KaizenOptions used for this adapter."""
        return self._kaizen_options

    @property
    def specialist_registry(self) -> Optional[SpecialistRegistry]:
        """Get the specialist registry.

        Returns:
            SpecialistRegistry if kaizen_options was provided, None otherwise.
        """
        return self._specialist_registry

    @property
    def skill_registry(self) -> Optional[SkillRegistry]:
        """Get the skill registry.

        Returns:
            SkillRegistry if kaizen_options was provided, None otherwise.
        """
        return self._skill_registry

    @property
    def context_file(self) -> Optional[ContextFile]:
        """Get the loaded context file (e.g., KAIZEN.md).

        Returns:
            ContextFile if found and loaded, None otherwise.
        """
        return self._context_file

    @property
    def available_tools(self) -> Optional[List[str]]:
        """Get available tools, may be limited by specialist config."""
        return self._available_tools

    @property
    def effective_budget_limit(self) -> Optional[float]:
        """Get the effective budget limit.

        Config budget takes precedence over KaizenOptions budget.
        """
        if self.config.budget_limit_usd is not None:
            return self.config.budget_limit_usd
        if self._kaizen_options is not None:
            return self._kaizen_options.budget_limit_usd
        return None

    @property
    def working_directory(self) -> Path:
        """Get the working directory for this adapter.

        Returns KaizenOptions.cwd if set, otherwise current directory.
        """
        if self._kaizen_options is not None and self._kaizen_options.cwd is not None:
            return Path(self._kaizen_options.cwd)
        return Path.cwd()

    def get_specialist(self, name: str) -> Optional[SpecialistDefinition]:
        """Get a specialist by name.

        Args:
            name: Specialist name (filename without .md)

        Returns:
            SpecialistDefinition if found, None otherwise.
        """
        if self._specialist_registry is None:
            return None
        return self._specialist_registry.get(name)

    def list_specialists(self) -> List[str]:
        """List all available specialist names.

        Returns:
            List of specialist names.
        """
        if self._specialist_registry is None:
            return []
        return self._specialist_registry.list()

    def get_skill(self, name: str) -> Optional[SkillDefinition]:
        """Get a skill by name.

        Args:
            name: Skill name (directory name or from frontmatter)

        Returns:
            SkillDefinition if found, None otherwise.
        """
        if self._skill_registry is None:
            return None
        return self._skill_registry.get(name)

    def list_skills(self) -> List[str]:
        """List all available skill names.

        Returns:
            List of skill names.
        """
        if self._skill_registry is None:
            return []
        return self._skill_registry.list()

    def load_skill_content(self, skill: SkillDefinition) -> SkillDefinition:
        """Load full content for a skill (progressive disclosure).

        Args:
            skill: SkillDefinition with location set

        Returns:
            Updated SkillDefinition with content loaded.
        """
        if self._specialist_loader is None:
            return skill
        return self._specialist_loader.load_skill_content(skill)

    def get_context_prompt_section(self) -> Optional[str]:
        """Get context file content formatted for system prompt.

        Returns:
            Formatted context section, or None if no context loaded.
        """
        if self._context_file is None:
            return None

        return f"""## Project Context
{self._context_file.content}
"""

    def for_specialist(self, name: str) -> Optional["LocalKaizenAdapter"]:
        """Create a new adapter configured for a specific specialist.

        The returned adapter inherits registries but uses specialist-specific:
        - System prompt
        - Model and temperature
        - Available tools

        Args:
            name: Specialist name to configure for

        Returns:
            Configured LocalKaizenAdapter, or None if specialist not found.
        """
        specialist = self.get_specialist(name)
        if specialist is None:
            return None

        # Create config from specialist
        new_config = AutonomousConfig(
            model=specialist.model or self.config.model,
            temperature=specialist.temperature or self.config.temperature,
            max_cycles=self.config.max_cycles,
            budget_limit_usd=self.effective_budget_limit,
            planning_strategy=self.config.planning_strategy,
            permission_mode=self.config.permission_mode,
        )

        # Create new adapter with shared registries
        new_adapter = LocalKaizenAdapter(
            config=new_config,
            kaizen_options=self._kaizen_options,
            state_manager=self._state_manager,
            hook_manager=self._hook_manager,
            interrupt_manager=self._interrupt_manager,
            tool_registry=self._tool_registry,
            llm_provider=self._llm_provider,
        )

        # Share registries (don't reload)
        new_adapter._specialist_registry = self._specialist_registry
        new_adapter._skill_registry = self._skill_registry
        new_adapter._context_file = self._context_file
        new_adapter._specialist_loader = self._specialist_loader

        # Set specialist-specific config
        new_adapter._available_tools = specialist.available_tools
        new_adapter._specialist_system_prompt = specialist.system_prompt

        return new_adapter

    @property
    def capabilities(self) -> RuntimeCapabilities:
        """Return the capabilities of this runtime.

        LocalKaizenAdapter supports:
        - Tool calling with any LLM
        - File access via native tools
        - Code execution via bash tool
        - Streaming output
        - Interrupt handling
        - Vision (if LLM supports it)

        Returns:
            RuntimeCapabilities describing this runtime's features
        """
        return self._capabilities

    @property
    def state_manager(self) -> Optional[Any]:
        """Get state manager, creating default if needed."""
        return self._state_manager

    @property
    def hook_manager(self) -> Optional[Any]:
        """Get hook manager, creating default if needed."""
        return self._hook_manager

    @property
    def interrupt_manager(self) -> Optional[Any]:
        """Get interrupt manager, creating default if needed."""
        return self._interrupt_manager

    @property
    def tool_registry(self) -> Optional[Any]:
        """Get tool registry, creating default if needed."""
        return self._tool_registry

    def _build_capabilities(self) -> RuntimeCapabilities:
        """Build capabilities based on configuration.

        Returns:
            RuntimeCapabilities for this adapter
        """
        # Start with pre-defined Kaizen local capabilities
        base_caps = KAIZEN_LOCAL_CAPABILITIES

        # Customize based on config
        return RuntimeCapabilities(
            runtime_name="kaizen_local",
            provider="kaizen",
            version=base_caps.version,
            supports_streaming=True,
            supports_tool_calling=True,
            supports_parallel_tools=False,  # Execute tools sequentially for safety
            supports_vision=True,  # Depends on LLM, but we support it
            supports_audio=False,  # Not yet supported
            supports_code_execution=True,
            supports_file_access=True,
            supports_web_access=True,
            supports_interrupt=True,
            max_context_tokens=base_caps.max_context_tokens,
            max_output_tokens=base_caps.max_output_tokens,
            cost_per_1k_input_tokens=None,  # Varies by LLM provider
            cost_per_1k_output_tokens=None,
            typical_latency_ms=base_caps.typical_latency_ms,
            native_tools=base_caps.native_tools,
            supported_models=[],  # Supports any model via provider abstraction
            metadata={
                "planning_strategy": self.config.planning_strategy.value,
                "permission_mode": self.config.permission_mode.value,
            },
        )

    async def execute(
        self,
        context: ExecutionContext,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExecutionResult:
        """Execute a task using the TAOD loop.

        This is the main entry point for autonomous task execution.
        The method:
        1. Initializes execution state
        2. Fires execution_start hook
        3. Runs the Think-Act-Observe-Decide loop
        4. Handles checkpointing, hooks, and interrupts
        5. Fires execution_complete hook
        6. Returns normalized ExecutionResult

        Args:
            context: Normalized execution context with task and tools
            on_progress: Optional callback for progress updates

        Returns:
            ExecutionResult with output, status, and metrics
        """
        await self.ensure_initialized()

        # Initialize execution state
        self._current_state = ExecutionState(
            task=context.task,
            session_id=context.session_id,
        )
        self._on_progress = on_progress

        # Add initial user message
        self._current_state.add_message(
            {
                "role": "user",
                "content": context.task,
            }
        )

        logger.info(
            f"Starting execution for task: {context.task[:50]}..., "
            f"session_id: {self._current_state.session_id}"
        )

        # Fire execution_start hook
        await self._fire_hook(
            "execution_start",
            {
                "task": context.task,
                "session_id": self._current_state.session_id,
            },
        )

        try:
            # Create plan if using PEV strategy
            if self.config.planning_strategy == PlanningStrategy.PEV:
                await self._create_plan(self._current_state)

            # Run TAOD loop
            await self._run_taod_loop()

            # Fire execution_complete hook
            await self._fire_hook(
                "execution_complete",
                {
                    "task": context.task,
                    "session_id": self._current_state.session_id,
                    "cycles": self._current_state.current_cycle,
                    "status": self._current_state.status,
                },
            )

            return self.normalize_result(self._current_state)

        except Exception as e:
            logger.exception(f"Execution error: {e}")
            self._current_state.fail(error=str(e))

            # Fire execution_error hook
            await self._fire_hook(
                "execution_error",
                {
                    "task": context.task,
                    "session_id": self._current_state.session_id,
                    "error": str(e),
                },
            )

            return self.normalize_result(self._current_state)

        finally:
            self._current_state = None
            self._on_progress = None

    async def _run_taod_loop(self) -> None:
        """Run the Think-Act-Observe-Decide loop.

        Continues until:
        - LLM returns no tool calls (task complete)
        - Max cycles reached
        - Budget exceeded
        - Interrupted
        - Error occurs
        """
        state = self._current_state

        while not self._should_stop(state):
            state.advance_cycle()

            logger.debug(f"TAOD cycle {state.current_cycle}")

            # Fire cycle_start hook
            await self._fire_hook(
                "cycle_start",
                {
                    "cycle": state.current_cycle,
                    "session_id": state.session_id,
                },
            )

            # THINK: Call LLM to decide next action
            state.set_phase(AutonomousPhase.THINK)
            await self._think_phase(state)

            if self._should_stop(state):
                break

            # Check for checkpoint at cycle boundary
            await self._maybe_checkpoint(state)

            # DECIDE: Check if we should stop (no tool calls = done)
            state.set_phase(AutonomousPhase.DECIDE)
            should_stop = await self._decide_phase(state)
            if should_stop:
                break

            # ACT: Execute pending tool calls
            state.set_phase(AutonomousPhase.ACT)
            await self._act_phase(state)

            if self._should_stop(state):
                break

            # OBSERVE: Process tool results
            state.set_phase(AutonomousPhase.OBSERVE)
            await self._observe_phase(state)

        # Finalize result if not already set
        if not state.is_complete:
            # Get final output from last assistant message
            final_output = self._extract_final_output(state)
            state.complete(result=final_output)

    def _build_system_prompt(self, state: ExecutionState) -> str:
        """Build strategy-specific system prompt.

        Generates a system prompt that sets up the agent's persona, capabilities,
        and planning strategy. The prompt varies based on:
        - Specialist system prompt (if configured via for_specialist)
        - Project context (from KAIZEN.md)
        - Planning strategy (ReAct, PEV, Tree-of-Thoughts)
        - Permission mode (auto, confirm_all, etc.)
        - Current cycle and progress

        Args:
            state: Current execution state

        Returns:
            System prompt string
        """
        # Use specialist-specific prompt if available
        if self._specialist_system_prompt:
            base_prompt = self._specialist_system_prompt + "\n\n"
        else:
            # Base autonomous agent prompt
            base_prompt = """You are an autonomous AI agent capable of executing complex tasks.
You have access to tools that allow you to interact with the environment.
"""

        # Add project context if available
        context_prompt = self.get_context_prompt_section()
        if context_prompt:
            base_prompt += "\n" + context_prompt

        # Strategy-specific instructions
        strategy = self.config.planning_strategy
        if strategy == PlanningStrategy.REACT:
            strategy_prompt = """
## Reasoning Strategy: ReAct (Reason + Act)

Think step-by-step before each action:
1. **Thought**: Reason about the current situation and what to do next
2. **Action**: Choose a tool to execute based on your reasoning
3. **Observation**: Observe the result and reason about it

Always explain your thinking before taking action. Break complex tasks into smaller steps.
"""
        elif strategy == PlanningStrategy.PEV:
            strategy_prompt = """
## Reasoning Strategy: Plan-Execute-Verify

Follow this cycle for each major task:
1. **Plan**: Create a clear plan with specific steps to accomplish the goal
2. **Execute**: Execute each step of the plan using available tools
3. **Verify**: Check if the step was successful and the plan is on track

Before acting, create or reference your plan. After acting, verify results match expectations.
"""
            # Add plan context if available
            if state.plan:
                completed_steps = state.plan[: state.plan_index]
                current_step = (
                    state.plan[state.plan_index]
                    if state.plan_index < len(state.plan)
                    else None
                )
                remaining_steps = (
                    state.plan[state.plan_index + 1 :]
                    if state.plan_index < len(state.plan)
                    else []
                )

                strategy_prompt += f"""
### Current Plan Status:
- Completed steps: {len(completed_steps)}
- Current step: {current_step or "None - create a new plan"}
- Remaining steps: {len(remaining_steps)}
"""
        else:  # TREE_OF_THOUGHTS
            strategy_prompt = """
## Reasoning Strategy: Tree-of-Thoughts

Explore multiple reasoning paths before acting:
1. **Generate**: Think of several possible approaches to the problem
2. **Evaluate**: Assess each approach for feasibility and effectiveness
3. **Select**: Choose the best path forward based on your evaluation
4. **Execute**: Act on the selected approach

Consider multiple perspectives and alternative solutions before committing to an action.
"""

        # Permission mode context
        permission_mode = self.config.permission_mode
        if permission_mode == PermissionMode.CONFIRM_ALL:
            permission_prompt = """
## Permission Mode: Confirm All
All tool executions require user approval. Explain what you plan to do and why.
"""
        elif permission_mode == PermissionMode.CONFIRM_DANGEROUS:
            permission_prompt = """
## Permission Mode: Confirm Dangerous
Dangerous operations (file writes, command execution) require user approval.
Safe operations (file reads, searches) can proceed automatically.
"""
        elif permission_mode == PermissionMode.DENY_ALL:
            permission_prompt = """
## Permission Mode: Read-Only
You cannot execute any tools. Provide analysis and recommendations only.
"""
        else:  # AUTO
            permission_prompt = """
## Permission Mode: Autonomous
You can execute tools automatically. Use good judgment about safety.
"""

        # Cycle information
        cycle_prompt = f"""
## Execution Status
- Current cycle: {state.current_cycle} of {self.config.max_cycles} maximum
- Tokens used: {state.tokens_used}
"""
        if self.config.budget_limit_usd:
            cycle_prompt += f"- Budget: ${state.cost_usd:.4f} of ${self.config.budget_limit_usd} limit\n"

        # Memory context
        memory_context = self._format_memory_context(state)
        if memory_context:
            memory_prompt = f"""
## Memory Context
{memory_context}
"""
        else:
            memory_prompt = ""

        return (
            base_prompt
            + strategy_prompt
            + permission_prompt
            + cycle_prompt
            + memory_prompt
        )

    def _format_memory_context(self, state: ExecutionState) -> str:
        """Format working memory and learned patterns for context.

        Serializes the current working memory and any learned patterns
        into a string suitable for inclusion in the system prompt.

        Args:
            state: Current execution state

        Returns:
            Formatted memory context string (may be empty)
        """
        parts = []

        # Format working memory (excluding internal keys)
        if state.working_memory:
            internal_keys = {"last_response_content"}
            user_memory = {
                k: v for k, v in state.working_memory.items() if k not in internal_keys
            }
            if user_memory:
                try:
                    # Truncate very long values
                    truncated_memory = {}
                    for k, v in user_memory.items():
                        str_v = str(v) if v is not None else "null"
                        if len(str_v) > 1000:
                            truncated_memory[k] = str_v[:1000] + "... (truncated)"
                        else:
                            truncated_memory[k] = v

                    memory_str = json.dumps(truncated_memory, indent=2, default=str)
                    # Truncate entire memory if too long
                    if len(memory_str) > 5000:
                        memory_str = memory_str[:5000] + "\n... (memory truncated)"
                    parts.append(f"### Working Memory\n```json\n{memory_str}\n```")
                except (TypeError, ValueError):
                    # Fallback to string representation
                    memory_str = str(user_memory)[:5000]
                    parts.append(f"### Working Memory\n{memory_str}")

        # Format learned patterns
        if state.learned_patterns:
            patterns_str = "\n".join(f"- {p}" for p in state.learned_patterns[:20])
            if len(state.learned_patterns) > 20:
                patterns_str += (
                    f"\n... and {len(state.learned_patterns) - 20} more patterns"
                )
            parts.append(f"### Learned Patterns\n{patterns_str}")

        result = "\n\n".join(parts)

        # Final truncation safeguard
        if len(result) > 10000:
            result = result[:10000] + "\n... (context truncated)"

        return result

    def _build_thinking_context(self, state: ExecutionState) -> Dict[str, Any]:
        """Build complete context for LLM thinking phase.

        Combines system prompt, messages, tools, and model configuration
        into a dictionary ready for the LLM provider.

        Args:
            state: Current execution state

        Returns:
            Dictionary with messages, model, temperature, and optionally tools
        """
        # Build system prompt
        system_prompt = self._build_system_prompt(state)

        # Construct messages with system prompt first
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(state.messages)

        # Get tools if available
        tools = []
        if self._tool_registry and hasattr(self._tool_registry, "get_tool_schemas"):
            tools = self._tool_registry.get_tool_schemas()

        context = {
            "messages": messages,
            "model": self.config.model,
            "temperature": self.config.temperature,
        }

        if tools:
            context["tools"] = tools

        return context

    async def _think_phase(self, state: ExecutionState) -> None:
        """THINK phase: Call LLM with context and tools.

        Builds context from state, calls LLM, extracts any tool calls.

        Args:
            state: Current execution state
        """
        logger.debug("THINK phase: Calling LLM")

        if self._on_progress:
            self._on_progress("thinking", {"cycle": state.current_cycle})

        # Check if we have an LLM provider
        if not self._llm_provider:
            logger.warning("No LLM provider configured, completing task")
            state.complete(result="No LLM provider configured")
            return

        try:
            # Build thinking context with system prompt and tools
            context = self._build_thinking_context(state)

            # Call LLM with built context
            response = await self._llm_provider.chat_async(
                messages=context["messages"],
                model=context["model"],
                temperature=context["temperature"],
                tools=context.get("tools"),
            )

            # Update token usage and cost
            if "usage" in response:
                usage = response["usage"]
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", input_tokens + output_tokens)
                cost = self._calculate_cost(input_tokens, output_tokens)
                state.update_budget(tokens=total_tokens, cost=cost)

            # Extract content
            content = response.get("content")
            tool_calls = response.get("tool_calls")

            # Store last response content
            state.working_memory["last_response_content"] = content

            # Add assistant message to history
            assistant_msg = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            state.add_message(assistant_msg)

            # Extract tool calls if present
            if tool_calls:
                for tc in tool_calls:
                    try:
                        tool_call = self._parse_tool_call(tc)
                        if tool_call:
                            state.add_tool_call(tool_call)
                    except Exception as e:
                        logger.warning(f"Failed to parse tool call: {e}")

            if self._on_progress:
                self._on_progress(
                    "thought",
                    {
                        "content": content,
                        "tool_calls_count": len(state.pending_tool_calls),
                    },
                )

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            state.fail(error=f"LLM call failed: {e}")

    def _parse_tool_call(self, tc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a tool call from LLM response.

        Args:
            tc: Raw tool call from LLM

        Returns:
            Parsed tool call dict or None if invalid
        """
        # Handle OpenAI format
        if "function" in tc:
            func = tc["function"]
            args_str = func.get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                args = {}

            return {
                "id": tc.get("id", ""),
                "name": func.get("name", ""),
                "arguments": args,
            }

        # Handle simplified format
        if "name" in tc:
            return {
                "id": tc.get("id", ""),
                "name": tc["name"],
                "arguments": tc.get("arguments", {}),
            }

        return None

    async def _act_phase(self, state: ExecutionState) -> None:
        """ACT phase: Execute pending tool calls.

        Executes each tool call sequentially and records results.

        Args:
            state: Current execution state
        """
        logger.debug(f"ACT phase: {len(state.pending_tool_calls)} tools to execute")

        if not state.pending_tool_calls:
            return

        if not self._tool_registry:
            logger.warning("No tool registry, skipping tool execution")
            state.clear_pending_tool_calls()
            return

        for tool_call in state.pending_tool_calls[:]:  # Copy to avoid mutation issues
            tool_name = tool_call.get("name", "")
            tool_args = tool_call.get("arguments", {})
            tool_id = tool_call.get("id", "")

            # Fire tool_start hook
            await self._fire_hook(
                "tool_start",
                {
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "tool_id": tool_id,
                    "session_id": state.session_id,
                },
            )

            if self._on_progress:
                self._on_progress(
                    "tool_call",
                    {
                        "tool": tool_name,
                        "args": tool_args,
                    },
                )

            try:
                # Execute tool
                result = await self._tool_registry.execute(tool_name, tool_args)

                # Record result
                if hasattr(result, "success"):
                    output = result.output if result.success else result.error
                    success = result.success
                else:
                    output = str(result)
                    success = True

                state.add_tool_result(
                    {
                        "tool_call_id": tool_id,
                        "tool_name": tool_name,
                        "output": output,
                        "success": success,
                    }
                )

                # Fire tool_complete hook
                await self._fire_hook(
                    "tool_complete",
                    {
                        "tool_name": tool_name,
                        "tool_id": tool_id,
                        "success": success,
                        "session_id": state.session_id,
                    },
                )

                if self._on_progress:
                    self._on_progress(
                        "tool_result",
                        {
                            "tool": tool_name,
                            "success": success,
                            "output": str(output)[:200],
                        },
                    )

            except Exception as e:
                logger.error(f"Tool {tool_name} failed: {e}")
                state.add_tool_result(
                    {
                        "tool_call_id": tool_id,
                        "tool_name": tool_name,
                        "output": f"Error: {e}",
                        "success": False,
                    }
                )

                # Fire tool_error hook
                await self._fire_hook(
                    "tool_error",
                    {
                        "tool_name": tool_name,
                        "tool_id": tool_id,
                        "error": str(e),
                        "session_id": state.session_id,
                    },
                )

        # Clear pending after processing all
        state.clear_pending_tool_calls()

    async def _observe_phase(self, state: ExecutionState) -> None:
        """OBSERVE phase: Process tool results and add to conversation.

        Formats tool results and adds them to message history.

        Args:
            state: Current execution state
        """
        logger.debug(f"OBSERVE phase: {len(state.tool_results)} results to process")

        if not state.tool_results:
            return

        # Add tool results to message history
        for result in state.tool_results:
            output = result.get("output", "")

            # Safely serialize output
            try:
                content = json.dumps(output) if not isinstance(output, str) else output
            except (TypeError, ValueError):
                content = str(output)

            tool_msg = {
                "role": "tool",
                "tool_call_id": result.get("tool_call_id", ""),
                "content": content,
            }
            state.add_message(tool_msg)

        # Clear processed results
        state.tool_results = []

    async def _decide_phase(self, state: ExecutionState) -> bool:
        """DECIDE phase: Determine if we should stop.

        Checks completion conditions:
        - No pending tool calls (LLM is done)
        - Max cycles reached
        - Budget exceeded
        - Interrupted

        Args:
            state: Current execution state

        Returns:
            True if we should stop, False to continue
        """
        logger.debug("DECIDE phase: Checking stop conditions")

        # No pending tools = LLM is done
        if not state.pending_tool_calls:
            logger.debug("No pending tool calls, task complete")
            return True

        # Check max cycles
        if state.current_cycle >= self.config.max_cycles:
            logger.info(f"Max cycles ({self.config.max_cycles}) reached")
            state.status = "max_cycles"
            return True

        # Check budget
        if (
            self.config.budget_limit_usd
            and state.cost_usd > self.config.budget_limit_usd
        ):
            logger.info(f"Budget ({self.config.budget_limit_usd}) exceeded")
            state.status = "budget_exceeded"
            return True

        # Check interrupt
        if self._interrupt_manager and hasattr(
            self._interrupt_manager, "is_interrupted"
        ):
            if self._interrupt_manager.is_interrupted():
                logger.info("Interrupted by user")
                state.interrupt()

                # Fire interrupt hook
                await self._fire_hook(
                    "interrupt",
                    {
                        "session_id": state.session_id,
                        "cycle": state.current_cycle,
                        "reason": "user_interrupt",
                    },
                )

                # Checkpoint on interrupt if configured
                if self.config.checkpoint_on_interrupt:
                    await self._create_checkpoint(state, force=True)

                return True

        return False

    def _should_stop(self, state: ExecutionState) -> bool:
        """Check if execution should stop.

        Args:
            state: Current execution state

        Returns:
            True if we should stop
        """
        # Already complete
        if state.is_complete:
            return True

        # Max cycles
        if state.current_cycle >= self.config.max_cycles:
            return True

        # Budget exceeded
        if (
            self.config.budget_limit_usd
            and state.cost_usd > self.config.budget_limit_usd
        ):
            return True

        return False

    def _extract_final_output(self, state: ExecutionState) -> str:
        """Extract final output from state.

        Gets the last assistant message content or a summary.

        Args:
            state: Current execution state

        Returns:
            Final output string
        """
        # Try to get last response content from working memory
        if "last_response_content" in state.working_memory:
            content = state.working_memory["last_response_content"]
            if content:
                return content

        # Find last assistant message with content
        for msg in reversed(state.messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                return msg["content"]

        return f"Task completed after {state.current_cycle} cycles"

    async def stream(
        self,
        context: ExecutionContext,
    ) -> AsyncIterator[str]:
        """Stream execution output as it's generated.

        For LocalKaizenAdapter, streaming is implemented by:
        1. Setting up a progress callback that yields content
        2. Yielding thought content as LLM generates it
        3. Yielding tool execution status updates
        4. Yielding final output

        Args:
            context: Normalized execution context

        Yields:
            Output chunks as they're generated
        """
        if not self.capabilities.supports_streaming:
            raise NotImplementedError(
                f"{self.capabilities.runtime_name} does not support streaming"
            )

        import asyncio

        # Use a queue to collect streaming chunks
        chunk_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

        async def progress_callback(event: str, data: Dict[str, Any]) -> None:
            """Callback to capture progress and add to stream."""
            if event == "thinking":
                await chunk_queue.put(f"[Thinking: cycle {data.get('cycle', '?')}]\n")
            elif event == "thought":
                content = data.get("content")
                if content:
                    await chunk_queue.put(f"{content}\n")
                tool_count = data.get("tool_calls_count", 0)
                if tool_count > 0:
                    await chunk_queue.put(f"[Calling {tool_count} tool(s)...]\n")
            elif event == "tool_call":
                tool = data.get("tool", "unknown")
                await chunk_queue.put(f"[Tool: {tool}]\n")
            elif event == "tool_result":
                tool = data.get("tool", "unknown")
                success = data.get("success", False)
                status = "✓" if success else "✗"
                await chunk_queue.put(f"[{status} {tool} complete]\n")

        # Run execution in background task
        async def run_execution() -> None:
            try:
                await self.execute(context, on_progress=progress_callback)
            finally:
                # Signal end of stream
                await chunk_queue.put(None)

        task = asyncio.create_task(run_execution())

        # Yield chunks as they become available
        try:
            while True:
                chunk = await chunk_queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            # Ensure task completes
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def interrupt(
        self,
        session_id: str,
        mode: str = "graceful",
    ) -> bool:
        """Interrupt an ongoing execution.

        Args:
            session_id: The session to interrupt
            mode: Interrupt mode ("graceful", "immediate", "rollback")

        Returns:
            True if interrupt was successful
        """
        if not self._current_state:
            logger.warning(f"No active session to interrupt: {session_id}")
            return False

        if self._current_state.session_id != session_id:
            logger.warning(
                f"Session ID mismatch: {session_id} != {self._current_state.session_id}"
            )
            return False

        # Request interrupt through interrupt manager if available
        if self._interrupt_manager:
            self._interrupt_manager.request_interrupt(mode=mode)
            return True

        # Fallback: directly mark state as interrupted
        self._current_state.interrupt()
        return True

    def map_tools(
        self,
        kaizen_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Map tools from Kaizen format to runtime format.

        LocalKaizenAdapter uses the same OpenAI function calling format,
        so this is a pass-through operation.

        Args:
            kaizen_tools: Tools in OpenAI function format

        Returns:
            Tools unchanged (same format)
        """
        return kaizen_tools

    def normalize_result(
        self,
        raw_result: Any,
    ) -> ExecutionResult:
        """Normalize result to ExecutionResult.

        Handles various result types:
        - ExecutionResult: pass through
        - ExecutionState: convert to ExecutionResult
        - str: wrap as successful result
        - dict: parse as ExecutionResult fields

        Args:
            raw_result: Raw result from execution

        Returns:
            Normalized ExecutionResult
        """
        # Already an ExecutionResult
        if isinstance(raw_result, ExecutionResult):
            return raw_result

        # ExecutionState from TAOD loop
        if isinstance(raw_result, ExecutionState):
            return self._state_to_result(raw_result)

        # String output
        if isinstance(raw_result, str):
            return ExecutionResult.from_success(
                output=raw_result,
                runtime_name=self.capabilities.runtime_name,
            )

        # Dictionary with result fields
        if isinstance(raw_result, dict):
            if "output" in raw_result:
                return ExecutionResult.from_dict(raw_result)
            return ExecutionResult.from_success(
                output=str(raw_result),
                runtime_name=self.capabilities.runtime_name,
            )

        # Fallback
        return ExecutionResult.from_success(
            output=str(raw_result),
            runtime_name=self.capabilities.runtime_name,
        )

    def _state_to_result(self, state: ExecutionState) -> ExecutionResult:
        """Convert ExecutionState to ExecutionResult.

        Args:
            state: Execution state from TAOD loop

        Returns:
            ExecutionResult with appropriate status
        """
        # Map state status to ExecutionStatus
        status_map = {
            "completed": ExecutionStatus.COMPLETE,
            "error": ExecutionStatus.ERROR,
            "interrupted": ExecutionStatus.INTERRUPTED,
            "running": ExecutionStatus.PENDING,
        }
        status = status_map.get(state.status, ExecutionStatus.ERROR)

        # Build tool call records
        tool_calls = []
        # TODO: Convert state.tool_results to ToolCallRecord in Phase 3

        return ExecutionResult(
            output=state.result or "",
            status=status,
            tokens_used=state.tokens_used,
            cost_usd=state.cost_usd if state.cost_usd > 0 else None,
            cycles_used=state.current_cycle,
            runtime_name=self.capabilities.runtime_name,
            session_id=state.session_id,
            tool_calls=tool_calls,
            error_message=state.error,
            error_type="ExecutionError" if state.error else None,
        )

    def get_current_session_id(self) -> Optional[str]:
        """Get the session ID of the current execution.

        Returns:
            Session ID if executing, None otherwise
        """
        if self._current_state:
            return self._current_state.session_id
        return None

    # -------------------------------------------------------------------------
    # Infrastructure Integration Helpers
    # -------------------------------------------------------------------------

    async def _fire_hook(
        self,
        event_type: str,
        data: Dict[str, Any],
    ) -> None:
        """Fire a hook event if HookManager is available.

        Args:
            event_type: The type of event (e.g., "execution_start")
            data: Data to pass to hook handlers
        """
        if not self._hook_manager:
            return

        try:
            agent_id = data.get("session_id", "")
            await self._hook_manager.trigger(
                event_type=event_type,
                agent_id=agent_id,
                data=data,
            )
        except Exception as e:
            logger.warning(f"Hook {event_type} failed: {e}")

    async def _maybe_checkpoint(self, state: ExecutionState) -> None:
        """Create checkpoint if needed based on frequency.

        Args:
            state: Current execution state
        """
        if not self._state_manager:
            return

        # Check if we should checkpoint based on frequency
        checkpoint_frequency = self.config.checkpoint_frequency
        if state.current_cycle % checkpoint_frequency == 0:
            await self._create_checkpoint(state, force=False)

    async def _create_checkpoint(
        self,
        state: ExecutionState,
        force: bool = False,
    ) -> Optional[str]:
        """Create a checkpoint of current state.

        Args:
            state: Current execution state
            force: Force checkpoint even if not at frequency boundary

        Returns:
            Checkpoint ID if created, None otherwise
        """
        if not self._state_manager:
            return None

        try:
            checkpoint_id = self._state_manager.save_checkpoint(state, force=force)
            logger.debug(f"Created checkpoint: {checkpoint_id}")

            # Fire checkpoint hook
            await self._fire_hook(
                "checkpoint_created",
                {
                    "checkpoint_id": checkpoint_id,
                    "session_id": state.session_id,
                    "cycle": state.current_cycle,
                    "forced": force,
                },
            )

            return checkpoint_id

        except Exception as e:
            logger.error(f"Failed to create checkpoint: {e}")
            return None

    # -------------------------------------------------------------------------
    # Planning Strategy Methods
    # -------------------------------------------------------------------------

    async def _create_plan(self, state: ExecutionState) -> None:
        """Create a plan for PEV strategy.

        Uses the LLM to generate a step-by-step plan for the task.
        The plan is stored in state.plan as a list of steps.

        Args:
            state: Current execution state
        """
        if not self._llm_provider:
            logger.warning("No LLM provider, cannot create plan")
            return

        # Build planning prompt
        planning_prompt = f"""Create a step-by-step plan to accomplish the following task:

Task: {state.task}

Please provide a numbered list of clear, actionable steps. Each step should be specific and achievable.
Format your plan as:
1. First step
2. Second step
3. Third step
etc."""

        try:
            response = await self._llm_provider.chat_async(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a planning assistant. Create clear, actionable plans.",
                    },
                    {"role": "user", "content": planning_prompt},
                ],
                model=self.config.model,
                temperature=0.3,  # Lower temperature for more consistent plans
            )

            # Parse plan from response
            content = response.get("content", "")
            steps = self._parse_plan_from_response(content)

            if steps:
                state.plan = steps
                state.plan_index = 0
                logger.debug(f"Created plan with {len(steps)} steps")
            else:
                # Fallback: treat entire task as single step
                state.plan = [state.task]
                state.plan_index = 0

            # Update token usage
            if "usage" in response:
                usage = response["usage"]
                tokens = usage.get("total_tokens", 0)
                state.update_budget(tokens=tokens, cost=0.0)

        except Exception as e:
            logger.warning(f"Failed to create plan: {e}")
            # Fallback to single step
            state.plan = [state.task]
            state.plan_index = 0

    def _parse_plan_from_response(self, response: str) -> List[str]:
        """Parse plan steps from LLM response.

        Handles various formats:
        - Numbered lists (1. First, 2. Second)
        - Bulleted lists (- First, * Second)
        - Step prefix (Step 1: First)

        Args:
            response: LLM response text

        Returns:
            List of plan steps
        """
        import re

        if not response or not response.strip():
            return []

        steps = []
        lines = response.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Match numbered format: "1. Step" or "1) Step"
            numbered_match = re.match(r"^\d+[\.\)]\s*(.+)$", line)
            if numbered_match:
                steps.append(numbered_match.group(1).strip())
                continue

            # Match bulleted format: "- Step" or "* Step"
            bullet_match = re.match(r"^[-\*]\s*(.+)$", line)
            if bullet_match:
                steps.append(bullet_match.group(1).strip())
                continue

            # Match Step prefix: "Step 1: ..." or "Step 1 - ..."
            step_match = re.match(r"^Step\s*\d+[:\-]\s*(.+)$", line, re.IGNORECASE)
            if step_match:
                steps.append(step_match.group(1).strip())
                continue

        return steps

    def _advance_plan(self, state: ExecutionState) -> None:
        """Advance to the next plan step.

        Increments plan_index if there are more steps.

        Args:
            state: Current execution state
        """
        if state.plan_index < len(state.plan):
            state.plan_index += 1
            state.updated_at = state.updated_at  # Trigger timestamp update

    def _is_plan_complete(self, state: ExecutionState) -> bool:
        """Check if the plan is complete.

        Args:
            state: Current execution state

        Returns:
            True if all plan steps are done
        """
        return state.plan_index >= len(state.plan)

    def _get_current_plan_step(self, state: ExecutionState) -> Optional[str]:
        """Get the current plan step.

        Args:
            state: Current execution state

        Returns:
            Current step text, or None if plan is empty or complete
        """
        if not state.plan:
            return None

        if state.plan_index >= len(state.plan):
            return None

        return state.plan[state.plan_index]

    # -------------------------------------------------------------------------
    # Advanced Features: Cost, Learning, Permissions
    # -------------------------------------------------------------------------

    # Model pricing (per 1M tokens) as of late 2024
    _MODEL_PRICING: Dict[str, Dict[str, float]] = {
        # OpenAI models
        "gpt-4o": {"input": 5.0, "output": 15.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.6},
        "gpt-4-turbo": {"input": 10.0, "output": 30.0},
        "gpt-4": {"input": 30.0, "output": 60.0},
        "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
        # Anthropic models
        "claude-3-opus": {"input": 15.0, "output": 75.0},
        "claude-3-sonnet": {"input": 3.0, "output": 15.0},
        "claude-3-haiku": {"input": 0.25, "output": 1.25},
        "claude-3-5-sonnet": {"input": 3.0, "output": 15.0},
        # Default for unknown models
        "default": {"input": 5.0, "output": 15.0},
    }

    def _calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Calculate cost for token usage.

        Args:
            input_tokens: Number of input/prompt tokens
            output_tokens: Number of output/completion tokens

        Returns:
            Estimated cost in USD
        """
        if input_tokens == 0 and output_tokens == 0:
            return 0.0

        model = self.config.model
        pricing = self._MODEL_PRICING.get(model, self._MODEL_PRICING["default"])

        # Calculate cost (pricing is per 1M tokens)
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return input_cost + output_cost

    def _learn_pattern(self, state: ExecutionState, pattern: str) -> None:
        """Add a learned pattern to state.

        Args:
            state: Current execution state
            pattern: Pattern to learn
        """
        # Prevent duplicates
        if pattern in state.learned_patterns:
            return

        # Respect limit (50 patterns max)
        if len(state.learned_patterns) >= 50:
            # Remove oldest pattern
            state.learned_patterns.pop(0)

        state.learned_patterns.append(pattern)

    def _extract_patterns(self, state: ExecutionState) -> List[str]:
        """Extract patterns from execution.

        Analyzes the execution to identify useful patterns
        that could help in future tasks.

        Args:
            state: Current execution state

        Returns:
            List of extracted patterns
        """
        patterns = []

        # Analyze tool results for patterns
        for result in state.tool_results:
            tool_name = result.get("tool_name", "")
            success = result.get("success", False)
            output = result.get("output", "")

            if not success and "not found" in str(output).lower():
                patterns.append(f"Check if resource exists before using {tool_name}")
            elif success and tool_name == "read_file":
                patterns.append("Reading files is effective for understanding content")

        return patterns

    def _check_tool_permission(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> bool:
        """Check if tool execution is permitted.

        Args:
            tool_name: Name of the tool
            tool_args: Arguments to the tool

        Returns:
            True if execution is permitted
        """
        mode = self.config.permission_mode

        if mode == PermissionMode.DENY_ALL:
            return False

        if mode == PermissionMode.CONFIRM_ALL:
            # Would require approval callback; without it, deny
            return False

        is_dangerous = self._is_dangerous_tool(tool_name, tool_args)

        if mode == PermissionMode.AUTO:
            # Auto-approve safe tools, deny dangerous ones
            return not is_dangerous

        if mode == PermissionMode.CONFIRM_DANGEROUS:
            # Auto-approve safe, deny dangerous without approval
            return not is_dangerous

        return False

    def _is_dangerous_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> bool:
        """Check if a tool is considered dangerous.

        Dangerous tools include:
        - File writes/deletes
        - Bash commands with destructive operations
        - Network requests that could exfiltrate data

        Args:
            tool_name: Name of the tool
            tool_args: Arguments to the tool

        Returns:
            True if tool is dangerous
        """
        # File write operations
        dangerous_tools = {
            "write_file",
            "delete_file",
            "create_file",
            "edit_file",
            "remove_file",
        }
        if tool_name in dangerous_tools:
            return True

        # Bash commands need inspection
        if tool_name in ("bash_command", "bash", "shell", "execute"):
            command = str(tool_args.get("command", "")).lower()
            dangerous_commands = [
                "rm ",
                "rm -",
                "rmdir",
                "del ",
                "mv ",
                "cp -r",
                "chmod",
                "chown",
                "curl",
                "wget",
                "nc ",
                "netcat",
                "> /",
                ">> /",  # File redirects
            ]
            for dangerous in dangerous_commands:
                if dangerous in command:
                    return True

        return False

    def _update_working_memory(
        self,
        state: ExecutionState,
        key: str,
        value: Any,
    ) -> None:
        """Update working memory.

        Args:
            state: Current execution state
            key: Memory key
            value: Value to store
        """
        state.working_memory[key] = value

    def _clear_working_memory(
        self,
        state: ExecutionState,
        key: Optional[str] = None,
    ) -> None:
        """Clear working memory.

        Args:
            state: Current execution state
            key: Specific key to clear, or None to clear all
        """
        if key is None:
            state.working_memory.clear()
        elif key in state.working_memory:
            del state.working_memory[key]

    def __repr__(self) -> str:
        return (
            f"LocalKaizenAdapter(runtime={self.capabilities.runtime_name}, "
            f"model={self.config.model})"
        )
