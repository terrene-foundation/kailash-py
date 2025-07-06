"""
RAG Workflow Registry

Central registry for discovering and accessing RAG workflows and strategies.
Provides a unified interface for users to find the right RAG approach.
"""

import logging
from typing import Any, Dict, List, Optional, Type

from .router import (
    RAGPerformanceMonitorNode,
    RAGQualityAnalyzerNode,
    RAGStrategyRouterNode,
)
from .strategies import (
    HierarchicalRAGNode,
    HybridRAGNode,
    RAGConfig,
    SemanticRAGNode,
    StatisticalRAGNode,
    create_hierarchical_rag_workflow,
    create_hybrid_rag_workflow,
    create_semantic_rag_workflow,
    create_statistical_rag_workflow,
)
from .workflows import (
    AdaptiveRAGWorkflowNode,
    AdvancedRAGWorkflowNode,
    RAGPipelineWorkflowNode,
    SimpleRAGWorkflowNode,
)

logger = logging.getLogger(__name__)


class RAGWorkflowRegistry:
    """
    Central registry for RAG workflows and strategies.

    Provides discovery, recommendation, and instantiation of RAG components
    based on user requirements and use cases.
    """

    def __init__(self):
        self._strategies = {}
        self._workflows = {}
        self._utilities = {}
        self._register_components()

    def _register_components(self):
        """Register all available RAG components"""

        # Core strategies
        self._strategies = {
            "semantic": {
                "class": SemanticRAGNode,
                "factory": create_semantic_rag_workflow,
                "description": "Semantic chunking with dense embeddings for conceptual queries",
                "use_cases": ["general Q&A", "narrative content", "conceptual queries"],
                "strengths": ["excellent semantic matching", "good for flowing text"],
                "performance": {
                    "speed": "fast",
                    "accuracy": "high",
                    "complexity": "low",
                },
            },
            "statistical": {
                "class": StatisticalRAGNode,
                "factory": create_statistical_rag_workflow,
                "description": "Statistical chunking with sparse retrieval for technical content",
                "use_cases": ["technical documentation", "code", "structured content"],
                "strengths": ["precise keyword matching", "handles technical terms"],
                "performance": {
                    "speed": "fast",
                    "accuracy": "high",
                    "complexity": "low",
                },
            },
            "hybrid": {
                "class": HybridRAGNode,
                "factory": create_hybrid_rag_workflow,
                "description": "Combines semantic + statistical for optimal coverage",
                "use_cases": ["mixed content", "general purpose", "maximum coverage"],
                "strengths": ["20-30% better performance", "comprehensive results"],
                "performance": {
                    "speed": "medium",
                    "accuracy": "very high",
                    "complexity": "medium",
                },
            },
            "hierarchical": {
                "class": HierarchicalRAGNode,
                "factory": create_hierarchical_rag_workflow,
                "description": "Multi-level processing preserving document structure",
                "use_cases": [
                    "long documents",
                    "structured content",
                    "complex queries",
                ],
                "strengths": ["maintains context", "handles complex documents"],
                "performance": {
                    "speed": "slow",
                    "accuracy": "very high",
                    "complexity": "high",
                },
            },
        }

        # Workflow components
        self._workflows = {
            "simple": {
                "class": SimpleRAGWorkflowNode,
                "description": "Basic RAG workflow for getting started",
                "complexity": "beginner",
                "features": ["semantic chunking", "dense retrieval", "single strategy"],
            },
            "advanced": {
                "class": AdvancedRAGWorkflowNode,
                "description": "Multi-strategy RAG with quality checks",
                "complexity": "intermediate",
                "features": [
                    "strategy selection",
                    "quality validation",
                    "performance monitoring",
                ],
            },
            "adaptive": {
                "class": AdaptiveRAGWorkflowNode,
                "description": "AI-driven strategy selection",
                "complexity": "advanced",
                "features": [
                    "LLM-powered routing",
                    "automatic optimization",
                    "context awareness",
                ],
            },
            "configurable": {
                "class": RAGPipelineWorkflowNode,
                "description": "Flexible pipeline for custom configurations",
                "complexity": "intermediate",
                "features": [
                    "runtime configuration",
                    "strategy switching",
                    "custom parameters",
                ],
            },
        }

        # Utility components
        self._utilities = {
            "router": {
                "class": RAGStrategyRouterNode,
                "description": "LLM-powered strategy selection",
                "use_case": "automatic strategy routing",
            },
            "quality_analyzer": {
                "class": RAGQualityAnalyzerNode,
                "description": "Analyzes RAG results quality",
                "use_case": "quality assessment and optimization",
            },
            "performance_monitor": {
                "class": RAGPerformanceMonitorNode,
                "description": "Monitors performance over time",
                "use_case": "performance tracking and insights",
            },
        }

    def list_strategies(self) -> Dict[str, Dict[str, Any]]:
        """List all available RAG strategies"""
        return {
            name: {
                "description": info["description"],
                "use_cases": info["use_cases"],
                "strengths": info["strengths"],
                "performance": info["performance"],
            }
            for name, info in self._strategies.items()
        }

    def list_workflows(self) -> Dict[str, Dict[str, Any]]:
        """List all available RAG workflows"""
        return {
            name: {
                "description": info["description"],
                "complexity": info["complexity"],
                "features": info["features"],
            }
            for name, info in self._workflows.items()
        }

    def list_utilities(self) -> Dict[str, Dict[str, Any]]:
        """List all available RAG utilities"""
        return {
            name: {"description": info["description"], "use_case": info["use_case"]}
            for name, info in self._utilities.items()
        }

    def recommend_strategy(
        self,
        document_count: int = 0,
        avg_document_length: int = 0,
        is_technical: bool = False,
        has_structure: bool = False,
        query_type: str = "general",
        performance_priority: str = "accuracy",
    ) -> Dict[str, Any]:
        """
        Recommend optimal RAG strategy based on use case characteristics.

        Args:
            document_count: Number of documents in collection
            avg_document_length: Average document length in characters
            is_technical: Whether content is technical/code-heavy
            has_structure: Whether documents have clear structure (headings, sections)
            query_type: Type of queries ("technical", "conceptual", "general")
            performance_priority: Priority ("speed", "accuracy", "coverage")

        Returns:
            Recommendation with strategy name, reasoning, and alternatives
        """

        # Rule-based recommendation logic
        recommendations = []

        # Hierarchical for structured long documents
        if has_structure and avg_document_length > 2000:
            recommendations.append(
                {
                    "strategy": "hierarchical",
                    "score": 0.9,
                    "reasoning": "Long structured documents benefit from hierarchical processing",
                }
            )

        # Statistical for technical content
        if is_technical or query_type == "technical":
            recommendations.append(
                {
                    "strategy": "statistical",
                    "score": 0.85,
                    "reasoning": "Technical content requires precise keyword matching",
                }
            )

        # Hybrid for large collections or when accuracy is priority
        if document_count > 50 or performance_priority == "accuracy":
            recommendations.append(
                {
                    "strategy": "hybrid",
                    "score": 0.8,
                    "reasoning": "Large collections and accuracy priority benefit from hybrid approach",
                }
            )

        # Semantic for conceptual queries or general content
        if query_type == "conceptual" or (not is_technical and not has_structure):
            recommendations.append(
                {
                    "strategy": "semantic",
                    "score": 0.75,
                    "reasoning": "Conceptual queries and general content work well with semantic matching",
                }
            )

        # Speed priority adjustments
        if performance_priority == "speed":
            for rec in recommendations:
                if rec["strategy"] in ["semantic", "statistical"]:
                    rec["score"] += 0.1
                elif rec["strategy"] == "hierarchical":
                    rec["score"] -= 0.2

        # Sort by score
        recommendations.sort(key=lambda x: x["score"], reverse=True)

        # Default fallback
        if not recommendations:
            recommendations.append(
                {
                    "strategy": "semantic",
                    "score": 0.7,
                    "reasoning": "Default strategy for general use cases",
                }
            )

        primary = recommendations[0]
        alternatives = recommendations[1:3] if len(recommendations) > 1 else []

        return {
            "recommended_strategy": primary["strategy"],
            "reasoning": primary["reasoning"],
            "confidence": primary["score"],
            "alternatives": [
                {"strategy": alt["strategy"], "reasoning": alt["reasoning"]}
                for alt in alternatives
            ],
            "strategy_details": self._strategies[primary["strategy"]],
        }

    def recommend_workflow(
        self,
        user_level: str = "beginner",
        use_case: str = "general",
        needs_customization: bool = False,
        needs_monitoring: bool = False,
    ) -> Dict[str, Any]:
        """
        Recommend optimal RAG workflow based on user requirements.

        Args:
            user_level: User experience level ("beginner", "intermediate", "advanced")
            use_case: Primary use case ("prototyping", "production", "research")
            needs_customization: Whether user needs runtime customization
            needs_monitoring: Whether user needs performance monitoring

        Returns:
            Workflow recommendation with details
        """

        # Workflow selection logic
        if user_level == "beginner" or use_case == "prototyping":
            workflow = "simple"
            reasoning = "Simple workflow is best for beginners and prototyping"
        elif needs_customization:
            workflow = "configurable"
            reasoning = "Configurable pipeline provides runtime flexibility"
        elif use_case == "research" or user_level == "advanced":
            workflow = "adaptive"
            reasoning = "Adaptive workflow provides AI-driven optimization for research"
        elif needs_monitoring or use_case == "production":
            workflow = "advanced"
            reasoning = "Advanced workflow includes monitoring for production use"
        else:
            workflow = "simple"
            reasoning = "Simple workflow covers most general use cases"

        return {
            "recommended_workflow": workflow,
            "reasoning": reasoning,
            "workflow_details": self._workflows[workflow],
            "suggested_utilities": self._get_suggested_utilities(
                workflow, needs_monitoring
            ),
        }

    def _get_suggested_utilities(
        self, workflow: str, needs_monitoring: bool
    ) -> List[str]:
        """Get suggested utility components for a workflow"""
        utilities = []

        if workflow == "adaptive":
            utilities.append("router")

        if workflow in ["advanced", "adaptive"] or needs_monitoring:
            utilities.extend(["quality_analyzer", "performance_monitor"])

        return utilities

    def create_strategy(
        self, strategy_name: str, config: Optional[RAGConfig] = None, **kwargs
    ):
        """Create a strategy instance"""
        if strategy_name not in self._strategies:
            raise ValueError(
                f"Unknown strategy: {strategy_name}. Available: {list(self._strategies.keys())}"
            )

        strategy_info = self._strategies[strategy_name]
        strategy_class = strategy_info["class"]

        # Create instance with config
        if config:
            return strategy_class(config=config, **kwargs)
        else:
            return strategy_class(**kwargs)

    def create_workflow(
        self, workflow_name: str, config: Optional[RAGConfig] = None, **kwargs
    ):
        """Create a workflow instance"""
        if workflow_name not in self._workflows:
            raise ValueError(
                f"Unknown workflow: {workflow_name}. Available: {list(self._workflows.keys())}"
            )

        workflow_info = self._workflows[workflow_name]
        workflow_class = workflow_info["class"]

        # Create instance with config
        if config:
            return workflow_class(config=config, **kwargs)
        else:
            return workflow_class(**kwargs)

    def create_utility(self, utility_name: str, **kwargs):
        """Create a utility instance"""
        if utility_name not in self._utilities:
            raise ValueError(
                f"Unknown utility: {utility_name}. Available: {list(self._utilities.keys())}"
            )

        utility_info = self._utilities[utility_name]
        utility_class = utility_info["class"]

        return utility_class(**kwargs)

    def get_quick_start_guide(self) -> str:
        """Get quick start guide for RAG toolkit"""
        return """
# RAG Toolkit Quick Start Guide

## 1. Choose Your Approach

### For Beginners:
```python
from kailash.nodes.rag import RAGWorkflowRegistry

registry = RAGWorkflowRegistry()
simple_rag = registry.create_workflow("simple")
```

### For Custom Requirements:
```python
# Get recommendation
recommendation = registry.recommend_strategy(
    document_count=100,
    avg_document_length=1500,
    is_technical=True
)

# Create recommended strategy
strategy = registry.create_strategy(recommendation["recommended_strategy"])
```

### For Production Use:
```python
# Advanced workflow with monitoring
advanced_rag = registry.create_workflow("advanced")
quality_analyzer = registry.create_utility("quality_analyzer")
performance_monitor = registry.create_utility("performance_monitor")
```

## 2. Integration Patterns

### Direct Usage:
```python
# Use strategy directly
semantic_rag = registry.create_strategy("semantic")
result = semantic_rag.execute(documents=docs, operation="index")
```

### In Workflows:
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.logic import SwitchNode

builder = WorkflowBuilder()

# Add RAG router
router = registry.create_utility("router")
builder.add_node(router, "rag_router")

# Add strategies
semantic_rag = registry.create_strategy("semantic")
hybrid_rag = registry.create_strategy("hybrid")

builder.add_node(semantic_rag, "semantic_strategy")
builder.add_node(hybrid_rag, "hybrid_strategy")

# Add routing logic
switch = SwitchNode(
    condition_field="strategy",
    routes={
        "semantic": "semantic_strategy",
        "hybrid": "hybrid_strategy"
    }
)
builder.add_node(switch, "strategy_switch")

# Connect pipeline
builder.connect("rag_router", "strategy_switch")
builder.connect("strategy_switch", "semantic_strategy", route="semantic")
builder.connect("strategy_switch", "hybrid_strategy", route="hybrid")
```

## 3. Available Components

### Strategies:
- **semantic**: Best for general content and conceptual queries
- **statistical**: Best for technical documentation and code
- **hybrid**: Best for mixed content (20-30% better performance)
- **hierarchical**: Best for long, structured documents

### Workflows:
- **simple**: Basic RAG for getting started
- **advanced**: Multi-strategy with quality checks
- **adaptive**: AI-driven strategy selection
- **configurable**: Flexible runtime configuration

### Utilities:
- **router**: LLM-powered strategy selection
- **quality_analyzer**: Results quality assessment
- **performance_monitor**: Performance tracking over time

## 4. Best Practices

1. **Start Simple**: Use SimpleRAGWorkflowNode for prototyping
2. **Measure Performance**: Always use quality analyzer in production
3. **Let AI Decide**: Use AdaptiveRAGWorkflowNode for optimal results
4. **Monitor Over Time**: Use performance monitor for continuous improvement
5. **Customize When Needed**: Use configurable pipeline for specific requirements

For detailed examples, see: sdk-users/workflows/by-pattern/rag/
"""

    def get_strategy_comparison(self) -> Dict[str, Any]:
        """Get detailed comparison of all strategies"""
        comparison = {
            "performance_matrix": {
                "semantic": {"speed": 9, "accuracy": 8, "complexity": 3},
                "statistical": {"speed": 9, "accuracy": 8, "complexity": 3},
                "hybrid": {"speed": 7, "accuracy": 9, "complexity": 6},
                "hierarchical": {"speed": 5, "accuracy": 9, "complexity": 8},
            },
            "use_case_fit": {
                "general_qa": ["semantic", "hybrid"],
                "technical_docs": ["statistical", "hybrid"],
                "long_documents": ["hierarchical", "hybrid"],
                "mixed_content": ["hybrid", "adaptive"],
                "code_search": ["statistical", "hybrid"],
            },
            "selection_guide": {
                "prioritize_speed": ["semantic", "statistical"],
                "prioritize_accuracy": ["hybrid", "hierarchical"],
                "large_collections": ["hybrid", "hierarchical"],
                "technical_content": ["statistical", "hybrid"],
                "narrative_content": ["semantic", "hybrid"],
            },
        }

        return comparison


# Global registry instance
rag_registry = RAGWorkflowRegistry()
