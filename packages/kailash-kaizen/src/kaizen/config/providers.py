"""
Model Provider Configuration System for Kaizen

Provides unified configuration and auto-detection for:
- OpenAI (gpt-4o-mini - fast, cost-effective)
- Azure AI Foundry (Azure-hosted models)
- Anthropic (Claude models)
- Google Gemini (gemini-2.0-flash - multimodal, embeddings)
- Perplexity AI (sonar - web search with citations)
- Ollama (local models)
- Docker Model Runner (local GPU-accelerated)
- Cohere (embeddings)
- HuggingFace (embeddings)

Implements smart provider detection based on environment and supports
explicit configuration when needed.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

logger = logging.getLogger(__name__)


ProviderType = Literal[
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
]


@dataclass
class ProviderConfig:
    """Configuration for a specific LLM provider."""

    provider: ProviderType
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: int = 30
    max_retries: int = 3


class ConfigurationError(Exception):
    """Raised when provider configuration is invalid or unavailable."""

    pass


def check_ollama_available() -> bool:
    """
    Check if Ollama is available locally.

    Returns:
        bool: True if Ollama is accessible, False otherwise
    """
    try:
        import requests

        # Use configurable base URL (matches get_ollama_config)
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        response = requests.get(f"{base_url}/api/tags", timeout=1)
        return response.status_code == 200
    except Exception:
        return False


def check_azure_available() -> bool:
    """
    Check if Azure AI Foundry is configured.

    Returns:
        bool: True if endpoint and API key are set
    """
    endpoint = os.getenv("AZURE_AI_INFERENCE_ENDPOINT")
    api_key = os.getenv("AZURE_AI_INFERENCE_API_KEY")
    return bool(endpoint and api_key)


def check_docker_available() -> bool:
    """
    Check if Docker Model Runner is running.

    Returns:
        bool: True if Docker Model Runner is accessible
    """
    try:
        import urllib.error
        import urllib.request

        base_url = os.getenv(
            "DOCKER_MODEL_RUNNER_URL",
            "http://localhost:12434/engines/llama.cpp/v1",
        )
        url = f"{base_url}/models"
        req = urllib.request.urlopen(url, timeout=2)
        return req.status == 200
    except Exception:
        return False


def check_anthropic_available() -> bool:
    """Check if Anthropic API key is configured."""
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def check_cohere_available() -> bool:
    """Check if Cohere API key is configured."""
    return bool(os.getenv("COHERE_API_KEY"))


def check_huggingface_available() -> bool:
    """
    Check if HuggingFace is available.

    Returns True if either:
    - HUGGINGFACE_API_KEY is set (API mode)
    - transformers package is installed (local mode)
    """
    if os.getenv("HUGGINGFACE_API_KEY"):
        return True
    try:
        import transformers  # noqa: F401

        return True
    except ImportError:
        return False


def check_google_available() -> bool:
    """
    Check if Google Gemini is available.

    Returns True if:
    - GOOGLE_API_KEY or GEMINI_API_KEY is set (API mode)
    - OR GOOGLE_CLOUD_PROJECT is set (Vertex AI mode)
    """
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    return bool(api_key or project)


def check_perplexity_available() -> bool:
    """
    Check if Perplexity AI is available.

    Returns True if PERPLEXITY_API_KEY is set.
    """
    return bool(os.getenv("PERPLEXITY_API_KEY"))


def get_openai_config(model: Optional[str] = None) -> ProviderConfig:
    """
    Get OpenAI provider configuration.

    Args:
        model: Optional model override (default: gpt-4o-mini)

    Returns:
        ProviderConfig for OpenAI

    Raises:
        ConfigurationError: If API key is not available
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ConfigurationError(
            "OpenAI API key not found. Set OPENAI_API_KEY environment variable."
        )

    default_model = "gpt-4o-mini"  # Fast, cost-effective model
    return ProviderConfig(
        provider="openai",
        model=model or os.getenv("KAIZEN_OPENAI_MODEL", default_model),
        api_key=api_key,
        timeout=int(os.getenv("KAIZEN_TIMEOUT", "30")),
        max_retries=int(os.getenv("KAIZEN_MAX_RETRIES", "3")),
    )


