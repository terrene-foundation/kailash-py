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
from typing import Any, Dict, List, Optional

from kailash_mcp.client import MCPClient

from kailash.nodes.base import Node, NodeParameter
from kailash.workflow.builder import WorkflowBuilder
from kaizen.signatures import InputField, OutputField, Signature
from kaizen.tools.types import ToolCategory, ToolDefinition, ToolParameter

from ._provider_env import detect_provider_from_env as _detect_provider
from .a2a_mixin import A2AMixin
from .agent_loop import AgentLoop
from .config import BaseAgentConfig
from .mcp_mixin import MCPMixin

__all__ = ["BaseAgent", "BaseAgentConfig"]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Log-hygiene helpers (#2030)
# ---------------------------------------------------------------------------
# Agent inputs and results routinely carry user prompts, retrieved documents,
# PII and — for agents that take credentials as parameters — secrets. NOTHING
# below ever renders a VALUE into a log record at INFO or above. The structured
# summary (key names + counts) is what makes the trace useful; the values are
# what makes it a disclosure.


def _summarize_payload(payload: Any) -> Dict[str, Any]:
    """Value-FREE description of an agent I/O dict: key names and a count.

    Key names are schema, not data — they are what an operator needs to
    correlate a run, and they are safe. Values never appear.
    """
    if isinstance(payload, dict):
        return {"keys": sorted(str(key) for key in payload), "count": len(payload)}
    return {"keys": [], "count": 0, "type": type(payload).__name__}


def _safe_log_extra(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize a caller-supplied context into record attributes safe to emit.

    ``AgentLoop`` calls ``_handle_error(error, {"inputs": inputs})``, so passing
    the context straight through as ``extra=`` put the FULL agent inputs onto
    the LogRecord at ERROR — a level that survives every production log config.
    Default formatters do not render extra attributes, but structured handlers
    (python-json-logger, structlog, OTel log export) do, which is precisely
    where logs get shipped off-host.

    Every emitted name is ``ctx_``-prefixed, which cannot collide with a
    reserved ``LogRecord`` attribute (none of them start with ``ctx_``); a
    collision would otherwise make ``logging`` raise at the call site.
    """
    safe: Dict[str, Any] = {}
    for key, value in (context or {}).items():
        name = f"ctx_{key}"
        if isinstance(value, dict):
            summary = _summarize_payload(value)
            safe[f"{name}_keys"] = summary["keys"]
            safe[f"{name}_count"] = summary["count"]
        else:
            safe[f"{name}_type"] = type(value).__name__
    return safe


def _configuration_error_types() -> tuple:
    """Error classes meaning "the agent was never wired", not "the run failed".

    Imported lazily: ``kaizen.config`` and ``kaizen.llm`` sit above
    ``kaizen.core`` in the import graph, so a module-scope import would create
    a cycle. Resolved once per call and cheap (all modules are already in
    ``sys.modules`` by the time an execution error can occur).
    """
    from kaizen.config.providers import ConfigurationError
    from kaizen.errors import EnvModelMissing, ProviderUndetectable
    from kaizen.llm.errors import MissingCredential
    from kaizen.llm.provider import UnknownModelProvider

    return (
        ConfigurationError,
        EnvModelMissing,
        ProviderUndetectable,
        UnknownModelProvider,
        MissingCredential,
    )


class BaseAgent(MCPMixin, A2AMixin, Node):
    """Universal base agent class with strategy-based execution and mixin composition.

    Inherits MCP integration from MCPMixin and A2A protocol support from A2AMixin.
    Execution is delegated to AgentLoop for both sync and async paths.
    """

    # Extension points — subclasses may override these directly.
    # Composition wrappers (StreamingAgent, MonitoredAgent, GovernedAgent)
    # are preferred for new code.

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
        checkpoint_manager: Optional[Any] = None,
    ):
        """Initialize BaseAgent.

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
            checkpoint_manager: Optional checkpoint manager for persisting
                intermediate agent state (AgentCheckpointManager or
                compatible). The manager is stored on the instance as
                ``self.checkpoint_manager`` so strategies/hooks that opt
                into checkpointing can discover it via duck-typing.
                ``None`` disables checkpointing for this agent.
        """
        # Auto-convert domain config to BaseAgentConfig
        if not isinstance(config, BaseAgentConfig):
            config = BaseAgentConfig.from_domain_config(config)

        self.config = config
        agent_config = config

        # Signature and strategy — subclass overrides win via normal MRO.
        self.signature = (
            signature if signature is not None else self._default_signature()
        )
        self.strategy = strategy if strategy is not None else self._default_strategy()

        # Memory
        self.memory = memory
        self.shared_memory = shared_memory
        self.agent_id = agent_id if agent_id is not None else f"agent_{id(self)}"

        # Control protocol
        self.control_protocol = control_protocol

        # Checkpoint manager (optional) — strategies/hooks that opt into
        # checkpointing discover this via ``self.checkpoint_manager``.
        # ``None`` disables checkpointing for this agent.
        self.checkpoint_manager = checkpoint_manager

        # MCP initialization
        # When mcp_servers is not specified (None), auto-inject the builtin
        # MCP server UNLESS the config requests structured output.  Gemini
        # (and potentially other providers) reject requests that combine
        # function calling with JSON response mode (response_mime_type).
        # Structured output takes priority over auto-tool discovery.
        # See: https://github.com/terrene-foundation/kailash-py/issues/357
        if mcp_servers is None:
            if self.config.has_structured_output:
                logger.debug(
                    "MCP auto-discovery suppressed: config has structured output "
                    "enabled (response_format=%s), which is incompatible with "
                    "function calling on some providers (e.g. Gemini).",
                    self.config.response_format,
                )
                self._mcp_servers = []
            else:
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

        # Trace exporter (cross-SDK diagnostics per issue #567 PR#6).
        # When set via attach_trace_exporter(), AgentLoop emits
        # agent.run.start / agent.run.end TraceEvents through the
        # exporter so downstream sinks see the full run lifecycle.
        # None = no-op: every tracing call short-circuits without cost.
        # See rules/orphan-detection.md §1 — this attribute is the
        # production call site that keeps kaizen.observability's
        # TraceExporter from becoming an orphan facade.
        self._trace_exporter = None

        # Node.__init__
        super().__init__()

        # Restore config (Node.__init__ overwrites with dict)
        self.config = agent_config

        # Lazy initialization
        self._framework = None
        self._agent = None
        self._workflow = None
        self._workflow_provider = None  # provider `_workflow` was built with

        # WorkflowGenerator
        from .workflow_generator import WorkflowGenerator

        self.workflow_generator = WorkflowGenerator(
            config=self.config,
            signature=self.signature,
            prompt_generator=lambda: self._generate_system_prompt(),
            agent=self,
        )

        # Apply mixins based on config flags (lazy imports to avoid cycles)
        _MIXIN_MAP = (
            ("logging_enabled", "kaizen.core.mixins.logging_mixin", "LoggingMixin"),
            ("performance_enabled", "kaizen.core.mixins.metrics_mixin", "MetricsMixin"),
            ("error_handling_enabled", "kaizen.core.mixins.retry_mixin", "RetryMixin"),
            (
                "batch_processing_enabled",
                "kaizen.core.mixins.caching_mixin",
                "CachingMixin",
            ),
            ("memory_enabled", "kaizen.core.mixins.timeout_mixin", "TimeoutMixin"),
            (
                "transparency_enabled",
                "kaizen.core.mixins.tracing_mixin",
                "TracingMixin",
            ),
            ("mcp_enabled", "kaizen.core.mixins.validation_mixin", "ValidationMixin"),
        )
        for flag, mod_path, cls_name in _MIXIN_MAP:
            if getattr(config, flag, False):
                import importlib

                try:
                    mixin_cls = getattr(importlib.import_module(mod_path), cls_name)
                except (ImportError, AttributeError) as exc:
                    raise ImportError(
                        f"Failed to load mixin {cls_name} from {mod_path} "
                        f"(config flag: {flag}): {exc}"
                    ) from exc
                mixin_cls.apply(self)

    # =========================================================================
    # Node interface
    # =========================================================================

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get parameter schema for agent contract (required by Node base class)."""
        parameters = {}
        # Pre-initialize to silence CodeQL py/uninitialized-local — every
        # runtime path that reaches the NodeParameter construction below
        # reassigns is_required, but static analysis cannot prove the
        # loop body runs before the read.
        is_required = True

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
        """Simple async execution via the four-axis ``LlmClient`` (fallback).

        #1720 Wave-B1c: cut over from the legacy ``OpenAIProvider`` to the
        four-axis path — ``resolve_deployment_for("openai", ...)`` ->
        ``LlmClient.from_deployment(...)`` -> ``await client.complete(...)``.
        The multimodal-input detection, the system-prompt prepend, the
        config->env model resolution, and the return shape are unchanged;
        the legacy ``response["content"]`` is read via ``to_legacy_shape``.
        """
        from kaizen.llm._legacy_shape import to_legacy_shape
        from kaizen.llm.client import LlmClient
        from kaizen.llm.deployment_resolver import resolve_deployment_for
        from kaizen.nodes.ai.llm_agent import _sampling_kwargs_from_generation_config

        messages = []
        system_prompt = self._generate_system_prompt()
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Build user content, detecting multimodal inputs (#410)
        from kaizen.strategies.async_single_shot import _classify_input_value

        text_parts: list[str] = []
        multimodal_parts: list[dict] = []
        has_multimodal = False

        for k, v in inputs.items():
            if v is None or str(k).startswith("_"):
                continue
            content_part = _classify_input_value(v, k, {})
            if content_part is not None:
                has_multimodal = True
                multimodal_parts.append(content_part)
            else:
                text_parts.append(str(v))

        if has_multimodal:
            content_list: list[dict] = []
            if text_parts:
                content_list.append({"type": "text", "text": " | ".join(text_parts)})
            content_list.extend(multimodal_parts)
            user_content = content_list
        else:
            user_content = " | ".join(text_parts) if text_parts else "No input provided"

        messages.append({"role": "user", "content": user_content})

        # Model resolution unchanged: config -> DEFAULT_LLM_MODEL -> OPENAI_PROD_MODEL.
        model = (
            self.config.model
            or os.environ.get("DEFAULT_LLM_MODEL")
            or os.environ.get("OPENAI_PROD_MODEL")
        )

        # Four-axis path: resolve the OpenAI deployment (BYOK config.api_key /
        # config.base_url honored; env OPENAI_API_KEY otherwise), then complete.
        deployment = resolve_deployment_for(
            "openai",
            model=model,
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )
        if deployment is None:
            raise ValueError(
                "_simple_execute_async: could not resolve an OpenAI four-axis "
                "deployment; set OPENAI_API_KEY (or pass config.api_key)."
            )
        # #1779: honor the agent's governance opt-out at the four-axis chokepoint.
        client = LlmClient.from_deployment(
            deployment, ungoverned=self.config.ungoverned
        )

        # generation_config temperature/max_tokens -> four-axis sampling kwargs.
        sampling_kwargs = _sampling_kwargs_from_generation_config(
            {
                "temperature": self.config.temperature or 0.7,
                "max_tokens": self.config.max_tokens or 500,
            }
        )
        try:
            result = await client.complete(messages, model=model, **sampling_kwargs)
        except Exception as e:
            # #1779: a lazy-re-check governance refusal propagates UNWRAPPED (inv 4).
            from kailash.trust.pact import UngovernedEgressRefused

            if isinstance(e, UngovernedEgressRefused):
                raise
            # #1720 Wave-B1 redteam MED — sanitize provider errors at
            # enforcement-surface parity with the B1a live path
            # (llm_agent._provider_llm_response). A raw wire exception can echo
            # a user-supplied config.base_url; scrub before it reaches
            # _handle_error's logger / returned {"error": ...} surface.
            from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error

            raise RuntimeError(sanitize_provider_error(e, "openai")) from e
        content = to_legacy_shape(result)["content"]

        if self.signature:
            output_fields = list(self.signature.output_fields.keys())
            if output_fields:
                return {output_fields[0]: content}

        return {"response": content}

    def _simple_execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback when no strategy is configured."""
        raise NotImplementedError(
            "No execution strategy configured. Pass strategy= to "
            "BaseAgent.__init__() or override _default_strategy()."
        )

    # =========================================================================
    # Trace exporter wiring (issue #567 PR#6)
    # =========================================================================

    def attach_trace_exporter(self, exporter: Any) -> None:
        """Attach a ``TraceExporter`` for cross-SDK diagnostics.

        When set, :class:`~kaizen.core.agent_loop.AgentLoop` emits
        ``agent.run.start`` and ``agent.run.end``
        :class:`kailash.diagnostics.protocols.TraceEvent` records on
        the production hot path. The exporter stamps each event with
        its cross-SDK fingerprint (kailash-rs#468 / v3.17.1+) and
        routes it to the configured sink.

        Passing ``None`` detaches the exporter — every tracing call
        short-circuits to a no-op thereafter.

        Typed accept: the argument is duck-typed to
        ``kaizen.observability.TraceExporter`` to avoid a hard import
        cycle (``kaizen.observability`` imports from ``kaizen.core``).
        The hot path simply calls ``exporter.export(event)``; a mis-
        shaped object fails loudly at first emission with a typed
        error, not silently.

        Args:
            exporter: A :class:`~kaizen.observability.TraceExporter` or
                ``None`` to detach.
        """
        self._trace_exporter = exporter

    @property
    def trace_exporter(self) -> Any:
        """The currently attached trace exporter, or ``None``."""
        return self._trace_exporter

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
        # Memo is provider-aware (env-dependent resolution -> rebuild on drift).
        current_provider = self.config.llm_provider or _detect_provider()
        if self._workflow is not None and self._workflow_provider == current_provider:
            return self._workflow

        workflow = WorkflowBuilder()

        node_config = {
            "system_prompt": self._generate_system_prompt(),
        }

        if self.config.model is not None:
            node_config["model"] = self.config.model
        node_config["provider"] = current_provider  # None keyless → #1947 gate
        # generation_config is LLMAgentNode's declared dict param (the only one
        # llm_agent.py reads at runtime) — top-level temperature/max_tokens
        # aren't declared NodeParameters and the Kailash validator flags them
        # as "Unknown parameter" every run since temperature defaults non-None.
        generation_config: Dict[str, Any] = {}
        if self.config.temperature is not None:
            generation_config["temperature"] = self.config.temperature
        if self.config.max_tokens is not None:
            generation_config["max_tokens"] = self.config.max_tokens
        if generation_config:
            node_config["generation_config"] = generation_config
        if self.config.provider_config is not None:
            node_config["provider_config"] = self.config.provider_config
        if self.config.response_format is not None:
            node_config["response_format"] = self.config.response_format
        # #1779: thread the governance opt-out into the LLMAgentNode egress path.
        node_config["ungoverned"] = self.config.ungoverned

        workflow.add_node("LLMAgentNode", "agent", node_config)

        self._workflow = workflow
        self._workflow_provider = current_provider
        return workflow

    def to_workflow_node(self) -> Node:
        """Convert this agent into a single node for composition."""
        return self

    # =========================================================================
    # Extension Points — override in subclasses or pass params to __init__
    # =========================================================================

    def _default_signature(self) -> Signature:
        """Default signature used by BaseAgent when no signature is provided."""

        class DefaultSignature(Signature):
            """Default signature with generic input/output."""

            input: str = InputField(desc="Generic input")
            output: str = OutputField(desc="Generic output")

        return DefaultSignature()

    def _default_strategy(self) -> Any:
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

    def _generate_system_prompt(self) -> str:
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

    def _validate_signature_output(self, output: Dict[str, Any]) -> bool:
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

    def _log_full_payload(self, label: str, payload: Any) -> None:
        """Dump a full agent payload at DEBUG — opt-in only, always scrubbed.

        Two independent gates, both of which must open (#2030):

        1. ``config.log_full_payloads`` — defaults False, so turning DEBUG on
           globally (routine during incident response) does NOT start dumping
           user prompts, retrieved documents and PII.
        2. the logger actually being at DEBUG.

        Even then the rendered payload routes through ``scrub_credentials``,
        the single credential-scrub implementation in Kaizen. Scrubbing claims
        credential SHAPES, not arbitrary PII — gate (1) is what protects PII,
        which is why it fails closed.
        """
        if not getattr(self.config, "log_full_payloads", False):
            return
        if not logger.isEnabledFor(logging.DEBUG):
            return

        from kaizen.utils.credential_scrub import scrub_credentials

        logger.debug("Full %s payload: %s", label, scrub_credentials(repr(payload)))

    def _pre_execution_hook(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Default pre-execution hook (logs execution start).

        Emits STRUCTURE (signature name, input key names, count) at INFO —
        never input values. See ``_summarize_payload``.
        """
        logging_enabled = getattr(self.config, "logging_enabled", True)
        if logging_enabled:
            signature_name = getattr(self.signature, "name", "unknown")
            summary = _summarize_payload(inputs)
            logger.info(
                "Executing %s with %d input(s): %s",
                signature_name,
                summary["count"],
                summary["keys"],
            )
            self._log_full_payload("inputs", inputs)
        return inputs

    def _post_execution_hook(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Default post-execution hook (logs completion).

        Emits result key names and count at INFO — never result values.
        """
        logging_enabled = getattr(self.config, "logging_enabled", True)
        if logging_enabled:
            summary = _summarize_payload(result)
            logger.info(
                "Execution complete. %d result field(s): %s",
                summary["count"],
                summary["keys"],
            )
            self._log_full_payload("result", result)
        return result

    def _handle_error(
        self, error: Exception, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Default error handler.

        Configuration failures are re-raised unconditionally (#2022). Every
        other error keeps the historical ``{"success": False}`` envelope, with
        the message scrubbed and the context summarized rather than rendered
        (#2030).
        """
        # #2022 — a configuration failure is not an execution failure. Folding
        # one into {"success": False} hands the caller an EMPTY result, which
        # downstream validators then reject as a malformed model response: the
        # user is told the LLM misbehaved when in fact their provider was never
        # wired, and the stack trace that would have said so is gone. This is
        # the rules/zero-tolerance.md Rule 3 silent-error-hiding shape, so the
        # re-raise is NOT gated on ``error_handling_enabled`` — that flag
        # governs run-time resilience, not the reporting of a broken setup.
        if isinstance(error, _configuration_error_types()):
            raise error

        error_handling_enabled = getattr(self.config, "error_handling_enabled", True)
        if error_handling_enabled:
            from kaizen.utils.credential_scrub import scrub_credentials

            # extra=context used to carry AgentLoop's {"inputs": inputs}
            # verbatim onto the record; summarize to key names + counts.
            logger.error(
                "Error during execution: %s",
                scrub_credentials(str(error)),
                extra=_safe_log_extra(context),
            )
            return {"error": str(error), "type": type(error).__name__, "success": False}
        else:
            raise error

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

    # =========================================================================
    # Observability (MCP tool methods inherited from MCPMixin)
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
        # Lazy import (module-scope would pull the kaizen.nodes.ai tree); both
        # except-handlers below call it — a missing import would mask the error.
        from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error

        if hasattr(self, "_mcp_server") and self._mcp_server is not None:
            try:
                if hasattr(self._mcp_server, "stop"):
                    self._mcp_server.stop()
            except Exception as e:
                logger.warning(
                    f"Error stopping MCP server: {sanitize_provider_error(e, 'MCP')}"
                )
            self._mcp_server = None

        if hasattr(self, "_mcp_registrar") and self._mcp_registrar is not None:
            try:
                if hasattr(self._mcp_registrar, "unregister"):
                    self._mcp_registrar.unregister()
            except Exception as e:
                logger.warning(
                    f"Error unregistering from MCP discovery: {sanitize_provider_error(e, 'MCP')}"
                )
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
        self._workflow_provider = None

        logger.debug(f"Cleanup completed for agent {self.agent_id}")
