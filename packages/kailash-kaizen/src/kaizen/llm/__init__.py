"""
LLM Module for Kaizen Agent Framework.

Provides LLM routing, capability management, intelligent model selection,
and LLM-first reasoning helpers (similarity + capability matching).
"""

from kaizen.llm.reasoning import (
    CapabilityMatchAgent,
    CapabilityMatchSignature,
    TextSimilarityAgent,
    TextSimilaritySignature,
    clear_reasoning_cache,
    get_capability_match_agent,
    get_text_similarity_agent,
    llm_capability_match,
    llm_text_similarity,
)
from kaizen.llm.routing import (  # Capabilities; Task Analysis; Routing
    MODEL_REGISTRY,
    FallbackRouter,
    LLMCapabilities,
    LLMRouter,
    RoutingRule,
    RoutingStrategy,
    TaskAnalysis,
    TaskAnalyzer,
    TaskComplexity,
    TaskType,
    get_model_capabilities,
    list_models,
    register_model,
)

__all__ = [
    # Capabilities
    "LLMCapabilities",
    "MODEL_REGISTRY",
    "get_model_capabilities",
    "register_model",
    "list_models",
    # Task Analysis
    "TaskComplexity",
    "TaskType",
    "TaskAnalysis",
    "TaskAnalyzer",
    # Routing
    "RoutingStrategy",
    "RoutingRule",
    "LLMRouter",
    "FallbackRouter",
    # LLM-first reasoning
    "TextSimilaritySignature",
    "CapabilityMatchSignature",
    "TextSimilarityAgent",
    "CapabilityMatchAgent",
    "llm_text_similarity",
    "llm_capability_match",
    "get_text_similarity_agent",
    "get_capability_match_agent",
    "clear_reasoning_cache",
]
