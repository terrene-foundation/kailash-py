"""
LLM Capabilities and Model Registry.

Provides a standardized way to describe and query model capabilities
for intelligent routing decisions.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMCapabilities:
    """Capabilities and characteristics of an LLM model.

    Attributes:
        provider: Provider name (openai, anthropic, google, ollama, etc.)
        model: Model identifier (gpt-4, claude-3-opus, etc.)
        supports_vision: Can process images
        supports_audio: Can process audio
        supports_tool_calling: Supports function/tool calling
        supports_structured_output: Can output structured JSON
        supports_streaming: Supports streaming responses
        max_context: Maximum context window in tokens
        max_output: Maximum output tokens
        cost_per_1k_input: Cost per 1000 input tokens (USD)
        cost_per_1k_output: Cost per 1000 output tokens (USD)
        latency_p50_ms: Median response latency in milliseconds
        quality_score: Overall quality score (0.0-1.0)
        specialties: Areas of expertise (code, math, reasoning, creative, etc.)

    Example:
        >>> gpt4 = LLMCapabilities(
        ...     provider="openai",
        ...     model="gpt-4",
        ...     supports_vision=False,
        ...     supports_tool_calling=True,
        ...     max_context=8192,
        ...     cost_per_1k_input=0.03,
        ...     cost_per_1k_output=0.06,
        ...     quality_score=0.95,
        ...     specialties=["reasoning", "code", "analysis"],
        ... )
    """

    # Identity
    provider: str
    model: str

    # Capabilities
    supports_vision: bool = False
    supports_audio: bool = False
    supports_tool_calling: bool = True
    supports_structured_output: bool = True
    supports_streaming: bool = True

    # Context limits
    max_context: int = 8192
    max_output: int = 4096

    # Cost (per 1000 tokens, USD)
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0

    # Performance
    latency_p50_ms: int = 1000
    quality_score: float = 0.7

    # Specialties
    specialties: List[str] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        """Full model identifier (provider/model)."""
        return f"{self.provider}/{self.model}"

    @property
    def is_free(self) -> bool:
        """Whether the model is free to use."""
        return self.cost_per_1k_input == 0.0 and self.cost_per_1k_output == 0.0

    @property
    def is_local(self) -> bool:
        """Whether the model runs locally."""
        return self.provider in ("ollama", "docker", "local")

    def supports_specialty(self, specialty: str) -> bool:
        """Check if model specializes in a given area."""
        return specialty.lower() in [s.lower() for s in self.specialties]

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost for given token counts."""
        input_cost = (input_tokens / 1000) * self.cost_per_1k_input
        output_cost = (output_tokens / 1000) * self.cost_per_1k_output
        return input_cost + output_cost

    def matches_requirements(
        self,
        requires_vision: bool = False,
        requires_audio: bool = False,
        requires_tools: bool = False,
        requires_structured: bool = False,
        min_context: int = 0,
        min_quality: float = 0.0,
    ) -> bool:
        """Check if model meets specified requirements."""
        if requires_vision and not self.supports_vision:
            return False
        if requires_audio and not self.supports_audio:
            return False
        if requires_tools and not self.supports_tool_calling:
            return False
        if requires_structured and not self.supports_structured_output:
            return False
        if min_context > 0 and self.max_context < min_context:
            return False
        if min_quality > 0 and self.quality_score < min_quality:
            return False
        return True

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "provider": self.provider,
            "model": self.model,
            "supports_vision": self.supports_vision,
            "supports_audio": self.supports_audio,
            "supports_tool_calling": self.supports_tool_calling,
            "supports_structured_output": self.supports_structured_output,
            "supports_streaming": self.supports_streaming,
            "max_context": self.max_context,
            "max_output": self.max_output,
            "cost_per_1k_input": self.cost_per_1k_input,
            "cost_per_1k_output": self.cost_per_1k_output,
            "latency_p50_ms": self.latency_p50_ms,
            "quality_score": self.quality_score,
            "specialties": self.specialties,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "LLMCapabilities":
        """Create from dictionary."""
        return cls(
            provider=data["provider"],
            model=data["model"],
            supports_vision=data.get("supports_vision", False),
            supports_audio=data.get("supports_audio", False),
            supports_tool_calling=data.get("supports_tool_calling", True),
            supports_structured_output=data.get("supports_structured_output", True),
            supports_streaming=data.get("supports_streaming", True),
            max_context=data.get("max_context", 8192),
            max_output=data.get("max_output", 4096),
            cost_per_1k_input=data.get("cost_per_1k_input", 0.0),
            cost_per_1k_output=data.get("cost_per_1k_output", 0.0),
            latency_p50_ms=data.get("latency_p50_ms", 1000),
            quality_score=data.get("quality_score", 0.7),
            specialties=data.get("specialties", []),
        )