def get_ollama_config(model: Optional[str] = None) -> ProviderConfig:
    """
    Get Ollama provider configuration.

    Args:
        model: Optional model override (default: llama3.2)

    Returns:
        ProviderConfig for Ollama

    Raises:
        ConfigurationError: If Ollama is not available
    """
    if not check_ollama_available():
        raise ConfigurationError(
            "Ollama is not available. Install and start Ollama: https://ollama.ai"
        )

    default_model = "llama3.2"  # Using llama3.2 as it's more commonly available
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    return ProviderConfig(
        provider="ollama",
        model=model or os.getenv("KAIZEN_OLLAMA_MODEL", default_model),
        base_url=base_url,
        timeout=int(os.getenv("KAIZEN_TIMEOUT", "60")),  # Ollama may need more time
        max_retries=int(os.getenv("KAIZEN_MAX_RETRIES", "3")),
    )


def get_azure_config(model: Optional[str] = None) -> ProviderConfig:
    """
    Get Azure AI Foundry provider configuration.

    Args:
        model: Optional model override (default: gpt-4o)

    Returns:
        ProviderConfig for Azure AI Foundry

    Raises:
        ConfigurationError: If Azure credentials not available
    """
    if not check_azure_available():
        raise ConfigurationError(
            "Azure AI Foundry not configured. Set AZURE_AI_INFERENCE_ENDPOINT "
            "and AZURE_AI_INFERENCE_API_KEY environment variables."
        )

    default_model = "gpt-4o"  # Common Azure deployment
    return ProviderConfig(
        provider="azure",
        model=model or os.getenv("KAIZEN_AZURE_MODEL", default_model),
        api_key=os.getenv("AZURE_AI_INFERENCE_API_KEY"),
        base_url=os.getenv("AZURE_AI_INFERENCE_ENDPOINT"),
        timeout=int(os.getenv("KAIZEN_TIMEOUT", "60")),
        max_retries=int(os.getenv("KAIZEN_MAX_RETRIES", "3")),
    )


def get_docker_config(model: Optional[str] = None) -> ProviderConfig:
    """
    Get Docker Model Runner provider configuration.

    Args:
        model: Optional model override (default: ai/llama3.2)

    Returns:
        ProviderConfig for Docker Model Runner

    Raises:
        ConfigurationError: If Docker Model Runner not available
    """
    if not check_docker_available():
        raise ConfigurationError(
            "Docker Model Runner not available. Ensure Docker Desktop 4.40+ "
            "is running with Model Runner enabled: "
            "docker desktop enable model-runner --tcp 12434"
        )

    default_model = "ai/llama3.2"
    base_url = os.getenv(
        "DOCKER_MODEL_RUNNER_URL",
        "http://localhost:12434/engines/llama.cpp/v1",
    )

    return ProviderConfig(
        provider="docker",
        model=model or os.getenv("KAIZEN_DOCKER_MODEL", default_model),
        base_url=base_url,
        timeout=int(os.getenv("KAIZEN_TIMEOUT", "120")),  # Local models may be slower
        max_retries=int(os.getenv("KAIZEN_MAX_RETRIES", "3")),
    )


