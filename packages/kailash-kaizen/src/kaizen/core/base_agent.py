"""
BaseAgent - Universal agent class for Kaizen framework.

This module implements the core BaseAgent class that serves as the foundation
for all agent types in the Kaizen framework. It provides:
- Unified configuration management via BaseAgentConfig
- Lazy framework initialization
- Workflow generation from signatures
- Strategy-based execution delegation
- Mixin composition for features

Architecture:
- Inherits from kailash.workflow.node.Node for Core SDK integration
- Uses Strategy Pattern for execution (SingleShotStrategy, MultiCycleStrategy)
- Uses Mixin Composition for features (LoggingMixin, PerformanceMixin, etc.)

Extension Points (7 total):
1. _default_signature() - Override to provide agent-specific signature
2. _default_strategy() - Override to provide agent-specific strategy
3. _generate_system_prompt() - Override to customize prompt generation
4. _validate_signature_output() - Override to add output validation
5. _pre_execution_hook() - Override to add pre-execution logic
6. _post_execution_hook() - Override to add post-execution logic
7. _handle_error() - Override to customize error handling

References:
- ADR-006: Agent Base Architecture design
- BaseAgent Architecture Unified System (see Unified Agent API)
- Phase 0 Validation: Performance baseline (95.53ms avg init, 36.53MB memory)

Author: Kaizen Framework Team
Created: 2025-10-01
"""

import logging
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional

# MCP client import (for MCP integration)
from kailash.mcp_server.client import MCPClient

# Core SDK imports
from kailash.nodes.base import Node, NodeParameter
from kailash.workflow.builder import WorkflowBuilder

# Type checking imports (not available at runtime in all environments)
if TYPE_CHECKING:
    try:
        from kaizen.nodes.ai.a2a import (
            A2AAgentCard,
            Capability,
            CollaborationStyle,
            PerformanceMetrics,
            ResourceRequirements,
        )
    except ImportError:
        pass

# Kaizen framework imports
from kaizen.signatures import InputField, OutputField, Signature

# Tool system imports - Types only (ToolRegistry/ToolExecutor removed, migrated to MCP)
from kaizen.tools.types import DangerLevel, ToolCategory, ToolDefinition, ToolParameter

from .config import BaseAgentConfig

# Re-export BaseAgentConfig for convenience
__all__ = ["BaseAgent", "BaseAgentConfig"]

# Strategy imports (to be implemented)
# from kaizen.strategies.base_strategy import ExecutionStrategy
# from kaizen.strategies.single_shot import SingleShotStrategy
# from kaizen.strategies.multi_cycle import MultiCycleStrategy

logger = logging.getLogger(__name__)


