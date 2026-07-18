"""AI and ML nodes for the Kailash SDK."""

import importlib
import warnings
from typing import TYPE_CHECKING

# ---------------------------------------------------------------------------
# Legacy provider re-exports — deprecated (#1720; removed in Wave-C).
#
# These provider classes and registry accessors used to be eagerly re-exported
# here from their canonical ``kaizen.providers.*`` locations (SPEC-02). They are
# now lazy DeprecationWarning shims (PEP 562 ``__getattr__``): attribute ACCESS
# warns and resolves the real symbol, while a bare ``import kaizen.nodes.ai``
# does NOT warn. Import providers from ``kaizen.providers.llm.<mod>`` /
# ``kaizen.providers.registry`` (or the ``kaizen.providers`` barrel) instead.
# ---------------------------------------------------------------------------
_LEGACY_PROVIDER_MODULES: dict[str, str] = {
    "LLMProvider": "kaizen.providers.base",
    "AzureAIFoundryProvider": "kaizen.providers.llm.azure",
    "PROVIDERS": "kaizen.providers.registry",
    "get_available_providers": "kaizen.providers.registry",
    "get_provider": "kaizen.providers.registry",
}

if TYPE_CHECKING:
    # Analyzer-only imports so pyright / CodeQL py/undefined-export / Sphinx
    # autodoc still resolve the legacy names kept in ``__all__`` below.
    from kaizen.providers.base import LLMProvider
    from kaizen.providers.llm.azure import AzureAIFoundryProvider
    from kaizen.providers.registry import (
        PROVIDERS,
        get_available_providers,
        get_provider,
    )


def __getattr__(name: str) -> object:
    """Lazily resolve deprecated legacy provider re-exports (PEP 562)."""
    module_path = _LEGACY_PROVIDER_MODULES.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    warnings.warn(
        f"Importing {name} from {__name__} is deprecated and will be removed "
        f"in a future release (#1720); import from {module_path} instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    module = importlib.import_module(module_path)
    return getattr(module, name)


# Import A2A communication nodes
from .a2a import A2AAgentNode, A2ACoordinatorNode, SharedMemoryPoolNode
from .agents import ChatAgent, FunctionCallingAgent, PlanningAgent, RetrievalAgent
from .embedding_generator import EmbeddingGeneratorNode
from .hybrid_search import AdaptiveSearchNode, SemanticHybridSearchNode

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
    "SemanticHybridSearchNode",
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
    # Provider Infrastructure (kept — legacy chat providers retired in #1720 Wave-2)
    "LLMProvider",
    "AzureAIFoundryProvider",
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
