"""
RAG Strategy Workflow Nodes

RAG strategies implemented as WorkflowNodes that encapsulate complete
RAG pipelines using existing Kailash components. Each strategy creates
a workflow using WorkflowBuilder and delegates all execution to the SDK.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from kailash.nodes.base import Node, NodeParameter, register_node

# PythonCodeNode is imported for BOTH its @register_node side effect (the inner
# graphs reference it by string in add_node(...)) AND its `from_function`
# classmethod: the COMPUTE-stage nodes below are wired via
# `PythonCodeNode.from_function(<module_fn>)` (Wave 3 Shard S5b — #1117
# publish-nothing / #1123 brace-escape / #1118 import-trap root-cause fix),
# never via an inline source-string body.
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic.workflow import WorkflowNode

# Registering import: kailash uses a lazy module cache, so the
# `@register_node()` decorators on SemanticChunkerNode / StatisticalChunkerNode /
# HierarchicalChunkerNode fire only when `kailash.nodes.transform.chunkers` is
# actually imported. The `create_*_rag_workflow` builders below reference those
# node types by string in `add_node(...)`; importing the module here ensures the
# registry is populated before any `_create_workflow()` runs.
from kailash.nodes.transform import chunkers as _chunkers  # noqa: F401
from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)


@dataclass
class RAGConfig:
    """Configuration for RAG strategies"""

    chunk_size: int = 1000
    chunk_overlap: int = 200
    embedding_model: str = "text-embedding-3-small"
    embedding_provider: str = "openai"
    vector_db_provider: str = "postgresql"
    retrieval_k: int = 5
    similarity_threshold: float = 0.7


# ==========================================================================
# Wave 3 Shard S5b — COMPUTE-stage `from_function` targets lifted from the
# prior PythonCodeNode `"code"` strings (#1117 publish-nothing / #1123
# brace-escape / #1118 import-trap root-cause fix). Each function is a real
# module-level def wired via `PythonCodeNode.from_function(fn)`; the node
# publishes its `return` on the SINGLE flat `result` port (the downstream
# `add_connection(..., "result", ...)` edges read that port). The bodies are
# behavior-equivalent to the codegen they replace.
# ==========================================================================

# Stop-word set shared by the statistical keyword extractor (was an inline
# literal in the prior codegen body).
_KEYWORD_STOP_WORDS = {
    "the",
    "and",
    "for",
    "are",
    "but",
    "not",
    "you",
    "all",
    "can",
    "had",
    "her",
    "was",
    "one",
    "our",
    "out",
    "day",
    "get",
    "has",
    "him",
    "his",
    "how",
    "man",
    "new",
    "now",
    "old",
    "see",
    "two",
    "way",
    "who",
    "boy",
    "did",
    "its",
    "let",
    "put",
    "say",
    "she",
    "too",
    "use",
}


def _extract_keywords(chunks=None) -> dict:
    """Sparse keyword extraction over the chunk corpus (statistical RAG).

    Was the ``keyword_extractor`` ``code`` string. Reads the ``chunks`` input
    (list of dicts), extracts 3+-letter alpha tokens minus stop-words, capped
    at 20 per chunk. A present-but-None ``content`` value is coerced to ``""``
    so ``.lower()`` never crashes; non-dict elements are filtered. Publishes the
    flat ``{"keywords": [...]}`` dict on the from_function ``result`` port — the
    downstream ``vector_db`` reads it as its ``keywords`` input.
    """

    def extract(text) -> list:
        # A present-but-None `content` key would otherwise crash text.lower().
        words = re.findall(r"\b[a-zA-Z]{3,}\b", (text or "").lower())
        keywords = [word for word in set(words) if word not in _KEYWORD_STOP_WORDS]
        return keywords[:20]

    return {
        "keywords": [
            extract(chunk.get("content"))
            for chunk in (chunks or [])
            if isinstance(chunk, dict)
        ]
    }


def _make_result_fusion(*, fusion_method: str):
    """Build a from_function-compatible ``result_fusion`` bound to the build-time
    ``fusion_method`` (hybrid RAG).

    Closure-bound factory (the #1123 brace-escape / #1118 import-trap root-cause
    fix): the prior ``result_fusion`` was an f-STRING codegen interpolating the
    ``fusion_method`` literal into the ``code`` body (doubled ``{{`` braces).
    Lifting to a real function with ``fusion_method`` captured in a closure
    removes the f-string + brace-escape surface entirely while preserving the
    SAME behavior — the value is bound as a Python object, never re-rendered into
    source text.

    The returned function declares ``semantic_results`` / ``statistical_results``
    as its explicit inputs (the ports the prior codegen read as locals) and
    returns the flat ``{"fused_results": ...}`` dict on the from_function
    ``result`` port (terminal — no downstream edge reads it).
    """

    def _fuse(semantic_results=None, statistical_results=None) -> dict:
        def rrf_fusion(semantic, statistical, k=60) -> dict:
            """Reciprocal Rank Fusion for combining results."""
            doc_scores: dict = {}

            # Add semantic results
            semantic = semantic if isinstance(semantic, dict) else {}
            for i, doc in enumerate(semantic.get("results", [])):
                doc_id = doc.get("id", f"semantic_{i}")
                doc_scores[doc_id] = {
                    "document": doc,
                    "score": 1 / (k + i + 1),
                    "sources": ["semantic"],
                }

            # Add statistical results
            statistical = statistical if isinstance(statistical, dict) else {}
            for i, doc in enumerate(statistical.get("results", [])):
                doc_id = doc.get("id", f"statistical_{i}")
                if doc_id in doc_scores:
                    doc_scores[doc_id]["score"] += 1 / (k + i + 1)
                    doc_scores[doc_id]["sources"].append("statistical")
                else:
                    doc_scores[doc_id] = {
                        "document": doc,
                        "score": 1 / (k + i + 1),
                        "sources": ["statistical"],
                    }

            # Sort by fused score
            sorted_results = sorted(
                doc_scores.items(), key=lambda x: x[1]["score"], reverse=True
            )

            return {
                "documents": [item[1]["document"] for item in sorted_results[:5]],
                "scores": [item[1]["score"] for item in sorted_results[:5]],
                "fusion_method": fusion_method,
            }

        fusion_results = rrf_fusion(semantic_results, statistical_results)
        return {"fused_results": fusion_results}

    _fuse.__name__ = "result_fusion"
    _fuse.__doc__ = "Combine semantic + statistical results via rank fusion."
    return _fuse


def _process_levels(chunks=None) -> dict:
    """Organize chunks by hierarchy level (hierarchical RAG).

    Was the ``level_processor`` ``code`` string. Buckets the ``chunks`` input
    into document/section/paragraph levels by each chunk's ``hierarchy_level``
    key; non-dict elements are filtered. Publishes the flat
    ``{"level_chunks": {...}, "levels": [...]}`` dict on the from_function
    ``result`` port — each of the three ``vector_db`` nodes reads it as its
    ``level_chunks`` input.
    """
    levels = ["document", "section", "paragraph"]
    _chunks = [c for c in (chunks or []) if isinstance(c, dict)]

    level_chunks = {
        level: [chunk for chunk in _chunks if chunk.get("hierarchy_level") == level]
        for level in levels
    }

    return {"level_chunks": level_chunks, "levels": levels}


def create_semantic_rag_workflow(config: RAGConfig) -> WorkflowNode:
    """
    Create semantic RAG workflow using existing Kailash nodes.

    Pipeline: Documents → SemanticChunker → EmbeddingGenerator → VectorDatabase → HybridRetriever
    """
    builder = WorkflowBuilder()

    # Add chunking node
    chunker_id = builder.add_node(
        "SemanticChunkerNode",
        node_id="semantic_chunker",
        config={
            "chunk_size": config.chunk_size,
            "chunk_overlap": config.chunk_overlap,
            "similarity_threshold": config.similarity_threshold,
        },
    )

    # Add embedding generation
    embedder_id = builder.add_node(
        "EmbeddingGeneratorNode",
        node_id="embedder",
        config={"model": config.embedding_model, "provider": config.embedding_provider},
    )

    # Add vector database storage
    vectordb_id = builder.add_node(
        "VectorDatabaseNode",
        node_id="vector_db",
        config={
            "provider": config.vector_db_provider,
            "collection_name": "semantic_rag",
        },
    )

    # Add retrieval node
    retriever_id = builder.add_node(
        "HybridRetrieverNode",
        node_id="retriever",
        config={
            "k": config.retrieval_k,
            "similarity_threshold": config.similarity_threshold,
            "method": "dense",
        },
    )

    # Connect the pipeline
    builder.add_connection(chunker_id, "chunks", embedder_id, "texts")
    builder.add_connection(embedder_id, "embeddings", vectordb_id, "embeddings")
    builder.add_connection(chunker_id, "chunks", vectordb_id, "documents")
    builder.add_connection(
        vectordb_id, "stored_documents", retriever_id, "document_store"
    )

    # Build workflow
    workflow = builder.build(name="semantic_rag_workflow")

    # Return as WorkflowNode
    return WorkflowNode(
        workflow=workflow,
        name="semantic_rag_node",
        description="Semantic RAG with dense embeddings and semantic chunking",
    )


def create_statistical_rag_workflow(config: RAGConfig) -> WorkflowNode:
    """
    Create statistical RAG workflow using existing Kailash nodes.

    Pipeline: Documents → StatisticalChunker → EmbeddingGenerator → VectorDatabase → HybridRetriever (sparse)
    """
    builder = WorkflowBuilder()

    # Add statistical chunking
    chunker_id = builder.add_node(
        "StatisticalChunkerNode",
        node_id="statistical_chunker",
        config={"chunk_size": config.chunk_size, "overlap": config.chunk_overlap},
    )

    # Add embedding generation (for backup dense retrieval)
    embedder_id = builder.add_node(
        "EmbeddingGeneratorNode",
        node_id="embedder",
        config={"model": config.embedding_model, "provider": config.embedding_provider},
    )

    # Add keyword extraction for sparse retrieval
    # `_extract_keywords` function wired via `PythonCodeNode.from_function`. The
    # node publishes its `{"keywords": [...]}` return on the flat `result` port;
    # the `vector_db` reads it via the `keyword_extractor → keywords` edge below.
    # `_internal=True` suppresses the consumer-facing instance-API advisory
    # (SDK-internal construction path, mirrors optimized.py).
    keyword_extractor_id = builder.add_node_instance(
        PythonCodeNode.from_function(
            _extract_keywords,
            name="keyword_extractor",
        ),
        node_id="keyword_extractor",
        _internal=True,
    )

    # Add vector database
    vectordb_id = builder.add_node(
        "VectorDatabaseNode",
        node_id="vector_db",
        config={
            "provider": config.vector_db_provider,
            "collection_name": "statistical_rag",
        },
    )

    # Add sparse retrieval
    retriever_id = builder.add_node(
        "HybridRetrieverNode",
        node_id="retriever",
        config={"k": config.retrieval_k, "method": "sparse"},
    )

    # Connect pipeline
    builder.add_connection(chunker_id, "chunks", keyword_extractor_id, "chunks")
    builder.add_connection(chunker_id, "chunks", embedder_id, "texts")
    builder.add_connection(keyword_extractor_id, "result", vectordb_id, "keywords")
    builder.add_connection(embedder_id, "embeddings", vectordb_id, "embeddings")
    builder.add_connection(chunker_id, "chunks", vectordb_id, "documents")
    builder.add_connection(
        vectordb_id, "stored_documents", retriever_id, "document_store"
    )

    workflow = builder.build(name="statistical_rag_workflow")

    return WorkflowNode(
        workflow=workflow,
        name="statistical_rag_node",
        description="Statistical RAG with sparse retrieval and keyword matching",
    )


def create_hybrid_rag_workflow(
    config: RAGConfig, fusion_method: str = "rrf"
) -> WorkflowNode:
    """
    Create hybrid RAG workflow combining semantic and statistical approaches.

    Pipeline: Documents → [SemanticRAG + StatisticalRAG] → ResultFuser → HybridRetriever
    """
    builder = WorkflowBuilder()

    # Create both semantic and statistical sub-workflows
    semantic_workflow = create_semantic_rag_workflow(config)
    statistical_workflow = create_statistical_rag_workflow(config)

    # Add sub-workflows as nodes.
    # `# type: ignore[attr-defined]` on each `.workflow` access below:
    # @register_node erases the concrete WorkflowNode type to base Node, so a
    # static checker does not see `.workflow` — but it IS a real read-only
    # WorkflowNode property (added by shard A3) and resolves at runtime.
    semantic_id = builder.add_node(
        "WorkflowNode",
        node_id="semantic_rag",
        config={"workflow": semantic_workflow.workflow},  # type: ignore[attr-defined]
    )

    statistical_id = builder.add_node(
        "WorkflowNode",
        node_id="statistical_rag",
        config={"workflow": statistical_workflow.workflow},  # type: ignore[attr-defined]
    )

    # Add result fusion node.
    #
    # #1117/#1123/#1118 root-cause fix: lifted to the closure-bound
    # `_make_result_fusion` factory wired via `PythonCodeNode.from_function`,
    # with the build-time `fusion_method` bound into the closure (no f-string
    # interpolation / brace-escape surface). The node publishes its
    # `{"fused_results": {...}}` return on the flat `result` port (terminal — no
    # downstream edge reads it). `_internal=True` suppresses the consumer-facing
    # instance-API advisory (SDK-internal construction path, mirrors
    # optimized.py).
    fusion_id = builder.add_node_instance(
        PythonCodeNode.from_function(
            _make_result_fusion(fusion_method=fusion_method),
            name="result_fusion",
        ),
        node_id="result_fusion",
        _internal=True,
    )

    # Connect workflows to fusion
    builder.add_connection(semantic_id, "output", fusion_id, "semantic_results")
    builder.add_connection(statistical_id, "output", fusion_id, "statistical_results")

    workflow = builder.build(name="hybrid_rag_workflow")

    return WorkflowNode(
        workflow=workflow,
        name="hybrid_rag_node",
        description=f"Hybrid RAG with {fusion_method} fusion combining semantic and statistical approaches",
    )


def create_hierarchical_rag_workflow(config: RAGConfig) -> WorkflowNode:
    """
    Create hierarchical RAG workflow for multi-level document processing.

    Pipeline: Documents → HierarchicalChunker → Multi-level Embedding → Multi-collection Storage → Hierarchical Retrieval
    """
    builder = WorkflowBuilder()

    # Add hierarchical chunking
    chunker_id = builder.add_node(
        "HierarchicalChunkerNode",
        node_id="hierarchical_chunker",
        config={"chunk_size": config.chunk_size, "overlap": config.chunk_overlap},
    )

    # Add embedding for each level
    embedder_id = builder.add_node(
        "EmbeddingGeneratorNode",
        node_id="embedder",
        config={"model": config.embedding_model, "provider": config.embedding_provider},
    )

    # Add level processor for organizing chunks by hierarchy
    # `_process_levels` function wired via `PythonCodeNode.from_function`. The
    # node publishes its `{"level_chunks": {...}, "levels": [...]}` return on the
    # flat `result` port; the three `vector_db` nodes read it via the
    # `level_processor → level_chunks` edges below. `_internal=True` suppresses
    # the consumer-facing instance-API advisory (mirrors optimized.py).
    level_processor_id = builder.add_node_instance(
        PythonCodeNode.from_function(
            _process_levels,
            name="level_processor",
        ),
        node_id="level_processor",
        _internal=True,
    )

    # Add vector databases for each level
    doc_vectordb_id = builder.add_node(
        "VectorDatabaseNode",
        node_id="doc_vector_db",
        config={
            "provider": config.vector_db_provider,
            "collection_name": "hierarchical_rag_document",
        },
    )

    section_vectordb_id = builder.add_node(
        "VectorDatabaseNode",
        node_id="section_vector_db",
        config={
            "provider": config.vector_db_provider,
            "collection_name": "hierarchical_rag_section",
        },
    )

    para_vectordb_id = builder.add_node(
        "VectorDatabaseNode",
        node_id="para_vector_db",
        config={
            "provider": config.vector_db_provider,
            "collection_name": "hierarchical_rag_paragraph",
        },
    )

    # Add hierarchical retriever
    retriever_id = builder.add_node(
        "HybridRetrieverNode",
        node_id="hierarchical_retriever",
        config={"k": config.retrieval_k, "method": "hierarchical"},
    )

    # Connect pipeline
    builder.add_connection(chunker_id, "chunks", level_processor_id, "chunks")
    builder.add_connection(chunker_id, "chunks", embedder_id, "texts")
    builder.add_connection(
        level_processor_id, "result", doc_vectordb_id, "level_chunks"
    )
    builder.add_connection(
        level_processor_id, "result", section_vectordb_id, "level_chunks"
    )
    builder.add_connection(
        level_processor_id, "result", para_vectordb_id, "level_chunks"
    )
    builder.add_connection(embedder_id, "embeddings", doc_vectordb_id, "embeddings")
    builder.add_connection(embedder_id, "embeddings", section_vectordb_id, "embeddings")
    builder.add_connection(embedder_id, "embeddings", para_vectordb_id, "embeddings")

    # Connect all vector DBs to retriever
    builder.add_connection(
        doc_vectordb_id, "stored_documents", retriever_id, "document_store"
    )
    builder.add_connection(
        section_vectordb_id, "stored_documents", retriever_id, "section_store"
    )
    builder.add_connection(
        para_vectordb_id, "stored_documents", retriever_id, "paragraph_store"
    )

    workflow = builder.build(name="hierarchical_rag_workflow")

    return WorkflowNode(
        workflow=workflow,
        name="hierarchical_rag_node",
        description="Hierarchical RAG with multi-level document processing and context aggregation",
    )


@register_node()
class SemanticRAGNode(Node):
    """
    Semantic RAG Strategy Node

    Wraps the semantic RAG workflow as a single node for easy integration.
    Uses semantic chunking with dense embeddings for optimal semantic matching.
    """

    def __init__(self, name: str = "semantic_rag", config: Optional[RAGConfig] = None):
        super().__init__(name=name)
        # Node-specific RAG configuration: stored under `rag_config`, NOT
        # `self.config` — the base Node reserves `self.config` for its dict
        # config-bag, and the __init_with_capture wrapper iterates it.
        self.rag_config = config or RAGConfig()
        self.workflow_node = None

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="semantic_rag",
                description="Node instance name",
            ),
            "config": NodeParameter(
                name="config",
                type=dict,
                required=False,
                description="RAG configuration parameters",
            ),
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=True,
                description="Documents to process for semantic RAG",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                description="Query for retrieval",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                default="index",
                description="Operation: 'index' or 'retrieve'",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run semantic RAG using WorkflowNode"""
        if not self.workflow_node:
            self.workflow_node = create_semantic_rag_workflow(self.rag_config)

        # Delegate to WorkflowNode
        return self.workflow_node.execute(**kwargs)


@register_node()
class StatisticalRAGNode(Node):
    """
    Statistical RAG Strategy Node

    Wraps the statistical RAG workflow for sparse keyword-based retrieval.
    Uses statistical chunking with keyword extraction for technical content.
    """

    def __init__(
        self, name: str = "statistical_rag", config: Optional[RAGConfig] = None
    ):
        super().__init__(name=name)
        # Node-specific RAG configuration under `rag_config` (see SemanticRAGNode).
        self.rag_config = config or RAGConfig()
        self.workflow_node = None

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="statistical_rag",
                description="Node instance name",
            ),
            "config": NodeParameter(
                name="config",
                type=dict,
                required=False,
                description="RAG configuration parameters",
            ),
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=True,
                description="Documents to process for statistical RAG",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                description="Query for retrieval",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                default="index",
                description="Operation: 'index' or 'retrieve'",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run statistical RAG using WorkflowNode"""
        if not self.workflow_node:
            self.workflow_node = create_statistical_rag_workflow(self.rag_config)

        return self.workflow_node.execute(**kwargs)


@register_node()
class HybridRAGNode(Node):
    """
    Hybrid RAG Strategy Node

    Combines semantic and statistical approaches using result fusion.
    Provides 20-30% better performance than individual methods.
    """

    def __init__(
        self,
        name: str = "hybrid_rag",
        config: Optional[RAGConfig] = None,
        fusion_method: str = "rrf",
    ):
        super().__init__(name=name, fusion_method=fusion_method)
        # Node-specific RAG configuration under `rag_config` (see SemanticRAGNode).
        self.rag_config = config or RAGConfig()
        self.fusion_method = fusion_method
        self.workflow_node = None

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="hybrid_rag",
                description="Node instance name",
            ),
            "config": NodeParameter(
                name="config",
                type=dict,
                required=False,
                description="RAG configuration parameters",
            ),
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=True,
                description="Documents to process for hybrid RAG",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                description="Query for retrieval",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                default="index",
                description="Operation: 'index' or 'retrieve'",
            ),
            "fusion_method": NodeParameter(
                name="fusion_method",
                type=str,
                default="rrf",
                description="Fusion method: 'rrf', 'linear', 'weighted'",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run hybrid RAG using WorkflowNode"""
        fusion_method = kwargs.get("fusion_method", self.fusion_method)

        if not self.workflow_node or fusion_method != self.fusion_method:
            self.fusion_method = fusion_method
            self.workflow_node = create_hybrid_rag_workflow(
                self.rag_config, fusion_method
            )

        return self.workflow_node.execute(**kwargs)


@register_node()
class HierarchicalRAGNode(Node):
    """
    Hierarchical RAG Strategy Node

    Multi-level document processing that preserves document structure.
    Processes documents at document, section, and paragraph levels.
    """

    def __init__(
        self, name: str = "hierarchical_rag", config: Optional[RAGConfig] = None
    ):
        super().__init__(name=name)
        # Node-specific RAG configuration under `rag_config` (see SemanticRAGNode).
        self.rag_config = config or RAGConfig()
        self.workflow_node = None

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name",
                type=str,
                required=False,
                default="hierarchical_rag",
                description="Node instance name",
            ),
            "config": NodeParameter(
                name="config",
                type=dict,
                required=False,
                description="RAG configuration parameters",
            ),
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=True,
                description="Documents to process hierarchically",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                description="Query for hierarchical retrieval",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                default="index",
                description="Operation: 'index' or 'retrieve'",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run hierarchical RAG using WorkflowNode"""
        if not self.workflow_node:
            self.workflow_node = create_hierarchical_rag_workflow(self.rag_config)

        return self.workflow_node.execute(**kwargs)