# Pre-populated Model Registry
# Prices and specs as of 2024/2025 (may need periodic updates)
MODEL_REGISTRY: Dict[str, LLMCapabilities] = {}


def _init_model_registry():
    """Initialize the model registry with common models."""
    global MODEL_REGISTRY

    # OpenAI Models
    MODEL_REGISTRY["gpt-4"] = LLMCapabilities(
        provider="openai",
        model="gpt-4",
        supports_vision=False,
        supports_tool_calling=True,
        max_context=8192,
        max_output=4096,
        cost_per_1k_input=0.03,
        cost_per_1k_output=0.06,
        latency_p50_ms=2000,
        quality_score=0.95,
        specialties=["reasoning", "code", "analysis", "math"],
    )

    MODEL_REGISTRY["gpt-4-turbo"] = LLMCapabilities(
        provider="openai",
        model="gpt-4-turbo",
        supports_vision=True,
        supports_tool_calling=True,
        max_context=128000,
        max_output=4096,
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.03,
        latency_p50_ms=1500,
        quality_score=0.93,
        specialties=["reasoning", "code", "analysis", "vision"],
    )

    MODEL_REGISTRY["gpt-4-vision"] = LLMCapabilities(
        provider="openai",
        model="gpt-4-vision-preview",
        supports_vision=True,
        supports_tool_calling=True,
        max_context=128000,
        max_output=4096,
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.03,
        latency_p50_ms=2000,
        quality_score=0.92,
        specialties=["vision", "analysis", "reasoning"],
    )

    MODEL_REGISTRY["gpt-4o"] = LLMCapabilities(
        provider="openai",
        model="gpt-4o",
        supports_vision=True,
        supports_audio=True,
        supports_tool_calling=True,
        max_context=128000,
        max_output=16384,
        cost_per_1k_input=0.005,
        cost_per_1k_output=0.015,
        latency_p50_ms=800,
        quality_score=0.94,
        specialties=["reasoning", "code", "vision", "multimodal"],
    )

    MODEL_REGISTRY["gpt-4o-mini"] = LLMCapabilities(
        provider="openai",
        model="gpt-4o-mini",
        supports_vision=True,
        supports_tool_calling=True,
        max_context=128000,
        max_output=16384,
        cost_per_1k_input=0.00015,
        cost_per_1k_output=0.0006,
        latency_p50_ms=500,
        quality_score=0.85,
        specialties=["general", "fast"],
    )

    MODEL_REGISTRY["gpt-3.5-turbo"] = LLMCapabilities(
        provider="openai",
        model="gpt-3.5-turbo",
        supports_vision=False,
        supports_tool_calling=True,
        max_context=16385,
        max_output=4096,
        cost_per_1k_input=0.0005,
        cost_per_1k_output=0.0015,
        latency_p50_ms=400,
        quality_score=0.75,
        specialties=["general", "fast", "simple"],
    )

    MODEL_REGISTRY["o1"] = LLMCapabilities(
        provider="openai",
        model="o1",
        supports_vision=False,
        supports_tool_calling=False,  # o1 has limited tool support
        max_context=200000,
        max_output=100000,
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.060,
        latency_p50_ms=10000,  # Reasoning takes time
        quality_score=0.98,
        specialties=["reasoning", "math", "code", "science"],
    )

    MODEL_REGISTRY["o1-mini"] = LLMCapabilities(
        provider="openai",
        model="o1-mini",
        supports_vision=False,
        supports_tool_calling=False,
        max_context=128000,
        max_output=65536,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.012,
        latency_p50_ms=5000,
        quality_score=0.90,
        specialties=["reasoning", "math", "code"],
    )

    # Anthropic Models
    MODEL_REGISTRY["claude-3-opus"] = LLMCapabilities(
        provider="anthropic",
        model="claude-3-opus-20240229",
        supports_vision=True,
        supports_tool_calling=True,
        max_context=200000,
        max_output=4096,
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
        latency_p50_ms=3000,
        quality_score=0.97,
        specialties=["reasoning", "code", "analysis", "creative", "vision"],
    )

    MODEL_REGISTRY["claude-3-sonnet"] = LLMCapabilities(
        provider="anthropic",
        model="claude-3-sonnet-20240229",
        supports_vision=True,
        supports_tool_calling=True,
        max_context=200000,
        max_output=4096,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        latency_p50_ms=1500,
        quality_score=0.90,
        specialties=["code", "analysis", "general"],
    )

    MODEL_REGISTRY["claude-3.5-sonnet"] = LLMCapabilities(
        provider="anthropic",
        model="claude-3-5-sonnet-20241022",
        supports_vision=True,
        supports_tool_calling=True,
        max_context=200000,
        max_output=8192,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        latency_p50_ms=1200,
        quality_score=0.94,
        specialties=["code", "analysis", "reasoning", "vision"],
    )

    MODEL_REGISTRY["claude-3-haiku"] = LLMCapabilities(
        provider="anthropic",
        model="claude-3-haiku-20240307",
        supports_vision=True,
        supports_tool_calling=True,
        max_context=200000,
        max_output=4096,
        cost_per_1k_input=0.00025,
        cost_per_1k_output=0.00125,
        latency_p50_ms=500,
        quality_score=0.80,
        specialties=["fast", "simple", "general"],
    )

    MODEL_REGISTRY["claude-3.5-haiku"] = LLMCapabilities(
        provider="anthropic",
        model="claude-3-5-haiku-20241022",
        supports_vision=True,
        supports_tool_calling=True,
        max_context=200000,
        max_output=8192,
        cost_per_1k_input=0.001,
        cost_per_1k_output=0.005,
        latency_p50_ms=400,
        quality_score=0.85,
        specialties=["fast", "code", "general"],
    )

    # Google Models
    MODEL_REGISTRY["gemini-pro"] = LLMCapabilities(
        provider="google",
        model="gemini-pro",
        supports_vision=False,
        supports_tool_calling=True,
        max_context=32760,
        max_output=8192,
        cost_per_1k_input=0.00025,
        cost_per_1k_output=0.0005,
        latency_p50_ms=1000,
        quality_score=0.85,
        specialties=["general", "reasoning"],
    )

    MODEL_REGISTRY["gemini-1.5-pro"] = LLMCapabilities(
        provider="google",
        model="gemini-1.5-pro",
        supports_vision=True,
        supports_audio=True,
        supports_tool_calling=True,
        max_context=1000000,
        max_output=8192,
        cost_per_1k_input=0.00125,
        cost_per_1k_output=0.005,
        latency_p50_ms=1500,
        quality_score=0.92,
        specialties=["reasoning", "code", "multimodal", "long-context"],
    )

    MODEL_REGISTRY["gemini-1.5-flash"] = LLMCapabilities(
        provider="google",
        model="gemini-1.5-flash",
        supports_vision=True,
        supports_audio=True,
        supports_tool_calling=True,
        max_context=1000000,
        max_output=8192,
        cost_per_1k_input=0.000075,
        cost_per_1k_output=0.0003,
        latency_p50_ms=300,
        quality_score=0.82,
        specialties=["fast", "general", "multimodal"],
    )

    MODEL_REGISTRY["gemini-2.0-flash"] = LLMCapabilities(
        provider="google",
        model="gemini-2.0-flash",
        supports_vision=True,
        supports_audio=True,
        supports_tool_calling=True,
        max_context=1000000,
        max_output=8192,
        cost_per_1k_input=0.0001,
        cost_per_1k_output=0.0004,
        latency_p50_ms=250,
        quality_score=0.88,
        specialties=["fast", "agentic", "multimodal"],
    )

    # Ollama (local) Models - Free but need local resources
    MODEL_REGISTRY["llama3.2"] = LLMCapabilities(
        provider="ollama",
        model="llama3.2",
        supports_vision=False,
        supports_tool_calling=True,
        max_context=128000,
        max_output=4096,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        latency_p50_ms=500,
        quality_score=0.78,
        specialties=["general", "code", "local"],
    )

    MODEL_REGISTRY["llama3.2:3b"] = LLMCapabilities(
        provider="ollama",
        model="llama3.2:3b",
        supports_vision=False,
        supports_tool_calling=True,
        max_context=128000,
        max_output=4096,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        latency_p50_ms=200,
        quality_score=0.70,
        specialties=["fast", "simple", "local"],
    )

    MODEL_REGISTRY["codellama"] = LLMCapabilities(
        provider="ollama",
        model="codellama",
        supports_vision=False,
        supports_tool_calling=False,
        max_context=16384,
        max_output=4096,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        latency_p50_ms=400,
        quality_score=0.80,
        specialties=["code", "local"],
    )

    MODEL_REGISTRY["mistral"] = LLMCapabilities(
        provider="ollama",
        model="mistral",
        supports_vision=False,
        supports_tool_calling=True,
        max_context=32768,
        max_output=4096,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        latency_p50_ms=300,
        quality_score=0.75,
        specialties=["general", "fast", "local"],
    )

    MODEL_REGISTRY["deepseek-coder"] = LLMCapabilities(
        provider="ollama",
        model="deepseek-coder",
        supports_vision=False,
        supports_tool_calling=False,
        max_context=16384,
        max_output=4096,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        latency_p50_ms=400,
        quality_score=0.82,
        specialties=["code", "local"],
    )

    MODEL_REGISTRY["qwen2.5-coder"] = LLMCapabilities(
        provider="ollama",
        model="qwen2.5-coder",
        supports_vision=False,
        supports_tool_calling=True,
        max_context=32768,
        max_output=8192,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
        latency_p50_ms=350,
        quality_score=0.85,
        specialties=["code", "reasoning", "local"],
    )

    logger.debug(f"Initialized MODEL_REGISTRY with {len(MODEL_REGISTRY)} models")


