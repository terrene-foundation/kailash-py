"""
Agent Configuration for Unified Agent API

Provides configuration system for the unified Agent class with smart defaults
and progressive disclosure (Layer 1 → Layer 2 → Layer 3).

Part of ADR-020: Unified Agent API Architecture
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class AgentConfig:
    """
    Configuration for unified Agent API.

    Supports 3-layer architecture:
    - Layer 1 (Zero-Config): Smart defaults for everything
    - Layer 2 (Configuration): Behavioral parameters
    - Layer 3 (Expert Override): Custom implementations

    Example (Layer 1 - Zero-Config):
        >>> config = AgentConfig(model="gpt-4")
        >>> # All defaults auto-configured

    Example (Layer 2 - Configuration):
        >>> config = AgentConfig(
        ...     model="gpt-4",
        ...     agent_type="react",
        ...     memory_turns=20,
        ...     tools=["read_file", "http_get"],
        ...     budget_limit_usd=5.0,
        ... )

    Example (Layer 3 - Expert Override):
        >>> config = AgentConfig(
        ...     model="gpt-4",
        ...     custom_memory=RedisMemory(),
        ...     custom_mcp_servers=[{"name": "custom", "command": "python", "args": ["-m", "my.mcp.server"]}],
        ... )
    """

    # =========================================================================
    # REQUIRED: Core model configuration
    # =========================================================================

    model: str
    """LLM model name (e.g., 'gpt-4', 'claude-3', 'gpt-3.5-turbo')"""

    llm_provider: Optional[str] = None
    """LLM provider (auto-detected from model if not specified)"""

    # =========================================================================
    # LAYER 2: Agent Type & Behavior
    # =========================================================================

    agent_type: str = "simple"
    """
    Agent behavior preset.

    Available types:
    - "simple": Direct Q&A (default)
    - "react": Reasoning + Action cycles
    - "cot": Chain of thought reasoning
    - "rag": Retrieval-augmented generation
    - "autonomous": Full autonomous agent
    - "vision": Vision processing
    - "audio": Audio transcription
    """

    temperature: float = 0.7
    """Sampling temperature (0.0 = deterministic, 1.0 = creative)"""

    max_tokens: Optional[int] = None
    """Maximum tokens to generate (None = model default)"""

    # =========================================================================
    # LAYER 2: Memory Configuration
    # =========================================================================

    memory_turns: Optional[int] = 10
    """
    Number of conversation turns to remember.

    - None: Memory disabled
    - int: BufferMemory with specified turns (default: 10)
    """

    memory_backend: str = "buffer"
    """
    Memory backend type.

    - "buffer": In-memory buffer (default)
    - "semantic": Semantic similarity search
    - "persistent": DataFlow-backed persistence
    """

    # =========================================================================
    # LAYER 2: Tool Configuration
    # =========================================================================

    tools: Union[str, List[str], None] = "all"
    """
    Tools to enable.

    - "all": All 12 builtin tools (default)
    - list: Subset of tools (e.g., ["read_file", "http_get"])
    - None: No tools
    """

    # =========================================================================
    # LAYER 2: Observability Configuration
    # =========================================================================

    enable_tracing: bool = True
    """Enable distributed tracing (Jaeger)"""

    tracing_endpoint: str = "http://localhost:16686"
    """Jaeger tracing endpoint"""

    enable_metrics: bool = True
    """Enable Prometheus metrics collection"""

    metrics_port: int = 9090
    """Prometheus metrics port"""

    enable_logging: bool = True
    """Enable structured JSON logging"""

    log_level: str = "INFO"
    """Logging level (DEBUG, INFO, WARNING, ERROR)"""

    enable_audit: bool = True
    """Enable compliance audit trails"""

    audit_log_path: str = ".kaizen/audit.jsonl"
    """Audit log file path"""

    # =========================================================================
    # LAYER 2: Checkpointing Configuration
    # =========================================================================

    enable_checkpointing: bool = False
    """Enable automatic checkpointing (disabled by default until checkpoint module is implemented)"""

    checkpoint_path: str = ".kaizen/checkpoints"
    """Checkpoint storage directory"""

    checkpoint_interval: Optional[int] = None
    """
    Checkpoint interval in iterations.

    - None: Checkpoint on demand only (default)
    - int: Automatic checkpoint every N iterations
    """

    # =========================================================================
    # LAYER 2: Streaming Configuration
    # =========================================================================

    streaming: bool = True
    """Enable streaming output"""

    stream_output: str = "console"
    """
    Streaming output destination.

    - "console": Rich console output (default)
    - "http": Server-sent events (SSE)
    - "none": No streaming
    """

    # =========================================================================
    # LAYER 2: Control Protocol Configuration
    # =========================================================================

    control_protocol: str = "cli"
    """
    Control protocol transport.

    - "cli": CLI-based interaction (default)
    - "http": HTTP/SSE transport
    - "stdio": Standard I/O transport
    - "memory": In-memory transport (testing)
    """

    # =========================================================================
    # LAYER 2: Error Handling Configuration
    # =========================================================================

    max_retries: int = 3
    """Maximum retries on error"""

    retry_delay: float = 1.0
    """Delay between retries (seconds)"""

    # =========================================================================
    # LAYER 2: Cost Tracking Configuration
    # =========================================================================

    budget_limit_usd: Optional[float] = None
    """
    Maximum cost in USD.

    - None: No limit (default)
    - float: Budget constraint (e.g., 5.0 = $5 limit)
    """

    warn_threshold: float = 0.8
    """Warn when budget usage reaches this threshold (default: 80%)"""

    # =========================================================================
    # LAYER 3: Expert Overrides (Custom Implementations)
    # =========================================================================

    custom_memory: Optional[Any] = None
    """Custom memory implementation (overrides memory_turns)"""

    custom_mcp_servers: Optional[List[Dict[str, Any]]] = None
    """Custom MCP server configurations (overrides tools)"""

    custom_hook_manager: Optional[Any] = None
    """Custom hook manager (overrides observability defaults)"""

    custom_checkpoint_manager: Optional[Any] = None
    """Custom checkpoint manager (overrides checkpointing defaults)"""

    custom_control_protocol: Optional[Any] = None
    """Custom control protocol (overrides control_protocol default)"""

    # =========================================================================
    # INTERNAL: Agent-specific configuration
    # =========================================================================

    instructions: Optional[str] = None
    """System instructions for the agent"""

    signature: Optional[Any] = None
    """Signature definition (auto-generated from agent_type if not provided)"""

    session_id: Optional[str] = None
    """Session ID for memory continuity"""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional metadata"""

    # =========================================================================
    # Helper Methods
    # =========================================================================

    # Valid provider names (lowercase)
    VALID_PROVIDERS = frozenset(
        {
            "openai",
            "azure",
            "anthropic",
            "ollama",
            "docker",
            "cohere",
            "huggingface",
            "google",
            "gemini",
            "perplexity",
            "pplx",
            "mock",
        }
    )

    def __post_init__(self):
        """Post-initialization validation and auto-configuration."""
        # Validate llm_provider if explicitly set
        if self.llm_provider is not None:
            # Reject empty string
            if self.llm_provider == "":
                raise ValueError(
                    "llm_provider cannot be empty string. "
                    "Use None for auto-detection or specify a valid provider: "
                    f"{sorted(self.VALID_PROVIDERS)}"
                )
            # Validate against known providers
            if self.llm_provider.lower() not in self.VALID_PROVIDERS:
                raise ValueError(
                    f"Invalid llm_provider: '{self.llm_provider}'. "
                    f"Valid providers: {sorted(self.VALID_PROVIDERS)}"
                )

        # Auto-detect LLM provider if not specified
        if self.llm_provider is None:
            self.llm_provider = self._detect_provider_from_model(self.model)

    def _detect_provider_from_model(self, model: str) -> str:
        """
        Auto-detect LLM provider from model name.

        Args:
            model: Model name

        Returns:
            Provider name
        """
        model_lower = model.lower()

        if "gpt" in model_lower or "davinci" in model_lower:
            return "openai"
        elif "claude" in model_lower:
            return "anthropic"
        elif (
            "llama" in model_lower
            or "mistral" in model_lower
            or "bakllava" in model_lower
        ):
            return "ollama"
        elif "gemini" in model_lower:
            return "google"
        else:
            # Default to openai for unknown models
            return "openai"

    def has_custom_memory(self) -> bool:
        """Check if custom memory implementation is provided."""
        return self.custom_memory is not None

    def has_custom_tools(self) -> bool:
        """Check if custom MCP servers are provided."""
        return self.custom_mcp_servers is not None

    def has_custom_observability(self) -> bool:
        """Check if custom hook manager is provided."""
        return self.custom_hook_manager is not None

    def has_custom_checkpointing(self) -> bool:
        """Check if custom checkpoint manager is provided."""
        return self.custom_checkpoint_manager is not None

    def has_custom_control_protocol(self) -> bool:
        """Check if custom control protocol is provided."""
        return self.custom_control_protocol is not None

    def is_memory_enabled(self) -> bool:
        """Check if memory is enabled (either default or custom)."""
        return self.has_custom_memory() or self.memory_turns is not None

    def is_tools_enabled(self) -> bool:
        """Check if tools are enabled (either default or custom)."""
        return self.has_custom_tools() or (
            self.tools is not None and (self.tools == "all" or len(self.tools) > 0)
        )

    def is_observability_enabled(self) -> bool:
        """Check if observability is enabled (either default or custom)."""
        return self.has_custom_observability() or (
            self.enable_tracing
            or self.enable_metrics
            or self.enable_logging
            or self.enable_audit
        )

    def is_checkpointing_enabled(self) -> bool:
        """Check if checkpointing is enabled (either default or custom)."""
        return self.has_custom_checkpointing() or self.enable_checkpointing

    def get_enabled_features(self) -> List[str]:
        """
        Get list of enabled features.

        Returns:
            List of enabled feature names
        """
        features = []

        if self.is_memory_enabled():
            features.append("memory")

        if self.is_tools_enabled():
            features.append("tools")

        if self.is_observability_enabled():
            features.append("observability")

        if self.is_checkpointing_enabled():
            features.append("checkpointing")

        if self.streaming:
            features.append("streaming")

        if self.budget_limit_usd is not None:
            features.append("cost_tracking")

        return features

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "model": self.model,
            "llm_provider": self.llm_provider,
            "agent_type": self.agent_type,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "memory_turns": self.memory_turns,
            "memory_backend": self.memory_backend,
            "tools": self.tools,
            "enabled_features": self.get_enabled_features(),
        }

    def __repr__(self) -> str:
        """String representation."""
        features = ", ".join(self.get_enabled_features())
        return (
            f"AgentConfig(model={self.model}, agent_type={self.agent_type}, "
            f"features=[{features}])"
        )
