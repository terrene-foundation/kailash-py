"""
AgentConfig - Expert Configuration for Unified Agent API

This module provides the AgentConfig dataclass for full control over
agent behavior. Use this for advanced use cases where presets are
not sufficient.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from kaizen.api.types import AgentCapabilities, ExecutionMode, MemoryDepth, ToolAccess

# Type aliases for hooks
HookCallback = Callable[[Dict[str, Any]], None]
AsyncHookCallback = Callable[[Dict[str, Any]], Any]  # Coroutine


@dataclass
class CheckpointConfig:
    """
    Configuration for execution checkpointing.

    Checkpoints allow resuming interrupted executions and
    provide state snapshots for debugging.
    """

    enabled: bool = True
    """Whether checkpointing is enabled."""

    strategy: str = "periodic"
    """Checkpoint strategy: 'periodic', 'on_tool_call', 'on_cycle', 'manual'."""

    interval_seconds: float = 60.0
    """Interval between periodic checkpoints."""

    interval_cycles: int = 10
    """Number of cycles between checkpoints (for cycle-based strategy)."""

    storage_path: Optional[str] = None
    """Path for checkpoint storage. None uses default."""

    max_checkpoints: int = 10
    """Maximum number of checkpoints to retain."""

    compress: bool = True
    """Whether to compress checkpoint data."""

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "strategy": self.strategy,
            "interval_seconds": self.interval_seconds,
            "interval_cycles": self.interval_cycles,
            "storage_path": self.storage_path,
            "max_checkpoints": self.max_checkpoints,
            "compress": self.compress,
        }


@dataclass
class HookConfig:
    """
    Configuration for execution hooks.

    Hooks allow custom code to run at various points during execution.
    """

    on_start: Optional[HookCallback] = None
    """Called when execution starts."""

    on_cycle: Optional[HookCallback] = None
    """Called at the start of each TAOD cycle."""

    on_think: Optional[HookCallback] = None
    """Called after Think phase."""

    on_act: Optional[HookCallback] = None
    """Called after Act phase (tool calls)."""

    on_observe: Optional[HookCallback] = None
    """Called after Observe phase."""

    on_decide: Optional[HookCallback] = None
    """Called after Decide phase."""

    on_tool_call: Optional[HookCallback] = None
    """Called before each tool call."""

    on_tool_result: Optional[HookCallback] = None
    """Called after each tool call."""

    on_error: Optional[HookCallback] = None
    """Called when an error occurs."""

    on_complete: Optional[HookCallback] = None
    """Called when execution completes."""

    on_interrupt: Optional[HookCallback] = None
    """Called when execution is interrupted."""

    def get_hooks(self) -> Dict[str, Optional[HookCallback]]:
        """Get all configured hooks as a dictionary."""
        return {
            "on_start": self.on_start,
            "on_cycle": self.on_cycle,
            "on_think": self.on_think,
            "on_act": self.on_act,
            "on_observe": self.on_observe,
            "on_decide": self.on_decide,
            "on_tool_call": self.on_tool_call,
            "on_tool_result": self.on_tool_result,
            "on_error": self.on_error,
            "on_complete": self.on_complete,
            "on_interrupt": self.on_interrupt,
        }


@dataclass
class LLMRoutingConfig:
    """
    Configuration for multi-LLM routing.

    Enables intelligent model selection based on task characteristics.
    Only applies to LocalKaizenAdapter.
    """

    enabled: bool = False
    """Whether LLM routing is enabled."""

    strategy: str = "balanced"
    """Routing strategy: 'rules', 'task_complexity', 'cost_optimized', 'quality_optimized', 'balanced'."""

    task_model_mapping: Dict[str, str] = field(default_factory=dict)
    """Map task types to specific models."""

    fallback_chain: List[str] = field(default_factory=list)
    """Ordered list of fallback models."""

    max_retries: int = 3
    """Maximum retries per model before fallback."""

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "strategy": self.strategy,
            "task_model_mapping": self.task_model_mapping,
            "fallback_chain": self.fallback_chain,
            "max_retries": self.max_retries,
        }


@dataclass
class AgentConfig:
    """
    Complete configuration for expert agent customization.

    Use AgentConfig when you need full control over agent behavior.
    For most use cases, the simpler Agent constructor parameters or
    CapabilityPresets are sufficient.

    Precedence: AgentConfig values > explicit parameters > defaults

    Examples:
        # Expert configuration
        config = AgentConfig(
            model="gpt-4",
            execution_mode=ExecutionMode.AUTONOMOUS,
            max_cycles=100,
            memory=my_custom_memory,
            runtime=my_custom_runtime,
            checkpoint=CheckpointConfig(strategy="on_cycle"),
            hooks=HookConfig(
                on_cycle=lambda ctx: print(f"Cycle {ctx['cycle']}"),
                on_error=lambda ctx: log_error(ctx['error']),
            ),
        )
        agent = Agent(config=config)

        # Override specific values
        config = AgentConfig.from_preset("developer")
        config.max_cycles = 200
        agent = Agent(config=config)
    """

    # === Core Configuration ===

    model: str = "gpt-4"
    """Primary model to use."""

    provider: Optional[str] = None
    """LLM provider. None for auto-detection based on model."""

    # === Execution Configuration ===

    execution_mode: ExecutionMode = ExecutionMode.SINGLE
    """Execution mode: SINGLE, MULTI, or AUTONOMOUS."""

    max_cycles: int = 100
    """Maximum TAOD cycles (AUTONOMOUS mode)."""

    max_turns: int = 50
    """Maximum conversation turns (MULTI mode)."""

    max_tool_calls: int = 1000
    """Maximum tool calls per session."""

    max_tokens_per_turn: int = 8192
    """Maximum tokens per turn."""

    timeout_seconds: float = 300.0
    """Overall execution timeout in seconds."""

    tool_timeout_seconds: float = 60.0
    """Individual tool call timeout in seconds."""

    # === Memory Configuration ===

    memory: Optional[Any] = None
    """Memory provider instance or shortcut string.

    Shortcuts: 'stateless', 'session', 'persistent', 'learning'
    Or pass a MemoryProvider instance directly.
    """

    memory_path: Optional[str] = None
    """Path for persistent memory storage."""

    max_memory_tokens: int = 16000
    """Maximum tokens to include from memory in context."""

    # === Tool Configuration ===

    tool_access: ToolAccess = ToolAccess.NONE
    """Tool access level: NONE, READ_ONLY, CONSTRAINED, FULL."""

    tools: Optional[List[Any]] = None
    """List of Tool instances to register."""

    allowed_tools: Optional[List[str]] = None
    """Whitelist of allowed tool names."""

    denied_tools: Optional[List[str]] = None
    """Blacklist of denied tool names."""

    require_tool_confirmation: bool = False
    """Whether to require confirmation for dangerous tools."""

    # === Runtime Configuration ===

    runtime: Optional[Any] = None
    """Runtime adapter instance or shortcut string.

    Shortcuts: 'local', 'claude_code', 'codex', 'gemini_cli'
    Or pass a RuntimeAdapter instance directly.
    """

    runtime_config: Dict[str, Any] = field(default_factory=dict)
    """Additional runtime configuration."""

    # === LLM Routing Configuration ===

    llm_routing: Optional[LLMRoutingConfig] = None
    """Multi-LLM routing configuration."""

    routing_strategy: str = "balanced"
    """Default routing strategy when llm_routing is enabled."""

    # === Checkpointing Configuration ===

    checkpoint: Optional[CheckpointConfig] = None
    """Checkpoint configuration for state persistence."""

    # === Hook Configuration ===

    hooks: Optional[HookConfig] = None
    """Execution hooks for custom callbacks."""

    # === Model Parameters ===

    temperature: float = 0.7
    """Model temperature for response generation."""

    top_p: float = 1.0
    """Top-p sampling parameter."""

    max_output_tokens: Optional[int] = None
    """Maximum output tokens. None for model default."""

    stop_sequences: List[str] = field(default_factory=list)
    """Stop sequences for generation."""

    # === System Prompt ===

    system_prompt: Optional[str] = None
    """Custom system prompt. None for default."""

    system_prompt_template: Optional[str] = None
    """System prompt template with {placeholders}."""

    # === Metadata ===

    name: Optional[str] = None
    """Agent name for identification."""

    description: Optional[str] = None
    """Agent description."""

    tags: List[str] = field(default_factory=list)
    """Tags for categorization."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional metadata."""

    # === Methods ===

    def get_capabilities(self) -> AgentCapabilities:
        """
        Build AgentCapabilities from this config.

        Returns:
            AgentCapabilities instance
        """
        return AgentCapabilities(
            execution_modes=[self.execution_mode],
            max_memory_depth=self._infer_memory_depth(),
            tool_access=self.tool_access,
            allowed_tools=self.allowed_tools,
            denied_tools=self.denied_tools,
            max_turns=self.max_turns,
            max_cycles=self.max_cycles,
            max_tool_calls=self.max_tool_calls,
            max_tokens_per_turn=self.max_tokens_per_turn,
            timeout_seconds=self.timeout_seconds,
            tool_timeout_seconds=self.tool_timeout_seconds,
        )

    def _infer_memory_depth(self) -> MemoryDepth:
        """Infer memory depth from configuration."""
        if self.memory is None:
            return MemoryDepth.STATELESS
        if isinstance(self.memory, str):
            try:
                return MemoryDepth(self.memory)
            except ValueError:
                return MemoryDepth.SESSION
        # Assume instance - check for persistence indicators
        return MemoryDepth.SESSION

    def to_dict(self) -> dict:
        """Serialize configuration to dictionary."""
        return {
            "model": self.model,
            "provider": self.provider,
            "execution_mode": self.execution_mode.value,
            "max_cycles": self.max_cycles,
            "max_turns": self.max_turns,
            "max_tool_calls": self.max_tool_calls,
            "max_tokens_per_turn": self.max_tokens_per_turn,
            "timeout_seconds": self.timeout_seconds,
            "tool_timeout_seconds": self.tool_timeout_seconds,
            "memory": self.memory if isinstance(self.memory, str) else None,
            "memory_path": self.memory_path,
            "max_memory_tokens": self.max_memory_tokens,
            "tool_access": self.tool_access.value,
            "allowed_tools": self.allowed_tools,
            "denied_tools": self.denied_tools,
            "require_tool_confirmation": self.require_tool_confirmation,
            "runtime": self.runtime if isinstance(self.runtime, str) else None,
            "runtime_config": self.runtime_config,
            "routing_strategy": self.routing_strategy,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_output_tokens": self.max_output_tokens,
            "stop_sequences": self.stop_sequences,
            "system_prompt": self.system_prompt,
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "metadata": self.metadata,
            "checkpoint": self.checkpoint.to_dict() if self.checkpoint else None,
            "llm_routing": self.llm_routing.to_dict() if self.llm_routing else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentConfig":
        """Create configuration from dictionary."""
        # Handle enum conversions
        if "execution_mode" in data and isinstance(data["execution_mode"], str):
            data["execution_mode"] = ExecutionMode(data["execution_mode"])
        if "tool_access" in data and isinstance(data["tool_access"], str):
            data["tool_access"] = ToolAccess(data["tool_access"])

        # Handle nested configs
        if "checkpoint" in data and data["checkpoint"]:
            data["checkpoint"] = CheckpointConfig(**data["checkpoint"])
        if "llm_routing" in data and data["llm_routing"]:
            data["llm_routing"] = LLMRoutingConfig(**data["llm_routing"])

        # Remove None values for cleaner initialization
        data = {k: v for k, v in data.items() if v is not None}

        return cls(**data)

    @classmethod
    def from_preset(cls, preset_name: str, **overrides) -> "AgentConfig":
        """
        Create configuration from a preset.

        Args:
            preset_name: Name of the preset
            **overrides: Override values

        Returns:
            AgentConfig instance

        Example:
            config = AgentConfig.from_preset("developer", max_cycles=200)
        """
        from kaizen.api.presets import CapabilityPresets

        preset_config = CapabilityPresets.get_preset(preset_name, **overrides)

        # Map preset config to AgentConfig fields
        return cls(
            model=preset_config.get("model", "gpt-4"),
            execution_mode=ExecutionMode(preset_config.get("execution_mode", "single")),
            max_cycles=preset_config.get("max_cycles", 100),
            max_turns=preset_config.get("max_turns", 50),
            timeout_seconds=preset_config.get("timeout_seconds", 300.0),
            memory=preset_config.get("memory"),
            memory_path=preset_config.get("memory_path"),
            tool_access=ToolAccess(preset_config.get("tool_access", "none")),
            allowed_tools=preset_config.get("allowed_tools"),
            **{k: v for k, v in overrides.items() if k not in preset_config},
        )

    def merge_with(self, **params) -> "AgentConfig":
        """
        Create a new config with merged parameters.

        Args:
            **params: Parameters to merge

        Returns:
            New AgentConfig with merged values
        """
        current = self.to_dict()
        current.update(params)
        return AgentConfig.from_dict(current)

    def __str__(self) -> str:
        return (
            f"AgentConfig("
            f"model={self.model!r}, "
            f"mode={self.execution_mode.value}, "
            f"tools={self.tool_access.value})"
        )
