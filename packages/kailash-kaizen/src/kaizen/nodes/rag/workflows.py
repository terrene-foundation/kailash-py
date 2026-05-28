"""
RAG Workflow Nodes

Pre-built WorkflowNode components that combine multiple RAG strategies
and operations into reusable workflow patterns.
"""

import logging
import os
from typing import Optional

from kailash.nodes.base import register_node
from kailash.nodes.logic.workflow import WorkflowNode
from kailash.workflow.builder import WorkflowBuilder

from .strategies import (
    RAGConfig,
    create_hierarchical_rag_workflow,
    create_hybrid_rag_workflow,
    create_semantic_rag_workflow,
    create_statistical_rag_workflow,
)

logger = logging.getLogger(__name__)


# F9 #1126: env-loaded default LLM model. Mirrors the router.py precedent
# (F8 B10). May be None when neither env var is set — that is
# env-models-compliant; do NOT fall back to a hardcoded model name.
_DEFAULT_LLM_MODEL = os.environ.get(
    "OPENAI_PROD_MODEL", os.environ.get("DEFAULT_LLM_MODEL")
)


@register_node()
class SimpleRAGWorkflowNode(WorkflowNode):
    """
    Simple RAG Workflow Node

    Basic chunk → embed → store → retrieve pipeline using semantic chunking.
    Perfect for getting started with RAG or simple document Q&A.

    Inputs
    ------
    text : str
        Document text to chunk + embed + store. Routed to the inner-graph
        ``semantic_chunker`` via ``input_mapping`` (see __init__).

    The mapping makes the workflow self-sufficient at the public API surface:
    callers invoke ``node.execute(text="...")`` and the inner-graph chunker
    receives ``text`` without the caller having to know inner-graph node IDs.
    """

    def __init__(
        self, name: str = "simple_rag_workflow", config: Optional[RAGConfig] = None
    ):
        self.rag_config = config or RAGConfig()

        # Create semantic RAG workflow
        workflow_node = create_semantic_rag_workflow(self.rag_config)

        # Initialize as WorkflowNode.
        # `# type: ignore[attr-defined]` on every `.workflow` access in this
        # module: @register_node erases the concrete WorkflowNode type to base
        # Node, so a static checker does not see `.workflow` — but it IS a real
        # read-only WorkflowNode property (added by shard A3) and resolves at
        # runtime. (Known Core SDK type-erasure gap; B1-B6 worked around it the
        # same way at the call site.)
        #
        # ``input_mapping`` routes the public ``text`` parameter to the
        # inner-graph ``semantic_chunker`` node's ``text`` parameter. Without
        # this mapping the inner graph's chunker has no source for ``text`` —
        # ``LocalRuntime`` raises ``WorkflowValidationError`` on execute. The
        # entry-node parameter MUST be exposed via the WorkflowNode facade so
        # users don't have to learn inner-graph node IDs to invoke the
        # workflow.
        super().__init__(
            workflow=workflow_node.workflow,  # type: ignore[attr-defined]
            name=name,
            description="Simple RAG workflow with semantic chunking and dense retrieval",
            input_mapping={
                "text": {
                    "node": "semantic_chunker",
                    "parameter": "text",
                    "type": str,
                    "required": True,
                    "description": "Document text to chunk + embed + store",
                }
            },
        )


