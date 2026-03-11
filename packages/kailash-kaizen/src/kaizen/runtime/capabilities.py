"""
Runtime Capabilities for Runtime Abstraction Layer

Defines the RuntimeCapabilities dataclass that describes what each
autonomous agent runtime can do. Used for capability negotiation
and intelligent runtime selection.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class RuntimeCapabilities:
    """Capabilities declaration for an autonomous agent runtime.

    Describes what features, modalities, and resources a runtime supports.
    Used by RuntimeSelector to match tasks to appropriate runtimes.

    Attributes:
        runtime_name: Unique identifier for this runtime
        provider: Provider/vendor name (e.g., "anthropic", "openai", "kaizen")
        version: Runtime version string

        supports_streaming: Can stream responses token by token
        supports_tool_calling: Can invoke tools/functions
        supports_parallel_tools: Can execute multiple tools in parallel

        supports_vision: Can process images
        supports_audio: Can process audio
        supports_code_execution: Can execute code safely

        supports_file_access: Can read/write local files
        supports_web_access: Can fetch URLs
        supports_interrupt: Can be interrupted mid-execution

        max_context_tokens: Maximum input context size
        max_output_tokens: Maximum output size

        cost_per_1k_input_tokens: Cost for 1000 input tokens (USD)
        cost_per_1k_output_tokens: Cost for 1000 output tokens (USD)

        typical_latency_ms: Average response latency
        cold_start_ms: First request latency (if applicable)

        native_tools: List of built-in tool names
        supported_models: List of model identifiers this runtime can use

        metadata: Extension point for additional capabilities
    """

    # Identity
    runtime_name: str
    provider: str
    version: str = "1.0.0"

    # Core capabilities
    supports_streaming: bool = True
    supports_tool_calling: bool = True
    supports_parallel_tools: bool = False

    # Modality capabilities
    supports_vision: bool = False
    supports_audio: bool = False
    supports_code_execution: bool = False

    # Access capabilities
    supports_file_access: bool = False
    supports_web_access: bool = False
    supports_interrupt: bool = False

    # Context limits
    max_context_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None

    # Cost metrics (USD per 1000 tokens)
    cost_per_1k_input_tokens: Optional[float] = None
    cost_per_1k_output_tokens: Optional[float] = None

    # Latency metrics (milliseconds)
    typical_latency_ms: Optional[float] = None
    cold_start_ms: Optional[float] = None

    # Tool configuration
    native_tools: List[str] = field(default_factory=list)
    supported_models: List[str] = field(default_factory=list)

    # Extension point
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Internal: computed capability set for fast lookup
    _capability_set: Set[str] = field(default_factory=set, repr=False)

    def __post_init__(self):
        """Build capability set for fast lookup."""
        self._build_capability_set()

    def _build_capability_set(self) -> None:
        """Build the internal capability set from boolean attributes."""
        self._capability_set = set()

        capability_map = {
            "streaming": self.supports_streaming,
            "tool_calling": self.supports_tool_calling,
            "parallel_tools": self.supports_parallel_tools,
            "vision": self.supports_vision,
            "audio": self.supports_audio,
            "code_execution": self.supports_code_execution,
            "file_access": self.supports_file_access,
            "web_access": self.supports_web_access,
            "interrupt": self.supports_interrupt,
        }

        for name, supported in capability_map.items():
            if supported:
                self._capability_set.add(name)

        # Add native tools as capabilities
        for tool in self.native_tools:
            self._capability_set.add(f"tool:{tool}")

    def supports(self, requirement: str) -> bool:
        """Check if a single capability requirement is supported.

        Args:
            requirement: Capability name (e.g., "vision", "file_access", "tool:bash")

        Returns:
            True if the capability is supported
        """
        requirement_lower = requirement.lower()

        # Direct capability match
        if requirement_lower in self._capability_set:
            return True

        # Check for tool requirement (format: "tool:name")
        if requirement_lower.startswith("tool:"):
            tool_name = requirement_lower[5:]
            return (
                tool_name in self.native_tools
                or f"tool:{tool_name}" in self._capability_set
            )

        # Alias handling
        aliases = {
            "images": "vision",
            "image": "vision",
            "files": "file_access",
            "file": "file_access",
            "web": "web_access",
            "http": "web_access",
            "bash": "code_execution",
            "shell": "code_execution",
            "tools": "tool_calling",
            "stream": "streaming",
        }

        if requirement_lower in aliases:
            return aliases[requirement_lower] in self._capability_set

        return False

    def meets_requirements(self, requirements: List[str]) -> bool:
        """Check if all capability requirements are met.

        Args:
            requirements: List of required capabilities

        Returns:
            True if ALL requirements are met
        """
        return all(self.supports(req) for req in requirements)

    def get_missing_requirements(self, requirements: List[str]) -> List[str]:
        """Get list of requirements that are NOT met.

        Args:
            requirements: List of required capabilities

        Returns:
            List of unmet requirements
        """
        return [req for req in requirements if not self.supports(req)]

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> Optional[float]:
        """Estimate cost for given token counts.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Estimated cost in USD, or None if costs not configured
        """
        if (
            self.cost_per_1k_input_tokens is None
            or self.cost_per_1k_output_tokens is None
        ):
            return None

        input_cost = (input_tokens / 1000) * self.cost_per_1k_input_tokens
        output_cost = (output_tokens / 1000) * self.cost_per_1k_output_tokens
        return input_cost + output_cost

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "runtime_name": self.runtime_name,
            "provider": self.provider,
            "version": self.version,
            "supports_streaming": self.supports_streaming,
            "supports_tool_calling": self.supports_tool_calling,
            "supports_parallel_tools": self.supports_parallel_tools,
            "supports_vision": self.supports_vision,
            "supports_audio": self.supports_audio,
            "supports_code_execution": self.supports_code_execution,
            "supports_file_access": self.supports_file_access,
            "supports_web_access": self.supports_web_access,
            "supports_interrupt": self.supports_interrupt,
            "max_context_tokens": self.max_context_tokens,
            "max_output_tokens": self.max_output_tokens,
            "cost_per_1k_input_tokens": self.cost_per_1k_input_tokens,
            "cost_per_1k_output_tokens": self.cost_per_1k_output_tokens,
            "typical_latency_ms": self.typical_latency_ms,
            "cold_start_ms": self.cold_start_ms,
            "native_tools": self.native_tools,
            "supported_models": self.supported_models,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RuntimeCapabilities":
        """Create from dictionary."""
        return cls(
            runtime_name=data["runtime_name"],
            provider=data["provider"],
            version=data.get("version", "1.0.0"),
            supports_streaming=data.get("supports_streaming", True),
            supports_tool_calling=data.get("supports_tool_calling", True),
            supports_parallel_tools=data.get("supports_parallel_tools", False),
            supports_vision=data.get("supports_vision", False),
            supports_audio=data.get("supports_audio", False),
            supports_code_execution=data.get("supports_code_execution", False),
            supports_file_access=data.get("supports_file_access", False),
            supports_web_access=data.get("supports_web_access", False),
            supports_interrupt=data.get("supports_interrupt", False),
            max_context_tokens=data.get("max_context_tokens"),
            max_output_tokens=data.get("max_output_tokens"),
            cost_per_1k_input_tokens=data.get("cost_per_1k_input_tokens"),
            cost_per_1k_output_tokens=data.get("cost_per_1k_output_tokens"),
            typical_latency_ms=data.get("typical_latency_ms"),
            cold_start_ms=data.get("cold_start_ms"),
            native_tools=data.get("native_tools", []),
            supported_models=data.get("supported_models", []),
            metadata=data.get("metadata", {}),
        )


# Pre-defined capabilities for known runtimes

KAIZEN_LOCAL_CAPABILITIES = RuntimeCapabilities(
    runtime_name="kaizen_local",
    provider="kaizen",
    version="0.9.0",
    supports_streaming=True,
    supports_tool_calling=True,
    supports_parallel_tools=True,
    supports_vision=True,
    supports_audio=False,
    supports_code_execution=True,
    supports_file_access=True,
    supports_web_access=True,
    supports_interrupt=True,
    max_context_tokens=200000,
    max_output_tokens=8192,
    cost_per_1k_input_tokens=0.003,
    cost_per_1k_output_tokens=0.015,
    typical_latency_ms=500,
    native_tools=[
        "read_file",
        "write_file",
        "edit_file",
        "glob",
        "grep",
        "list_directory",
        "file_exists",
        "bash_command",
        "web_search",
        "web_fetch",
    ],
    supported_models=[
        "claude-3-5-sonnet-20241022",
        "claude-3-opus-20240229",
        "gpt-4-turbo",
        "gpt-4o",
        "gemini-1.5-pro",
    ],
)

CLAUDE_CODE_CAPABILITIES = RuntimeCapabilities(
    runtime_name="claude_code",
    provider="anthropic",
    version="1.0.0",
    supports_streaming=True,
    supports_tool_calling=True,
    supports_parallel_tools=True,
    supports_vision=True,
    supports_audio=False,
    supports_code_execution=True,
    supports_file_access=True,
    supports_web_access=True,
    supports_interrupt=True,
    max_context_tokens=200000,
    max_output_tokens=8192,
    cost_per_1k_input_tokens=0.003,
    cost_per_1k_output_tokens=0.015,
    typical_latency_ms=300,
    native_tools=[
        "Read",
        "Write",
        "Edit",
        "Glob",
        "Grep",
        "LS",
        "Bash",
        "WebFetch",
        "WebSearch",
        "Task",
    ],
    supported_models=["claude-3-5-sonnet-20241022"],
)

OPENAI_CODEX_CAPABILITIES = RuntimeCapabilities(
    runtime_name="openai_codex",
    provider="openai",
    version="1.0.0",
    supports_streaming=True,
    supports_tool_calling=True,
    supports_parallel_tools=True,
    supports_vision=True,
    supports_audio=False,
    supports_code_execution=True,
    supports_file_access=True,
    supports_web_access=True,
    supports_interrupt=False,
    max_context_tokens=128000,
    max_output_tokens=4096,
    cost_per_1k_input_tokens=0.01,
    cost_per_1k_output_tokens=0.03,
    typical_latency_ms=400,
    native_tools=["code_interpreter", "file_search"],
    supported_models=["gpt-4-turbo", "gpt-4o"],
)

GEMINI_CLI_CAPABILITIES = RuntimeCapabilities(
    runtime_name="gemini_cli",
    provider="google",
    version="1.0.0",
    supports_streaming=True,
    supports_tool_calling=True,
    supports_parallel_tools=False,
    supports_vision=True,
    supports_audio=True,
    supports_code_execution=True,
    supports_file_access=True,
    supports_web_access=True,
    supports_interrupt=False,
    max_context_tokens=1000000,
    max_output_tokens=8192,
    cost_per_1k_input_tokens=0.00125,
    cost_per_1k_output_tokens=0.005,
    typical_latency_ms=600,
    native_tools=["code_execution", "google_search"],
    supported_models=["gemini-1.5-pro", "gemini-1.5-flash"],
)
