"""
BaseAgent - Universal agent class for Kaizen framework.

Provides the foundation for all agent types with:
- Unified configuration management via BaseAgentConfig
- Lazy framework initialization
- Workflow generation from signatures
- Strategy-based execution via AgentLoop
- MCP integration via MCPMixin
- A2A protocol via A2AMixin
- Mixin composition for features

Extension Points (7 total, deprecated in v2.5.0 -- use composition wrappers):
1. _default_signature()
2. _default_strategy()
3. _generate_system_prompt()
4. _validate_signature_output()
5. _pre_execution_hook()
6. _post_execution_hook()
7. _handle_error()

Author: Kaizen Framework Team
Copyright 2025 Terrene Foundation (Singapore CLG)
Licensed under Apache-2.0
"""

import json
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional

# Core SDK imports
from kailash.nodes.base import Node, NodeParameter
from kailash.workflow.builder import WorkflowBuilder
from kailash_mcp.client import MCPClient

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
from kaizen.tools.types import ToolCategory, ToolDefinition, ToolParameter

from .a2a_mixin import A2AMixin
from .agent_loop import AgentLoop
from .config import BaseAgentConfig
from .deprecation import deprecated
from .mcp_mixin import MCPMixin

__all__ = ["BaseAgent", "BaseAgentConfig"]

logger = logging.getLogger(__name__)


