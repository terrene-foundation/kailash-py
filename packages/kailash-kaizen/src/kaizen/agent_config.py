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
    """Enable distributed tracing (OpenTelemetry spans exported to Jaeger)"""

    tracing_endpoint: str = "http://localhost:4317"
    """
    OTLP gRPC INGEST endpoint that spans are exported to.

    This is the collector's ingest port (4317), not the Jaeger web UI (16686).
    The default was ``http://localhost:16686`` while nothing read the field;
    now that it is wired, pointing it at the UI port would export every span
    into a socket that cannot accept them.
    """

    enable_metrics: bool = True
    """Enable Prometheus metrics collection"""

    metrics_port: int = 9090
    """
    Port for serving collected metrics.

    Read by :class:`~kaizen.core.autonomy.hooks.endpoints.MetricsEndpoint`,
    which the operator starts explicitly -- agent construction collects metrics
    into an in-process registry but never binds a listener, because opening a
    network port is not something a zero-config default may do on its own.
    """

    enable_logging: bool = True
    """Enable structured JSON logging"""

    log_level: str = "INFO"
    """Logging level (DEBUG, INFO, WARNING, ERROR)"""

    log_payload_keys: bool = False
    """
    Log the KEY NAMES of agent payloads (never the values). Off by default.

    ``enable_logging`` is on by default, so this hook runs on every agent
    construction in every downstream consumer. Key names are a genuine
    disclosure even with values withheld: a payload keyed ``ssn``,
    ``patient_diagnosis``, ``termination_reason`` or ``acme_contract_value``
    leaks schema, subject matter, and often the fact that such a record exists
    at all. That is a bounded leak, not an absent one, and a default-on logger
    is the wrong place to spend it.

    Set ``True`` to get payload structure (key names and field counts) in the
    lifecycle logs. Payload VALUES are never emitted at this level whatever
    this is set to -- see ``LoggingHook.log_full_payloads`` (#2070), which is a
    separate, additionally DEBUG-gated opt-in.
    """

    enable_audit: bool = True
    """Enable compliance audit trails"""

    audit_log_path: Optional[str] = None
    """
    Where the compliance audit trail is written.

    ``None`` -- the default -- is a SENTINEL meaning "the caller did not
    choose". ``__post_init__`` resolves it, per instance, to the XDG state
    location ``$XDG_STATE_HOME/kaizen/audit.jsonl`` (falling back to
    ``~/.local/state/kaizen/audit.jsonl``) via
    ``observability.audit_paths.default_audit_path``. Readers of this
    attribute therefore always see a concrete absolute path, never the
    sentinel.

    #2110 -- this used to default to the RELATIVE ``.kaizen/audit.jsonl``,
    with ``enable_audit`` defaulting ``True``, so a bare ``AgentConfig(...)``
    wrote into whatever directory the process happened to be launched from.
    The stray ``.kaizen/`` in the caller's working tree was the visible half;
    the half that matters is that running the same agent from two directories
    produced two DISJOINT trails, neither of which is the complete record an
    auditor asked for. Completeness is the entire value of a compliance
    artifact, so the default is ANCHORED rather than merely documented as
    CWD-relative: a library does not get to choose its caller's working
    directory, and a default that silently depends on it is not a default the
    caller can reason about.

    An EXPLICIT value is honoured verbatim -- relative ones included.
    ``audit_log_path="./my.jsonl"`` writes beside the process, because a
    caller who asks for CWD-relative semantics has chosen them. Only the
    DEFAULT moved.
    """

    # =========================================================================
    # LAYER 2: Checkpointing Configuration
    # =========================================================================

    enable_checkpointing: bool = False
    """Enable automatic checkpointing.

    #2111 — the stated reason for this default ("until checkpoint module is
    implemented") no longer holds: checkpointing is wired to
    ``StateManager`` over ``FilesystemStorage``. The default stays ``False``
    here so that constructing an ``AgentConfig`` directly has no filesystem
    side effect; ``Agent`` opts in for its own callers, and enabling it
    creates ``checkpoint_path``.
    """

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
    # LAYER 2: Governance Envelope (L3)
    # =========================================================================

    envelope: Optional[Any] = None
    """
    PACT constraint envelope governing this agent's authority.

    When set, downstream systems (TAOD runner, tool executor, delegation)
    enforce constraints from this envelope. When absent, no envelope
    enforcement is applied (L0-L2 backward-compatible behavior).

    Type: Optional[ConstraintEnvelopeConfig] from kailash.trust.pact.config.
    Typed as Any to avoid hard dependency on kailash-pact for minimal installs.
    """

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

    # Valid provider names (lowercase).
    #
    # Hand-maintained ON PURPOSE, and NOT derived from
    # ``LlmProvider._REGISTRY``. That registry is a model-PREFIX table — a
    # provider earns a row only once it has a confirmed prefix mapping — so
    # deriving from it was measured to drop nine dispatchable providers,
    # including ``mock`` (which the whole test harness runs on) and ``ollama``
    # (which detection itself used to return, so a derived allowlist would
    # have contradicted its own detector on day one).
    #
    # What IS enforced is one-directional containment: this set may never be
    # NARROWER than what the resolvers can emit, since a provider that can be
    # resolved but not validated makes the class reject its own output. The
    # reverse is left free, because a provider can be dispatchable without
    # owning a prefix row. Pinned by
    # ``tests/regression/test_issue_2069_provider_fail_closed.py``.
    #
    # ``deepseek`` was the live gap that invariant caught (#2069).
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
            "deepseek",
        }
    )

    def __post_init__(self):
        """Post-initialization validation and auto-configuration.

        #2069 — ORDER MATTERS HERE. The allowlist gate used to run only when
        ``llm_provider`` arrived non-None, which put it strictly ABOVE the
        auto-detect assignment and left the auto-detected path structurally
        un-validatable: whatever detection returned was adopted unchecked. It
        never bit only because every literal detection could return happened
        to sit in ``VALID_PROVIDERS``.

        So detection now runs FIRST and the gate sits BELOW it, where both
        paths pass through exactly one check. Moving the gate down is a
        prerequisite for delegating detection to a shared resolver — a
        resolver can legitimately return a provider this class does not list
        (``deepseek`` was the live example), and adopting that unchecked would
        be worse than the fail-open it replaced: inconsistent rather than
        merely wrong.
        """
        # Reject empty string. Only meaningful for an explicitly-supplied
        # value; auto-detection never produces one.
        if self.llm_provider == "":
            raise ValueError(
                "llm_provider cannot be empty string. "
                "Use None for auto-detection or specify a valid provider: "
                f"{sorted(self.VALID_PROVIDERS)}"
            )

        # Auto-detect LLM provider if not specified.
        #
        # #2069 — delegated to the shared resolver rather than kept as a local
        # substring table. This class used to own one, ending in a terminal
        # `else: return "openai"`, so a model it did not recognise was
        # dispatched to OpenAI under whatever credential was configured, with
        # the caller never told. `resolve_agent_provider` adds no mapping of
        # its own: it delegates to the registry-DERIVED prefix table (which
        # cannot drift from the provider registry) and raises
        # ConfigurationError naming the model when that cannot answer.
        #
        # #2220 removed the env fallback that used to sit behind that table.
        # It answered "which credential exists" in place of "which vendor
        # serves this model", so an unregistered model resolved to whichever
        # vendor's key happened to be exported — sending local-model prompts
        # to a third party. An unrecognised model now RAISES here, at config
        # construction, before any network call.
        auto_detected = self.llm_provider is None
        if auto_detected:
            from kaizen.core import _provider_env

            self.llm_provider = _provider_env.resolve_agent_provider(
                self.model, component="AgentConfig"
            )

        # ONE gate, reached by BOTH paths.
        if self.llm_provider.lower() not in self.VALID_PROVIDERS:
            if auto_detected:
                # Not user error — the resolver emitted something this class
                # cannot validate, so say that rather than blaming the caller.
                raise ValueError(
                    f"Auto-detected llm_provider '{self.llm_provider}' for model "
                    f"'{self.model}' is not in VALID_PROVIDERS: "
                    f"{sorted(self.VALID_PROVIDERS)}. The provider resolver and "
                    f"this allowlist have drifted apart; add the provider to "
                    f"VALID_PROVIDERS or pass llm_provider explicitly."
                )
            raise ValueError(
                f"Invalid llm_provider: '{self.llm_provider}'. "
                f"Valid providers: {sorted(self.VALID_PROVIDERS)}"
            )

        # #2110 -- resolve the audit-path sentinel.
        #
        # Deliberately NOT an import-time default (`= str(default_audit_path())`
        # in the class body): that form evaluates ONCE, when this module is
        # first imported, freezing whatever `$XDG_STATE_HOME`/`$HOME` happened
        # to hold at import. Anything that sets those afterwards -- a test
        # fixture, a service manager, a setuid drop -- would be silently
        # ignored, and the frozen value would be untestable by construction.
        # Resolving HERE makes it per-instance and honours the environment as
        # it stands when the config is built.
        #
        # The resolved value is MATERIALIZED onto the field rather than left
        # for each reader to resolve, so that every existing consumer
        # (`smart_defaults.create_observability`, the startup banner) keeps
        # reading a plain `str` and the resolved location shows up in anything
        # that displays the config. One resolution, one owner.
        if self.audit_log_path is None:
            from kaizen.core.autonomy.observability.audit_paths import (
                default_audit_path,
            )

            self.audit_log_path = str(default_audit_path())
        elif self.audit_log_path == "":
            # An empty path would resolve to the CWD itself. Refuse rather
            # than quietly substituting the default: the caller passed
            # something, and silently overriding it is how a compliance sink
            # ends up somewhere nobody chose.
            raise ValueError(
                "audit_log_path cannot be empty string. Pass None for the "
                "default location, or an explicit path."
            )

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
            "envelope": (
                self.envelope.to_dict()  # type: ignore[union-attr]
                if self.envelope is not None and hasattr(self.envelope, "to_dict")
                else self.envelope
            ),
            "enabled_features": self.get_enabled_features(),
        }

    def __repr__(self) -> str:
        """String representation."""
        features = ", ".join(self.get_enabled_features())
        return (
            f"AgentConfig(model={self.model}, agent_type={self.agent_type}, "
            f"features=[{features}])"
        )