# Initialize registry on module load
_init_model_registry()


def get_model_capabilities(model: str) -> Optional[LLMCapabilities]:
    """Get capabilities for a model.

    Args:
        model: Model identifier (e.g., "gpt-4", "claude-3-opus")

    Returns:
        LLMCapabilities if found, None otherwise

    Example:
        >>> caps = get_model_capabilities("gpt-4")
        >>> caps.quality_score
        0.95
    """
    return MODEL_REGISTRY.get(model)


def register_model(capabilities: LLMCapabilities) -> None:
    """Register a new model in the registry.

    Args:
        capabilities: Model capabilities to register

    Example:
        >>> caps = LLMCapabilities(
        ...     provider="custom",
        ...     model="my-model",
        ...     quality_score=0.9,
        ... )
        >>> register_model(caps)
    """
    MODEL_REGISTRY[capabilities.model] = capabilities
    logger.debug(f"Registered model: {capabilities.full_name}")


def list_models(
    provider: Optional[str] = None,
    supports_vision: Optional[bool] = None,
    supports_tools: Optional[bool] = None,
    min_quality: Optional[float] = None,
    specialty: Optional[str] = None,
) -> List[str]:
    """List models matching criteria.

    Args:
        provider: Filter by provider (e.g., "openai", "anthropic")
        supports_vision: Filter by vision support
        supports_tools: Filter by tool calling support
        min_quality: Minimum quality score
        specialty: Required specialty

    Returns:
        List of model identifiers

    Example:
        >>> list_models(provider="openai", min_quality=0.9)
        ['gpt-4', 'gpt-4-turbo', 'gpt-4o', 'o1']
    """
    result = []

    for model_id, caps in MODEL_REGISTRY.items():
        # Filter by provider
        if provider and caps.provider != provider:
            continue

        # Filter by vision
        if supports_vision is not None and caps.supports_vision != supports_vision:
            continue

        # Filter by tools
        if supports_tools is not None and caps.supports_tool_calling != supports_tools:
            continue

        # Filter by quality
        if min_quality is not None and caps.quality_score < min_quality:
            continue

        # Filter by specialty
        if specialty and not caps.supports_specialty(specialty):
            continue

        result.append(model_id)

    return result