class BaseAgent(MCPMixin, A2AMixin, Node):
    """Universal base agent class with strategy-based execution and mixin composition.

    Inherits MCP integration from MCPMixin and A2A protocol support from A2AMixin.
    Execution is delegated to AgentLoop for both sync and async paths.
    """

    # SPEC-04: Extension points deprecated in v2.5.0 — override emits warning.
    # Replacement: composition wrappers.
    _DEPRECATED_EXTENSION_POINTS = (
        "_default_signature",
        "_default_strategy",
        "_generate_system_prompt",
        "_validate_signature_output",
        "_pre_execution_hook",
        "_post_execution_hook",
        "_handle_error",
    )

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Warn subclasses that override deprecated extension points."""
        super().__init_subclass__(**kwargs)
        import warnings as _warnings

        base_attrs = {
            name: getattr(BaseAgent, name, None)
            for name in cls._DEPRECATED_EXTENSION_POINTS
        }
        for name in cls._DEPRECATED_EXTENSION_POINTS:
            if name in cls.__dict__ and cls.__dict__[name] is not base_attrs[name]:
                _warnings.warn(
                    f"{cls.__name__} overrides deprecated extension point "
                    f"BaseAgent.{name}() (deprecated in v2.5.0). Use composition "
                    f"wrappers (kaizen_agents.StreamingAgent, MonitoredAgent, "
                    f"GovernedAgent) instead of subclassing.",
                    DeprecationWarning,
                    stacklevel=2,
                )

    def _invoke_extension_point(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Dispatch to a subclass override or the private ``_impl`` default.

        SPEC-04 deprecates the seven extension points. Subclass overrides
        run unchanged (they shadow the decorated wrapper). When no override
        exists, the private ``_<name>_impl`` runs directly so vanilla
        agents emit no deprecation warnings. ``__init_subclass__`` already
        warned once at class-definition time for any override.
        """
        base_slot = getattr(BaseAgent, name, None)
        actual_slot = getattr(type(self), name, None)
        if actual_slot is not None and actual_slot is not base_slot:
            return actual_slot(self, *args, **kwargs)
        impl = getattr(self, f"{name}_impl", None)
        if impl is None:
            return getattr(self, name)(*args, **kwargs)
        return impl(*args, **kwargs)

    def __init__(
        self,
        config: Any,
        signature: Optional[Signature] = None,
        strategy: Optional[Any] = None,
        memory: Optional[Any] = None,
        shared_memory: Optional[Any] = None,
        agent_id: Optional[str] = None,
        control_protocol: Optional[Any] = None,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        hook_manager: Optional[Any] = None,
        **kwargs,
    ):
        """Initialize BaseAgent with lazy loading pattern.

        Args:
            config: Agent configuration (BaseAgentConfig or domain config, auto-converted).
            signature: Optional signature (uses _default_signature() if None).
            strategy: Optional execution strategy (uses _default_strategy() if None).
            memory: Optional conversation memory (KaizenMemory instance).
            shared_memory: Optional shared memory pool (SharedMemoryPool).
            agent_id: Optional agent identifier (auto-generated if None).
            control_protocol: Optional ControlProtocol for user interaction.
            mcp_servers: Optional MCP server configurations. None = auto-connect builtin.
                        Set to [] to disable MCP.
            hook_manager: Optional HookManager instance for lifecycle hooks.
            **kwargs: Additional arguments passed to Node.__init__
        """
        # Auto-convert domain config to BaseAgentConfig
        if not isinstance(config, BaseAgentConfig):
            config = BaseAgentConfig.from_domain_config(config)

        self.config = config
        agent_config = config

        # Signature and strategy (extension points).
        # BaseAgent resolves defaults via ``_invoke_extension_point``: if the
        # subclass overrides the slot, the override runs (no decorator
        # warning because subclass methods are not decorated); otherwise the
        # private ``_impl`` helper runs directly (no decorator warning on
        # vanilla BaseAgent construction). See SPEC-04 § 1 item 5.
        self.signature = (
            signature
            if signature is not None
            else self._invoke_extension_point("_default_signature")
        )
        self.strategy = (
            strategy
            if strategy is not None
            else self._invoke_extension_point("_default_strategy")
        )

        # Memory
        self.memory = memory
        self.shared_memory = shared_memory
        self.agent_id = agent_id if agent_id is not None else f"agent_{id(self)}"

        # Control protocol
        self.control_protocol = control_protocol

        # MCP initialization
        if mcp_servers is None:
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

        if self._mcp_servers:
            self._mcp_client = MCPClient()
            self._discovered_mcp_tools = {}
            self._discovered_mcp_resources = {}
            self._discovered_mcp_prompts = {}
            logger.debug(
                f"MCP client initialized with {len(self._mcp_servers)} server(s). "
                f"Call await discover_mcp_tools() to discover tools."
            )
        else:
            self._mcp_client = None
            self._discovered_mcp_tools = {}
            self._discovered_mcp_resources = {}
            self._discovered_mcp_prompts = {}

        # Permission system
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

        # Hook system
        if hook_manager is not None:
            self.hook_manager = hook_manager
        elif self.config.hooks_enabled:
            from kaizen.core.autonomy.hooks.manager import HookManager

            self.hook_manager = HookManager()
        else:
            self.hook_manager = None

        self._hook_manager = self.hook_manager

        # Observability (lazy)
        self._observability_manager = None

        # Node.__init__
        super().__init__(**kwargs)

        # Restore config (Node.__init__ overwrites with dict)
        self.config = agent_config

        # Lazy initialization
        self._framework = None
        self._agent = None
        self._workflow = None

        # WorkflowGenerator
        from .workflow_generator import WorkflowGenerator

        # Route prompt generation through _invoke_extension_point so
        # subclass overrides still win while vanilla agents skip the
        # deprecation warning path (SPEC-04 § 1 item 5).
        self.workflow_generator = WorkflowGenerator(
            config=self.config,
            signature=self.signature,
            prompt_generator=lambda: self._invoke_extension_point(
                "_generate_system_prompt"
            ),
            agent=self,
        )

        # Mixin state tracking
        self._mixins_applied = []

        # Apply mixins based on config
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

    # =========================================================================
    # Mixin application
    # =========================================================================

    def _apply_logging_mixin(self):
        from kaizen.core.mixins.logging_mixin import LoggingMixin

        LoggingMixin.apply(self)
        self._mixins_applied.append("LoggingMixin")

    def _apply_performance_mixin(self):
        from kaizen.core.mixins.metrics_mixin import MetricsMixin

        MetricsMixin.apply(self)
        self._mixins_applied.append("PerformanceMixin")

    def _apply_error_handling_mixin(self):
        from kaizen.core.mixins.retry_mixin import RetryMixin

        RetryMixin.apply(self)
        self._mixins_applied.append("ErrorHandlingMixin")

    def _apply_batch_processing_mixin(self):
        from kaizen.core.mixins.caching_mixin import CachingMixin

        CachingMixin.apply(self)
        self._mixins_applied.append("BatchProcessingMixin")

    def _apply_memory_mixin(self):
        from kaizen.core.mixins.timeout_mixin import TimeoutMixin

        TimeoutMixin.apply(self)
        self._mixins_applied.append("MemoryMixin")

    def _apply_transparency_mixin(self):
        from kaizen.core.mixins.tracing_mixin import TracingMixin

        TracingMixin.apply(self)
        self._mixins_applied.append("TransparencyMixin")

    def _apply_mcp_integration_mixin(self):
        from kaizen.core.mixins.validation_mixin import ValidationMixin

        ValidationMixin.apply(self)
        self._mixins_applied.append("MCPIntegrationMixin")

    # =========================================================================
    # Node interface
    # =========================================================================

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get parameter schema for agent contract (required by Node base class)."""
        parameters = {}

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

        return parameters

    # =========================================================================
    # Execution (delegates to AgentLoop)
    # =========================================================================

    def _run_async_hook(self, coro) -> None:
        """Run an async coroutine from sync context (hook bridge)."""
        from .agent_loop import run_async_hook

        run_async_hook(coro)

    def run(self, **inputs) -> Dict[str, Any]:
        """Execute agent synchronously with strategy-based execution.

        Args:
            **inputs: Input parameters matching signature input fields.
                     Special parameter: session_id (str) for memory persistence.

        Returns:
            Dict[str, Any]: Results matching signature output fields.
        """
        return AgentLoop.run_sync(self, **inputs)

    async def run_async(self, **inputs) -> Dict[str, Any]:
        """Execute agent asynchronously with non-blocking I/O.

        Requires use_async_llm=True in configuration.

        Args:
            **inputs: Input parameters matching signature input fields.
                     Special parameter: session_id (str) for memory persistence.

        Returns:
            Dict[str, Any]: Results matching signature output fields.

        Raises:
            ValueError: If use_async_llm=False.
        """
        return await AgentLoop.run_async(self, **inputs)

    async def _simple_execute_async(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Simple async execution using direct provider call (fallback)."""
        from kaizen.nodes.ai.ai_providers import OpenAIProvider

        provider = OpenAIProvider(use_async=True)

        messages = []
        system_prompt = self._invoke_extension_point("_generate_system_prompt")
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        user_content = " | ".join(
            str(v) for v in inputs.values() if not str(v).startswith("_")
        )
        messages.append({"role": "user", "content": user_content})

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

        if self.signature:
            output_fields = list(self.signature.output_fields.keys())
            if output_fields:
                return {output_fields[0]: response["content"]}

        return {"response": response["content"]}

    def _simple_execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Simple execution without strategy (fallback)."""
        return {"result": "Simple execution placeholder"}

    # =========================================================================
    # Convenience methods
    # =========================================================================

    def write_to_memory(
        self,
        content: Any,
        tags: Optional[List[str]] = None,
        importance: float = 0.5,
        segment: str = "execution",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Write insights to shared memory (convenience method)."""
        if not self.shared_memory:
            return

        if isinstance(content, (dict, list)):
            content_str = json.dumps(content)
        else:
            content_str = str(content)

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
        """Extract a list field from result with type safety."""
        if default is None:
            default = []

        field_value = result.get(field_name, default)

        if isinstance(field_value, list):
            return field_value

        if isinstance(field_value, str):
            try:
                parsed = json.loads(field_value) if field_value else default
                return parsed if isinstance(parsed, list) else default
            except Exception:
                return default

        return default

    def extract_dict(
        self, result: Dict[str, Any], field_name: str, default: Optional[Dict] = None
    ) -> Dict:
        """Extract a dict field from result with type safety."""
        if default is None:
            default = {}

        field_value = result.get(field_name, default)

        if isinstance(field_value, dict):
            return field_value

        if isinstance(field_value, str):
            try:
                parsed = json.loads(field_value) if field_value else default
                return parsed if isinstance(parsed, dict) else default
            except Exception:
                return default

        return default

    def extract_float(
        self, result: Dict[str, Any], field_name: str, default: float = 0.0
    ) -> float:
        """Extract a float field from result with type safety."""
        field_value = result.get(field_name, default)

        if isinstance(field_value, (int, float)):
            return float(field_value)

        if isinstance(field_value, str):
            try:
                return float(field_value)
            except Exception:
                return default

        return default

    def extract_str(
        self, result: Dict[str, Any], field_name: str, default: str = ""
    ) -> str:
        """Extract a string field from result with type safety."""
        field_value = result.get(field_name, default)
        return str(field_value) if field_value is not None else default

    # =========================================================================
    # Workflow generation
    # =========================================================================

    def to_workflow(self) -> WorkflowBuilder:
        """Generate a Core SDK workflow from the agent's signature.

        Returns:
            WorkflowBuilder: Workflow representation ready for execution.
        """
        if self._workflow is not None:
            return self._workflow

        workflow = WorkflowBuilder()

        node_config = {
            "system_prompt": self._invoke_extension_point("_generate_system_prompt"),
        }

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

        workflow.add_node("LLMAgentNode", "agent", node_config)

        self._workflow = workflow
        return workflow

    def to_workflow_node(self) -> Node:
        """Convert this agent into a single node for composition."""
        return self

    # =========================================================================
    # Extension Points (SPEC-04 § 1 item 5 -- deprecated in v2.5.0)
    # ``_*_impl`` are the private default implementations BaseAgent uses.
    # The public slots below carry the deprecation wrapper for subclasses.
    # =========================================================================

    def _default_signature_impl(self) -> Signature:
        """Default signature used by BaseAgent when no signature is provided."""

        class DefaultSignature(Signature):
            """Default signature with generic input/output."""

            input: str = InputField(desc="Generic input")
            output: str = OutputField(desc="Generic output")

        return DefaultSignature()

    def _default_strategy_impl(self) -> Any:
        """Default execution strategy resolved from config.strategy_type."""
        try:
            from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy
            from kaizen.strategies.multi_cycle import MultiCycleStrategy

            if self.config.strategy_type == "multi_cycle":
                return MultiCycleStrategy(max_cycles=self.config.max_cycles)
            else:
                return AsyncSingleShotStrategy()
        except ImportError:

            class SimpleStrategy:
                async def execute(self, agent, inputs, **kwargs):
                    return {"result": "Simple strategy execution"}

            return SimpleStrategy()

    def _generate_system_prompt_impl(self) -> str:
        """Generate the default system prompt from signature + discovered tools."""
        from kaizen.core.prompt_utils import generate_prompt_from_signature

        prompt_parts = [generate_prompt_from_signature(self.signature)]

        all_tools = []
        for server_tools in self._discovered_mcp_tools.values():
            all_tools.extend(server_tools)

        if all_tools:
            prompt_parts.append(
                "\n\n## Available Tools\n"
                "\nYou have access to the following tools to help complete tasks:\n"
            )
            for tool in all_tools:
                display_name = tool.get("name", "unknown").replace(
                    "mcp__kaizen_builtin__", ""
                )
                description = tool.get("description", "No description available")
                prompt_parts.append(f"- **{display_name}**: {description}")
                params = (tool.get("inputSchema") or {}).get("properties") or {}
                if params:
                    param_list = [
                        f"{name} ({info.get('description', '')})"
                        for name, info in params.items()
                    ]
                    prompt_parts.append(f"  Parameters: {', '.join(param_list)}")
            prompt_parts.append(
                "\n\n## Tool Usage Instructions\n"
                "\nTo use a tool, set the 'action' field to 'tool_use' and provide:\n"
                "- action_input: A dict with 'tool_name' (without mcp__ prefix) and 'params' dict\n"
                "\nExample:\n"
                '  action: "tool_use"\n'
                "  action_input:\n"
                '    tool_name: "read_file"\n'
                "    params:\n"
                '      path: "/path/to/file.txt"\n'
                "\nAfter using a tool, you will receive the result in the 'context' field.\n"
                'When the task is complete, set action to "finish" with your final response.'
            )

        return "\n".join(prompt_parts)

    def _validate_signature_output_impl(self, output: Dict[str, Any]) -> bool:
        """Validate that output matches signature (default implementation)."""
        has_special_keys = any(
            key in output for key in ["_write_insight", "response", "result"]
        )

        if has_special_keys:
            return True

        if hasattr(self.signature, "output_fields") and self.signature.output_fields:
            for field in self.signature.output_fields:
                field_name = field.name if hasattr(field, "name") else str(field)
                if field_name not in output:
                    raise ValueError(f"Missing required output field: {field_name}")
        return True

    def _pre_execution_hook_impl(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Default pre-execution hook (logs execution start)."""
        logging_enabled = getattr(self.config, "logging_enabled", True)
        if logging_enabled:
            signature_name = getattr(self.signature, "name", "unknown")
            logger.info(f"Executing {signature_name} with inputs: {inputs}")
        return inputs

    def _post_execution_hook_impl(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Default post-execution hook (logs completion)."""
        logging_enabled = getattr(self.config, "logging_enabled", True)
        if logging_enabled:
            logger.info(f"Execution complete. Result: {result}")
        return result

    def _handle_error_impl(
        self, error: Exception, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Default error handler."""
        error_handling_enabled = getattr(self.config, "error_handling_enabled", True)
        if error_handling_enabled:
            logger.error(f"Error during execution: {error}", extra=context)
            return {"error": str(error), "type": type(error).__name__, "success": False}
        else:
            raise error

    # -------------------------------------------------------------------------
    # Deprecated extension-point slots (SPEC-04 § 1 item 5)
    #
    # Each slot delegates to its ``_impl`` sibling so existing overrides
    # keep working. The deprecation wrapper fires only when the slot is
    # invoked directly; BaseAgent and AgentLoop route around the slots via
    # ``_invoke_extension_point`` so vanilla agents stay warning-free.
    # -------------------------------------------------------------------------

    _DEPRECATION_MSG = (
        "BaseAgent extension points are deprecated. Use composition wrappers "
        "(kaizen_agents.StreamingAgent, MonitoredAgent, GovernedAgent) or "
        "BaseAgentConfig/signature parameters instead of subclassing."
    )

    @deprecated(_DEPRECATION_MSG, since="2.5.0")
    def _default_signature(self) -> Signature:
        """Deprecated extension point: return the default Signature."""
        return self._default_signature_impl()

    @deprecated(_DEPRECATION_MSG, since="2.5.0")
    def _default_strategy(self) -> Any:
        """Deprecated extension point: return the default strategy."""
        return self._default_strategy_impl()

    @deprecated(_DEPRECATION_MSG, since="2.5.0")
    def _generate_system_prompt(self) -> str:
        """Deprecated extension point: generate the system prompt."""
        return self._generate_system_prompt_impl()

    @deprecated(_DEPRECATION_MSG, since="2.5.0")
    def _validate_signature_output(self, output: Dict[str, Any]) -> bool:
        """Deprecated extension point: validate LLM output against signature."""
        return self._validate_signature_output_impl(output)

    @deprecated(_DEPRECATION_MSG, since="2.5.0")
    def _pre_execution_hook(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Deprecated extension point: called before execution."""
        return self._pre_execution_hook_impl(inputs)

    @deprecated(_DEPRECATION_MSG, since="2.5.0")
    def _post_execution_hook(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Deprecated extension point: called after execution."""
        return self._post_execution_hook_impl(result)

    @deprecated(_DEPRECATION_MSG, since="2.5.0")
    def _handle_error(
        self, error: Exception, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Deprecated extension point: handle execution errors."""
        return self._handle_error_impl(error, context)

    # =========================================================================
    # Control Protocol helpers
    # =========================================================================

    async def ask_user_question(
        self,
        question: str,
        options: Optional[List[str]] = None,
        timeout: float = 60.0,
    ) -> str:
        """Ask user a question during agent execution via Control Protocol."""
        if self.control_protocol is None:
            raise RuntimeError(
                "Control protocol not configured. "
                "Pass control_protocol parameter to BaseAgent.__init__()"
            )

        from kaizen.core.autonomy.control.types import ControlRequest

        data = {"question": question}
        if options:
            data["options"] = options

        request = ControlRequest.create("question", data)
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
        """Request user approval for an action via Control Protocol."""
        if self.control_protocol is None:
            raise RuntimeError(
                "Control protocol not configured. "
                "Pass control_protocol parameter to BaseAgent.__init__()"
            )

        from kaizen.core.autonomy.control.types import ControlRequest

        data = {"action": action}
        if details:
            data["details"] = details

        request = ControlRequest.create("approval", data)
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
        """Report progress update to user via Control Protocol."""
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
        for key, value in structured_content.items():
            if key not in result_dict:  # Don't overwrite existing keys
                result_dict[key] = value

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
            from kailash_mcp import MCPClient
        except ImportError:
            raise ImportError(
                "kailash_mcp not available. Install with: pip install kailash"
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
            ImportError: If kailash_mcp not available

        Example:
            >>> from kailash_mcp.auth.providers import APIKeyAuth
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
            from kailash_mcp import MCPServer
            from kailash_mcp import enable_auto_discovery as enable_discovery
        except ImportError:
            raise ImportError(
                "kailash_mcp not available. Install with: pip install kailash"
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

    # =========================================================================
    # Observability
    # =========================================================================

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
        """Enable comprehensive observability with unified manager (Systems 3-7).

        Args:
            service_name: Service name (default: agent_id).
            jaeger_host: Jaeger OTLP endpoint host.
            jaeger_port: Jaeger OTLP gRPC port.
            insecure: Use insecure connection.
            events_to_trace: Optional list of HookEvent to trace.
            enable_metrics: Enable metrics collection.
            enable_logging: Enable structured logging.
            enable_tracing: Enable distributed tracing.
            enable_audit: Enable audit trail recording.

        Returns:
            ObservabilityManager instance.
        """
        from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook
        from kaizen.core.autonomy.observability.manager import ObservabilityManager

        if service_name is None:
            service_name = self.agent_id

        self._observability_manager = ObservabilityManager(
            service_name=service_name,
            enable_metrics=enable_metrics,
            enable_logging=enable_logging,
            enable_tracing=enable_tracing,
            enable_audit=enable_audit,
        )

        if enable_tracing and self._observability_manager.tracing:
            tracing_hook = TracingHook(
                tracing_manager=self._observability_manager.tracing,
                events_to_trace=events_to_trace,
            )
            self._hook_manager.register_hook(tracing_hook)

        if enable_tracing:
            self._tracing_manager = self._observability_manager.tracing
        else:
            self._tracing_manager = None

        enabled = self._observability_manager.get_enabled_components()
        logger.info(
            f"Observability enabled for {service_name}",
            extra={
                "enabled_components": enabled,
                "jaeger_ui": f"http://{jaeger_host}:16686" if enable_tracing else None,
            },
        )

        return self._observability_manager

    # =========================================================================
    # Hooks system API
    # =========================================================================

    def register_hook(
        self,
        event_type: "HookEvent",
        handler: Any,
        priority: "HookPriority" = None,
    ) -> None:
        """Register a hook for an event type."""
        if not self.config.hooks_enabled:
            raise RuntimeError(
                "Hooks are not enabled. Set hooks_enabled=True in BaseAgentConfig."
            )

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
        """Trigger all hooks for an event type."""
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
        """Get hook execution statistics."""
        if not self.config.hooks_enabled:
            return {}

        return self._hook_manager.get_stats()

    # =========================================================================
    # Cleanup
    # =========================================================================

    def cleanup(self):
        """Cleanup agent resources."""
        if hasattr(self, "_mcp_server") and self._mcp_server is not None:
            try:
                if hasattr(self._mcp_server, "stop"):
                    self._mcp_server.stop()
            except Exception as e:
                logger.warning(f"Error stopping MCP server: {e}")
            self._mcp_server = None

        if hasattr(self, "_mcp_registrar") and self._mcp_registrar is not None:
            try:
                if hasattr(self._mcp_registrar, "unregister"):
                    self._mcp_registrar.unregister()
            except Exception as e:
                logger.warning(f"Error unregistering from MCP discovery: {e}")
            self._mcp_registrar = None

        if hasattr(self, "shared_memory") and self.shared_memory is not None:
            self.shared_memory = None

        if hasattr(self, "memory") and self.memory is not None:
            self.memory = None

        if hasattr(self, "_hook_manager") and self._hook_manager is not None:
            self._hook_manager = None

        if hasattr(self, "_tracing_manager") and self._tracing_manager is not None:
            try:
                self._tracing_manager.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down tracing manager: {e}")
            self._tracing_manager = None

        if (
            hasattr(self, "_observability_manager")
            and self._observability_manager is not None
        ):
            try:
                self._observability_manager.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down observability manager: {e}")
            self._observability_manager = None

        self._framework = None
        self._agent = None
        self._workflow = None

        logger.debug(f"Cleanup completed for agent {self.agent_id}")