def get_anthropic_config(model: Optional[str] = None) -> ProviderConfig:
    """Get Anthropic provider configuration."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ConfigurationError(
            "Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable."
        )

    default_model = "claude-3-haiku-20240307"  # Fast, cost-effective
    return ProviderConfig(
        provider="anthropic",
        model=model or os.getenv("KAIZEN_ANTHROPIC_MODEL", default_model),
        api_key=api_key,
        timeout=int(os.getenv("KAIZEN_TIMEOUT", "30")),
        max_retries=int(os.getenv("KAIZEN_MAX_RETRIES", "3")),
    )


def get_cohere_config(model: Optional[str] = None) -> ProviderConfig:
    """Get Cohere provider configuration (embeddings only)."""
    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        raise ConfigurationError(
            "Cohere API key not found. Set COHERE_API_KEY environment variable."
        )

    default_model = "embed-english-v3.0"
    return ProviderConfig(
        provider="cohere",
        model=model or os.getenv("KAIZEN_COHERE_MODEL", default_model),
        api_key=api_key,
        timeout=int(os.getenv("KAIZEN_TIMEOUT", "30")),
        max_retries=int(os.getenv("KAIZEN_MAX_RETRIES", "3")),
    )


def get_huggingface_config(model: Optional[str] = None) -> ProviderConfig:
    """Get HuggingFace provider configuration (embeddings only)."""
    default_model = "sentence-transformers/all-MiniLM-L6-v2"
    return ProviderConfig(
        provider="huggingface",
        model=model or os.getenv("KAIZEN_HUGGINGFACE_MODEL", default_model),
        api_key=os.getenv("HUGGINGFACE_API_KEY"),  # Optional for local
        timeout=int(os.getenv("KAIZEN_TIMEOUT", "60")),
        max_retries=int(os.getenv("KAIZEN_MAX_RETRIES", "3")),
    )


def get_google_config(model: Optional[str] = None) -> ProviderConfig:
    """
    Get Google Gemini provider configuration.

    Args:
        model: Optional model override (default: gemini-2.0-flash)

    Returns:
        ProviderConfig for Google Gemini

    Raises:
        ConfigurationError: If API key or project is not available
    """
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    project = os.getenv("GOOGLE_CLOUD_PROJECT")

    if not api_key and not project:
        raise ConfigurationError(
            "Google credentials not found. Set GOOGLE_API_KEY, GEMINI_API_KEY, "
            "or GOOGLE_CLOUD_PROJECT environment variable."
        )

    default_model = "gemini-2.0-flash"  # Fast, efficient model
    return ProviderConfig(
        provider="google",
        model=model or os.getenv("KAIZEN_GOOGLE_MODEL", default_model),
        api_key=api_key,
        timeout=int(os.getenv("KAIZEN_TIMEOUT", "30")),
        max_retries=int(os.getenv("KAIZEN_MAX_RETRIES", "3")),
    )


def get_perplexity_config(model: Optional[str] = None) -> ProviderConfig:
    """
    Get Perplexity AI provider configuration.

    Perplexity provides LLM capabilities with integrated web search,
    delivering real-time information with source citations.

    Args:
        model: Optional model override (default: sonar)
            Available models:
            - sonar: Lightweight search model
            - sonar-pro: Advanced search capabilities
            - sonar-reasoning: Reasoning with search
            - sonar-reasoning-pro: Premier reasoning model
            - sonar-deep-research: Exhaustive research

    Returns:
        ProviderConfig for Perplexity

    Raises:
        ConfigurationError: If API key is not available
    """
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise ConfigurationError(
            "Perplexity API key not found. Set PERPLEXITY_API_KEY environment variable."
        )

    default_model = "sonar"  # Lightweight, fast model
    return ProviderConfig(
        provider="perplexity",
        model=model or os.getenv("KAIZEN_PERPLEXITY_MODEL", default_model),
        api_key=api_key,
        base_url="https://api.perplexity.ai",
        timeout=int(os.getenv("KAIZEN_TIMEOUT", "60")),  # Web search may take longer
        max_retries=int(os.getenv("KAIZEN_MAX_RETRIES", "3")),
    )


def get_mock_config(model: Optional[str] = None) -> ProviderConfig:
    """Get Mock provider configuration (testing only)."""
    return ProviderConfig(
        provider="mock",
        model=model or "mock-model",
        timeout=1,
        max_retries=0,
    )


def auto_detect_provider(preferred: Optional[ProviderType] = None) -> ProviderConfig:
    """
    Auto-detect available LLM provider.

    Detection order (if preferred not specified):
    1. OpenAI (if OPENAI_API_KEY is set)
    2. Azure AI Foundry (if AZURE_AI_INFERENCE_ENDPOINT is set)
    3. Anthropic (if ANTHROPIC_API_KEY is set)
    4. Google Gemini (if GOOGLE_API_KEY or GEMINI_API_KEY is set)
    5. Ollama (if running locally)
    6. Docker Model Runner (if running locally)

    Args:
        preferred: Optional preferred provider to try first

    Returns:
        ProviderConfig for first available provider

    Raises:
        ConfigurationError: If no provider is available
    """
    # Check for explicit override
    explicit_provider = os.getenv("KAIZEN_DEFAULT_PROVIDER")
    if explicit_provider:
        preferred = explicit_provider.lower()

    # Config function mapping for chat-capable providers
    config_functions = {
        "openai": get_openai_config,
        "azure": get_azure_config,
        "anthropic": get_anthropic_config,
        "google": get_google_config,
        "gemini": get_google_config,  # Alias
        "ollama": get_ollama_config,
        "docker": get_docker_config,
        "cohere": get_cohere_config,
        "huggingface": get_huggingface_config,
        "perplexity": get_perplexity_config,
        "pplx": get_perplexity_config,  # Alias
        "mock": get_mock_config,
    }

    # Try preferred provider first
    if preferred and preferred in config_functions:
        try:
            config = config_functions[preferred]()
            logger.info(
                f"Using preferred provider: {preferred} (model: {config.model})"
            )
            return config
        except ConfigurationError:
            logger.warning(
                f"Preferred provider {preferred} not available, trying alternatives"
            )

    # Auto-detect in order of preference (chat-capable providers only)
    detection_order = [
        "openai",
        "azure",
        "anthropic",
        "google",
        "perplexity",
        "ollama",
        "docker",
    ]

    for provider_name in detection_order:
        try:
            config = config_functions[provider_name]()
            logger.info(
                f"Auto-detected provider: {provider_name} (model: {config.model})"
            )
            return config
        except ConfigurationError:
            logger.debug(f"{provider_name} not available, trying next")

    # No provider available
    raise ConfigurationError(
        "No LLM provider available. Please configure one of:\n"
        "  1. Set OPENAI_API_KEY for OpenAI\n"
        "  2. Set AZURE_AI_INFERENCE_ENDPOINT and AZURE_AI_INFERENCE_API_KEY for Azure\n"
        "  3. Set ANTHROPIC_API_KEY for Anthropic\n"
        "  4. Set GOOGLE_API_KEY or GEMINI_API_KEY for Google Gemini\n"
        "  5. Set PERPLEXITY_API_KEY for Perplexity AI\n"
        "  6. Start Ollama (https://ollama.ai)\n"
        "  7. Enable Docker Model Runner (docker desktop enable model-runner --tcp 12434)"
    )


def get_provider_config(
    provider: Optional[ProviderType] = None, model: Optional[str] = None
) -> ProviderConfig:
    """
    Get provider configuration with auto-detection support.

    Args:
        provider: Optional explicit provider selection
        model: Optional model override

    Returns:
        ProviderConfig for requested or auto-detected provider

    Examples:
        >>> # Auto-detect provider
        >>> config = get_provider_config()

        >>> # Explicit provider
        >>> config = get_provider_config(provider="openai")

        >>> # Custom model
        >>> config = get_provider_config(provider="ollama", model="llama3.2")

        >>> # Azure provider
        >>> config = get_provider_config(provider="azure", model="gpt-4o")

        >>> # Google Gemini provider
        >>> config = get_provider_config(provider="google", model="gemini-2.0-flash")

        >>> # Docker Model Runner
        >>> config = get_provider_config(provider="docker", model="ai/llama3.2")

        >>> # Perplexity AI (web search enabled)
        >>> config = get_provider_config(provider="perplexity", model="sonar-pro")
    """
    config_functions = {
        "openai": get_openai_config,
        "azure": get_azure_config,
        "anthropic": get_anthropic_config,
        "google": get_google_config,
        "gemini": get_google_config,  # Alias
        "ollama": get_ollama_config,
        "docker": get_docker_config,
        "cohere": get_cohere_config,
        "huggingface": get_huggingface_config,
        "perplexity": get_perplexity_config,
        "pplx": get_perplexity_config,  # Alias
        "mock": get_mock_config,
    }

    if provider in config_functions:
        return config_functions[provider](model)
    else:
        # Auto-detect
        return auto_detect_provider(preferred=provider)


def provider_config_to_dict(config: ProviderConfig) -> Dict[str, Any]:
    """
    Convert ProviderConfig to dictionary suitable for Kaizen agent configuration.

    Args:
        config: ProviderConfig object

    Returns:
        Dict with provider configuration suitable for agent creation
    """
    config_dict = {
        "provider": config.provider,
        "model": config.model,
        "timeout": config.timeout,
    }

    # Add provider-specific fields
    if config.api_key:
        config_dict["api_key"] = config.api_key
    if config.base_url:
        config_dict["base_url"] = config.base_url

    # Add generation config
    config_dict["generation_config"] = {
        "max_retries": config.max_retries,
    }

    return config_dict


# Convenience function for examples
def get_default_model_config() -> Dict[str, Any]:
    """
    Get default model configuration for Kaizen examples.

    Auto-detects available provider and returns configuration dict
    ready for use with kaizen.create_agent().

    Returns:
        Dict with model configuration

    Examples:
        >>> import kaizen
        >>> from kaizen.config.providers import get_default_model_config
        >>>
        >>> config = get_default_model_config()
        >>> agent = kaizen.create_agent("my_agent", config=config)
    """
    provider_config = auto_detect_provider()
    return provider_config_to_dict(provider_config)