def get_cheapest_model(
    requires_vision: bool = False,
    requires_tools: bool = False,
    min_quality: float = 0.0,
) -> Optional[str]:
    """Get the cheapest model meeting requirements.

    Args:
        requires_vision: Must support vision
        requires_tools: Must support tool calling
        min_quality: Minimum quality score

    Returns:
        Model identifier if found, None otherwise
    """
    candidates = []

    for model_id, caps in MODEL_REGISTRY.items():
        if not caps.matches_requirements(
            requires_vision=requires_vision,
            requires_tools=requires_tools,
            min_quality=min_quality,
        ):
            continue

        # Calculate estimated cost for typical request (1000 in, 500 out)
        cost = caps.estimate_cost(1000, 500)
        candidates.append((model_id, cost))

    if not candidates:
        return None

    # Sort by cost
    candidates.sort(key=lambda x: x[1])
    return candidates[0][0]


def get_best_quality_model(
    requires_vision: bool = False,
    requires_tools: bool = False,
    max_cost_per_1k: float = float("inf"),
) -> Optional[str]:
    """Get the highest quality model meeting requirements.

    Args:
        requires_vision: Must support vision
        requires_tools: Must support tool calling
        max_cost_per_1k: Maximum cost per 1000 output tokens

    Returns:
        Model identifier if found, None otherwise
    """
    candidates = []

    for model_id, caps in MODEL_REGISTRY.items():
        if not caps.matches_requirements(
            requires_vision=requires_vision,
            requires_tools=requires_tools,
        ):
            continue

        if caps.cost_per_1k_output > max_cost_per_1k:
            continue

        candidates.append((model_id, caps.quality_score))

    if not candidates:
        return None

    # Sort by quality descending
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]
