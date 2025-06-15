"""
RAG Workflow Nodes

Pre-built WorkflowNode components that combine multiple RAG strategies
and operations into reusable workflow patterns.
"""

import logging
from typing import Any, Dict, Optional

from ...workflow.builder import WorkflowBuilder
from ..base import Node, NodeParameter, register_node
from ..logic import SwitchNode
from ..logic.workflow import WorkflowNode
from .strategies import (
    RAGConfig,
    create_hierarchical_rag_workflow,
    create_hybrid_rag_workflow,
    create_semantic_rag_workflow,
    create_statistical_rag_workflow,
)

logger = logging.getLogger(__name__)


@register_node()
class SimpleRAGWorkflowNode(WorkflowNode):
    """
    Simple RAG Workflow Node

    Basic chunk → embed → store → retrieve pipeline using semantic chunking.
    Perfect for getting started with RAG or simple document Q&A.
    """

    def __init__(
        self, name: str = "simple_rag_workflow", config: Optional[RAGConfig] = None
    ):
        self.rag_config = config or RAGConfig()

        # Create semantic RAG workflow
        workflow_node = create_semantic_rag_workflow(self.rag_config)

        # Initialize as WorkflowNode
        super().__init__(
            workflow=workflow_node.workflow,
            name=name,
            description="Simple RAG workflow with semantic chunking and dense retrieval",
        )


@register_node()
class AdvancedRAGWorkflowNode(WorkflowNode):
    """
    Advanced RAG Workflow Node

    Multi-stage RAG pipeline with quality checks, multiple retrieval strategies,
    and result validation. Includes monitoring and performance optimization.
    """

    def __init__(
        self, name: str = "advanced_rag_workflow", config: Optional[RAGConfig] = None
    ):
        self.rag_config = config or RAGConfig()

        # Build advanced workflow
        workflow = self._create_advanced_workflow()

        super().__init__(
            workflow=workflow,
            name=name,
            description="Advanced RAG with quality checks and multi-stage processing",
        )

    def _create_advanced_workflow(self):
        """Create advanced RAG workflow with quality checks and monitoring"""
        builder = WorkflowBuilder()

        # Document quality analyzer
        quality_analyzer_id = builder.add_node(
            "PythonCodeNode",
            node_id="quality_analyzer",
            config={
                "code": """
# Analyze document quality and determine best RAG strategy
def analyze_documents(documents):
    analysis = {
        "total_docs": len(documents),
        "avg_length": sum(len(doc.get("content", "")) for doc in documents) / len(documents) if documents else 0,
        "has_structure": any("section" in doc or "heading" in doc for doc in documents),
        "is_technical": any(keyword in doc.get("content", "").lower()
                          for doc in documents
                          for keyword in ["code", "function", "algorithm", "api", "class"]),
        "recommended_strategy": "semantic"  # Default
    }

    # Determine best strategy based on analysis
    if analysis["has_structure"] and analysis["avg_length"] > 2000:
        analysis["recommended_strategy"] = "hierarchical"
    elif analysis["is_technical"]:
        analysis["recommended_strategy"] = "statistical"
    elif analysis["total_docs"] > 100:
        analysis["recommended_strategy"] = "hybrid"

    return analysis

result = {"analysis": analyze_documents(documents), "documents": documents}
"""
            },
        )

        # Strategy router using switch node
        router_id = builder.add_node(
            "SwitchNode",
            node_id="strategy_router",
            config={
                "condition_field": "analysis.recommended_strategy",
                "routes": {
                    "semantic": "semantic_rag_pipeline",
                    "statistical": "statistical_rag_pipeline",
                    "hybrid": "hybrid_rag_pipeline",
                    "hierarchical": "hierarchical_rag_pipeline",
                },
            },
        )

        # Add all RAG strategy pipelines
        semantic_workflow = create_semantic_rag_workflow(self.rag_config)
        statistical_workflow = create_statistical_rag_workflow(self.rag_config)
        hybrid_workflow = create_hybrid_rag_workflow(self.rag_config)
        hierarchical_workflow = create_hierarchical_rag_workflow(self.rag_config)

        semantic_id = builder.add_node(
            "WorkflowNode",
            node_id="semantic_rag_pipeline",
            config={"workflow": semantic_workflow.workflow},
        )

        statistical_id = builder.add_node(
            "WorkflowNode",
            node_id="statistical_rag_pipeline",
            config={"workflow": statistical_workflow.workflow},
        )

        hybrid_id = builder.add_node(
            "WorkflowNode",
            node_id="hybrid_rag_pipeline",
            config={"workflow": hybrid_workflow.workflow},
        )

        hierarchical_id = builder.add_node(
            "WorkflowNode",
            node_id="hierarchical_rag_pipeline",
            config={"workflow": hierarchical_workflow.workflow},
        )

        # Quality validator
        validator_id = builder.add_node(
            "PythonCodeNode",
            node_id="quality_validator",
            config={
                "code": """
def validate_rag_results(results, analysis):
    validation = {
        "results_count": len(results.get("documents", [])),
        "avg_score": sum(results.get("scores", [])) / len(results.get("scores", [])) if results.get("scores") else 0,
        "quality_score": 0.0,
        "passed": False
    }

    # Calculate quality score
    if validation["results_count"] > 0:
        validation["quality_score"] = validation["avg_score"] * (validation["results_count"] / 5.0)
        validation["passed"] = validation["quality_score"] > 0.5

    return {
        "results": results,
        "validation": validation,
        "strategy_used": analysis.get("recommended_strategy"),
        "final_status": "passed" if validation["passed"] else "needs_improvement"
    }

result = validate_rag_results(rag_results, analysis)
"""
            },
        )

        # Connect the advanced pipeline
        builder.add_connection(quality_analyzer_id, "result", router_id, "input")

        # Connect router to all strategy pipelines
        builder.add_connection(router_id, semantic_id, route="semantic")
        builder.add_connection(router_id, statistical_id, route="statistical")
        builder.add_connection(router_id, hybrid_id, route="hybrid")
        builder.add_connection(router_id, hierarchical_id, route="hierarchical")

        # Connect all pipelines to validator
        builder.add_connection(semantic_id, "output", validator_id, "rag_results")
        builder.add_connection(statistical_id, "output", validator_id, "rag_results")
        builder.add_connection(hybrid_id, "output", validator_id, "rag_results")
        builder.add_connection(hierarchical_id, "output", validator_id, "rag_results")
        builder.add_connection(quality_analyzer_id, "result", validator_id, "analysis")

        return builder.build(name="advanced_rag_workflow")