@register_node()
class AdvancedRAGWorkflowNode(WorkflowNode):
    """
    Advanced RAG Workflow Node

    Multi-stage RAG pipeline with quality checks, multiple retrieval strategies,
    and result validation. Includes monitoring and performance optimization.

    Inputs
    ------
    documents : list
        Document list to analyze + route through the quality-driven RAG
        strategy. Routed to the inner-graph ``quality_analyzer`` via
        ``input_mapping`` (see __init__).

    The mapping makes the workflow self-sufficient at the public API
    surface: callers invoke ``node.execute(documents=[...])`` and the
    inner-graph quality analyzer receives ``documents`` without the
    caller having to know inner-graph node IDs.
    """

    def __init__(
        self, name: str = "advanced_rag_workflow", config: Optional[RAGConfig] = None
    ):
        self.rag_config = config or RAGConfig()

        # Build advanced workflow
        workflow = self._create_advanced_workflow()

        # ``input_mapping`` routes the public ``documents`` parameter to the
        # inner-graph ``quality_analyzer`` node's ``documents`` parameter.
        # Without this mapping the facade auto-derives ``quality_analyzer_
        # documents`` (node_id + ``_`` + param_name) — users would have to
        # know the inner-graph node ID to invoke the workflow. Per F25 Shard D
        # (same defect class as SimpleRAGWorkflowNode F25 Shard C): the entry
        # parameter MUST be exposed via the WorkflowNode facade so users
        # don't have to learn inner-graph node IDs to invoke the workflow.
        super().__init__(
            workflow=workflow,
            name=name,
            description="Advanced RAG with quality checks and multi-stage processing",
            input_mapping={
                "documents": {
                    "node": "quality_analyzer",
                    "parameter": "documents",
                    "type": list,
                    "required": True,
                    "description": "Documents to analyze + route through quality-driven RAG strategy",
                }
            },
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
    # `_content` is a nested local (PythonCodeNode execs the body in a scope
    # where module-level defs are not visible to nested genexprs). A
    # present-but-None `content` key returns None from dict.get(..., ""), so
    # `or ""` is required; non-dict elements are filtered out first.
    def _content(doc):
        return (doc.get("content") or "") if isinstance(doc, dict) else ""

    documents = [d for d in (documents or []) if isinstance(d, dict)]
    analysis = {
        "total_docs": len(documents),
        "avg_length": sum(len(_content(doc)) for doc in documents) / len(documents) if documents else 0,
        "has_structure": any("section" in doc or "heading" in doc for doc in documents),
        "is_technical": any(keyword in _content(doc).lower()
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

        # Strategy router using switch node.
        # SwitchNode multi-case mode: `cases` is the list of values to match on
        # the `condition_field`; each match is emitted on a `case_<value>`
        # output port (see kailash SwitchNode._sanitize_case_name). The four
        # strategy names contain no characters that sanitize, so the ports are
        # `case_semantic` / `case_statistical` / `case_hybrid` /
        # `case_hierarchical`.
        router_id = builder.add_node(
            "SwitchNode",
            node_id="strategy_router",
            config={
                "condition_field": "recommended_strategy",
                "cases": ["semantic", "statistical", "hybrid", "hierarchical"],
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
            config={"workflow": semantic_workflow.workflow},  # type: ignore[attr-defined]
        )

        statistical_id = builder.add_node(
            "WorkflowNode",
            node_id="statistical_rag_pipeline",
            config={"workflow": statistical_workflow.workflow},  # type: ignore[attr-defined]
        )

        hybrid_id = builder.add_node(
            "WorkflowNode",
            node_id="hybrid_rag_pipeline",
            config={"workflow": hybrid_workflow.workflow},  # type: ignore[attr-defined]
        )

        hierarchical_id = builder.add_node(
            "WorkflowNode",
            node_id="hierarchical_rag_pipeline",
            config={"workflow": hierarchical_workflow.workflow},  # type: ignore[attr-defined]
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

        # Connect the advanced pipeline. SwitchNode's primary input port is
        # `input_data`; each multi-case match emits on `case_<value>`.
        builder.add_connection(quality_analyzer_id, "result", router_id, "input_data")

        # Connect router to all strategy pipelines via the per-case output ports.
        builder.add_connection(router_id, "case_semantic", semantic_id, "input")
        builder.add_connection(router_id, "case_statistical", statistical_id, "input")
        builder.add_connection(router_id, "case_hybrid", hybrid_id, "input")
        builder.add_connection(router_id, "case_hierarchical", hierarchical_id, "input")

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

    Inputs
    ------
    documents : list
        Document list to analyze for adaptive strategy selection. Routed
        to the inner-graph ``document_preprocessor`` via ``input_mapping``.
    query : str, optional
        Query text passed alongside ``documents`` for LLM-driven strategy
        selection. Defaults to ``""`` (matches preprocessor codegen
        default). Also routed via ``input_mapping``.

    The mapping makes the workflow self-sufficient at the public API
    surface: callers invoke ``node.execute(documents=[...], query="...")``
    and the inner-graph preprocessor receives both without the caller
    having to know inner-graph node IDs.
    """

    def __init__(
        self,
        name: str = "adaptive_rag_workflow",
        llm_model: Optional[str] = _DEFAULT_LLM_MODEL,
        config: Optional[RAGConfig] = None,
    ):
        self.rag_config = config or RAGConfig()
        self.llm_model = llm_model

        # Build adaptive workflow
        workflow = self._create_adaptive_workflow()

        # ``input_mapping`` routes the public ``documents`` + ``query``
        # parameters to the inner-graph ``document_preprocessor`` node's
        # ``documents`` / ``query`` parameters. Without this mapping the
        # facade auto-derives ``document_preprocessor_documents`` /
        # ``document_preprocessor_query`` — users would have to know the
        # inner-graph node ID to invoke the workflow. Per F25 Shard D
        # (same defect class as SimpleRAGWorkflowNode F25 Shard C).
        super().__init__(
            workflow=workflow,
            name=name,
            description="AI-driven adaptive RAG with intelligent strategy selection",
            input_mapping={
                "documents": {
                    "node": "document_preprocessor",
                    "parameter": "documents",
                    "type": list,
                    "required": True,
                    "description": "Documents to analyze for adaptive strategy selection",
                },
                "query": {
                    "node": "document_preprocessor",
                    "parameter": "query",
                    "type": str,
                    "required": False,
                    "default": "",
                    "description": "Query text for LLM-driven strategy selection",
                },
            },
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
    # `_content` is a nested local (PythonCodeNode execs the body in a scope
    # where module-level defs are not visible to nested genexprs). A
    # present-but-None `content` key returns None from dict.get(..., ""), so
    # `or ""` is required; non-dict elements are filtered out first.
    def _content(doc):
        return (doc.get("content") or "") if isinstance(doc, dict) else ""

    documents = [d for d in (documents or []) if isinstance(d, dict)]
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
    total_length = sum(len(_content(doc)) for doc in documents)
    avg_length = total_length / len(documents)

    # Check for structure
    has_structure = any(
        any(keyword in _content(doc).lower()
            for keyword in ["# ", "## ", "### ", "heading", "section", "chapter"])
        for doc in documents
    )

    # Check for technical content
    technical_keywords = ["code", "function", "class", "algorithm", "api", "import", "def ", "return", "variable"]
    is_technical = any(
        any(keyword in _content(doc).lower()
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
                "cases": ["semantic", "statistical", "hybrid", "hierarchical"],
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
            config={"workflow": semantic_workflow.workflow},  # type: ignore[attr-defined]
        )

        statistical_pipeline_id = builder.add_node(
            "WorkflowNode",
            node_id="statistical_pipeline",
            config={"workflow": statistical_workflow.workflow},  # type: ignore[attr-defined]
        )

        hybrid_pipeline_id = builder.add_node(
            "WorkflowNode",
            node_id="hybrid_pipeline",
            config={"workflow": hybrid_workflow.workflow},  # type: ignore[attr-defined]
        )

        hierarchical_pipeline_id = builder.add_node(
            "WorkflowNode",
            node_id="hierarchical_pipeline",
            config={"workflow": hierarchical_workflow.workflow},  # type: ignore[attr-defined]
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
            # F9 #1126: this dict lives inside a PythonCodeNode codegen
            # body exec'd in a fresh namespace; the workflows.py
            # module-scope `_DEFAULT_LLM_MODEL` is NOT visible inside the
            # exec scope. Emit a documented sentinel; downstream consumers
            # read the actual model from the upstream LLMAgentNode config.
            "llm_model_used": "<env-default>",
            "strategy_selection_method": "llm_analysis",
            "fallback_available": llm_decision.get("fallback_strategy")
        }
    }

result = aggregate_adaptive_results(rag_results, llm_decision, preprocessed_data)
"""
            },
        )

        # Connect adaptive pipeline. SwitchNode's primary input port is
        # `input_data`; each multi-case match emits on `case_<value>`.
        builder.add_connection(preprocessor_id, "result", llm_analyzer_id, "input")
        builder.add_connection(llm_analyzer_id, "result", executor_id, "input_data")
        builder.add_connection(
            preprocessor_id, "result", executor_id, "preprocessed_data"
        )

        # Connect executor to strategy pipelines via the per-case output ports.
        builder.add_connection(
            executor_id, "case_semantic", semantic_pipeline_id, "input"
        )
        builder.add_connection(
            executor_id, "case_statistical", statistical_pipeline_id, "input"
        )
        builder.add_connection(executor_id, "case_hybrid", hybrid_pipeline_id, "input")
        builder.add_connection(
            executor_id, "case_hierarchical", hierarchical_pipeline_id, "input"
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

    Inputs
    ------
    documents : list
        Document list to process through the configurable RAG pipeline.
        Routed to the inner-graph ``config_processor`` via ``input_mapping``.
    query : str, optional
        Query text for retrieval. Defaults to ``""`` (matches the
        processor codegen default). Routed via ``input_mapping``.
    strategy : str, optional
        Strategy selection (``semantic`` / ``statistical`` / ``hybrid`` /
        ``hierarchical``). Defaults to the class's ``default_strategy``
        argument. Routed via ``input_mapping``.

    The mapping makes the workflow self-sufficient at the public API
    surface: callers invoke ``node.execute(documents=[...])`` and the
    inner-graph processor receives the inputs without the caller having
    to know inner-graph node IDs.
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

        # ``input_mapping`` routes the public ``documents`` + ``query`` +
        # ``strategy`` parameters to the inner-graph ``config_processor``
        # node's ``documents`` / ``query`` / ``strategy`` parameters.
        # Without this mapping the facade auto-derives ``config_processor_
        # documents`` / ``config_processor_query`` / ``config_processor_
        # strategy`` — users would have to know the inner-graph node ID to
        # invoke the workflow. Per F25 Shard D (same defect class as
        # SimpleRAGWorkflowNode F25 Shard C).
        super().__init__(
            workflow=workflow,
            name=name,
            description=f"Configurable RAG pipeline with {default_strategy} as default strategy",
            input_mapping={
                "documents": {
                    "node": "config_processor",
                    "parameter": "documents",
                    "type": list,
                    "required": True,
                    "description": "Documents to process through the configurable RAG pipeline",
                },
                "query": {
                    "node": "config_processor",
                    "parameter": "query",
                    "type": str,
                    "required": False,
                    "default": "",
                    "description": "Query text for retrieval",
                },
                "strategy": {
                    "node": "config_processor",
                    "parameter": "strategy",
                    "type": str,
                    "required": False,
                    "default": default_strategy,
                    "description": "Strategy selection: semantic / statistical / hybrid / hierarchical",
                },
            },
        )

    def _create_configurable_workflow(self):
        """Create configurable RAG workflow"""
        builder = WorkflowBuilder()

        # Configuration processor.
        #
        # F25 Shard D sibling-sweep fix (autonomous-execution.md MUST Rule 4
        # — same-bug-class fix surfaced during the entry-wiring sweep):
        # the prior codegen ended with ``result = process_config(documents,
        # **kwargs)`` but ``kwargs`` is NOT defined in the PythonCodeNode
        # exec scope (PythonCodeNode binds explicit input parameters as
        # locals — ``documents``, ``query``, ``strategy`` — not a kwargs
        # dict). Every invocation raised ``NameError: name 'kwargs' is
        # not defined`` at the entry node.
        #
        # The fix constructs the config dict directly without the wrapper
        # function + undefined ``**kwargs`` unpacking. The default values
        # (chunk_size / overlap / embedding_model / retrieval_k) are
        # interpolated from ``self.rag_config`` at workflow-build time,
        # matching the original codegen's behavior when no override is
        # supplied. PythonCodeNode does not expose a kwargs dict, so the
        # original codegen's "user can override chunk_size at runtime"
        # contract was never reachable through this PythonCodeNode anyway
        # — the override path is via ``config: RAGConfig`` at construction
        # time, which IS preserved.
        config_processor_id = builder.add_node(
            "PythonCodeNode",
            node_id="config_processor",
            config={
                "code": f"""
processed_config = {{
    "strategy": strategy if strategy else "{self.default_strategy}",
    "documents": documents,
    "query": query if query else "",
    "chunk_size": {self.rag_config.chunk_size},
    "chunk_overlap": {self.rag_config.chunk_overlap},
    "embedding_model": "{self.rag_config.embedding_model}",
    "retrieval_k": {self.rag_config.retrieval_k},
}}

result = processed_config
"""
            },
        )

        # Strategy dispatcher
        dispatcher_id = builder.add_node(
            "SwitchNode",
            node_id="strategy_dispatcher",
            config={
                "condition_field": "strategy",
                "cases": ["semantic", "statistical", "hybrid", "hierarchical"],
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
                config={"workflow": workflow_node.workflow},  # type: ignore[attr-defined]
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

        # Connect configurable pipeline. SwitchNode's primary input port is
        # `input_data`; each multi-case match emits on `case_<value>` where
        # `<value>` is the matched `strategy` field value.
        builder.add_connection(
            config_processor_id, "result", dispatcher_id, "input_data"
        )

        # Connect dispatcher to all strategies via the per-case output ports.
        for strategy_name, strategy_id in strategy_ids.items():
            builder.add_connection(
                dispatcher_id, f"case_{strategy_name}", strategy_id, "input"
            )
            builder.add_connection(
                strategy_id, "output", formatter_id, "strategy_results"
            )

        builder.add_connection(
            config_processor_id, "result", formatter_id, "processed_config"
        )

        return builder.build(name="configurable_rag_pipeline")
