"""
LLM Module for Kaizen Agent Framework.

Provides LLM routing, capability management, and intelligent model selection.
"""

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
]
