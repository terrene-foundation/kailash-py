"""AI and ML nodes for the Kailash SDK."""

# Import A2A communication nodes
# Import from canonical provider locations (SPEC-02)
from kaizen.providers.base import LLMProvider
from kaizen.providers.llm.anthropic import AnthropicProvider
from kaizen.providers.llm.azure import AzureAIFoundryProvider
from kaizen.providers.llm.docker import DockerModelRunnerProvider
from kaizen.providers.llm.google import GoogleGeminiProvider
from kaizen.providers.llm.mock import MockProvider
from kaizen.providers.llm.ollama import OllamaProvider
from kaizen.providers.llm.openai import OpenAIProvider
from kaizen.providers.llm.perplexity import PerplexityProvider
from kaizen.providers.registry import PROVIDERS, get_available_providers, get_provider

from .a2a import A2AAgentNode, A2ACoordinatorNode, SharedMemoryPoolNode
from .agents import ChatAgent, FunctionCallingAgent, PlanningAgent, RetrievalAgent
from .embedding_generator import EmbeddingGeneratorNode
from .hybrid_search import AdaptiveSearchNode, HybridSearchNode

# Import intelligent orchestration nodes
from .intelligent_agent_orchestrator import (
    ConvergenceDetectorNode,
    IntelligentCacheNode,
    MCPAgentNode,
    OrchestrationManagerNode,
    QueryAnalysisNode,
)
from .iterative_llm_agent import IterativeLLMAgentNode
from .llm_agent import LLMAgentNode
from .models import (
    ModelPredictor,
    NamedEntityRecognizer,
    SentimentAnalyzer,
    TextClassifier,
    TextEmbedder,
    TextSummarizer,
)

# Import self-organizing nodes
from .self_organizing import (
    AgentPoolManagerNode,
    ProblemAnalyzerNode,
    SelfOrganizingAgentNode,
    SolutionEvaluatorNode,
    TeamFormationNode,
)

# Import A2A enhancement nodes
from .semantic_memory import (
    SemanticAgentMatchingNode,
    SemanticMemorySearchNode,
    SemanticMemoryStoreNode,
)
from .streaming_analytics import A2AMonitoringNode, StreamingAnalyticsNode

__all__ = [
    # Agents
    "ChatAgent",
    "RetrievalAgent",
    "FunctionCallingAgent",
    "PlanningAgent",
    "LLMAgentNode",
    "IterativeLLMAgentNode",
    # A2A Communication
    "A2AAgentNode",
    "SharedMemoryPoolNode",
    "A2ACoordinatorNode",
    # A2A Enhancement Nodes
    "SemanticMemoryStoreNode",
    "SemanticMemorySearchNode",
    "SemanticAgentMatchingNode",
    "HybridSearchNode",
    "AdaptiveSearchNode",
    "StreamingAnalyticsNode",
    "A2AMonitoringNode",
    # Self-Organizing Agents
    "AgentPoolManagerNode",
    "ProblemAnalyzerNode",
    "SelfOrganizingAgentNode",
    "SolutionEvaluatorNode",
    "TeamFormationNode",
    # Intelligent Orchestration
    "ConvergenceDetectorNode",
    "IntelligentCacheNode",
    "MCPAgentNode",
    "OrchestrationManagerNode",
    "QueryAnalysisNode",
    # Embedding and Vector Operations
    "EmbeddingGeneratorNode",
    # Provider Infrastructure
    "LLMProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "AzureAIFoundryProvider",
    "DockerModelRunnerProvider",
    "GoogleGeminiProvider",
    "PerplexityProvider",
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