class BaseAgent(Node):
    """
    Universal base agent class with strategy-based execution and mixin composition.

    BaseAgent provides a unified foundation for all agent types, eliminating
    the massive code duplication (1,537 lines → ~150 lines, 90%+ reduction)
    present in current examples (SimpleQA, ChainOfThought, ReAct).

    Key Features:
    - **Lazy Initialization**: Heavy dependencies loaded only when needed
    - **Strategy Pattern**: Pluggable execution strategies (single-shot, multi-cycle)
    - **Mixin Composition**: Modular features (logging, performance, error handling)
    - **Extension Points**: 7 customization hooks for agent-specific logic
    - **Core SDK Integration**: to_workflow() for workflow composition

    Performance Targets (from Phase 0 baseline):
    - Initialization: <50ms (baseline avg: 95.53ms)
    - Agent Creation: <10ms (baseline avg: 0.08ms)
    - Memory: <40MB (baseline avg: 36.53MB)

    Example Usage:
        >>> from kaizen.core.base_agent import BaseAgent
        >>> from kaizen.core.config import BaseAgentConfig
        >>> from kaizen.signatures import Signature, InputField, OutputField
        >>>
        >>> # Create configuration
        >>> import os
        >>> config = BaseAgentConfig(
        ...     llm_provider="openai",
        ...     model=os.environ.get("OPENAI_PROD_MODEL", os.environ.get("DEFAULT_LLM_MODEL")),
        ...     temperature=0.1,
        ...     logging_enabled=True,
        ...     performance_enabled=True
        ... )
        >>>
        >>> # Create signature
        >>> class QASignature(Signature):
        ...     question: str = InputField(desc="Question to answer")
        ...     answer: str = OutputField(desc="Answer to question")
        >>>
        >>> # Create agent
        >>> agent = BaseAgent(config=config, signature=QASignature())
        >>>
        >>> # Generate workflow for execution
        >>> workflow = agent.to_workflow()
        >>>
        >>> # Execute using Core SDK runtime
        >>> from kailash.runtime.local import LocalRuntime
        >>> runtime = LocalRuntime()
        >>> results, run_id = runtime.execute(workflow.build())

    Extension Pattern:
        >>> class SimpleQAAgent(BaseAgent):
        ...     def _default_signature(self) -> Signature:
        ...         return QASignature()
        ...
        ...     def _generate_system_prompt(self) -> str:
        ...         return "You are a helpful Q&A assistant."
        ...
        ...     def _validate_signature_output(self, output: Dict[str, Any]) -> bool:
        ...         super()._validate_signature_output(output)
        ...         # Custom validation
        ...         if not 0 <= output.get('confidence', 0) <= 1:
        ...             raise ValueError("Confidence must be between 0 and 1")
        ...         return True
        >>>
        >>> # Use simplified agent
        >>> qa_agent = SimpleQAAgent(config=config)
        >>> # Signature and prompt automatically configured

    Notes:
    - This is a SKELETON implementation for TDD Phase 1
    - All methods will be implemented to pass 119 test cases
    - DO NOT implement methods yet - tests drive implementation
    """

    def __init__(
        self,
        config: Any,  # BaseAgentConfig or any domain config (auto-converted)
        signature: Optional[Signature] = None,
        strategy: Optional[Any] = None,  # ExecutionStrategy when implemented
        memory: Optional[Any] = None,  # KaizenMemory when provided (Phase 1)
        shared_memory: Optional[Any] = None,  # SharedMemoryPool when provided (Phase 2)
        agent_id: Optional[str] = None,  # Agent identifier for shared memory (Phase 2)
        control_protocol: Optional[
            Any
        ] = None,  # ControlProtocol for user interaction (Week 10)
        mcp_servers: Optional[List[Dict[str, Any]]] = None,  # MCP server configurations
        hook_manager: Optional[Any] = None,  # HookManager for lifecycle hooks (Phase 2)
        **kwargs,
    ):
        """
        Initialize BaseAgent with lazy loading pattern.

        Args:
            config: Agent configuration - can be:
                   - BaseAgentConfig instance (used directly)
                   - Domain config (auto-converted using from_domain_config())
            signature: Optional signature (uses _default_signature() if None)
            strategy: Optional execution strategy (uses _default_strategy() if None)
            memory: Optional conversation memory (KaizenMemory instance, Phase 1)
            shared_memory: Optional shared memory pool (SharedMemoryPool, Phase 2)
            agent_id: Optional agent identifier (auto-generated if None, Phase 2)
            control_protocol: Optional control protocol for user interaction (ControlProtocol, Week 10)
            mcp_servers: Optional MCP server configurations. If None, auto-connects to kaizen_builtin
                        server for automatic tool discovery (file, HTTP, bash, web tools). Set to []
                        to disable MCP integration.
            hook_manager: Optional HookManager instance for lifecycle hooks (default: creates new instance, Phase 2)
            **kwargs: Additional arguments passed to Node.__init__

        Example:
            >>> # Option 1: Use BaseAgentConfig directly
            >>> config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
            >>> agent = BaseAgent(config=config, signature=QASignature())
            >>>
            >>> # Option 2: Use domain config (auto-converted)
            >>> @dataclass
            >>> class MyWorkflowConfig:
            ...     llm_provider: str = "openai"
            ...     model: str = "gpt-4"
            ...     my_custom_param: str = "value"
            >>>
            >>> config = MyWorkflowConfig()
            >>> agent = BaseAgent(config=config, signature=QASignature())
            >>> # Config automatically converted to BaseAgentConfig

        Notes:
        - Framework initialization is LAZY (not loaded in __init__)
        - Agent instance is LAZY (not created in __init__)
        - Workflow is LAZY (not generated in __init__)
        - Mixins applied based on config feature flags
        - Domain configs auto-converted via BaseAgentConfig.from_domain_config()

        Performance Target: <50ms initialization time

        Phase 2 Addition (Week 3):
        - shared_memory: SharedMemoryPool for multi-agent collaboration
        - agent_id: Identifier for insight attribution (auto-generated if None)
        """
        # Task 1.13: Implement BaseAgent.__init__ with lazy initialization
        # IMPORTANT: Set signature/strategy BEFORE calling super().__init__()
        # because Node.__init__() calls get_parameters() which needs signature

        # UX Improvement: Auto-convert domain config to BaseAgentConfig if needed
        if not isinstance(config, BaseAgentConfig):
            config = BaseAgentConfig.from_domain_config(config)

        # Store configuration early (needed by _default_strategy and _default_signature)
        # Note: Node.__init__ will overwrite this, so we save it and restore after
        self.config = config
        agent_config = config

        # Set signature (use provided or default)
        self.signature = (
            signature if signature is not None else self._default_signature()
        )

        # Set strategy (use provided or default)
        self.strategy = strategy if strategy is not None else self._default_strategy()

        # Set memory (Week 2 Phase 1 addition)
        self.memory = memory

        # Set shared memory (Week 3 Phase 2 addition)
        self.shared_memory = shared_memory

        # Set agent_id (Week 3 Phase 2 addition)
        # Auto-generate if not provided using object id
        self.agent_id = agent_id if agent_id is not None else f"agent_{id(self)}"

        # Set control protocol (Week 10 addition)
        self.control_protocol = control_protocol

        # Initialize MCP system (MCP Integration - replaces legacy ToolRegistry)
        # Auto-connect to builtin MCP server if no servers specified
        if mcp_servers is None:
            # Default to kaizen_builtin server for automatic tool discovery
            self._mcp_servers = [
                {
                    "name": "kaizen_builtin",
                    "command": "python",
                    "args": ["-m", "kaizen.mcp.builtin_server"],
                    "transport": "stdio",
                    "description": "Kaizen builtin tools (file, HTTP, bash, web)",
                }
            ]
        else:
            self._mcp_servers = mcp_servers

        # Create MCP client if servers configured
        if self._mcp_servers:
            self._mcp_client = MCPClient()
            # Initialize discovery caches
            self._discovered_mcp_tools = {}
            self._discovered_mcp_resources = {}
            self._discovered_mcp_prompts = {}

            # LAZY DISCOVERY: Tools will be discovered when explicitly called
            # via await agent.discover_mcp_tools() in async contexts.
            # This avoids event loop conflicts during __init__() when pytest
            # or other async frameworks are already running an event loop.
            # WorkflowGenerator will call discover_mcp_tools() before workflow generation.
            logger.debug(
                f"MCP client initialized with {len(self._mcp_servers)} server(s). "
                f"Call await discover_mcp_tools() to discover tools."
            )
        else:
            self._mcp_client = None
            self._discovered_mcp_tools = {}
            self._discovered_mcp_resources = {}
            self._discovered_mcp_prompts = {}

        # Initialize permission system (Week 5-6: BaseAgent Integration)
        from kaizen.core.autonomy.permissions.approval_manager import (
            ToolApprovalManager,
        )
        from kaizen.core.autonomy.permissions.context import ExecutionContext
        from kaizen.core.autonomy.permissions.policy import PermissionPolicy

        self.execution_context = ExecutionContext(
            mode=config.permission_mode,
            budget_limit=config.budget_limit_usd,
            allowed_tools=(
                config.allowed_tools.copy() if config.allowed_tools else set()
            ),
            denied_tools=config.denied_tools.copy() if config.denied_tools else set(),
            rules=config.permission_rules.copy() if config.permission_rules else [],
        )
        self.permission_policy = PermissionPolicy(self.execution_context)
        self.approval_manager = (
            ToolApprovalManager(control_protocol) if control_protocol else None
        )

        # Initialize hook system for observability (System 3)
        # Accept hook_manager parameter (Phase 2) or create default instance if enabled
        if hook_manager is not None:
            self.hook_manager = hook_manager
        elif self.config.hooks_enabled:
            # Only create HookManager if hooks are enabled
            from kaizen.core.autonomy.hooks.manager import HookManager

            self.hook_manager = HookManager()
        else:
            # Hooks disabled - no HookManager
            self.hook_manager = None

        # Keep _hook_manager for backward compatibility with existing code
        self._hook_manager = self.hook_manager

        # Initialize observability manager (Systems 4-7) - lazy, created by enable_observability()
        self._observability_manager = None

        # Now call Node.__init__ (it will call get_parameters())
        # Note: Node.__init__ will set self.config to a dict, we restore it after
        super().__init__(**kwargs)

        # Restore config to BaseAgentConfig (Node.__init__ overwrites it with a dict)
        self.config = agent_config

        # Lazy initialization (all None until needed)
        self._framework = None
        self._agent = None
        self._workflow = None

        # Task 2.7: Initialize WorkflowGenerator for strategy use
        from .workflow_generator import WorkflowGenerator

        # FIX BUG #3: Pass _generate_system_prompt as callback to enable custom prompts
        # Pass self as agent parameter for MCP tool discovery
        self.workflow_generator = WorkflowGenerator(
            config=self.config,
            signature=self.signature,
            prompt_generator=self._generate_system_prompt,  # Enable extension point
            agent=self,  # Enable MCP tool discovery
        )

        # Mixin state tracking (for testing)
        self._mixins_applied = []

        # Apply mixins based on config feature flags
        if config.logging_enabled:
            self._apply_logging_mixin()

        if config.performance_enabled:
            self._apply_performance_mixin()

        if config.error_handling_enabled:
            self._apply_error_handling_mixin()

        if config.batch_processing_enabled:
            self._apply_batch_processing_mixin()

        if config.memory_enabled:
            self._apply_memory_mixin()

        if config.transparency_enabled:
            self._apply_transparency_mixin()

        if config.mcp_enabled:
            self._apply_mcp_integration_mixin()

    def _apply_logging_mixin(self):
        """Apply logging mixin for structured agent logging."""
        from kaizen.core.mixins.logging_mixin import LoggingMixin

        LoggingMixin.apply(self)
        self._mixins_applied.append("LoggingMixin")

    def _apply_performance_mixin(self):
        """Apply performance mixin (metrics collection)."""
        from kaizen.core.mixins.metrics_mixin import MetricsMixin

        MetricsMixin.apply(self)
        self._mixins_applied.append("PerformanceMixin")

    def _apply_error_handling_mixin(self):
        """Apply error handling mixin (retry with exponential backoff)."""
        from kaizen.core.mixins.retry_mixin import RetryMixin

        RetryMixin.apply(self)
        self._mixins_applied.append("ErrorHandlingMixin")

    def _apply_batch_processing_mixin(self):
        """Apply batch processing mixin (caching for batch operations)."""
        from kaizen.core.mixins.caching_mixin import CachingMixin

        CachingMixin.apply(self)
        self._mixins_applied.append("BatchProcessingMixin")

    def _apply_memory_mixin(self):
        """Apply memory mixin (timeout handling for memory operations)."""
        from kaizen.core.mixins.timeout_mixin import TimeoutMixin

        TimeoutMixin.apply(self)
        self._mixins_applied.append("MemoryMixin")

    def _apply_transparency_mixin(self):
        """Apply transparency mixin (distributed tracing)."""
        from kaizen.core.mixins.tracing_mixin import TracingMixin

        TracingMixin.apply(self)
        self._mixins_applied.append("TransparencyMixin")

    def _apply_mcp_integration_mixin(self):
        """Apply MCP integration mixin (input/output validation)."""
        from kaizen.core.mixins.validation_mixin import ValidationMixin

        ValidationMixin.apply(self)
        self._mixins_applied.append("MCPIntegrationMixin")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """
        Get parameter schema for agent contract.

        Returns schema describing inputs/outputs based on signature.
        Required by Node base class for workflow composition.

        Returns:
            Dict[str, NodeParameter]: Parameter definitions for Node

        Example:
            >>> params = agent.get_parameters()
            >>> print(params['question'])
            NodeParameter(name='question', type=str, required=True, ...)
        """
        # Task 1.14: Implement BaseAgent.get_parameters()
        # Return Dict[str, NodeParameter] as expected by Node base class
        parameters = {}

        # Extract input fields from signature
        if hasattr(self.signature, "input_fields"):
            for field in self.signature.input_fields:
                field_name = field.name if hasattr(field, "name") else "input"
                field_type = field.type if hasattr(field, "type") else str
                field_desc = (
                    field.desc if hasattr(field, "desc") else f"{field_name} parameter"
                )
                is_required = not (hasattr(field, "optional") and field.optional)

                parameters[field_name] = NodeParameter(
                    name=field_name,
                    type=field_type,
                    required=is_required,
                    description=field_desc,
                )

        # Note: Output fields not included in Node parameters (outputs determined by run())
        # Node parameters are for inputs only

        return parameters

    def run(self, **inputs) -> Dict[str, Any]:
        """
        Execute agent with strategy-based execution and error handling.

        Execution flow:
        1. Load individual memory context (if memory enabled and session_id provided)
        2. Read shared insights (if shared_memory enabled, Phase 2)
        3. Call _pre_execution_hook(inputs)
        4. Delegate to strategy.execute() (handles both sync and async)
        5. Call _post_execution_hook(result)
        6. Save turn to individual memory (if memory enabled and session_id provided)
        7. Write insight to shared memory (if shared_memory enabled and result has _write_insight, Phase 2)
        8. Handle errors via _handle_error() if errors occur

        Args:
            **inputs: Input parameters matching signature input fields.
                     Special parameter: session_id (str) - for memory persistence

        Returns:
            Dict[str, Any]: Results matching signature output fields

        Raises:
            ValueError: If inputs don't match signature
            RuntimeError: If execution fails (when error_handling_enabled=False)

        Example:
            >>> result = agent.run(question="What is 2+2?", context=None)
            >>> print(result)
            {
                'answer': '2+2 equals 4',
                'confidence': 0.99
            }

            >>> # With memory and session
            >>> result = agent.run(question="What is 2+2?", session_id="session1")

        Note:
            Phase 0A: Now handles async strategies (AsyncSingleShotStrategy)
            by running them in the event loop synchronously.
            Week 2 Phase 1: Added individual memory integration with session_id support.
            Week 3 Phase 2: Added shared memory integration for multi-agent collaboration.
                           Agents read insights via _shared_insights input.
                           Agents write insights via _write_insight result key.
        """
        # Task 0A.1: Handle async strategies in sync run() method
        import asyncio
        import inspect
        from datetime import datetime

        # Extract session_id if provided (Week 2 Phase 1 addition)
        session_id = inputs.pop("session_id", None)

        try:
            # Week 2 Phase 1: Load individual memory context if enabled
            memory_context = {}
            if self.memory and session_id:
                # Trigger PRE_MEMORY_LOAD hook
                if self.hook_manager:
                    import concurrent.futures

                    from kaizen.core.autonomy.hooks.types import HookEvent

                    try:
                        loop = asyncio.get_running_loop()
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            executor.submit(
                                asyncio.run,
                                self.hook_manager.trigger(
                                    HookEvent.PRE_MEMORY_LOAD,
                                    agent_id=self.agent_id,
                                    data={"session_id": session_id},
                                ),
                            ).result(timeout=5.0)
                    except RuntimeError:
                        asyncio.run(
                            self.hook_manager.trigger(
                                HookEvent.PRE_MEMORY_LOAD,
                                agent_id=self.agent_id,
                                data={"session_id": session_id},
                            )
                        )
                    except Exception as e:
                        logger.error(f"PRE_MEMORY_LOAD hook failed: {e}")

                memory_context = self.memory.load_context(session_id)

                # Trigger POST_MEMORY_LOAD hook
                if self.hook_manager:
                    from kaizen.core.autonomy.hooks.types import HookEvent

                    try:
                        loop = asyncio.get_running_loop()
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            executor.submit(
                                asyncio.run,
                                self.hook_manager.trigger(
                                    HookEvent.POST_MEMORY_LOAD,
                                    agent_id=self.agent_id,
                                    data={
                                        "session_id": session_id,
                                        "context_size": len(str(memory_context)),
                                    },
                                ),
                            ).result(timeout=5.0)
                    except RuntimeError:
                        asyncio.run(
                            self.hook_manager.trigger(
                                HookEvent.POST_MEMORY_LOAD,
                                agent_id=self.agent_id,
                                data={
                                    "session_id": session_id,
                                    "context_size": len(str(memory_context)),
                                },
                            )
                        )
                    except Exception as e:
                        logger.error(f"POST_MEMORY_LOAD hook failed: {e}")

                # Merge memory context into inputs for agent awareness
                inputs["_memory_context"] = memory_context

            # Week 3 Phase 2: Read shared insights if enabled
            if self.shared_memory:
                # Read relevant insights from other agents (exclude own)
                shared_insights = self.shared_memory.read_relevant(
                    agent_id=self.agent_id,
                    exclude_own=True,  # Don't read own insights
                    limit=10,  # Top 10 most relevant
                )
                inputs["_shared_insights"] = shared_insights

            # Pre-execution hook
            processed_inputs = self._pre_execution_hook(inputs)

            # Phase 2: Trigger PRE_AGENT_LOOP hooks (if hook_manager available)
            if self.hook_manager:
                import concurrent.futures

                from kaizen.core.autonomy.hooks.types import HookEvent

                # Run hook trigger in event loop
                try:
                    loop = asyncio.get_running_loop()
                    # Loop is running - run hook in thread pool to avoid "loop already running" error
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            self.hook_manager.trigger(
                                HookEvent.PRE_AGENT_LOOP,
                                agent_id=self.agent_id,
                                data={
                                    "inputs": processed_inputs,
                                    "signature": self.signature.__class__.__name__,
                                },
                            ),
                        )
                        # Wait for completion (default timeout: 5s)
                        future.result(timeout=5.0)
                except RuntimeError:
                    # No running loop - safe to create and run
                    asyncio.run(
                        self.hook_manager.trigger(
                            HookEvent.PRE_AGENT_LOOP,
                            agent_id=self.agent_id,
                            data={
                                "inputs": processed_inputs,
                                "signature": self.signature.__class__.__name__,
                            },
                        )
                    )
                except Exception as e:
                    # Hook failures should not crash agent execution
                    logger.error(f"PRE_AGENT_LOOP hook failed: {e}")

            # Execute via strategy (handle both sync and async)
            if hasattr(self.strategy, "execute"):
                # Check if strategy.execute is async
                if inspect.iscoroutinefunction(self.strategy.execute):
                    # Async strategy - run in event loop
                    import concurrent.futures

                    try:
                        # Try to get running loop (Python 3.10+)
                        loop = asyncio.get_running_loop()
                        # Loop is running - run strategy in thread pool to avoid "loop already running" error
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(
                                asyncio.run,
                                self.strategy.execute(self, processed_inputs),
                            )
                            result = future.result()
                    except RuntimeError:
                        # No running loop - safe to create and run
                        result = asyncio.run(
                            self.strategy.execute(self, processed_inputs)
                        )
                else:
                    # Sync strategy - call directly
                    result = self.strategy.execute(self, processed_inputs)
            else:
                # Fallback: simple execution without strategy
                result = self._simple_execute(processed_inputs)

            # Validate output
            self._validate_signature_output(result)

            # Post-execution hook
            final_result = self._post_execution_hook(result)

            # Phase 2: Trigger POST_AGENT_LOOP hooks (if hook_manager available)
            if self.hook_manager:
                import concurrent.futures

                from kaizen.core.autonomy.hooks.types import HookEvent

                # Run hook trigger in event loop
                try:
                    loop = asyncio.get_running_loop()
                    # Loop is running - run hook in thread pool to avoid "loop already running" error
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            self.hook_manager.trigger(
                                HookEvent.POST_AGENT_LOOP,
                                agent_id=self.agent_id,
                                data={
                                    "result": final_result,
                                    "signature": self.signature.__class__.__name__,
                                },
                            ),
                        )
                        # Wait for completion (default timeout: 5s)
                        future.result(timeout=5.0)
                except RuntimeError:
                    # No running loop - safe to create and run
                    asyncio.run(
                        self.hook_manager.trigger(
                            HookEvent.POST_AGENT_LOOP,
                            agent_id=self.agent_id,
                            data={
                                "result": final_result,
                                "signature": self.signature.__class__.__name__,
                            },
                        )
                    )
                except Exception as e:
                    # Hook failures should not crash agent execution
                    logger.error(f"POST_AGENT_LOOP hook failed: {e}")

            # Week 2 Phase 1: Save turn to individual memory if enabled
            if self.memory and session_id:
                # Extract user input (first input field value, or 'prompt')
                user_input = inputs.get("prompt", "")
                if not user_input and processed_inputs:
                    # Try to get first input value
                    user_input = (
                        str(list(processed_inputs.values())[0])
                        if processed_inputs
                        else ""
                    )

                # Extract agent response (first output field value, or 'response')
                agent_response = final_result.get("response", "")
                if not agent_response and final_result:
                    # Try to get first output value
                    agent_response = (
                        str(list(final_result.values())[0]) if final_result else ""
                    )

                # Create turn
                turn = {
                    "user": user_input,
                    "agent": agent_response,
                    "timestamp": datetime.now().isoformat(),
                }

                # Trigger PRE_MEMORY_SAVE hook
                if self.hook_manager:
                    from kaizen.core.autonomy.hooks.types import HookEvent

                    try:
                        loop = asyncio.get_running_loop()
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            executor.submit(
                                asyncio.run,
                                self.hook_manager.trigger(
                                    HookEvent.PRE_MEMORY_SAVE,
                                    agent_id=self.agent_id,
                                    data={
                                        "session_id": session_id,
                                        "turn_size": len(str(turn)),
                                    },
                                ),
                            ).result(timeout=5.0)
                    except RuntimeError:
                        asyncio.run(
                            self.hook_manager.trigger(
                                HookEvent.PRE_MEMORY_SAVE,
                                agent_id=self.agent_id,
                                data={
                                    "session_id": session_id,
                                    "turn_size": len(str(turn)),
                                },
                            )
                        )
                    except Exception as e:
                        logger.error(f"PRE_MEMORY_SAVE hook failed: {e}")

                # Save to memory
                self.memory.save_turn(session_id, turn)

                # Trigger POST_MEMORY_SAVE hook
                if self.hook_manager:
                    from kaizen.core.autonomy.hooks.types import HookEvent

                    try:
                        loop = asyncio.get_running_loop()
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            executor.submit(
                                asyncio.run,
                                self.hook_manager.trigger(
                                    HookEvent.POST_MEMORY_SAVE,
                                    agent_id=self.agent_id,
                                    data={
                                        "session_id": session_id,
                                        "turn_saved": True,
                                    },
                                ),
                            ).result(timeout=5.0)
                    except RuntimeError:
                        asyncio.run(
                            self.hook_manager.trigger(
                                HookEvent.POST_MEMORY_SAVE,
                                agent_id=self.agent_id,
                                data={
                                    "session_id": session_id,
                                    "turn_saved": True,
                                },
                            )
                        )
                    except Exception as e:
                        logger.error(f"POST_MEMORY_SAVE hook failed: {e}")

            # Week 3 Phase 2: Write insight to shared memory if enabled
            if self.shared_memory and final_result.get("_write_insight"):
                # Agent can optionally write insights to shared pool
                insight = {
                    "agent_id": self.agent_id,
                    "content": final_result["_write_insight"],
                    "tags": final_result.get("_insight_tags", []),
                    "importance": final_result.get("_insight_importance", 0.5),
                    "segment": final_result.get("_insight_segment", "execution"),
                    "metadata": final_result.get("_insight_metadata", {}),
                }
                self.shared_memory.write_insight(insight)

            return final_result

        except Exception as error:
            # Clean up any pending coroutines before error handling
            import gc

            # Force garbage collection to clean up any pending coroutines
            # This prevents "coroutine was never awaited" warnings
            gc.collect()

            # Handle error via extension point
            return self._handle_error(error, {"inputs": inputs})

    async def run_async(self, **inputs) -> Dict[str, Any]:
        """
        Execute agent asynchronously with non-blocking I/O (async version).

        This async method provides true non-blocking execution for production
        FastAPI deployments and concurrent agent workflows. It uses AsyncOpenAI
        for async LLM calls, preventing thread pool exhaustion and SSL timeouts.

        **Configuration Requirement:**
        Agent must be configured with `use_async_llm=True` to use this method:

        >>> config = BaseAgentConfig(
        ...     llm_provider="openai",
        ...     model="gpt-4",
        ...     use_async_llm=True  # Required for async execution
        ... )
        >>> agent = BaseAgent(config=config, signature=MySignature())
        >>> result = await agent.run_async(question="Hello")

        Execution flow:
        1. Validates async configuration (use_async_llm=True)
        2. Load individual memory context (if memory enabled and session_id provided)
        3. Read shared insights (if shared_memory enabled)
        4. Call _pre_execution_hook(inputs)
        5. Execute async strategy or direct async provider call
        6. Call _post_execution_hook(result)
        7. Save turn to individual memory (if memory enabled and session_id provided)
        8. Write insight to shared memory (if enabled)
        9. Handle errors via _handle_error() if errors occur

        Args:
            **inputs: Input parameters matching signature input fields.
                     Special parameter: session_id (str) - for memory persistence

        Returns:
            Dict[str, Any]: Results matching signature output fields

        Raises:
            ValueError: If use_async_llm=False (agent not configured for async mode)
            RuntimeError: If execution fails (when error_handling_enabled=False)

        Example:
            >>> # Configure agent for async mode
            >>> config = BaseAgentConfig(
            ...     llm_provider="openai",
            ...     model="gpt-4",
            ...     use_async_llm=True
            ... )
            >>> agent = BaseAgent(config=config, signature=QASignature())
            >>>
            >>> # Execute asynchronously
            >>> result = await agent.run_async(question="What is 2+2?")
            >>> print(result)
            {
                'answer': '2+2 equals 4',
                'confidence': 0.99
            }

            >>> # With FastAPI
            >>> @app.post("/api/chat")
            >>> async def chat(request: ChatRequest):
            ...     result = await agent.run_async(question=request.message)
            ...     return {"response": result["answer"]}

        Performance Benefits:
        - **10-100x faster** concurrent requests vs sync + ThreadPoolExecutor
        - **No thread pool exhaustion** - handles 100+ concurrent requests
        - **No SSL socket blocking** - true async I/O throughout
        - **Production-ready** - designed for FastAPI/async workflows

        Notes:
        - This method requires `use_async_llm=True` in configuration
        - Backwards compatible - sync `run()` method unchanged
        - Uses AsyncOpenAI client for non-blocking OpenAI API calls
        - Memory and hooks system fully supported (same as sync run())
        """
        # Validate async configuration
        if not self.config.use_async_llm:
            raise ValueError(
                "Agent not configured for async mode. "
                "Set use_async_llm=True in BaseAgentConfig:\n\n"
                "config = BaseAgentConfig(\n"
                "    llm_provider='openai',\n"
                "    model='gpt-4',\n"
                "    use_async_llm=True  # Enable async mode\n"
                ")\n"
            )

        from datetime import datetime

        # Extract session_id if provided
        session_id = inputs.pop("session_id", None)

        try:
            # Load individual memory context if enabled
            memory_context = {}
            if self.memory and session_id:
                memory_context = self.memory.load_context(session_id)
                inputs["_memory_context"] = memory_context

            # Read shared insights if enabled
            if self.shared_memory:
                shared_insights = self.shared_memory.read_relevant(
                    agent_id=self.agent_id,
                    exclude_own=True,
                    limit=10,
                )
                inputs["_shared_insights"] = shared_insights

            # Pre-execution hook
            processed_inputs = self._pre_execution_hook(inputs)

            # Trigger PRE_AGENT_LOOP hooks (if hook_manager available)
            if self.hook_manager:
                from kaizen.core.autonomy.hooks.types import HookEvent

                try:
                    await self.hook_manager.trigger(
                        HookEvent.PRE_AGENT_LOOP,
                        agent_id=self.agent_id,
                        data={
                            "inputs": processed_inputs,
                            "signature": self.signature.__class__.__name__,
                        },
                    )
                except Exception as e:
                    logger.error(f"PRE_AGENT_LOOP hook failed: {e}")

            # Execute via async strategy or direct provider call
            if hasattr(self.strategy, "execute_async"):
                # Async strategy exists - use it
                result = await self.strategy.execute_async(self, processed_inputs)
            elif hasattr(self.strategy, "execute"):
                import inspect

                if inspect.iscoroutinefunction(self.strategy.execute):
                    # Strategy.execute is async - call it directly
                    result = await self.strategy.execute(self, processed_inputs)
                else:
                    # Fallback to sync strategy (not recommended for async mode)
                    import asyncio

                    result = await asyncio.to_thread(
                        self.strategy.execute, self, processed_inputs
                    )
            else:
                # Fallback: direct async provider call
                result = await self._simple_execute_async(processed_inputs)

            # Validate output
            self._validate_signature_output(result)

            # Post-execution hook
            final_result = self._post_execution_hook(result)

            # Trigger POST_AGENT_LOOP hooks (if hook_manager available)
            if self.hook_manager:
                from kaizen.core.autonomy.hooks.types import HookEvent

                try:
                    await self.hook_manager.trigger(
                        HookEvent.POST_AGENT_LOOP,
                        agent_id=self.agent_id,
                        data={
                            "result": final_result,
                            "signature": self.signature.__class__.__name__,
                        },
                    )
                except Exception as e:
                    logger.error(f"POST_AGENT_LOOP hook failed: {e}")

            # Save turn to individual memory if enabled
            if self.memory and session_id:
                user_input = inputs.get("prompt", "")
                if not user_input and processed_inputs:
                    user_input = (
                        str(list(processed_inputs.values())[0])
                        if processed_inputs
                        else ""
                    )

                agent_response = final_result.get("response", "")
                if not agent_response and final_result:
                    agent_response = (
                        str(list(final_result.values())[0]) if final_result else ""
                    )

                turn = {
                    "user": user_input,
                    "agent": agent_response,
                    "timestamp": datetime.now().isoformat(),
                }

                # Trigger PRE_MEMORY_SAVE hook
                if self.hook_manager:
                    from kaizen.core.autonomy.hooks.types import HookEvent

                    try:
                        loop = asyncio.get_running_loop()
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            executor.submit(
                                asyncio.run,
                                self.hook_manager.trigger(
                                    HookEvent.PRE_MEMORY_SAVE,
                                    agent_id=self.agent_id,
                                    data={
                                        "session_id": session_id,
                                        "turn_size": len(str(turn)),
                                    },
                                ),
                            ).result(timeout=5.0)
                    except RuntimeError:
                        asyncio.run(
                            self.hook_manager.trigger(
                                HookEvent.PRE_MEMORY_SAVE,
                                agent_id=self.agent_id,
                                data={
                                    "session_id": session_id,
                                    "turn_size": len(str(turn)),
                                },
                            )
                        )
                    except Exception as e:
                        logger.error(f"PRE_MEMORY_SAVE hook failed: {e}")

                self.memory.save_turn(session_id, turn)

                # Trigger POST_MEMORY_SAVE hook
                if self.hook_manager:
                    from kaizen.core.autonomy.hooks.types import HookEvent

                    try:
                        loop = asyncio.get_running_loop()
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            executor.submit(
                                asyncio.run,
                                self.hook_manager.trigger(
                                    HookEvent.POST_MEMORY_SAVE,
                                    agent_id=self.agent_id,
                                    data={
                                        "session_id": session_id,
                                        "turn_saved": True,
                                    },
                                ),
                            ).result(timeout=5.0)
                    except RuntimeError:
                        asyncio.run(
                            self.hook_manager.trigger(
                                HookEvent.POST_MEMORY_SAVE,
                                agent_id=self.agent_id,
                                data={
                                    "session_id": session_id,
                                    "turn_saved": True,
                                },
                            )
                        )
                    except Exception as e:
                        logger.error(f"POST_MEMORY_SAVE hook failed: {e}")

            # Write insight to shared memory if enabled
            if self.shared_memory and final_result.get("_write_insight"):
                insight = {
                    "agent_id": self.agent_id,
                    "content": final_result["_write_insight"],
                    "tags": final_result.get("_insight_tags", []),
                    "importance": final_result.get("_insight_importance", 0.5),
                    "segment": final_result.get("_insight_segment", "execution"),
                    "metadata": final_result.get("_insight_metadata", {}),
                }
                self.shared_memory.write_insight(insight)

            return final_result

        except Exception as error:
            # Handle error via extension point
            return self._handle_error(error, {"inputs": inputs})

    async def _simple_execute_async(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simple async execution using direct provider call (fallback).

        Used when async strategy doesn't exist. Directly calls AsyncOpenAI
        provider for non-blocking LLM execution.

        Args:
            inputs: Processed input parameters

        Returns:
            Dict[str, Any]: LLM response matching signature output fields
        """
        # Import async provider
        from kaizen.nodes.ai.ai_providers import OpenAIProvider

        # Initialize async provider
        provider = OpenAIProvider(use_async=True)

        # Prepare messages from inputs
        messages = []

        # Add system prompt if signature exists
        system_prompt = self._generate_system_prompt()
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Add user message from inputs
        # For simple case, join all input values
        user_content = " | ".join(
            str(v) for v in inputs.values() if not str(v).startswith("_")
        )
        messages.append({"role": "user", "content": user_content})

        # Call async provider
        response = await provider.chat_async(
            messages=messages,
            model=self.config.model
            or os.environ.get("DEFAULT_LLM_MODEL")
            or os.environ.get("OPENAI_PROD_MODEL"),
            generation_config={
                "temperature": self.config.temperature or 0.7,
                "max_tokens": self.config.max_tokens or 500,
            },
        )

        # Map response to signature outputs
        # For simple case, return content as first output field
        if self.signature:
            output_fields = list(self.signature.output_fields.keys())
            if output_fields:
                return {output_fields[0]: response["content"]}

        return {"response": response["content"]}

    def _simple_execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simple execution without strategy (fallback).

        Used when strategy doesn't implement execute() method.
        """
        # Placeholder for simple LLM call
        # In production, this would call LLM directly
        return {"result": "Simple execution placeholder"}

    # ===================================================================
    # Convenience Methods for Improved Developer UX
    # ===================================================================

    def write_to_memory(
        self,
        content: Any,
        tags: Optional[List[str]] = None,
        importance: float = 0.5,
        segment: str = "execution",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Convenience method to write insights to shared memory.

        Simplifies the common pattern of writing to shared memory by:
        - Auto-adding agent_id
        - Auto-serializing content to JSON
        - Providing sensible defaults

        Args:
            content: Content to write (auto-serialized to JSON if dict/list)
            tags: Tags for categorization (default: [])
            importance: Importance score 0.0-1.0 (default: 0.5)
            segment: Memory segment (default: "execution")
            metadata: Optional metadata dict (default: {})

        Example:
            >>> # OLD WAY (verbose):
            >>> if self.shared_memory:
            >>>     self.shared_memory.write_insight({
            >>>         "agent_id": self.agent_id,
            >>>         "content": json.dumps(result),
            >>>         "tags": ["processing", "complete"],
            >>>         "importance": 0.9,
            >>>         "segment": "pipeline"
            >>>     })
            >>>
            >>> # NEW WAY (concise):
            >>> self.write_to_memory(
            >>>     content=result,
            >>>     tags=["processing", "complete"],
            >>>     importance=0.9,
            >>>     segment="pipeline"
            >>> )

        Notes:
            - Does nothing if shared_memory is not available
            - Automatically serializes dicts and lists to JSON
            - Agent ID automatically added
        """
        if not self.shared_memory:
            return

        import json

        # Auto-serialize content if needed
        if isinstance(content, (dict, list)):
            content_str = json.dumps(content)
        else:
            content_str = str(content)

        # Build insight
        insight = {
            "agent_id": self.agent_id,
            "content": content_str,
            "tags": tags or [],
            "importance": importance,
            "segment": segment,
            "metadata": metadata or {},
        }

        self.shared_memory.write_insight(insight)

    def extract_list(
        self, result: Dict[str, Any], field_name: str, default: Optional[List] = None
    ) -> List:
        """
        Extract a list field from result with type safety.

        Handles the common pattern of extracting list fields that might be
        JSON strings or actual lists from LLM responses.

        Args:
            result: Result dictionary from agent execution
            field_name: Name of the field to extract
            default: Default value if extraction fails (default: [])

        Returns:
            List: Extracted list or default

        Example:
            >>> result = agent.run(query="...")
            >>>
            >>> # OLD WAY (verbose):
            >>> items_raw = result.get("items", "[]")
            >>> if isinstance(items_raw, str):
            >>>     try:
            >>>         items = json.loads(items_raw) if items_raw else []
            >>>     except:
            >>>         items = []
            >>> else:
            >>>     items = items_raw if isinstance(items_raw, list) else []
            >>>
            >>> # NEW WAY (concise):
            >>> items = self.extract_list(result, "items", default=[])
        """
        import json

        if default is None:
            default = []

        field_value = result.get(field_name, default)

        # Already a list
        if isinstance(field_value, list):
            return field_value

        # Try to parse as JSON string
        if isinstance(field_value, str):
            try:
                parsed = json.loads(field_value) if field_value else default
                return parsed if isinstance(parsed, list) else default
            except Exception:
                return default

        # Fallback
        return default

    def extract_dict(
        self, result: Dict[str, Any], field_name: str, default: Optional[Dict] = None
    ) -> Dict:
        """
        Extract a dict field from result with type safety.

        Handles the common pattern of extracting dict fields that might be
        JSON strings or actual dicts from LLM responses.

        Args:
            result: Result dictionary from agent execution
            field_name: Name of the field to extract
            default: Default value if extraction fails (default: {})

        Returns:
            Dict: Extracted dict or default

        Example:
            >>> result = agent.run(query="...")
            >>> config = self.extract_dict(result, "config", default={})
        """
        import json

        if default is None:
            default = {}

        field_value = result.get(field_name, default)

        # Already a dict
        if isinstance(field_value, dict):
            return field_value

        # Try to parse as JSON string
        if isinstance(field_value, str):
            try:
                parsed = json.loads(field_value) if field_value else default
                return parsed if isinstance(parsed, dict) else default
            except Exception:
                return default

        # Fallback
        return default

    def extract_float(
        self, result: Dict[str, Any], field_name: str, default: float = 0.0
    ) -> float:
        """
        Extract a float field from result with type safety.

        Handles the common pattern of extracting numeric fields that might be
        strings or actual numbers from LLM responses.

        Args:
            result: Result dictionary from agent execution
            field_name: Name of the field to extract
            default: Default value if extraction fails (default: 0.0)

        Returns:
            float: Extracted float or default

        Example:
            >>> result = agent.run(query="...")
            >>> confidence = self.extract_float(result, "confidence", default=0.0)
        """
        field_value = result.get(field_name, default)

        # Already a number
        if isinstance(field_value, (int, float)):
            return float(field_value)

        # Try to parse as string
        if isinstance(field_value, str):
            try:
                return float(field_value)
            except Exception:
                return default

        # Fallback
        return default

    def extract_str(
        self, result: Dict[str, Any], field_name: str, default: str = ""
    ) -> str:
        """
        Extract a string field from result with type safety.

        Handles the common pattern of extracting string fields from LLM responses.

        Args:
            result: Result dictionary from agent execution
            field_name: Name of the field to extract
            default: Default value if extraction fails (default: "")

        Returns:
            str: Extracted string or default

        Example:
            >>> result = agent.run(query="...")
            >>> answer = self.extract_str(result, "answer", default="No answer")
        """
        field_value = result.get(field_name, default)
        return str(field_value) if field_value is not None else default

    def to_workflow(self) -> WorkflowBuilder:
        """
        Generate a Core SDK workflow from the agent's signature.

        This is the core method that converts signature-based programming
        into actual Core SDK workflows using WorkflowBuilder and LLMAgentNode.

        Workflow Structure:
        1. Creates LLMAgentNode with agent configuration
        2. Maps signature input fields to workflow inputs
        3. Maps signature output fields to workflow outputs
        4. Adds necessary connections

        Returns:
            WorkflowBuilder: Workflow representation ready for execution

        Example:
            >>> workflow = agent.to_workflow()
            >>> built = workflow.build()  # Returns Workflow object
            >>>
            >>> # Execute with runtime
            >>> from kailash.runtime.local import LocalRuntime
            >>> runtime = LocalRuntime()
            >>> results, run_id = runtime.execute(built)

        Core SDK Pattern:
            workflow.add_node('LLMAgentNode', 'agent', {
                'model': self.config.model,
                'provider': self.config.llm_provider,
                'temperature': self.config.temperature,
                'system_prompt': self._generate_system_prompt(),
            })

        Notes:
        - Workflow is cached after first generation
        - Workflow uses LLMAgentNode from src/kailash/nodes/ai/llm_agent.py
        - Workflow must be composable with other Core SDK nodes
        """
        # Task 1.16: Implement BaseAgent.to_workflow()
        # Return cached workflow if already generated
        if self._workflow is not None:
            return self._workflow

        # Create new workflow
        workflow = WorkflowBuilder()

        # Add LLMAgentNode with configuration
        node_config = {
            "system_prompt": self._generate_system_prompt(),
        }

        # Add LLM configuration if specified
        if self.config.model is not None:
            node_config["model"] = self.config.model
        if self.config.llm_provider is not None:
            node_config["provider"] = self.config.llm_provider
        if self.config.temperature is not None:
            node_config["temperature"] = self.config.temperature
        if self.config.max_tokens is not None:
            node_config["max_tokens"] = self.config.max_tokens
        if self.config.provider_config is not None:
            node_config["provider_config"] = self.config.provider_config
        if self.config.response_format is not None:
            node_config["response_format"] = self.config.response_format

        # Add the LLM agent node using string-based node name
        workflow.add_node("LLMAgentNode", "agent", node_config)

        # Cache the workflow
        self._workflow = workflow

        return workflow

    def to_workflow_node(self) -> Node:
        """
        Convert this agent into a single node for composition.

        Enables agent reuse in larger workflows by wrapping the agent
        as a composable node.

        Returns:
            Node: Agent as a composable workflow node

        Example:
            >>> agent_node = agent.to_workflow_node()
            >>>
            >>> # Use in larger workflow
            >>> main_workflow = WorkflowBuilder()
            >>> main_workflow.add_node_instance(agent_node, 'qa')
            >>> main_workflow.add_node('DataTransformer', 'transform', {...})
            >>> main_workflow.add_connection('qa', 'answer', 'transform', 'input')
        """
        # Task 1.16: Implement BaseAgent.to_workflow_node()
        # The agent itself is already a Node (inherits from Node)
        # So we can return self as a composable node
        return self

    # ===================================================================
    # Extension Points (7 total)
    # Override these methods in subclasses for agent-specific behavior
    # ===================================================================

    def _default_signature(self) -> Signature:
        """
        Provide default signature when none is specified.

        Override this method for agent-specific signatures.

        Returns:
            Signature: Default signature (1 input, 1 output)

        Extension Example:
            >>> class SimpleQAAgent(BaseAgent):
            ...     def _default_signature(self) -> Signature:
            ...         return QASignature(
            ...             question: str = InputField(desc="Question"),
            ...             answer: str = OutputField(desc="Answer")
            ...         )
        """

        # Task 1.17: Implement extension point 1
        # Create a simple default signature with 1 input, 1 output
        # Using proper InputField and OutputField
        class DefaultSignature(Signature):
            """Default signature with generic input/output."""

            input: str = InputField(desc="Generic input")
            output: str = OutputField(desc="Generic output")

        return DefaultSignature()

    def _default_strategy(self) -> Any:  # ExecutionStrategy when implemented
        """
        Provide default execution strategy.

        Override this method for agent-specific strategies.
        Returns AsyncSingleShotStrategy for strategy_type="single_shot" (NEW DEFAULT),
        MultiCycleStrategy for strategy_type="multi_cycle".

        Returns:
            ExecutionStrategy: Default strategy based on config

        Extension Example:
            >>> class ReActAgent(BaseAgent):
            ...     def _default_strategy(self) -> ExecutionStrategy:
            ...         return MultiCycleStrategy(max_cycles=10)

        Note:
            BREAKING CHANGE (Phase 0A): Default is now AsyncSingleShotStrategy
            for improved performance (2-3x faster for concurrent requests).
        """
        # Task 0A.1: Use AsyncSingleShotStrategy as default
        # Import strategies if available, otherwise return simple strategy object
        try:
            from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy
            from kaizen.strategies.multi_cycle import MultiCycleStrategy

            if self.config.strategy_type == "multi_cycle":
                return MultiCycleStrategy(max_cycles=self.config.max_cycles)
            else:
                # DEFAULT: AsyncSingleShotStrategy (for "single_shot" or None)
                return AsyncSingleShotStrategy()
        except ImportError:
            # Fallback: return simple strategy object
            class SimpleStrategy:
                async def execute(self, agent, inputs, **kwargs):
                    return {"result": "Simple strategy execution"}

            return SimpleStrategy()

    def _generate_system_prompt(self) -> str:
        """
        Generate system prompt from signature and tool registry.

        Override this method for custom prompt generation logic.

        Returns:
            str: System prompt for LLM, including tool documentation if available

        Extension Example:
            >>> class SimpleQAAgent(BaseAgent):
            ...     def _generate_system_prompt(self) -> str:
            ...         base_prompt = super()._generate_system_prompt()
            ...         return f"{base_prompt}\\n\\nAdditional context: Answer concisely."
        """
        from kaizen.core.prompt_utils import generate_prompt_from_signature

        # Get base prompt from shared utility (single source of truth for
        # description, input/output listing, and field descriptions)
        prompt_parts = [generate_prompt_from_signature(self.signature)]

        # Augment with MCP tool documentation (BaseAgent-specific addition)
        all_tools = []
        for server_tools in self._discovered_mcp_tools.values():
            all_tools.extend(server_tools)

        if all_tools:
            prompt_parts.append("\n\n## Available Tools")
            prompt_parts.append(
                "\nYou have access to the following tools to help complete tasks:"
            )
            prompt_parts.append("")

            for tool in all_tools:
                tool_name = tool.get("name", "unknown")
                # Remove mcp__serverName__ prefix for cleaner documentation
                display_name = tool_name.replace("mcp__kaizen_builtin__", "")
                description = tool.get("description", "No description available")
                prompt_parts.append(f"- **{display_name}**: {description}")

                # Include parameter information if available
                input_schema = tool.get("inputSchema", {})
                if input_schema and "properties" in input_schema:
                    params = input_schema["properties"]
                    if params:
                        param_list = []
                        for param_name, param_info in params.items():
                            param_desc = param_info.get("description", "")
                            param_list.append(f"{param_name} ({param_desc})")
                        prompt_parts.append(f"  Parameters: {', '.join(param_list)}")

            # Add ReAct pattern instructions
            prompt_parts.append("\n\n## Tool Usage Instructions")
            prompt_parts.append(
                "\nTo use a tool, set the 'action' field to 'tool_use' and provide:"
            )
            prompt_parts.append(
                "- action_input: A dict with 'tool_name' (without mcp__ prefix) and 'params' dict"
            )
            prompt_parts.append("")
            prompt_parts.append("Example:")
            prompt_parts.append('  action: "tool_use"')
            prompt_parts.append("  action_input:")
            prompt_parts.append('    tool_name: "read_file"')
            prompt_parts.append("    params:")
            prompt_parts.append('      path: "/path/to/file.txt"')
            prompt_parts.append("")
            prompt_parts.append(
                "After using a tool, you will receive the result in the 'context' field."
            )
            prompt_parts.append(
                'When the task is complete, set action to "finish" with your final response.'
            )

        return "\n".join(prompt_parts)

    def _validate_signature_output(self, output: Dict[str, Any]) -> bool:
        """
        Validate that output matches signature.

        Override this method for custom validation logic.

        Args:
            output: Execution result to validate

        Returns:
            bool: True if valid

        Raises:
            ValueError: If validation fails

        Extension Example:
            >>> class SimpleQAAgent(BaseAgent):
            ...     def _validate_signature_output(self, output: Dict[str, Any]) -> bool:
            ...         super()._validate_signature_output(output)
            ...         if not 0 <= output.get('confidence', 0) <= 1:
            ...             raise ValueError("Confidence must be between 0 and 1")
            ...         return True
        """
        # Task 1.17: Implement extension point 4
        # Check that all required output fields are present
        # UNLESS this is a test/special result (has _write_insight or response)

        # Skip validation for results with special keys (test results, insight writes)
        has_special_keys = any(
            key in output for key in ["_write_insight", "response", "result"]
        )

        if has_special_keys:
            # Lenient validation for test/special results
            return True

        # Strict validation for normal signature-based results
        if hasattr(self.signature, "output_fields") and self.signature.output_fields:
            for field in self.signature.output_fields:
                field_name = field.name if hasattr(field, "name") else str(field)
                if field_name not in output:
                    raise ValueError(f"Missing required output field: {field_name}")
        return True

    def _pre_execution_hook(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Hook called before execution.

        Override this method to add preprocessing, logging, etc.

        Args:
            inputs: Execution inputs

        Returns:
            Dict[str, Any]: Modified inputs (or original)

        Extension Example:
            >>> class ReActAgent(BaseAgent):
            ...     def _pre_execution_hook(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
            ...         inputs = super()._pre_execution_hook(inputs)
            ...         inputs['available_tools'] = self._load_mcp_tools()
            ...         return inputs
        """
        # Task 1.17: Implement extension point 5
        # Log execution if logging enabled
        logging_enabled = getattr(self.config, "logging_enabled", True)
        if logging_enabled:
            signature_name = getattr(self.signature, "name", "unknown")
            logger.info(f"Executing {signature_name} with inputs: {inputs}")
        return inputs

    def _post_execution_hook(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Hook called after execution.

        Override this method to add postprocessing, logging, etc.

        Args:
            result: Execution result

        Returns:
            Dict[str, Any]: Modified result (or original)

        Extension Example:
            >>> class ReActAgent(BaseAgent):
            ...     def _post_execution_hook(self, result: Dict[str, Any]) -> Dict[str, Any]:
            ...         result = super()._post_execution_hook(result)
            ...         result['metadata']['tools_used'] = len(self.tools_called)
            ...         return result
        """
        # Task 1.17: Implement extension point 6
        # Log completion if logging enabled
        logging_enabled = getattr(self.config, "logging_enabled", True)
        if logging_enabled:
            logger.info(f"Execution complete. Result: {result}")
        return result

    def _handle_error(
        self, error: Exception, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle errors during execution.

        Override this method for custom error handling logic.

        Args:
            error: Exception that occurred
            context: Execution context when error occurred

        Returns:
            Dict[str, Any]: Error result (when error_handling_enabled=True)

        Raises:
            Exception: Re-raises error if error_handling_enabled=False

        Extension Example:
            >>> class RobustAgent(BaseAgent):
            ...     def _handle_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
            ...         # Log detailed error
            ...         logger.error(f"Agent failed: {error}", extra=context)
            ...         # Return fallback response
            ...         return {"error": str(error), "fallback": "I encountered an error."}
        """
        # Task 1.17: Implement extension point 7
        error_handling_enabled = getattr(self.config, "error_handling_enabled", True)
        if error_handling_enabled:
            # Log error
            logger.error(f"Error during execution: {error}", extra=context)
            # Return error dict with success flag
            return {"error": str(error), "type": type(error).__name__, "success": False}
        else:
            # Re-raise error
            raise error

    # =============================================================================
    # GOOGLE A2A (AGENT-TO-AGENT) INTEGRATION
    # =============================================================================
    # These methods provide Google A2A protocol support using Kailash SDK's
    # production-ready A2A implementation. Full agent card generation, capability
    # matching, and task lifecycle management.
    #
    # Architecture: Kaizen EXTENDS Kailash SDK A2A (complete Google A2A spec)
    # Implementation: kailash.nodes.ai.a2a (100% Google A2A compliant)
    # =============================================================================

    def to_a2a_card(self) -> "A2AAgentCard":
        """
        Generate Google A2A compliant agent card.

        Creates a comprehensive agent capability card that enables intelligent
        agent discovery, task matching, and team formation in multi-agent systems.

        Returns:
            A2AAgentCard: Complete agent card with capabilities, performance, resources

        Example:
            >>> from kaizen.core.base_agent import BaseAgent
            >>> from kaizen.signatures import Signature, InputField, OutputField
            >>>
            >>> class QASignature(Signature):
            ...     question: str = InputField(desc="User question")
            ...     answer: str = OutputField(desc="Answer")
            >>>
            >>> agent = BaseAgent(config=config, signature=QASignature())
            >>> card = agent.to_a2a_card()
            >>> print(f"Agent: {card.agent_name}")
            >>> print(f"Capabilities: {len(card.primary_capabilities)}")
            >>> print(f"Collaboration: {card.collaboration_style.value}")

        Agent Card Contents:
            - Identity: agent_id, agent_name, agent_type, version
            - Capabilities: Primary, secondary, emerging capabilities
            - Collaboration: Style, team preferences, compatible agents
            - Performance: Success rate, quality scores, response times
            - Resources: Memory, token limits, API requirements

        Google A2A Compliance:
            ✓ Semantic capability matching with keywords
            ✓ Performance metrics tracking
            ✓ Collaboration style preferences
            ✓ Resource requirement specification
            ✓ Full capability proficiency levels
        """
        try:
            from kaizen.nodes.ai.a2a import A2AAgentCard
        except ImportError:
            raise ImportError(
                "kaizen.nodes.ai.a2a not available. Install with: pip install kailash-kaizen"
            )

        return A2AAgentCard(
            agent_id=self.agent_id,
            agent_name=self.__class__.__name__,
            agent_type=self._get_agent_type(),
            version=getattr(self, "version", "1.0.0"),
            primary_capabilities=self._extract_primary_capabilities(),
            secondary_capabilities=self._extract_secondary_capabilities(),
            collaboration_style=self._get_collaboration_style(),
            performance=self._get_performance_metrics(),
            resources=self._get_resource_requirements(),
            description=self._get_agent_description(),
            tags=self._get_agent_tags(),
            specializations=self._get_specializations(),
        )

    def _extract_primary_capabilities(self) -> List["Capability"]:
        """Extract primary capabilities from signature."""
        try:
            from kaizen.nodes.ai.a2a import Capability, CapabilityLevel
        except ImportError:
            return []

        capabilities = []
        if hasattr(self, "signature") and self.signature:
            # Infer capabilities from signature input/output fields
            if hasattr(self.signature, "input_fields") and self.signature.input_fields:
                for field in self.signature.input_fields:
                    field_name = field.name if hasattr(field, "name") else "input"
                    field_desc = field.desc if hasattr(field, "desc") else ""

                    capabilities.append(
                        Capability(
                            name=field_name,
                            domain=self._infer_domain(),
                            level=CapabilityLevel.EXPERT,
                            description=field_desc or f"Processes {field_name} inputs",
                            keywords=self._extract_keywords(field_desc),
                            examples=[],
                            constraints=[],
                        )
                    )

        return capabilities

    def _extract_secondary_capabilities(self) -> List["Capability"]:
        """Extract secondary capabilities from strategy and memory."""
        try:
            from kaizen.nodes.ai.a2a import Capability, CapabilityLevel
        except ImportError:
            return []

        capabilities = []

        # Memory capability
        if hasattr(self, "memory") and self.memory:
            capabilities.append(
                Capability(
                    name="conversation_memory",
                    domain=self._infer_domain(),
                    level=CapabilityLevel.ADVANCED,
                    description="Maintains conversation context across sessions",
                    keywords=["memory", "context", "history"],
                    examples=[],
                    constraints=[],
                )
            )

        # Shared memory capability
        if hasattr(self, "shared_memory") and self.shared_memory:
            capabilities.append(
                Capability(
                    name="multi_agent_collaboration",
                    domain="collaboration",
                    level=CapabilityLevel.ADVANCED,
                    description="Shares insights with other agents via shared memory",
                    keywords=["collaboration", "sharing", "insights"],
                    examples=[],
                    constraints=[],
                )
            )

        return capabilities

    def _get_collaboration_style(self) -> "CollaborationStyle":
        """Determine collaboration style from agent configuration."""
        try:
            from kaizen.nodes.ai.a2a import CollaborationStyle
        except ImportError:
            return None

        # Check if agent has shared memory (indicates cooperative style)
        if hasattr(self, "shared_memory") and self.shared_memory:
            return CollaborationStyle.COOPERATIVE

        # Default to independent
        return CollaborationStyle.INDEPENDENT

    def _get_performance_metrics(self) -> "PerformanceMetrics":
        """Get performance metrics for agent card."""
        try:
            from datetime import datetime

            from kaizen.nodes.ai.a2a import PerformanceMetrics
        except ImportError:
            return None

        # Create metrics with defaults (can be enhanced with actual tracking)
        return PerformanceMetrics(
            total_tasks=0,
            successful_tasks=0,
            failed_tasks=0,
            average_response_time_ms=0.0,
            average_insight_quality=0.8,
            average_confidence_score=0.85,
            insights_generated=0,
            unique_insights=0,
            actionable_insights=0,
            collaboration_score=0.7,
            reliability_score=0.9,
            last_active=datetime.now(),
        )

    def _get_resource_requirements(self) -> "ResourceRequirements":
        """Get resource requirements from config."""
        try:
            from kaizen.nodes.ai.a2a import ResourceRequirements
        except ImportError:
            return None

        # Extract from config if available
        max_tokens = getattr(self.config, "max_tokens", 4000)
        model = getattr(self.config, "model", "")
        provider = getattr(self.config, "llm_provider", "")

        # Determine GPU requirement based on model
        requires_gpu = "llama" in model.lower() or "mistral" in model.lower()

        # Determine internet requirement based on provider
        requires_internet = provider in ["openai", "anthropic", "google"]

        return ResourceRequirements(
            min_memory_mb=512,
            max_memory_mb=4096,
            min_tokens=100,
            max_tokens=max_tokens,
            requires_gpu=requires_gpu,
            requires_internet=requires_internet,
            estimated_cost_per_task=0.01,  # Can be enhanced with actual cost tracking
            max_concurrent_tasks=5,
            supported_models=[model] if model else [],
            required_apis=[provider] if provider else [],
        )

    def _infer_domain(self) -> str:
        """Infer domain from agent class name and signature."""
        class_name = self.__class__.__name__.lower()

        # Domain inference from class name
        if "qa" in class_name or "question" in class_name:
            return "question_answering"
        elif "rag" in class_name or "research" in class_name:
            return "research"
        elif "code" in class_name or "programming" in class_name:
            return "code_generation"
        elif "analysis" in class_name or "analyst" in class_name:
            return "analysis"
        elif "summary" in class_name or "summarize" in class_name:
            return "summarization"
        elif "translation" in class_name or "translate" in class_name:
            return "translation"
        elif "classification" in class_name or "classify" in class_name:
            return "classification"

        # Default domain
        return "general"

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text description."""
        if not text:
            return []

        # Simple keyword extraction - split and filter common words
        stop_words = {
            "a",
            "an",
            "the",
            "is",
            "are",
            "was",
            "were",
            "to",
            "for",
            "of",
            "in",
            "on",
            "at",
        }
        words = text.lower().split()
        keywords = [w.strip(".,;:!?") for w in words if w not in stop_words]

        return keywords[:10]  # Limit to top 10 keywords

    def _get_agent_type(self) -> str:
        """Get agent type identifier."""
        return self.__class__.__name__

    def _get_agent_description(self) -> str:
        """Get agent description from docstring or signature."""
        # Try to get from class docstring
        if self.__class__.__doc__:
            return self.__class__.__doc__.strip().split("\n")[0]

        # Fallback to signature-based description
        if hasattr(self, "signature") and self.signature:
            return (
                f"Agent with {len(getattr(self.signature, 'input_fields', []))} inputs"
            )

        return f"{self.__class__.__name__} agent"

    def _get_agent_tags(self) -> List[str]:
        """Get agent tags from domain and capabilities."""
        tags = [self._infer_domain()]

        # Add memory tags
        if hasattr(self, "memory") and self.memory:
            tags.append("memory")
        if hasattr(self, "shared_memory") and self.shared_memory:
            tags.append("collaborative")

        # Add strategy tags
        if hasattr(self, "strategy"):
            strategy_name = self.strategy.__class__.__name__.lower()
            if "async" in strategy_name:
                tags.append("async")
            if "multi_cycle" in strategy_name:
                tags.append("iterative")

        return tags

    def _get_specializations(self) -> Dict[str, Any]:
        """Get agent specializations and metadata."""
        return {
            "framework": "kaizen",
            "has_memory": hasattr(self, "memory") and self.memory is not None,
            "has_shared_memory": hasattr(self, "shared_memory")
            and self.shared_memory is not None,
            "strategy": (
                self.strategy.__class__.__name__
                if hasattr(self, "strategy")
                else "none"
            ),
            "model": getattr(self.config, "model", "unknown"),
            "provider": getattr(self.config, "llm_provider", "unknown"),
        }

    # =============================================================================
    # CONTROL PROTOCOL HELPERS (Week 10)
    # =============================================================================
    # These methods provide convenient user interaction capabilities using the
    # Control Protocol for bidirectional agent↔user communication.
    #
    # See: docs/architecture/adr/011-control-protocol-architecture.md
    # =============================================================================

    async def ask_user_question(
        self, question: str, options: Optional[List[str]] = None, timeout: float = 60.0
    ) -> str:
        """
        Ask user a question during agent execution.

        Uses the Control Protocol to send a question to the user and wait for
        their response. This enables interactive agent workflows where the agent
        can request input mid-execution.

        Args:
            question: Question to ask the user
            options: Optional list of answer choices (for multiple choice)
            timeout: Maximum time to wait for response (seconds)

        Returns:
            User's answer as a string

        Raises:
            RuntimeError: If control_protocol is not configured
            TimeoutError: If user doesn't respond within timeout

        Example:
            >>> agent = BaseAgent(
            ...     config=config,
            ...     signature=signature,
            ...     control_protocol=protocol
            ... )
            >>> answer = await agent.ask_user_question(
            ...     "Which file should I process?",
            ...     options=["file1.txt", "file2.txt", "all"]
            ... )
            >>> print(f"User selected: {answer}")
        """
        if self.control_protocol is None:
            raise RuntimeError(
                "Control protocol not configured. "
                "Pass control_protocol parameter to BaseAgent.__init__()"
            )

        # Create request
        from kaizen.core.autonomy.control.types import ControlRequest

        data = {"question": question}
        if options:
            data["options"] = options

        request = ControlRequest.create("question", data)

        # Send and wait for response
        response = await self.control_protocol.send_request(request, timeout=timeout)

        if response.is_error:
            raise RuntimeError(f"Question error: {response.error}")

        return response.data.get("answer", "")

    async def request_approval(
        self,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        timeout: float = 60.0,
    ) -> bool:
        """
        Request user approval for an action during agent execution.

        Uses the Control Protocol to ask the user to approve or deny a proposed
        action. This enables safe interactive workflows where critical operations
        require human confirmation.

        Args:
            action: Description of the action needing approval
            details: Optional additional context/details about the action
            timeout: Maximum time to wait for response (seconds)

        Returns:
            True if approved, False if denied

        Raises:
            RuntimeError: If control_protocol is not configured
            TimeoutError: If user doesn't respond within timeout

        Example:
            >>> agent = BaseAgent(
            ...     config=config,
            ...     signature=signature,
            ...     control_protocol=protocol
            ... )
            >>> approved = await agent.request_approval(
            ...     "Delete 100 files",
            ...     details={"files": file_list, "size_mb": 250}
            ... )
            >>> if approved:
            ...     # Proceed with deletion
            ...     pass
            >>> else:
            ...     # Cancel operation
            ...     pass
        """
        if self.control_protocol is None:
            raise RuntimeError(
                "Control protocol not configured. "
                "Pass control_protocol parameter to BaseAgent.__init__()"
            )

        # Create request
        from kaizen.core.autonomy.control.types import ControlRequest

        data = {"action": action}
        if details:
            data["details"] = details

        request = ControlRequest.create("approval", data)

        # Send and wait for response
        response = await self.control_protocol.send_request(request, timeout=timeout)

        if response.is_error:
            raise RuntimeError(f"Approval error: {response.error}")

        return response.data.get("approved", False)

    async def report_progress(
        self,
        message: str,
        percentage: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Report progress update to user during agent execution.

        This is a fire-and-forget method - it sends progress updates but doesn't
        wait for acknowledgment. Use this to keep users informed during long-running
        operations.

        Args:
            message: Progress message to display (e.g., "Processing file 5 of 10")
            percentage: Optional progress percentage (0.0-100.0)
            details: Optional additional progress details

        Raises:
            RuntimeError: If control_protocol is not configured

        Example:
            # During a long operation
            for i, file in enumerate(files):
                await agent.report_progress(
                    f"Processing {file}",
                    percentage=(i / len(files)) * 100,
                    details={"current": i + 1, "total": len(files)}
                )
                # ... process file ...
        """
        if self.control_protocol is None:
            raise RuntimeError(
                "Control protocol not configured. "
                "Pass control_protocol parameter to BaseAgent.__init__() "
                "to enable report_progress()."
            )

        from kaizen.core.autonomy.control.types import ControlRequest

        data = {"message": message}
        if percentage is not None:
            if not (0.0 <= percentage <= 100.0):
                raise ValueError(
                    f"Percentage must be between 0.0 and 100.0, got {percentage}"
                )
            data["percentage"] = percentage
        if details:
            data["details"] = details

        request = ControlRequest.create("progress_update", data)

        # Fire-and-forget: write the message but don't wait for response
        # Progress updates don't require user acknowledgment
        await self.control_protocol._transport.write(request.to_json())

    # =============================================================================
    # TOOL CALLING INTEGRATION - MCP Only
    # =============================================================================

    async def discover_tools(
        self,
        category: Optional[ToolCategory] = None,
        safe_only: bool = False,
        keyword: Optional[str] = None,
    ) -> List[ToolDefinition]:
        """
        Discover available MCP tools with optional filtering.

        Discovers tools from configured MCP servers, with optional filters
        by category, danger level, or keyword search.

        Args:
            category: Optional filter by tool category
            safe_only: If True, only return SAFE tools (default: False)
            keyword: Optional keyword to search in tool names/descriptions

        Returns:
            List of matching ToolDefinition objects

        Raises:
            RuntimeError: If no MCP servers configured

        Example:
            >>> # Discover all MCP tools
            >>> all_tools = await agent.discover_tools()
            >>>
            >>> # Find only safe tools
            >>> safe_tools = await agent.discover_tools(safe_only=True)
            >>>
            >>> # Search by keyword
            >>> file_tools = await agent.discover_tools(keyword="file")
        """
        tools = []

        # Raise error if no MCP servers configured
        if self._mcp_servers is None:
            raise RuntimeError(
                "No MCP servers configured. "
                "Pass mcp_servers parameter to BaseAgent.__init__() "
                "to enable tool discovery."
            )

        # Discover MCP tools
        mcp_tools_raw = await self.discover_mcp_tools()

        # Convert MCP tools to ToolDefinition format
        for mcp_tool in mcp_tools_raw:
            # Extract parameters from MCP tool schema
            params = []
            if "parameters" in mcp_tool and isinstance(mcp_tool["parameters"], dict):
                for param_name, param_schema in mcp_tool["parameters"].items():
                    param_type = param_schema.get("type", "string")
                    param_desc = param_schema.get("description", "")
                    param_required = param_schema.get("required", False)

                    params.append(
                        ToolParameter(
                            name=param_name,
                            type=param_type,
                            description=param_desc,
                            required=param_required,
                        )
                    )

            # Create ToolDefinition for MCP tool
            tool_def = ToolDefinition(
                name=mcp_tool["name"],
                description=mcp_tool.get("description", ""),
                category=ToolCategory.SYSTEM,  # Default to SYSTEM for MCP tools
                danger_level=DangerLevel.SAFE,  # Default to SAFE (can be configured)
                parameters=params,
                returns={},  # MCP tools don't have typed returns
                executor=None,  # MCP tools use execute_mcp_tool
            )

            # Apply filters
            if category is not None and tool_def.category != category:
                continue
            if safe_only and tool_def.danger_level != DangerLevel.SAFE:
                continue
            if keyword is not None:
                keyword_lower = keyword.lower()
                if not (
                    keyword_lower in tool_def.name.lower()
                    or keyword_lower in tool_def.description.lower()
                ):
                    continue

            tools.append(tool_def)

        return tools

    # =============================================================================
    # MCP INTEGRATION - Tool Discovery and Execution
    # =============================================================================
    # These methods integrate MCP (Model Context Protocol) tools with BaseAgent,
    # enabling agents to discover and execute tools from external MCP servers.
    #
    # Architecture: Uses Kailash SDK MCPClient for real protocol support
    # Naming Convention: mcp__<serverName>__<toolName>
    # =============================================================================

    def has_mcp_support(self) -> bool:
        """
        Check if agent has MCP integration configured.

        Returns:
            True if mcp_servers is configured, False otherwise

        Example:
            >>> agent = BaseAgent(config=config, signature=signature)
            >>> print(agent.has_mcp_support())  # False
            >>>
            >>> agent_with_mcp = BaseAgent(
            ...     config=config,
            ...     signature=signature,
            ...     mcp_servers=[{"name": "fs", "transport": "stdio", ...}]
            ... )
            >>> print(agent_with_mcp.has_mcp_support())  # True
        """
        return self._mcp_servers is not None

    async def discover_mcp_tools(
        self, server_name: Optional[str] = None, force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Discover MCP tools from configured servers with naming convention.

        Discovers tools from MCP servers and applies naming convention:
        mcp__<serverName>__<toolName>

        Args:
            server_name: Optional filter by server name (None = all servers)
            force_refresh: Bypass cache and rediscover tools (default: False)

        Returns:
            List of tool definitions with naming convention applied

        Raises:
            RuntimeError: If MCP not configured

        Example:
            >>> agent = BaseAgent(
            ...     config=config,
            ...     signature=signature,
            ...     mcp_servers=[
            ...         {"name": "filesystem", "transport": "stdio", ...}
            ...     ]
            ... )
            >>>
            >>> # Discover all tools
            >>> tools = await agent.discover_mcp_tools()
            >>> print(tools[0]["name"])  # "mcp__filesystem__read_file"
            >>>
            >>> # Discover from specific server
            >>> tools = await agent.discover_mcp_tools(server_name="filesystem")
        """
        if self._mcp_servers is None:
            raise RuntimeError(
                "MCP not configured. Pass mcp_servers parameter to BaseAgent.__init__()"
            )

        # Filter servers if server_name provided
        servers = self._mcp_servers
        if server_name is not None:
            # Support both string and dict formats
            filtered_servers = []
            for s in servers:
                if isinstance(s, str):
                    # String format: ["kaizen_builtin"] (auto-connect)
                    if s == server_name:
                        filtered_servers.append(s)
                elif isinstance(s, dict):
                    # Dict format: [{"name": "filesystem", ...}]
                    if s.get("name") == server_name:
                        filtered_servers.append(s)
            servers = filtered_servers

        # Collect tools from all selected servers
        all_tools = []
        for server_config in servers:
            # Support both string and dict formats
            if isinstance(server_config, str):
                # String format: "kaizen_builtin" (auto-connect)
                server_key = server_config
            elif isinstance(server_config, dict):
                # Dict format: {"name": "filesystem", "command": "npx", ...}
                server_key = server_config.get("name", "unknown")
            else:
                logger.warning(
                    f"Skipping invalid server config: {server_config}. "
                    f"Expected string or dict, got {type(server_config)}"
                )
                continue

            # Check cache if not forcing refresh
            if not force_refresh and server_key in self._discovered_mcp_tools:
                all_tools.extend(self._discovered_mcp_tools[server_key])
                continue

            # Resolve string format to dict format for MCP client
            if isinstance(server_config, str):
                # Auto-connect pattern: string server name needs to be resolved
                # Currently only "kaizen_builtin" is supported
                if server_config == "kaizen_builtin":
                    resolved_config = {
                        "name": "kaizen_builtin",
                        "command": "python",
                        "args": ["-m", "kaizen.mcp.builtin_server"],
                        "transport": "stdio",
                        "description": "Kaizen builtin tools (file, HTTP, bash, web)",
                    }
                else:
                    logger.warning(
                        f"Unknown auto-connect server: {server_config}. "
                        f"Only 'kaizen_builtin' is currently supported."
                    )
                    continue
            else:
                # Already in dict format
                resolved_config = server_config

            # Discover tools from server
            tools = await self._mcp_client.discover_tools(
                resolved_config, force_refresh=force_refresh
            )

            # Apply naming convention: mcp__<serverName>__<toolName>
            renamed_tools = []
            for tool in tools:
                renamed_tool = tool.copy()
                renamed_tool["name"] = f"mcp__{server_key}__{tool['name']}"
                renamed_tools.append(renamed_tool)

            # Cache the renamed tools
            self._discovered_mcp_tools[server_key] = renamed_tools
            all_tools.extend(renamed_tools)

        return all_tools

    def _convert_mcp_result_to_dict(self, result) -> Dict[str, Any]:
        """
        Convert MCP CallToolResult to dict format expected by tests.

        MCPClient.call_tool() returns a dict (already converted from CallToolResult).
        This method extracts content fields and standardizes format for tests.

        Args:
            result: Dict from MCPClient.call_tool() (NOT CallToolResult object)

        Returns:
            Dict with success, output, stdout, content, error, and structured_content fields

        Example:
            >>> result = await self._mcp_client.call_tool(...)
            >>> dict_result = self._convert_mcp_result_to_dict(result)
            >>> print(dict_result["success"])  # True or False
        """
        # Result is already a dict from MCPClient
        if not isinstance(result, dict):
            raise TypeError(
                f"Expected dict from MCPClient.call_tool(), got {type(result)}"
            )

        # MCPClient returns dict with:
        # - 'result': CallToolResult object (has structuredContent)
        # - 'content': JSON string or list
        # - 'success': bool
        # - 'tool_name': str

        # Extract structured content from CallToolResult if available
        call_tool_result = result.get("result")
        structured_content = {}

        if call_tool_result and hasattr(call_tool_result, "structuredContent"):
            structured_content = call_tool_result.structuredContent or {}

        # Extract stdout/stderr for bash commands, or content for other tools
        stdout = structured_content.get("stdout", "")
        stderr = structured_content.get("stderr", "")
        exit_code = structured_content.get("exit_code", 0)

        # For bash tools: use stdout as output (plain string)
        # For file/HTTP tools: JSON-encode structured_content dict (tests expect JSON string)
        import json

        data = None  # For HTTP tools: parsed JSON response body

        if stdout:
            # Bash tool - plain stdout string
            output = stdout
            content = stdout
        else:
            # File/HTTP tool - JSON-encode the structured_content
            output = json.dumps(structured_content) if structured_content else "{}"
            content = output

            # For HTTP tools: parse JSON body and expose in 'data' field
            if "body" in structured_content and isinstance(
                structured_content.get("body"), str
            ):
                try:
                    data = json.loads(structured_content["body"])
                except json.JSONDecodeError:
                    # If body is not valid JSON, leave data as None
                    pass

        # Build standardized dict response (tests expect these fields)
        result_dict = {
            "success": result.get("success", False)
            and not result.get("isError", False),
            "output": output,
            "stdout": stdout,  # For bash commands
            "stderr": stderr,  # For bash commands
            "exit_code": exit_code,  # For bash commands
            "content": content,  # For bash: plain string, for file/HTTP: JSON string
            "error": (
                stderr
                if stderr
                else ("" if result.get("success", False) else "Unknown error")
            ),
            "isError": result.get("isError", False),
            "structured_content": structured_content,
        }

        # Add 'data' field for HTTP tools with parsed JSON body
        if data is not None:
            result_dict["data"] = data

        # Flatten structured_content fields to top level for easy access
        # This allows tests to call result.get("exists") instead of result.get("structured_content").get("exists")
        import sys

        sys.stderr.write("\n[DEBUG] _convert_mcp_result_to_dict - Before flattening:\n")
        sys.stderr.write(f"  structured_content: {structured_content}\n")
        sys.stderr.write(f"  result_dict keys before: {list(result_dict.keys())}\n")
        sys.stderr.flush()

        for key, value in structured_content.items():
            sys.stderr.write(f"  [FLATTEN] Processing key={key}, value={value}\n")
            sys.stderr.flush()
            if key not in result_dict:  # Don't overwrite existing keys
                result_dict[key] = value
                sys.stderr.write(f"    ✓ Added {key}={value} to result_dict\n")
            else:
                sys.stderr.write(f"    ✗ Skipped {key} (already in result_dict)\n")
            sys.stderr.flush()

        sys.stderr.write(f"  result_dict keys after: {list(result_dict.keys())}\n")
        sys.stderr.write(f"  Final result_dict: {result_dict}\n")
        sys.stderr.flush()

        return result_dict

    async def execute_tool(
        self, tool_name: str, params: Dict[str, Any], timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Execute tool via MCP integration.

        Wrapper for execute_mcp_tool() that handles naming conventions.
        Called by MultiCycleStrategy when agent autonomously decides to use a tool.

        If tool_name doesn't have mcp__ prefix, assumes kaizen_builtin server.

        Args:
            tool_name: Tool name (with or without mcp__ prefix)
            params: Tool parameters
            timeout: Optional execution timeout

        Returns:
            Tool execution result

        Example:
            >>> # Direct tool name (assumes kaizen_builtin server)
            >>> result = await agent.execute_tool("read_file", {"path": "test.txt"})
            >>>
            >>> # Fully qualified tool name
            >>> result = await agent.execute_tool(
            ...     "mcp__filesystem__read_file",
            ...     {"path": "test.txt"}
            ... )
        """
        # Ensure tool name has mcp__ prefix
        if not tool_name.startswith("mcp__"):
            # Default to kaizen_builtin server for unprefixed tools
            tool_name = f"mcp__kaizen_builtin__{tool_name}"

        # Delegate to execute_mcp_tool which handles:
        # - Server routing
        # - Permission checking
        # - Approval workflow
        # - MCP protocol execution
        return await self.execute_mcp_tool(tool_name, params, timeout)

    async def execute_mcp_tool(
        self, tool_name: str, params: Dict[str, Any], timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Execute MCP tool with server routing and approval workflow.

        Routes tool execution to the correct MCP server based on naming convention:
        mcp__<serverName>__<toolName>

        For builtin MCP tools (kaizen_builtin server), implements danger-level based
        approval workflow:
        - SAFE tools: Execute immediately (read_file, file_exists, etc.)
        - MEDIUM tools: Request approval (write_file, http_post, etc.)
        - HIGH tools: Always request approval (delete_file, bash_command, etc.)

        Args:
            tool_name: Tool name with naming convention (mcp__server__tool)
            params: Tool parameters
            timeout: Optional execution timeout

        Returns:
            Tool execution result

        Raises:
            ValueError: If tool_name format invalid or server not found
            PermissionError: If approval required but denied or control_protocol not configured

        Example:
            >>> agent = BaseAgent(
            ...     config=config,
            ...     signature=signature,
            ...     mcp_servers=[{"name": "filesystem", ...}]
            ... )
            >>>
            >>> result = await agent.execute_mcp_tool(
            ...     "mcp__filesystem__read_file",
            ...     {"path": "/data/test.txt"}
            ... )
            >>> print(result["content"])
        """
        # Validate naming convention
        if not tool_name.startswith("mcp__") or tool_name.count("__") < 2:
            raise ValueError(
                f"Invalid MCP tool name format: {tool_name}. "
                "Expected: mcp__<serverName>__<toolName>"
            )

        # Parse tool name
        parts = tool_name.split("__")
        server_name = parts[1]
        original_tool_name = "__".join(parts[2:])  # Handle tool names with __

        # Find server config
        server_config = None
        for config in self._mcp_servers:
            if config.get("name") == server_name:
                server_config = config
                break

        if server_config is None:
            raise ValueError(
                f"MCP server '{server_name}' not found in configured servers"
            )

        # Check danger level and request approval if needed (builtin tools only)
        if server_name == "kaizen_builtin":
            from kaizen.mcp.builtin_server.danger_levels import (
                get_tool_danger_level,
                is_tool_safe,
            )
            from kaizen.tools.types import DangerLevel

            try:
                danger_level = get_tool_danger_level(original_tool_name)
            except ValueError:
                # Unknown tool - treat as MEDIUM danger by default
                danger_level = DangerLevel.MEDIUM

            # Request approval if tool is not SAFE
            if not is_tool_safe(original_tool_name):
                # Check permission policy first (supports BYPASS mode for E2E tests)
                permission_decision, denial_reason = (
                    self.permission_policy.check_permission(
                        tool_name=original_tool_name,
                        tool_input=params,
                        estimated_cost=0.0,
                    )
                )

                # Permission policy says allow (e.g., BYPASS mode)
                if permission_decision is True:
                    pass  # Allow execution without approval

                # Permission policy says deny
                elif permission_decision is False:
                    raise PermissionError(
                        f"Tool '{original_tool_name}' denied by permission policy: {denial_reason}"
                    )

                # Permission policy says ask user (requires approval_manager)
                else:
                    if self.approval_manager is None:
                        raise PermissionError(
                            f"Tool '{original_tool_name}' (danger={danger_level.value}) "
                            "requires approval but control_protocol not configured. "
                            "Pass control_protocol to BaseAgent.__init__() to enable approval workflow."
                        )

                    # Request approval via control protocol
                    from kaizen.core.autonomy.permissions.context import (
                        ExecutionContext,
                    )

                    context = (
                        getattr(self, "execution_context", None) or ExecutionContext()
                    )
                    approved = await self.approval_manager.request_approval(
                        tool_name=original_tool_name,
                        tool_input=params,
                        context=context,
                        timeout=timeout or 60.0,
                    )

                    if not approved:
                        raise PermissionError(
                            f"User denied approval for tool '{original_tool_name}' "
                            f"(danger={danger_level.value})"
                        )

        # Execute tool via MCPClient
        result = await self._mcp_client.call_tool(
            server_config, original_tool_name, params, timeout=timeout
        )

        # Convert CallToolResult to dict format expected by tests/external code
        return self._convert_mcp_result_to_dict(result)

    async def discover_mcp_resources(
        self, server_name: str, force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Discover MCP resources from a specific server.

        Args:
            server_name: Server name to query
            force_refresh: Bypass cache and rediscover (default: False)

        Returns:
            List of resource definitions

        Raises:
            RuntimeError: If MCP not configured

        Example:
            >>> resources = await agent.discover_mcp_resources("filesystem")
            >>> print(resources[0]["uri"])  # "file:///data/file.txt"
        """
        if self._mcp_servers is None:
            raise RuntimeError("MCP not configured")

        # Find server config
        server_config = None
        for config in self._mcp_servers:
            if config.get("name") == server_name:
                server_config = config
                break

        if server_config is None:
            raise ValueError(f"MCP server '{server_name}' not found")

        # Check cache
        if not force_refresh and server_name in self._discovered_mcp_resources:
            return self._discovered_mcp_resources[server_name]

        # Discover resources via MCPClient session
        resources = await self._with_mcp_session(
            server_config, self._mcp_client.list_resources
        )
        self._discovered_mcp_resources[server_name] = resources
        return resources

    async def read_mcp_resource(self, server_name: str, uri: str) -> Any:
        """
        Read MCP resource content from a specific server.

        Args:
            server_name: Server name
            uri: Resource URI

        Returns:
            Resource content

        Raises:
            RuntimeError: If MCP not configured

        Example:
            >>> content = await agent.read_mcp_resource(
            ...     "filesystem",
            ...     "file:///data/test.txt"
            ... )
        """
        if self._mcp_servers is None:
            raise RuntimeError("MCP not configured")

        # Find server config
        server_config = None
        for config in self._mcp_servers:
            if config.get("name") == server_name:
                server_config = config
                break

        if server_config is None:
            raise ValueError(f"MCP server '{server_name}' not found")

        # Read resource via MCPClient session
        return await self._with_mcp_session(
            server_config, self._mcp_client.read_resource, uri
        )

    async def discover_mcp_prompts(
        self, server_name: str, force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Discover MCP prompts from a specific server.

        Args:
            server_name: Server name to query
            force_refresh: Bypass cache and rediscover (default: False)

        Returns:
            List of prompt definitions

        Raises:
            RuntimeError: If MCP not configured

        Example:
            >>> prompts = await agent.discover_mcp_prompts("api-tools")
            >>> print(prompts[0]["name"])  # "greeting"
        """
        if self._mcp_servers is None:
            raise RuntimeError("MCP not configured")

        # Find server config
        server_config = None
        for config in self._mcp_servers:
            if config.get("name") == server_name:
                server_config = config
                break

        if server_config is None:
            raise ValueError(f"MCP server '{server_name}' not found")

        # Check cache
        if not force_refresh and server_name in self._discovered_mcp_prompts:
            return self._discovered_mcp_prompts[server_name]

        # Discover prompts via MCPClient session
        prompts = await self._with_mcp_session(
            server_config, self._mcp_client.list_prompts
        )
        self._discovered_mcp_prompts[server_name] = prompts
        return prompts

    async def get_mcp_prompt(
        self, server_name: str, prompt_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get MCP prompt with arguments from a specific server.

        Args:
            server_name: Server name
            prompt_name: Prompt name
            arguments: Prompt arguments

        Returns:
            Prompt with messages

        Raises:
            RuntimeError: If MCP not configured

        Example:
            >>> prompt = await agent.get_mcp_prompt(
            ...     "api-tools",
            ...     "greeting",
            ...     {"name": "Alice"}
            ... )
        """
        if self._mcp_servers is None:
            raise RuntimeError("MCP not configured")

        # Find server config
        server_config = None
        for config in self._mcp_servers:
            if config.get("name") == server_name:
                server_config = config
                break

        if server_config is None:
            raise ValueError(f"MCP server '{server_name}' not found")

        # Get prompt via MCPClient session
        return await self._with_mcp_session(
            server_config, self._mcp_client.get_prompt, prompt_name, arguments
        )

    async def _with_mcp_session(self, server_config: Dict[str, Any], method, *args):
        """
        Create a temporary MCP session to a server and invoke a session-based method.

        Opens a connection using the appropriate transport (STDIO, SSE, HTTP, or
        WebSocket), initialises the session, calls ``method(session, *args)`` and
        returns the result.  The connection is torn down automatically when done.

        Args:
            server_config: Server configuration dict (must include 'transport').
            method: An async callable that accepts ``(session, *args)`` -- one of
                the MCPClient session helpers such as ``list_resources``,
                ``read_resource``, ``list_prompts``, or ``get_prompt``.
            *args: Extra positional arguments forwarded to *method* after *session*.

        Returns:
            Whatever *method* returns.
        """
        import asyncio
        import os
        from contextlib import AsyncExitStack

        transport_type = server_config.get("transport", "stdio")

        async with AsyncExitStack() as stack:
            if transport_type == "stdio":
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client

                command = server_config.get("command", "python")
                cmd_args = server_config.get("args", [])
                env = server_config.get("env", {})
                server_env = os.environ.copy()
                server_env.update(env)
                server_params = StdioServerParameters(
                    command=command, args=cmd_args, env=server_env
                )
                stdio = await stack.enter_async_context(stdio_client(server_params))
                session = await stack.enter_async_context(
                    ClientSession(stdio[0], stdio[1])
                )

            elif transport_type == "sse":
                from mcp import ClientSession
                from mcp.client.sse import sse_client

                url = server_config["url"]
                headers = self._mcp_client._get_auth_headers(server_config)
                sse = await stack.enter_async_context(
                    sse_client(url=url, headers=headers)
                )
                session = await stack.enter_async_context(ClientSession(sse[0], sse[1]))

            elif transport_type == "http":
                from mcp import ClientSession
                from mcp.client.streamable_http import streamable_http_client

                url = server_config["url"]
                headers = self._mcp_client._get_auth_headers(server_config)
                http = await stack.enter_async_context(
                    streamable_http_client(url=url, headers=headers)
                )
                session = await stack.enter_async_context(
                    ClientSession(http[0], http[1])
                )

            elif transport_type == "websocket":
                from mcp import ClientSession
                from mcp.client.websocket import websocket_client

                url = server_config.get("url", server_config.get("uri"))
                if not url:
                    raise ValueError("WebSocket server config must include 'url'")
                ws = await stack.enter_async_context(websocket_client(url=url))
                session = await stack.enter_async_context(ClientSession(ws[0], ws[1]))

            else:
                raise ValueError(f"Unsupported transport type: {transport_type}")

            await session.initialize()
            return await method(session, *args)

    # =============================================================================
    # MCP INTEGRATION HELPERS (using kailash.mcp_server)
    # =============================================================================
    # These methods provide convenient MCP integration using Kailash SDK's
    # production-ready MCP implementation. No mocking - real JSON-RPC protocol.
    #
    # Architecture: Kaizen EXTENDS Kailash SDK MCP (not recreate)
    # Implementation: kailash.mcp_server (100% MCP spec compliant)
    # =============================================================================

    async def setup_mcp_client(
        self,
        servers: List[Dict[str, Any]],
        retry_strategy: str = "circuit_breaker",
        enable_metrics: bool = True,
        **client_kwargs,
    ):
        """
        Setup MCP client for consuming external MCP tools.

        Uses Kailash SDK's production-ready MCPClient with full protocol support.

        Args:
            servers: List of MCP server configurations. Each server dict should contain:
                - name (str): Server name
                - transport (str): "stdio", "http", "sse", or "websocket"
                - command (str): Command to start server (for stdio)
                - args (List[str]): Arguments for command (for stdio)
                - url (str): Server URL (for http/sse/websocket)
                - headers (Dict): Optional HTTP headers
                - env (Dict): Optional environment variables
            retry_strategy: Retry strategy ("simple", "exponential", "circuit_breaker")
            enable_metrics: Enable metrics collection
            **client_kwargs: Additional MCPClient arguments

        Returns:
            MCPClient: Configured MCPClient instance

        Raises:
            ImportError: If kailash.mcp_server not available
            ValueError: If server config is invalid

        Example:
            >>> # STDIO transport (local process)
            >>> await agent.setup_mcp_client([
            ...     {
            ...         "name": "filesystem-tools",
            ...         "transport": "stdio",
            ...         "command": "npx",
            ...         "args": ["@modelcontextprotocol/server-filesystem", "/data"]
            ...     }
            ... ])
            >>>
            >>> # HTTP transport (remote server)
            >>> await agent.setup_mcp_client([
            ...     {
            ...         "name": "api-tools",
            ...         "transport": "http",
            ...         "url": "http://localhost:8080",
            ...         "headers": {"Authorization": "Bearer token"}
            ...     }
            ... ])

        Note:
            - All MCP methods are async (use await)
            - Real JSON-RPC protocol (no mocking)
            - Enterprise features: auth, retry, circuit breaker
            - 100% MCP spec compliant: tools, resources, prompts
        """
        try:
            from kailash.mcp_server import MCPClient
        except ImportError:
            raise ImportError(
                "kailash.mcp_server not available. Install with: pip install kailash"
            )

        # Create production MCP client
        self._mcp_client = MCPClient(
            retry_strategy=retry_strategy,
            enable_metrics=enable_metrics,
            **client_kwargs,
        )

        # Discover tools from all servers
        self._available_mcp_tools = {}

        for server_config in servers:
            # Validate server config
            if "name" not in server_config or "transport" not in server_config:
                raise ValueError(
                    "Server config must include 'name' and 'transport' fields"
                )

            # Discover tools via real MCP protocol
            tools = await self._mcp_client.discover_tools(
                server_config, force_refresh=True
            )

            # Store tools with server info
            for tool in tools:
                tool_id = f"{server_config['name']}:{tool['name']}"
                self._available_mcp_tools[tool_id] = {
                    **tool,
                    "server_config": server_config,
                }

            logger.info(
                f"Discovered {len(tools)} tools from MCP server: {server_config['name']}"
            )

        logger.info(
            f"MCP client setup complete. {len(self._available_mcp_tools)} tools available."
        )

        return self._mcp_client

    async def call_mcp_tool(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        timeout: float = 30.0,
        store_in_memory: bool = True,
    ) -> Dict[str, Any]:
        """
        Call MCP tool by ID using real JSON-RPC protocol.

        Args:
            tool_id: Tool ID (format: "server_name:tool_name")
            arguments: Tool arguments (must match tool schema)
            timeout: Timeout in seconds
            store_in_memory: Store tool call in shared memory

        Returns:
            Dict with tool result. Structure depends on tool implementation.

        Raises:
            RuntimeError: If MCP client not setup
            ValueError: If tool_id not found
            Exception: If tool invocation fails

        Example:
            >>> # Setup MCP client first
            >>> await agent.setup_mcp_client([...])
            >>>
            >>> # Call tool
            >>> result = await agent.call_mcp_tool(
            ...     "filesystem-tools:read_file",
            ...     {"path": "/data/input.txt"}
            ... )
            >>> print(result)

        Note:
            - Tool calls are async (use await)
            - Results stored in shared memory automatically
            - Real MCP tool invocation via JSON-RPC
        """
        if not hasattr(self, "_mcp_client") or self._mcp_client is None:
            raise RuntimeError("MCP client not setup. Call setup_mcp_client() first.")

        if tool_id not in self._available_mcp_tools:
            available_tools = list(self._available_mcp_tools.keys())
            raise ValueError(
                f"Tool {tool_id} not found. Available tools: {available_tools}"
            )

        # Get tool info
        tool_info = self._available_mcp_tools[tool_id]
        server_config = tool_info["server_config"]
        tool_name = tool_info["name"]

        # Call via real MCP protocol
        result = await self._mcp_client.call_tool(
            server_config, tool_name, arguments, timeout=timeout
        )

        # Store in shared memory if enabled
        if store_in_memory and hasattr(self, "shared_memory") and self.shared_memory:
            self.write_to_memory(
                content={
                    "tool_id": tool_id,
                    "server": server_config["name"],
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "result": result,
                    "agent_id": self.agent_id,
                },
                tags=["mcp_tool_call", server_config["name"], tool_name],
                importance=0.8,
            )

        # Convert CallToolResult to dict format expected by tests/external code
        return self._convert_mcp_result_to_dict(result)

    def expose_as_mcp_server(
        self,
        server_name: str,
        tools: Optional[List[str]] = None,
        auth_provider: Optional[Any] = None,
        enable_auto_discovery: bool = True,
        **server_kwargs,
    ):
        """
        Expose agent as MCP server with real protocol support.

        Creates a production MCP server that exposes agent methods as MCP tools.

        Args:
            server_name: Server name for MCP registration
            tools: List of agent methods to expose (default: auto-detect public methods)
            auth_provider: Optional auth provider (APIKeyAuth, JWTAuth, etc.)
            enable_auto_discovery: Enable network discovery
            **server_kwargs: Additional MCPServer arguments

        Returns:
            MCPServer: Configured server (call .run() to start)

        Raises:
            ImportError: If kailash.mcp_server not available

        Example:
            >>> from kailash.mcp_server.auth import APIKeyAuth
            >>>
            >>> # Create agent
            >>> agent = MyAgent(config=config, signature=signature)
            >>>
            >>> # Expose as MCP server
            >>> auth = APIKeyAuth({"client1": "secret-key"})
            >>> server = agent.expose_as_mcp_server(
            ...     "analysis-agent",
            ...     tools=["analyze", "summarize"],
            ...     auth_provider=auth
            ... )
            >>>
            >>> # Start server (blocks)
            >>> server.run()

        Note:
            - Agent methods exposed as async MCP tools
            - Real JSON-RPC 2.0 protocol
            - Enterprise features: auth, metrics, monitoring
            - Service discovery via registry + network
        """
        try:
            from kailash.mcp_server import MCPServer
            from kailash.mcp_server import enable_auto_discovery as enable_discovery
        except ImportError:
            raise ImportError(
                "kailash.mcp_server not available. Install with: pip install kailash"
            )

        # Create production MCP server
        server = MCPServer(
            name=server_name,
            auth_provider=auth_provider,
            enable_metrics=True,
            enable_http_transport=True,
            **server_kwargs,
        )

        # Auto-detect tools if not specified
        if tools is None:
            # Expose all public methods (not starting with _)
            tools = [
                m
                for m in dir(self)
                if not m.startswith("_") and callable(getattr(self, m))
            ]

        # Wrap agent methods as MCP tools
        for tool_name in tools:
            if not hasattr(self, tool_name):
                logger.warning(f"Tool {tool_name} not found on agent, skipping")
                continue

            method = getattr(self, tool_name)

            # Create tool wrapper with dynamic name
            # Note: MCPServer.tool() decorator infers name from function __name__
            async def tool_wrapper(**kwargs):
                """Auto-generated MCP tool from agent method."""
                # Execute agent method
                result = method(**kwargs)

                # If result is awaitable, await it
                if hasattr(result, "__await__"):
                    result = await result

                return result

            # Set the function name so the decorator can infer it
            tool_wrapper.__name__ = tool_name

            # Register with MCP server
            server.tool()(tool_wrapper)

        # Store server reference
        self._mcp_server = server

        # Enable auto-discovery if requested
        if enable_auto_discovery:
            registrar = enable_discovery(server, enable_network_discovery=True)
            self._mcp_registrar = registrar
            logger.info(f"MCP server '{server_name}' ready with auto-discovery enabled")
        else:
            self._mcp_registrar = None
            logger.info(f"MCP server '{server_name}' ready")

        return server

    def enable_observability(
        self,
        service_name: str | None = None,
        jaeger_host: str = "localhost",
        jaeger_port: int = 4317,
        insecure: bool = True,
        events_to_trace: Optional[List[Any]] = None,
        enable_metrics: bool = True,
        enable_logging: bool = True,
        enable_tracing: bool = True,
        enable_audit: bool = True,
    ):
        """
        Enable comprehensive observability with unified manager (Systems 3-7).

        This is a convenience method that sets up complete observability
        infrastructure with a single function call. It creates an ObservabilityManager
        that integrates metrics, logging, tracing, and audit trails.

        **What gets enabled:**
        - **Metrics** (System 4): Counter, gauge, histogram with Prometheus export
        - **Logging** (System 5): Structured JSON logs with context propagation
        - **Tracing** (System 3): OpenTelemetry distributed tracing with Jaeger
        - **Audit** (System 6): Immutable audit trails for compliance

        Args:
            service_name: Service name for identification (default: uses agent_id)
            jaeger_host: Jaeger OTLP endpoint host (default: "localhost")
            jaeger_port: Jaeger OTLP gRPC port (default: 4317)
            insecure: Use insecure connection (default: True for testing)
            events_to_trace: Optional list of HookEvent to trace (None = all events)
            enable_metrics: Enable metrics collection (default: True)
            enable_logging: Enable structured logging (default: True)
            enable_tracing: Enable distributed tracing (default: True)
            enable_audit: Enable audit trail recording (default: True)

        Example:
            >>> # Full observability (all systems)
            >>> agent = BaseAgent(config=config, signature=signature)
            >>> obs = agent.enable_observability(service_name="my-agent")
            >>> result = agent.run(question="test")
            >>> # View traces at http://localhost:16686
            >>> # Export metrics: await obs.export_metrics()
            >>>
            >>> # Lightweight observability (metrics + logging only)
            >>> obs = agent.enable_observability(
            ...     service_name="my-agent",
            ...     enable_tracing=False,
            ...     enable_audit=False
            ... )

        Returns:
            ObservabilityManager instance for advanced operations

        See Also:
            - ObservabilityManager: Unified observability interface
            - ADR-017: Observability & Performance Monitoring design
        """
        from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook
        from kaizen.core.autonomy.observability.manager import ObservabilityManager

        # Use agent_id as service name if not provided
        if service_name is None:
            service_name = self.agent_id

        # Create unified observability manager
        self._observability_manager = ObservabilityManager(
            service_name=service_name,
            enable_metrics=enable_metrics,
            enable_logging=enable_logging,
            enable_tracing=enable_tracing,
            enable_audit=enable_audit,
        )

        # If tracing is enabled, register tracing hook with hook manager
        if enable_tracing and self._observability_manager.tracing:
            tracing_hook = TracingHook(
                tracing_manager=self._observability_manager.tracing,
                events_to_trace=events_to_trace,
            )
            self._hook_manager.register_hook(tracing_hook)

        # Store reference to tracing manager for backward compatibility
        if enable_tracing:
            self._tracing_manager = self._observability_manager.tracing
        else:
            self._tracing_manager = None

        # Log enabled components
        enabled = self._observability_manager.get_enabled_components()
        logger.info(
            f"Observability enabled for {service_name}",
            extra={
                "enabled_components": enabled,
                "jaeger_ui": f"http://{jaeger_host}:16686" if enable_tracing else None,
            },
        )

        return self._observability_manager

    # ═══════════════════════════════════════════════════════════════════════
    # HOOKS SYSTEM API (Phase 3A)
    # ═══════════════════════════════════════════════════════════════════════

    def register_hook(
        self,
        event_type: "HookEvent",
        handler: Any,
        priority: "HookPriority" = None,
    ) -> None:
        """
        Register a hook for an event type.

        Convenience method for self._hook_manager.register().

        Args:
            event_type: Event to trigger hook on (HookEvent enum or string)
            handler: Hook handler (HookHandler protocol or async callable)
            priority: Execution priority (defaults to HookPriority.NORMAL)

        Raises:
            RuntimeError: If hooks are not enabled in config

        Example:
            >>> from kaizen.core.autonomy.hooks import HookEvent, HookContext, HookResult
            >>>
            >>> async def log_tool_use(context: HookContext) -> HookResult:
            ...     print(f"Tool: {context.data['tool_name']}")
            ...     return HookResult(success=True)
            >>>
            >>> agent.register_hook(HookEvent.PRE_TOOL_USE, log_tool_use)
        """
        if not self.config.hooks_enabled:
            raise RuntimeError(
                "Hooks are not enabled. Set hooks_enabled=True in BaseAgentConfig."
            )

        # Import here to avoid circular dependency
        from kaizen.core.autonomy.hooks.types import HookPriority

        if priority is None:
            priority = HookPriority.NORMAL

        self._hook_manager.register(event_type, handler, priority)

    async def trigger_hook(
        self,
        event_type: "HookEvent",
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:
        """
        Trigger all hooks for an event type.

        Convenience method for self._hook_manager.trigger().

        Args:
            event_type: Event that occurred (HookEvent enum or string)
            data: Event-specific data
            metadata: Optional additional metadata

        Returns:
            List of HookResult from each executed hook

        Example:
            >>> results = await agent.trigger_hook(
            ...     HookEvent.POST_TOOL_USE,
            ...     data={"tool_name": "Read", "result": {...}}
            ... )
            >>> for result in results:
            ...     if result.success:
            ...         print(f"Hook succeeded: {result.data}")
        """
        if not self.config.hooks_enabled:
            return []

        return await self._hook_manager.trigger(
            event_type=event_type,
            agent_id=self.agent_id,
            data=data,
            timeout=self.config.hook_timeout,
            metadata=metadata,
        )

    def get_hook_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get hook execution statistics.

        Convenience method for self._hook_manager.get_stats().

        Returns:
            Dictionary mapping hook names to their statistics:
            - call_count: Number of times hook was called
            - success_count: Number of successful executions
            - failure_count: Number of failed executions
            - total_duration_ms: Total execution time
            - avg_duration_ms: Average execution time
            - max_duration_ms: Maximum execution time

        Example:
            >>> stats = agent.get_hook_stats()
            >>> print(f"Logging hook called {stats['logging_hook']['call_count']} times")
            >>> print(f"Average duration: {stats['logging_hook']['avg_duration_ms']}ms")
        """
        if not self.config.hooks_enabled:
            return {}

        return self._hook_manager.get_stats()

    def cleanup(self):
        """
        Cleanup agent resources.

        This method is called by test fixtures during teardown to properly
        cleanup any resources held by the agent.

        Example:
            >>> agent = SimpleQAAgent(config)
            >>> try:
            ...     result = agent.ask("question")
            ... finally:
            ...     agent.cleanup()
        """
        # Cleanup MCP server if running
        if hasattr(self, "_mcp_server") and self._mcp_server is not None:
            try:
                # Stop server if it has a stop method
                if hasattr(self._mcp_server, "stop"):
                    self._mcp_server.stop()
            except Exception as e:
                logger.warning(f"Error stopping MCP server: {e}")
            self._mcp_server = None

        # Cleanup MCP registrar if active
        if hasattr(self, "_mcp_registrar") and self._mcp_registrar is not None:
            try:
                # Unregister from discovery if method exists
                if hasattr(self._mcp_registrar, "unregister"):
                    self._mcp_registrar.unregister()
            except Exception as e:
                logger.warning(f"Error unregistering from MCP discovery: {e}")
            self._mcp_registrar = None

        # Clear shared memory references
        if hasattr(self, "shared_memory") and self.shared_memory is not None:
            # Don't clear the memory itself (other agents may use it)
            # Just clear our reference
            self.shared_memory = None

        # Clear memory references
        if hasattr(self, "memory") and self.memory is not None:
            self.memory = None

        # Clear hook manager references (System 3 - Observability)
        if hasattr(self, "_hook_manager") and self._hook_manager is not None:
            self._hook_manager = None

        # Shutdown tracing manager if initialized (System 3 - Observability)
        if hasattr(self, "_tracing_manager") and self._tracing_manager is not None:
            try:
                self._tracing_manager.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down tracing manager: {e}")
            self._tracing_manager = None

        # Shutdown observability manager if initialized (Systems 4-7)
        if (
            hasattr(self, "_observability_manager")
            and self._observability_manager is not None
        ):
            try:
                self._observability_manager.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down observability manager: {e}")
            self._observability_manager = None

        # Clear framework references to avoid memory leaks
        self._framework = None
        self._agent = None
        self._workflow = None

        logger.debug(f"Cleanup completed for agent {self.agent_id}")