@register_node()
class AdaptiveRAGWorkflowNode(WorkflowNode):
    """
    Adaptive RAG Workflow Node

    AI-driven strategy selection that uses LLM to analyze documents and queries
    to automatically choose the optimal RAG approach for each use case.
    """

    def __init__(
        self,
        name: str = "adaptive_rag_workflow",
        llm_model: str = "gpt-4",
        config: Optional[RAGConfig] = None,
    ):
        self.rag_config = config or RAGConfig()
        self.llm_model = llm_model

        # Build adaptive workflow
        workflow = self._create_adaptive_workflow()

        super().__init__(
            workflow=workflow,
            name=name,
            description="AI-driven adaptive RAG with intelligent strategy selection",
        )

    def _create_adaptive_workflow(self):
        """Create adaptive RAG workflow with LLM-driven strategy selection"""
        builder = WorkflowBuilder()

        # LLM Strategy Analyzer
        llm_analyzer_id = builder.add_node(
            "LLMAgentNode",
            node_id="rag_strategy_analyzer",
            config={
                "model": self.llm_model,
                "provider": "openai",
                "system_prompt": """You are a RAG strategy expert. Analyze documents and queries to recommend the optimal RAG approach.

Available strategies:
- semantic: Best for narrative content, general Q&A, semantic similarity
- statistical: Best for technical docs, code, structured content, keyword matching
- hybrid: Best for mixed content, combines semantic + statistical (20-30% better performance)
- hierarchical: Best for long documents, structured content with sections/headings

Analyze the input and respond with ONLY a JSON object:
{
    "recommended_strategy": "semantic|statistical|hybrid|hierarchical",
    "reasoning": "Brief explanation of why this strategy is optimal",
    "confidence": 0.0-1.0,
    "fallback_strategy": "backup strategy if primary fails"
}""",
                "prompt_template": """Analyze these documents for optimal RAG strategy:

Document Analysis:
- Count: {document_count}
- Average length: {avg_length} characters
- Has structure (headings/sections): {has_structure}
- Technical content detected: {is_technical}
- Content types: {content_types}

Query (if provided): {query}

Recommend the optimal RAG strategy:""",
            },
        )

        # Document preprocessor for LLM analysis
        preprocessor_id = builder.add_node(
            "PythonCodeNode",
            node_id="document_preprocessor",
            config={
                "code": """
import re

def analyze_for_llm(documents, query=""):
    if not documents:
        return {
            "document_count": 0,
            "avg_length": 0,
            "has_structure": False,
            "is_technical": False,
            "content_types": [],
            "query": query
        }

    # Analyze documents
    total_length = sum(len(doc.get("content", "")) for doc in documents)
    avg_length = total_length / len(documents)

    # Check for structure
    has_structure = any(
        any(keyword in doc.get("content", "").lower()
            for keyword in ["# ", "## ", "### ", "heading", "section", "chapter"])
        for doc in documents
    )

    # Check for technical content
    technical_keywords = ["code", "function", "class", "algorithm", "api", "import", "def ", "return", "variable"]
    is_technical = any(
        any(keyword in doc.get("content", "").lower()
            for keyword in technical_keywords)
        for doc in documents
    )

    # Determine content types
    content_types = []
    if has_structure:
        content_types.append("structured")
    if is_technical:
        content_types.append("technical")
    if avg_length > 2000:
        content_types.append("long_form")
    if len(documents) > 50:
        content_types.append("large_collection")

    return {
        "document_count": len(documents),
        "avg_length": int(avg_length),
        "has_structure": has_structure,
        "is_technical": is_technical,
        "content_types": content_types,
        "query": query,
        "documents": documents
    }

result = analyze_for_llm(documents, query)
"""
            },
        )

        # Strategy executor with switch
        executor_id = builder.add_node(
            "SwitchNode",
            node_id="strategy_executor",
            config={
                "condition_field": "recommended_strategy",
                "routes": {
                    "semantic": "semantic_pipeline",
                    "statistical": "statistical_pipeline",
                    "hybrid": "hybrid_pipeline",
                    "hierarchical": "hierarchical_pipeline",
                },
            },
        )

        # Add strategy pipelines
        semantic_workflow = create_semantic_rag_workflow(self.rag_config)
        statistical_workflow = create_statistical_rag_workflow(self.rag_config)
        hybrid_workflow = create_hybrid_rag_workflow(self.rag_config)
        hierarchical_workflow = create_hierarchical_rag_workflow(self.rag_config)

        semantic_pipeline_id = builder.add_node(
            "WorkflowNode",
            node_id="semantic_pipeline",
            config={"workflow": semantic_workflow.workflow},
        )

        statistical_pipeline_id = builder.add_node(
            "WorkflowNode",
            node_id="statistical_pipeline",
            config={"workflow": statistical_workflow.workflow},
        )

        hybrid_pipeline_id = builder.add_node(
            "WorkflowNode",
            node_id="hybrid_pipeline",
            config={"workflow": hybrid_workflow.workflow},
        )

        hierarchical_pipeline_id = builder.add_node(
            "WorkflowNode",
            node_id="hierarchical_pipeline",
            config={"workflow": hierarchical_workflow.workflow},
        )

        # Results aggregator
        aggregator_id = builder.add_node(
            "PythonCodeNode",
            node_id="results_aggregator",
            config={
                "code": """
def aggregate_adaptive_results(rag_results, llm_decision, preprocessed_data):
    return {
        "results": rag_results,
        "strategy_used": llm_decision.get("recommended_strategy"),
        "llm_reasoning": llm_decision.get("reasoning"),
        "confidence": llm_decision.get("confidence"),
        "document_analysis": {
            "count": preprocessed_data.get("document_count"),
            "avg_length": preprocessed_data.get("avg_length"),
            "content_types": preprocessed_data.get("content_types")
        },
        "adaptive_metadata": {
            "llm_model_used": "gpt-4",
            "strategy_selection_method": "llm_analysis",
            "fallback_available": llm_decision.get("fallback_strategy")
        }
    }

result = aggregate_adaptive_results(rag_results, llm_decision, preprocessed_data)
"""
            },
        )

        # Connect adaptive pipeline
        builder.add_connection(preprocessor_id, "result", llm_analyzer_id, "input")
        builder.add_connection(llm_analyzer_id, "result", executor_id, "input")
        builder.add_connection(
            preprocessor_id, "result", executor_id, "preprocessed_data"
        )

        # Connect executor to strategy pipelines
        builder.add_connection(executor_id, semantic_pipeline_id, route="semantic")
        builder.add_connection(
            executor_id, statistical_pipeline_id, route="statistical"
        )
        builder.add_connection(executor_id, hybrid_pipeline_id, route="hybrid")
        builder.add_connection(
            executor_id, hierarchical_pipeline_id, route="hierarchical"
        )

        # Connect all pipelines to aggregator
        builder.add_connection(
            semantic_pipeline_id, "output", aggregator_id, "rag_results"
        )
        builder.add_connection(
            statistical_pipeline_id, "output", aggregator_id, "rag_results"
        )
        builder.add_connection(
            hybrid_pipeline_id, "output", aggregator_id, "rag_results"
        )
        builder.add_connection(
            hierarchical_pipeline_id, "output", aggregator_id, "rag_results"
        )
        builder.add_connection(llm_analyzer_id, "result", aggregator_id, "llm_decision")
        builder.add_connection(
            preprocessor_id, "result", aggregator_id, "preprocessed_data"
        )

        return builder.build(name="adaptive_rag_workflow")


