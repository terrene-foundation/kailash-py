"""
LLM Routing Module for Kaizen Agent Framework.

Provides intelligent model selection based on task requirements,
cost optimization, and fallback chains.

Components:
- LLMCapabilities: Model capability registry
- TaskAnalyzer: Task complexity and type detection
- LLMRouter: Intelligent model routing
- FallbackRouter: Resilient routing with fallback chains
"""

from kaizen.llm.routing.analyzer import (
    TaskAnalysis,
    TaskAnalyzer,
    TaskComplexity,
    TaskType,
)
from kaizen.llm.routing.capabilities import (
    MODEL_REGISTRY,
    LLMCapabilities,
    get_model_capabilities,
    list_models,
    register_model,
)
from kaizen.llm.routing.fallback import FallbackRouter
from kaizen.llm.routing.router import LLMRouter, RoutingRule, RoutingStrategy

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
