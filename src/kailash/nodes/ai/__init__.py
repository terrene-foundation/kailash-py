"""AI and ML nodes for the Kailash SDK."""

from .agents import ChatAgent, FunctionCallingAgent, PlanningAgent, RetrievalAgent

# Import from unified ai_providers module
from .ai_providers import (
    PROVIDERS,
    AnthropicProvider,
    LLMProvider,
    MockProvider,
    OllamaProvider,
    OpenAIProvider,
    get_available_providers,
    get_provider,
)
from .embedding_generator import EmbeddingGenerator
from .llm_agent import LLMAgent
from .models import (
    ModelPredictor,
    NamedEntityRecognizer,
    SentimentAnalyzer,
    TextClassifier,
    TextEmbedder,
    TextSummarizer,
)

__all__ = [
    # Agents
    "ChatAgent",
    "RetrievalAgent",
    "FunctionCallingAgent",
    "PlanningAgent",
    "LLMAgent",
    # Embedding and Vector Operations
    "EmbeddingGenerator",
    # Provider Infrastructure
    "LLMProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "MockProvider",
    "get_provider",
    "get_available_providers",
    "PROVIDERS",
    # Models
    "TextClassifier",
    "TextEmbedder",
    "SentimentAnalyzer",
    "NamedEntityRecognizer",
    "ModelPredictor",
    "TextSummarizer",
]