@register_node()
class RAGPipelineWorkflowNode(WorkflowNode):
    """
    Configurable RAG Pipeline Workflow Node

    Flexible RAG workflow that can be configured for different use cases
    without code changes. Supports all strategies and custom configurations.
    """

    def __init__(
        self,
        name: str = "rag_pipeline",
        default_strategy: str = "hybrid",
        config: Optional[RAGConfig] = None,
    ):
        self.rag_config = config or RAGConfig()
        self.default_strategy = default_strategy

        # Build configurable workflow
        workflow = self._create_configurable_workflow()

        super().__init__(
            workflow=workflow,
            name=name,
            description=f"Configurable RAG pipeline with {default_strategy} as default strategy",
        )

    def _create_configurable_workflow(self):
        """Create configurable RAG workflow"""
        builder = WorkflowBuilder()

        # Configuration processor
        config_processor_id = builder.add_node(
            "PythonCodeNode",
            node_id="config_processor",
            config={
                "code": f"""
def process_config(documents, query="", strategy="{self.default_strategy}", **kwargs):
    # Merge user config with defaults
    processed_config = {{
        "strategy": strategy,
        "documents": documents,
        "query": query,
        "chunk_size": kwargs.get("chunk_size", {self.rag_config.chunk_size}),
        "chunk_overlap": kwargs.get("chunk_overlap", {self.rag_config.chunk_overlap}),
        "embedding_model": kwargs.get("embedding_model", "{self.rag_config.embedding_model}"),
        "retrieval_k": kwargs.get("retrieval_k", {self.rag_config.retrieval_k})
    }}

    return processed_config

result = process_config(documents, **kwargs)
"""
            },
        )

        # Strategy dispatcher
        dispatcher_id = builder.add_node(
            "SwitchNode",
            node_id="strategy_dispatcher",
            config={
                "condition_field": "strategy",
                "routes": {
                    "semantic": "semantic_strategy",
                    "statistical": "statistical_strategy",
                    "hybrid": "hybrid_strategy",
                    "hierarchical": "hierarchical_strategy",
                },
                "default_route": "hybrid_strategy",
            },
        )

        # Add all strategy implementations
        strategies = {
            "semantic": create_semantic_rag_workflow(self.rag_config),
            "statistical": create_statistical_rag_workflow(self.rag_config),
            "hybrid": create_hybrid_rag_workflow(self.rag_config),
            "hierarchical": create_hierarchical_rag_workflow(self.rag_config),
        }

        strategy_ids = {}
        for strategy_name, workflow_node in strategies.items():
            strategy_id = builder.add_node(
                "WorkflowNode",
                node_id=f"{strategy_name}_strategy",
                config={"workflow": workflow_node.workflow},
            )
            strategy_ids[strategy_name] = strategy_id

        # Results formatter
        formatter_id = builder.add_node(
            "PythonCodeNode",
            node_id="results_formatter",
            config={
                "code": """
def format_pipeline_results(results, config):
    return {
        "results": results,
        "strategy_used": config.get("strategy"),
        "configuration": config,
        "pipeline_type": "configurable",
        "success": True if results else False
    }

result = format_pipeline_results(strategy_results, processed_config)
"""
            },
        )

        # Connect configurable pipeline
        builder.add_connection(config_processor_id, "result", dispatcher_id, "input")

        # Connect dispatcher to all strategies
        for strategy_name, strategy_id in strategy_ids.items():
            builder.add_connection(
                dispatcher_id, strategy_id, route=f"{strategy_name}_strategy"
            )
            builder.add_connection(
                strategy_id, "output", formatter_id, "strategy_results"
            )

        builder.add_connection(
            config_processor_id, "result", formatter_id, "processed_config"
        )

        return builder.build(name="configurable_rag_pipeline")
