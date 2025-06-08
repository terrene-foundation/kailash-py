"""AI and ML nodes for the Kailash SDK."""

# Import A2A communication nodes
from .a2a import A2AAgentNode, A2ACoordinatorNode, SharedMemoryPoolNode
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
from .embedding_generator import EmbeddingGeneratorNode

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
