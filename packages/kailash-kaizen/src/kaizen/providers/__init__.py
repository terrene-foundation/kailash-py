"""
Kaizen Provider Integrations.

Supports multiple LLM providers with optional dependencies.
Following DataFlow/Nexus pattern for availability checks.
"""

# Check Ollama availability
OLLAMA_AVAILABLE = False
try:
    import ollama

    OLLAMA_AVAILABLE = True
except ImportError:
    ollama = None

# Export availability flag
__all__ = ["OLLAMA_AVAILABLE"]

if OLLAMA_AVAILABLE:
    from .ollama_model_manager import ModelInfo, OllamaModelManager
    from .ollama_provider import OllamaConfig, OllamaProvider
    from .ollama_vision_provider import OllamaVisionConfig, OllamaVisionProvider

    __all__.extend(
        [
            "OllamaProvider",
            "OllamaConfig",
            "OllamaModelManager",
            "ModelInfo",
            "OllamaVisionProvider",
            "OllamaVisionConfig",
        ]
    )
